""""HARD TIME COMPONENT STATUS" -- born-digital, real ruled (bordered) table,
extracted via pdfplumber's `extract_tables()` rather than coordinate-word
bucketing (confirmed directly on the sample file: `page.rects` is populated
-- 172 vector rects on page 1 -- and `page.find_tables()`/`extract_tables()`
return a clean, stable 13-column grid on every page, so pdfplumber's own
cell-boundary detection is used directly instead of re-deriving column
edges from word x-positions).

This is a distinct template from this project's other "Hard Time
Component(s) ..."-titled variants. Checked directly against the two
nearest look-alikes:

  * `aercap_hard_time_component_status.py` -- shares the words "HARD TIME
    COMPONENT STATUS" in its own title line, but is a completely different
    parser keyed off its own "COMP.TIMELINE" / "A/C TIMELINE (@INSTL)"
    header phrases (neither of which appears anywhere in this file's own
    header block) and an ATA+task-code text anchor rather than a ruled
    table.
  * `hard_time_status_mpd_cert_fin.py` -- also a ruled-table HT parser, but
    its own column set (MPD Item #/P/N #/S/N #/DESCRIPTION/CERTIFICATES/
    FIN/TASK plus an Interval/LAST INSP-OVH/DUE ON/REMAINING triplet) has
    no overlap with this file's own MPD Reference/Description/Part
    Number/Serial Number/Pos./Action Date/TSO/CSO/LIMIT/CONTROL/NEXT DUE/
    REMAINING/NOTES header row.

Also checked against every other SIGNATURES list in occm.py/ht.py/llp.py
and every occm_variants/ht_variants/llp_variants module for the exact
contiguous phrase this file's own signature below uses; no collision
found (nearest look-alike, georgian_airways_ht_components_status.py's own
"... SPEC LIMIT NEXT DUE REMAINING", is a different, shorter phrase with
no "CONTROL" and no "NOTES").

Header block (repeats verbatim at the top of every page)::

    MSN <MSN> Registration <tail>            <report date>
    Total Hours <n>                          HARD TIME COMPONENT STATUS
    Total Cycles <n>
    MPD Reference Description Part Number Serial Number Pos. Action Date
        TSO CSO LIMIT CONTROL NEXT DUE REMAINING NOTES

followed by the main ruled data table, 13 columns::

    MPD Reference | Description | Part Number | Serial Number | Pos. |
    Action Date | TSO | CSO | LIMIT | CONTROL | NEXT DUE | REMAINING |
    NOTES

Row grain, confirmed directly against the ruled cell boundaries on the
sample file (cell y-ranges, not just word positions): each tracked
component/instance is rendered as ONE OR TWO physical table rows sharing
the same ruled LIMIT/CONTROL/NEXT DUE/REMAINING column x-range but split
top/bottom within it --

  * a "primary" row carrying MPD_REFERENCE/DESCRIPTION/PART_NUMBER/
    SERIAL_NUMBER/POS/ACTION_DATE/TSO/CSO plus its own first tracking
    basis (e.g. `LIMIT "50000"`, `CONTROL "HOURS"`), and
  * an optional second physical row directly below it, sharing the same
    component identity but carrying only a second tracking basis (e.g.
    `LIMIT "6387"`, `CONTROL "DAYS"`) -- MPD_REFERENCE through CSO come
    back as `None` on this row because pdfplumber's own cell grid merges
    those columns vertically across both physical rows.

CONTROL is not a status flag here but the tracked basis unit for that
LIMIT row -- confirmed directly against the sample file's own values,
which are only ever "HOURS", "CYCLES" or "DAYS" -- so NEXT_DUE reads as a
plain number for a HOURS/CYCLES-basis row and a calendar date for a
DAYS-basis row on the very same component.

A small number of components are also nested one level deeper: several
distinct physical units (e.g. left/right, forward/aft positions) share
one printed MPD_REFERENCE/DESCRIPTION cell (merged vertically across all
of their own rows) but each still carries its own PART_NUMBER/
SERIAL_NUMBER/POS/ACTION_DATE/TSO/CSO/LIMIT/CONTROL/NEXT_DUE/REMAINING --
these rows come back with MPD_REFERENCE and/or DESCRIPTION as `None`
(merged cell) but PART_NUMBER (or another of the instance-identity
columns) populated, distinguishing them from a bare second-basis row.

This parser reconstructs full row identity with a single forward-fill
pass, keyed off which of the two column groups is present on each row
(never by counting or interpolating -- if a row's own LIMIT/CONTROL/NEXT
DUE/REMAINING cells come back blank, e.g. several PART_NUMBER-bearing
rows on pages 2-3 of the sample file whose limit/basis literally isn't
repeated on that physical unit's own row, they stay blank rather than
being guessed from the neighbouring instance's own values):

  * MPD_REFERENCE and DESCRIPTION are forward-filled independently from
    the last row that populated each (they can update on different rows
    from each other, per the merged-cell behaviour above).
  * A row is treated as declaring a NEW physical instance whenever ANY of
    its own PART_NUMBER..CSO cells are populated; when that happens its
    own (possibly blank) PART_NUMBER/SERIAL_NUMBER/POS/ACTION_DATE/TSO/
    CSO values become the new forward-fill state for any later bare
    second-basis row.
  * A row with none of PART_NUMBER..CSO populated but at least one of
    LIMIT/CONTROL/NEXT_DUE/REMAINING populated is treated as a second
    tracking-basis row for the current forward-filled instance.
  * A row with neither group populated carries no data of its own (e.g. a
    row whose only real content already attached to the row above via a
    vertically-merged cell) and is skipped.

A handful of components carry no discrete tracking data at all -- their
row's PART_NUMBER cell instead holds a full free-text instruction (e.g.
"Overhaul Life Vests - SEE LIFE VEST SURVEY") with every other cell on
that row blank. Rather than guess this sentence apart into PART_NUMBER/
NOTES-shaped fields, it is kept exactly where the ruled table puts it (in
PART_NUMBER) -- these rows will naturally surface a PART_NUMBER pattern
flag downstream, which is preferable to silently mis-splitting an
airworthiness record.

Every page's own header row ("MPD Reference Description Part Number
...") is skipped by an exact first-two-cell match; a header/footer
signature block (an authorised-representative name and the lessor's
sub-servicer company) prints BELOW the ruled table's own bbox on the
final page -- confirmed directly it is never captured by
`extract_tables()` (the words sit well below every table's own bbox on
that page) -- so no name or company from that block ever reaches any
output field.

Header metadata (aircraft MSN, registration, report date, total hours,
total cycles) is parsed once from page 1's own header text and stamped
on every row.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.ht_variants._base import merged_rules
from shared.cleanup import normalize_dashes

NAME = "Hard Time Limit/Control Status"
SIGNATURES = [
    # Checked against every SIGNATURES list in occm.py/ht.py/llp.py and
    # every occm_variants/ht_variants/llp_variants module (including a
    # plain grep for "LIMIT CONTROL"/"NEXT DUE REMAINING"/"CONTROL NEXT
    # DUE"); no collision found. The nearest look-alike,
    # georgian_airways_ht_components_status.py's own "... SPEC LIMIT NEXT
    # DUE REMAINING", is a different, shorter phrase (no "CONTROL", no
    # "NOTES") and not a substring of this one in either direction.
    "LIMIT CONTROL NEXT DUE REMAINING NOTES",
]

CANONICAL_COLUMNS = [
    "MPD_REFERENCE",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "POS",
    "ACTION_DATE",
    "TSO",
    "CSO",
    "LIMIT",
    "CONTROL",
    "NEXT_DUE",
    "REMAINING",
    "NOTES",
    # Header metadata -- same on every row of a given file.
    "AC_MSN",
    "AC_REG",
    "REPORT_DATE",
    "TOTAL_HOURS",
    "TOTAL_CYCLES",
]

_DATE_RE = r"^\d{1,2}-[A-Za-z]{1,3}-\d{2,4}$"
_NUM_RE = r"^[\d,]+$"
_NUM_OR_NA_RE = r"^(?:[\d,]+|N/A)$"

_OVERRIDES = {
    "PART_NUMBER":   {"allow_empty": True},
    "SERIAL_NUMBER": {"allow_empty": True},
    "POS":           {"allow_empty": True},
    "ACTION_DATE":   {"pattern": _DATE_RE, "allow_empty": True},
    "TSO":           {"pattern": _NUM_OR_NA_RE, "allow_empty": True},
    "CSO":           {"pattern": _NUM_OR_NA_RE, "allow_empty": True},
    "LIMIT":         {"pattern": r"^(?:[\d,]+|VR)$", "allow_empty": True},
    "CONTROL":       {"pattern": r"^(?:HOURS|CYCLES|DAYS)$", "allow_empty": True},
    "NEXT_DUE":      {"pattern": _DATE_RE + r"|^[\d,]+$", "allow_empty": True},
    "REMAINING":     {"pattern": _NUM_RE, "allow_empty": True},
    "NOTES":         {"allow_empty": True},
    "AC_MSN":        {"pattern": r"^\d+$", "allow_empty": True},
    "AC_REG":        {"pattern": r"^[A-Z0-9\-]+$", "uppercase": True,
                       "allow_empty": True},
    "REPORT_DATE":   {"pattern": _DATE_RE, "allow_empty": True},
    "TOTAL_HOURS":   {"pattern": r"^[\d,]+(?:\.\d+)?$", "allow_empty": True},
    "TOTAL_CYCLES":  {"pattern": _NUM_RE, "allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_HEADER_ROW_FIRST_TWO = ("MPD Reference", "Description")

_META_RE = re.compile(
    r"MSN\s+(\S+)\s+Registration\s+(\S+)\s+(\d{1,2}-[A-Za-z]{3}-\d{2,4})"
)
_TOTAL_HOURS_RE = re.compile(r"Total Hours\s+([\d,]+(?:\.\d+)?)")
_TOTAL_CYCLES_RE = re.compile(r"Total Cycles\s+([\d,]+)")


def _clean_cell(value: str | None) -> str:
    if not value:
        return ""
    # A wrapped/annotated cell's internal line break is joined with a
    # single space rather than left embedded or mid-word split.
    text = " ".join(value.split())
    return normalize_dashes(text)


def _parse_header_meta(page) -> dict:
    meta = {
        "AC_MSN": "", "AC_REG": "", "REPORT_DATE": "",
        "TOTAL_HOURS": "", "TOTAL_CYCLES": "",
    }
    text = normalize_dashes(page.extract_text() or "")
    m = _META_RE.search(text)
    if m:
        meta["AC_MSN"], meta["AC_REG"], meta["REPORT_DATE"] = m.groups()
    m = _TOTAL_HOURS_RE.search(text)
    if m:
        meta["TOTAL_HOURS"] = m.group(1)
    m = _TOTAL_CYCLES_RE.search(text)
    if m:
        meta["TOTAL_CYCLES"] = m.group(1)
    return meta


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    meta = {}

    cur_mpd = cur_desc = ""
    cur_part = cur_serial = cur_pos = cur_action = cur_tso = cur_cso = ""
    have_instance = False

    with pdfplumber.open(pdf_path) as pdf:
        if pdf.pages:
            meta = _parse_header_meta(pdf.pages[0])

        for page_num, page in enumerate(pdf.pages, start=1):
            for table in page.extract_tables():
                for raw in table:
                    if raw is None or len(raw) < 13:
                        continue
                    cells = [_clean_cell(c) for c in raw]
                    if (cells[0], cells[1]) == _HEADER_ROW_FIRST_TWO:
                        continue
                    if not any(cells):
                        continue

                    if cells[0]:
                        cur_mpd = cells[0]
                    if cells[1]:
                        cur_desc = cells[1]

                    instance_cells = cells[2:8]
                    basis_cells = cells[8:12]
                    notes = cells[12]

                    if any(instance_cells):
                        cur_part, cur_serial, cur_pos, cur_action, cur_tso, cur_cso = instance_cells
                        have_instance = True
                        row = {
                            "MPD_REFERENCE": cur_mpd,
                            "DESCRIPTION": cur_desc,
                            "PART_NUMBER": cur_part,
                            "SERIAL_NUMBER": cur_serial,
                            "POS": cur_pos,
                            "ACTION_DATE": cur_action,
                            "TSO": cur_tso,
                            "CSO": cur_cso,
                            "LIMIT": cells[8],
                            "CONTROL": cells[9],
                            "NEXT_DUE": cells[10],
                            "REMAINING": cells[11],
                            "NOTES": notes,
                        }
                    elif any(basis_cells):
                        if not have_instance:
                            # No anchoring physical instance seen yet this
                            # file -- not a recognisable data row, skip
                            # rather than emit an orphaned basis line.
                            continue
                        row = {
                            "MPD_REFERENCE": cur_mpd,
                            "DESCRIPTION": cur_desc,
                            "PART_NUMBER": cur_part,
                            "SERIAL_NUMBER": cur_serial,
                            "POS": cur_pos,
                            "ACTION_DATE": cur_action,
                            "TSO": cur_tso,
                            "CSO": cur_cso,
                            "LIMIT": cells[8],
                            "CONTROL": cells[9],
                            "NEXT_DUE": cells[10],
                            "REMAINING": cells[11],
                            "NOTES": notes,
                        }
                    else:
                        # Only MPD_REFERENCE/DESCRIPTION (or nothing) on
                        # this physical line -- already folded into the
                        # forward-fill state above, no row of its own.
                        continue

                    row["_page"] = page_num
                    row.update(meta)
                    records.append(row)

    return records
