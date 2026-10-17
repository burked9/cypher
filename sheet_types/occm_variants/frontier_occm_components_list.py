"""OCCM Components List variant — tabular 12-column layout with snake_case
column headers and DD/MM/YYYY dates.

Format: 12 columns per row (pdfplumber table extraction).
    ATA  pn  sn  Description  installed_position  installed_date
    actual_hours  actual_cycles  installed_hour  installed_minute
    ac_hours  ac_cycles

The header block (aircraft info + column headers) repeats on every page.
ATA is a 2-digit chapter code; some rows (structural parts) have it empty,
so ATA is forward-filled from the most recent non-empty value.

Strategy: pdfplumber's ``extract_tables()`` returns clean 12-column rows
on every page. Data rows are identified by having a non-empty part number
(column index 1) and a date in column index 5.
"""
from __future__ import annotations

import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "OCCM Components List"
SIGNATURES = [
    "installed_position installed_date actual_hours actual_cycles",
]

CANONICAL_COLUMNS = [
    "ATA",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
    "INSTALLED_POSITION",
    "INSTALLED_DATE",
    "ACTUAL_HOURS",
    "ACTUAL_CYCLES",
    "INSTALLED_HOUR",
    "INSTALLED_MINUTE",
    "AC_HOURS",
    "AC_CYCLES",
]

_NUM_RULE = {"pattern": r"^\d+(?:\.\d+)?$"}
_INT_RULE = {"pattern": r"^\d+$"}

_OVERRIDES = {
    "ATA": {"allow_empty": True},
    "INSTALLED_POSITION": {"allow_empty": True},
    "INSTALLED_DATE": {"pattern": r"^\d{2}/\d{2}/\d{4}$"},
    "ACTUAL_HOURS": _NUM_RULE,
    "ACTUAL_CYCLES": _INT_RULE,
    "INSTALLED_HOUR": _INT_RULE,
    "INSTALLED_MINUTE": _INT_RULE,
    "AC_HOURS": _INT_RULE,
    "AC_CYCLES": _INT_RULE,
}
RULES = merged_rules(_OVERRIDES)

_DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")

# Column header row text used to skip repeated headers on each page
_HEADER_ROW = ["ATA", "pn", "sn", "Description", "installed_position",
               "installed_date", "actual_hours", "actual_cycles",
               "installed_hour", "installed_minute", "ac_hours", "ac_cycles"]


def _is_header_row(row: list[str | None]) -> bool:
    """Return True if the row is the column-header row repeated on each page."""
    if not row or len(row) < 12:
        return False
    return (row[0] or "").strip().upper() == "ATA" and (row[1] or "").strip().lower() == "pn"


def _is_data_row(row: list[str | None]) -> bool:
    """Return True if the row looks like a real data row."""
    if not row or len(row) < 12:
        return False
    pn = (row[1] or "").strip()
    date = (row[5] or "").strip()
    if not pn or not date:
        return False
    return bool(_DATE_RE.match(date))


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    current_ata = ""

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            tables = page.extract_tables()
            if not tables:
                continue
            for table in tables:
                for row in table:
                    if _is_header_row(row) or not _is_data_row(row):
                        continue

                    cells = [(c or "").strip() for c in row[:12]]
                    ata = cells[0]
                    if ata:
                        current_ata = ata

                    rec = {
                        "ATA": current_ata,
                        "PART_NUMBER": cells[1],
                        "SERIAL_NUMBER": cells[2],
                        "DESCRIPTION": cells[3],
                        "INSTALLED_POSITION": cells[4],
                        "INSTALLED_DATE": cells[5],
                        "ACTUAL_HOURS": cells[6],
                        "ACTUAL_CYCLES": cells[7],
                        "INSTALLED_HOUR": cells[8],
                        "INSTALLED_MINUTE": cells[9],
                        "AC_HOURS": cells[10],
                        "AC_CYCLES": cells[11],
                        "_page": page_num,
                    }
                    records.append(rec)

    return records
