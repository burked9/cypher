"""OCCM router — detects which OCCM variant a PDF is, dispatches to its parser.

Variants live under `sheet_types/occm_variants/`. Each exposes a uniform
interface (NAME, SIGNATURES, CANONICAL_COLUMNS, RULES, extract).

Public functions:
    detect_variant(pdf_path) -> str            — name of detected variant
    extract(pdf_path) -> dict                  — {variant, columns, records}
    normalize_and_validate(records, variant)   — apply per-variant rules
"""
from __future__ import annotations
import pdfplumber

from sheet_types.occm_variants import (
    a330_engineering_planning, aegean_erj_occm, avianca_occm,
    b777_annex7_occm, b777_annex8_occm,
    cca_a340_occm, swiss_a340_occm, a305_a340_occm, on_condition_monitoring_occm,
    msn_components_status_list, sedor_b737_occm, elal_b767_records_package,
    georgian_airways_b737,
    aeroflot, aircraft_inventory_report, aircraft_rotables_report,
    aircraft_spec_file_occm, amos,
    cathay_occm, config_slot_occm, iberia_listado, oases,
    occm_list_as_at, occm_status_list, on_condition_components_report,
    remaining_potentials, standard_occm, tap_compact_occm, technical_object_listing,
    aircraft_components_list, stars_trax_occm, sriwijaya_b737_occm,
    aircraft_inventory_report_scanned, xiamen_b737_installed_components,
    aircraft_rotables_report_scanned, occm_list_for_registration,
    fl_compound_code_occm, occm_tah_tac_at_install, occm_report_scanned,
    occm_report, aircraft_occm_list_scanned,
    occm_summary_list, occm_list_msn_dotdate,
    eastar_jet_occm_list,
)
from shared.cleanup import clean_record, forward_fill_ata
from shared.ocr_bridge import maybe_await

# Specific-format variants must precede generic ones: detection returns the
# first match. Specific airframe/operator variants are listed first.
VARIANTS = [
    aircraft_spec_file_occm,
    aegean_erj_occm,
    a330_engineering_planning,
    avianca_occm,
    b777_annex8_occm,
    b777_annex7_occm,
    cca_a340_occm,
    swiss_a340_occm,
    a305_a340_occm,
    on_condition_monitoring_occm,
    msn_components_status_list,
    sedor_b737_occm,
    elal_b767_records_package,
    georgian_airways_b737,
    fl_compound_code_occm,
    occm_tah_tac_at_install,
    occm_list_msn_dotdate,
    aeroflot, aircraft_inventory_report, aircraft_rotables_report, amos,
    cathay_occm, config_slot_occm, iberia_listado, oases,
    occm_list_as_at, occm_status_list, on_condition_components_report,
    remaining_potentials, standard_occm, tap_compact_occm, technical_object_listing,
    aircraft_components_list, stars_trax_occm, sriwijaya_b737_occm,
    aircraft_inventory_report_scanned, xiamen_b737_installed_components,
    aircraft_rotables_report_scanned, occm_list_for_registration,
    occm_report, occm_report_scanned, aircraft_occm_list_scanned,
    occm_summary_list, eastar_jet_occm_list,
]

