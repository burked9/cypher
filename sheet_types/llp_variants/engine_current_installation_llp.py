"""Engine "Current Installation Data" LLP status report -- single-page,
per-engine (V2500-family style) life-limited-parts status sheet. Confirmed
on the one known sample file (a flattened raster page embedded as a single
JPEG image, 0-char text layer, no vector drawings -- checked directly via
`page.get_text()`/`page.get_images()`/`page.get_drawings()`), so this
module renders and OCRs via `shared/ocr_bridge.py`'s async primitives
(`render_page()`/`ocr_text()`/`ocr_words()`) exactly like the other
OCR-only LLP variants (e.g. `kalstar_engine_llp_status.py`,
`part_m_engine_disk_sheet.py`) rather than touching fitz/pytesseract
directly, so the same code also runs under Pyodide via the JS bridge.

Header layout (values below are placeholders, never real figures from the
known sample)::

    <operator logo>   <esn side, e.g. "L/H"> Engine S/N: <esn> LLPs   | Current Installation Data
                                                          A/C: <ac type> | Rating: <rating>
                                                          MSN : <msn>    | Pos: <position>

    STATUS IS APPLICABLE ON:            <date>      | LSV Dated    | TFH at LSV | TSLV
    ENGINE TOTAL FLIGHT HOURS (TFH):    <hh:cc>     | <date>       | <hh:cc>    | <hh:cc>
    ENGINE TOTAL FLIGHT CYCLES (TFC):   <n>          |              | TFC at LSV | CSLV
                                                                     | <n>        | <n>

The title/rating box and the STATUS/LSV box are parsed by cropping each to
its own narrow band and OCR'ing it in isolation, NOT as one flattened OCR
pass over the whole header -- confirmed directly on the one known sample
that a single wide `ocr_text()` pass over the combined header silently
drops the "A/C:"/"MSN:"/"Pos:" line and the entire right-hand LSV box
(Tesseract's own layout analysis gives up on the two side-by-side
sub-tables and returns nothing for the right one, even though the same
pixels read perfectly once cropped down to just that box -- confirmed by
directly comparing whole-header vs isolated-box OCR output on the same
render). The right-hand LSV box goes a step further: even in isolation,
whole-block OCR (`ocr_text()` at every page-segmentation mode tried)
returns nothing at all for it, while the same pixels read perfectly once
each of its cells is OCR'd individually against grid lines detected by
pixel-darkness (mirroring the ruled-grid detection the data table itself
needs) -- so the LSV box is parsed cell-by-cell, not as flattened text
like the title box and the STATUS box (both of which DO tolerate an
isolated flattened-text regex pass).

Row shape: MODULE section headers (e.g. a shaded banner naming an engine
module) each followed by zero or more part rows of::

    PART_DESCRIPTION | PART_NUMBER | SERIAL_NUMBER | DATE_OF_INSTALLATION |
    <install-time engine hours/cycles pair> |
    <install-time component hours/cycles pair> |
    <current engine hours/cycles pair> |
    LIFE_LIMIT | LIFE_REMAINING | STATUS | REMARKS

Confirmed by direct inspection of the one known sample: this is a fully
ruled ("boxed") grid -- ruled-grid detection (row/column lines found by
scanning for near-continuous dark pixel runs, the same technique
`part_m_engine_disk_sheet.py` uses) recovers exactly 14 columns (13
internal dividers plus the two outer edges) and one row-band per
module-header/part row, with NO skew problem (unlike
`kalstar_engine_llp_status.py`'s sample, a full-width horizontal-line scan
here already gives clean, precisely-spaced row boundaries with no need for
a narrow-column-interior rescan). One genuinely blank spacer row-band sits
between the column-header row and the first module banner in the known
sample; it is skipped automatically because its own PART_DESCRIPTION cell
OCRs empty, the same test used to distinguish a real part row from a
module-header row (see below) -- no special-case handling was needed.

Module-header vs part-row disambiguation: a module-header banner spans
the full row width with no per-column content, so its own PART_NUMBER
cell is blank (or, once, OCR noise bled in from the banner's background
shading -- confirmed directly on the known sample: a shaded banner row's
PART_NUMBER cell OCR'd as a short two-letter fragment, not a real part
number). Rather than trust "cell is non-empty" as the signal, a row only
counts as a real part row when its PART_NUMBER cell OCRs to something
matching this format's actual part-number shape (letter+digit clusters,
4-10 characters after stripping non-alnum) -- confirmed against every
part row in the known sample, and confirmed to correctly reject the
shading-noise banner row that a bare non-empty check would have
misattributed as a data row.

Numeric cells (the three hours/cycles pairs, LIFE_LIMIT, LIFE_REMAINING)
are OCR'd with a digit whitelist and single-line PSM; STATUS/REMARKS are
free text and use a block PSM instead, since the one known sample's sole
populated REMARKS cell wraps onto two lines -- confirmed directly that
the single-line PSM truncates it to nothing while the block PSM recovers
it in full.

Blank-cell false-positive fix: STATUS/REMARKS cells that are genuinely
blank were confirmed, on direct pixel inspection, to sometimes carry a
thin non-black rule-color sliver bleeding in from an adjacent cell's own
border coloring (visible as a faint vertical line, well above black but
still just dark enough that Tesseract hallucinated stray punctuation-like
glyphs from it on an otherwise textless crop). Fix: before OCR'ing any
cell, check whether it contains at least a handful of genuinely dark
pixels (a much stricter threshold than the one used for grid-line
detection, since grid rules and body text are both "dark" but this sliver
is not); a cell with no such pixels is treated as blank text without ever
invoking OCR on it. Confirmed to eliminate every instance of this noise
across the known sample's STATUS column (uniformly blank) and the 24
genuinely-blank REMARKS cells, while still recovering the one populated
REMARKS cell (which has plenty of real dark ink) unaffected.

Header metadata (ENGINE_SERIAL_NUMBER, RATING, POSITION, AIRCRAFT_TYPE,
AIRCRAFT_MSN, STATUS_DATE, ENGINE_TFH, ENGINE_TFC, LSV_DATE, TFH_AT_LSV,
TSLV, TFC_AT_LSV, CSLV) is parsed once per file and stamped onto every
row, mirroring every other multi-section LLP variant in this project
(e.g. `powerplant_maintenance_center_llp_status.py`). MODULE_NAME is
forward-filled from the most recent module-header banner onto every part
row beneath it the same way.

No numeric sub-block in this format required folding into a catch-all
STATUS_TRAIL column: the ruled grid gives every one of the three
hours/cycles pairs (and LIFE_LIMIT/LIFE_REMAINING) its own unambiguous
column, confirmed against every row of the one known sample -- unlike the
free-text-column-position guessing problem other LLP variants document,
a real ruled grid boundary is not a "guess."

Only one sample file is known. Every hardcoded pixel fraction/threshold
below is confirmed against that file directly (not guessed), but -- as
with every other single/few-sample OCR variant in this project -- may
need adjustment the day a second real sample of this exact template
turns up.
"""
from __future__ import annotations
import re

