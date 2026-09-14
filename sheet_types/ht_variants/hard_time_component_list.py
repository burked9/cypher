""""HARD TIME COMPONENT LIST" -- born-digital, full text layer, coordinate-
bucketed columns (confirmed via a direct pdfplumber `extract_words()` pass
over the real sample file: text is present and well-positioned on every
page, no OCR needed).

This is a genuinely different template from this project's other
"Hard Time Component(s) ..."-titled variants: its own title line is the
exact phrase "HARD TIME COMPONENT LIST" (checked directly against
`ca004_hard_time_monitoring_sheet.py`, whose own title is "Hard Time
Monitoring Sheet" -- a different phrase, different header boilerplate
("Aircraft Type:"/"Reference Date:"/"MSN:"/"CSN:" vs this file's own
"A/C TYPE:"/"DATE:"/"A/C MSN:"/"AIRCRAFT HOURS:"/"A/C REG:"/"AIRCRAFT
CYCLES:"), and a completely different column layout -- not a shared
parser).

Header block (repeats verbatim at the top of every page)::

    HARD TIME COMPONENT LIST
    A/C TYPE: <type>            DATE: <dd-Mon-yy>
    A/C MSN: <msn>               AIRCRAFT HOURS: <n>
    A/C REG: <tail>              AIRCRAFT CYCLES: <n>
    PART DATA | INSTALLATION DATA | COMPONENT DATA | LIFE LIMIT | REMAINING LIFE
    ATA  MPD Reference  PART NUMBER  DESCRIPTION | SERIAL NUMBER  Location/Zone
        Date of Installation  Release Date/Inspection Date |
        @A/C TSN  @A/C CSN  @Part TSN  @Part CSN  @Part TSO  @Part CSO  DSI
        TSN  CSN  TSI  CSI  TSO  CSO  DSO |
        Hours  Cycle  Days  LIMITER |
        Hours  Cycle  Days

Row grain: one row per tracked component. Columns, left to right::

    ATA | MPD_REFERENCE | PART_NUMBER | DESCRIPTION |
    SERIAL_NUMBER | LOCATION_ZONE |
    DATE_OF_INSTALLATION | RELEASE_INSPECTION_DATE |
    AC_TSN | AC_CSN | PART_TSN | PART_CSN | PART_TSO | PART_CSO | DSI |
    TSN | CSN | TSI | CSI | TSO | CSO | DSO |
    LIMIT_HOURS | LIMIT_CYCLES | LIMIT_DAYS | LIMITER |
    REMAINING_HOURS | REMAINING_CYCLES | REMAINING_DAYS

Column assignment is done by nearest-header-x snapping for the numeric
block (confirmed directly via `extract_words()`: every one of the numeric
sub-columns' own header label sits at a fixed x-position repeated
identically on every page, and data values line up on that same x0 to
within a point or two -- e.g. a component tracked on Hours+Days alone
(cell values present only in the LIMIT_HOURS and LIMIT_DAYS x-slots, the
LIMIT_CYCLES slot simply carrying no token that row) cross-checks exactly
against its own REMAINING_DAYS figure and DSO figure elsewhere on the same
row: `LIMIT_DAYS - DSO == REMAINING_DAYS` held on every row checked this
way). Each of LIMIT_HOURS/LIMIT_CYCLES/LIMIT_DAYS and
REMAINING_HOURS/REMAINING_CYCLES/REMAINING_DAYS is populated only when
that basis applies to the row's own component -- the untracked
sub-columns are simply blank (no placeholder glyph at all, unlike some of
this project's other HT templates), so the row's numeric tokens are
assigned to whichever of the known header x-positions each is closest to,
never by a fixed left-to-right count of "however many numbers are on this
line".

Physical-line grouping uses the same top-tolerance bucketing this
project's other coordinate-based HT variants use (e.g.
`ca004_hard_time_monitoring_sheet.py`): a small number of rows have their
own trailing numeric sub-columns rendered by the source PDF on a physical
text line a fraction of a point below the row's main line (not a genuine
multi-line wrap -- confirmed the vertical gap between the two fragments of
one such row is under a point, far tighter than the ~3.6-4pt gap between
two consecutive real rows), so a small top-tolerance when bucketing words
into lines merges them back into one row correctly without needing any
special-case row-continuation logic.

DESCRIPTION can be more than one word (e.g. a two-word component name);
its own column band is wide enough that the widest DESCRIPTION value seen
across the whole sample file never approaches the next column's (SERIAL
NUMBER) start x -- confirmed directly by scanning every word's x-extent
across every page.

A small number of cells carry the literal token "UNK" instead of a
number or date where the source data was itself unknown/not captured
(confirmed directly in the sample file, e.g. an as-yet-unrecorded
TSN/CSN pair, or an as-yet-unrecorded installation/release date) -- this
is data, not a rendering artefact, so both the numeric-field and
date-field patterns accept either their normal value or the literal
"UNK".

Header metadata (aircraft type, report date, MSN, aircraft hours,
registration, aircraft cycles) is parsed once from page 1's own header
block (restricted to the text preceding the "PART DATA" column-group
marker, so a same-labelled field in the page footer -- e.g. this
template's own signature block carries a "DATE:" label too -- can never
be picked up in its place) and stamped on every row.

The last page carries a signature/authorisation footer block
("AUTHORIZED AIRLINE REPRESENTATIVE" / "SIGNATURE:" / "NAME:" /
"POSITION:" / "DATE:") below the table, which can include a real
individual's name. That block is recognised by an exact-phrase match on
its own opening line and everything from that line to the end of the
page is dropped outright (not merged into the nearest data row as
overflow text) -- confirmed this name is never captured into any output
field.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.ht_variants._base import merged_rules
from shared.cleanup import normalize_dashes

NAME = "Hard Time Component List"
SIGNATURES = [
    # Checked against every SIGNATURES list in occm.py/ht.py/llp.py and
    # every occm_variants/ht_variants/llp_variants module; no collision
    # found. This exact title phrase does not appear as a substring of any
    # other variant's own signature phrase in either direction.
    "HARD TIME COMPONENT LIST",
]

CANONICAL_COLUMNS = [
    "ATA",
    "MPD_REFERENCE",
    "PART_NUMBER",
    "DESCRIPTION",
    "SERIAL_NUMBER",
    "LOCATION_ZONE",
    "DATE_OF_INSTALLATION",
    "RELEASE_INSPECTION_DATE",
    "AC_TSN",
    "AC_CSN",
    "PART_TSN",
    "PART_CSN",
    "PART_TSO",
    "PART_CSO",
    "DSI",
    "TSN",
    "CSN",
    "TSI",
    "CSI",
    "TSO",
    "CSO",
    "DSO",
    "LIMIT_HOURS",
    "LIMIT_CYCLES",
    "LIMIT_DAYS",
    "LIMITER",
    "REMAINING_HOURS",
    "REMAINING_CYCLES",
    "REMAINING_DAYS",
    # Header metadata -- same on every row of a given file.
    "AC_TYPE",
    "REPORT_DATE",
    "AC_MSN",
    "AC_HOURS",
    "AC_REG",
    "AC_CYCLES",
]

_DATE_RE = r"^(?:\d{2}-[A-Za-z]{3}-\d{2}|UNK)$"
_NUM_RE = r"^(?:[\d,]+|UNK)$"

_OVERRIDES = {
    "MPD_REFERENCE":           {"allow_empty": True},
    "PART_NUMBER":             {"allow_empty": True},
    "SERIAL_NUMBER":           {"allow_empty": True},
    "LOCATION_ZONE":           {"allow_empty": True},
    "DATE_OF_INSTALLATION":    {"pattern": _DATE_RE, "allow_empty": True},
    "RELEASE_INSPECTION_DATE": {"pattern": _DATE_RE, "allow_empty": True},
    "AC_TSN":                  {"pattern": _NUM_RE, "allow_empty": True},
    "AC_CSN":                  {"pattern": _NUM_RE, "allow_empty": True},
    "PART_TSN":                {"pattern": _NUM_RE, "allow_empty": True},
    "PART_CSN":                {"pattern": _NUM_RE, "allow_empty": True},
    "PART_TSO":                {"pattern": _NUM_RE, "allow_empty": True},
    "PART_CSO":                {"pattern": _NUM_RE, "allow_empty": True},
    "DSI":                     {"pattern": _NUM_RE, "allow_empty": True},
    "TSN":                     {"pattern": _NUM_RE, "allow_empty": True},
    "CSN":                     {"pattern": _NUM_RE, "allow_empty": True},
    "TSI":                     {"pattern": _NUM_RE, "allow_empty": True},
    "CSI":                     {"pattern": _NUM_RE, "allow_empty": True},
    "TSO":                     {"pattern": _NUM_RE, "allow_empty": True},
    "CSO":                     {"pattern": _NUM_RE, "allow_empty": True},
    "DSO":                     {"pattern": _NUM_RE, "allow_empty": True},
    "LIMIT_HOURS":             {"pattern": _NUM_RE, "allow_empty": True},
    "LIMIT_CYCLES":            {"pattern": _NUM_RE, "allow_empty": True},
    "LIMIT_DAYS":              {"pattern": _NUM_RE, "allow_empty": True},
    "LIMITER":                 {"allow_empty": True},
    "REMAINING_HOURS":         {"pattern": _NUM_RE, "allow_empty": True},
    "REMAINING_CYCLES":        {"pattern": _NUM_RE, "allow_empty": True},
    "REMAINING_DAYS":          {"pattern": _NUM_RE, "allow_empty": True},
    "AC_TYPE":                 {"pattern": r"^[A-Z0-9\-]+$", "uppercase": True,
                                 "allow_empty": True},
    "REPORT_DATE":             {"pattern": _DATE_RE, "allow_empty": True},
    "AC_MSN":                  {"pattern": r"^\d+$", "allow_empty": True},
    "AC_HOURS":                {"pattern": _NUM_RE, "allow_empty": True},
    "AC_REG":                  {"pattern": r"^[A-Z0-9\-]+$", "uppercase": True,
                                 "allow_empty": True},
    "AC_CYCLES":               {"pattern": _NUM_RE, "allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Left edges (PDF points) of the fixed-width left-hand columns, from the
# real header/body coordinates on the sample file.
_MPD_X = 60.0
_PN_X = 95.0
_DESC_X = 155.0
_SN_X = 215.0
_LOC_X = 268.0
_INSTALL_DATE_X = 293.0
_RELEASE_DATE_X = 318.0
_NUM_BLOCK_X = 350.0       # start of the AC_TSN..LIMIT_DAYS numeric block
_LIMITER_X = 648.0         # start of the free-text LIMITER zone
_REM_BLOCK_X = 680.0       # start of the REMAINING_* numeric block

_NUM_FIELDS_1 = [
    "AC_TSN", "AC_CSN", "PART_TSN", "PART_CSN", "PART_TSO", "PART_CSO", "DSI",
    "TSN", "CSN", "TSI", "CSI", "TSO", "CSO", "DSO",
    "LIMIT_HOURS", "LIMIT_CYCLES", "LIMIT_DAYS",
]
_NUM_HEADER_X_1 = [
    354.1, 383.6, 412.4, 433.1, 453.8, 469.7, 482.1,
    494.6, 510.8, 527.5, 543.4, 559.3, 575.2, 591.9,
    606.2, 622.1, 638.8,
]
_NUM_FIELDS_2 = ["REMAINING_HOURS", "REMAINING_CYCLES", "REMAINING_DAYS"]
_NUM_HEADER_X_2 = [685.0, 701.6, 717.7]

_HEADER_ROW_RE = re.compile(r"^ATA\s+MPD\s+Reference\s+PART\s+NUMBER\s+DESCRIPTION")
_ATA_RE = re.compile(r"^\d{1,2}$")
_FOOTER_START_RE = re.compile(
    r"^(AUTHORIZED AIRLINE REPRESENTATIVE|SIGNATURE:|NAME:|POSITION:|DATE:)"
)
_PAGE_FOOTER_RE = re.compile(r"^\d+\s+of\s+\d+$")

_META_RE = {
    "AC_TYPE":    re.compile(r"A/C TYPE:\s*(\S+)"),
    "REPORT_DATE": re.compile(r"\bDATE:\s*(\S+)"),
    "AC_MSN":     re.compile(r"A/C MSN:\s*(\S+)"),
    "AC_HOURS":   re.compile(r"AIRCRAFT HOURS:\s*(\S+)"),
    "AC_REG":     re.compile(r"A/C REG:\s*(\S+)"),
    "AC_CYCLES":  re.compile(r"AIRCRAFT CYCLES:\s*(\S+)"),
}


def _nearest(x0: float, fields: list[str], xs: list[float]) -> str:
    best_i, best_dist = 0, abs(x0 - xs[0])
    for i in range(1, len(xs)):
        dist = abs(x0 - xs[i])
        if dist < best_dist:
            best_i, best_dist = i, dist
    return fields[best_i]


def _group_lines(words: list[dict]) -> list[dict]:
    ws = sorted(words, key=lambda w: (w["top"], w["x0"]))
    lines: list[dict] = []
    for w in ws:
        if lines and abs(w["top"] - lines[-1]["top"]) <= 2.5:
            lines[-1]["words"].append(w)
            lines[-1]["top"] = (lines[-1]["top"] + w["top"]) / 2
        else:
            lines.append({"top": w["top"], "words": [w]})
    for line in lines:
        line["words"].sort(key=lambda w: w["x0"])
    return lines


def _line_text(line: dict) -> str:
    return " ".join(w["text"] for w in line["words"])


# A small number of rows come back from `extract_words()` fully
# letter-spaced -- every character (including within a single number or
# word) its own token -- the same rendering quirk this project's
# `maintenance_due_report_porp96rr.py` documents for a different template.
# Confirmed directly: the gap between two consecutive characters *within*
# one word/number is ~0.0pt (occasionally a hair negative, i.e. touching),
# while the gap at a genuine word boundary within a multi-word
# DESCRIPTION on the very same letter-spaced row is ~0.7pt -- an order of
# magnitude larger and consistently so. A single gap threshold well
# between those two (comfortably below every real inter-field gap too,
# which run 7pt or more since those are already separated into different
# columns by x-position before this function ever runs) reconstructs the
# original word/number text -- including preserving genuine inter-word
# spaces in a multi-word DESCRIPTION -- without needing to special-case
# the letter-spaced rendering at all: it falls out of the same join logic
# used for this template's normal, already-word-segmented rows.
_WORD_GAP_THRESHOLD = 0.4


def _join_words(words: list[dict]) -> str:
    if not words:
        return ""
    ws = sorted(words, key=lambda w: w["x0"])
    parts = [ws[0]["text"]]
    prev_x1 = ws[0]["x1"]
    for w in ws[1:]:
        if w["x0"] - prev_x1 > _WORD_GAP_THRESHOLD:
            parts.append(" ")
        parts.append(w["text"])
        prev_x1 = w["x1"]
    return "".join(parts)


def _row_from_line(line: dict) -> dict:
    row = {col: "" for col in CANONICAL_COLUMNS}
    buckets: dict[str, list[dict]] = {
        "ATA": [], "MPD_REFERENCE": [], "PART_NUMBER": [], "DESCRIPTION": [],
        "SERIAL_NUMBER": [], "LOCATION_ZONE": [],
        "DATE_OF_INSTALLATION": [], "RELEASE_INSPECTION_DATE": [],
        "LIMITER": [],
    }
    for w in line["words"]:
        x0 = w["x0"]
        if x0 < _MPD_X:
            buckets["ATA"].append(w)
        elif x0 < _PN_X:
            buckets["MPD_REFERENCE"].append(w)
        elif x0 < _DESC_X:
            buckets["PART_NUMBER"].append(w)
        elif x0 < _SN_X:
            buckets["DESCRIPTION"].append(w)
        elif x0 < _LOC_X:
            buckets["SERIAL_NUMBER"].append(w)
        elif x0 < _INSTALL_DATE_X:
            buckets["LOCATION_ZONE"].append(w)
        elif x0 < _RELEASE_DATE_X:
            buckets["DATE_OF_INSTALLATION"].append(w)
        elif x0 < _NUM_BLOCK_X:
            buckets["RELEASE_INSPECTION_DATE"].append(w)
        elif x0 < _LIMITER_X:
            field = _nearest(x0, _NUM_FIELDS_1, _NUM_HEADER_X_1)
            buckets.setdefault(field, []).append(w)
        elif x0 < _REM_BLOCK_X:
            buckets["LIMITER"].append(w)
        else:
            field = _nearest(x0, _NUM_FIELDS_2, _NUM_HEADER_X_2)
            buckets.setdefault(field, []).append(w)
    for field, ws in buckets.items():
        row[field] = _join_words(ws)
    return row


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    meta = {k: "" for k in _META_RE}

    with pdfplumber.open(pdf_path) as pdf:
        if pdf.pages:
            head_text = normalize_dashes(pdf.pages[0].extract_text() or "")
            head_text = head_text.split("PART DATA")[0]
            for field, rx in _META_RE.items():
                m = rx.search(head_text)
                if m:
                    meta[field] = m.group(1)

        for page_num, page in enumerate(pdf.pages, start=1):
            words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
            if not words:
                continue
            for w in words:
                w["text"] = normalize_dashes(w["text"])
            lines = _group_lines(words)

            for line in lines:
                text = _line_text(line)
                if _HEADER_ROW_RE.match(text):
                    continue
                if _PAGE_FOOTER_RE.match(text):
                    continue
                if _FOOTER_START_RE.match(text):
                    # Signature/authorisation block -- everything from here
                    # to the end of the page is dropped, not merged into a
                    # data row.
                    break
                ata_text = " ".join(w["text"] for w in line["words"] if w["x0"] < _MPD_X)
                has_numeric = any(_NUM_BLOCK_X <= w["x0"] < _LIMITER_X for w in line["words"])
                if not (_ATA_RE.match(ata_text) and has_numeric):
                    # Not a recognisable data row (e.g. an aircraft-info
                    # header line, or stray page furniture) -- skip rather
                    # than force it into a row.
                    continue
                row = _row_from_line(line)
                row["_page"] = page_num
                row.update(meta)
                records.append(row)

    return records
