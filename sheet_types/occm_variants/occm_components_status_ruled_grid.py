"""OCCM COMPONENTS STATUS -- plain 6-column ruled grid, scanned, no text
layer, OCR required throughout.

Confirmed directly on a real corpus file: 0 extractable characters on every
page via pdfplumber (a straight scan). Every page repeats the same header
block, then a single ruled 6-column grid (values genericized per this
project's data-sensitivity convention -- no real registration/MSN/hours/
cycles/PN/SN/date from the source file is written in this module)::

    <operator logo/name>          OCCM COMPONENTS STATUS
                        A/F FH: <fh>            A/C Reg: <reg>
                        A/F FC: <fc>             MSN: <msn>
                        Report Date: <date>    A/C Type: <type>

    ATA | DESCRIPTION | PART NUMBER | SERIAL NUMBER | POSITION | INSTALL DATE ON AIRCRAFT
    21  | <description...>  | <pn>  | <sn>           | <posn>   | <dd>.<Mon>.<yyyy>

Blank, shaded (no-text) rows appear between ATA-chapter groups -- genuine
grid rows with no cell content at all, not a rendering artifact -- and are
simply not emitted as records (confirmed directly: several per file,
always immediately following the last row of one ATA chapter).

This report's title line ("OCCM COMPONENTS STATUS") is a plural-COMPONENTS
phrase already used elsewhere in this package as a SIGNATURES/docstring
reference, so it was checked carefully rather than reused bare as this
module's own anchor (see `ocr_detect()` below for the exact collision
analysis). This module's own known source file has no text layer at all,
so no born-digital module's own pdfplumber SIGNATURES match (all of which
require real extracted text) can ever fire on it through the router's
normal path; this module is reached only via its own `ocr_detect()`.

Row/column geometry -- pixel-ruling detection, not word-position
bucketing or fixed fractions: this particular scan's table is a clean,
crisply-rendered ruled grid (every internal divider and the shaded
column-header band render as solid, fully dark pixel runs at every DPI
and every page checked -- front, several middle, and the last page of the
sample), unlike this package's other ruled-grid OCR variants (e.g.
`occm_component_status_posn_fin.py`) whose own thin row rulings were
confirmed too faint/skewed to detect this way. Because detection is this
reliable here, both the row boundaries (horizontal rules) and the column
boundaries (vertical rules) are found fresh on every page from that
page's own pixel data -- see `_find_header_bottom`, `_find_row_lines`,
`_find_col_lines` -- rather than hardcoded as fixed fractions of the page
box, so a page rendered at a different DPI or with a slightly different
scan crop still resolves correctly.

Per-column OCR uses one whole-column-height `ocr_words()` call per column
per page (not one call per cell) -- confirmed directly to be both faster
and, since a blank cell (see POSITION on several rows, confirmed directly
-- e.g. cabin-attendant-seat rows with no distinct install position) would
otherwise silently shift a naive per-column line-index alignment out of
sync with its sibling columns, no less accurate: each returned word is
instead bucketed into the row band (from `_find_row_lines`) whose Y-range
contains its own vertical center, so an empty cell in one column never
misaligns that row's other columns.

Known limitation, confirmed directly against the real sample file and its
own real pipeline run (`occm.normalize_and_validate()`): roughly two in
five rows carry at least one flagged field. Two distinct causes, both
left uncorrected here per this project's "never guess a wrong split, wrong
data is worse than missing data" convention (see `shared/aviation_rules.py`):
(1) the POSITION column's own font renders small enough (row height
~25px even at this module's own 400 DPI) that a meaningful share of its
values OCR with a misread glyph (e.g. a leading digit misread as a
similar-shaped letter); (2) on a minority of rows -- confirmed directly,
most often where the real cell value is short (a 2-4 digit SERIAL_NUMBER)
or genuinely blank (POSITION) -- Tesseract hallucinates an unrelated
glyph run across that cell's own whitespace rather than returning nothing.
Both failure modes were confirmed directly to still serve their purpose:
the hallucinated/misread text almost always contains a character outside
that column's own validation pattern (a stray `~`, repeated letters with
no digit, etc.), so it surfaces as a flagged row rather than a
plausible-looking wrong value. ATA, DESCRIPTION and PART_NUMBER were
confirmed directly to OCR far more reliably than SERIAL_NUMBER,
INSTALL_DATE and POSITION across the sample at the same settings.
"""
from __future__ import annotations
import re

