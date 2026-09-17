"""HT Aircraft Component LOG -- title reads literally "HT Aircraft
Component LOG" followed by an "AIRCRAFT <reg>" line and a small metadata
block. Has a REAL TEXT LAYER (confirmed directly via a pdfplumber pass over
the real sample file) -- this module is synchronous, pdfplumber-only, no
OCR.

Header block, first page only (confirmed: not repeated on later pages)::

    HT Aircraft Component LOG
    AIRCRAFT <reg>
    SINCE NEW HOUR: <n>
    CYCLES: <n>
    UNIT REMOVAL BASED ON <n> HOURS AND <n> CYCLES PER DAY
    A/C at Installation | Component usage | Shedule Limit | Remaining
    ATA  Part Description  Part No  Serial No  Stock No  POS  Forecast
    DATE TIME CYCLE  TSN TSO CSN CSO DSN DSO DSLV  TIME CYCLE DAY  TIME CYCLE DAY

The two-band header is confirmed directly against real word x-positions:
"A/C at Installation" groups DATE/TIME/CYCLE (aircraft hours/cycles at the
moment this part was installed); "Component usage" groups TSN/TSO/CSN/CSO/
DSN/DSO/DSLV (time-since-new / time-since-overhaul / cycles-since-new /
cycles-since-overhaul / days-since-new / days-since-overhaul / days-since-
last-visit, all printed abbreviations verbatim rather than renamed, since
guessing at the exact expansion of the source report's own abbreviation
risks mislabeling it); "Shedule Limit" (sic, matches the source's own
spelling, not corrected) and "Remaining" each group their own TIME/CYCLE/
DAY triple. A single-letter governing-basis column (seen values: D/H/C,
presumably Days/Hours/Cycles -- whichever parameter governs the Forecast
date) sits between the Remaining triple and Forecast with no printed header
text of its own (confirmed directly: no word occupies that header row's x
range above it) -- this module still carries it as its own column since its
x-position is stable and distinct from its neighbours on every real row.

Table layout, confirmed directly against real word x-positions (columns are
NOT evenly spaced and several are right-aligned numeric fields, so a plain
`.split()` tokenizer would misalign them)::

    <ata> <description> <part_no> <serial_no> <stock_no> <pos> <date> <ac_time> <ac_cycle>
    <tsn> <tso> <csn> <cso> <dsn> <dso> <dslv>
    <sched_time> <sched_cycle> <sched_day> <rem_time> <rem_cycle> <rem_day>
    <governing_basis> <forecast_date>

Row extraction uses `extract_words()` (word-level boxes); words are
clustered into visual rows by `top` position (small tolerance, since words
on the same printed row can differ by a fraction of a point due to font
baseline/rendering -- same technique as this project's other position-
column HT/OCCM variants), then each word is assigned to a column purely by
which column's x-range its centre falls in.

Confirmed real-file quirks driving the RULES/merge logic below:

- DESCRIPTION and PART_NUMBER are blank on rows that continue an earlier
  ATA/part group (confirmed directly, e.g. a part with several fitted
  serials/positions lists the description/part number once, then leaves
  both blank on each subsequent serial row) -- left as printed, no forced
  fill. Unlike sheet_types/occm.py, sheet_types/ht.py's own
  normalize_and_validate() does not run a generic ATA forward-fill
  post-process, so ATA is simply allowed empty here (RULES override below)
  rather than assumed to be back-filled elsewhere.
- DESCRIPTION genuinely wraps across multiple physical PDF lines for a
  single logical row (confirmed directly against the real sample file --
  e.g. a 3-line wrap where the row's own numeric data sits on the middle
  line). A "continuation" physical line here is one with NO value in any
  of the numeric/date columns -- confirmed directly, every real data row
  carries a parseable INSTALL_DATE, so a physical line failing that check
  is never itself a distinct record. Rather than guess which canonical
  column a continuation line's word(s) belong to (a short numeric token on
  a continuation line has been confirmed, directly against the real file,
  to sometimes read as a serial-number-shaped fragment and sometimes as
  plain description text that merely renders further right than usual --
  there is no reliable way to tell which from position alone), every
  continuation line's full text (all its words, left-to-right, regardless
  of which column x-range they individually fall in) is appended verbatim
  to a dedicated CONTINUATION_TEXT catch-all column on the nearest
  preceding data row -- never merged into DESCRIPTION, SERIAL_NUMBER, or
  any other typed column. This is the "never guess a wrong split" rule
  applied here: ambiguous wrapped text is preserved for a human reviewer
  rather than being forced into a column it might not belong to.
- Several numeric columns print an Excel-style column-overflow placeholder
  ("#######"/"#########") or a very large integer placeholder (e.g.
  "10000000"/"1,000,000") in place of a real value on real rows -- neither
  is a parse failure; both are accepted, not flagged, by the shared numeric
  pattern below.
- AC_CYCLES_AT_INSTALL and a few other numeric fields print a literal "-"
  placeholder on rows where the corresponding hours value reads "0.00"
  (part installed since new) -- accepted, not flagged, same convention as
  this project's other HT/OCCM variants with an installed-since-new case.

No further catch-all column is needed beyond CONTINUATION_TEXT: every other
column is resolved with confidence from position, and any resulting
ambiguity in THOSE (blank cells, unusual formats) is left as literal empty/
free text and handled by RULES below rather than guessed at.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.ht_variants._base import merged_rules

NAME = "HT Aircraft Component LOG"
SIGNATURES = [
    "HT Aircraft Component LOG",
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
    "TSN",
    "TSO",
    "CSN",
    "CSO",
    "DSN",
    "DSO",
    "DSLV",
    "SCHEDULE_LIMIT_TIME",
    "SCHEDULE_LIMIT_CYCLE",
    "SCHEDULE_LIMIT_DAY",
    "REMAINING_TIME",
    "REMAINING_CYCLE",
    "REMAINING_DAY",
    "GOVERNING_BASIS",
    "FORECAST_DATE",
    # Catch-all for continuation-line text that cannot be confidently
    # attributed to a specific typed column -- see module docstring.
    "CONTINUATION_TEXT",
    # Header metadata, parsed once per file and stamped on every row.
    "AIRCRAFT_REG",
    "SINCE_NEW_HOUR",
    "SINCE_NEW_CYCLES",
    "REMOVAL_HOURS_PER_DAY",
    "REMOVAL_CYCLES_PER_DAY",
]

# Accepts: a literal "-" placeholder, a plain or comma-grouped integer with
# an optional decimal part (confirmed directly on real rows: some numeric
# columns print plain unthousanded digit runs like "24358.11", others print
# comma-grouped placeholders like "1,000,000" -- both accepted, since this
# is the source report's own inconsistent-but-genuine formatting, not an
# extraction error), or an Excel-style column-overflow placeholder run of
# "#" characters.
_NUMERIC_RULE = {
    "pattern": r"^(?:-|#+|\d+(?:,\d{3})*(?:\.\d+)?)$",
    "allow_empty": True,
}
_DATE_RULE = {"pattern": r"^\d{2}-\d{2}-\d{2}$", "allow_empty": True}
_FORECAST_DATE_RULE = {"pattern": r"^\d{2}-[A-Za-z]{3}-\d{4}$", "allow_empty": True}

_OVERRIDES = {
    # Blank whenever a row continues an earlier ATA/part group (see module
    # docstring) -- this router (unlike sheet_types/occm.py) does not run a
    # generic ATA forward-fill post-process, so blank is accepted here
    # directly rather than flagged, same convention as this project's other
    # HT variants with the same continuation-row shape (e.g.
    # air_france_ccinv_aircraft_inventory.py, ca004_hard_time_monitoring_
    # sheet.py).
    "ATA": {"allow_empty": True},
    "DESCRIPTION": {"uppercase": True, "allow_empty": True},
    "PART_NUMBER": {
        # Confirmed directly against the real sample file: a genuine part
        # number can contain a forward slash (e.g. "DK120/90") -- the
        # shared global PART_NUMBER pattern doesn't allow that, so it's
        # widened here rather than flagging a real, correctly-split value.
        "pattern": r"^[A-Z0-9](?:[A-Z0-9\-/]*[A-Z0-9])?$",
        "allow_empty": True,
    },
    "SERIAL_NUMBER": {"allow_empty": True},
    # POSITION is a genuine mix of dotted codes, bare digits, side/bay/seat
    # free text, and station/label codes (confirmed directly against the
    # real sample file) -- deliberately permissive rather than guessing a
    # wrong shape.
    "POSITION": {
        "pattern": r"^[A-Z0-9](?:[A-Z0-9 ./#\[\]\-]{0,40})?$",
        "uppercase": True,
        "allow_empty": True,
    },
    # Confirmed directly against the real sample file: always 7 characters,
    # but a genuine minority mix in letters (e.g. "26M0018") rather than
    # being purely numeric.
    "STOCK_NUMBER": {"pattern": r"^[A-Z0-9]{7}$", "uppercase": True, "allow_empty": True},
    "INSTALL_DATE": _DATE_RULE,
    "AC_HOURS_AT_INSTALL": _NUMERIC_RULE,
    "AC_CYCLES_AT_INSTALL": _NUMERIC_RULE,
    "TSN": _NUMERIC_RULE,
    "TSO": _NUMERIC_RULE,
    "CSN": _NUMERIC_RULE,
    "CSO": _NUMERIC_RULE,
    "DSN": _NUMERIC_RULE,
    "DSO": _NUMERIC_RULE,
    "DSLV": _NUMERIC_RULE,
    "SCHEDULE_LIMIT_TIME": _NUMERIC_RULE,
    "SCHEDULE_LIMIT_CYCLE": _NUMERIC_RULE,
    "SCHEDULE_LIMIT_DAY": _NUMERIC_RULE,
    "REMAINING_TIME": _NUMERIC_RULE,
    "REMAINING_CYCLE": _NUMERIC_RULE,
    "REMAINING_DAY": _NUMERIC_RULE,
    # Seen values D/H/C on the real sample file; kept permissive (any
    # single uppercase letter) rather than an enum, since a different real
    # file could plausibly use another governing-parameter letter.
    "GOVERNING_BASIS": {"pattern": r"^[A-Z]$", "allow_empty": True},
    "FORECAST_DATE": _FORECAST_DATE_RULE,
    # Free-text catch-all; deliberately unvalidated (see module docstring).
    "CONTINUATION_TEXT": {"allow_empty": True},
    "AIRCRAFT_REG": {"uppercase": True, "allow_empty": True},
    "SINCE_NEW_HOUR": {"allow_empty": True},
    "SINCE_NEW_CYCLES": {"allow_empty": True},
    "REMOVAL_HOURS_PER_DAY": {"allow_empty": True},
    "REMOVAL_CYCLES_PER_DAY": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Column boundaries as (x0_inclusive, x1_exclusive, CANONICAL_COLUMNS name),
# derived as midpoints between the real header's own word x-position
# centres, confirmed directly against the real sample file's header word
# positions. GOVERNING_BASIS carries no header text of its own (see module
# docstring) -- its slot is inferred from real data rows' own word
# position, which is stable and distinct from its neighbours.
_COLUMNS = [
    (-1e9, 89.5, "ATA"),
    (89.5, 154.6, "DESCRIPTION"),
    (154.6, 217.9, "PART_NUMBER"),
    (217.9, 275.0, "SERIAL_NUMBER"),
    (275.0, 329.4, "STOCK_NUMBER"),
    (329.4, 377.5, "POSITION"),
    (377.5, 419.3, "INSTALL_DATE"),
    (419.3, 461.3, "AC_HOURS_AT_INSTALL"),
    (461.3, 503.8, "AC_CYCLES_AT_INSTALL"),
    (503.8, 544.7, "TSN"),
    (544.7, 583.4, "TSO"),
    (583.4, 620.1, "CSN"),
    (620.1, 658.0, "CSO"),
    (658.0, 698.3, "DSN"),
    (698.3, 739.4, "DSO"),
    (739.4, 781.8, "DSLV"),
    (781.8, 825.0, "SCHEDULE_LIMIT_TIME"),
    (825.0, 866.1, "SCHEDULE_LIMIT_CYCLE"),
    (866.1, 907.2, "SCHEDULE_LIMIT_DAY"),
    (907.2, 951.3, "REMAINING_TIME"),
    (951.3, 1000.3, "REMAINING_CYCLE"),
    (1000.3, 1043.6, "REMAINING_DAY"),
    (1043.6, 1085.4, "GOVERNING_BASIS"),
    (1085.4, 1e9, "FORECAST_DATE"),
]
# Header/body split for page 1 only -- the real header block (title + A/C
# metadata + the two-band column-group header) ends well above this,
# confirmed directly against the real sample file's own header word
# positions (last header word's `top` is ~142). Pages after the first carry
# no repeated header at all (confirmed: their first line is already a data
# row), so no cutoff is applied there.
_PAGE1_BODY_TOP_MIN = 150.0
_ROW_CLUSTER_TOL = 3.5

_REG_RE = re.compile(r"AIRCRAFT\s+(\S+)")
_SNH_RE = re.compile(r"SINCE\s+NEW\s+HOUR:\s*(\S+)")
_CYCLES_RE = re.compile(r"\bCYCLES:\s*(\S+)")
_REMOVAL_RE = re.compile(
    r"UNIT\s+REMOVAL\s+BASED\s+ON\s+(\S+)\s+HOURS\s+AND\s+(\S+)\s+CYCLES\s+PER\s+DAY"
)
_INSTALL_DATE_RE = re.compile(r"^\d{2}-\d{2}-\d{2}$")


def _col_for_x(x: float) -> str | None:
    for lo, hi, name in _COLUMNS:
        if lo <= x < hi:
            return name
    return None


def _parse_header_meta(first_page_text: str) -> dict:
    meta = {
        "AIRCRAFT_REG": "", "SINCE_NEW_HOUR": "", "SINCE_NEW_CYCLES": "",
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
        meta["SINCE_NEW_CYCLES"] = m.group(1)
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


def _row_words_to_cols(row_words: list[dict]) -> dict[str, list[str]]:
    cols: dict[str, list[str]] = {}
    for w in row_words:
        cx = (w["x0"] + w["x1"]) / 2
        name = _col_for_x(cx)
        if name is None:
            continue
        cols.setdefault(name, []).append(w["text"])
    return cols


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        if not pdf.pages:
            return records
        meta = _parse_header_meta(pdf.pages[0].extract_text() or "")
        pending_prefix: list[str] = []
        last_record: dict | None = None
        for page_num, page in enumerate(pdf.pages, start=1):
            words = page.extract_words()
            if not words:
                continue
            top_min = _PAGE1_BODY_TOP_MIN if page_num == 1 else -1.0
            for row_words in _cluster_rows(words, top_min):
                cols = _row_words_to_cols(row_words)
                if not cols:
                    continue
                install_date = " ".join(cols.get("INSTALL_DATE", []))
                if _INSTALL_DATE_RE.match(install_date):
                    # Genuine data row.
                    rec = {name: " ".join(cols.get(name, [])) for _, _, name in _COLUMNS}
                    rec["CONTINUATION_TEXT"] = ""
                    rec.update(meta)
                    rec["_page"] = page_num
                    if pending_prefix:
                        rec["CONTINUATION_TEXT"] = " ".join(pending_prefix)
                        pending_prefix = []
                    records.append(rec)
                    last_record = rec
                else:
                    # Continuation line -- no reliable per-column split (see
                    # module docstring); preserve verbatim, left-to-right,
                    # on the nearest preceding data row (or buffered for the
                    # next one if none has been seen yet on this file).
                    frag_words = sorted(row_words, key=lambda w: w["x0"])
                    frag_text = " ".join(w["text"] for w in frag_words)
                    if last_record is not None:
                        existing = last_record["CONTINUATION_TEXT"]
                        last_record["CONTINUATION_TEXT"] = (
                            f"{existing} {frag_text}".strip() if existing else frag_text
                        )
                    else:
                        pending_prefix.append(frag_text)
    return records
