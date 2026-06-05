"""LLP (Life Limited Parts) sheet-type router. Mirrors HT/OCCM routers."""
from __future__ import annotations
import pdfplumber

from sheet_types.llp_variants import (
    vietnam_airlines, amos, lan_engine_llp, pro_rata_engine_llp,
    cfm_overhaul_llp, cfm56_7b_llp,
)
from shared.cleanup import clean_record

VARIANTS = [
    vietnam_airlines, amos, lan_engine_llp, pro_rata_engine_llp,
    cfm_overhaul_llp, cfm56_7b_llp,
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


# Expose CANONICAL_COLUMNS for legacy callers (single-variant convenience).
CANONICAL_COLUMNS = vietnam_airlines.CANONICAL_COLUMNS
