""""HT LIST REPORT" -- born-digital PDF with a genuinely broken body-table
font encoding: the header/title block and the per-page footer are fine, but
every table-body character (column headers included) comes back from
`pdfplumber.extract_text()`/`extract_words()` as the WRONG letter/digit --
not blank, not a "(cid:n)" placeholder (the failure mode this project's
`aircraft_kardex_status_broken_font_scanned.py` / `occm.py`'s
`_is_cid_garbled()` catch), but a plausible-looking WRONG character, silently.

Confirmed directly on the real sample file, character by character, via
`pdfplumber.Page.chars`: the glyphs for a body-table serial number visually
reading "BNG5050" decode through pdfplumber's font/encoding metadata as the
literal string "BNGSOSO" (glyph "5" -> code point that maps to "S", glyph
"0" -> code point that maps to "O") -- confirmed the rendered glyph SHAPE at
that exact position is unambiguously "5"/"0" (rendered the page to an image
at 400 DPI and inspected the cropped cell directly), so this is a genuine
font-encoding mismatch in the source file, not a transcription/rendering
bug on this project's own side. Also confirmed the column-header row itself
carries the same corruption ("SERIAL NUM8ER" for "SERIAL NUMBER", "DV" for
the interval-days header's own "DY") -- so this is not limited to a
smaller-vs-larger font-size split, and the router's SIGNATURES match (this
module's own title line, "HT LIST REPORT") is the only text-layer content
trusted at all; every other on-page string, including this module's own
metadata block below, is read from a DIFFERENT, confirmed-clean font run
that is NOT reused anywhere in the table body (see below).

The A/C Reg / MSN / TSN / CSN / Report Date header block (top of page 1
only) is a separate, confirmed-clean text run -- checked directly against
the same page rendered to an image: every value read via
`pdfplumber.extract_text()` there matches the rendered glyphs exactly, with
no substitutions of the kind documented above. It is parsed straight from
the text layer once (page 1) and stamped on every row; the table body itself
is never read from the text layer, only from its own (reliable) word
POSITIONS -- used purely to lay out per-row OCR crops, never to read
character content.

Row/column recovery strategy, confirmed directly on the real sample file:

  1. `pdfplumber.Page.extract_words()` gives correct word BOUNDING BOXES
     (the glyph outlines render and lay out correctly; only the
     code-point-to-Unicode mapping is broken), so those positions -- never
     the `.text` content -- are used to cluster body words into physical
     table rows (small top-tolerance bucketing, ties to this table's own
     confirmed ~7.2pt row pitch).
  2. For each row, two image crops are OCR'd independently via
     `shared/ocr_bridge.py` at 300 DPI (2x upscaled before OCR -- confirmed
     directly this recovers this report's own ~5pt body font cleanly, where
     one single whole-row or whole-page OCR pass across the full column
     width was confirmed directly to come back badly garbled: gridlines and
     the sheer number of adjacent narrow numeric sub-columns confuse
     Tesseract's own word segmentation at that width, exactly the "if you
     see garbled results, use per-column-strip OCR instead" case):
       - a left-hand TEXT strip covering NO./DESCRIPTION/POSITION/
         PART_NUMBER/SERIAL_NUMBER, bucketed by fixed x-cut boundaries
         (these five columns are wide and unambiguous -- no numeric
         sub-column crowding);
       - a right-hand METRICS strip covering the twelve FH/FC/DATE cells
         (INSTALL DATE / SINCE LAST / NEXT DUE / INTERVAL, each FH+FC+DATE
         or FH+FC+DY) plus REMARK, bucketed by NEAREST column-header x
         (mirrors `hard_time_component_list.py`'s own `_nearest()`
         convention in this same package) rather than fixed cut points,
         since sparsely-populated rows (see below) leave many of these
         sub-columns entirely empty.
  3. A row is accepted as real table data only if its own NO. bucket OCRs
     to a small integer (`^\\d{1,4}$`) -- this single gate is confirmed
     directly to reject every non-data line on the real sample file (the
     page-1 title/info block, the repeated-per-page column-header row, the
     per-page "Page n of n" footer, AND the LAST page's own
     signature/authorisation block) without any separate positional
     cutoff, since none of those lines ever carries a bare small integer in
     the NO. column's own x-range. The right-hand METRICS crop is only ever
     taken for a row that already passed this gate, so no OCR effort (or
     output-field risk) is spent on non-data lines at all.

Two structurally different row shapes are both handled by the SAME nearest-
column-header bucketing in step 2, confirmed directly, no per-shape
branching needed:
  * the common case -- an FH-or-FC-or-DATE value (or a dash placeholder,
    dropped by the OCR pass itself since it carries no recognizable glyph)
    in most of the twelve metric sub-columns;
  * a calendar-life item (e.g. an expiry-dated safety component): only
    INSTALL_DATE and NEXT_DUE_DATE are populated, and the descriptive
    phrase "Until EXP. Date" appears literally in place of a numeric value
    -- confirmed directly, its own three OCR'd words all land nearest the
    INTERVAL_DY header x-position, so INTERVAL_DY is treated as free text
    (a number OR a short phrase), never forced into a numeric pattern.

A real individual's name appears in the printed signature block on the
LAST page, below the last real data row (confirmed directly on the real
sample file). It is never read into any output field: the whole
signature/authorisation block fails the NO.-gate check above (its own
left-hand text never starts a small integer in the NO. column's x-range),
so no OCR crop is ever taken for it and no downstream code path can surface
it, by construction -- not by a text-content check that a mis-OCR could
someday defeat.
"""
from __future__ import annotations
import re

