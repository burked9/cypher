"""AMOS Aircraft Equipment List Report — HT-side variant.

Reuses the existing AMOS OCCM parser verbatim. The "HT" version of the AMOS
Aircraft Equipment List Report differs from the OCCM version only in which
ATA chapters are included and in the presence of per-row HT continuation
lines (REQUIREMENT / TASKCARD / INTERVAL / DUE AT / TSR / EXPECTED TO GO).

For sextant — which needs the *position fingerprint* of HT components per
airframe family — those continuation lines aren't required. The main row's
ATA + POS + PART_NUMBER + SERIAL_NUMBER + INST_DATE + TSN/CSN is identical
to the OCCM layout, and the existing parser already extracts it cleanly.

48 files in the HT corpus matched on the page-1 signature
`Aircraft Equipment List Report`. Smoke-tested on four representative
files: 23 / 323 / 141 / 445 rows extracted respectively, no parse changes
required.
"""
from __future__ import annotations

from sheet_types.occm_variants import amos as _amos_occm

NAME = "AMOS HT (Aircraft Equipment List Report)"
SIGNATURES = [
    # The AMOS HT report header is identical to the OCCM one — the file
    # ends up in the HT folder rather than the OCCM folder because the
    # operator generated it from the HT-task subset of their AMOS data.
    "Aircraft Equipment List Report",
    # Hyphenated variant of the same report, used by Alitalia / I-BI**,
    # 4X-EAR (EL AL), VT-JGA (JetGo) and others. Identical row layout but
    # the title carries hyphens and the column header row is sometimes
    # printed in a doubled-character font (AATTAA DDeessccrriippttiioonn …).
    "Aircraft-Equipment-List",
    # Some operators (EI-FFM Stobart Air, FFM HT List) strip the AMOS
    # branding from the header but emit the exact same column layout.
    # The column header line itself is the cleanest signature.
    "PART NO. SERIAL NO. DESCRIPTION POS.",
]

CANONICAL_COLUMNS = _amos_occm.CANONICAL_COLUMNS
RULES = _amos_occm.RULES


def extract(pdf_path: str):
    return _amos_occm.extract(pdf_path)