import numpy as np

from sheet_types.llp_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, ocr_words

NAME = "Engine Current Installation Data LLP Status"

# No text layer on the one known source file (0 chars, single embedded
# JPEG image, no vector drawings -- confirmed directly), so SIGNATURES is
# deliberately empty and detection happens purely via ocr_detect() below,
# mirroring kalstar_engine_llp_status.py's own reasoning.
SIGNATURES: list[str] = []

CANONICAL_COLUMNS = [
    "MODULE_NAME",
    "PART_DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DATE_OF_INSTALLATION",
    "INSTALL_ENGINE_HOURS",
    "INSTALL_ENGINE_CYCLES",
    "INSTALL_COMPONENT_HOURS",
    "INSTALL_COMPONENT_CYCLES",
    "CURRENT_HOURS",
    "CURRENT_CYCLES",
    "LIFE_LIMIT",
    "LIFE_REMAINING",
    "STATUS",
    "REMARKS",
    # File-level header metadata -- same on every row of a given file.
    "ENGINE_SERIAL_NUMBER",
    "RATING",
    "POSITION",
    "AIRCRAFT_TYPE",
    "AIRCRAFT_MSN",
    "STATUS_DATE",
    "ENGINE_TFH",
    "ENGINE_TFC",
    "LSV_DATE",
    "TFH_AT_LSV",
    "TSLV",
    "TFC_AT_LSV",
    "CSLV",
]

