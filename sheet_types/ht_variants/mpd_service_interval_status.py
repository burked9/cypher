"""HT - COMPONENT STATUS -- born-digital, real ruled (bordered) table,
extracted via pdfplumber's `extract_tables()` rather than coordinate-word
bucketing (confirmed directly on the sample file: `page.rects` is populated
-- over a hundred vector rects per page -- and `page.find_tables()`/
`extract_tables()` return a clean, stable 19-column grid on every page, so
pdfplumber's own cell-boundary detection is used directly instead of
re-deriving column edges from word x-positions).

Header block (repeats verbatim at the top of every page)::

    HT - COMPONENT STATUS
    AIRCRAFT MODEL <type>
    AIRCRAFT REG:<tail no.>       CURRENT DATE :<date>
    MSN:<MSN>                     TOTAL AIRCRAFT HOURS :<n>
    MFD:<date>                    TOTAL AIRCRAFT CYCLES :<n>
    MPD          PART   SERIAL  INSTALLED  SERVICE  INTERVAL  NEXT DUE  REMAINING  REMARKS
      DESCRIPTION  POSITION
    TASK NO.  NUMBER  NUMBER  DATE  TAH  TAC  DATE  DY FH FC  DY FH FC  DAYS HOURS CYCLES

The 19 ruled columns, confirmed directly against `extract_tables()` output
(NOT the printed sub-header labels alone -- the "NEXT DUE" group's own
sub-header row repeats "DY FH FC" but the DY slot's actual cell values are
always calendar dates or blank, never a bare day count; the true shape,
cross-checked arithmetically against several rows, e.g. INSTALLED TAH +
INTERVAL FH == NEXT DUE FH, and NEXT DUE FC - TOTAL AIRCRAFT CYCLES ==
REMAINING CYCLES, is DATE/FH/FC, not DY/FH/FC)::

    MPD_TASK_NO | DESCRIPTION | POSITION | PART_NUMBER | SERIAL_NUMBER |
    INSTALLED_DATE | INSTALLED_TAH | INSTALLED_TAC | SERVICE_DATE |
    INTERVAL_DY | INTERVAL_FH | INTERVAL_FC | NEXT_DUE_DATE | NEXT_DUE_FH |
    NEXT_DUE_FC | REMAINING_DAYS | REMAINING_HOURS | REMAINING_CYCLES |
    REMARKS

An ATA-chapter divider row (e.g. "ATA 21 AIR CONDITIONING") precedes each
chapter's block, in its own row with every other cell blank; it carries no
component data itself and is used only to forward-fill an ATA column onto
the rows that follow, across page breaks (an aircraft's systems run
contiguously in chapter order without necessarily reprinting the divider on
every later page, so ATA state is NOT reset per page).

Row grain: a tracked component instance is usually one physical row, but
DESCRIPTION and/or POSITION/PART_NUMBER/SERIAL_NUMBER/INSTALLED_DATE/
INSTALLED_TAH/INSTALLED_TAC come back as `None` (pdfplumber's own merged
cell, not an empty string) on a second row directly below when that row is
either (a) a second scheduled task under the very same physical unit (same
PN/SN, a new MPD_TASK_NO of its own), or (b) a second tracking basis for
the same task (no new MPD_TASK_NO at all -- e.g. a life-limit "DISCARD"
line under an "HST" hydrostatic-test line for the same reservoir). Both
shapes are reconstructed with a single forward-fill pass, independently per
field (DESCRIPTION can carry over on its own from a different row than
POSITION does, matching the ruled cell's own vertical merge), RESET AT THE
START OF EACH PAGE -- confirmed directly that no genuine continuation in
this file's own table crosses a page boundary (every page's first data row
carries its own full identity); the reset exists specifically to contain a
different, page-boundary-only defect described next.

Known PDF-rendering quirk, confirmed directly on the sample file: the very
last data row `extract_tables()` returns for a page occasionally comes back
with DESCRIPTION/POSITION/PART_NUMBER blanked out (merged-cell `None`)
even though the row is NOT a genuine continuation of the row above it (its
own MPD_TASK_NO and SERIAL_NUMBER are both new, unrelated to the preceding
component) -- the row's leading cells were simply cut by the page/table
boundary during rendering. Forward-filling this row the same way as a
genuine continuation would silently attribute one component's PN/SN/
description to a completely different one, which is worse than leaving the
gap visible. So forward-fill is skipped (fields kept blank) specifically
when a row is the last data row taken from its page's table AND at least
three of its own DESCRIPTION/POSITION/PART_NUMBER/INSTALLED_DATE cells are
`None`; such a row still comes through with its own SERIAL_NUMBER and
interval/next-due/remaining data intact, just short its component identity,
and downstream validation will naturally flag the resulting blanks rather
than this parser guessing at them.

A handful of components carry no discrete tracking data at all -- one row's
PART_NUMBER/SERIAL_NUMBER cells instead hold a single free-text instruction
split arbitrarily across those two ruled cells (e.g. an "OXYGEN GENERATOR
DISCARD" row pointing to a separate inventory list). Rather than guess
these two cells back into one sentence or re-split them some other way,
they are kept exactly where the ruled table puts each half -- these rows
will naturally surface a PART_NUMBER/SERIAL_NUMBER pattern flag downstream,
which is preferable to silently mis-splitting an airworthiness record.

Every page's own two-line header row ("MPD TASK NO." / "DESCRIPTION" ...)
is skipped by an exact first-cell match; a signature block (an approving
official's name and title) prints on the final page, but confirmed directly
it is never captured by `extract_tables()` -- the words sit inside the
table's own bounding-box y-range but outside every ruled cell's column
x-range, so `extract_tables()` returns a trailing all-blank row there
instead of the name text -- so no name from that block ever reaches any
output field.

Header metadata (aircraft model, registration, MSN, manufacture date,
report date, total aircraft hours, total aircraft cycles) is parsed once
from page 1's own header text and stamped on every row.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.ht_variants._base import merged_rules
from shared.cleanup import normalize_dashes

NAME = "MPD Service Interval Status"
SIGNATURES = [
    # Checked against every SIGNATURES list in occm.py/ht.py/llp.py and
    # every occm_variants/ht_variants/llp_variants module's own SIGNATURES
    # list (plus a plain grep for "HT" + "COMPONENT STATUS" combinations
    # and for "COMPONENT STATUS" generally); no collision found. Several
    # other variants' own titles contain the words "COMPONENT STATUS" as a
    # substring (e.g. occm_variants/occm_component_status_report.py's "OCCM
    # COMPONENT STATUS", occm_variants/oc_component_status.py's "O/C
    # COMPONENT STATUS", aercap_hard_time_component_status.py's and
    # hard_time_limit_control_status.py's own "HARD TIME COMPONENT STATUS")
    # but none of them is preceded by the bare, hyphen-flanked "HT" this
    # file's own title line uses, so this full contiguous phrase is not a
    # substring of any of theirs and none of theirs is a substring of it.
    # The literal character between "HT" and "COMPONENT" in the source PDF
    # is U+2010 HYPHEN (confirmed directly against the file's own
    # extracted text), not the ASCII hyphen-minus -- reproduced verbatim
    # here since SIGNATURES matching is a plain substring check against
    # un-normalized page text.
    "HT ‐ COMPONENT STATUS",
    # Backup anchor: the ruled table's own top header-row text, verbatim,
    # for the (unseen in this corpus so far) case of a sibling file using a
    # differently-punctuated title line. Checked against every SIGNATURES
    # list in occm.py/ht.py/llp.py and every occm_variants/ht_variants/
    # llp_variants module (including a plain grep for "MPD PART SERIAL");
    # no collision found.
    "MPD PART SERIAL INSTALLED SERVICE INTERVAL NEXT DUE REMAINING REMARKS",
]

CANONICAL_COLUMNS = [
    "ATA",
    "MPD_TASK_NO",
    "DESCRIPTION",
    "POSITION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "INSTALLED_DATE",
    "INSTALLED_TAH",
    "INSTALLED_TAC",
    "SERVICE_DATE",
    "INTERVAL_DY",
    "INTERVAL_FH",
    "INTERVAL_FC",
    "NEXT_DUE_DATE",
    "NEXT_DUE_FH",
    "NEXT_DUE_FC",
    "REMAINING_DAYS",
    "REMAINING_HOURS",
    "REMAINING_CYCLES",
    "REMARKS",
    # Header metadata -- same on every row of a given file.
    "AIRCRAFT_MODEL",
    "AC_REG",
    "AC_MSN",
    "MFD",
    "REPORT_DATE",
    "TOTAL_AIRCRAFT_HOURS",
    "TOTAL_AIRCRAFT_CYCLES",
]

_DATE_RE = r"^\d{1,2}-[A-Za-z]{3,9}-\d{2,4}$|^[A-Za-z]{3,9}-\d{2,4}$"
_NUM_RE = r"^[\d,]+$"
_INTERVAL_DY_RE = r"^\d+\s*MO$"

_OVERRIDES = {
    "MPD_TASK_NO":     {"pattern": r"^(?:\d{5,6}-\d{2}-\d{1,2}|N/A)$",
                         "allow_empty": True},
    "POSITION":        {"allow_empty": True},
    "INSTALLED_DATE":  {"pattern": _DATE_RE, "allow_empty": True},
    "INSTALLED_TAH":   {"pattern": _NUM_RE, "allow_empty": True},
    "INSTALLED_TAC":   {"pattern": _NUM_RE, "allow_empty": True},
    "SERVICE_DATE":    {"pattern": _DATE_RE, "allow_empty": True},
    "INTERVAL_DY":     {"pattern": _INTERVAL_DY_RE, "allow_empty": True},
    "INTERVAL_FH":     {"pattern": _NUM_RE, "allow_empty": True},
    "INTERVAL_FC":     {"pattern": _NUM_RE, "allow_empty": True},
    "NEXT_DUE_DATE":   {"pattern": _DATE_RE, "allow_empty": True},
    "NEXT_DUE_FH":     {"pattern": _NUM_RE, "allow_empty": True},
    "NEXT_DUE_FC":     {"pattern": _NUM_RE, "allow_empty": True},
    "REMAINING_DAYS":  {"pattern": _NUM_RE, "allow_empty": True},
    "REMAINING_HOURS": {"pattern": _NUM_RE, "allow_empty": True},
    "REMAINING_CYCLES": {"pattern": _NUM_RE, "allow_empty": True},
    "REMARKS":         {"allow_empty": True},
    "AIRCRAFT_MODEL":  {"allow_empty": True},
    "AC_REG":          {"pattern": r"^[A-Z0-9\-]+$", "uppercase": True,
                         "allow_empty": True},
    "AC_MSN":          {"pattern": r"^\d+$", "allow_empty": True},
    "MFD":             {"pattern": _DATE_RE, "allow_empty": True},
    "REPORT_DATE":     {"pattern": _DATE_RE, "allow_empty": True},
    "TOTAL_AIRCRAFT_HOURS":  {"pattern": _NUM_RE, "allow_empty": True},
    "TOTAL_AIRCRAFT_CYCLES": {"pattern": _NUM_RE, "allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_HEADER_ROW_FIRST_CELL = "MPD\nTASK NO."
_BLANK_TOKENS = {"-", ""}
_ATA_DIVIDER_RE = re.compile(r"^ATA\s+(\d{2})\b")

_MODEL_RE = re.compile(r"AIRCRAFT MODEL\s+(\S+)")
_REG_RE = re.compile(r"AIRCRAFT REG:(\S+)")
_MSN_RE = re.compile(r"MSN:(\S+)")
_MFD_RE = re.compile(r"MFD:(\S+)")
_REPORT_DATE_RE = re.compile(r"CURRENT DATE\s*:(\S+)")
_TOTAL_HOURS_RE = re.compile(r"TOTAL AIRCRAFT HOURS\s*:([\d,]+)")
_TOTAL_CYCLES_RE = re.compile(r"TOTAL AIRCRAFT CYCLES\s*:([\d,]+)")


def _clean_cell(value: str | None) -> str:
    if value is None:
        return None
    # A wrapped/annotated cell's internal line break is joined with a
    # single space rather than left embedded or mid-word split.
    text = " ".join(str(value).split())
    text = normalize_dashes(text)
    if text in _BLANK_TOKENS:
        return ""
    return text


def _parse_header_meta(page) -> dict:
    meta = {
        "AIRCRAFT_MODEL": "", "AC_REG": "", "AC_MSN": "", "MFD": "",
        "REPORT_DATE": "", "TOTAL_AIRCRAFT_HOURS": "",
        "TOTAL_AIRCRAFT_CYCLES": "",
    }
    text = normalize_dashes(page.extract_text() or "")
    for rx, key in (
        (_MODEL_RE, "AIRCRAFT_MODEL"), (_REG_RE, "AC_REG"),
        (_MSN_RE, "AC_MSN"), (_MFD_RE, "MFD"),
        (_REPORT_DATE_RE, "REPORT_DATE"),
        (_TOTAL_HOURS_RE, "TOTAL_AIRCRAFT_HOURS"),
        (_TOTAL_CYCLES_RE, "TOTAL_AIRCRAFT_CYCLES"),
    ):
        m = rx.search(text)
        if m:
            meta[key] = m.group(1)
    return meta


_FIELD_NAMES = [
    "MPD_TASK_NO", "DESCRIPTION", "POSITION", "PART_NUMBER", "SERIAL_NUMBER",
    "INSTALLED_DATE", "INSTALLED_TAH", "INSTALLED_TAC", "SERVICE_DATE",
    "INTERVAL_DY", "INTERVAL_FH", "INTERVAL_FC", "NEXT_DUE_DATE",
    "NEXT_DUE_FH", "NEXT_DUE_FC", "REMAINING_DAYS", "REMAINING_HOURS",
    "REMAINING_CYCLES", "REMARKS",
]
# Fields eligible for forward-fill from the previous row on the same page
# (component-identity fields only -- interval/next-due/remaining figures
# are always specific to the row's own task/tracking-basis and are never
# carried over).
_FILLABLE = ("DESCRIPTION", "POSITION", "PART_NUMBER", "SERIAL_NUMBER",
             "INSTALLED_DATE", "INSTALLED_TAH", "INSTALLED_TAC")


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    meta = {}
    cur_ata = ""

    with pdfplumber.open(pdf_path) as pdf:
        if pdf.pages:
            meta = _parse_header_meta(pdf.pages[0])

        for page_num, page in enumerate(pdf.pages, start=1):
            for table in page.extract_tables():
                # Collect this page's real data rows first (drop header /
                # ATA-divider / fully-blank rows) so "last row on the page"
                # can be identified before the forward-fill pass runs.
                data_rows = []
                for raw in table:
                    if raw is None or len(raw) < 19:
                        continue
                    cells = [_clean_cell(c) for c in raw]
                    first = cells[0] or ""
                    if (raw[0] or "").strip() == _HEADER_ROW_FIRST_CELL:
                        continue
                    if cells[5] == "DATE" and cells[6] == "TAH":
                        # Second header sub-row (DATE/TAH/TAC/.../CYCLES),
                        # first cell blank.
                        continue
                    if not any(c for c in cells if c):
                        continue
                    m = _ATA_DIVIDER_RE.match(first.strip())
                    if m and not any(c for c in cells[1:] if c):
                        cur_ata = m.group(1)
                        continue
                    data_rows.append((cur_ata, cells))

                n = len(data_rows)
                cur = {f: "" for f in _FILLABLE}
                for i, (ata, cells) in enumerate(data_rows):
                    is_last = (i == n - 1)
                    missing_identity = sum(
                        1 for v in (cells[1], cells[2], cells[3], cells[5])
                        if v is None
                    )
                    skip_fill = is_last and missing_identity >= 3

                    row = {}
                    for name, val in zip(_FIELD_NAMES, cells[:19]):
                        if val is None:
                            if name in _FILLABLE and not skip_fill:
                                val = cur.get(name, "")
                            else:
                                val = ""
                        row[name] = val

                    for name in _FILLABLE:
                        if row[name]:
                            cur[name] = row[name]

                    row["ATA"] = ata
                    row["_page"] = page_num
                    row.update(meta)
                    records.append(row)

    return records
