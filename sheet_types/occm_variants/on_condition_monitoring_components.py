"""On Condition Monitoring Components (ATA-range title) -- an OCCM export
with a genuine, page-searchable text layer confirmed via a direct
pdfplumber pass over the real sample file (no OCR needed) -- this module is
synchronous, pdfplumber-only.

Title line (page 1 only; NOT repeated with the same wording on every page --
most later pages carry the same block but with a single ATA chapter number
instead of a range, e.g. `ATA 21`, `ATA 33`, confirmed directly across the
whole sample)::

    <operator> ATA <n>[-<n>] ON CONDITION MONITORING COMPONENTS
    MODEL: <type> Date: <date>
    Manufacture Date: <date> TAT (FH): <n>
    A/C MSN: <msn> TAC: <n>

The title/meta block is only parsed once, from page 1, per this project's
usual convention -- MSN/TAT/TAC identify the aircraft, not the page's ATA
chapter, so they don't change page to page. "ON CONDITION MONITORING
COMPONENTS" itself renders cleanly on every page checked and is this
module's SIGNATURES anchor; the operator name and a few header tokens
around it are subject to the same glyph-rendering noise described below, so
they are deliberately NOT used as anchors.

Column-header line (also renders on most, but not all, pages -- some pages
run straight from the meta block into data rows with no repeated column
header, confirmed directly)::

    ATA COMP. DESCRIPTION PART NUMBER SERIAL NUMBER INSTALLED ON TSN (FH) CSN (CY) REMARK

Row shape, one line per component::

    <ata> <comp> <description...> <part_number> <serial_number> <installed_on> <tsn> <csn> [<remark...>]

Extraction strategy -- structural (right-anchored token) parsing, NOT
x-position column bucketing: the real sample's column x-positions shift
noticeably page to page (confirmed directly, e.g. the ATA column's x0 sits
at ~38-56pt depending on the page) and a meaningful minority of pages have
no column-header line of their own to derive per-page anchors from, so
reusing a previous page's anchors on a header-less page produces wrong
buckets (confirmed directly: doing so misfiled the leading ATA token into
the COMP column, and a wrapped DESCRIPTION word past the narrower-than-usual
description boundary into PART_NUMBER, on a real page in the sample).
Instead each row is parsed from its own token shape: ATA (2 digits) and
COMP (a signed/unsigned 3-6 digit item number, e.g. `-<nnnn>`, `<nnnnn>`) are
the first two tokens; the row's own INSTALLED_ON date token is located by
scanning backward from the end for a `D-Mon-YY`-shaped token (tolerant of
the OCR noise below); PART_NUMBER and SERIAL_NUMBER are the two tokens
immediately before it; TSN and CSN are the (up to) two numeric tokens
immediately after it; anything left over is REMARK (empty on every row in
the real sample). DESCRIPTION is everything between COMP and PART_NUMBER,
joined back together -- this also naturally absorbs the occasional stray
single-character token (a checkbox/tick-mark artifact, e.g. a trailing `I`
or `1` seen directly after a `-LH` position suffix in the real sample)
without having to special-case it.

Two real, source-level rendering defects, both confirmed directly and
handled explicitly rather than guessed at:

1. A missing thousands-separator glyph occasionally splits one number into
   two adjacent word tokens with almost no gap between them (e.g. TSN
   `<n>,<nnn>` rendering as the two tokens `<n>` and `<nnn>`). Re-joining is
   gated on the actual horizontal gap between the two word boxes (a tight
   ~1-2pt gap, vs. the ~40-60pt real gap between genuinely distinct
   columns), not on digit shape alone -- shape alone would also wrongly
   merge a genuinely short TSN with an unrelated following CSN that happens
   to be exactly 3 digits.
2. A handful of rows (a small minority of the real sample) have their
   INSTALLED_ON date corrupted beyond this module's tolerant date pattern
   (e.g. a month rendered with digits substituted for letters so badly no
   3-letter month token remains, or trailing junk glyphs fused onto the
   token). These rows are not force-parsed with a guessed split; they are
   dropped rather than risk misassigning PART_NUMBER/SERIAL_NUMBER/TSN/CSN
   into the wrong slot, per this project's "never guess a wrong split"
   convention (see e.g. `occm_variants/multi_basis_accumulated_occm.py`,
   `occm_variants/stars_trax_occm.py`).

Header metadata (AIRCRAFT_TYPE, REPORT_DATE, MANUFACTURE_DATE, TAT_FH, MSN,
TAC) is parsed once from page 1 and stamped onto every row. The real
sample's MSN/TAC separator sometimes renders as a stray middle-dot (`·`)
instead of `:` (an OCR/glyph-substitution artifact, not a real punctuation
choice), and TAC's own value is subject to the same missing-comma splitting
described above (e.g. `<n>,<nnn>` rendering as `<n> <nnn>`) -- both are handled
by the same tolerant parsing used for MSN/TAC's separator and thousands
grouping respectively.

No OCR is used: extract() is synchronous, unlike the OCR-backed variants in
this same package.
"""
from __future__ import annotations
import re