_INT_RULE = {"pattern": r"^\d*$", "allow_empty": True,
             "int_range": (0, 200000), "int_range_review": (0, 100000)}
_HHMM_RULE = {"pattern": r"^\d*:?\d*$", "allow_empty": True}
_DATE_SLASH_RULE = {"pattern": r"^(\d{2}/\d{2}/\d{4})?$", "allow_empty": True}
_DATE_DASH_RULE = {"pattern": r"^(\d{1,2}-[A-Za-z]{3,9}-\d{2,4})?$", "allow_empty": True}
_OVERRIDES = {
    "MODULE_NAME":              {"allow_empty": True},
    "PART_NUMBER":              {"pattern": r"^[A-Z0-9]{4,12}$", "uppercase": True},
    "SERIAL_NUMBER":            {"pattern": r"^[A-Z0-9]{3,15}$", "uppercase": True},
    "DATE_OF_INSTALLATION":     _DATE_SLASH_RULE,
    "INSTALL_ENGINE_HOURS":     _INT_RULE,
    "INSTALL_ENGINE_CYCLES":    _INT_RULE,
    "INSTALL_COMPONENT_HOURS":  _INT_RULE,
    "INSTALL_COMPONENT_CYCLES": _INT_RULE,
    "CURRENT_HOURS":            _INT_RULE,
    "CURRENT_CYCLES":           _INT_RULE,
    "LIFE_LIMIT":               _INT_RULE,
    "LIFE_REMAINING":           _INT_RULE,
    "STATUS":                  {"pattern": r"^[A-Z ]*$", "uppercase": True, "allow_empty": True},
    "REMARKS":                 {"allow_empty": True},
    "ENGINE_SERIAL_NUMBER":    {"pattern": r"^[A-Z0-9]*$", "uppercase": True, "allow_empty": True},
    "RATING":                  {"pattern": r"^[A-Z0-9\-]*$", "uppercase": True, "allow_empty": True},
    "POSITION":                {"allow_empty": True},
    "AIRCRAFT_TYPE":           {"pattern": r"^[A-Z0-9\-]*$", "uppercase": True, "allow_empty": True},
    "AIRCRAFT_MSN":            {"pattern": r"^\d*$", "allow_empty": True},
    "STATUS_DATE":              _DATE_DASH_RULE,
    "ENGINE_TFH":               _HHMM_RULE,
    "ENGINE_TFC":               _INT_RULE,
    "LSV_DATE":                 _DATE_DASH_RULE,
    "TFH_AT_LSV":               _HHMM_RULE,
    "TSLV":                     _HHMM_RULE,
    "TFC_AT_LSV":               _INT_RULE,
    "CSLV":                     _INT_RULE,
}
RULES = merged_rules(_OVERRIDES)

_DPI = 300
_DARK_THRESH = 200
_LINE_FRAC = 0.5
_N_TABLE_COLS = 14

# Strict darkness threshold used only to decide whether a cell has any
# real ink worth OCR'ing at all (see module docstring's note on the
# rule-color-sliver false positive) -- deliberately much stricter than
# _DARK_THRESH, which is tuned for grid-line detection, not glyph
# presence.
_GLYPH_THRESH = 150
_GLYPH_MIN_PIXELS = 8

_PN_RE = re.compile(r"^[A-Z0-9]{4,10}$")
_ALNUM_RE = re.compile(r"[A-Z0-9]")
_DIGITS = "0123456789"


def _line_groups(frac: np.ndarray, thresh: float) -> list[int]:
    idx = np.where(frac > thresh)[0]
    if not len(idx):
        return []
    groups, cur = [], [idx[0]]
    for v in idx[1:]:
        if v - cur[-1] <= 3:
            cur.append(v)
        else:
            groups.append(cur)
            cur = [v]
    groups.append(cur)
    return [int(np.mean(g)) for g in groups]


