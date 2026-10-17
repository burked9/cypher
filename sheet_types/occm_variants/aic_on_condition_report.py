r"""AIC On Condition Report -- born-digital, full text layer, word-position
bucketed columns.  The column layout (x-positions) shifts between pages,
so column boundaries are re-derived from each page's own header row.

Header block (repeats at the top of every page)::

    AIC ON CONDITION REPORT
    [ AIC NATATA  AICSIN: <sin>  TypelSeries: <type>  AIC TT: <tt>
      AICTC: <tc>  TimeAsOf. <date>  |
                                  Scheduled           Actuals
    aATA  Description  PIN  SIN  Category  Position  b  Hours Cycles Days
                                                        [Date] Hours Cyc Days

The ``a`` before ``ATA`` and the standalone ``b`` marker are layout artefacts
and are stripped during header detection.

Data rows carry:
    ATA  DESCRIPTION  PART_NUMBER  SERIAL_NUMBER  CATEGORY  [POSITION]
    SCHED_HOURS  SCHED_CYCLES  SCHED_DAYS
    [ACTUAL_DATE]  ACTUAL_HOURS  ACTUAL_CYCLES  ACTUAL_DAYS

CATEGORY is one of TSN / TSO / OHI (and OCR variants TsO / OH! etc.).
POSITION is present on most but not all rows.  The ``Date`` column under
Actuals is declared in some pages' headers but almost never populated in
the data rows -- it is captured when present and left blank otherwise.

Numeric values occasionally carry trailing punctuation artefacts (commas,
periods) from the text layer -- these are stripped.  The token ``oO`` or
``Oo`` is treated as ``0``.
"""
from __future__ import annotations

import re
from typing import Any

import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "AIC On Condition Report"
SIGNATURES = [
    "AIC ON CONDITION REPORT",
]

CANONICAL_COLUMNS = [
    "ATA",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "CATEGORY",
    "POSITION",
    "SCHED_HOURS",
    "SCHED_CYCLES",
    "SCHED_DAYS",
    "ACTUAL_DATE",
    "ACTUAL_HOURS",
    "ACTUAL_CYCLES",
    "ACTUAL_DAYS",
    # Header metadata -- parsed once, stamped onto every row.
    "SIN",
    "TYPE_SERIES",
    "AIC_TT",
    "AIC_TC",
    "TIME_AS_OF",
]

