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
    msn_components_status_list, sedor_b737_occm, elal_b767_msn28132,
    georgian_airways_b737,
    aeroflot, aircraft_inventory_report, aircraft_rotables_report,
    aircraft_spec_file_occm, amos,
    cathay_occm, config_slot_occm, iberia_listado, oases,
    occm_list_as_at, occm_status_list, on_condition_components_report,
    remaining_potentials, standard_occm, tap_compact_occm, technical_object_listing,
)
from shared.cleanup import clean_record, forward_fill_ata

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
    elal_b767_msn28132,
    georgian_airways_b737,
    aeroflot, aircraft_inventory_report, aircraft_rotables_report, amos,
    cathay_occm, config_slot_occm, iberia_listado, oases,
    occm_list_as_at, occm_status_list, on_condition_components_report,
    remaining_potentials, standard_occm, tap_compact_occm, technical_object_listing,
]

# Sheet-type level signatures, used by the top-level router (sheet_types/router.py)
SIGNATURES = [
    "OCCM",
    "AVIONIC INSTALLED UNITS",
    "AIRCRAFT EQUIPMENT LIST REPORT",
    "OCCM COMPONENTS STATUS LIST",
    "OCCM STATUS",
    "AIRCRAFT REGISTRATION:",
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


def detect_variant(pdf_path: str) -> str:
    head = _read_head_text(pdf_path).upper()
    # Default to Aeroflot when there's no text layer at all — Aeroflot is
    # currently the only known no-text-layer variant. This will need
    # revisiting when we encounter another scanned-only OCCM, at which point
    # we'd run a tiny page-1 OCR pass to detect signatures.
    if len(head.strip()) < 50:
        return "Aeroflot"
    for v in VARIANTS:
        for sig in v.SIGNATURES:
            if sig.upper() in head:
                return v.NAME
    return "Unknown"


def extract(pdf_path: str, variant_name: str | None = None) -> dict:
    if variant_name is None:
        variant_name = detect_variant(pdf_path)
    v = _BY_NAME.get(variant_name)
    if v is None:
        return {"variant": "Unknown", "columns": [], "records": []}
    records = v.extract(pdf_path)
    return {"variant": v.NAME, "columns": v.CANONICAL_COLUMNS, "records": records}


def normalize_and_validate(records: list[dict], variant_name: str = "Aeroflot") -> list[dict]:
    v = _BY_NAME.get(variant_name, aeroflot)
    cleaned = [clean_record(dict(r), v.RULES) for r in records]
    # Generic post-process: forward-fill ATA chapters across rows. Cheap safety
    # net for variants where ATA only appears on section headings.
    if "ATA" in v.CANONICAL_COLUMNS:
        forward_fill_ata(cleaned)
    return cleaned