import numpy as np
from PIL import Image

from sheet_types.occm_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, ocr_words, page_count

NAME = "OCCM Components Status (Plain Ruled Grid, Scanned)"

# This module's known source file has no text layer at all (confirmed via
# pdfplumber -- 0 chars on every page), so these SIGNATURES can never fire
# through occm.py's normal pdfplumber head-text match; real detection
# happens via ocr_detect() below. Deliberately left empty, same convention
# as this package's other purely-OCR ruled-grid variants.
SIGNATURES = []

CANONICAL_COLUMNS = [
    "ATA",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "POSITION",
    "INSTALL_DATE",
    # Header metadata -- parsed once (page 1) and stamped on every row.
    "AIRCRAFT_REG",
    "MSN",
    "AIRCRAFT_TYPE",
    "AIRCRAFT_FH",
    "AIRCRAFT_FC",
    "REPORT_DATE",
]

_OVERRIDES = {
    # No global default exists for POSITION -- a compact zone/side/instance
    # code, confirmed to sometimes be blank on the real sample file
    # (components with no distinct install position, e.g. cabin-attendant
    # seats). Loose pattern rather than a strict one: the small column font
    # is the one confirmed OCR weak-point in this module (see module
    # docstring), and a strict pattern here would flag noise rather than
    # signal.
    "POSITION": {
        "pattern": r"^[A-Z0-9][A-Z0-9 ,#/\-]{0,24}$",
        "uppercase": True,
        "allow_empty": True,
    },
    # Real dates on this file are "D[D].Mon.YYYY" (dot-separated, not
    # hyphen) -- confirmed directly across the sample.
    "INSTALL_DATE": {
        "pattern": r"^\d{1,2}\.[A-Za-z]{3,5}\.\d{4}$",
        "allow_empty": True,
    },
    # Header metadata -- each value is a single figure parsed once (page 1)
    # and stamped identically on every row of the file, so a tight pattern
    # here would either flag every single row over one OCR misread in one
    # place, or none at all -- neither is a useful per-row signal. Same
    # reasoning as this package's other header-plus-body OCCM variants.
    "AIRCRAFT_REG": {"allow_empty": True},
    "MSN": {"allow_empty": True},
    "AIRCRAFT_TYPE": {"allow_empty": True},
    "AIRCRAFT_FH": {"allow_empty": True},
    "AIRCRAFT_FC": {"allow_empty": True},
    "REPORT_DATE": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# --- Pixel-grid detection ---------------------------------------------------
_DARK_PIXEL_THRESH = 180
_LINE_MERGE_GAP = 3
# Shaded title/column-header band -- thick (tens of px), always in the top
# fifth of the page across the sample.
_HEADER_DARKFRAC_THRESH = 0.3
_HEADER_BAND_MIN_HEIGHT = 15
_HEADER_BAND_MAX_TOP_FRAC = 0.2
# Thin single-pixel row rulings below the header -- confirmed solid (dark
# fraction consistently > 0.85 across the table's own inner width) at
# every DPI and every page checked, unlike this package's other ruled-grid
# OCR variants whose own row rulings were confirmed too faint/skewed for
# this technique (see module docstring).
_ROW_DARKFRAC_THRESH = 0.85
# Vertical column-divider rulings -- confirmed fully solid (dark fraction
# 1.0) immediately below the header band on every page checked.
_COL_DARKFRAC_THRESH = 0.9
_COL_SCAN_HEIGHT = 150

_COLUMN_ORDER = ("ATA", "DESCRIPTION", "PART_NUMBER", "SERIAL_NUMBER",
                  "POSITION", "INSTALL_DATE")


def _merge_dark_groups(ys: np.ndarray, gap: int = _LINE_MERGE_GAP) -> list[tuple[int, int]]:
    if len(ys) == 0:
        return []
    groups: list[tuple[int, int]] = []
    start = prev = int(ys[0])
    for y in ys[1:]:
        y = int(y)
        if y - prev > gap:
            groups.append((start, prev))
            start = y
        prev = y
    groups.append((start, prev))
    return groups


def _find_header_bottom(arr: np.ndarray) -> int | None:
    """Bottom Y of the shaded title/column-header band -- see module
    docstring 'Row/column geometry'."""
    h, _ = arr.shape
    darkfrac = (arr < _DARK_PIXEL_THRESH).mean(axis=1)
    band_top = int(h * _HEADER_BAND_MAX_TOP_FRAC)
    ys = np.where(darkfrac[:band_top] > _HEADER_DARKFRAC_THRESH)[0]
    groups = _merge_dark_groups(ys)
    thick = [g for g in groups if g[1] - g[0] > _HEADER_BAND_MIN_HEIGHT]
    if not thick:
        return None
    return thick[-1][1]


def _find_col_lines(arr: np.ndarray, header_bottom: int) -> list[int]:
    """X-centers of the vertical column-divider rulings, found fresh from
    this page's own pixel data just below the header band (see module
    docstring)."""
    h, w = arr.shape
    y0, y1 = header_bottom, min(header_bottom + _COL_SCAN_HEIGHT, h)
    if y1 - y0 < 10:
        return []
    band = arr[y0:y1, :]
    darkfrac_col = (band < _DARK_PIXEL_THRESH).mean(axis=0)
    xs = np.where(darkfrac_col > _COL_DARKFRAC_THRESH)[0]
    groups = _merge_dark_groups(xs)
    return [(g[0] + g[1]) // 2 for g in groups]


def _find_row_lines(arr: np.ndarray, header_bottom: int, x0: int, x1: int) -> list[int]:
    """Y-centers of the horizontal row rulings across the table's own
    inner width, found fresh from this page's own pixel data (see module
    docstring). Stops naturally once no more full-width dark rows are
    found -- ordinary body text below the table (e.g. a signature block
    on the last page) never spans the full table width, so it never
    produces a spurious line here."""
    h, _ = arr.shape
    xi0, xi1 = x0 + 3, x1 - 3
    if xi1 - xi0 < 10:
        return []
    sub = arr[:, xi0:xi1]
    darkfrac = (sub < _DARK_PIXEL_THRESH).mean(axis=1)
    ys = np.where(darkfrac > _ROW_DARKFRAC_THRESH)[0]
    ys = ys[ys >= header_bottom]
    groups = _merge_dark_groups(ys, gap=2)
    return [(g[0] + g[1]) // 2 for g in groups]


_NOISE_TOKEN_RE = re.compile(r"^[|\[\]_\-—–~=<>`\"'*]+$")
_EDGE_STRIP = " _-|[]=~.\"'`*"


def _clean(text: str) -> str:
    return text.strip(_EDGE_STRIP).strip()


async def _ocr_page_rows(img: Image.Image) -> list[dict]:
    arr = np.array(img.convert("L"))
    header_bottom = _find_header_bottom(arr)
    if header_bottom is None:
        return []
    col_lines = _find_col_lines(arr, header_bottom)
    if len(col_lines) < len(_COLUMN_ORDER) + 1:
        return []
    row_lines = _find_row_lines(arr, header_bottom, col_lines[0], col_lines[-1])
    if len(row_lines) < 2:
        return []

    row_bands = list(zip(row_lines[:-1], row_lines[1:]))
    col_bounds = list(zip(col_lines[:-1], col_lines[1:]))
    # Extra trailing column-divider pairs (if any stray vertical line was
    # picked up past INSTALL_DATE) are ignored -- only the first N bounds
    # matching this module's own known columns are used.
    col_bounds = col_bounds[: len(_COLUMN_ORDER)]

    records = [dict.fromkeys(_COLUMN_ORDER, "") for _ in row_bands]
    row_tops = [b[0] for b in row_bands]
    row_bots = [b[1] for b in row_bands]

    for name, (cx0, cx1) in zip(_COLUMN_ORDER, col_bounds):
        x0, x1 = cx0 + 6, cx1 - 6
        if x1 - x0 < 5:
            continue
        crop = img.crop((x0, row_tops[0] + 2, x1, row_bots[-1] - 1))
        words = await ocr_words(crop, psm=6, min_conf=-1)
        buckets: list[list[tuple[float, str]]] = [[] for _ in row_bands]
        for wd in words:
            text = str(wd.get("text", "")).strip()
            if not text or _NOISE_TOKEN_RE.match(text):
                continue
            word_top = row_tops[0] + 2 + wd["top"]
            word_center = word_top + wd.get("height", 0) / 2
            # Nearest row band by center distance.
            best_i, best_d = None, float("inf")
            for i, (rt, rb) in enumerate(row_bands):
                center = (rt + rb) / 2
                d = abs(word_center - center)
                if d < best_d:
                    best_i, best_d = i, d
            if best_i is not None:
                buckets[best_i].append((wd["left"], text))
        for i, toks in enumerate(buckets):
            toks.sort(key=lambda t: t[0])
            records[i][name] = _clean(" ".join(t for _, t in toks))

    out = []
    for rec in records:
        # Separator (blank) rows between ATA chapters carry no cell content
        # at all -- see module docstring.
        if not (rec["ATA"] or rec["DESCRIPTION"] or rec["PART_NUMBER"] or rec["SERIAL_NUMBER"]):
            continue
        out.append(rec)
    return out


_HEADER_FIELDS = ("AIRCRAFT_FH", "AIRCRAFT_FC", "REPORT_DATE",
                   "AIRCRAFT_REG", "MSN", "AIRCRAFT_TYPE")


async def _parse_header_meta(img: Image.Image) -> dict:
    """Page-1 header info box (A/F FH, A/F FC, Report Date -- left column;
    A/C Reg, MSN, A/C Type -- right column). OCR'd as two narrow
    value-only column crops rather than the whole box at once: the two
    label columns' own text visually interleaves at this crop width
    (confirmed directly -- a whole-box OCR pass drops/garbles the labels),
    but each value-only strip (positioned clear of both label columns)
    reads cleanly in a fixed top-to-bottom order."""
    meta = {k: "" for k in _HEADER_FIELDS}
    w, h = img.size
    left_crop = img.crop((int(w * 0.30), int(h * 0.08), int(w * 0.40), int(h * 0.125)))
    right_crop = img.crop((int(w * 0.55), int(h * 0.08), int(w * 0.85), int(h * 0.125)))
    left_text = await ocr_text(left_crop, psm=6)
    right_text = await ocr_text(right_crop, psm=6)
    left_lines = [ln.strip() for ln in left_text.splitlines() if ln.strip()]
    right_lines = [ln.strip() for ln in right_text.splitlines() if ln.strip()]
    if len(left_lines) >= 3:
        meta["AIRCRAFT_FH"], meta["AIRCRAFT_FC"], meta["REPORT_DATE"] = left_lines[:3]
    if len(right_lines) >= 3:
        meta["AIRCRAFT_REG"], meta["MSN"], meta["AIRCRAFT_TYPE"] = right_lines[:3]
    return meta


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback (see
    sheet_types/occm.py) -- this variant's known source file has no text
    layer at all, so it can never be found through the normal pdfplumber
    head-text match.

    Requires BOTH the report's own title-line phrase ("OCCM COMPONENTS
    STATUS") and its own column-header words ("INSTALL DATE" + "POSITION"),
    all three present anywhere in the same top-of-page crop (not required
    contiguous: the column-header band's own two-line-wrapped "INSTALL
    DATE ON\nAIRCRAFT" cell was confirmed directly to sometimes OCR with
    its "AIRCRAFT" fragment reordered relative to neighbouring cells at
    this psm, so an exact-phrase match on "INSTALL DATE ON AIRCRAFT" is
    NOT used here -- three independently-checked substrings are more
    robust). Checked directly (grep across every SIGNATURES list in
    sheet_types/{occm,ht,llp}.py and every existing occm_variants/
    ht_variants/llp_variants module, plus every module's own ocr_detect()
    anchor text): no other module's own SIGNATURES/ocr_detect anchor
    requires this same three-way combination. The bare title phrase alone
    would not have been safe to use: it is a prefix substring of
    occm_status_list.py's own SIGNATURES entry "OCCM COMPONENTS STATUS
    LIST" (a *born-digital*, non-OCR module -- never actually reachable
    through this router's OCR-fallback loop -- but not reused bare here
    regardless, per this project's convention of keeping ocr_detect
    anchors self-evidently distinct from any sibling's own SIGNATURES
    text). It is also NOT a match for occm_component_status_posn_fin.py's
    own anchor phrase "COMPONENT STATUS" (singular COMPONENT): the
    character immediately after "COMPONENT" differs ("S" here vs a space
    there), so neither containment direction holds, and that module's
    own ocr_detect additionally requires a `<reg> (<type>)`-shaped title
    line that this report's own label:value header box never produces.
    Also checked directly against aircraft_occm_components_status_scanned
    .py's own anchor ("AIRCRAFT" + "OC/CM" + "COMPONENTS" + "STATUS"):
    this report's title band has no "AIRCRAFT" and no "OC/CM" (it renders
    "OCCM", one word, no slash), so that anchor cannot fire here either.
    "INSTALL DATE" and "POSITION" individually both appear in several
    other modules' own module-docstring column-shape descriptions (e.g.
    occm_report_scanned.py, occm_list_as_at.py), but none of those
    modules' own ocr_detect() anchors (checked directly, see above) test
    for either word at all, let alone combined with this report's own
    title phrase, so no collision risk in practice.
    """
    try:
        img = await render_page(pdf_path, 0, dpi=300)
        w, h = img.size
        # Title band: narrow crop, confirmed to OCR cleanly on its own.
        title_crop = img.crop((0, 0, w, int(h * 0.10)))
        title_text = (await ocr_text(title_crop, psm=6)).upper()
        if "OCCM COMPONENTS STATUS" not in " ".join(title_text.split()):
            return False
        # Shaded column-header band: a full-width crop at this height was
        # confirmed directly to garble this band into noise (too little
        # dark content relative to the wide empty margins either side
        # confuses tesseract's own block segmentation at this psm) -- an
        # x-restricted crop (found the same way `extract()` finds the
        # table's own column dividers) OCRs it cleanly instead.
        arr = np.array(img.convert("L"))
        header_bottom = _find_header_bottom(arr)
        if header_bottom is None:
            return False
        darkfrac = (arr < _DARK_PIXEL_THRESH).mean(axis=1)
        band_top_limit = int(h * _HEADER_BAND_MAX_TOP_FRAC)
        ys = np.where(darkfrac[:band_top_limit] > _HEADER_DARKFRAC_THRESH)[0]
        groups = [g for g in _merge_dark_groups(ys) if g[1] - g[0] > _HEADER_BAND_MIN_HEIGHT]
        if not groups:
            return False
        band_top = groups[-1][0]
        col_lines = _find_col_lines(arr, header_bottom)
        if len(col_lines) < 2:
            return False
        hdr_crop = img.crop((col_lines[0] - 2, band_top - 2, col_lines[-1] + 10, header_bottom + 5))
        hdr_text = (await ocr_text(hdr_crop, psm=6)).upper()
        normed_hdr = " ".join(hdr_text.split())
        return "INSTALL DATE" in normed_hdr and "POSITION" in normed_hdr
    except Exception:
        return False


async def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    header_meta = {k: "" for k in _HEADER_FIELDS}
    n_pages = await page_count(pdf_path)
    for page_index in range(n_pages):
        # 400 DPI (vs. this module's own ocr_detect()'s cheaper 300 DPI
        # page-1-only check): confirmed directly, side by side, to recover
        # visibly more PART_NUMBER/SERIAL_NUMBER/POSITION characters
        # correctly on the small-font POSITION column especially (see
        # module docstring "Known limitation") than 300 DPI, at an
        # acceptable per-page OCR cost.
        img = await render_page(pdf_path, page_index, dpi=400)
        if page_index == 0:
            header_meta = await _parse_header_meta(img)
        page_records = await _ocr_page_rows(img)
        for rec in page_records:
            rec.update(header_meta)
            rec["_page"] = page_index + 1
            records.append(rec)
    return records
