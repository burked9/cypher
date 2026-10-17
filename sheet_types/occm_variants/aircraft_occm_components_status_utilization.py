r"""Aircraft OC/CM Components Status (Utilization) -- born-digital, full text
layer, coordinate-bucketed columns. Confirmed on one real sample file (29
pages, clean pdfplumber text layer; no OCR needed; extract() is synchronous).

Header block (repeats verbatim at the top of every data page)::

    AIRCRAFT OC/CM COMPONENTS STATUS
    <type>
    Actual FH <fh> MSN <msn>
    Actual FC <fc> Registration <reg>
    Date <date> Prod No: <prod_no>

followed by a two-line column header and then one row per component.

Page 1 and last page are blank (no text) on the known sample -- skipped
automatically (fewer than 50 chars).

Column layout (header lines)::

    Ata  Part Number  Serial Number  Description  Position
                                               Installed        Utilization
                                               Date  A/C Hours  A/C Cycles  Hours  Cycles

The "Installed" / "Utilization" sub-header labels two groups of trailing
numeric columns: "Installed" covers the aircraft's own hours and cycles at
the time of that row's installation, "Utilization" covers the component's
own hours and cycles since installation. Confirmed arithmetically on the
real sample: for a row installed mid-life, header Actual FH minus that
row's own HOURS_AT_INSTALL equals its own HOURS_SINCE_INSTALL (and
likewise for cycles).

Column geometry (x0 anchors, measured directly off real data-row words
across multiple pages -- stable throughout, every page renders the same
layout at the same offsets):

    ATA(57.7)  PART_NUMBER(85-137)  SERIAL_NUMBER(192-290)
    DESCRIPTION(291-418)  POSITION(477-500)  INSTALL_DATE(528.1)
    HOURS_AT_INSTALL(593-608)  CYCLES_AT_INSTALL(657-673)
    HOURS_SINCE_INSTALL(708-715)  CYCLES_SINCE_INSTALL(757-763)

Word-position bucketing: each data word is assigned to its column via x0
midpoint boundaries (halfway between adjacent columns' confirmed x0
ranges). A ~0.2pt baseline offset on some rows (confirmed: comma-formatted
numbers in the HOURS_AT_INSTALL / CYCLES_AT_INSTALL columns render at top
+0.2 vs the rest of the row's words) is handled by the _TOP_TOLERANCE in
row clustering.

POSITION is genuinely blank on some rows (confirmed directly).

Header metadata (AIRCRAFT_TYPE, ACTUAL_FH, MSN, ACTUAL_FC, AIRCRAFT_REG,
REPORT_DATE, PROD_NO) is parsed once from page 1's header block and
stamped onto every row.
"""
from __future__ import annotations

import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "Aircraft OC/CM Components Status (Utilization)"

SIGNATURES = [
    # The report title. Checked directly (grep across every SIGNATURES list
    # in sheet_types/{occm,ht,llp}.py and every existing occm_variants/
    # ht_variants/llp_variants file): the phrase appears only in
    # aircraft_occm_components_status_scanned.py, whose own SIGNATURES list
    # is deliberately empty (that module has no text layer and is reached
    # only via ocr_detect), so no collision on the pdfplumber text-match
    # path.
    "AIRCRAFT OC/CM COMPONENTS STATUS",
]

CANONICAL_COLUMNS = [
    "ATA",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
    "POSITION",
    "INSTALL_DATE",
    "HOURS_AT_INSTALL",
    "CYCLES_AT_INSTALL",
    "HOURS_SINCE_INSTALL",
    "CYCLES_SINCE_INSTALL",
    "STATUS_TRAIL",
    # Header metadata -- parsed once, stamped onto every row.
    "AIRCRAFT_TYPE",
    "ACTUAL_FH",
    "MSN",
    "ACTUAL_FC",
    "AIRCRAFT_REG",
    "REPORT_DATE",
    "PROD_NO",
]

