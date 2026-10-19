"""VIM Component Fitted List — headerless tabular OCCM with 7 columns.

Born-digital PDF with a scanned cover page (page 0) and pure data rows
starting from page 1. No title, header text, or column labels appear in
the extractable text layer — the only content is data rows in a fixed
7-column grid.

Column structure (from pdfplumber table extraction)::

    ATA  PART_NUMBER  SERIAL_NUMBER  DESCRIPTION  POSITION  DATE  REMARKS

Dates use mixed formats (``dd-Mon-yy`` and ``dd.mm.yyyy``). REMARKS
carries OCCM status codes specific to maintenance check intervals
(e.g. ``A4 CHECK``, ``OUT OF PHASE``, ``< 3 YEARS``, ``D.O.M``).

Detection uses a ``data_detect`` heuristic rather than SIGNATURES
because the file has no header text at all.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "VIM Component Fitted List"
SIGNATURES: list[str] = []

CANONICAL_COLUMNS = [
    "ATA",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
    "POSITION",
    "INSTALL_DATE",
    "REMARKS",
]

RULES = merged_rules({
    "INSTALL_DATE": {"allow_empty": True},
    "POSITION": {"allow_empty": True, "uppercase": True},
    "REMARKS": {"allow_empty": True},
})

_ATA_RE = re.compile(r"^\d{2}$")
_HEADER_WORDS = frozenset([
    "OCCM", "STATUS", "COMPONENTS", "LIST", "REPORT", "INVENTORY",
    "AIRCRAFT", "REGISTRATION", "CONDITION", "MONITORING",
])


def data_detect(head: str) -> bool:
    """Detect this format by its headerless data-only pattern."""
    lines = [ln.strip() for ln in head.splitlines() if ln.strip()]
    if len(lines) < 10:
        return False
    data_count = 0
    for line in lines[:20]:
        parts = line.split()
        if len(parts) >= 5 and _ATA_RE.match(parts[0]):
            data_count += 1
        elif any(w in _HEADER_WORDS for w in line.upper().split()):
            return False
    return data_count >= 10


def _clean_cell(val: str | None) -> str:
    if val is None:
        return ""
    return val.strip()


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages):
            tables = page.find_tables()
            if not tables:
                continue
            for row in tables[0].extract():
                if not row or len(row) < 7:
                    continue
                ata = _clean_cell(row[0])
                if not _ATA_RE.match(ata):
                    continue
                records.append({
                    "ATA": ata,
                    "PART_NUMBER": _clean_cell(row[1]),
                    "SERIAL_NUMBER": _clean_cell(row[2]),
                    "DESCRIPTION": _clean_cell(row[3]),
                    "POSITION": _clean_cell(row[4]),
                    "INSTALL_DATE": _clean_cell(row[5]),
                    "REMARKS": _clean_cell(row[6]),
                    "_page": page_num + 1,
                })
    return records