import pdfplumber

from sheet_types.ht_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_words, page_count

NAME = "HT List Report"

# Checked against every SIGNATURES list in occm.py/ht.py/llp.py and every
# occm_variants/ht_variants/llp_variants module's own SIGNATURES list; no
# collision found. The nearest look-alike in this package,
# cognos_ht_listing.py's "HT LISTING", is not a substring of this phrase (or
# vice versa) in either direction.
SIGNATURES = [
    "HT LIST REPORT",
]

CANONICAL_COLUMNS = [
    "NO",
    "DESCRIPTION",
    "POSITION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "INSTALL_FH",
    "INSTALL_FC",
    "INSTALL_DATE",
    "SINCE_LAST_FH",
    "SINCE_LAST_FC",
    "SINCE_LAST_DATE",
    "NEXT_DUE_FH",
    "NEXT_DUE_FC",
    "NEXT_DUE_DATE",
    "INTERVAL_FH",
    "INTERVAL_FC",
    "INTERVAL_DY",
    "REMARK",
    # Header metadata -- same on every row of a given file.
    "AC_REG",
    "AC_MSN",
    "TSN",
    "CSN",
    "REPORT_DATE",
]

_FH_RE = r"^[\d,]+(?:\s*:\s*\d{1,2})?$"
_NUM_RE = r"^[\d,]+$"
_DATE_RE = r"^\d{4}-\d{1,2}-\d{1,2}$"