def _longest_dense_run(lines: list[int], max_gap: int = 150, min_run: int = 10) -> tuple[int, int] | None:
    """The data table is a dense run of closely-spaced ruled lines; the
    header info-boxes above it have the same kind of ruled lines but far
    sparser. Find the longest run of consecutive lines whose gaps all
    stay under `max_gap`, rather than hardcoding where the table starts
    (mirrors `part_m_engine_disk_sheet.py`'s identical helper)."""
    if len(lines) < min_run:
        return None
    gaps = [b - a for a, b in zip(lines[:-1], lines[1:])]
    best_start, best_len, cur_start, cur_len = 0, 0, 0, 0
    for i, g in enumerate(gaps):
        if g < max_gap:
            if cur_len == 0:
                cur_start = i
            cur_len += 1
        else:
            if cur_len > best_len:
                best_start, best_len = cur_start, cur_len
            cur_len = 0
    if cur_len > best_len:
        best_start, best_len = cur_start, cur_len
    if best_len < min_run:
        return None
    return lines[best_start], lines[best_start + best_len]


def _detect_table_grid(gray: np.ndarray) -> tuple[list[int], list[int]] | None:
    """Returns (h_lines, v_lines): row-band boundaries and the 15 vertical
    grid-line x-positions (14 columns). Returns None if the grid can't be
    confirmed -- no guessed fallback."""
    dark = gray < _DARK_THRESH
    full_h_lines = _line_groups(dark.mean(axis=1), _LINE_FRAC)
    band = _longest_dense_run(full_h_lines)
    if band is None:
        return None
    y0, y1 = band
    h_lines = [y for y in full_h_lines if y0 <= y <= y1]
    v_lines = _line_groups(dark[y0:y1, :].mean(axis=0), _LINE_FRAC)
    if len(v_lines) != _N_TABLE_COLS + 1:
        return None
    return h_lines, v_lines


def _is_blank(arr: np.ndarray) -> bool:
    return bool((arr < _GLYPH_THRESH).sum() < _GLYPH_MIN_PIXELS)


async def _cell_text(img, y0: int, y1: int, x0: int, x1: int, pad: int = 6,
                      psm: int = 7, whitelist: str | None = None) -> str:
    crop = img.crop((x0 + pad, y0 + pad, x1 - pad, y1 - pad))
    gray = np.array(crop.convert("L"))
    if _is_blank(gray):
        return ""
    return (await ocr_text(crop, psm=psm, whitelist=whitelist)).strip()


def _clean_alnum(raw: str) -> str:
    return "".join(c for c in raw.upper() if _ALNUM_RE.match(c))


def _clean_digits(raw: str) -> str:
    return re.sub(r"[^0-9]", "", raw)


async def _parse_title_box(img) -> dict:
    """Title/rating box -- confirmed on the known sample to OCR cleanly as
    flattened text once cropped to just this band (see module docstring
    for why the header can't be OCR'd as one wide pass)."""
    w, h = img.size
    crop = img.crop((0, int(h * 0.0843), w, int(h * 0.1464)))
    text = (await ocr_text(crop, psm=6)).upper()

    meta: dict[str, str] = {}

    def grab(pat: str, key: str, clean=lambda s: s.strip()):
        m = re.search(pat, text, re.I)
        if m:
            meta[key] = clean(m.group(1))

    grab(r"ENGINE\s*S/N\s*:?\s*([A-Z0-9]+)\s*LLPS", "ENGINE_SERIAL_NUMBER")
    grab(r"LLPS.*?([A-Z0-9]{3,4}-\d{2,3})\s*\|?\s*RATING", "AIRCRAFT_TYPE")
    grab(r"RATING\s*:?\s*\|?\s*([A-Z0-9\-]+)", "RATING")
    grab(r"MSN\s*:?\s*\|?\s*(\d+)", "AIRCRAFT_MSN")
    grab(r"POS\s*:?\s*\|?\s*([A-Z0-9\- ]+?)(?:\||$)", "POSITION", lambda s: re.sub(r"\s+", " ", s).strip())
    return meta