_NUM_RULE = {"pattern": r"^[\d,]+(\.\d+)?$", "allow_empty": True}
_OVERRIDES = {
    "POSITION": {
        "pattern": r"^[A-Z0-9 /]{0,15}$",
        "uppercase": True,
        "allow_empty": True,
    },
    "INSTALL_DATE": {
        "pattern": r"^\d{4}-\d{2}-\d{2}$",
        "allow_empty": True,
    },
    "HOURS_AT_INSTALL": _NUM_RULE,
    "CYCLES_AT_INSTALL": _NUM_RULE,
    "HOURS_SINCE_INSTALL": _NUM_RULE,
    "CYCLES_SINCE_INSTALL": _NUM_RULE,
    "STATUS_TRAIL": {"allow_empty": True},
    "AIRCRAFT_TYPE": {
        "pattern": r"^[A-Z0-9][A-Z0-9\-]{1,10}$",
        "uppercase": True,
        "allow_empty": True,
    },
    "ACTUAL_FH": {"allow_empty": True},
    "MSN": {"pattern": r"^\d{3,6}$", "allow_empty": True},
    "ACTUAL_FC": {"allow_empty": True},
    "AIRCRAFT_REG": {
        "pattern": r"^[A-Z0-9]{1,3}-[A-Z0-9]{2,6}$",
        "uppercase": True,
        "allow_empty": True,
    },
    "REPORT_DATE": {
        "pattern": r"^\d{4}-\d{2}-\d{2}$",
        "allow_empty": True,
    },
    "PROD_NO": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# ---------------------------------------------------------------------------
# Column x-position boundaries -- explicit upper edges, measured from the
# confirmed gap between adjacent columns' real data-word x0 ranges across
# all 29 pages of the real sample.  Midpoints would work for evenly-spaced
# columns, but the SERIAL_NUMBER / DESCRIPTION gap is wide (~43pt) and
# asymmetric, so explicit edges are safer.
#
# Confirmed real x0 ranges (all pages, data rows only):
#   ATA:                 57.7 (always)
#   PART_NUMBER:         85 - 137
#   SERIAL_NUMBER:       192 - 228  (rightmost x1 = 234)
#   DESCRIPTION:         277 - 418  (gap to SN right edge = 43pt)
#   POSITION:            477 - 500
#   INSTALL_DATE:        528 (always)
#   HOURS_AT_INSTALL:    593 - 608
#   CYCLES_AT_INSTALL:   657 - 673
#   HOURS_SINCE_INSTALL: 708 - 715
#   CYCLES_SINCE_INSTALL:757 - 763
# ---------------------------------------------------------------------------
_COL_BOUNDS: list[tuple[str, float]] = [
    # (column_name, upper_x0_boundary)
    # A word with x0 < this value (and >= the previous boundary) is assigned
    # to this column.
    ("ATA",                   80.0),
    ("PART_NUMBER",          180.0),   # gap 137 .. 192
    ("SERIAL_NUMBER",        255.0),   # gap 234(x1) .. 277(x0)
    ("DESCRIPTION",          470.0),   # gap 418 .. 477
    ("POSITION",             515.0),   # gap 500 .. 528
    ("INSTALL_DATE",         585.0),   # gap 569(x1) .. 593
    ("HOURS_AT_INSTALL",     645.0),   # gap 628(x1) .. 657
    ("CYCLES_AT_INSTALL",    700.0),   # gap 692(x1) .. 708
    ("HOURS_SINCE_INSTALL",  750.0),   # gap 740(x1) .. 757
    ("CYCLES_SINCE_INSTALL", 1e6),     # everything remaining
]


def _bucket_for(x0: float) -> str:
    for name, upper in _COL_BOUNDS:
        if x0 < upper:
            return name
    return _COL_BOUNDS[-1][0]


_ATA_RE = re.compile(r"^\d{2}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# --- Row clustering -------------------------------------------------------
_TOP_TOLERANCE = 2.0


def _cluster_rows(words: list[dict]) -> list[list[dict]]:
    """Group words into visual line-clusters by their ``top`` coordinate,
    chain-merging consecutive tops within ``_TOP_TOLERANCE``.  The confirmed
    ~0.2pt baseline offset on comma-formatted numbers is well within this
    tolerance."""
    if not words:
        return []
    tops = sorted(set(round(w["top"], 1) for w in words))
    clusters: list[list[float]] = []
    cur = [tops[0]]
    for t in tops[1:]:
        if t - cur[-1] <= _TOP_TOLERANCE:
            cur.append(t)
        else:
            clusters.append(cur)
            cur = [t]
    clusters.append(cur)

    row_groups: list[list[dict]] = []
    for cl in clusters:
        lo, hi = min(cl) - 0.5, max(cl) + 0.5
        row_words = [w for w in words if lo <= w["top"] <= hi]
        if row_words:
            row_groups.append(sorted(row_words, key=lambda w: w["x0"]))
    return row_groups


# --- Header metadata -------------------------------------------------------
_TITLE_RE = re.compile(
    r"AIRCRAFT\s+OC/CM\s+COMPONENTS\s+STATUS",
    re.IGNORECASE,
)
_FH_RE = re.compile(r"Actual\s+FH\s+([\d,]+(?:\.\d+)?)")
_FC_RE = re.compile(r"Actual\s+FC\s+([\d,]+(?:\.\d+)?)")
_MSN_RE = re.compile(r"MSN\s+(\d+)")
_REG_RE = re.compile(r"Registration\s+(\S+)")
_DATE_HDR_RE = re.compile(r"Date\s+(\d{4}-\d{2}-\d{2})")
_PROD_RE = re.compile(r"Prod\s+No:\s*(\S+)")


def _parse_header(text: str) -> dict:
    """Parse the header metadata block from a page's own extract_text().
    Returns only the keys it successfully found; callers merge onto a
    running dict so a blank page does not erase earlier values."""
    meta: dict = {}
    m = _FH_RE.search(text)
    if m:
        meta["ACTUAL_FH"] = m.group(1)
    m = _FC_RE.search(text)
    if m:
        meta["ACTUAL_FC"] = m.group(1)
    m = _MSN_RE.search(text)
    if m:
        meta["MSN"] = m.group(1)
    m = _REG_RE.search(text)
    if m:
        meta["AIRCRAFT_REG"] = m.group(1)
    m = _DATE_HDR_RE.search(text)
    if m:
        meta["REPORT_DATE"] = m.group(1)
    m = _PROD_RE.search(text)
    if m:
        meta["PROD_NO"] = m.group(1)
    # Aircraft type sits alone on the line after the title
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if _TITLE_RE.search(line):
            if i + 1 < len(lines):
                candidate = lines[i + 1].strip()
                if re.match(r"^[A-Z0-9][A-Z0-9\-]{1,10}$", candidate):
                    meta["AIRCRAFT_TYPE"] = candidate
            break
    return meta


_HEADER_META_KEYS = (
    "AIRCRAFT_TYPE", "ACTUAL_FH", "MSN", "ACTUAL_FC",
    "AIRCRAFT_REG", "REPORT_DATE", "PROD_NO",
)

# Markers that identify the repeating header block and column-header lines,
# so they are excluded from data-row parsing.
_HEADER_MARKERS = (
    "AIRCRAFT OC/CM",
    "Actual FH",
    "Actual FC",
    "Prod No:",
    "Installed",
    "Utilization",
    "Part Number",
    "Serial Number",
    "Description",
    "A/C Hours",
    "A/C Cycles",
)


def _is_header_line(tokens: list[dict]) -> bool:
    joined = " ".join(w["text"] for w in tokens)
    return any(marker in joined for marker in _HEADER_MARKERS)


def _is_data_row(tokens: list[dict]) -> bool:
    """A data row always starts with a 2-digit ATA code as its leftmost
    word (confirmed stable across all pages of the real sample)."""
    if not tokens:
        return False
    return bool(_ATA_RE.match(tokens[0]["text"]))


def _build_record(tokens: list[dict]) -> dict:
    """Bucket each word into its column by x-position and assemble a record."""
    rec: dict = {c: "" for c in CANONICAL_COLUMNS}
    buckets: dict[str, list[str]] = {}
    for w in tokens:
        col = _bucket_for(w["x0"])
        buckets.setdefault(col, []).append(w["text"])

    rec["ATA"] = " ".join(buckets.get("ATA", []))
    rec["PART_NUMBER"] = " ".join(buckets.get("PART_NUMBER", []))
    rec["SERIAL_NUMBER"] = " ".join(buckets.get("SERIAL_NUMBER", []))
    rec["DESCRIPTION"] = " ".join(buckets.get("DESCRIPTION", []))
    rec["POSITION"] = " ".join(buckets.get("POSITION", []))
    rec["INSTALL_DATE"] = " ".join(buckets.get("INSTALL_DATE", []))
    rec["HOURS_AT_INSTALL"] = " ".join(buckets.get("HOURS_AT_INSTALL", []))
    rec["CYCLES_AT_INSTALL"] = " ".join(buckets.get("CYCLES_AT_INSTALL", []))
    rec["HOURS_SINCE_INSTALL"] = " ".join(buckets.get("HOURS_SINCE_INSTALL", []))
    rec["CYCLES_SINCE_INSTALL"] = " ".join(buckets.get("CYCLES_SINCE_INSTALL", []))
    rec["STATUS_TRAIL"] = ""
    return rec


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    header_meta: dict = {k: "" for k in _HEADER_META_KEYS}
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if len(text) < 50:
                continue

            page_meta = _parse_header(text)
            for k, v in page_meta.items():
                if v:
                    header_meta[k] = v

            words = page.extract_words()
            if not words:
                continue

            for row_words in _cluster_rows(words):
                if _is_header_line(row_words):
                    continue
                if not _is_data_row(row_words):
                    continue
                rec = _build_record(row_words)
                if not rec["PART_NUMBER"] and not rec["SERIAL_NUMBER"]:
                    continue
                for key in _HEADER_META_KEYS:
                    rec[key] = header_meta.get(key, "")
                rec["_page"] = page_num
                records.append(rec)
    return records