_OVERRIDES = {
    "NO": {"pattern": r"^\d+$"},
    "POSITION": {"allow_empty": True},
    "PART_NUMBER": {"allow_empty": True},
    "SERIAL_NUMBER": {"allow_empty": True},
    "INSTALL_FH": {"pattern": _FH_RE, "allow_empty": True},
    "INSTALL_FC": {"pattern": _NUM_RE, "allow_empty": True},
    "INSTALL_DATE": {"pattern": _DATE_RE, "allow_empty": True},
    "SINCE_LAST_FH": {"pattern": _FH_RE, "allow_empty": True},
    "SINCE_LAST_FC": {"pattern": _NUM_RE, "allow_empty": True},
    "SINCE_LAST_DATE": {"pattern": _DATE_RE, "allow_empty": True},
    "NEXT_DUE_FH": {"pattern": _FH_RE, "allow_empty": True},
    "NEXT_DUE_FC": {"pattern": _NUM_RE, "allow_empty": True},
    "NEXT_DUE_DATE": {"pattern": _DATE_RE, "allow_empty": True},
    "INTERVAL_FH": {"pattern": _FH_RE, "allow_empty": True},
    "INTERVAL_FC": {"pattern": _NUM_RE, "allow_empty": True},
    # Free text on calendar-life rows (e.g. "Until EXP. Date") as well as a
    # plain day count -- see module docstring. Never forced numeric.
    "INTERVAL_DY": {"allow_empty": True},
    "REMARK": {"allow_empty": True},
    "AC_REG": {"pattern": r"^[A-Z0-9\-]+$", "uppercase": True, "allow_empty": True},
    "AC_MSN": {"pattern": r"^\d+$", "allow_empty": True},
    "TSN": {"allow_empty": True},
    "CSN": {"allow_empty": True},
    "REPORT_DATE": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# --- Geometry (PDF points, 72/in) -- derived directly from this report's
# own column-header word x-positions on the real sample file, confirmed
# stable across every page checked (front, several middle, and the last
# page). Data values were also confirmed to line up against these same
# x-positions to within a few points on every page checked. ---------------
_TEXT_BOUNDS = [
    (0.0, 78.0, "NO"),
    (78.0, 204.0, "DESCRIPTION"),
    (204.0, 258.0, "POSITION"),
    (258.0, 312.0, "PART_NUMBER"),
    (312.0, 369.0, "SERIAL_NUMBER"),
]
_TEXT_BLOCK_X0, _TEXT_BLOCK_X1 = 0.0, 369.0

_METRIC_FIELDS = [
    "INSTALL_FH", "INSTALL_FC", "INSTALL_DATE",
    "SINCE_LAST_FH", "SINCE_LAST_FC", "SINCE_LAST_DATE",
    "NEXT_DUE_FH", "NEXT_DUE_FC", "NEXT_DUE_DATE",
    "INTERVAL_FH", "INTERVAL_FC", "INTERVAL_DY",
    "REMARK",
]
_METRIC_HEADER_X = [
    388.3, 422.9, 449.7,
    484.3, 514.5, 542.9,
    577.4, 607.7, 636.0,
    668.1, 692.9, 723.1,
    756.5,
]
_METRIC_BLOCK_X0, _METRIC_BLOCK_X1 = 369.0, 842.64

_DPI = 300
_UPSCALE = 2
_ROW_TOL = 2.5      # pdfplumber-word top-clustering tolerance, points
_ROW_PAD = 0.7       # crop padding above/below a row's own word bbox, points

_NO_GATE_RE = re.compile(r"^\d{1,4}$")

# The ruled table's own gridlines OCR as stray border/leader glyphs glued
# onto real tokens (e.g. a leading "|" in front of the NO. column's own
# digit) -- confirmed directly on the real sample file, most commonly on
# the NO. cell's own left border. Stripped before the NO.-gate check and
# from every bucketed field's own edges, same convention as this package's
# other per-cell/per-strip OCR variants (e.g.
# `aircraft_rotables_ht_scanned.py`'s own `_clean_bucket()`).
_BORDER_CHARS = " |{}[]<>=~()`*\"'“”‘’.,_-"


def _strip_border(text: str) -> str:
    return text.strip(_BORDER_CHARS)


_META_RE = {
    "AC_REG": re.compile(r"A/C Reg:\s*(\S+)"),
    "AC_MSN": re.compile(r"MSN:\s*(\S+)"),
    "TSN": re.compile(r"\bTSN\s+(\S+)"),
    "CSN": re.compile(r"\bCSN\s+(\S+)"),
    "REPORT_DATE": re.compile(r"Report Date\s+(\S+)"),
}


def _nearest_field(x0: float) -> str:
    best_i, best_dist = 0, abs(x0 - _METRIC_HEADER_X[0])
    for i in range(1, len(_METRIC_HEADER_X)):
        dist = abs(x0 - _METRIC_HEADER_X[i])
        if dist < best_dist:
            best_i, best_dist = i, dist
    return _METRIC_FIELDS[best_i]


def _group_rows(words: list[dict]) -> list[tuple[float, float]]:
    """Cluster word bounding boxes (positions only -- see module docstring)
    into physical row bands, returned as (top, bottom) in PDF points."""
    ws = sorted(words, key=lambda w: (w["top"], w["x0"]))
    rows: list[list[dict]] = []
    for w in ws:
        if rows and abs(w["top"] - rows[-1][0]["top"]) <= _ROW_TOL:
            rows[-1].append(w)
        else:
            rows.append([w])
    bands = []
    for row in rows:
        top = min(w["top"] for w in row)
        bottom = max(w["bottom"] for w in row)
        bands.append((top, bottom))
    return bands


_IMG_SCALE = _DPI / 72   # pixels-per-point on the render_page() image itself


def _crop(img, x0: float, top: float, x1: float, bottom: float):
    box = (
        max(0, int(x0 * _IMG_SCALE)),
        max(0, int((top - _ROW_PAD) * _IMG_SCALE)),
        min(img.width, int(x1 * _IMG_SCALE)),
        min(img.height, int((bottom + _ROW_PAD) * _IMG_SCALE)),
    )
    crop = img.crop(box)
    if _UPSCALE != 1:
        crop = crop.resize((crop.width * _UPSCALE, crop.height * _UPSCALE))
    return crop


# A dash ("-") placeholder cell (this report's own convention for "not
# tracked on this basis" -- see module docstring) OCRs unreliably at this
# report's ~5pt body font: confirmed directly, the same glyph comes back as
# a bare ":", a bare "°", or (less often) a short garbage word rather
# than "-" itself. A lone ":"/"°" token can never be a genuine value in
# any column on this report (the real "HH:MM" install/since-last FH suffix
# is always glued onto a preceding digit run, e.g. ":11", never standalone),
# so both are treated as the same border/placeholder noise as a literal "-"
# rather than kept as a spurious cell value.
_PURE_BORDER_RE = re.compile(r"^[\s|{}\[\]<>=~()`*\"'“”‘’.,_:°-]+$")


async def _ocr_bucket_text(img, top: float, bottom: float) -> dict[str, str]:
    crop = _crop(img, _TEXT_BLOCK_X0, top, _TEXT_BLOCK_X1, bottom)
    words = await ocr_words(crop, psm=6, min_conf=-1)
    scale = _IMG_SCALE * _UPSCALE
    out: dict[str, list[str]] = {name: [] for _, _, name in _TEXT_BOUNDS}
    for w in sorted(words, key=lambda w: w["left"]):
        if _PURE_BORDER_RE.match(w["text"]):
            continue
        x0_pt = w["left"] / scale
        for lo, hi, name in _TEXT_BOUNDS:
            if lo <= x0_pt < hi:
                out[name].append(w["text"])
                break
    return {name: _strip_border(" ".join(vals)) for name, vals in out.items()}


async def _ocr_bucket_metrics(img, top: float, bottom: float) -> dict[str, str]:
    crop = _crop(img, _METRIC_BLOCK_X0, top, _METRIC_BLOCK_X1, bottom)
    words = await ocr_words(crop, psm=6, min_conf=-1)
    scale = _IMG_SCALE * _UPSCALE
    out: dict[str, list[str]] = {f: [] for f in _METRIC_FIELDS}
    for w in sorted(words, key=lambda w: w["left"]):
        if _PURE_BORDER_RE.match(w["text"]):
            continue
        x0_pt = w["left"] / scale + _METRIC_BLOCK_X0
        field = _nearest_field(x0_pt)
        out[field].append(w["text"])
    return {f: _strip_border(" ".join(vals)) for f, vals in out.items()}


async def _parse_page(pdf_page, img, page_num: int, meta: dict) -> list[dict]:
    words = pdf_page.extract_words(use_text_flow=False, keep_blank_chars=False)
    if not words:
        return []
    bands = _group_rows(words)
    records = []
    for top, bottom in bands:
        text_fields = await _ocr_bucket_text(img, top, bottom)
        no_val = text_fields.get("NO", "").strip()
        if not _NO_GATE_RE.match(no_val):
            # Not a data row (title/info block, repeated column-header row,
            # page footer, or the last page's own signature block) -- see
            # module docstring. Skipped entirely, no further OCR spent.
            continue
        metric_fields = await _ocr_bucket_metrics(img, top, bottom)
        row = {col: "" for col in CANONICAL_COLUMNS}
        row.update(text_fields)
        row.update(metric_fields)
        row.update(meta)
        row["_page"] = page_num
        records.append(row)
    return records


def _parse_meta(pdf_path: str) -> dict:
    meta = {k: "" for k in _META_RE}
    try:
        with pdfplumber.open(pdf_path) as pdf:
            if pdf.pages:
                head_text = pdf.pages[0].extract_text() or ""
                head_text = head_text.split("TASK")[0]
                for field, rx in _META_RE.items():
                    m = rx.search(head_text)
                    if m:
                        meta[field] = m.group(1)
    except Exception:
        pass
    return meta


async def extract(pdf_path: str) -> list[dict]:
    meta = _parse_meta(pdf_path)
    records: list[dict] = []
    n_pages = await page_count(pdf_path)
    with pdfplumber.open(pdf_path) as pdf:
        for page_index in range(n_pages):
            img = await render_page(pdf_path, page_index, dpi=_DPI)
            pdf_page = pdf.pages[page_index]
            records.extend(await _parse_page(pdf_page, img, page_index + 1, meta))
    return records
