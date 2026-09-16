""""HARD TIME COMPONENTS" -- born-digital, real ruled (bordered) table,
extracted via pdfplumber's `find_tables()`/`extract_table()` rather than
coordinate-word-bucketing (confirmed directly: `page.edges` on the sample
file is populated -- 397 line segments on page 1 -- and
`page.find_tables()` returns 3 clean tables per page: two small
aircraft-header key/value tables and one large ruled data table with a
stable 19-column shape on every page, so pdfplumber's own cell-boundary
detection is used directly instead of re-deriving column edges from word
x-positions).

This is a distinct template from this project's other
"Hard Time Component(s) ..."-titled variants: its own title line is the
exact two-word-shorter phrase "HARD TIME COMPONENTS" (no "STATUS",
no "LIST", no "REPORT" suffix) -- checked directly against
`hard_time_component_list.py` ("HARD TIME COMPONENT LIST", singular
COMPONENT, different header block and column layout, coordinate-word
extraction not a ruled table) and
`georgian_airways_ht_components_status.py`/`..._scanned.py`
("HARD TIME COMPONENTS STATUS FOR A/C-REGISTRATION", a superset phrase of
this file's own title but never followed by "STATUS FOR" here -- a
different template with its own distinct header block and column set).

Header block (repeats verbatim at the top of every page, as two small
key/value tables to the left and right of the title line)::

    HARD TIME COMPONENTS
    AIRCRAFT REGISTRATION <tail>   TOTAL TIMES SINCE NEW <n>
    SERIAL NO. <aircraft msn>      TOTAL CYCLES SINCE NEW <n>
    SUMMARY DATE <dd-Mon-yy>

followed by the main ruled data table, two header rows tall::

    ATA | MPD REF. | DESCRIPTION | POS | PART NUMBER | SERIAL NUMBER |
        APP Y/N | TASK | CMM REF. | INTERVAL | DATE OF LAST OH/NEW |
        NEXT DUE (A/C) | REMAINING
    (row 2, sub-headers under the grouped columns:)
        DAYS FH FC | DATE | FH FC | DAYS FH FC

Row grain: one row per tracked hard-time component/task. Columns, left to
right (19 total, matching the ruled table's own cell grid exactly)::

    ATA | MPD_REFERENCE | DESCRIPTION | POS | PART_NUMBER | SERIAL_NUMBER |
    APPLICABLE | TASK | CMM_REFERENCE |
    INTERVAL_DAYS | INTERVAL_FH | INTERVAL_FC |
    DATE_OF_LAST_OH_NEW |
    NEXT_DUE_DATE | NEXT_DUE_FH | NEXT_DUE_FC |
    REMAINING_DAYS | REMAINING_FH | REMAINING_FC

MPD_REFERENCE and CMM_REFERENCE are present as header columns but are
never once populated in the sample file (every cell in both columns reads
empty) -- both are still carried through, blank, rather than dropped, on
the assumption another file of this same template may populate them.

NEXT_DUE_FH/NEXT_DUE_FC and REMAINING_FH/REMAINING_FC each hold whichever
one basis applies to that row's own component (the other reading a bare
`-`), and the populated one is captured as the ruled table already renders
it -- a single cell carrying both the figure and its own unit suffix
together (e.g. `94,188 FH`, `6,109 DYS`) -- rather than re-splitting
figure from unit into separate fields: the source table renders them as
one cell with no internal delimiter to split on reliably, so this follows
the project convention of not force-splitting ambiguous combined text.

Column extraction uses `page.find_tables()` and picks out the one table
per page whose own first extracted row starts with the literal header
cell "ATA" (rather than assuming a fixed table index), so a page with an
extra or missing decorative table would not silently misalign the column
set.

TASK is a free-text field and, on a very small number of rows, its cell
carries more than one physical line worth of text joined with an internal
line break; the join for `\\n` is normalized to a single space, not
mid-word split. On rarer rows still, the source table's own cell/row
boundary detection appears to place a wrapped continuation word from the
*next* printed row's TASK cell into the current row's TASK cell instead
(confirmed directly: one row in the sample file reads TASK
"Functional Check Cleaning" while the very next row -- a different
serial number of the same component/task pair -- reads TASK empty,
i.e. the second row's own "Cleaning" was captured by the first row's
cell instead of its own). This is a genuine source-table rendering
ambiguity above the ruled-cell boundary, not something this parser
introduces or can safely resolve without guessing, so the raw cell text
is carried through as-is rather than force-corrected.

A small number of PART_NUMBER cells carry a trailing annotation fragment
from a wrapped second line (e.g. an amendment marker) merged into the
same cell as the base part number, separated by a space -- carried
through as one PART_NUMBER value rather than guessed apart from the
following SERIAL_NUMBER cell's own similarly-wrapped continuation; this
is expected to surface as a validation flag (PART_NUMBER's global rule
disallows internal spaces) rather than being silently "fixed".

Each page ends with a blank signature footer line ("Sign:____________
Title:____________  <n> of <total>") below the ruled table -- outside the
data table's own bbox, so it is never captured as a data row. It carries
no name, no data -- confirmed directly across every page of the sample
file (the sign/title lines are always blank).

Header metadata (aircraft registration, aircraft serial number, summary
date, total times since new, total cycles since new) is parsed once from
page 1's own header tables and stamped on every row.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.ht_variants._base import merged_rules
from shared.cleanup import normalize_dashes

NAME = "Hard Time Components (Bordered Table)"
SIGNATURES = [
    # Distinctive combination that only appears on this template's own
    # aircraft-header key/value table. Checked against every SIGNATURES
    # list in occm.py/ht.py/llp.py and every occm_variants/ht_variants/
    # llp_variants module (including a plain grep for "SINCE NEW" across
    # every one of those files); no collision found -- the nearest
    # look-alikes are occm_variants/config_slot_occm.py's own
    # "TIME SINCE NEW TIME SINCE OVERHAUL ..." (a different, longer
    # phrase: "TIME" not "TOTAL TIMES", and no "SINCE NEW" occurrence in
    # this file's own header reads "TOTAL TIMES SINCE NEW"/"TOTAL CYCLES
    # SINCE NEW" instead) and ht_variants/mm510.py's own
    # "Time Since New : <FH>  Cycle Since New : <FC>" (again "Time"/"Cycle"
    # singular, not "TOTAL TIMES"/"TOTAL CYCLES").
    "TOTAL TIMES SINCE NEW",
    "TOTAL CYCLES SINCE NEW",
]

CANONICAL_COLUMNS = [
    "ATA",
    "MPD_REFERENCE",
    "DESCRIPTION",
    "POS",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "APPLICABLE",
    "TASK",
    "CMM_REFERENCE",
    "INTERVAL_DAYS",
    "INTERVAL_FH",
    "INTERVAL_FC",
    "DATE_OF_LAST_OH_NEW",
    "NEXT_DUE_DATE",
    "NEXT_DUE_FH",
    "NEXT_DUE_FC",
    "REMAINING_DAYS",
    "REMAINING_FH",
    "REMAINING_FC",
    # Header metadata -- same on every row of a given file.
    "AC_REG",
    "AC_SERIAL_NO",
    "SUMMARY_DATE",
    "TOTAL_TIMES_SINCE_NEW",
    "TOTAL_CYCLES_SINCE_NEW",
]

_DATE_RE = r"^\d{1,2}-[A-Za-z]{3}-\d{2}$"
_NUM_RE = r"^[\d,]+$"
_NUM_OR_NA_RE = r"^(?:[\d,]+|N/A)$"
_BASIS_RE = r"^(?:[\d,]+ (?:FH|FC|DYS)|-)$"

_OVERRIDES = {
    "MPD_REFERENCE":         {"allow_empty": True},
    "POS":                   {"allow_empty": True},
    "APPLICABLE":            {"pattern": r"^[YN]$", "allow_empty": True},
    "TASK":                  {"allow_empty": True},
    "CMM_REFERENCE":         {"allow_empty": True},
    "INTERVAL_DAYS":         {"pattern": _NUM_OR_NA_RE, "allow_empty": True},
    "INTERVAL_FH":           {"pattern": _NUM_OR_NA_RE, "allow_empty": True},
    "INTERVAL_FC":           {"pattern": _NUM_OR_NA_RE, "allow_empty": True},
    "DATE_OF_LAST_OH_NEW":   {"pattern": _DATE_RE, "allow_empty": True},
    "NEXT_DUE_DATE":         {"pattern": _DATE_RE + r"|^-$", "allow_empty": True},
    "NEXT_DUE_FH":           {"pattern": _BASIS_RE, "allow_empty": True},
    "NEXT_DUE_FC":           {"pattern": _BASIS_RE, "allow_empty": True},
    "REMAINING_DAYS":        {"pattern": _BASIS_RE, "allow_empty": True},
    "REMAINING_FH":          {"pattern": _BASIS_RE, "allow_empty": True},
    "REMAINING_FC":          {"pattern": _BASIS_RE, "allow_empty": True},
    "AC_REG":                {"pattern": r"^[A-Z0-9\-]+$", "uppercase": True,
                               "allow_empty": True},
    "AC_SERIAL_NO":          {"pattern": r"^[A-Z0-9\-]+$", "uppercase": True,
                               "allow_empty": True},
    "SUMMARY_DATE":          {"pattern": _DATE_RE, "allow_empty": True},
    "TOTAL_TIMES_SINCE_NEW": {"pattern": _NUM_RE, "allow_empty": True},
    "TOTAL_CYCLES_SINCE_NEW": {"pattern": _NUM_RE, "allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_HEADER_FIRST_CELL = "ATA"
_HEADER_SECOND_ROW_FIRST_CELL = "DAYS"


def _clean_cell(value: str | None) -> str:
    if not value:
        return ""
    # Multi-line cell content (wrapped text within one ruled cell) is
    # joined with a single space rather than left with an embedded
    # newline.
    text = " ".join(value.split())
    return normalize_dashes(text)


def _find_data_table(page):
    for table in page.find_tables():
        rows = table.extract()
        if not rows:
            continue
        first_cell = (rows[0][0] or "").strip()
        if first_cell == _HEADER_FIRST_CELL:
            return table, rows
    return None, None


def _parse_header_meta(page) -> dict:
    meta = {
        "AC_REG": "",
        "AC_SERIAL_NO": "",
        "SUMMARY_DATE": "",
        "TOTAL_TIMES_SINCE_NEW": "",
        "TOTAL_CYCLES_SINCE_NEW": "",
    }
    for table in page.find_tables():
        rows = table.extract()
        for row in rows:
            if len(row) < 2 or not row[0]:
                continue
            label = row[0].strip().upper()
            value = _clean_cell(row[1])
            if label == "AIRCRAFT REGISTRATION":
                meta["AC_REG"] = value
            elif label == "SERIAL NO.":
                meta["AC_SERIAL_NO"] = value
            elif label == "SUMMARY DATE":
                meta["SUMMARY_DATE"] = value
            elif label == "TOTAL TIMES SINCE NEW":
                meta["TOTAL_TIMES_SINCE_NEW"] = value
            elif label == "TOTAL CYCLES SINCE NEW":
                meta["TOTAL_CYCLES_SINCE_NEW"] = value
    return meta


_ATA_RE = re.compile(r"^\d{1,2}$")


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []

    with pdfplumber.open(pdf_path) as pdf:
        meta = {}
        if pdf.pages:
            meta = _parse_header_meta(pdf.pages[0])

        for page_num, page in enumerate(pdf.pages, start=1):
            _, rows = _find_data_table(page)
            if not rows:
                continue

            # Drop the two-row header (row 0: top-level labels; row 1:
            # DAYS/FH/FC sub-labels under the grouped columns).
            data_rows = rows
            if data_rows and (data_rows[0][0] or "").strip() == _HEADER_FIRST_CELL:
                data_rows = data_rows[1:]
            if data_rows and (data_rows[0][9] or "").strip() == _HEADER_SECOND_ROW_FIRST_CELL:
                data_rows = data_rows[1:]

            for raw in data_rows:
                if len(raw) < 19:
                    continue
                ata = _clean_cell(raw[0])
                if not _ATA_RE.match(ata):
                    # Not a recognisable data row -- skip rather than
                    # force it into a row.
                    continue
                row = {
                    "ATA": ata,
                    "MPD_REFERENCE": _clean_cell(raw[1]),
                    "DESCRIPTION": _clean_cell(raw[2]),
                    "POS": _clean_cell(raw[3]),
                    "PART_NUMBER": _clean_cell(raw[4]),
                    "SERIAL_NUMBER": _clean_cell(raw[5]),
                    "APPLICABLE": _clean_cell(raw[6]),
                    "TASK": _clean_cell(raw[7]),
                    "CMM_REFERENCE": _clean_cell(raw[8]),
                    "INTERVAL_DAYS": _clean_cell(raw[9]),
                    "INTERVAL_FH": _clean_cell(raw[10]),
                    "INTERVAL_FC": _clean_cell(raw[11]),
                    "DATE_OF_LAST_OH_NEW": _clean_cell(raw[12]),
                    "NEXT_DUE_DATE": _clean_cell(raw[13]),
                    "NEXT_DUE_FH": _clean_cell(raw[14]),
                    "NEXT_DUE_FC": _clean_cell(raw[15]),
                    "REMAINING_DAYS": _clean_cell(raw[16]),
                    "REMAINING_FH": _clean_cell(raw[17]),
                    "REMAINING_FC": _clean_cell(raw[18]),
                }
                row["_page"] = page_num
                row.update(meta)
                records.append(row)

    return records