_NUM_RULE: dict[str, Any] = {
    "pattern": r"^\d+$",
    "int_range": (0, 500000),
    "allow_empty": True,
}
_OVERRIDES: dict[str, dict[str, Any]] = {
    "CATEGORY": {
        "pattern": r"^(TSN|TSO|OHI|OH)$",
        "uppercase": True,
    },
    "POSITION": {"allow_empty": True},
    "SCHED_HOURS": _NUM_RULE,
    "SCHED_CYCLES": _NUM_RULE,
    "SCHED_DAYS": _NUM_RULE,
    "ACTUAL_DATE": {"allow_empty": True},
    "ACTUAL_HOURS": _NUM_RULE,
    "ACTUAL_CYCLES": _NUM_RULE,
    "ACTUAL_DAYS": _NUM_RULE,
    "SIN": {"pattern": r"^\d+$", "allow_empty": True},
    "TYPE_SERIES": {"allow_empty": True},
    "AIC_TT": {"allow_empty": True},
    "AIC_TC": {"pattern": r"^\d+$", "allow_empty": True},
    "TIME_AS_OF": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# ---------------------------------------------------------------------------
# Header metadata regex
# ---------------------------------------------------------------------------
_SIN_RE = re.compile(r"(?:AIC\s*SIN|ACSIN)[:\s]+(\d+)", re.IGNORECASE)
_TYPE_RE = re.compile(r"Type[lI/|]Series[:\s]+(\S+)", re.IGNORECASE)
_TT_RE = re.compile(r"AIC\s*TT[:\s]+([\d:]+)", re.IGNORECASE)
_TC_RE = re.compile(r"AIC\s*TC[:\s]+(\d+)", re.IGNORECASE)
_TIME_RE = re.compile(r"TimeAsOf[.:\s]+([\d/]+)", re.IGNORECASE)

_ATA_RE = re.compile(r"^\d{2}-?\d{0,2}-?\d?$")


def _parse_header_meta(text: str) -> dict[str, str]:
    """Extract aircraft-level metadata from the page header text."""
    meta: dict[str, str] = {}
    m = _SIN_RE.search(text)
    if m:
        meta["SIN"] = m.group(1)
    m = _TYPE_RE.search(text)
    if m:
        meta["TYPE_SERIES"] = m.group(1)
    m = _TT_RE.search(text)
    if m:
        meta["AIC_TT"] = m.group(1)
    m = _TC_RE.search(text)
    if m:
        meta["AIC_TC"] = m.group(1)
    m = _TIME_RE.search(text)
    if m:
        meta["TIME_AS_OF"] = m.group(1)
    return meta


# ---------------------------------------------------------------------------
# Per-page column detection
# ---------------------------------------------------------------------------

# Reference column x0 positions, measured on page 1 of the sample file.
# The layout shifts horizontally between pages but column spacing is fixed.
# We detect each page's shift from a stable anchor ("Category") and apply it.
_REF_CATEGORY_X0 = 350.9  # anchor: "Category" header word on reference page

_REF_COLUMNS: list[tuple[str, float]] = [
    ("ATA", 55.7),
    ("DESCRIPTION", 98.9),
    ("PART_NUMBER", 215.5),
    ("SERIAL_NUMBER", 288.0),
    ("CATEGORY", 350.9),
    ("POSITION", 391.7),
    ("SCHED_HOURS", 456.5),
    ("SCHED_CYCLES", 487.7),
    ("SCHED_DAYS", 527.5),
    ("ACTUAL_HOURS", 596.6),
    ("ACTUAL_CYCLES", 630.2),
    ("ACTUAL_DAYS", 663.8),
]


def _detect_columns(words: list[dict]) -> tuple[list[tuple[str, float]], float] | None:
    """Locate the column header row and return shifted column positions.

    Returns (col_positions, header_top) or None.  Instead of parsing every
    garbled header token, we locate the "Category" header word (the most
    reliably rendered anchor) and compute the horizontal shift relative to
    the reference page, then apply that shift to all reference columns.
    """
    by_top: dict[float, list[dict]] = {}
    for w in words:
        t = round(w["top"], 0)
        by_top.setdefault(t, []).append(w)

    # Find the header row: look for "Category" (the most stable token).
    # Falls back to fuzzy match when the text layer garbles it (e.g.
    # "C011egory" or "Calegory").
    _CAT_RE = re.compile(r"^c.{3,6}gory$", re.IGNORECASE)
    for top in sorted(by_top):
        if top < 80 or top > 130:
            continue
        row = by_top[top]
        for w in row:
            clean = w["text"].lower().rstrip(".,=:")
            if clean == "category" or _CAT_RE.match(clean):
                shift = w["x0"] - _REF_CATEGORY_X0
                cols = [(name, x0 + shift) for name, x0 in _REF_COLUMNS]
                return cols, top

    return None


def _build_boundaries(
    cols: list[tuple[str, float]],
) -> list[tuple[str, float, float]]:
    """Return (col_name, lo, hi) for each column, using midpoints."""
    result: list[tuple[str, float, float]] = []
    xs = [x for _, x in cols]
    names = [n for n, _ in cols]
    for i in range(len(xs)):
        lo = float("-inf") if i == 0 else (xs[i - 1] + xs[i]) / 2
        hi = float("inf") if i == len(xs) - 1 else (xs[i] + xs[i + 1]) / 2
        result.append((names[i], lo, hi))
    return result


def _bucket_for(
    x0: float, boundaries: list[tuple[str, float, float]]
) -> str:
    for name, lo, hi in boundaries:
        if lo <= x0 < hi:
            return name
    return boundaries[-1][0]


# ---------------------------------------------------------------------------
# Row clustering and parsing
# ---------------------------------------------------------------------------

def _cluster_rows(
    words: list[dict], header_top: float
) -> list[list[dict]]:
    """Group words below the header into visual rows by top coordinate."""
    data_words = [w for w in words if w["top"] > header_top + 2]
    if not data_words:
        return []

    tops = sorted(set(round(w["top"], 1) for w in data_words))
    clusters: list[list[float]] = []
    cur = [tops[0]]
    for t in tops[1:]:
        if t - cur[-1] <= 2.5:
            cur.append(t)
        else:
            clusters.append(cur)
            cur = [t]
    clusters.append(cur)

    row_groups: list[list[dict]] = []
    for cl in clusters:
        lo, hi = min(cl) - 0.5, max(cl) + 0.5
        rw = [w for w in data_words if lo <= w["top"] <= hi]
        if rw:
            row_groups.append(sorted(rw, key=lambda w: w["x0"]))
    return row_groups


def _clean_num(val: str) -> str:
    """Strip trailing punctuation artefacts and normalise OCR zeros."""
    val = val.strip().rstrip(",.=")
    if val.lower() in ("oo", "o0", "0o"):
        return "0"
    # Remove any non-digit chars that are clearly artefacts
    if val and not val[0].isdigit() and len(val) > 1:
        val = val.lstrip("'\"")
    return val


_NUMERIC_TRIPLETS = [
    ("SCHED_HOURS", "SCHED_CYCLES", "SCHED_DAYS"),
    ("ACTUAL_HOURS", "ACTUAL_CYCLES", "ACTUAL_DAYS"),
]


def _split_merged_word(
    word: dict,
    boundaries: list[tuple[str, float, float]],
    page_chars: list[dict],
) -> dict[str, str]:
    """Split a single word that spans multiple column boundaries using its
    constituent chars.  Returns {col_name: text} for each column the word
    spans."""
    w_top, w_x0, w_x1 = word["top"], word["x0"], word.get("x1", word["x0"] + 50)
    # Find chars belonging to this word (same top, within x-range)
    wchars = [
        c for c in page_chars
        if abs(c["top"] - w_top) < 2.5 and c["x0"] >= w_x0 - 0.5 and c["x0"] <= w_x1 + 0.5
    ]
    wchars.sort(key=lambda c: c["x0"])

    col_texts: dict[str, list[str]] = {}
    for c in wchars:
        col = _bucket_for(c["x0"], boundaries)
        col_texts.setdefault(col, []).append(c["text"])

    return {col: "".join(chars) for col, chars in col_texts.items()}


def _parse_row(
    row_words: list[dict],
    boundaries: list[tuple[str, float, float]],
    page_chars: list[dict],
) -> dict | None:
    """Parse a single visual row into a record dict, or None if not a data row."""
    buckets: dict[str, list[str]] = {}
    # Track words per column for potential char-level re-splitting
    word_objs: dict[str, list[dict]] = {}
    for w in row_words:
        col = _bucket_for(w["x0"], boundaries)
        buckets.setdefault(col, []).append(w["text"])
        word_objs.setdefault(col, []).append(w)

    ata_raw = " ".join(buckets.get("ATA", [])).strip()
    # ATA is sometimes printed only on the first row of a section; later
    # rows on the same or following pages may lack it entirely.  Accept
    # rows without ATA (caller forward-fills from the previous row).
    if ata_raw and not _ATA_RE.match(ata_raw):
        return None

    rec: dict[str, str] = {c: "" for c in CANONICAL_COLUMNS}
    rec["ATA"] = ata_raw
    rec["DESCRIPTION"] = " ".join(buckets.get("DESCRIPTION", [])).strip()
    rec["PART_NUMBER"] = " ".join(buckets.get("PART_NUMBER", [])).strip()
    rec["SERIAL_NUMBER"] = " ".join(buckets.get("SERIAL_NUMBER", [])).strip()

    cat_raw = " ".join(buckets.get("CATEGORY", [])).strip().upper()
    # Normalise common text-layer artefacts and OCR variants
    cat_raw = cat_raw.lstrip("=«'").rstrip(".,")
    if cat_raw in ("TSO", "TS0", "T$0", "SO"):
        cat_raw = "TSO"
    elif cat_raw in ("TSN",):
        pass
    elif cat_raw.startswith("OH"):
        cat_raw = "OHI"
    elif cat_raw.startswith("TTS"):
        # Doubled-character corruption: "TTSSNN" -> "TSN", "TTSSOO" -> "TSO"
        collapsed = "".join(
            cat_raw[i] for i in range(0, len(cat_raw), 2)
            if i < len(cat_raw)
        )
        if collapsed in ("TSN", "TSO", "OHI"):
            cat_raw = collapsed
    rec["CATEGORY"] = cat_raw

    rec["POSITION"] = " ".join(buckets.get("POSITION", [])).strip()

    # Numeric columns
    for col in (
        "SCHED_HOURS", "SCHED_CYCLES", "SCHED_DAYS",
        "ACTUAL_DATE", "ACTUAL_HOURS", "ACTUAL_CYCLES", "ACTUAL_DAYS",
    ):
        raw = " ".join(buckets.get(col, [])).strip()
        if col == "ACTUAL_DATE":
            rec[col] = raw
        else:
            rec[col] = _clean_num(raw)

    # Fix merged numeric values: when a word in one numeric column's
    # bucket actually spans into the next column (e.g. "4382-2113" is
    # hours+cycles merged), split it using char positions.
    for hours_col, cycles_col, days_col in _NUMERIC_TRIPLETS:
        h_val = rec[hours_col]
        c_val = rec[cycles_col]
        # Case 1: hours has a separator-merged value and cycles is empty
        if h_val and not c_val:
            for sep in ("-", "="):
                if sep in h_val:
                    parts = h_val.split(sep, 1)
                    if parts[0].isdigit() and parts[1].isdigit():
                        rec[hours_col] = parts[0]
                        rec[cycles_col] = parts[1]
                        break
            if rec[cycles_col]:
                continue
        # Case 2: hours looks like concatenated digits and cycles is empty
        # Use char-level splitting to separate
        if h_val and not c_val and len(h_val) > 5 and h_val.isdigit():
            h_words = word_objs.get(hours_col, [])
            if h_words:
                split = _split_merged_word(h_words[0], boundaries, page_chars)
                new_h = _clean_num(split.get(hours_col, ""))
                new_c = _clean_num(split.get(cycles_col, ""))
                if new_h and new_c:
                    rec[hours_col] = new_h
                    rec[cycles_col] = new_c

    # Basic validity: a real component row must have a recognised category
    # and at least one of part number or serial number.
    if rec["CATEGORY"] not in ("TSN", "TSO", "OHI", "TSR", "OH"):
        return None
    if not rec["PART_NUMBER"] and not rec["SERIAL_NUMBER"]:
        return None

    return rec


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    header_meta: dict[str, str] = {
        "SIN": "",
        "TYPE_SERIES": "",
        "AIC_TT": "",
        "AIC_TC": "",
        "TIME_AS_OF": "",
    }
    last_ata = ""

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ""
            page_meta = _parse_header_meta(text)
            for k, v in page_meta.items():
                if v:
                    header_meta[k] = v

            words = page.extract_words()
            if not words:
                continue

            detection = _detect_columns(words)
            if detection is None:
                continue

            cols, header_top = detection
            boundaries = _build_boundaries(cols)

            page_chars = page.chars

            row_groups = _cluster_rows(words, header_top)
            for rw in row_groups:
                rec = _parse_row(rw, boundaries, page_chars)
                if rec is None:
                    continue
                # Forward-fill ATA from previous row when missing
                if rec["ATA"]:
                    last_ata = rec["ATA"]
                else:
                    rec["ATA"] = last_ata
                rec.update(header_meta)
                rec["_page"] = page_num
                records.append(rec)

    return records
