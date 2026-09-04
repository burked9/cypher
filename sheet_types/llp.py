"""LLP (Life Limited Parts) sheet-type router. Mirrors HT/OCCM routers."""
from __future__ import annotations
import pdfplumber

from sheet_types.llp_variants import (
    vietnam_airlines, amos, lan_engine_llp, pro_rata_engine_llp,
    cfm_overhaul_llp, cfm56_7b_llp,
    erj190_landing_gear_llp, n3_engine_overhaul_llp, messier_dowty_landing_gear_llp,
    gear_llp_status_list, emes_airframe_llp_status, serialized_unit_hard_limits,
    cai_first_landing_gear_llp, mm510_llp, swiss_a340_ldg_llp,
    landing_gear_llp_report, aircraft_llp_status_report, sas_drawing_item_llp,
    sky_airlines_llp_summary, b737_gear_llp_inventory, egat_llp_on_log_list,
    ihi_engine_llp_time_cycle_record, elal_internal_parts_list,
    iai_dual_rating_engine_llp, kalstar_engine_llp_status,
    kalstar_aviation_llp_status, thai_landing_gear_llp_status,
    b777_gear_llp_availability, part_m_engine_disk_sheet,
    revima_landing_gear_als_status, powerplant_maintenance_center_llp_status,
    lan_engine_control_fleet_llp, engine_items_control_llp_status,
)
from shared.cleanup import clean_record
from shared.ocr_bridge import maybe_await

VARIANTS = [
    vietnam_airlines, amos, lan_engine_llp, pro_rata_engine_llp,
    cfm_overhaul_llp, cfm56_7b_llp,
    erj190_landing_gear_llp, n3_engine_overhaul_llp, messier_dowty_landing_gear_llp,
    gear_llp_status_list, emes_airframe_llp_status, serialized_unit_hard_limits,
    cai_first_landing_gear_llp, mm510_llp, swiss_a340_ldg_llp,
    landing_gear_llp_report, aircraft_llp_status_report, sas_drawing_item_llp,
    sky_airlines_llp_summary, b737_gear_llp_inventory, egat_llp_on_log_list,
    ihi_engine_llp_time_cycle_record, elal_internal_parts_list,
    iai_dual_rating_engine_llp, kalstar_engine_llp_status,
    kalstar_aviation_llp_status, thai_landing_gear_llp_status,
    b777_gear_llp_availability, part_m_engine_disk_sheet,
    revima_landing_gear_als_status, powerplant_maintenance_center_llp_status,
    lan_engine_control_fleet_llp, engine_items_control_llp_status,
]

_BY_NAME = {v.NAME: v for v in VARIANTS}

