"""OC/CM Inventory List (Brazilian format) -- born-digital, clean table layer.

Header block (repeats verbatim on every page)::

    ACFT REG: <reg>
    MSN: <msn>
    TSN: <tsn>
    CSN: <csn>
    DATE: <dd>/<mon>/<yy>
    OC/CM INVENTORY LIST
    ITEM  PART NUMBER  SERIAL NUMBER  DESCRIPTION  TYPE

Five data columns per row: ITEM, PART_NUMBER, SERIAL_NUMBER, DESCRIPTION,
TYPE (O/C or C/M or similar). The ITEM column is a sequential row number
and is not emitted as a record field. DESCRIPTION may be truncated in
the PDF when the original text was too long for the cell width.

pdfplumber's extract_table() returns all five columns cleanly on every
page of both known source files (confirmed directly). Empty trailing rows
sometimes appear on the last page and are filtered out.
"""
from __future__ import annotations

import re

import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "OC/CM Inventory List (BR)"
SIGNATURES = [
    "OC/CM INVENTORY LIST",
]

CANONICAL_COLUMNS = [
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
    "TYPE",
    # Header metadata -- parsed once per page, stamped onto every row.
    "AIRCRAFT_REG",
    "MSN",
    "TSN",
    "CSN",
    "DATE",
]

_OVERRIDES = {
    "DESCRIPTION": {"uppercase": True, "allow_empty": True},
    "TYPE": {
        "pattern": r"^[A-Z0-9/ ]{2,10}$",
        "uppercase": True,
        "allow_empty": True,
    },
    "AIRCRAFT_REG": {
        "pattern": r"^[A-Z0-9\-]{2,10}$",
        "uppercase": True,
        "allow_empty": True,
    },
    "MSN": {"pattern": r"^\d{1,6}$", "allow_empty": True},
    "TSN": {"allow_empty": True},
    "CSN": {"pattern": r"^\d+$", "allow_empty": True},
    "DATE": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_HEADER_RE = re.compile(
    r"ACFT\s+REG:\s*(?P<reg>\S+).*?"
    r"MSN:\s*(?P<msn>\d+).*?"
    r"TSN:\s*(?P<tsn>\S+).*?"
    r"CSN:\s*(?P<csn>\S+).*?"
    r"DATE:\s*(?P<date>\S+)",
    re.DOTALL,
)


def _parse_header(text: str) -> dict:
    """Extract aircraft metadata from the per-page header block."""
    meta: dict = {}
    m = _HEADER_RE.search(text)
    if m:
        meta["AIRCRAFT_REG"] = m.group("reg")
        meta["MSN"] = m.group("msn")
        meta["TSN"] = m.group("tsn")
        meta["CSN"] = m.group("csn")
        meta["DATE"] = m.group("date")
    return meta


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    header_meta: dict = {
        "AIRCRAFT_REG": "", "MSN": "", "TSN": "", "CSN": "", "DATE": "",
    }

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            page_meta = _parse_header(text)
            for k, v in page_meta.items():
                if v:
                    header_meta[k] = v

            table = page.extract_table()
            if not table:
                continue

            for row in table:
                # Skip header row and empty trailing rows.
                if not row or not row[0] or row[0] == "ITEM":
                    continue
                # Expect 5 cells: ITEM, PART_NUMBER, SERIAL_NUMBER,
                # DESCRIPTION, TYPE.
                if len(row) < 5:
                    continue

                item, pn, sn, desc, typ = (
                    (row[i] or "").strip() for i in range(5)
                )

                # A valid data row needs at least a part number or serial.
                if not pn and not sn:
                    continue

                rec = {
                    "PART_NUMBER": pn,
                    "SERIAL_NUMBER": sn,
                    "DESCRIPTION": desc,
                    "TYPE": typ,
                    "_page": page_num,
                }
                rec.update(header_meta)
                records.append(rec)

    return records
