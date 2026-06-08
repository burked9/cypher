"""HT (Hard Time) sheet-type router.

Mirrors `sheet_types/occm.py`. Detects which HT variant a PDF is and
dispatches to the variant's `extract()`.
"""
from __future__ import annotations
import pdfplumber

from sheet_types.ht_variants import (
    vietnam_airlines, amos, mm510, tap, iberia, oases_lifed_components,
    stars_trax, aircraft_rotables_ht,
)
from shared.cleanup import clean_record

# Order matters: more-specific signatures must precede generic ones.
# Variants with distinctive headers sit before the AMOS catch-all.
VARIANTS = [vietnam_airlines, mm510, tap, iberia,
            oases_lifed_components, stars_trax, aircraft_rotables_ht, amos]
_BY_NAME = {v.NAME: v for v in VARIANTS}

# Sheet-type level signatures (used by the top-level router)
SIGNATURES = [
    "PLAN OF AIRCRAFT COMPONENT REPLACEMENT",
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
