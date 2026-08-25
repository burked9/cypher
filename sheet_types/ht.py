"""HT (Hard Time) sheet-type router.

Mirrors `sheet_types/occm.py`. Detects which HT variant a PDF is and
dispatches to the variant's `extract()`.
"""
from __future__ import annotations
import pdfplumber

from sheet_types.ht_variants import (
    vietnam_airlines, amos, mm510, tap, iberia, oases_lifed_components,
    stars_trax, aircraft_rotables_ht,
    georgian_airways_ht_components_status, mpd_hard_time_list, htll_status,
    hard_time_component_status_mpd_task,
    aercap_hard_time_component_status, aercap_oxygen_generator_status,
    emes_hard_time_component_status,
    xiamen_time_controlled_components, aircraft_rotables_ht_scanned,
)
from shared.cleanup import clean_record

# Order matters: more-specific signatures must precede generic ones.
# Variants with distinctive headers sit before the AMOS catch-all.
VARIANTS = [vietnam_airlines, mm510, tap, iberia,
            oases_lifed_components, stars_trax, aircraft_rotables_ht, amos,
            georgian_airways_ht_components_status, mpd_hard_time_list, htll_status,
            hard_time_component_status_mpd_task,
            aercap_hard_time_component_status, aercap_oxygen_generator_status,
            emes_hard_time_component_status,
            xiamen_time_controlled_components, aircraft_rotables_ht_scanned]
_BY_NAME = {v.NAME: v for v in VARIANTS}

# Sheet-type level signatures (used by the top-level router)
SIGNATURES = [
    "PLAN OF AIRCRAFT COMPONENT REPLACEMENT",
    "HARD TIME COMPONENTS STATUS FOR A/C-REGISTRATION",  # georgian_airways_ht_components_status.py
    "HARD TIME LIST AS AT",                              # mpd_hard_time_list.py
    "HT-LL STATUS",                                      # htll_status.py
    "HT&LLP STATUS",                                     # htll_status.py, other sub-format
    "MPD TASK NO",                                       # hard_time_component_status_mpd_task.py
    "COMP.TIMELINE",                                     # aercap_hard_time_component_status.py
    "OXYGEN GENERATOR STATUS",                           # aercap_oxygen_generator_status.py
    # NOT "FROM E.MES" -- that phrase is also emes_airframe_llp_status.py's
    # (LLP) own signature, the same cross-sheet-type MIS-vendor-boilerplate
    # pattern as MM_510/STARS Trax elsewhere in this file. This phrase is
    # unique to the HT-side format instead.
    "T/C # TASK HT",                                     # emes_hard_time_component_status.py
    "Time-controlled Components",                        # xiamen_time_controlled_components.py
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


def detect_variant(pdf_path: str) -> str:
    head = _read_head_text(pdf_path).upper()
    for v in VARIANTS:
        for sig in v.SIGNATURES:
            if sig.upper() in head:
                return v.NAME
    if len(head.strip()) < 50:
        # No usable text layer -- likely a scanned PDF. Ask any OCR-capable
        # variant to confirm its own template via a cheap header OCR pass
        # rather than guessing (mirrors occm.py/llp.py). Without this block,
        # router.py's own OCR-fallback loop can still correctly resolve
        # sheet_type="HT" for a blank-text file (it checks every sheet
        # type's variants directly), but then this function -- called next,
        # to pick the specific variant -- would return "Unknown" regardless,
        # since it only checked plain-text SIGNATURES above.
        for v in VARIANTS:
            ocr_check = getattr(v, "ocr_detect", None)
            if ocr_check and ocr_check(pdf_path):
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


def normalize_and_validate(records: list[dict], variant_name: str = "Vietnam Airlines") -> list[dict]:
    v = _BY_NAME.get(variant_name, vietnam_airlines)
    return [clean_record(dict(r), v.RULES) for r in records]
