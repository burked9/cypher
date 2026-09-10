""""OCCM COMPONENT STATUS" report -- parent-serial/TSN-CSN grid variant,
scanned, no text layer, OCR required throughout.

Confirmed directly on a real corpus file: 0 extractable characters on every
page via `fitz`/pdfplumber (a straight scan, 27 pages). Page 1 carries a
title/logo banner plus a small info box in the top-right corner; every page
(including page 1, below its extra banner) then carries a single ruled
8-column grid, e.g. (values genericized per this project's data-sensitivity
convention -- no real registration/MSN/line/var/hours/cycles/PN/SN from the
source file is ever written in this module)::

    Regn.: <reg>
    OCCM COMPONENT STATUS                    MSN: <msn>     A/C FH: <fh>
    <operator>                                Line #: <n>    A/C FC: <fc>
                                               Var #: <code>

    ATA | PART DESCRIPTION | PARENT SERIAL | PART NO. | SERIAL NO. | TSN | CSN | INSTALL DATE
    21  | <description...> | <parent_sn>   | <pn>     | <sn>       | <hh>:<mm> | <n> | <dd>/<mm>/<yyyy>

This report's title line ("OCCM COMPONENT STATUS") is also this project's
existing `occm_component_status_report.py` module's own SIGNATURES entry --
a deliberately generic-sounding phrase checked carefully against every
similarly-named sibling in this package (`occm_component_status_report.py`,
`occm_components_status.py`, `occm_component_status_dual_basis.py`,
`occm_component_status_facility_msn.py`). None of the four collide with
this module in practice: `occm_component_status_report.py` is a
*born-digital* variant reached only through the router's pdfplumber
SIGNATURES match (its column shape is also different -- NO/ATA/LOCATION/
DESCRIPTION/PART_NUMBER/SERIAL_NUMBER/INSTALL_DATE/TSI/CSI, no PARENT
SERIAL, no CSN); the other three each key on their own distinct
column-header phrase, none of which is "PARENT SERIAL" or a substring of
it. This module's own known source file has no text layer at all, so
`occm_component_status_report.py`'s SIGNATURES entry can never match it
through the router's normal pdfplumber path; this module is reached only
via its own `ocr_detect()` below, anchored on "PARENT SERIAL" -- confirmed
directly (grep across every SIGNATURES list in
`sheet_types/{occm,ht,llp}.py` and every existing `occm_variants/`,
`ht_variants/`, `llp_variants/` module) to appear nowhere else in this
package, so it cannot collide with any sibling's own SIGNATURES or
`ocr_detect()` anchor.

An earlier rough OCR pass of the source file looked highly irregular --
inconsistent column presence row to row, and a stray "AGEMP"-shaped token
appearing where POSITION might be expected. Direct inspection (rendering
every page and reading real ruled-cell pixel boundaries, not trusting that
rough pass) shows the opposite: the table is a completely regular, cleanly
ruled 8-column grid on every page, with every row the same height (a
horizontal-ruled-line scan down the ATA column's own pixel span finds row
boundaries 42-47px apart, with zero exceptions, across the first, a middle,
and the last page of the real sample -- no wrapped/multi-line rows anywhere
in the file). The "AGEMP" oddity is resolved by the same direct inspection:
it is not a separate column, and not registration bleed from the title
banner -- it is simply this file's own PARENT SERIAL column, which most
rows populate with the aircraft's own registration (with its hyphen
dropped), and which the OCR engine occasionally misreads as containing a
"G" rather than the digit "6" (a single-character digit/letter confusion,
not a structural difference). A minority of PARENT SERIAL cells instead
carry a plain numeric sub-assembly serial (seen on engine/APU/thrust-
reverser-adjacent rows near the end of the file) -- both are genuine values
of the same single column, not two different fields.

The embedded zone/position code fused into PART DESCRIPTION (e.g.
"-M21541-LH", "-B21251-LH", "-No 1 INBD") was checked directly for whether
it could be reliably split out into its own column: it cannot. The suffix
shape is inconsistent across rows -- sometimes a zone code, sometimes a
side/position qualifier ("-LH"/"-RH"/"-FWD"/"-AFT"), sometimes a numbered
instance ("-No 1", "-No 14 OTBD"), sometimes absent entirely (e.g. a bare
"AMPLIFIER" or "ANTENNA HIGH GAIN" with no trailing code at all) -- so
DESCRIPTION is kept as one free-text column rather than force a fragile
split, per this project's "never guess a wrong split" convention. No
STATUS_TRAIL overflow column is populated by this module in practice: every
inspected row (including the aircraft-level totals row that appears first
in the file, before any real component row -- DESCRIPTION-only, its
remaining cells blank except SERIAL_NUMBER/TSN/CSN, evidently repeating the
airframe's own accumulated hours/cycles) fits the same 8-column ruled shape
with no wrapped or overflow text; STATUS_TRAIL is still carried on every
record (always empty in practice) purely for schema consistency with this
package's other OCCM variants, in case a genuinely unparseable overflow
line is ever found on another file of this same template.

OCR approach -- confirmed directly, side by side, against the real sample
file rather than assumed:

A whole-page or whole-row OCR pass (`ocr_text()`/`ocr_words()` on an entire
rendered page, any psm) fails badly here: entire rows collapse into a
handful of garbled multi-word blobs. This is what the rough OCR pass in the
task actually hit -- not evidence of an irregular table, but of a
badly-suited whole-page OCR call against a densely ruled grid. The fix
(also this package's established approach for a badly-behaved whole-page
pass, see e.g. `on_component_monitoring_listing_status.py`,
`msn_occm_list_scanned.py`) is to recover the table's own ruled row
boundaries directly from pixels (a numpy darkfrac scan over the ATA
column's X-span) and OCR each of the 8 columns as its own full-height ruled
strip, `ocr_words(psm=4)`, bucketing every recognized word into the real
ruled row it falls within by Y-position.

Two further findings, both confirmed directly by side-by-side experiment
against the real sample file, drove the rest of this module's design:

1. `psm=4` (assume a single column of text) recovers every column
   correctly as a full-height strip except a scattered handful of cells per
   page (mostly in PARENT_SERIAL and SERIAL_NUMBER) where Tesseract's own
   internal line segmentation silently drops a cell from a long strip of
   near-identical short values -- `psm=6` on the very same strip sometimes
   returns nothing at all instead. Cropping a strip so its bottom edge sits
   exactly on a ruled line (rather than a few px past it) reproduces the
   same silent-empty failure -- the ruled line itself clips a whisker of
   the last row's glyph pixels, which is enough to make some psm's layout
   analysis give up on the whole strip. Neither pathology is worth chasing
   with a single global fix.
2. The fix used instead: any table cell (row x column) still empty after
   the full-strip pass gets one direct fallback OCR call on its own
   isolated crop (a few px inset off its own ruled cell boundary so no
   neighbouring rule leaks in, 3x upscaled, white-padded, `psm=6`) --
   confirmed directly to recover every one of the gaps left by the
   full-strip pass on the real sample file's first, a middle, and its last
   page. This costs a modest number of extra OCR calls per page (a few
   dozen at most, only for the cells that actually came back empty), far
   cheaper than doing this for every cell up front.

Column X-boundaries (fraction of page width, stable across the first, a
middle, and the last page of the real sample file to within a handful of
px) are measured directly from the real rendered page's own ruled
vertical-line pixel columns, the same technique as this package's other
grid-based OCR variants.

Header metadata (AIRCRAFT_REG, MSN, AC_FH, LINE_NUMBER, AC_FC, VAR_NUMBER)
is parsed once from page 1's own info box (cropped to its right-hand third,
well clear of the title/logo banner and the data grid) and stamped
identically onto every row of the file, per this package's usual
header-plus-body OCCM convention.
"""
from __future__ import annotations
import re

