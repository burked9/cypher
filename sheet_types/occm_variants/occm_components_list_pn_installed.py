"""OCCM Components List (Part Number INSTALLED) -- born-digital variant with
a minimal header block and a clean pdfplumber-extractable table grid.

Two confirmed sub-formats share the same parsing logic:

Sub-format A -- 5-column grid, no date column::

    <title line>
    <reg>, MSN-<msn>
    ATA  Part Number INSTALLED  Serial/Lot Number INSTALLED  POSN/ MPD ZONE  DESCRIPTION

Sub-format B -- 6-column grid, with INST DATE::

    <title line>
    <reg>, MSN-<msn>
    ATA  Part Number  Serial/Lot Number  Part Description  POSN  INST DATE

Both sub-formats share:
  - A two-line header block (title + registration/MSN line) repeated on
    every page.
  - A single pdfplumber-extractable table per page whose first row is the
    column-header line (or the title line in sub-format B, with the column
    header on row index 2).
  - ATA as a bare two-digit chapter (sometimes empty -- forward-filled by
    the shared cleanup pipeline).
  - Leading apostrophe/punctuation artifacts on PART_NUMBER values (same
    rendering glitch as installed_parts_list.py).
  - Multi-line DESCRIPTION cells (pdfplumber joins them with ``\\n``).

Detection uses two SIGNATURES entries that together cover both sub-formats
without colliding with any other variant (checked directly -- see the
ordering comment in occm.py's VARIANTS list).
"""
from __future__ import annotations

import re

import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "OCCM Components List (PN Installed)"

SIGNATURES = [
    "Part Number INSTALLED",
    "AIRCRAFT EQUIPMENT LIST- OCCM",
]

CANONICAL_COLUMNS = [
    "ATA",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "POSITION",
    "DESCRIPTION",
    "INSTALL_DATE",
    # Header metadata -- parsed once, stamped onto every row.
    "MSN",
    "AIRCRAFT_REG",
]

_OVERRIDES = {
    "POSITION": {"pattern": r"^.+$", "allow_empty": True},
    "INSTALL_DATE": {"pattern": r"^\d{2}-[A-Za-z]{3}-\d{2}$", "allow_empty": True},
    "MSN": {"pattern": r"^\d{3,6}$", "allow_empty": True},
    "AIRCRAFT_REG": {"pattern": r"^[A-Z0-9\-]{3,10}$", "allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Leading punctuation artifact -- strip from PN/SN (same rendering glitch as
# installed_parts_list.py).
_LEADING_ARTIFACT_RE = re.compile(r"^[^A-Za-z0-9]+")

# Header line: "<reg>, MSN-<msn>" -- extract registration and MSN.
_HEADER_RE = re.compile(r"^([A-Z0-9\-]+),\s*MSN[- ](\d+)")


def _strip_artifact(s: str) -> str:
    """Strip leading non-alphanumeric rendering artifacts."""
    if not s:
        return s
    return _LEADING_ARTIFACT_RE.sub("", s)


def _clean_cell(val: str | None) -> str:
    """Normalise a table cell: collapse internal newlines, strip whitespace."""
    if val is None:
        return ""
    return " ".join(val.split())


def _parse_header_line(text: str) -> dict:
    """Extract registration and MSN from the title block."""
    meta: dict = {"MSN": "", "AIRCRAFT_REG": ""}
    for line in text.splitlines():
        m = _HEADER_RE.match(line.strip())
        if m:
            meta["AIRCRAFT_REG"] = m.group(1)
            meta["MSN"] = m.group(2)
            break
    return meta


def _detect_layout(header_row: list[str]) -> str | None:
    """Determine which sub-format this table is, based on the column header
    row text. Returns 'A' (5-col, no date), 'B' (6-col, with date), or
    None if unrecognised."""
    joined = " ".join(_clean_cell(c) for c in header_row).upper()
    if "PART NUMBER INSTALLED" in joined:
        return "A"
    if "PART DESCRIPTION" in joined and "INST DATE" in joined:
        return "B"
    return None


def _parse_row_a(row: list[str]) -> dict | None:
    """Parse a 5-column (sub-format A) table row."""
    if len(row) != 5:
        return None
    ata, pn, sn, posn, desc = [_clean_cell(c) for c in row]
    # Skip header rows and empty rows
    if not pn or pn.upper().startswith("PART NUMBER"):
        return None
    return {
        "ATA": ata,
        "PART_NUMBER": _strip_artifact(pn),
        "SERIAL_NUMBER": _strip_artifact(sn),
        "POSITION": posn,
        "DESCRIPTION": desc,
        "INSTALL_DATE": "",
    }


def _parse_row_b(row: list[str]) -> dict | None:
    """Parse a 6-column (sub-format B) table row."""
    if len(row) != 6:
        return None
    ata, pn, sn, desc, posn, inst_date = [_clean_cell(c) for c in row]
    # Skip header/title rows
    if not pn or pn.upper().startswith("PART NUMBER"):
        return None
    if "EQUIPMENT LIST" in pn.upper() or "MSN" in pn.upper():
        return None
    return {
        "ATA": ata,
        "PART_NUMBER": _strip_artifact(pn),
        "SERIAL_NUMBER": _strip_artifact(sn),
        "POSITION": posn,
        "DESCRIPTION": desc,
        "INSTALL_DATE": inst_date,
    }


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    header_meta: dict = {"MSN": "", "AIRCRAFT_REG": ""}
    header_locked = False
    layout: str | None = None

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            # Parse header metadata from the first page that yields it.
            if not header_locked:
                text = page.extract_text() or ""
                page_meta = _parse_header_line(text)
                if page_meta["MSN"] and page_meta["AIRCRAFT_REG"]:
                    header_meta = page_meta
                    header_locked = True

            tables = page.extract_tables()
            if not tables:
                continue

            table = tables[0]
            if not table:
                continue

            # Detect layout from the first page's header row.
            if layout is None:
                for row in table:
                    detected = _detect_layout(row)
                    if detected:
                        layout = detected
                        break
                if layout is None:
                    continue

            parse_fn = _parse_row_a if layout == "A" else _parse_row_b

            for row in table:
                rec = parse_fn(row)
                if rec is None:
                    continue
                rec.update(header_meta)
                rec["_page"] = page_num
                records.append(rec)

    return records
