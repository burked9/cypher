"""All Fitted Aircraft Component LOG -- title reads literally "All Fitted
Aircraft Component LOG" followed by an "AIRCRAFT <reg>" line and a small
metadata block. Has a REAL TEXT LAYER (confirmed directly via a pdfplumber
pass over the whole real sample file) -- this module is synchronous,
pdfplumber-only, no OCR.

Header block, first page only (confirmed: not repeated on later pages)::

    All Fitted Aircraft Component LOG
    AIRCRAFT <reg>
    SINCE NEW HOUR: <n>
    CYCLES: <n>
    UNIT REMOVAL BASED ON <n> HOURS AND <n> CYCLES PER DAY
    A/C at installation
    ATA PART desc  Part No  Serial No  Stock No  Pos   Date  Time  Cycle

parsed once from page 1 and stamped on every row, same convention this
project's other header-plus-body OCCM variants use. The last three column
headers ("Date", "Time", "Cycle") sit under the "A/C at installation"
super-header -- confirmed directly against word positions -- i.e. they are
the aircraft's own total hours/cycles *at the moment this part was
installed*, not the part's own life. "Time"/"Cycle" both read "0.00"/"-"
for parts installed since new (no prior aircraft life to record).

Table layout, confirmed directly against real word x-positions on the
rendered page (columns are NOT evenly spaced, so a simple `.split()`
tokenizer would misalign the free-text DESCRIPTION and POSITION columns,
both of which can contain embedded spaces)::

    <ata> <description...> <part_no> <serial_no> <stock_no> <pos> <date> <hours> <cycles>

Row extraction uses `extract_words()` (word-level boxes); words are
clustered into visual rows by `top` position, then each word is assigned to
a column purely by which column's x-range its center falls in -- the same
geometric "never guess a wrong split" technique this project's other
position-column OCCM variants use, so a blank cell simply contributes no
word to its column and comes out as "" rather than being guessed or shifted
into a neighbour.

Header/body split (page 1 only): the header block (title + metadata + the
two-band column-group header) sits above a fixed y-position on that page,
confirmed directly against its own word positions; pages after the first
carry no repeated header at all (confirmed: page 2's first line is already a
data row), so no top-of-page cutoff is applied there.

Confirmed real-file quirks driving the RULES below (soft-validation, "never
guess a wrong split"; ambiguous data is left as literal text and flagged by
the rules below rather than guessed at):

- DESCRIPTION and PART_NUMBER are blank on every row after the first row of
  a part group -- the report only prints the description/part-number once
  per distinct part number, then lists each of that part's fitted serials
  (often across different POSITION codes) on subsequent rows with those two
  columns blank. A part-group header line can also recur verbatim as its
  own row with no serial/date/hours/cycles at all when the group's serial
  list spans a page break (confirmed directly: the same "<description> ...
  <part_no>" text appears as the last row of one page and again, alone, as
  the first row of the next). Both are left exactly as printed -- no
  forward-fill is applied here (unlike this project's generic ATA
  forward-fill helper, which the router still applies afterward) since nothing
  in the row itself anchors which earlier PN/description group it belongs
  to strongly enough to fill with confidence.
- POSITION is a genuine grab-bag of formats on real rows: dotted position
  codes (e.g. <n>.<n>.<n>.<n>), a bare single digit, a side code (e.g. "LH"/
  "RH"), a bay/zone free-text code (e.g. "LWR CTR"), and a bracketed
  sub-position code -- one real row's bracketed code is truncated mid-token
  by the source report's own column width (confirmed directly: the closing
  bracket is simply absent from the page, not an extraction artefact), so
  the pattern is deliberately permissive rather than guessing a wrong close.
- STOCK_NUMBER and INSTALL_DATE/AC_HOURS_AT_INSTALL/AC_CYCLES_AT_INSTALL are
  each blank on a handful of real rows (confirmed directly) -- allowed empty
  rather than flagged, since this is genuinely missing source data, not a
  parse failure.
- AC_HOURS_AT_INSTALL is negative on a couple of real rows (confirmed
  directly, e.g. a part installed before the aircraft's own recorded life
  began) -- a genuine source-data oddity, not an extraction error, so a
  leading "-" is accepted rather than flagged.
- PART_NUMBER can end in a bare trailing hyphen on a real row (confirmed
  directly) -- this is NOT special-cased here; the global PART_NUMBER
  pattern already flags a trailing hyphen as `bad_format`, which is the
  correct outcome for a value that looks like a truncated/malformed PN in
  the source document itself, not a splitting error on this module's part.

No STATUS_TRAIL catch-all column is needed: every column is resolved with
confidence from position, and any resulting ambiguity (blank cells, unusual
formats) is left as literal empty/free text and handled by RULES below
rather than guessed at or merged into a catch-all.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "All Fitted Aircraft Component LOG"
SIGNATURES = [
    "All Fitted Aircraft Component LOG",
]

CANONICAL_COLUMNS = [
    "ATA",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "STOCK_NUMBER",
    "POSITION",
    "INSTALL_DATE",
    "AC_HOURS_AT_INSTALL",
    "AC_CYCLES_AT_INSTALL",
    # Header metadata, parsed once per file and stamped on every row.
    "AIRCRAFT_REG",
    "SINCE_NEW_HOUR",
    "CYCLES",
    "REMOVAL_HOURS_PER_DAY",
    "REMOVAL_CYCLES_PER_DAY",
]

# AC_HOURS_AT_INSTALL prints as a plain decimal, comma-grouped, and is
# occasionally negative on a real row (see module docstring) -- accepted
# rather than flagged. AC_CYCLES_AT_INSTALL prints as a bare integer or a
# literal "-" placeholder when hours read "0.00" (part installed since new).
_HOURS_RULE = {"pattern": r"^-?\d{1,3}(?:,\d{3})*\.\d{2}$", "allow_empty": True}
_CYCLES_RULE = {"pattern": r"^(?:-|\d+)$", "allow_empty": True}
_DATE_RULE = {"pattern": r"^\d{2}-\d{2}-\d{2}$", "allow_empty": True}

_OVERRIDES = {
    "DESCRIPTION": {"uppercase": True, "allow_empty": True},
    # Blank whenever a row continues a part group already named on an
    # earlier row (see module docstring) -- not a parse failure.
    "PART_NUMBER": {"allow_empty": True},
    # POSITION is a genuine mix of dotted codes, bare digits, side/bay free
    # text, and a bracketed sub-position code that one real row truncates
    # mid-token at the source report's own column edge (see module
    # docstring) -- deliberately permissive rather than guessing a wrong
    # close bracket or rejecting a real value shape.
    "POSITION": {
        "pattern": r"^[A-Z0-9](?:[A-Z0-9 ./#\[\]\-]{0,40})?$",
        "uppercase": True,
        "allow_empty": True,
    },
    # Confirmed directly against the real sample file: a stock number is
    # always 7 characters, but a genuine minority mix in letters (e.g. a
    # revision/lot-code prefix) rather than being purely numeric.
    "STOCK_NUMBER": {"pattern": r"^[A-Z0-9]{7}$", "uppercase": True, "allow_empty": True},
    "INSTALL_DATE": _DATE_RULE,
    "AC_HOURS_AT_INSTALL": _HOURS_RULE,
    "AC_CYCLES_AT_INSTALL": _CYCLES_RULE,
    "AIRCRAFT_REG": {"uppercase": True, "allow_empty": True},
    "SINCE_NEW_HOUR": {"pattern": r"^\d+$", "allow_empty": True},
    "CYCLES": {"pattern": r"^\d+$", "allow_empty": True},
    "REMOVAL_HOURS_PER_DAY": {"allow_empty": True},
    "REMOVAL_CYCLES_PER_DAY": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Column boundaries as (x0_inclusive, x1_exclusive, CANONICAL_COLUMNS name),
# derived from the real header's own word x-positions and confirmed
# row-by-row against the real sample file, including the sparse/blank-cell
# rows described in the module docstring.
_COLUMNS = [
    (-1e9, 95.0, "ATA"),
    (95.0, 320.0, "DESCRIPTION"),
    (320.0, 460.0, "PART_NUMBER"),
    (460.0, 580.0, "SERIAL_NUMBER"),
    (580.0, 685.0, "STOCK_NUMBER"),
    (685.0, 745.0, "POSITION"),
    (745.0, 835.0, "INSTALL_DATE"),
    (835.0, 910.0, "AC_HOURS_AT_INSTALL"),
    (910.0, 1e9, "AC_CYCLES_AT_INSTALL"),
]
# Header/body split for page 1 only -- the real header block (title + A/C
# metadata + the two-band column-group header) ends well above this,
# confirmed directly against the real sample file's header word positions.
# Pages after the first carry no repeated header at all (confirmed: their
# first line is already a data row), so no cutoff is applied there.
_PAGE1_BODY_TOP_MIN = 200.0
_ROW_CLUSTER_TOL = 3.5

_REG_RE = re.compile(r"AIRCRAFT\s+(\S+)")
_SNH_RE = re.compile(r"SINCE\s+NEW\s+HOUR:\s*(\S+)")
_CYCLES_RE = re.compile(r"\bCYCLES:\s*(\S+)")
_REMOVAL_RE = re.compile(
    r"UNIT\s+REMOVAL\s+BASED\s+ON\s+(\S+)\s+HOURS\s+AND\s+(\S+)\s+CYCLES\s+PER\s+DAY"
)


def _col_for_x(x: float) -> str | None:
    for lo, hi, name in _COLUMNS:
        if lo <= x < hi:
            return name
    return None


def _parse_header_meta(first_page_text: str) -> dict:
    meta = {
        "AIRCRAFT_REG": "", "SINCE_NEW_HOUR": "", "CYCLES": "",
        "REMOVAL_HOURS_PER_DAY": "", "REMOVAL_CYCLES_PER_DAY": "",
    }
    m = _REG_RE.search(first_page_text)
    if m:
        meta["AIRCRAFT_REG"] = m.group(1)
    m = _SNH_RE.search(first_page_text)
    if m:
        meta["SINCE_NEW_HOUR"] = m.group(1)
    m = _CYCLES_RE.search(first_page_text)
    if m:
        meta["CYCLES"] = m.group(1)
    m = _REMOVAL_RE.search(first_page_text)
    if m:
        meta["REMOVAL_HOURS_PER_DAY"] = m.group(1)
        meta["REMOVAL_CYCLES_PER_DAY"] = m.group(2)
    return meta


def _cluster_rows(words: list[dict], top_min: float) -> list[list[dict]]:
    """Group words into visual table rows by `top` position. Words on the
    same printed row can differ by a fraction of a point due to font
    baseline/rendering, so a small tolerance is used rather than an exact
    match."""
    body = [w for w in words if w["top"] > top_min]
    body.sort(key=lambda w: (w["top"], w["x0"]))
    rows: list[list[dict]] = []
    cur: list[dict] = []
    cur_top: float | None = None
    for w in body:
        if cur_top is None or abs(w["top"] - cur_top) <= _ROW_CLUSTER_TOL:
            cur.append(w)
            if cur_top is None:
                cur_top = w["top"]
        else:
            rows.append(cur)
            cur = [w]
            cur_top = w["top"]
    if cur:
        rows.append(cur)
    return rows


def _row_to_record(row_words: list[dict]) -> dict | None:
    cols: dict[str, list[str]] = {}
    for w in row_words:
        cx = (w["x0"] + w["x1"]) / 2
        name = _col_for_x(cx)
        if name is None:
            continue
        cols.setdefault(name, []).append(w["text"])
    # A row with no recognisable data in any column is skipped -- every
    # genuine data row (confirmed against the real sample file) carries at
    # least a PART_NUMBER, SERIAL_NUMBER, or ATA anchor.
    if not any(cols.get(name) for _, _, name in _COLUMNS):
        return None
    rec = {name: " ".join(cols.get(name, [])) for _, _, name in _COLUMNS}
    return rec


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        if not pdf.pages:
            return records
        meta = _parse_header_meta(pdf.pages[0].extract_text() or "")
        for page_num, page in enumerate(pdf.pages, start=1):
            words = page.extract_words()
            if not words:
                continue
            top_min = _PAGE1_BODY_TOP_MIN if page_num == 1 else -1.0
            for row_words in _cluster_rows(words, top_min):
                rec = _row_to_record(row_words)
                if rec is None:
                    continue
                rec.update(meta)
                rec["_page"] = page_num
                records.append(rec)
    return records