import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "On Condition Monitoring Components"
SIGNATURES = [
    "ON CONDITION MONITORING COMPONENTS",
]

CANONICAL_COLUMNS = [
    "AIRCRAFT_TYPE", "REPORT_DATE", "MANUFACTURE_DATE", "TAT_FH", "MSN", "TAC",
    "ATA", "COMP", "DESCRIPTION", "PART_NUMBER", "SERIAL_NUMBER",
    "INSTALLED_ON", "TSN", "CSN", "REMARK",
]

_NUMERIC_RULE = {
    "pattern": r"^\d{1,3}(?:,\d{3})*$",
    "int_range": (0, 500000),
    "allow_empty": True,
}
_ROW_DATE_RULE = {"pattern": r"^\d{1,2}-[A-Za-z]{3}-\d{2}$", "allow_empty": True}

_OVERRIDES = {
    "AIRCRAFT_TYPE": {"pattern": r"^[A-Z0-9\-]{2,15}$", "uppercase": True, "allow_empty": True},
    "REPORT_DATE": dict(_ROW_DATE_RULE),
    # MANUFACTURE_DATE prints with a 4-digit year (`<dd>-<MON>-<yyyy>`), unlike
    # every other date field in this module, which use a 2-digit year --
    # confirmed directly against the real sample, so it gets its own rule
    # rather than reusing _ROW_DATE_RULE.
    "MANUFACTURE_DATE": {"pattern": r"^\d{1,2}-[A-Za-z]{3}-\d{4}$", "allow_empty": True},
    "TAT_FH": dict(_NUMERIC_RULE),
    "MSN": {"pattern": r"^[A-Z0-9]{1,10}$", "uppercase": True, "allow_empty": True},
    "TAC": dict(_NUMERIC_RULE),
    # COMP is this format's own item/index number: a zero-padded positive
    # index or a hyphen-prefixed index number -- no global rule exists for
    # this column name so it's given one here.
    "COMP": {"pattern": r"^-?\d{3,6}[A-Z]?$", "uppercase": True},
    "INSTALLED_ON": dict(_ROW_DATE_RULE),
    "TSN": dict(_NUMERIC_RULE),
    "CSN": dict(_NUMERIC_RULE),
    "REMARK": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_ATA_RE = re.compile(r"^\d{2}$")
_COMP_RE = re.compile(r"^-?\d{3,6}[A-Za-z]?$")
# Tolerant of real OCR/glyph noise seen directly in the sample: a digit
# substituted for a letter within the month or year token, or `.`/`~` used
# in place of a `-` separator.
_DATE_RE = re.compile(r"^\d{1,2}[-.][A-Za-z0-9]{3}[-.][A-Za-z0-9]{2,4}$")
_SHORT_NUM_RE = re.compile(r"^\d{1,3}$")
_THREE_DIGIT_RE = re.compile(r"^\d{3}$")
_SPLIT_GAP_MAX = 5.0  # pt; a missing-comma intra-number gap is ~1-2pt, a
                       # real inter-column gap in this format is ~40-60pt.

_MODEL_RE = re.compile(r"M[O0]?[DC]EL:\s*(\S+)\s+Date:\s*(\S+)", re.IGNORECASE)
_MANUFACTURE_RE = re.compile(
    r"Manufacture Date:\s*(\S+)\s+TAT\s*\(F\w*\):\s*([\d,\s]+?)(?=\s*(?:A/C|$))",
    re.IGNORECASE,
)
# MSN/TAC's separator sometimes renders as a stray middle-dot glyph (`·`)
# instead of `:` -- confirmed directly, not a real punctuation choice.
_MSN_TAC_RE = re.compile(
    r"A/?C\s+MSN[·:]\s*(\S+)\s+TAC[·:]\s*([\d,\s]+?)(?=\s*(?:'|$))",
    re.IGNORECASE,
)


def _normalize_thousands(raw: str) -> str:
    """Re-join a thousands group that a missing comma glyph split across
    whitespace (e.g. `<n> <nnn>` -> `<n>,<nnn>`); leaves an already-comma'd or
    otherwise-shaped value untouched."""
    s = raw.strip()
    if re.fullmatch(r"\d{1,3}(?:[,\s]\d{3})*", s):
        return re.sub(r"[,\s]+", ",", s)
    return s


def _parse_meta(first_page_text: str) -> dict:
    meta = {
        "AIRCRAFT_TYPE": "", "REPORT_DATE": "", "MANUFACTURE_DATE": "",
        "TAT_FH": "", "MSN": "", "TAC": "",
    }
    text = first_page_text or ""
    m = _MODEL_RE.search(text)
    if m:
        meta["AIRCRAFT_TYPE"] = m.group(1)
        meta["REPORT_DATE"] = m.group(2)
    m = _MANUFACTURE_RE.search(text)
    if m:
        meta["MANUFACTURE_DATE"] = m.group(1)
        meta["TAT_FH"] = _normalize_thousands(m.group(2))
    m = _MSN_TAC_RE.search(text)
    if m:
        meta["MSN"] = m.group(1)
        meta["TAC"] = _normalize_thousands(m.group(2))
    return meta


def _cluster_rows(words: list[dict]) -> list[list[dict]]:
    """Group words into visual rows by their `top` coordinate (~11-12pt row
    height in the real sample; a 2pt tolerance clusters same-line words
    without merging adjacent lines)."""
    if not words:
        return []
    tops = sorted(set(round(w["top"], 1) for w in words))
    clusters: list[list[float]] = []
    cur = [tops[0]]
    for t in tops[1:]:
        if t - cur[-1] <= 2.0:
            cur.append(t)
        else:
            clusters.append(cur)
            cur = [t]
    clusters.append(cur)

    rows = []
    for cl in clusters:
        lo, hi = min(cl) - 0.5, max(cl) + 0.5
        row_words = [w for w in words if lo <= w["top"] <= hi]
        if row_words:
            rows.append(sorted(row_words, key=lambda w: w["x0"]))
    return rows


def _take_number(row_words: list[dict], pos: int) -> tuple[str, int]:
    """Consume one numeric field starting at row_words[pos], re-joining a
    thousands group split by the missing-comma rendering defect (see module
    docstring) when the gap to the next token is tight enough to indicate
    it's the same number, not a distinct column."""
    val = row_words[pos]["text"]
    x1 = row_words[pos]["x1"]
    pos += 1
    if _SHORT_NUM_RE.match(val) and pos < len(row_words):
        nxt = row_words[pos]
        if _THREE_DIGIT_RE.match(nxt["text"]) and (nxt["x0"] - x1) < _SPLIT_GAP_MAX:
            val = val + "," + nxt["text"]
            pos += 1
    return val, pos


def _parse_data_row(row_words: list[dict]) -> dict | None:
    tokens = [w["text"] for w in row_words]
    if len(tokens) < 8:
        return None
    if not _ATA_RE.match(tokens[0]):
        return None
    if not _COMP_RE.match(tokens[1]):
        return None

    date_idx = None
    for i in range(len(tokens) - 1, 1, -1):
        if _DATE_RE.match(tokens[i]):
            date_idx = i
            break
    if date_idx is None or date_idx < 4 or date_idx > len(tokens) - 3:
        return None

    desc = " ".join(tokens[2:date_idx - 2])
    if not desc:
        return None

    pn = tokens[date_idx - 2]
    sn = tokens[date_idx - 1]
    date = tokens[date_idx]
    tsn, pos = _take_number(row_words, date_idx + 1)
    csn, pos = _take_number(row_words, pos)
    remark = " ".join(t["text"] for t in row_words[pos:])

    return {
        "ATA": tokens[0],
        "COMP": tokens[1],
        "DESCRIPTION": desc,
        "PART_NUMBER": pn,
        "SERIAL_NUMBER": sn,
        "INSTALLED_ON": date,
        "TSN": tsn,
        "CSN": csn,
        "REMARK": remark,
    }


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    meta: dict = {}

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            if page_num == 1:
                meta = _parse_meta(page.extract_text() or "")

            words = page.extract_words()
            for row_words in _cluster_rows(words):
                rec = _parse_data_row(row_words)
                if rec is None:
                    continue
                out = dict(meta)
                out.update(rec)
                out["_page"] = page_num
                records.append(out)

    return records
