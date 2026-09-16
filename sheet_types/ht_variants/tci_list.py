""""TCI List" -- born-digital, real ruled (bordered) table, extracted via
pdfplumber's `find_tables()`/`extract_table()` rather than coordinate-word
bucketing (confirmed directly: the sample file's early pages have real
vector rects/edges -- pdfplumber's own cell-boundary detection returns one
clean 18-column table per page, so that is used directly instead of
re-deriving column edges from word x-positions).

Header block, page 1 only (repeats as a small key/value strip above the
main table; later pages of the same file carry no repeated header row,
just the "TCI List" title text and data rows straight through)::

    TCI List
    CURRENT DATE <dd.mm.yyyy> TAH <n> TAC <n>   INSTALLATION DATA   INTERVAL   NEXT DUE
    ATA OMP REF REQ PN SN DESCRIPTION POS INST DATE TAH TAC TSN CSN INT H INT C INT D ND H ND C ND DATE

Row grain: one row per tracked hard-time component/requirement
combination (a single PN/SN pair commonly repeats across several rows,
once per distinct maintenance requirement code -- e.g. a restoration/
overhaul limit and a separate detailed-inspection limit on the same
physical unit). Columns, left to right (18 total, matching the ruled
table's own cell grid exactly)::

    ATA | OMP_REF | REQ | PART_NUMBER | SERIAL_NUMBER | DESCRIPTION | POS |
    INST_DATE | TAH | TAC | TSN | CSN |
    INT_H | INT_C | INT_D |
    ND_H | ND_C | ND_DATE

OMP_REF usually holds a numeric task-reference code (e.g. "215200-01-1")
but a life-limited-part subset of rows instead carries the literal text
"LIFE LIMIT" (with REQ correspondingly reading "LL") -- confirmed directly
on the sample file, not an extraction artefact -- so OMP_REF is kept as
free text rather than forced into a numeric pattern.

REQ is a short maintenance-requirement-type code (e.g. RST/FNC/DIS/OPC/
DET/SDI/GVI/LL); TAH/TAC/TSN/CSN commonly read the literal string
"UNKNOWN" in place of a number when that basis isn't tracked for a given
row.

INT_H/INT_C/INT_D and ND_H/ND_C/ND_DATE are a ragged trailing block: each
row is tracked against whichever bases apply to its own component (hours,
cycles, and/or calendar days for the interval; hours, cycles, and/or a
calendar date for the next-due side), so most rows leave two of the three
interval cells and/or two of the three next-due cells blank. Column
assignment is by the ruled table's own cell position (not word order or
count), so blank cells stay correctly blank rather than shifting
neighbouring values left -- confirmed directly across many ragged rows on
the sample file (e.g. a row with only INT_D populated correctly leaves
INT_H/INT_C blank rather than INT_D's value landing in INT_H).

Numeric cells in the INT_*/ND_* columns are printed with a plain space as
the thousands separator on this template (e.g. "12 000", "3 285") rather
than a comma/dot/apostrophe -- kept as-is (not the project's shared
comma/dot/apostrophe `int_range` numeric parsing, which doesn't recognise
a bare space as a separator) and validated with a pattern that tolerates
the internal space instead.

Header metadata (current report date, current aircraft TAH, current
aircraft TAC) is parsed once from page 1's own small key/value strip
above the main table and stamped on every row of the file.

Multi-page handling: this format's table is a genuine ruled (bordered)
table on every born-digital page, so `find_tables()` picks it up
cleanly throughout. On the specific sample file investigated, the final
page of the document is not born-digital at all -- it is a raster
image (JPEG) embedded as the entire page content, with no text layer and
no vector rects/edges (confirmed directly: `page.chars`, `page.edges`,
`page.rects` are all empty on that page, while `page.images` holds one
full-page JPEG). Per-cell OCR was attempted on that page (crops aligned
to the page's own detected grid lines, not the born-digital column
x-positions, since a rescan of a printed page does not reproduce the
same absolute coordinates) and came back with a meaningful digit error
rate on the numeric columns (e.g. 9/2 confusion recurring across
multiple cells) -- unreliable for hard-time data, so that page's rows are
not extracted. `extract()` silently skips any page with no ruled table
(no born-digital text/vector content) rather than guessing at OCR'd
values; the returned records cover every born-digital page of the file.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.ht_variants._base import merged_rules
from shared.cleanup import normalize_dashes

NAME = "TCI List"
SIGNATURES = [
    # The full column-header line is used rather than the bare "TCI List"
    # title (which, while not found colliding with anything today, is
    # short and generic enough to risk a future false-positive on an
    # unrelated format that also abbreviates "Time Controlled Items").
    # Checked against every SIGNATURES list in occm.py/ht.py/llp.py and
    # every occm_variants/ht_variants/llp_variants module (including a
    # plain grep for "OMP REF" and "TCI"); no collision found -- the only
    # existing "TCI" occurrence anywhere in the project is
    # occm_variants/aircraft_occm_list_hcd.py's unrelated "TSI TST TSO TSN
    # TTR TCI Limit Limit Type ..." column-header phrase, a different
    # contiguous string in both directions.
    "ATA OMP REF REQ PN SN DESCRIPTION POS INST DATE",
]

CANONICAL_COLUMNS = [
    "ATA",
    "OMP_REF",
    "REQ",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
    "POS",
    "INST_DATE",
    "TAH",
    "TAC",
    "TSN",
    "CSN",
    "INT_H",
    "INT_C",
    "INT_D",
    "ND_H",
    "ND_C",
    "ND_DATE",
    # Header metadata -- same on every row of a given file.
    "CURRENT_DATE",
    "CURRENT_TAH",
    "CURRENT_TAC",
]

_DATE_RE = r"^\d{2}\.\d{2}\.\d{4}$"
_HOURS_OR_UNKNOWN_RE = r"^(?:\d+|UNKNOWN)$"
_SPACED_NUM_RE = r"^\d+(?: \d{3})*$"

_OVERRIDES = {
    # Usually a numeric task-reference code, but a "LIFE LIMIT" subset of
    # rows carries that literal phrase instead -- see module docstring.
    "OMP_REF":       {"allow_empty": False},
    "REQ":           {"pattern": r"^[A-Z]{2,4}$", "uppercase": True,
                       "allow_empty": False},
    # On a small number of rows, this cell's real value gets interleaved
    # character-by-character with a stray fragment of the same row's own
    # (overflowing) DESCRIPTION text -- confirmed directly against a
    # rendered image of every affected row: the visible printed value is
    # a clean short code (e.g. "ENG1", "6137HM"), but the PDF's text
    # layer yields a longer glued string with extra letters spliced in
    # (e.g. "-ELNHG1", "E6N1T37HM") because the DESCRIPTION text extends
    # past its own ruled column border into this column's x-range while
    # staying visually clipped/hidden there. Rather than guess which
    # characters are real, this is caught by pattern shape: every
    # genuine POS value on this template is either DIGITS+LETTERS+DIGITS
    # (one run of each, e.g. "1500KM1"), LETTERS+DIGITS optionally
    # followed by " " + a second alphanumeric word (e.g. "ENG 1",
    # "ENGINE LH", "NOSE LANDING"), or bare LETTERS (e.g. "DFDR") --
    # never more than one digit-run and one letter-run outside the
    # optional second word. A glued/interleaved value alternates between
    # letters and digits far more than that and fails to match.
    "POS":           {"pattern": r"^(?:\d{1,4}[A-Z]{1,6}\d{0,3}"
                                  r"|[A-Z]{1,10}\d{0,3}(?: [A-Z0-9]{1,10})?)$",
                       "uppercase": True, "allow_empty": True},
    "INST_DATE":     {"pattern": _DATE_RE, "allow_empty": True},
    "TAH":           {"pattern": _HOURS_OR_UNKNOWN_RE, "allow_empty": True},
    "TAC":           {"pattern": _HOURS_OR_UNKNOWN_RE, "allow_empty": True},
    "TSN":           {"pattern": _HOURS_OR_UNKNOWN_RE, "allow_empty": True},
    "CSN":           {"pattern": _HOURS_OR_UNKNOWN_RE, "allow_empty": True},
    "INT_H":         {"pattern": _SPACED_NUM_RE, "allow_empty": True},
    "INT_C":         {"pattern": _SPACED_NUM_RE, "allow_empty": True},
    "INT_D":         {"pattern": _SPACED_NUM_RE, "allow_empty": True},
    "ND_H":          {"pattern": _SPACED_NUM_RE, "allow_empty": True},
    "ND_C":          {"pattern": _SPACED_NUM_RE, "allow_empty": True},
    "ND_DATE":       {"pattern": _DATE_RE, "allow_empty": True},
    "CURRENT_DATE":  {"pattern": _DATE_RE, "allow_empty": True},
    "CURRENT_TAH":   {"pattern": _SPACED_NUM_RE, "allow_empty": True},
    "CURRENT_TAC":   {"pattern": _SPACED_NUM_RE, "allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_ATA_RE = re.compile(r"^\d{2}$")

_COL_KEYS = CANONICAL_COLUMNS[:18]  # the 18 per-row table columns


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
        for row in rows:
            if row and (row[0] or "").strip() == "ATA":
                return table, rows
            # Pages after the first carry no repeated header row -- any
            # table whose first column is entirely 2-digit ATA codes (or
            # blank continuation cells) once the header/metadata rows are
            # excluded is treated as the data table.
        first_cells = [(row[0] or "").strip() for row in rows]
        if any(_ATA_RE.match(c) for c in first_cells):
            return table, rows
    return None, None


def _parse_header_meta(page) -> dict:
    meta = {"CURRENT_DATE": "", "CURRENT_TAH": "", "CURRENT_TAC": ""}
    for table in page.find_tables():
        rows = table.extract()
        for row in rows:
            if not row or len(row) < 7:
                continue
            if (row[0] or "").strip() != "" or row[1] or row[2] or row[3]:
                continue
            date_val = _clean_cell(row[4])
            tah_val = _clean_cell(row[5])
            tac_val = _clean_cell(row[6])
            if re.match(_DATE_RE, date_val):
                meta["CURRENT_DATE"] = date_val
                meta["CURRENT_TAH"] = tah_val
                meta["CURRENT_TAC"] = tac_val
                return meta
    return meta


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []

    with pdfplumber.open(pdf_path) as pdf:
        meta = {}
        if pdf.pages:
            meta = _parse_header_meta(pdf.pages[0])

        for page in pdf.pages:
            _, rows = _find_data_table(page)
            if not rows:
                # No ruled table found on this page -- e.g. a scanned
                # image-only page with no text/vector content. Skip
                # rather than guess; see module docstring.
                continue

            for row in rows:
                first_cell = (row[0] or "").strip()
                if not _ATA_RE.match(first_cell):
                    # Header row ("ATA" literal) or metadata row (blank
                    # first four cells) -- not a data row.
                    continue
                record = {}
                for i, col in enumerate(_COL_KEYS):
                    record[col] = _clean_cell(row[i] if i < len(row) else "")
                record.update(meta)
                records.append(record)

    return records