# Sheet-type level signatures, used by the top-level router (sheet_types/router.py)
SIGNATURES = [
    "OCCM",
    "AVIONIC INSTALLED UNITS",
    "AIRCRAFT EQUIPMENT LIST REPORT",
    "OCCM COMPONENTS STATUS LIST",
    "OCCM STATUS",
    "AIRCRAFT REGISTRATION:",
    # Variants added later that don't carry "OCCM" in the header text but
    # ARE OCCM-class data. Without these the in-browser top-level router
    # returns "Unknown" on these files and the single-PDF UI shows a
    # confusing "sheet type not recognised" error — even though we have
    # working per-variant parsers for each.
    "PROG. MAN:",                         # TAP Compact OCCM (CS-T**)
    "AIRCRAFT-EQUIPMENT-LIST",            # hyphenated AMOS variant
    "AIRCRAFT COMPONENT LOG",             # Georgian Airways variant
    "Parts Remaining Fitted at Build",    # EL AL B767 records-package
    "Parts Remaining fitted at Build",    # same, case variation
    "I-BIX",                              # Alitalia I-BIX* registrations
    "AIRCRAFT COMPONENTS LIST",           # aircraft_components_list.py
    # stars_trax_occm.py's OTHER signature, "A/C Detail Items Print", is
    # deliberately NOT added here -- it's also ht_variants/stars_trax.py's
    # signature, and the same "STARS/Trax" MIS tool emits it verbatim for
    # both an OCCM-shaped and an HT-shaped export (confirmed no reliable
    # discriminating phrase exists in the header either way, same root
    # cause as the mm510_llp.py gap below). Adding it here would risk
    # silently stealing genuinely-HT files from stars_trax.py, since LLP
    # and HT are both checked before OCCM in router.py's DETECTION_ORDER.
    # This means only the "A/C Status Audit Print"-headed half of
    # stars_trax_occm's cluster is reachable via normal routing today --
    # see docs/TODO.md for the other half and a real fix.
    "A/C Status Audit Print",             # stars_trax_occm.py (partial -- see above)
    # remaining_potentials.py's AMASIS template also emits an HT-flavoured
    # export of the same report ("Protocol Type H/T" in the header);
    # ht.py's own top-level SIGNATURES claims that specific phrase first
    # per DETECTION_ORDER, so this generic phrase is safe here for every
    # other (OCCM-flavoured) export of the same template.
    "Remaining potentials report",
    # occm_report.py's known source file has no "OCCM" text anywhere in it
    # (confirmed via direct inspection) -- its column-header line is the
    # only reliable anchor, and doubles as its own variant-level SIGNATURES
    # entry (checked for collisions against every SIGNATURES list in
    # sheet_types/{occm,ht,llp}.py and every existing variant file).
    "ATA INSTALL DATE POSITION PN SN DESCRIPTION",
    # occm_summary_list.py's own column-header line and title line both
    # contain "OCCM" already, but its variant-level SIGNATURES phrase
    # ("OCCM SUMMARY LIST") is added explicitly too, since it's a more
    # precise anchor than the generic "OCCM" entry above (checked for
    # collisions against every SIGNATURES list in sheet_types/
    # {occm,ht,llp}.py and every existing variant file first).
    "OCCM SUMMARY LIST",
    # sriwijaya_b737_occm.py needs no entry here: its files have no text
    # layer at all (confirmed near-zero chars), so they're only ever
    # reached via the ocr_detect fallback loop below, not this list.
    # occm_report_scanned.py: same reason -- no text layer on its known
    # source file either.
]
_BY_NAME = {v.NAME: v for v in VARIANTS}

# Backwards-compat for code that still imports CANONICAL_COLUMNS from occm.
CANONICAL_COLUMNS = aeroflot.CANONICAL_COLUMNS


def _read_head_text(pdf_path: str, n_pages: int = 3) -> str:
    """Read the first n_pages of text. Uses pdfplumber so the deploy needs
    only one PDF library (avoids the pymupdf binary dependency)."""
    parts = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for p in pdf.pages[:n_pages]:
                parts.append(p.extract_text() or "")
    except Exception:
        pass
    return "\n".join(parts)


async def detect_variant(pdf_path: str) -> str:
    head = _read_head_text(pdf_path).upper()
    for v in VARIANTS:
        for sig in v.SIGNATURES:
            if sig.upper() in head:
                return v.NAME
    if len(head.strip()) < 50:
        # No usable text layer -- ask any OCR-capable variant to confirm its
        # own template via a cheap header OCR pass rather than guessing.
        # This used to default blind to "Aeroflot" (the only OCR variant
        # when that line was written), which meant ANY blank-text PDF got
        # confidently mislabeled "Aeroflot" -- including, in practice, a
        # scanned document that wasn't OCCM at all. Mirrors the same
        # pattern in sheet_types/llp.py and sheet_types/router.py.
        for v in VARIANTS:
            ocr_check = getattr(v, "ocr_detect", None)
            if ocr_check and await maybe_await(ocr_check(pdf_path)):
                return v.NAME
    return "Unknown"


async def extract(pdf_path: str, variant_name: str | None = None) -> dict:
    if variant_name is None:
        variant_name = await detect_variant(pdf_path)
    v = _BY_NAME.get(variant_name)
    if v is None:
        return {"variant": "Unknown", "columns": [], "records": []}
    records = await maybe_await(v.extract(pdf_path))
    return {"variant": v.NAME, "columns": v.CANONICAL_COLUMNS, "records": records}


def normalize_and_validate(records: list[dict], variant_name: str = "Aeroflot") -> list[dict]:
    v = _BY_NAME.get(variant_name, aeroflot)
    cleaned = [clean_record(dict(r), v.RULES) for r in records]
    # Generic post-process: forward-fill ATA chapters across rows. Cheap safety
    # net for variants where ATA only appears on section headings.
    if "ATA" in v.CANONICAL_COLUMNS:
        forward_fill_ata(cleaned)
    return cleaned
