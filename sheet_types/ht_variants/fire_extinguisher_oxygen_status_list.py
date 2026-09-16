""""Fire Extinguisher Status List" / "OXYGEN STATUS LIST" -- born-digital,
full text layer, two sibling report templates sharing one parser (confirmed
directly against the real sample file: page 1 is titled "Fire Extinguisher
Status List" and pages 2+ are titled "OXYGEN STATUS LIST"; both share the
same top-of-page header shape -- `<aircraft MSN> <title>` then
`As of Date: <dd-Mon-yy>` -- and pdfplumber's `extract_tables()` returns
one clean ruled/aligned table per page for both, so one shared row-walking
parser handles both instead of two near-duplicate modules).

Fire Extinguisher page layout: a single table with two stacked sub-sections,
each starting with its own one-cell section-header row (no other cell
populated on that row) followed by its own two/three/four-cell column
header row (always starting with the literal cell "Position")::

    Portable Fire Extinguishers
    Position | P/N | S/N
    <data rows...>
    Lavatory Fire Extinguishers
    Position | P/N | S/N | Last Weight Done Date
    <data rows...>

Oxygen page layout: a single 5-column table, one column header row per page
(always starting with the literal cell "Description")::

    Description | ZONE | Position | P/N | S/N
    <data rows...>

The Oxygen table groups several positions under one task description +
zone; the source table only populates the Description/ZONE cells on the
first physical row of each group and leaves them blank (`None`) on every
following row of that same group -- confirmed directly in the sample file,
e.g. seven "REMOVE OXYGEN CYLINDER FOR HYDROSTATIC TEST" positions share
one Description cell and one ZONE cell, populated once. This parser
forward-fills both from the most recent non-blank cell within the table,
which is the source table's own grouping convention, not a guess.

Row grain: one row per tracked component/position (fire extinguisher unit
or oxygen equipment item). Columns, unified across both report templates::

    REPORT_SECTION | ZONE | POSITION | PART_NUMBER | SERIAL_NUMBER |
    LAST_WEIGHT_DATE

REPORT_SECTION carries the Fire Extinguisher table's own sub-section header
text ("Portable Fire Extinguishers" / "Lavatory Fire Extinguishers") on
fire-extinguisher rows, or the Oxygen table's own task Description text on
oxygen rows -- never force-split into a separate task/system taxonomy, since
the two templates don't share one. ZONE is only ever populated on Oxygen
rows (the Fire Extinguisher template has no ZONE column at all). Only the
"Lavatory Fire Extinguishers" section rows populate LAST_WEIGHT_DATE.

Section-header-row detection (a row whose first cell is populated and every
other cell is blank) is only attempted while still positioned inside a
Fire-Extinguisher-style table (i.e. before any "Description"-style column
header has been seen on the page) -- this keeps a hypothetical fully-blank
Oxygen data row (POSITION/PART_NUMBER/SERIAL_NUMBER all empty, which would
also satisfy "only the first cell populated" if ZONE happened to repeat)
from ever being misread as a new section instead of just being dropped as a
non-data row by the normal empty-row check.

Header metadata (aircraft MSN, "As of Date") is parsed once per page from
that page's own title/date line and stamped on every row extracted from
that page.

Each page ends with a "Prepared by: <name>" footer line -- confirmed
directly in the sample file, this is a real person's name and is never
captured into any field: the parser only reads cells inside the ruled
table extracted by `extract_tables()`, and this footer line sits outside
that table's own bounding box on every page, so it's structurally excluded
rather than filtered after the fact.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.ht_variants._base import merged_rules
from shared.cleanup import normalize_dashes

NAME = "Fire Extinguisher / Oxygen Status List"
SIGNATURES = [
    # Checked against every SIGNATURES list in occm.py/ht.py/llp.py and
    # every occm_variants/ht_variants/llp_variants module's own SIGNATURES
    # list (plus a plain grep for "OXYGEN" and "STATUS LIST" across all of
    # them); no collision found. Neither phrase is a substring of, nor
    # contains as a substring, any other variant's own signature phrase --
    # in particular distinct from aercap_oxygen_generator_status.py's own
    # "OXYGEN GENERATOR STATUS" (different word order/content, no "LIST").
    "Fire Extinguisher Status List",
    "OXYGEN STATUS LIST",
]

CANONICAL_COLUMNS = [
    "REPORT_SECTION",
    "ZONE",
    "POSITION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "LAST_WEIGHT_DATE",
    # Header metadata -- same on every row of a given page.
    "AC_MSN",
    "REPORT_DATE",
]

_DATE_RE = r"^\d{4}\.\d{1,2}\.\d{1,2}$"
_AS_OF_DATE_RE = r"^\d{1,2}-[A-Za-z]{3}-\d{2,4}$"

_OVERRIDES = {
    "REPORT_SECTION":    {"allow_empty": True},
    # ZONE only exists as a concept on the Oxygen report template -- the
    # Fire Extinguisher template has no zone column at all, so every
    # Fire Extinguisher row is genuinely, structurally zone-less rather
    # than missing data (confirmed directly: neither Fire Extinguisher
    # sub-table has a ZONE/Zone header cell anywhere in the sample file).
    "ZONE":              {"allow_empty": True},
    "LAST_WEIGHT_DATE":  {"pattern": _DATE_RE, "allow_empty": True},
    "AC_MSN":            {"pattern": r"^\d+$", "allow_empty": True},
    "REPORT_DATE":       {"pattern": _AS_OF_DATE_RE, "allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_MSN_RE = re.compile(r"MSN\s*(\d+)", re.IGNORECASE)
_AS_OF_RE = re.compile(r"As of Date:\s*(\S+)", re.IGNORECASE)

_FIREX_HEADER_FIRST_CELL = "Position"
_OXYGEN_HEADER_FIRST_CELL = "Description"


def _clean_cell(value: str | None) -> str:
    if not value:
        return ""
    text = " ".join(value.split())
    return normalize_dashes(text)


def _parse_page_meta(page) -> dict:
    text = page.extract_text() or ""
    meta = {"AC_MSN": "", "REPORT_DATE": ""}
    m = _MSN_RE.search(text)
    if m:
        meta["AC_MSN"] = m.group(1)
    m = _AS_OF_RE.search(text)
    if m:
        meta["REPORT_DATE"] = m.group(1)
    return meta


def _extract_page_rows(page) -> list[dict]:
    meta = _parse_page_meta(page)
    rows_out: list[dict] = []

    current_section = ""
    current_zone = ""
    header_cols: list[str] | None = None

    for table in page.extract_tables():
        for raw in table:
            cells = [_clean_cell(c) for c in raw]
            if not any(cells):
                continue

            # Section-header row (Fire Extinguisher template only -- see
            # module docstring for why this is gated to before any
            # "Description"-style header has been seen on the page).
            if (header_cols is None or header_cols[0] == _FIREX_HEADER_FIRST_CELL) \
                    and cells[0] and not any(cells[1:]):
                current_section = cells[0]
                continue

            if cells[0] in (_FIREX_HEADER_FIRST_CELL, _OXYGEN_HEADER_FIRST_CELL):
                header_cols = cells
                continue

            if header_cols is None:
                # Stray row before any column header seen -- skip.
                continue

            if header_cols[0] == _FIREX_HEADER_FIRST_CELL:
                position = cells[0] if len(cells) > 0 else ""
                part_number = cells[1] if len(cells) > 1 else ""
                serial_number = cells[2] if len(cells) > 2 else ""
                last_weight_date = cells[3] if len(cells) > 3 else ""
                zone = ""
                section = current_section
            else:
                if cells[0]:
                    current_section = cells[0]
                if len(cells) > 1 and cells[1]:
                    current_zone = cells[1]
                section = current_section
                zone = current_zone
                position = cells[2] if len(cells) > 2 else ""
                part_number = cells[3] if len(cells) > 3 else ""
                serial_number = cells[4] if len(cells) > 4 else ""
                last_weight_date = ""

            if not position and not part_number and not serial_number:
                continue

            row = {
                "REPORT_SECTION": section,
                "ZONE": zone,
                "POSITION": position,
                "PART_NUMBER": part_number,
                "SERIAL_NUMBER": serial_number,
                "LAST_WEIGHT_DATE": last_weight_date,
            }
            row.update(meta)
            rows_out.append(row)

    return rows_out


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            for row in _extract_page_rows(page):
                row["_page"] = page_num
                records.append(row)
    return records
