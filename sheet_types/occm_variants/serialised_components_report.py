"""Serialised Components Report OCCM — real text layer, columns run together.

Confirmed on a real-corpus sample file via a direct pdfplumber pass over
every page. Has a genuine text layer throughout (no OCR needed); this
module is synchronous, pdfplumber-only.

`extract_text()` on this file collapses inter-column whitespace: the
column-header line comes back as a single run-on string with no spaces
between column names (e.g. "reglocationmodel..." style garbling). The
individual words themselves are intact -- `extract_words()` reports each
one with its own x0/x1/top -- so rows and columns are reconstructed purely
from word x-position, never from splitting the flattened text.

The real file also has a separate, independent quirk unrelated to
spacing: a font-encoding issue where the digits `0` and `1` sometimes
render as the letters `o`/`O` and `l`/`i` instead (e.g. an ATA-chapter
code appears as `<n><n>-oo` instead of `<n><n>-00` on a handful of rows).
This project's global OCR_CHAR_MAP (`shared/aviation_rules.py`) already
folds `O`/`o` -> `0` and `l`/`I` -> `1` for columns that opt into
`char_map`, so the existing global PART_NUMBER/SERIAL_NUMBER rules handle
it for free; ATA's own pattern is loosened below (see _OVERRIDES) purely
to accept the finer `<n><n>-<n><n>` chapter-subchapter format this file
actually prints (the global default is a bare 2-digit chapter).

Layout, confirmed page by page:
  - Page 1 opens with a short operator/title block, then a differently
    shaped "life-limited parts" summary section (a handful of components
    such as landing-gear shocks, APU, aircraft airframe, engines --
    reg/location/model/serial/manufacture-date/life-code/status columns,
    each entry spanning several print lines with extra indented lines
    such as "last journey number", "last journey date", "status date").
    This summary section uses a materially different multi-line layout
    from the main table below it and is NOT modeled by this module --
    known limitation, see below.
  - Immediately after that summary (page 1), and repeated as the page
    header on every subsequent page, the real body table begins with a
    column-header line reading (once un-garbled by word position):
    "ATA Part No Part Description Serial Number Logbook (Aircraft /
    Model / Type) Location Date Installed TSN/CSN Carry Out Hours
    Last Performed Model (Name / Part No / Serial No / Cycles / Type)"
    -- a wide, multi-tier wrapped header (its own words print across 3-4
    separate print-lines per page due to column width).
  - Each component's body row is anchored by an ATA-chapter token (e.g.
    "<n><n>-<n><n>") in the leftmost column; PART_DESCRIPTION frequently
    wraps onto one or two further indented print-lines with no new ATA
    anchor, which this module folds back into the same record.

Everything to the right of Serial Number (Logbook aircraft/model/type,
Location, Date Installed, TSN/CSN, Carry Out Hours, Last Performed, and
the further Model/Name/Part No/Serial No/Cycles/Type sub-columns) is
confirmed, directly against the real sample file, to NOT have reliable
column boundaries: several of these sub-columns render as one merged,
run-together word per row (dates, hour counters, certificate/work-order
references and constant logbook labels all glued together with no gap),
and the boundaries drift by a few points from page to page. Rather than
guess a fragile split here, this module keeps that entire region as one
free-text column, STATUS_TRAIL, per this project's "never guess a wrong
split" convention -- the same principle applied geometrically instead of
lexically in this project's other run-together-text OCCM variants.

A second, narrower version of the same issue affects the PART_NUMBER /
PART_DESCRIPTION boundary itself: on some rows the source PDF's text
stream has zero gap between the part number and the start of the
description, so `extract_words()` returns them as a single merged word
token spanning both columns' x-ranges (confirmed directly, e.g. a part
number immediately followed by a description word with no separating
space at all in the underlying text). Per the same "never guess" rule,
such a merged token is assigned whole to whichever column its horizontal
midpoint falls into (this project's established tie-break for a word
that straddles a column boundary, also used in serialized_component_list.
py) rather than being split -- meaning PART_NUMBER is legitimately blank
on the handful of rows where this happens, rather than guessed.

Header metadata (parsed once from page 1, stamped on every row):
  - OPERATOR: the operator name printed above the report title.
  - REPORT_TITLE: the constant title line, "Serialised Components
    Report".

Known limitation, confirmed directly against the real sample file: the
page-1-only "life-limited parts" summary section described above is not
extracted by this module at all (its rows never match the ATA-chapter
row anchor the main table uses, so they fall out for free rather than
being mis-parsed) -- a real gap if that summary's own rows are ever
needed, left for a future variant/pass rather than guessed at here.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "Serialised Components Report"
SIGNATURES = [
    "serialised components report",
]

CANONICAL_COLUMNS = [
    "ATA",
    "PART_NUMBER",
    "DESCRIPTION",
    "SERIAL_NUMBER",
    "STATUS_TRAIL",
    # Header metadata, parsed once per file and stamped on every row.
    "OPERATOR",
    "REPORT_TITLE",
]

_OVERRIDES = {
    # This file prints the finer "<chapter>-<subchapter>" form rather than
    # the global default's bare 2-digit chapter. char_map/sequence_map are
    # inherited from the global ATA rule below via merged_rules, so the
    # font's occasional 0->o / 1->i substitution (see module docstring) is
    # still folded back automatically.
    "ATA": {
        "pattern": r"^\d{2}-\d{2}$",
        "int_range": None,
    },
    # A handful of rows legitimately merge PART_NUMBER into the following
    # DESCRIPTION word with no gap (see module docstring) -- allow_empty
    # so those rows aren't flagged for a column that's genuinely blank
    # here rather than a parsing failure.
    "PART_NUMBER": {"allow_empty": True},
    "SERIAL_NUMBER": {"allow_empty": True},
    "OPERATOR": {"allow_empty": True},
    "REPORT_TITLE": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Column boundaries as (x0_inclusive, x1_exclusive, name), derived from the
# real body table's own header word positions and confirmed row-by-row
# against the real sample file across multiple pages. A word is assigned
# to whichever column its horizontal midpoint falls in (see module
# docstring on the PART_NUMBER/DESCRIPTION merge edge case).
_COLUMNS = [
    (-1e9, 48.0, "ATA"),
    (48.0, 108.0, "PART_NUMBER"),
    (108.0, 198.0, "DESCRIPTION"),
    (198.0, 250.0, "SERIAL_NUMBER"),
    (250.0, 1e9, "STATUS_TRAIL"),
]
_ROW_CLUSTER_TOL = 3.5

# ATA-chapter row anchor: "<n><n>-<n><n>", tolerant of the font's own
# occasional 0/1 -> o/i substitution (confirmed real, see module
# docstring) so a garbled anchor still starts a new row rather than
# silently merging it into the previous one.
_ATA_ANCHOR_RE = re.compile(r"^\d{2}-[0-9a-zA-Z]{2}$")

_TITLE_RE = re.compile(r"serialised\s+components\s+report", re.IGNORECASE)


def _col_for_x(x0: float, x1: float) -> str | None:
    mid = (x0 + x1) / 2
    for lo, hi, name in _COLUMNS:
        if lo <= mid < hi:
            return name
    return None


def _parse_header_meta(page0_words: list[dict]) -> dict:
    """Operator name + report title, both printed once above page 1's
    body table. Parsed from word position rather than the flattened text
    so it isn't affected by the same column/whitespace quirks as the body
    (there's no column layout at this point in the page, but keeping the
    same word-position approach avoids relying on extract_text() at all)."""
    meta = {"OPERATOR": "", "REPORT_TITLE": "Serialised Components Report"}
    top_words = sorted((w for w in page0_words if w["top"] < 50), key=lambda w: w["top"])
    if top_words:
        meta["OPERATOR"] = top_words[0]["text"].strip(" æ®")
    return meta


def _cluster_rows(words: list[dict]) -> list[list[dict]]:
    """Group words into visual table rows by `top` position. Words on the
    same printed row can differ by a fraction of a point due to font
    baseline/rendering, so a small tolerance is used rather than an exact
    match."""
    ordered = sorted(words, key=lambda w: (w["top"], w["x0"]))
    rows: list[list[dict]] = []
    cur: list[dict] = []
    cur_top: float | None = None
    for w in ordered:
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


def _row_is_new_record(row_words: list[dict]) -> bool:
    for w in row_words:
        if _col_for_x(w["x0"], w["x1"]) == "ATA" and _ATA_ANCHOR_RE.match(w["text"]):
            return True
    return False


def _new_record() -> dict:
    return {"ATA": [], "PART_NUMBER": [], "DESCRIPTION": [], "SERIAL_NUMBER": [], "STATUS_TRAIL": []}


def _flush(cur: dict | None, meta: dict, page_num: int, out: list[dict]) -> None:
    if cur is None:
        return
    rec = {name: " ".join(cur[name]) for name in
           ("ATA", "PART_NUMBER", "DESCRIPTION", "SERIAL_NUMBER", "STATUS_TRAIL")}
    rec.update(meta)
    rec["_page"] = page_num
    out.append(rec)


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        if not pdf.pages:
            return records
        meta = _parse_header_meta(pdf.pages[0].extract_words())
        for page_num, page in enumerate(pdf.pages, start=1):
            words = page.extract_words()
            if not words:
                continue
            # Header/title-block text (page 1's summary section included)
            # never satisfies the ATA-anchor test, so it's dropped for
            # free by keeping `cur` unset until the first real anchor row
            # on each page -- no page-specific top-cutoff needed.
            cur: dict | None = None
            for row_words in _cluster_rows(words):
                if _row_is_new_record(row_words):
                    _flush(cur, meta, page_num, records)
                    cur = _new_record()
                if cur is None:
                    continue
                for w in row_words:
                    col = _col_for_x(w["x0"], w["x1"])
                    if col is None:
                        continue
                    cur[col].append(w["text"])
            _flush(cur, meta, page_num, records)
    return records
