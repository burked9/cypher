"""On-Condition Components Report -- paired "INSTALLATION DATA" / "CURRENT
DATA" OCCM status report, born-digital with a full text layer (confirmed
via a direct pdfplumber pass over every page of one real 33-page sample;
no OCR needed, extract() is synchronous).

Page 1 of the known sample is a cover/signature page only -- report title,
aircraft header block, and blank "Checked by" / "Approved by" signature
lines, but no data table at all. The real data table starts on page 2 and
its header block repeats verbatim at the top of every subsequent page::

    On-Condition Components Report <date>
    <reg> SN: <msn> MFGDate:<date> FH: <n> FC: <n>
    INSTALLATION DATA CURRENT DATA (<date>)
    ## ATA PN SN DESCRIPTION POS INST Date TAH TAC TSN CSN TSI CSI

extract() skips page 1 entirely and only parses page 2 onward. The header
metadata (REPORT_DATE, AIRCRAFT_REG, MSN, MFG_DATE, AIRCRAFT_FH,
AIRCRAFT_FC) is parsed once per page and stamped onto every row from that
page, keeping the last successfully-parsed value if a later page's header
line ever fails to match (confirmed identical across every page of the
sample, so this is a defensive carry-forward, not an expected code path).

Data rows carry a leading "#<n>" item-number token (ITEM_NO), then ATA (a
plain 2-digit chapter -- confirmed via `extract_words()`, e.g. an
airframe-systems chapter and a powerplant chapter both seen as ordinary
2-digit codes, no extended sub-chapter suffix in this file), PART_NUMBER,
SERIAL_NUMBER, a free-text DESCRIPTION that can run to several words,
POSITION (frequently blank), INSTALL_DATE (dot-separated DD.MM.YYYY,
occasionally blank), and up to six trailing numeric columns.

Periodically, a section-heading line interrupts the row sequence: a bare
2-digit ATA code followed by an all-caps section name and nothing else
(e.g. shaped like "<ata> <SECTION NAME>"), with no leading "#<n>" token and
no numeric columns. Confirmed directly across the whole sample: every
data row's own ATA already carries its own correct 2-digit chapter code,
so this heading is never needed to recover ATA itself -- but the section
name (a coarser sub-grouping unique to this format) has no other column to
live in. Per this project's established forward-fill pattern for this kind
of section-only heading, the heading's name is captured once and stamped
onto every following row as ATA_SECTION until the next heading line is
seen, and the heading line itself is not emitted as its own record.

Column geometry -- why word x-position bucketing, not token-count
splitting: DESCRIPTION can be one word or several, and POSITION and any of
the trailing numeric columns are routinely blank on a given row, so a
naive left-to-right token split would misalign every field after the
first gap. The seven leading fields (ITEM_NO / ATA / PART_NUMBER /
SERIAL_NUMBER / DESCRIPTION / POSITION / INSTALL_DATE) are left-aligned,
so they bucket cleanly by each word's own x0 against boundaries measured
from real data-row word positions (NOT the column-header row's own label
positions, which sit slightly right of the data -- confirmed directly).

The six trailing numeric columns (TAH_AT_INSTALL / TAC_AT_INSTALL / TSN /
CSN / TSI / CSI) are different: they are right-aligned within their own
column, so a value's x0 shifts left as its digit count grows while its x1
(right edge) stays essentially fixed regardless of width (confirmed
directly: a 1-digit "0" and a 6-digit value in the same column land at the
same x1, +/- a point, while their x0 values differ by tens of points).
Bucketing these six by x0 would therefore misclassify wider values into
the wrong column; bucketing by x1 against boundaries measured from real
data across the whole sample (not just one page) is what stays correct.
Each of these six is filled independently by its own bucket, so a row that
only reports two of the six (a common, legitimate shape -- e.g. only
TAH_AT_INSTALL/TAC_AT_INSTALL and TSI/CSI populated, TSN/CSN left blank)
just leaves the untouched buckets empty rather than shifting the values
that are present.

Soft-validation / "never guess a wrong split": every real numeric bucket
in the sample holds at most one token. If a bucket is ever seen holding
more than one token, or a non-numeric token, that shape is not guessed at
-- the entire raw numeric-region text for that row (every word to the
right of INSTALL_DATE, in left-to-right order) is captured verbatim into
STATUS_TRAIL instead, and all six named numeric columns are left blank for
that row, per this project's established convention (see e.g.
occm_variants/occm_component_data_install_current.py,
occm_variants/multi_basis_accumulated_occm.py).

Row validity: a genuine data row always carries a leading "#<n>" item
token and at least one of PART_NUMBER / SERIAL_NUMBER (confirmed on the
whole sample -- every real component line has one or both). Anything else
-- the repeating page header block, the column-header row itself, a
section-heading line (handled separately, see above), or the page's own
"Page <n> of <total>" footer -- is recognised and skipped rather than
emitted as a garbage record.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "On-Condition Components Report (Install / Current)"
SIGNATURES = [
    "INSTALLATION DATA CURRENT DATA (",
    "## ATA PN SN DESCRIPTION POS INST Date TAH TAC TSN CSN TSI CSI",
]

CANONICAL_COLUMNS = [
    "ITEM_NO",
    "ATA",
    "ATA_SECTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
    "POSITION",
    "INSTALL_DATE",
    "TAH_AT_INSTALL",
    "TAC_AT_INSTALL",
    "TSN",
    "CSN",
    "TSI",
    "CSI",
    # Ambiguous numeric-region text that can't be reliably split into the
    # six named columns above -- see module docstring.
    "STATUS_TRAIL",
    # Header metadata -- parsed once per page, stamped onto every row.
    "REPORT_DATE",
    "AIRCRAFT_REG",
    "MSN",
    "MFG_DATE",
    "AIRCRAFT_FH",
    "AIRCRAFT_FC",
]

_NUM_RULE = {"pattern": r"^\d+$", "int_range": (0, 300000), "allow_empty": True}
_DATE_RULE = {"pattern": r"^\d{2}\.\d{2}\.\d{4}$", "allow_empty": True}

_OVERRIDES = {
    "ITEM_NO": {"pattern": r"^\d+$", "allow_empty": True},
    # This file's own ATA chapters observed directly range from a low
    # single-digit-looking chapter (rendered as a 2-digit "01") up through
    # ordinary powerplant chapters -- outside the global rule's default
    # int_range, so it's disabled here rather than flagging legitimate
    # rows, per this project's convention (see e.g. amos.py, a305_a340_
    # occm.py, aircraft_rotables_report.py).
    "ATA": {"pattern": r"^\d{2}$", "int_range": None},
    "ATA_SECTION": {"pattern": r"^[A-Z0-9][A-Z0-9 &/\-.,']{0,60}$", "allow_empty": True},
    "POSITION": {
        # A leading "#" is a confirmed real shape (e.g. a bare position
        # like "#1" -- an item-number-style engine/unit suffix, not an
        # OCCM item-number token, confirmed directly against the real
        # sample), so it's allowed as the first character too, not just
        # mid-string.
        "pattern": r"^[A-Z0-9#][A-Z0-9#()./\-' ]{0,40}$",
        "uppercase": True,
        "allow_empty": True,
    },
    "INSTALL_DATE": _DATE_RULE,
    "TAH_AT_INSTALL": _NUM_RULE,
    "TAC_AT_INSTALL": _NUM_RULE,
    "TSN": _NUM_RULE,
    "CSN": _NUM_RULE,
    "TSI": _NUM_RULE,
    "CSI": _NUM_RULE,
    "STATUS_TRAIL": {"allow_empty": True},
    "DESCRIPTION": {"uppercase": True},
    "REPORT_DATE": _DATE_RULE,
    "AIRCRAFT_REG": {"pattern": r"^[A-Z0-9\-]{2,10}$", "uppercase": True, "allow_empty": True},
    "MSN": {"pattern": r"^\d{3,6}$", "allow_empty": True},
    "MFG_DATE": _DATE_RULE,
    "AIRCRAFT_FH": {"pattern": r"^\d{1,7}$", "allow_empty": True},
    "AIRCRAFT_FC": {"pattern": r"^\d{1,7}$", "allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# --- Column x-position anchors (left-aligned leading fields) --------------
# Measured directly off real data-row word coordinates (extract_words())
# across the whole sample -- NOT the column-header row's own label
# positions, which land noticeably right of the data (confirmed directly,
# same reasoning as occm_component_data_install_current.py).
_TEXT_COLS = [
    ("ITEM_NO", 21.1),
    ("ATA", 64.6),
    ("PART_NUMBER", 84.1),
    ("SERIAL_NUMBER", 178.6),
    ("DESCRIPTION", 259.6),
    ("POSITION", 443.7),
    ("INSTALL_DATE", 508.3),
]
# DESCRIPTION/POSITION need an explicit (non-midpoint) boundary: DESCRIPTION
# is free text that routinely runs long enough to overflow well past the
# naive midpoint between the two anchors (confirmed directly -- e.g. a
# trailing qualifier like "(<code>)" landing around x0 ~360), while genuine
# POSITION values cluster extremely tightly at their own anchor regardless
# of row (confirmed directly across the whole sample: x0 lands within
# essentially one point of 443.6-443.8 in the overwhelming majority of
# cases, versus scattered/rare x0 values anywhere from ~350 up to ~436 for
# overflowing DESCRIPTION words). The boundary is therefore set just ahead
# of that tight POSITION cluster (442.0) rather than at the midpoint.
_DESCRIPTION_POSITION_BOUNDARY = 442.0
# Same overflow shape one column later: POSITION occasionally carries a
# trailing qualifier word (e.g. a bay/zone-letter suffix) that lands past
# the naive midpoint between POSITION and INSTALL_DATE, while INSTALL_DATE
# itself clusters extremely tightly at its own anchor regardless of row
# (confirmed directly across the whole sample: x0 lands at essentially
# exactly 508.3 on effectively every row that has a date at all, versus a
# handful of scattered x0 values anywhere from ~470 up to ~486 for
# overflowing POSITION words). The boundary is set just ahead of that
# tight INSTALL_DATE cluster (500.0) rather than at the midpoint.
_POSITION_INSTALL_DATE_BOUNDARY = 500.0
# Everything at or beyond this x0 belongs to the six trailing numeric
# columns (bucketed by x1 instead -- see below); confirmed directly that
# no INSTALL_DATE token and no numeric-region token ever crosses this line
# anywhere in the sample (INSTALL_DATE always renders at x0=508.3, the
# left-most numeric-region token seen anywhere in the sample renders at
# x0 ~571).
_NUMERIC_REGION_X0 = 545.0

# --- Numeric column anchors (right-aligned -- bucketed by x1) -------------
# Measured directly off real data word x1 (right edge) across the whole
# sample, not just one page: each of the six columns clusters tightly
# around its own x1 regardless of how many digits a given value has
# (confirmed: e.g. a 1-digit "0" and a 6-digit value in the same column
# land within ~1pt of the same x1).
_NUMERIC_COLS = [
    ("TAH_AT_INSTALL", 593.0),
    ("TAC_AT_INSTALL", 639.0),
    ("TSN", 674.0),
    ("CSN", 708.0),
    ("TSI", 744.0),
    ("CSI", 781.0),
]


def _boundaries(anchors: list[tuple[str, float]]) -> list[tuple[float, float]]:
    xs = [a[1] for a in anchors]
    out = []
    for i in range(len(xs)):
        lo = float("-inf") if i == 0 else (xs[i - 1] + xs[i]) / 2
        hi = float("inf") if i == len(xs) - 1 else (xs[i] + xs[i + 1]) / 2
        out.append((lo, hi))
    return out


_TEXT_NAMES = [c[0] for c in _TEXT_COLS]
_TEXT_BOUNDS = _boundaries(_TEXT_COLS)
# Override the automatic midpoint between DESCRIPTION and POSITION -- see
# _DESCRIPTION_POSITION_BOUNDARY above.
_DESC_IDX = _TEXT_NAMES.index("DESCRIPTION")
_POS_IDX = _TEXT_NAMES.index("POSITION")
_DATE_IDX = _TEXT_NAMES.index("INSTALL_DATE")
_TEXT_BOUNDS[_DESC_IDX] = (_TEXT_BOUNDS[_DESC_IDX][0], _DESCRIPTION_POSITION_BOUNDARY)
_TEXT_BOUNDS[_POS_IDX] = (_DESCRIPTION_POSITION_BOUNDARY, _POSITION_INSTALL_DATE_BOUNDARY)
_TEXT_BOUNDS[_DATE_IDX] = (_POSITION_INSTALL_DATE_BOUNDARY, _TEXT_BOUNDS[_DATE_IDX][1])
_NUM_NAMES = [c[0] for c in _NUMERIC_COLS]
_NUM_BOUNDS = _boundaries(_NUMERIC_COLS)


def _bucket_text(x0: float) -> str:
    for name, (lo, hi) in zip(_TEXT_NAMES, _TEXT_BOUNDS):
        if lo <= x0 < hi:
            return name
    return _TEXT_NAMES[-1]


def _bucket_numeric(x1: float) -> str:
    for name, (lo, hi) in zip(_NUM_NAMES, _NUM_BOUNDS):
        if lo <= x1 < hi:
            return name
    return _NUM_NAMES[-1]


_HEADER_TITLE_RE = re.compile(
    r"^On-Condition Components Report\s+(?P<date>\d{2}\.\d{2}\.\d{4})\s*$"
)
_HEADER_META_RE = re.compile(
    r"^(?P<reg>\S+)\s+SN:\s*(?P<msn>\S+)\s+MFGDate:(?P<mfg>\S+)"
    r"\s+FH:\s*(?P<fh>\S+)\s+FC:\s*(?P<fc>\S+)\s*$"
)
_HEADER_MARKERS = ("INSTALLATION DATA", "## ATA")
_FOOTER_RE = re.compile(r"^Page\s+\d+\s+of\s+\d+\s*$")
_ITEM_RE = re.compile(r"^#(\d+)$")
_SECTION_RE = re.compile(r"^(?P<ata>\d{2})\s+(?P<name>[A-Z][A-Z0-9 &/\-.,']*)$")
_DIGIT_RE = re.compile(r"^\d+$")


def _parse_header_lines(lines: list[str]) -> dict:
    meta: dict = {}
    for line in lines:
        l = line.strip()
        m1 = _HEADER_TITLE_RE.match(l)
        if m1:
            meta["REPORT_DATE"] = m1.group("date")
            continue
        m2 = _HEADER_META_RE.match(l)
        if m2:
            meta["AIRCRAFT_REG"] = m2.group("reg")
            meta["MSN"] = m2.group("msn")
            meta["MFG_DATE"] = m2.group("mfg")
            meta["AIRCRAFT_FH"] = m2.group("fh")
            meta["AIRCRAFT_FC"] = m2.group("fc")
    return meta


def _is_skippable_line(joined: str) -> bool:
    if _HEADER_TITLE_RE.match(joined) or _HEADER_META_RE.match(joined):
        return True
    if any(marker in joined for marker in _HEADER_MARKERS):
        return True
    if _FOOTER_RE.match(joined):
        return True
    return False


def _cluster_rows(words: list[dict]) -> list[list[dict]]:
    """Group words into visual rows by their `top` coordinate (2pt
    tolerance -- enough to merge same-line jitter without merging adjacent
    printed lines)."""
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

    row_groups = []
    for cl in clusters:
        lo, hi = min(cl) - 0.5, max(cl) + 0.5
        row_words = [w for w in words if lo <= w["top"] <= hi]
        if row_words:
            row_groups.append(row_words)
    return row_groups


def _parse_section_heading(row_words: list[dict]) -> tuple[str, str] | None:
    """If this row is a bare "<ata> <SECTION NAME>" heading line (no
    leading "#<n>" item token, no numeric columns), return (ata, name);
    otherwise None."""
    row_words = sorted(row_words, key=lambda w: w["x0"])
    if not row_words:
        return None
    if _ITEM_RE.match(row_words[0]["text"]):
        return None
    joined = " ".join(w["text"] for w in row_words)
    m = _SECTION_RE.match(joined)
    if not m:
        return None
    return m.group("ata"), m.group("name")


def _parse_row(row_words: list[dict], page_num: int, header_meta: dict,
                section: dict) -> dict | None:
    row_words = sorted(row_words, key=lambda w: w["x0"])
    joined = " ".join(w["text"] for w in row_words)
    if _is_skippable_line(joined):
        return None
    if not row_words or not _ITEM_RE.match(row_words[0]["text"]):
        # Not a data row: either a section heading (handled by the caller
        # before this function runs) or unrecognised noise -- skip either
        # way rather than emit a garbage record.
        return None

    text_words = [w for w in row_words if w["x0"] < _NUMERIC_REGION_X0]
    numeric_words = [w for w in row_words if w["x0"] >= _NUMERIC_REGION_X0]

    buckets: dict[str, list[str]] = {}
    for w in text_words:
        col = _bucket_text(w["x0"])
        buckets.setdefault(col, []).append(w["text"])

    rec: dict = {c: "" for c in CANONICAL_COLUMNS}
    rec["ITEM_NO"] = _ITEM_RE.match(buckets.get("ITEM_NO", [""])[0]).group(1)
    for name in ("ATA", "PART_NUMBER", "SERIAL_NUMBER", "DESCRIPTION",
                 "POSITION", "INSTALL_DATE"):
        rec[name] = " ".join(buckets.get(name, []))

    num_buckets: dict[str, list[str]] = {}
    for w in numeric_words:
        col = _bucket_numeric(w["x1"])
        num_buckets.setdefault(col, []).append(w["text"])

    ambiguous = False
    for name, _anchor in _NUMERIC_COLS:
        toks = num_buckets.get(name, [])
        if not toks:
            rec[name] = ""
        elif len(toks) == 1 and _DIGIT_RE.match(toks[0]):
            rec[name] = toks[0]
        else:
            ambiguous = True

    if ambiguous:
        region_words = sorted(numeric_words, key=lambda w: w["x0"])
        rec["STATUS_TRAIL"] = " ".join(w["text"] for w in region_words)
        for name, _anchor in _NUMERIC_COLS:
            rec[name] = ""
    else:
        rec["STATUS_TRAIL"] = ""

    pn, sn = rec["PART_NUMBER"], rec["SERIAL_NUMBER"]
    if not pn and not sn:
        return None

    rec["ATA_SECTION"] = section.get("name", "")
    rec.update(header_meta)
    rec["_page"] = page_num
    return rec


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    header_meta: dict = {
        "REPORT_DATE": "", "AIRCRAFT_REG": "", "MSN": "",
        "MFG_DATE": "", "AIRCRAFT_FH": "", "AIRCRAFT_FC": "",
    }
    section: dict = {"ata": "", "name": ""}
    with pdfplumber.open(pdf_path) as pdf:
        # Page 1 is a cover/signature page only (report title, header
        # block, blank "Checked by"/"Approved by" lines) -- confirmed
        # directly, no data table on it. The real data table starts on
        # page 2, so page 1 is skipped outright.
        for page_num, page in enumerate(pdf.pages, start=1):
            if page_num == 1:
                continue

            text = page.extract_text() or ""
            page_meta = _parse_header_lines(text.splitlines()[:2])
            for k, v in page_meta.items():
                if v:
                    header_meta[k] = v

            words = page.extract_words()
            if not words:
                continue
            for row_words in _cluster_rows(words):
                heading = _parse_section_heading(row_words)
                if heading is not None:
                    section = {"ata": heading[0], "name": heading[1]}
                    continue
                rec = _parse_row(row_words, page_num, header_meta, section)
                if rec is not None:
                    records.append(rec)
    return records
