"""Top-level sheet-type dispatcher.

Cypher handles three document classes today:
    OCCM — On Condition / Condition Monitored (component status lists)
    HT   — Hard Time (planned replacement schedules)
    LLP  — Life Limited Parts (engine LLP lists)

Each class has its own router under `sheet_types/<class>.py` and one or more
variants under `sheet_types/<class>_variants/`. This top-level dispatcher
detects the class first, then delegates to the class-specific router which
detects the variant.

Detection priority: HT and LLP signatures are checked before OCCM, because
the OCCM signature list is broader and could otherwise match HT/LLP files
that happen to contain words like "AIRCRAFT REGISTRATION:".
"""
from __future__ import annotations
import pdfplumber

from sheet_types import occm, ht, llp
from shared.cleanup import clean_record


SHEET_TYPES = {
    "OCCM": occm,
    "HT":   ht,
    "LLP":  llp,
}
# Detection order matters — most specific first.
DETECTION_ORDER = ["LLP", "HT", "OCCM"]


def _read_head_text(pdf_path: str, n_pages: int = 3) -> str:
    parts = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for p in pdf.pages[:n_pages]:
                parts.append(p.extract_text() or "")
    except Exception:
        pass
    return "\n".join(parts)


def detect_sheet_type(pdf_path: str) -> str:
    """Return 'OCCM' / 'HT' / 'LLP' / 'Unknown' based on first-pages text."""
    head = _read_head_text(pdf_path).upper()
    if not head.strip():
        # No text layer at all — only the Aeroflot OCCM variant fits this today.
        return "OCCM"
    for st in DETECTION_ORDER:
        mod = SHEET_TYPES[st]
        for sig in mod.SIGNATURES:
            if sig.upper() in head:
                return st
    return "Unknown"


def extract(pdf_path: str) -> dict:
    """Detect sheet type + variant, run the right parser, return validated rows.

    Return shape:
        {
          "ok": True/False,
          "sheet_type": "OCCM" | "HT" | "LLP" | "Unknown",
          "variant":    "<variant name>",
          "columns":    [...],
          "records":    [{...}, ...],   # cleaned + validated
        }
    """
    sheet_type = detect_sheet_type(pdf_path)
    if sheet_type == "Unknown":
        return {"ok": False, "sheet_type": "Unknown", "variant": "Unknown",
                "columns": [], "records": [],
                "error": "Sheet type not recognized — extend signatures in sheet_types/"}

    mod = SHEET_TYPES[sheet_type]
    variant = mod.detect_variant(pdf_path)
    raw = mod.extract(pdf_path, variant_name=variant)
    cleaned = mod.normalize_and_validate(raw["records"], variant_name=variant)
    return {
        "ok": True,
        "sheet_type": sheet_type,
        "variant": raw["variant"],
        "columns": raw["columns"],
        "records": cleaned,
    }
