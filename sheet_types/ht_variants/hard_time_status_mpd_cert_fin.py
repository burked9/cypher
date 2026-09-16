"""Born-digital "HARD TIME COMPONENTS STATUS" report, real ruled (bordered)
table extracted via pdfplumber's `find_tables()`/`extract_table()` rather
than coordinate-word-bucketing (confirmed directly: `page.find_tables()`
returns exactly two clean tables per page -- a small "Current utilization"
key/value box and one large ruled data table with a stable 19-column shape
on every page -- so pdfplumber's own cell-boundary detection is used
directly instead of re-deriving column edges from word x-positions).

This is a distinct template from this project's other "Hard Time
Component(s) ..."-titled variants. Its title line reads plainly "HARD TIME
COMPONENTS STATUS" (plural COMPONENTS, singular STATUS, no trailing
qualifier) -- checked directly against
`georgian_airways_ht_components_status.py`/`..._scanned.py`, whose own
signature requires the longer phrase "HARD TIME COMPONENTS STATUS FOR
A/C-REGISTRATION" immediately following (never present in this file's own
title line, and this file's own column layout -- MPD Item #/P/N #/S/N
#/DESCRIPTION/CERTIFICATES/FIN/TASK plus a three-column-group
Interval/LAST INSP-OVH/DUE ON/REMAINING tail -- has no overlap with either
Georgian variant's own header block or `hard_time_components_bordered_table.py`'s
ATA/MPD REF./POS/PART NUMBER/... layout). Also distinct from
`aercap_hard_time_component_status.py` (COMP.TIMELINE / A/C TIMELINE
(@INSTL) headers, singular "COMPONENT") and `emes_hard_time_component_status.py`
(T/C # / HT Class / POS columns, singular "COMPONENT", "e.MES" footer),
both of which were compared directly against a sample file of this
template and do not match its column layout.

Header block (repeats verbatim at the top of every page)::

    HARD TIME COMPONENTS STATUS                 DATE   FH   FC
    Current utilization
    <A/C TYPE> MSN <MSN>
    <DD. Mon. YYYY>                              <FH>  <FC>
    Interval          LAST INSP/OVH   DUE ON      REMAINING
    MPD Item # P/N # S/N # DESCRIPTION CERTIFICATES FIN TASK
    FH FC Days         FH FC Date      FH FC Date   FH FC Days

followed by the main ruled data table, two header rows tall, grouped under
three FH/FC/Date-or-Days column triplets (Interval, LAST INSP/OVH -> DUE
ON, REMAINING). Rows are additionally grouped under bare ATA-chapter
section banners printed as their own full-width row (e.g.
"21-AIRCONDITIONING", "23- COMMUNICATIONS") -- these carry no other column
data and are tracked as a running ATA_SECTION value rather than emitted as
their own record.

Row grain: one row per tracked hard-time limit on a component. A single
physical component very often prints as *two or more* table rows sharing
the same identity (MPD item, part number, serial number, description,
position) but a different TASK/interval (e.g. one row for an OVH limit
tracked in flight-hours, a second row immediately below for an SDI/DS
limit tracked in calendar days) -- the ruled table renders the shared
identity cells as a single cell spanning both physical rows. pdfplumber's
grid extraction surfaces that spanned cell in one of two ways depending on
the file's own rendering: either duplicated verbatim into both rows (in
which case the MPD Item # cell reads as two stacked line-fragments joined
by an internal newline, carried through as-is rather than force-split --
which fragment belongs to which of the two data rows is not determinable
from the extracted text), or left blank on every row after the first. This
parser detects the second case -- a data row whose MPD Item #, P/N #, S/N
#, DESCRIPTION and FIN cells are individually blank -- and forward-fills
each of those columns independently from the closest preceding row that
did carry a value (a per-column "fill down the merged cell" pass, the same
class of blank-continuation handling other HT variants in this package
apply to their own forward-filled ATA/task-code columns). CERTIFICATES is
deliberately NOT forward-filled: it reads as a work-order/tag-style
reference that is plausibly specific to the individual limit/inspection
event rather than the physical component, so a genuinely blank cell is
left blank rather than guessed from the row above.

One row in the sample file (a DS-tracked reservoir/battery-type limit)
prints CERTIFICATES and FIN populated on an otherwise blank-identity row
while MPD Item #/P/N #/S/N #/DESCRIPTION are blank -- confirming the
per-column (not whole-row) forward-fill above: that row's own
CERTIFICATES/FIN values are kept as extracted, only the still-blank
identity columns are filled from the preceding row.

A few CERTIFICATES cells carry a wrapped second-line fragment that visibly
belongs to the *previous* printed row's own CERTIFICATES value (confirmed
directly: a work-order-shaped number appears as a lone first line inside
the *following* row's CERTIFICATES cell) -- a genuine source-table
cell-boundary rendering ambiguity above this parser's own control, so the
raw cell text is carried through as pdfplumber split it rather than
guessed apart and reassigned to the row it visually seems to belong to.

Column extraction picks the table on each page whose own first extracted
row starts with the literal header cell "MPD Item #" (rather than
assuming a fixed table index), so a page with an extra or missing
decorative table would not silently misalign the column set.

Header metadata (aircraft type, MSN, utilization date, utilization FH/FC)
is parsed once from page 1's own header text and stamped on every row.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.ht_variants._base import merged_rules
from shared.cleanup import normalize_dashes

NAME = "Hard Time Components Status (MPD/Certificates/FIN)"
SIGNATURES = [
    "MPD Item #",
    "LAST INSP/OVH",
]

CANONICAL_COLUMNS = [
    "ATA_SECTION",
    "MPD_ITEM",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
    "CERTIFICATES",
    "FIN",
    "TASK",
    "INTERVAL_FH",
    "INTERVAL_FC",
    "INTERVAL_DAYS",
    "LAST_FH",
    "LAST_FC",
    "LAST_DATE",
    "DUE_FH",
    "DUE_FC",
    "DUE_DATE",
    "REMAINING_FH",
    "REMAINING_FC",
    "REMAINING_DAYS",
    # Header metadata -- same on every row of a given file.
    "AC_TYPE",
    "MSN",
    "UTIL_DATE",
    "UTIL_FH",
    "UTIL_FC",
]

_DATE_RE = r"^\d{1,2}-[A-Za-z]{3}-\d{2,4}$"
_NUM_RE = r"^[\d,]+$"

_OVERRIDES = {
    "ATA_SECTION":     {"allow_empty": True},
    "MPD_ITEM":        {"allow_empty": True},
    "PART_NUMBER":     {"allow_empty": True},
    "SERIAL_NUMBER":   {"allow_empty": True},
    "CERTIFICATES":    {"allow_empty": True},
    "FIN":             {"allow_empty": True},
    "TASK":            {"pattern": r"^[A-Z]{2,6}$", "allow_empty": True},
    "INTERVAL_FH":     {"pattern": _NUM_RE, "allow_empty": True},
    "INTERVAL_FC":     {"pattern": _NUM_RE, "allow_empty": True},
    "INTERVAL_DAYS":   {"pattern": _NUM_RE, "allow_empty": True},
    "LAST_FH":         {"pattern": _NUM_RE, "allow_empty": True},
    "LAST_FC":         {"pattern": _NUM_RE, "allow_empty": True},
    "LAST_DATE":       {"pattern": _DATE_RE, "allow_empty": True},
    "DUE_FH":          {"pattern": _NUM_RE, "allow_empty": True},
    "DUE_FC":          {"pattern": _NUM_RE, "allow_empty": True},
    "DUE_DATE":        {"pattern": _DATE_RE, "allow_empty": True},
    "REMAINING_FH":    {"pattern": _NUM_RE, "allow_empty": True},
    "REMAINING_FC":    {"pattern": _NUM_RE, "allow_empty": True},
    "REMAINING_DAYS":  {"pattern": _NUM_RE, "allow_empty": True},
    "AC_TYPE":         {"allow_empty": True},
    "MSN":             {"allow_empty": True},
    "UTIL_DATE":       {"allow_empty": True},
    "UTIL_FH":         {"pattern": _NUM_RE, "allow_empty": True},
    "UTIL_FC":         {"pattern": _NUM_RE, "allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_HEADER_FIRST_CELL = "MPD Item #"
_HEADER_SECOND_ROW_SHAPE = ("FH", "FC", "Days")

# Bare ATA-chapter section banner rows, e.g. "21-AIRCONDITIONING" or
# "23- COMMUNICATIONS" -- a lone label in the MPD Item # column with every
# other cell blank.
_SECTION_RE = re.compile(r"^\d{1,2}-\s?[A-Z][A-Z/ ]*$")

# Identity columns that get forward-filled (per column, independently)
# when a continuation row leaves them blank -- see module docstring for
# why CERTIFICATES is deliberately excluded.
_FILL_DOWN_COLUMNS = ("MPD_ITEM", "PART_NUMBER", "SERIAL_NUMBER",
                      "DESCRIPTION", "FIN")

_HEADER_RE = re.compile(r"^(\S+)\s+MSN\s+(\S+)$")
_UTIL_RE = re.compile(
    r"^(\d{1,2}\.\s*[A-Za-z]{3}\.\s*\d{4})\s+([\d,]+)\s+([\d,]+)$"
)


def _clean_cell(value: str | None) -> str:
    if not value:
        return ""
    text = " ".join(value.split())
    return normalize_dashes(text)


def _find_data_table(page):
    for table in page.find_tables():
        rows = table.extract()
        if not rows:
            continue
        first_cell = (rows[0][0] or "").strip()
        if first_cell == _HEADER_FIRST_CELL:
            return rows
    return None


def _parse_header_meta(page) -> dict:
    meta = {
        "AC_TYPE": "", "MSN": "",
        "UTIL_DATE": "", "UTIL_FH": "", "UTIL_FC": "",
    }
    text = page.extract_text() or ""
    for line in text.splitlines():
        line = line.strip()
        m = _HEADER_RE.match(line)
        if m:
            meta["AC_TYPE"], meta["MSN"] = m.group(1), m.group(2)
            continue
        m = _UTIL_RE.match(line)
        if m:
            meta["UTIL_DATE"] = m.group(1)
            meta["UTIL_FH"] = m.group(2)
            meta["UTIL_FC"] = m.group(3)
    return meta


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []

    with pdfplumber.open(pdf_path) as pdf:
        meta = {}
        if pdf.pages:
            meta = _parse_header_meta(pdf.pages[0])

        ata_section = ""
        last: dict[str, str] = {c: "" for c in _FILL_DOWN_COLUMNS}

        for page_num, page in enumerate(pdf.pages, start=1):
            rows = _find_data_table(page)
            if not rows:
                continue

            for raw in rows:
                if len(raw) < 19:
                    continue
                cells = [_clean_cell(c) for c in raw[:19]]
                mpd_item = cells[0]

                # Two-row header, repeated on every page.
                if mpd_item == _HEADER_FIRST_CELL:
                    continue
                if not mpd_item and tuple(cells[7:10]) == _HEADER_SECOND_ROW_SHAPE:
                    continue

                # Bare ATA-chapter section banner -- update running state,
                # emit no record.
                rest = cells[1:]
                if mpd_item and not any(rest) and _SECTION_RE.match(mpd_item):
                    ata_section = mpd_item
                    continue

                # A row with nothing at all (stray table artifact) --
                # nothing to anchor a record to.
                if not mpd_item and not any(cells):
                    continue

                row = {
                    "ATA_SECTION": ata_section,
                    "MPD_ITEM": cells[0],
                    "PART_NUMBER": cells[1],
                    "SERIAL_NUMBER": cells[2],
                    "DESCRIPTION": cells[3],
                    "CERTIFICATES": cells[4],
                    "FIN": cells[5],
                    "TASK": cells[6],
                    "INTERVAL_FH": cells[7],
                    "INTERVAL_FC": cells[8],
                    "INTERVAL_DAYS": cells[9],
                    "LAST_FH": cells[10],
                    "LAST_FC": cells[11],
                    "LAST_DATE": cells[12],
                    "DUE_FH": cells[13],
                    "DUE_FC": cells[14],
                    "DUE_DATE": cells[15],
                    "REMAINING_FH": cells[16],
                    "REMAINING_FC": cells[17],
                    "REMAINING_DAYS": cells[18],
                }

                # Per-column forward-fill of merged/rowspan identity
                # cells the source table left blank on this continuation
                # row -- see module docstring.
                for col in _FILL_DOWN_COLUMNS:
                    if row[col]:
                        last[col] = row[col]
                    else:
                        row[col] = last[col]

                row["_page"] = page_num
                row.update(meta)
                records.append(row)

    return records
