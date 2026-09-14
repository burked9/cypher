"""TIME CONTROLLED ITEMS CURRENT STATUS -- per-aircraft hard-time export.
Born-digital, full text layer (confirmed via a direct pdfplumber pass over
the real sample file: `extract_words()` returns full content on every
page, no OCR needed).

Distinct title/template from this project's `time_controlled_items_status.py`
(no "Current" in that one's title, and a totally different ragged
3-line-block layout) and `time_controlled_components_status.py` (different
title, different column set). This format instead prints one clean
physical text line per component, with every field aligned to a fixed set
of x-position columns -- no cross-page word-order scrambling, no
line-wrap-into-orphan-fragment quirk, confirmed by grouping words into
physical lines (tolerant of the usual sub-point "top" jitter) and checking
every one of the 124 data lines on the real sample file resolves cleanly
on its own single line, no merge-with-neighbour needed.

Header block (repeats verbatim at the top of every page)::

    <type> MSN <msn> Time Controlled Items Current Status
    Date <dd-Mon-yy>
    Airframe TT <hours>
    Airframe TC <cycles>
    Component     Interval      Last Done     Next Due   CSN   Life Limit
    ATA Position Part-Number Serial-Number Description Task Date of Inst
        DY FH FC   DY (Form 1) FH FC   DY   A/C FH A/C FC   To Go

Row grain: one row per tracked component. Columns, left to right::

    ATA | POSITION | PART_NUMBER | SERIAL_NUMBER | DESCRIPTION | TASK |
    DATE_OF_INST |
    INTERVAL_DY | INTERVAL_FH | INTERVAL_FC |
    LAST_DONE_DATE | LAST_DONE_FH | LAST_DONE_FC |
    NEXT_DUE_DATE |
    CSN_FH | CSN_FC |
    LIFE_LIMIT_TO_GO

Despite the header printing "DY" three times (once under Interval, once
under Last Done, once under Next Due), those three columns hold different
kinds of value on the real data rows -- confirmed directly via
`extract_words()`: Interval's DY column always holds a bare day-count
integer (e.g. "4380", "3650"), while Last Done's "DY (Form 1)" column and
Next Due's "DY" column both always hold an actual calendar date (e.g.
"10-Aug-18") -- "Form 1" is this template's own label for the EASA/FAA
release-certificate date the component was last done against. Named
LAST_DONE_DATE / NEXT_DUE_DATE here rather than keeping the header's own
"DY" suffix, to avoid implying a day-count where the real value is a date.

A handful of dates in the Next Due and Life Limit columns print in French
rather than English month abbreviations (e.g. "26-mai-33", "28-févr-30",
"30-sept-22") -- confirmed this is the source PDF's own text layer, not an
extraction artefact, by rendering the page as an image and reading it
directly: the page is crisp and shows the same French abbreviations. Both
languages are accepted by this module's date pattern rather than flagging
the French ones as bad data.

Each component is tracked by whichever basis applies to it (FH-only,
FC-only, calendar-only, DY-only, or a mix), so most rows leave several of
the Interval/Last-Done/CSN sub-columns blank. Columns are assigned to
words by nearest fixed x-position bin (bin edges below are the midpoints
of the real, consistently wide gaps observed between adjacent columns'
word clusters across the whole sample file -- re-derived from data, not
from the printed header labels, because the header's own word positions
turned out NOT to line up with where the data actually sits, e.g. the
printed "Description" header sits well to the right of where every actual
description value starts).

Thousands-separator quirk: this template renders a >=4-digit figure with a
literal space as the thousands separator (e.g. "12 000", "64 853"), which
pdfplumber's word segmenter splits into two separate word tokens on the
same physical line. Both tokens always land inside the SAME column bin as
each other (confirmed across every split-number instance in the sample
file: the two halves are never more than ~9pt apart, far inside one
column's own width and far short of the >=15pt gap to the next real
column), so they are simply concatenated (digits only, no separator) when
more than one token lands in a numeric bin on a row.

CSN_FH / CSN_FC deserve a specific note since their columns sit unusually
close together (only a plain single-word "FH"/"FC" header label separates
them): confirmed directly against multiple rows that use only one of the
two (never both at once in the sample file) that the bin-based classifier
above assigns each pair of split-number tokens to the correct single
column and not split across the FH/FC boundary, because -- as above -- a
genuine split-number's two halves never straddle a real column boundary.

LIFE_LIMIT_TO_GO is kept as one catch-all trailing field (not split
further) because it mixes two genuinely different kinds of value on
different rows -- a bare remaining-count integer on some rows, a life-limit
expiry date (including the French-language ones noted above) on others --
and forcing a fixed sub-type split on an ambiguous trailing column risks a
wrong split. Same project convention as `hard_time_report_config_slot.py`'s
and `time_controlled_components_status.py`'s own trailing catch-all
columns.

Header metadata (aircraft type, MSN, report date, airframe total time,
airframe total cycles) is parsed once from the first page and stamped on
every row, the same convention `ca004_hard_time_monitoring_sheet.py` uses
for its own sibling header block.

The page-number footer (a single bare digit, e.g. "3", centred near the
bottom of every page) and the repeating title/date/airframe-info/column-
header lines are dropped: this module only turns a physical line into a
row when its own leftmost word sits in the ATA column's bin and is a bare
2-digit number, which none of that page furniture ever matches.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.ht_variants._base import merged_rules
from shared.cleanup import normalize_dashes

NAME = "Time Controlled Items Current Status"
SIGNATURES = [
    # Deliberately includes "CURRENT" so it can't collide with this
    # project's own "TIME CONTROLLED ITEMS STATUS"
    # (time_controlled_items_status.py) or "TIME CONTROLLED COMPONENTS
    # STATUS" (time_controlled_components_status.py) signatures -- neither
    # of those phrases is a contiguous substring of this one, so a
    # substring-match detector (as used by sheet_types/ht.py,
    # sheet_types/occm.py, sheet_types/llp.py) cannot mix them up in
    # either direction. Checked against every SIGNATURES list in
    # occm.py/ht.py/llp.py and every occm_variants/ht_variants/llp_variants
    # module; no collision found.
    "Time Controlled Items Current Status",
]

CANONICAL_COLUMNS = [
    "ATA",
    "POSITION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
    "TASK",
    "DATE_OF_INST",
    "INTERVAL_DY",
    "INTERVAL_FH",
    "INTERVAL_FC",
    "LAST_DONE_DATE",
    "LAST_DONE_FH",
    "LAST_DONE_FC",
    "NEXT_DUE_DATE",
    "CSN_FH",
    "CSN_FC",
    "LIFE_LIMIT_TO_GO",
    # Header metadata -- same on every row of a given file.
    "AIRCRAFT_TYPE",
    "MSN",
    "REPORT_DATE",
    "AIRFRAME_TT",
    "AIRFRAME_TC",
]

# Date values on this template are day-month-year with a dash separator,
# month as a 3-6 letter abbreviation in either English or French (e.g.
# "10-Aug-18", "28-févr-30") -- see module docstring.
_DATE_RE = r"^\d{1,2}-[A-Za-zÀ-ÿ]{3,6}-\d{2,4}$"
_NUM_RE = r"^\d+$"

_OVERRIDES = {
    "POSITION":        {"pattern": r"^[A-Z0-9]+$", "uppercase": True,
                         "allow_empty": True},
    # Occasionally a combined code, e.g. "HYD/WHT" (two task codes for one
    # component visit) -- confirmed a real value on the sample file, not
    # an extraction artefact.
    "TASK":            {"pattern": r"^[A-Z]{2,4}(?:/[A-Z]{2,4})?$",
                         "uppercase": True, "allow_empty": True},
    "DATE_OF_INST":    {"pattern": _DATE_RE, "allow_empty": True},
    "INTERVAL_DY":     {"pattern": _NUM_RE, "allow_empty": True},
    "INTERVAL_FH":     {"pattern": _NUM_RE, "allow_empty": True},
    "INTERVAL_FC":     {"pattern": _NUM_RE, "allow_empty": True},
    "LAST_DONE_DATE":  {"pattern": _DATE_RE, "allow_empty": True},
    "LAST_DONE_FH":    {"pattern": _NUM_RE, "allow_empty": True},
    "LAST_DONE_FC":    {"pattern": _NUM_RE, "allow_empty": True},
    "NEXT_DUE_DATE":   {"pattern": _DATE_RE, "allow_empty": True},
    "CSN_FH":          {"pattern": _NUM_RE, "allow_empty": True},
    "CSN_FC":          {"pattern": _NUM_RE, "allow_empty": True},
    # Bare remaining-count integer on some rows, a (possibly
    # French-language) life-limit expiry date on others -- kept as one
    # unvalidated catch-all string, see module docstring.
    "LIFE_LIMIT_TO_GO": {"allow_empty": True},
    "AIRCRAFT_TYPE":   {"pattern": r"^[A-Z0-9\-]+$", "uppercase": True,
                         "allow_empty": True},
    "MSN":             {"pattern": r"^\d+$", "allow_empty": True},
    "REPORT_DATE":     {"pattern": _DATE_RE, "allow_empty": True},
    "AIRFRAME_TT":     {"pattern": _NUM_RE, "allow_empty": True},
    "AIRFRAME_TC":     {"pattern": _NUM_RE, "allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_ATA_RE = re.compile(r"^\d{2}$")

# Column bins: (upper_x_bound, field, join_kind). A word's x0 is matched
# against the first bin whose upper bound it is less than. "text" joins
# multiple tokens in the bin with a space (e.g. a multi-word DESCRIPTION);
# "num" joins them with nothing, for the space-thousands-separator quirk
# described in the module docstring. Bounds are the midpoints of the real
# gaps measured between adjacent columns' word clusters across the whole
# sample file (see docstring) -- not the printed header's own positions,
# which don't reliably line up with the data.
_BINS = [
    (78.55,  "ATA",             "num"),
    (105.45, "POSITION",        "text"),
    (136.25, "PART_NUMBER",     "text"),
    (178.1,  "SERIAL_NUMBER",   "text"),
    (315.75, "DESCRIPTION",     "text"),
    (351.0,  "TASK",            "text"),
    (384.6,  "DATE_OF_INST",    "text"),
    (423.15, "INTERVAL_DY",     "num"),
    (442.0,  "INTERVAL_FH",     "num"),
    (468.45, "INTERVAL_FC",     "num"),
    (499.85, "LAST_DONE_DATE",  "text"),
    (534.8,  "LAST_DONE_FH",    "num"),
    (560.25, "LAST_DONE_FC",    "num"),
    (586.35, "NEXT_DUE_DATE",   "text"),
    (620.1,  "CSN_FH",          "num"),
    (660.9,  "CSN_FC",          "num"),
    (float("inf"), "LIFE_LIMIT_TO_GO", "text"),
]


def _bin_for(x0: float) -> tuple[str, str]:
    for upper, field, kind in _BINS:
        if x0 < upper:
            return field, kind
    return "LIFE_LIMIT_TO_GO", "text"  # pragma: no cover -- _BINS ends in +inf


def _group_lines(words: list[dict]) -> list[dict]:
    ws = sorted(words, key=lambda w: (w["top"], w["x0"]))
    lines: list[dict] = []
    for w in ws:
        if lines and abs(w["top"] - lines[-1]["top"]) <= 1.0:
            lines[-1]["words"].append(w)
            lines[-1]["top"] = (lines[-1]["top"] + w["top"]) / 2
        else:
            lines.append({"top": w["top"], "words": [w]})
    for line in lines:
        # Sorting is required here, not optional: words on the same
        # physical line can carry slightly different "top" values (seen
        # up to ~0.25pt apart on the sample file), and the initial sort
        # above is keyed on "top" first -- without re-sorting by x0 within
        # each grouped line, that jitter can reorder a line's own tokens
        # out of left-to-right order.
        line["words"].sort(key=lambda w: w["x0"])
    return lines


def _row_from_line(line: dict) -> dict:
    row = {col: "" for col in CANONICAL_COLUMNS}
    buckets: dict[str, list[str]] = {}
    for w in line["words"]:
        field, _kind = _bin_for(w["x0"])
        buckets.setdefault(field, []).append(w["text"])
    for field, tokens in buckets.items():
        _upper, _f, kind = next(b for b in _BINS if b[1] == field)
        row[field] = "".join(tokens) if kind == "num" else " ".join(tokens)
    return row


_TYPE_MSN_RE = re.compile(
    r"^(\S+)\s+MSN\s+(\S+)\s+Time Controlled Items Current Status", re.M)
_REPORT_DATE_RE = re.compile(r"^Date\s+(\S+)\s*$", re.M)
_TT_RE = re.compile(r"Airframe TT\s+(\S+)")
_TC_RE = re.compile(r"Airframe TC\s+(\S+)")


def _parse_header_meta(text: str) -> dict:
    meta = {"AIRCRAFT_TYPE": "", "MSN": "", "REPORT_DATE": "",
            "AIRFRAME_TT": "", "AIRFRAME_TC": ""}
    m = _TYPE_MSN_RE.search(text)
    if m:
        meta["AIRCRAFT_TYPE"], meta["MSN"] = m.group(1), m.group(2)
    m = _REPORT_DATE_RE.search(text)
    if m:
        meta["REPORT_DATE"] = m.group(1)
    m = _TT_RE.search(text)
    if m:
        meta["AIRFRAME_TT"] = m.group(1)
    m = _TC_RE.search(text)
    if m:
        meta["AIRFRAME_TC"] = m.group(1)
    return meta


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    meta: dict | None = None
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = normalize_dashes(page.extract_text() or "")
            if meta is None:
                meta = _parse_header_meta(text)
            words = [
                {**w, "text": normalize_dashes(w["text"])}
                for w in page.extract_words()
            ]
            for line in _group_lines(words):
                first = line["words"][0]
                if not (first["x0"] < _BINS[0][0]
                        and _ATA_RE.match(first["text"])):
                    continue  # page furniture: title/date/header/footer
                row = _row_from_line(line)
                row.update(meta or {})
                records.append(row)
    return records
