"""Iberia bilingual ES/EN HT report.

Same `LISTADO DE EQUIPOS INSTALADOS` template as the Iberia OCCM, just
flagged as a Hard-Time component list rather than installed-components.
The page-1 column layout is identical, so we reuse the OCCM parser.

Detected by the explicit Spanish-side header tokens
(`Fecha de listado` / `Horas de vuelo`).
"""
from __future__ import annotations

from sheet_types.occm_variants import iberia_listado as _iberia_occm

NAME = "Iberia Listado HT"
SIGNATURES = [
    "Fecha de listado",
    "Horas de vuelo",
]
CANONICAL_COLUMNS = _iberia_occm.CANONICAL_COLUMNS
RULES = _iberia_occm.RULES


def extract(pdf_path: str):
    return _iberia_occm.extract(pdf_path)