async def _parse_status_box(img) -> dict:
    """STATUS IS APPLICABLE ON / ENGINE TOTAL FLIGHT HOURS+CYCLES box (left
    half of the header's second band) -- also OCRs cleanly as flattened
    text once isolated to its own half-width crop."""
    w, h = img.size
    crop = img.crop((0, int(h * 0.1464), int(w * 0.45), int(h * 0.2136)))
    text = await ocr_text(crop, psm=6)

    meta: dict[str, str] = {}

    def grab(pat: str, key: str):
        m = re.search(pat, text, re.I)
        if m:
            meta[key] = m.group(1).strip()

    grab(r"STATUS IS APPLICABLE ON:?\s*([\d\-A-Za-z]+)", "STATUS_DATE")
    grab(r"ENGINE TOTAL FLIGHT HOURS\s*\(TFH\):?\s*([\d:,\.]+)", "ENGINE_TFH")
    grab(r"ENGINE TOTAL FLIGHT CYCLES\s*\(TFC\):?\s*([\d,]+)", "ENGINE_TFC")
    return meta


async def _parse_lsv_box(img) -> dict:
    """LSV Dated / TFH at LSV / TSLV / TFC at LSV / CSLV box (right half of
    the header's second band). Unlike the title and STATUS boxes, this one
    could not be recovered as flattened text at all (every PSM tried
    returned nothing for it, even in isolation -- see module docstring),
    so it's parsed cell-by-cell against its own detected ruled grid
    instead, the same fallback the main data table itself uses."""
    arr = np.array(img.convert("L"))
    dark = arr < _DARK_THRESH
    h, w = arr.shape
    # Row-line search band deliberately stops just short of 0.2136 (the
    # fraction used elsewhere for this header band's overall bottom) --
    # confirmed directly on the known sample that extending all the way to
    # 0.2136 picks up one extra stray line belonging to the *next* section
    # (the main table's own column-header top border sits just below this
    # box), which would throw off the expected 5-line row count.
    y0, y1 = int(h * 0.1464), int(h * 0.205)

    # Row lines: found from a vertical dark-pixel scan restricted to an
    # x-band confirmed (on the known sample) to sit inside this box's own
    # right-hand columns.
    x_lo, x_hi = int(w * 0.545), int(w * 0.698)
    row_lines = _line_groups(dark[y0:y1, x_lo:x_hi].mean(axis=1), 0.7)
    row_lines = [r + y0 for r in row_lines]
    if len(row_lines) != 5:
        return {}
    r0, r1, r2, r3, r4 = row_lines

    # Column lines: found from a horizontal dark-pixel scan restricted to
    # this box's own top TWO row-bands (header row + first value row).
    # Confirmed directly on the known sample that this box's leftmost
    # column rule only runs across those top two bands -- the bottom two
    # bands' leftmost cell is a merged blank cell there, so its own
    # left-edge rule doesn't extend down that far, and restricting the
    # scan to r0:r2 (rather than the full r0:r4 box height) is what
    # recovers that left edge as a clean line instead of a sub-threshold
    # partial one.
    col_lines = _line_groups(dark[r0:r2, x_lo - 500:x_hi + 20].mean(axis=0), 0.7)
    col_lines = [c + x_lo - 500 for c in col_lines]
    if len(col_lines) != 4:
        return {}
    c0, c1, c2, c3 = col_lines

    lsv_date = await _cell_text(img, r1, r2, c0, c1)
    tfh_at_lsv = await _cell_text(img, r1, r2, c1, c2)
    tslv = await _cell_text(img, r1, r2, c2, c3)
    tfc_at_lsv = await _cell_text(img, r3, r4, c1, c2)
    cslv = await _cell_text(img, r3, r4, c2, c3)
    return {
        "LSV_DATE": lsv_date,
        "TFH_AT_LSV": tfh_at_lsv,
        "TSLV": tslv,
        "TFC_AT_LSV": tfc_at_lsv,
        "CSLV": cslv,
    }