SIGNATURES = [
    "LIFE LIMITED PART LIST",
    "Lowest LLP",
    "Component Equipment List Report",
    "ENGINE LLPs STATUS REPORT",
    "Engine Life Limited Parts Status",
    "LIFE LIMITED PARTS SUMMARY",
    "CFM56-7B LIFE LIMITED PARTS",
    "LIFE LIMITS PARTS STATUS LIST",       # erj190_landing_gear_llp.py
    "LANDING GEAR STATUS",                 # messier_dowty_landing_gear_llp.py
    "Assemblies >> Gear LLPs",             # gear_llp_status_list.py
    "Life Limited Part Status",            # emes_airframe_llp_status.py
    "Serialized Unit List - Hard Limits",  # serialized_unit_hard_limits.py
    "LDG LLP COMPLIANCE STATUS",           # swiss_a340_ldg_llp.py
    "LANDING GEAR LIFE LIMIT PARTS REPORT",# landing_gear_llp_report.py
    "LLP Status Report",                   # aircraft_llp_status_report.py
    "When Airframe CSN:",                  # sas_drawing_item_llp.py
    "06331890969",                         # cai_first_landing_gear_llp.py -- the producer's
                                            # VAT number; not every real file also happens to
                                            # contain the pre-existing "LIFE LIMITED PARTS
                                            # SUMMARY" phrase, so this is needed for the rest
                                            # to be reachable at all
    "LOWER LIMITER",                       # kalstar_aviation_llp_status.py
    "LANDING GEAR LIFE LIMITED PARTS STATUS",  # thai_landing_gear_llp_status.py
    "MAINTENANCEPLANNING AND CONTROL",     # b737_gear_llp_inventory.py
    "Available hours/cycles for Component life limited parts",  # b777_gear_llp_availability.py
    "LIFE LIMITED PARTS FOR A",            # pro_rata_engine_llp.py -- IAI CFM56-5B "LIFE
                                            # LIMITED PARTS FOR A <engine model> ENGINE" title;
                                            # the variant's own SIGNATURES ("TSLSV"/"CSLSV")
                                            # already matched once inside LLP, but the sheet-type
                                            # gate itself had no phrase for this document family
                                            # at all, so it never got that far
    "ALS Part 1",                          # revima_landing_gear_als_status.py -- checked for
                                            # collisions against every SIGNATURES list in
                                            # sheet_types/{occm,ht,llp}.py and every existing
                                            # variant file; no collision found.
    "IHI Corporation",                     # ihi_engine_llp_time_cycle_record.py
    "LIST OF INTERNAL PARTS",              # elal_internal_parts_list.py
    "Life Limited Parts for:",             # iai_dual_rating_engine_llp.py -- the colon after
                                            # "for" distinguishes it from this list's own earlier
                                            # "LIFE LIMITED PARTS FOR A" entry (pro_rata_engine_llp.py)
    "POWERPLANT MAINTENANCE CENTER",       # powerplant_maintenance_center_llp_status.py -- checked
                                            # for collisions against every SIGNATURES list in this
                                            # file and every {occm,ht,llp}_variants/*.py file; none
                                            # found. ("P.CSN", the variant's other signature, is
                                            # equally collision-free but a facility-block heading is
                                            # the more legible anchor for this top-level list.)
    "ENGINE CONTROL FLEET ENGINES",        # lan_engine_control_fleet_llp.py -- checked for
                                            # collisions against every SIGNATURES list in
                                            # sheet_types/{occm,ht,llp}.py and every existing
                                            # variant file; no collision found.
    "ITEMS CONTROL FOR",                   # engine_items_control_llp_status.py -- checked for
                                            # collisions against every SIGNATURES list in
                                            # sheet_types/{occm,ht,llp}.py and every existing
                                            # variant file; no collision found. Deliberately
                                            # trimmed to drop "ENGINE" from the end of the
                                            # phrase -- the sample file's own text layer
                                            # corrupts that word to "EN8INE", so the full
                                            # "ITEMS CONTROL FOR ENGINE" phrase would not match.
    # mm510_llp.py deliberately has NO entry here: the same "MM_510" header
    # is emitted verbatim by the same MIS tool for both HT-relevant and
    # LLP-relevant queries (confirmed: no discriminating phrase exists in
    # the header either way -- which bucket a file belongs in depends on
    # what report was run, not its content). Adding "MM_510" or "HARD
    # TIME/LLP COMPONENTS" here would risk silently stealing genuinely-HT
    # files from ht_variants/mm510.py, since LLP is checked before HT in
    # router.py's DETECTION_ORDER. mm510_llp.py is registered below for
    # internal variant dispatch only -- it's unreachable via top-level
    # routing today. See docs/TODO.md for the real fix this needs
    # (content-based, not header-phrase-based, disambiguation).
]


def _read_head_text(pdf_path: str, n_pages: int = 3) -> str:
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
        # No usable text layer -- likely a scanned PDF. Ask any OCR-capable
        # variants to confirm their own template via a cheap header OCR pass
        # rather than guessing; each must self-check, there's no blind
        # default here (unlike occm.py's Aeroflot fallback, which defaults
        # ANY blank-text PDF to one specific variant -- exactly the mislabel
        # that sent a real LLP document through as "OCCM . Aeroflot").
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


def normalize_and_validate(records: list[dict], variant_name: str = "Vietnam Airlines") -> list[dict]:
    v = _BY_NAME.get(variant_name, vietnam_airlines)
    return [clean_record(dict(r), v.RULES) for r in records]


# Expose CANONICAL_COLUMNS for legacy callers (single-variant convenience).
CANONICAL_COLUMNS = vietnam_airlines.CANONICAL_COLUMNS