import numpy as np
from PIL import Image, ImageOps

from sheet_types.occm_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, ocr_words, page_count

NAME = "OCCM Component Status (Parent Serial / TSN-CSN Grid, Scanned)"

# This module's known source file has no text layer at all (confirmed via
# pdfplumber -- 0 chars on every page), so these SIGNATURES can never fire
# through occm.py's normal pdfplumber head-text match; real detection
# happens via ocr_detect() below. Deliberately left empty, same convention
# as this package's other purely-OCR variants.
SIGNATURES = []

CANONICAL_COLUMNS = [
    "ATA",
    "DESCRIPTION",
    "PARENT_SERIAL",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "TSN",
    "CSN",
    "INSTALL_DATE",
    # Header metadata, parsed once and stamped on every row.
    "AIRCRAFT_REG",
    "MSN",
    "AC_FH",
    "LINE_NUMBER",
    "AC_FC",
    "VAR_NUMBER",
    # Overflow catch-all -- always empty in practice on the known source
    # file (see module docstring), kept for schema consistency with this
    # package's other OCCM variants.
    "STATUS_TRAIL",
]

_OVERRIDES = {
    # A handful of rows (confirmed directly: an aircraft-level totals row
    # that precedes the real component rows on page 1) have no ATA at all;
    # sheet_types/occm.py's generic ATA forward-fill only ever fires
    # forward, so this row's blank ATA is simply left blank rather than
    # incorrectly inherited from a later row.
    "ATA": {"pattern": r"^\d{2}$", "int_range": (20, 83), "allow_empty": True},
    # PARENT_SERIAL is genuinely two different shapes on the real sample
    # file (an aircraft-registration-derived code on most rows, a plain
    # numeric sub-assembly serial on a minority near the end -- see module
    # docstring), so a loose alnum pattern is used rather than either
    # shape's own tighter one.
    "PARENT_SERIAL": {"pattern": r"^[A-Z0-9]{2,12}$", "uppercase": True,
                       "allow_empty": True, "_strip_leading_punct": True},
    "PART_NUMBER": {"allow_empty": True},
    "SERIAL_NUMBER": {"allow_empty": True},
    # TSN prints as either "<hours>:<mm>" or a bare integer hours value on
    # the real sample file (confirmed directly, both forms seen); CSN is a
    # bare integer, occasionally with a ".00"-style decimal suffix.
    "TSN": {"pattern": r"^\d{1,6}(:\d{2})?$", "allow_empty": True},
    "CSN": {"pattern": r"^\d{1,6}(\.\d{1,2})?$", "allow_empty": True},
    "INSTALL_DATE": {"pattern": r"^\d{2}/\d{2}/\d{4}$", "allow_empty": True},
    # Header metadata -- each value is a single figure parsed once and
    # stamped identically on every row of the file, so a tight pattern here
    # would either flag every single row over one OCR misread in one
    # place, or none at all -- neither is a useful per-row signal. Genuine
    # per-row corruption is still caught by the row-level rules above. Same
    # reasoning as this package's other header-plus-body OCCM variants
    # (e.g. `on_component_monitoring_listing_status.py`'s own header
    # fields).
    "AIRCRAFT_REG": {"allow_empty": True},
    "MSN": {"allow_empty": True},
    "AC_FH": {"allow_empty": True},
    "LINE_NUMBER": {"allow_empty": True},
    "AC_FC": {"allow_empty": True},
    "VAR_NUMBER": {"allow_empty": True},
    "STATUS_TRAIL": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Column X-boundaries (fraction of page width), measured directly from the
# real rendered page's own ruled vertical-line pixel columns -- confirmed
# stable across the first, a middle, and the last page of the real sample
# file (see module docstring).
_COLUMNS: list[tuple[str, float, float]] = [
    ("ATA", 0.04416, 0.10264),
    ("DESCRIPTION", 0.10264, 0.39563),
    ("PARENT_SERIAL", 0.39563, 0.48624),
    ("PART_NUMBER", 0.48624, 0.60446),
    ("SERIAL_NUMBER", 0.60446, 0.69783),
    ("TSN", 0.69783, 0.76318),
    ("CSN", 0.76318, 0.83486),
    ("INSTALL_DATE", 0.83486, 0.92803),
]
_JOIN_SPACE = {"DESCRIPTION"}

# Header metadata info-box crop: right-hand ~25% of the page, above the
# column-header row -- confirmed directly to sit well clear of both the
# title/logo banner (left side) and the data grid (below the column-header
# row) on the real sample file's page 1.
_HEADER_X0_FRAC = 0.75

# Row-grid detection: a pixel row counts as part of a ruled horizontal line
# once at least this fraction of the ATA column's own width is dark.
_LINE_DARKFRAC_THRESH = 0.85
_DARK_PIXEL_THRESH = 150
# Consecutive dark-row hits within this many px are the same ruled line.
_LINE_MERGE_GAP = 3
# The column-header text row is noticeably taller than an ordinary data
# row on the real sample file (confirmed directly: ~55-70px vs. ~42-47px
# for every data row, no exceptions found) -- the first line-to-line gap
# that falls in this band is the column-header row's own bottom edge, i.e.
# the top of the first real data row.
_HEADER_ROW_HEIGHT_RANGE = (50, 80)
# A few px of slack added past each chunk's own ruled edges before OCR --
# cropping exactly on the ruled line clips a whisker of the last row's
# glyph pixels and can make OCR give up on the whole strip (see module
# docstring).
_STRIP_PAD = 12

_NOISE_TOKEN_RE = re.compile(r"^[|\[\]_\-—–~=<>`\"'*]+$")
_EDGE_STRIP = " _-|[]=~.\"'`*"

_REGN_RE = re.compile(r"Regn\.?:?\s*([A-Z0-9\-]{2,12})", re.IGNORECASE)
_MSN_RE = re.compile(r"MSN:?\s*([A-Z0-9]{1,10})", re.IGNORECASE)
_FH_RE = re.compile(r"A\s*/?\s*C\s*FH:?\s*([\d,:]{2,15})", re.IGNORECASE)
_LINE_RE = re.compile(r"Line\s*#:?\s*(\S{1,10})", re.IGNORECASE)
_FC_RE = re.compile(r"A\s*/?\s*C\s*FC:?\s*([\d,]{1,10})", re.IGNORECASE)
_VAR_RE = re.compile(r"Var\s*#:?\s*(\S{1,12})", re.IGNORECASE)

_HEADER_FIELDS = ["AIRCRAFT_REG", "MSN", "AC_FH", "LINE_NUMBER", "AC_FC", "VAR_NUMBER"]

# ocr_detect() anchor -- "PARENT SERIAL" is this module's own column-header
# phrase. Checked directly (grep across every SIGNATURES list in
# sheet_types/{occm,ht,llp}.py and every existing occm_variants/,
# ht_variants/, llp_variants module): appears nowhere else in this
# package, and is not a substring of (nor contains) any other variant's
# own SIGNATURES/ocr_detect anchor.
_TITLE_RE = re.compile(r"PARENT\s+SERIAL", re.IGNORECASE)


def _col_bounds(name: str) -> tuple[float, float]:
    for n, lo, hi in _COLUMNS:
        if n == name:
            return lo, hi
    raise KeyError(name)


def _find_row_lines(arr: np.ndarray, x0: int, x1: int) -> list[int]:
    """Recover the table's own ruled horizontal-line Y-positions directly
    from the page image -- a numpy darkfrac scan over the ATA column's own
    X-span (see module docstring)."""
    band = arr[:, x0:x1]
    darkfrac = (band < _DARK_PIXEL_THRESH).mean(axis=1)
    rows_dark = np.where(darkfrac > _LINE_DARKFRAC_THRESH)[0]
    if len(rows_dark) == 0:
        return []
    lines: list[int] = []
    cur = [int(rows_dark[0])]
    for r in rows_dark[1:]:
        r = int(r)
        if r - cur[-1] <= _LINE_MERGE_GAP:
            cur.append(r)
        else:
            lines.append((cur[0] + cur[-1]) // 2)
            cur = [r]
    lines.append((cur[0] + cur[-1]) // 2)
    return lines


def _find_header_idx(lines: list[int]) -> int | None:
    """Index into `lines` of the column-header row's own TOP edge -- the
    first line-to-line gap that falls inside the header row's known height
    band (see module docstring). Returns None if no such gap is found
    (e.g. a page with no table at all)."""
    lo, hi = _HEADER_ROW_HEIGHT_RANGE
    for i in range(len(lines) - 1):
        if lo <= lines[i + 1] - lines[i] <= hi:
            return i
    return None


def _row_idx_for(top: float, row_bounds: list[tuple[int, int]]) -> int | None:
    for i, (rt, rb) in enumerate(row_bounds):
        if rt <= top <= rb:
            return i
    return None


def _clean_token(text: str) -> str:
    return text.strip(_EDGE_STRIP).strip()


async def _ocr_cell_fallback(img, x0: int, x1: int, top: int, bot: int) -> str:
    """Direct per-cell OCR fallback for a table cell still empty after the
    full-column-strip pass (see module docstring on why some cells come
    back empty from that cheaper pass). Insets a few px off the cell's own
    ruled boundary, upscales 3x, and pads with white before OCR -- confirmed
    directly to recover every gap left by the full-strip pass on the real
    sample file."""
    x0i, x1i = x0 + 4, x1 - 4
    y0i, y1i = top + 2, bot - 2
    if x1i - x0i < 5 or y1i - y0i < 5:
        return ""
    crop = img.crop((x0i, y0i, x1i, y1i))
    crop = crop.resize((crop.width * 3, crop.height * 3), Image.LANCZOS)
    padded = ImageOps.expand(crop, border=20, fill=(255, 255, 255))
    text = await ocr_text(padded, psm=6)
    text = " ".join(text.split())
    return _clean_token(text)


def _parse_header(text: str, meta: dict) -> None:
    for pat, key in (
        (_REGN_RE, "AIRCRAFT_REG"),
        (_MSN_RE, "MSN"),
        (_FH_RE, "AC_FH"),
        (_LINE_RE, "LINE_NUMBER"),
        (_FC_RE, "AC_FC"),
        (_VAR_RE, "VAR_NUMBER"),
    ):
        if meta.get(key):
            continue
        m = pat.search(text or "")
        if m:
            meta[key] = m.group(1)


def _join(tokens: list[str], col_name: str) -> str:
    sep = " " if col_name in _JOIN_SPACE else ""
    return _clean_token(sep.join(tokens))


async def _ocr_page_rows(img) -> tuple[dict, list[dict]]:
    """OCR one rendered page: parse header metadata (only meaningful when
    this is page 1) and return (header_meta_or_empty, records-without-
    header-stamped)."""
    w, h = img.size
    arr = np.array(img.convert("L"))
    ata_x0, ata_x1 = int(w * _col_bounds("ATA")[0]), int(w * _col_bounds("ATA")[1])
    lines = _find_row_lines(arr, ata_x0, ata_x1)
    header_idx = _find_header_idx(lines)
    if header_idx is None:
        return {}, []

    header_meta: dict = {}
    header_top = lines[header_idx]
    crop = img.crop((int(w * _HEADER_X0_FRAC), 0, w, max(0, header_top)))
    text = await ocr_text(crop, psm=6)
    _parse_header(text, header_meta)

    row_bounds = list(zip(lines[header_idx + 1:], lines[header_idx + 2:]))
    if not row_bounds:
        return header_meta, []

    buckets: list[dict[str, list[str]]] = [{} for _ in row_bounds]
    y0, y1 = row_bounds[0][0], row_bounds[-1][1]
    for name, f0, f1 in _COLUMNS:
        x0, x1 = int(w * f0), int(w * f1)
        y0p, y1p = max(0, y0 - _STRIP_PAD), min(h, y1 + _STRIP_PAD)
        crop = img.crop((x0, y0p, x1, y1p))
        words = await ocr_words(crop, psm=4, min_conf=-1)
        for wd in words:
            text = str(wd.get("text", "")).strip()
            if not text or _NOISE_TOKEN_RE.match(text):
                continue
            top = y0p + wd["top"]
            idx = _row_idx_for(top, row_bounds)
            if idx is not None:
                buckets[idx].setdefault(name, []).append(text)

    # Fallback pass: direct per-cell OCR for any table cell still empty
    # after the full-strip pass above (see module docstring).
    for name, f0, f1 in _COLUMNS:
        x0, x1 = int(w * f0), int(w * f1)
        for i, (rt, rb) in enumerate(row_bounds):
            if name in buckets[i]:
                continue
            text = await _ocr_cell_fallback(img, x0, x1, rt, rb)
            if text and not _NOISE_TOKEN_RE.match(text):
                buckets[i][name] = [text]

    records = []
    for i in range(len(row_bounds)):
        b = buckets[i]
        rec = {name: _join(b.get(name, []), name) for name, _, _ in _COLUMNS}
        if not any(rec.values()):
            # No real cell content attached to this ruled row at all --
            # almost certainly page furniture rather than a genuine row.
            continue
        rec["STATUS_TRAIL"] = ""
        records.append(rec)
    return header_meta, records


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback (see
    sheet_types/occm.py) -- this variant's known source file has no text
    layer at all, so it can never be found through the normal pdfplumber
    head-text match.

    Anchors on the column-header phrase "PARENT SERIAL" (see module
    docstring), cropped to the top ~28% of the page -- confirmed directly
    to include both the title banner and the column-header row on the real
    sample file's page 1."""
    try:
        img = await render_page(pdf_path, 0, dpi=300)
        w, h = img.size
        crop = img.crop((0, 0, w, int(h * 0.28)))
        text = await ocr_text(crop, psm=6)
        return bool(_TITLE_RE.search(text))
    except Exception:
        return False


async def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    header_meta: dict = {k: "" for k in _HEADER_FIELDS}
    n_pages = await page_count(pdf_path)
    for page_index in range(n_pages):
        img = await render_page(pdf_path, page_index, dpi=300)
        page_meta, page_records = await _ocr_page_rows(img)
        if page_index == 0:
            for k, v in page_meta.items():
                if v and not header_meta.get(k):
                    header_meta[k] = v
        for rec in page_records:
            rec.update(header_meta)
            rec["_page"] = page_index + 1
            records.append(rec)
    return records