_TITLE_ANCHOR = "STATUS IS APPLICABLE ON"
_BOX_ANCHOR = "CURRENT INSTALLATION DATA"


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 header OCR check for the router's blank-text fallback.
    Requires BOTH anchor phrases together (checked directly against every
    SIGNATURES list in sheet_types/{occm,ht,llp}.py and every existing
    variant file/ocr_detect(): no collision found for either phrase alone,
    but requiring both is cheap insurance against a future single-phrase
    collision)."""
    try:
        img = await render_page(pdf_path, 0, dpi=_DPI)
        crop = img.crop((0, 0, img.width, int(img.height * 0.22)))
        text = (await ocr_text(crop, psm=6)).upper()
        return _TITLE_ANCHOR in text and _BOX_ANCHOR in text
    except Exception:
        return False


async def extract(pdf_path: str) -> list[dict]:
    img = await render_page(pdf_path, 0, dpi=_DPI)
    gray = np.array(img.convert("L"))

    grid = _detect_table_grid(gray)
    if grid is None:
        return []
    h_lines, v_lines = grid

    meta: dict[str, str] = {}
    meta.update(await _parse_title_box(img))
    meta.update(await _parse_status_box(img))
    meta.update(await _parse_lsv_box(img))

    records: list[dict] = []
    current_module = ""
    for i in range(len(h_lines) - 1):
        ry0, ry1 = h_lines[i], h_lines[i + 1]

        desc = await _cell_text(img, ry0, ry1, v_lines[0], v_lines[1])
        if not desc:
            continue

        pn_raw = await _cell_text(img, ry0, ry1, v_lines[1], v_lines[2])
        pn = _clean_alnum(pn_raw)
        if not _PN_RE.match(pn):
            # No real part number in this row's PN cell -> this is a
            # MODULE section banner, not a part row (see module docstring
            # for why a bare non-empty check isn't safe here).
            current_module = desc
            continue

        sn = _clean_alnum(await _cell_text(img, ry0, ry1, v_lines[2], v_lines[3]))
        date = (await _cell_text(img, ry0, ry1, v_lines[3], v_lines[4])).strip()
        install_eng_h = _clean_digits(await _cell_text(img, ry0, ry1, v_lines[4], v_lines[5], whitelist=_DIGITS))
        install_eng_c = _clean_digits(await _cell_text(img, ry0, ry1, v_lines[5], v_lines[6], whitelist=_DIGITS))
        install_comp_h = _clean_digits(await _cell_text(img, ry0, ry1, v_lines[6], v_lines[7], whitelist=_DIGITS))
        install_comp_c = _clean_digits(await _cell_text(img, ry0, ry1, v_lines[7], v_lines[8], whitelist=_DIGITS))
        current_h = _clean_digits(await _cell_text(img, ry0, ry1, v_lines[8], v_lines[9], whitelist=_DIGITS))
        current_c = _clean_digits(await _cell_text(img, ry0, ry1, v_lines[9], v_lines[10], whitelist=_DIGITS))
        life_limit = _clean_digits(await _cell_text(img, ry0, ry1, v_lines[10], v_lines[11], whitelist=_DIGITS))
        life_remaining = _clean_digits(await _cell_text(img, ry0, ry1, v_lines[11], v_lines[12], whitelist=_DIGITS))
        status = (await _cell_text(img, ry0, ry1, v_lines[12], v_lines[13], psm=6)).strip().upper()
        remarks = (await _cell_text(img, ry0, ry1, v_lines[13], v_lines[14], psm=6)).strip()

        rec = {c: "" for c in CANONICAL_COLUMNS}
        rec["MODULE_NAME"] = current_module
        rec["PART_DESCRIPTION"] = desc
        rec["PART_NUMBER"] = pn
        rec["SERIAL_NUMBER"] = sn
        rec["DATE_OF_INSTALLATION"] = date
        rec["INSTALL_ENGINE_HOURS"] = install_eng_h
        rec["INSTALL_ENGINE_CYCLES"] = install_eng_c
        rec["INSTALL_COMPONENT_HOURS"] = install_comp_h
        rec["INSTALL_COMPONENT_CYCLES"] = install_comp_c
        rec["CURRENT_HOURS"] = current_h
        rec["CURRENT_CYCLES"] = current_c
        rec["LIFE_LIMIT"] = life_limit
        rec["LIFE_REMAINING"] = life_remaining
        rec["STATUS"] = status
        rec["REMARKS"] = remarks
        for k, v in meta.items():
            rec[k] = v
        rec["_page"] = 1
        records.append(rec)
    return records
