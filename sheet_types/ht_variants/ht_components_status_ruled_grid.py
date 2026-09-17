"""Born-digital "HT COMPONENTS STATUS" report, real ruled (bordered) table.

Header block (repeats verbatim at the top of every page, all inside the
same first table cell -- pdfplumber merges the whole block into row 0's
first column since there are no ruling lines separating those lines from
each other)::

    HT COMPONENTS STATUS
    <A/C REG>, MSN-<msn>
    AS OF: <dd-Mon-yy>
    TSN: <n>
    CSN: <n>
    HT LIMIT LAST DONE/ DOM NEXT DUE REMAINING

followed by the main ruled data table, two header rows tall (row 1: group
labels over the grouped sub-columns; row 2: the actual per-column
labels)::

    row 1: (blank) x7 | HT LIMIT (x4) | (blank x3) | LAST DONE/ DOM (x3) |
           NEXT DUE (x3) | REMAINING (x3)
    row 2: SL NO | MPD REF | DESCRIPTION | PART NO | SERIAL NO | POSITION |
           TASK REQUIRED | DY | FH | FC | UNIT | DOM | INSTALLED |
           DATE | FH | FC | DATE | FH | FC | DAY | FH | FC

Confirmed directly against the sample file: `page.extract_tables()`
returns a clean 22-column grid on every one of its pages (a second, tiny
3-row table alongside it just repeats the AS-OF/TSN/CSN header as a
key/value pair and is not a data table). Every data row carries all 22
cells and a numeric SL NO in column 0 -- no ragged rows, no missing
columns -- so this parser reads the ruled grid directly rather than
falling back to word-position bucketing.

Column grain, left to right (22 total, matching the ruled grid's own
cell boundaries exactly)::

    SL_NO | MPD_REF | DESCRIPTION | PART_NUMBER | SERIAL_NUMBER |
    POSITION | TASK_REQUIRED |
    LIMIT_DY | LIMIT_FH | LIMIT_FC | LIMIT_UNIT |
    DOM | INSTALLED_DATE |
    LAST_DONE_DATE | LAST_DONE_FH | LAST_DONE_FC |
    NEXT_DUE_DATE | NEXT_DUE_FH | NEXT_DUE_FC |
    REMAINING_DAY | REMAINING_FH | REMAINING_FC

MPD_REF is a mixed free-text field, not a bare 2-digit ATA chapter: seen
values include plain `NN-NNN-NN` task codes and also EO-style references
(e.g. an `EO/B737/NN` or `EO B737/NN` shape). Carried through as-is
rather than force-parsed into a stricter ATA-only shape.

LIMIT_DY sometimes carries free text instead of a day count (e.g. an
"AS PER <reference>" note, or a plain year count like "5 YRS") when the
component's actual limit is defined by an external document rather than a
number -- kept as-is rather than guessed apart, same "never force a wrong
split" rule this project follows elsewhere for ambiguous trailing/limit
cells.

INSTALLED_DATE is usually a date but a meaningful minority of rows carry
a bare "Y" instead (confirmed installed, exact date not tracked by this
export) -- kept as-is rather than coerced to a date pattern.

SERIAL_NUMBER and DOM are occasionally "AS PER LIST" / "VARIOUS"-style
free text on rows that track a pooled/serialized-by-list item rather than
a single serialized part -- left as free text; the pattern-validation
step already flags these as unusual so an analyst can review rather than
this parser silently normalizing them away.

Header metadata (aircraft registration, MSN, as-of date, TSN, CSN) is
parsed once from page 1's own merged header cell and stamped on every
row.

No signature block, name, or other personally-identifying content was
found anywhere in the sample file's text layer.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.ht_variants._base import merged_rules
from shared.cleanup import normalize_dashes

NAME = "HT Components Status (Ruled Grid)"

SIGNATURES = [
    # This template's own bare title line. Checked against every
    # SIGNATURES list in occm.py/ht.py/llp.py and every
    # occm_variants/ht_variants/llp_variants module (including a plain
    # grep for "HT COMPONENTS STATUS"); no collision found. Distinct from
    # georgian_airways_ht_components_status.py's own much longer
    # "HARD TIME COMPONENTS STATUS FOR A/C-REGISTRATION" (that phrase
    # starts with "HARD TIME", not the bare "HT" this template uses, and
    # is never a substring of it) and from
    # hard_time_status_mpd_cert_fin.py's own "HARD TIME COMPONENTS
    # STATUS" (again "HARD TIME", not "HT").
    "HT COMPONENTS STATUS",
    # Backup anchor: the grouped-column header line, verbatim, as it
    # collapses out of the merged first-page header cell. Checked against
    # every SIGNATURES list in occm.py/ht.py/llp.py and every
    # occm_variants/ht_variants/llp_variants module (including a plain
    # grep for "HT LIMIT"); no collision found.
    "HT LIMIT LAST DONE/ DOM NEXT DUE REMAINING",
]

CANONICAL_COLUMNS = [
    "SL_NO",
    "MPD_REF",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "POSITION",
    "TASK_REQUIRED",
    "LIMIT_DY",
    "LIMIT_FH",
    "LIMIT_FC",
    "LIMIT_UNIT",
    "DOM",
    "INSTALLED_DATE",
    "LAST_DONE_DATE",
    "LAST_DONE_FH",
    "LAST_DONE_FC",
    "NEXT_DUE_DATE",
    "NEXT_DUE_FH",
    "NEXT_DUE_FC",
    "REMAINING_DAY",
    "REMAINING_FH",
    "REMAINING_FC",
    # Header metadata -- same on every row of a given file.
    "AC_REG",
    "MSN",
    "AS_OF_DATE",
    "TSN",
    "CSN",
]

_DATE_RE = r"^\d{1,2}-[A-Za-z]{3}-\d{2,4}$"

_OVERRIDES = {
    "SL_NO":            {"pattern": r"^\d+$"},
    "MPD_REF":          {"allow_empty": True},
    "POSITION":         {"allow_empty": True, "uppercase": True},
    "TASK_REQUIRED":    {"allow_empty": True, "uppercase": True},
    "LIMIT_DY":         {"allow_empty": True},
    "LIMIT_FH":         {"allow_empty": True},
    "LIMIT_FC":         {"allow_empty": True},
    "LIMIT_UNIT":       {"pattern": r"^(?:DY|FH|FC)$", "allow_empty": True},
    "DOM":              {"allow_empty": True},
    "INSTALLED_DATE":   {"allow_empty": True},
    "LAST_DONE_DATE":   {"allow_empty": True},
    "LAST_DONE_FH":     {"allow_empty": True},
    "LAST_DONE_FC":     {"allow_empty": True},
    "NEXT_DUE_DATE":    {"allow_empty": True},
    "NEXT_DUE_FH":      {"allow_empty": True},
    "NEXT_DUE_FC":      {"allow_empty": True},
    "REMAINING_DAY":    {"allow_empty": True},
    "REMAINING_FH":     {"allow_empty": True},
    "REMAINING_FC":     {"allow_empty": True},
    "AC_REG":           {"pattern": r"^[A-Z0-9\-]+$", "uppercase": True,
                          "allow_empty": True},
    "MSN":              {"pattern": r"^\d+$", "allow_empty": True},
    "AS_OF_DATE":       {"pattern": _DATE_RE, "allow_empty": True},
    "TSN":              {"pattern": r"^[\d,]+$", "allow_empty": True},
    "CSN":              {"pattern": r"^[\d,]+$", "allow_empty": True},
    # Free-text fields with no dedicated project-wide rule of their own
    # still get one here so allow_empty is explicit rather than relying
    # on the "missing key = flag-friendly default" fallback.
    "PART_NUMBER":      {"allow_empty": True},
    "SERIAL_NUMBER":    {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_HEADER_TITLE = "HT COMPONENTS STATUS"
_SL_NO_RE = re.compile(r"^\d+$")
_META_RE = {
    "AC_REG": re.compile(r"([A-Z0-9\-]+),\s*MSN", re.IGNORECASE),
    "MSN": re.compile(r"MSN[\s\-]*(\d+)", re.IGNORECASE),
    "AS_OF_DATE": re.compile(r"AS OF:\s*([\d\-A-Za-z]+)"),
    "TSN": re.compile(r"TSN:\s*([\d,]+)"),
    "CSN": re.compile(r"CSN:\s*([\d,]+)"),
}


def _clean_cell(value: str | None) -> str:
    if not value:
        return ""
    text = " ".join(value.split())
    return normalize_dashes(text)


def _find_data_table(page):
    for table in page.extract_tables():
        if not table:
            continue
        first_cell = (table[0][0] or "").strip()
        if first_cell.startswith(_HEADER_TITLE):
            return table
    return None


def _parse_header_meta(header_cell: str) -> dict:
    meta = {"AC_REG": "", "MSN": "", "AS_OF_DATE": "", "TSN": "", "CSN": ""}
    text = normalize_dashes(header_cell or "")
    for key, rx in _META_RE.items():
        m = rx.search(text)
        if m:
            meta[key] = m.group(1).strip()
    return meta


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []

    with pdfplumber.open(pdf_path) as pdf:
        meta = {}
        for page in pdf.pages:
            table = _find_data_table(page)
            if table:
                meta = _parse_header_meta(table[0][0])
                break

        for page_num, page in enumerate(pdf.pages, start=1):
            table = _find_data_table(page)
            if not table:
                continue

            # Row 0: merged title/header-metadata cell. Row 1: grouped
            # column labels. Row 2: actual per-column labels. Data starts
            # at row 3.
            data_rows = table[3:]

            for raw in data_rows:
                if len(raw) < 22:
                    continue
                sl_no = _clean_cell(raw[0])
                if not _SL_NO_RE.match(sl_no):
                    # Not a recognisable data row -- skip rather than
                    # force it into a row.
                    continue
                row = {
                    "SL_NO": sl_no,
                    "MPD_REF": _clean_cell(raw[1]),
                    "DESCRIPTION": _clean_cell(raw[2]),
                    "PART_NUMBER": _clean_cell(raw[3]),
                    "SERIAL_NUMBER": _clean_cell(raw[4]),
                    "POSITION": _clean_cell(raw[5]),
                    "TASK_REQUIRED": _clean_cell(raw[6]),
                    "LIMIT_DY": _clean_cell(raw[7]),
                    "LIMIT_FH": _clean_cell(raw[8]),
                    "LIMIT_FC": _clean_cell(raw[9]),
                    "LIMIT_UNIT": _clean_cell(raw[10]),
                    "DOM": _clean_cell(raw[11]),
                    "INSTALLED_DATE": _clean_cell(raw[12]),
                    "LAST_DONE_DATE": _clean_cell(raw[13]),
                    "LAST_DONE_FH": _clean_cell(raw[14]),
                    "LAST_DONE_FC": _clean_cell(raw[15]),
                    "NEXT_DUE_DATE": _clean_cell(raw[16]),
                    "NEXT_DUE_FH": _clean_cell(raw[17]),
                    "NEXT_DUE_FC": _clean_cell(raw[18]),
                    "REMAINING_DAY": _clean_cell(raw[19]),
                    "REMAINING_FH": _clean_cell(raw[20]),
                    "REMAINING_FC": _clean_cell(raw[21]),
                }
                row["_page"] = page_num
                row.update(meta)
                records.append(row)

    return records
