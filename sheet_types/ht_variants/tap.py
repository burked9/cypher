"""TAP Portugal HT — same single-line `DDMmmYYYY` layout as the TAP OCCM.

TAP emits OCCM and HT reports from the same internal system with the same
header structure (`Serial Numbers Attached to Aircraft <REG>  PROG. MAN: TAP`)
and the same per-row column layout. We reuse `tap_compact_occm.extract`
verbatim and only register the variant under a distinct HT name so the
routing and downstream `sheet_type` tagging are right.
"""
from __future__ import annotations

from sheet_types.occm_variants import tap_compact_occm as _tap_occm

NAME = "TAP HT (compact)"
SIGNATURES = [
    "PROG. MAN: TAP",
    "FLIGHT TIME:",
]
CANONICAL_COLUMNS = _tap_occm.CANONICAL_COLUMNS
RULES = _tap_occm.RULES


def extract(pdf_path: str):
    return _tap_occm.extract(pdf_path)
