""""Life Limited Parts by PN and SN" — a flat EVENT LOG format, not a
snapshot status sheet. Every row is one install/removal event for one
life-limited part (identified by its own PN+SN), not "this part's current
status" — the same physical part typically appears on more than one row
(e.g. an install event, then a later removal event), each with its own
event date/type and the aircraft-position context that applied at that
moment. Confirmed on the one known source file: a single scanned page,
0-char text layer (a clean computer-rendered raster, not a photographed
form), one ruled table with a shaded header row and 2 data rows.

Column order (10 columns, confirmed directly against the rendered page,
left to right)::

    PartNumber | SerialNumber | EventDate | EventType | AC-Reg |
    AircraftType | AC-Serialnumber | LineNumber | CSO | CSN

EventDate is printed `dd-mon-yy` with a free-text 3+ letter month
abbreviation — confirmed NOT always English on the one known file (a
non-English abbreviation was observed), so the date pattern accepts any
alphabetic month token rather than a hardcoded English month list.
EventType is a short free-text status word/phrase (two distinct values
seen on the one known file, e.g. an install-style word and a removal-style
two-word phrase) — per this project's soft-validation convention, this is
NOT treated as a closed enum; RULES only checks it's upper-case-shaped
text, and an unfamiliar value is left alone rather than rejected or
guessed into a known bucket. CSO/CSN are plain non-negative cycle counts.

No page-level metadata block exists on this format (unlike most other LLP
variants in this package) — every field that matters is per-row, so
CANONICAL_COLUMNS carries no separate "file metadata" tail.

Grid detection (mirrors the ruled-grid approach used elsewhere in this
package, e.g. kalstar_engine_llp_status.py's `_table_grid()`): the page
also carries an outer decorative frame (thin border lines running almost
the full page width/height, well outside the table itself) which would
otherwise be misread as extra table rule lines. Two independent guards
against that, both confirmed directly on the one known file: (1) horizontal
rule detection is restricted to a y-band comfortably inside the frame's own
top/bottom bars, and (2) detected vertical lines within a page-edge margin
are dropped before column positions are finalized. The header row's own
shaded background text is dense enough to register as a false horizontal
line at a naive darkness threshold — raising that threshold until only the
genuinely solid ruled lines remain (confirmed directly: header-text-texture
darkness tops out well below the ruled-line darkness fraction) resolved it
without needing a separate text-vs-rule classifier.

Row text is OCR'd per-cell (a modest fixed inward padding off each cell's
own grid-line box, no further tight-cropping to a glyph bounding box) —
tried, and rejected, both alternatives this package's other ruled-grid
variants use: a whole-row strip with column dividers painted out (as
part_m_engine_disk_sheet.py's `_ocr_row_bucketed()` does) reads several
cells as one merged word here whenever two adjacent cells' text sits close
enough together, silently losing one of the two values into a single
bucket; and a glyph-bounding-box tight crop (as
kalstar_engine_llp_status.py's `_tight_crop()` does) confirmed directly to
mis-crop a numeric cell's single digit when that digit's own ink sits
close enough to its cell's right-hand grid line for the bounding-box
margin to clip it. A plain fixed-padding crop, large enough to clear the
grid lines but without any further content-driven cropping, read every
cell correctly on the one known file — including a right-aligned single-
digit cycle count whose own ink sits flush against its cell's grid line,
the exact case the tight-crop approach mis-cropped.

Known limitations, left unresolved rather than guessed at: only one source
file of this exact format has been seen, so column widths/positions are
detected fresh per file (not hardcoded), but the number of columns (10) and
their left-to-right order are assumed stable — if a future file of this
format turns out to have a different column count, `_detect_table_grid()`
returns None (empty result) rather than silently misaligning cells to the
wrong header. And one single trailing digit of PART_NUMBER was confirmed
(directly, against the rendered page) to OCR wrong on one of the two data
rows of the one known file, even though that same part+serial pair's other
row reads correctly — since the two rows' own printed PART_NUMBER values
are expected to usually, but not provably always, agree, silently
"correcting" one from the other risks being wrong in the opposite
direction on a file where they genuinely differ; left as the raw OCR
output rather than patched.
"""
from __future__ import annotations

import re

import numpy as np

from sheet_types.llp_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, page_count

NAME = "Life Limited Parts by PN and SN"

# No text layer on the one known source file (0 chars) -- see module
# docstring. Detection happens purely via ocr_detect() below, mirroring
# kalstar_engine_llp_status.py / part_m_engine_disk_sheet.py's own approach
# for the same reason.
SIGNATURES: list[str] = []

CANONICAL_COLUMNS = [
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "EVENT_DATE",
    "EVENT_TYPE",
    "AIRCRAFT_REG",
    "AIRCRAFT_TYPE",
    "MSN",
    "LINE_NUMBER",
    "CSO",
    "CSN",
]

_INT_RULE = {"pattern": r"^[\d,]*$", "allow_empty": True, "int_range": (0, 99999)}
_OVERRIDES = {
    # dd-<month>-yy(yy): month token left as free alphabetic text rather than
    # a fixed English list -- see module docstring (a non-English month
    # abbreviation was confirmed on the one known file).
    "EVENT_DATE":    {"pattern": r"^\d{1,2}-[A-Za-z]{3,9}-\d{2,4}$", "allow_empty": True},
    # Free-text event word/phrase -- deliberately not a closed enum, see
    # module docstring's note on soft validation for this column.
    "EVENT_TYPE":    {"pattern": r"^[A-Z0-9 /]*$", "uppercase": True, "allow_empty": True},
    "AIRCRAFT_REG":  {"pattern": r"^[A-Z0-9\-]*$", "uppercase": True, "allow_empty": True},
    "AIRCRAFT_TYPE": {"pattern": r"^[A-Za-z0-9\-]*$", "allow_empty": True},
    "MSN":           _INT_RULE,
    "LINE_NUMBER":   _INT_RULE,
    "CSO":           _INT_RULE,
    "CSN":           _INT_RULE,
}
RULES = merged_rules(_OVERRIDES)

_DPI = 300
# Ruled ("hard") lines read well above this darkness fraction on every row
# sampled directly against the one known file; the header row's own shaded-
# background text texture tops out well below it (see module docstring),
# so this single threshold cleanly separates "genuine rule" from "dense but
# non-rule row content" without a separate text/line classifier.
_LINE_FRAC = 0.75
_COL_FRAC = 0.7
# y-band (fraction of page height) searched for horizontal rule lines --
# comfortably inside the page's own outer decorative frame bars (confirmed
# directly to sit close to the very top/bottom of the page on the one known
# file, well outside this band) so those never get mistaken for table rules.
_TABLE_Y_BAND = (0.10, 0.92)
# Margin (fraction of page width) inside which a detected vertical line is
# discarded as outer-frame noise rather than a genuine column divider --
# confirmed directly against the one known file, where the frame's own
# vertical bars sit right at the page edges while every real column divider
# sits well inside this margin.
_EDGE_MARGIN_FRAC = 0.03
_N_COLS = len(CANONICAL_COLUMNS)

_TITLE_TEXT = "LIFE LIMITED PARTS BY PN AND SN"

_ALNUM_DASH_RE = re.compile(r"[A-Za-z0-9\-]+")
_NUM_RE = re.compile(r"[\d,]+")
_DATE_RE = re.compile(r"(\d{1,2}\s*-\s*[A-Za-z]{3,9}\s*-\s*\d{2,4})")


def _collapse_and_dedup(idx: np.ndarray, merge_dist: int = 15) -> list[int]:
    """Collapse a run of adjacent dark rows/cols into one line position, then
    merge lines still within `merge_dist` px of each other -- mirrors
    part_m_engine_disk_sheet.py's helper of the same name."""
    if len(idx) == 0:
        return []
    out, run = [], [int(idx[0])]
    for i in idx[1:]:
        if i - run[-1] <= 3:
            run.append(int(i))
        else:
            out.append(int(np.mean(run)))
            run = [int(i)]
    out.append(int(np.mean(run)))
    merged = [out[0]]
    for x in out[1:]:
        if x - merged[-1] <= merge_dist:
            merged[-1] = int((merged[-1] + x) / 2)
        else:
            merged.append(x)
    return merged


def _detect_table_grid(gray: np.ndarray) -> tuple[list[int], list[int]] | None:
    """Returns (h_lines, v_lines): h_lines are the row-boundary y-positions
    (header-top, header/data divider, then one per data-row boundary);
    v_lines are the _N_COLS+1 column-divider x-positions. Returns None if
    the grid can't be confirmed (wrong line/column count) -- never guessed."""
    h, w = gray.shape
    dark = gray < 150

    y0, y1 = int(h * _TABLE_Y_BAND[0]), int(h * _TABLE_Y_BAND[1])
    row_frac = dark[y0:y1, :].mean(axis=1)
    h_lines = [y0 + y for y in _collapse_and_dedup(np.where(row_frac > _LINE_FRAC)[0])]
    if len(h_lines) < 3:
        # Need at least top + header/data divider + bottom (>=1 data row).
        return None

    col_band = dark[h_lines[1]:h_lines[-1], :]
    col_frac = col_band.mean(axis=0)
    edge = int(w * _EDGE_MARGIN_FRAC)
    v_lines = [x for x in _collapse_and_dedup(np.where(col_frac > _COL_FRAC)[0])
               if edge <= x <= w - edge]
    if len(v_lines) != _N_COLS + 1:
        return None

    return h_lines, v_lines


# Fixed inward padding applied to every cell's own grid-line box before
# OCR -- large enough to clear the ruled lines themselves (confirmed
# directly against the one known file) without any further content-driven
# cropping. See module docstring for why this, not a whole-row strip or a
# glyph-bounding-box tight crop, is used here.
_CELL_PAD = 5
_DIGIT_COLS = {"MSN", "LINE_NUMBER", "CSO", "CSN"}
_DIGITS = "0123456789"


async def _cell_text(img, v_lines: list[int], col_i: int, ry0: int, ry1: int,
                      col_name: str, psm: int = 7) -> str:
    x0, x1 = v_lines[col_i] + _CELL_PAD, v_lines[col_i + 1] - _CELL_PAD
    y0, y1 = ry0 + _CELL_PAD, ry1 - _CELL_PAD
    cell = img.crop((x0, y0, x1, y1))
    whitelist = _DIGITS if col_name in _DIGIT_COLS else None
    text = await ocr_text(cell, psm=psm, whitelist=whitelist)
    return text.strip()


def _clean_alnum(raw: str) -> str:
    m = _ALNUM_DASH_RE.search(raw.upper())
    return m.group(0) if m else ""


def _clean_word(raw: str) -> str:
    return re.sub(r"[^A-Za-z0-9/ ]", "", raw).strip().upper()


def _clean_numeric(raw: str) -> str:
    m = _NUM_RE.search(raw)
    return re.sub(",", "", m.group(0)) if m else ""


def _clean_date(raw: str) -> str:
    m = _DATE_RE.search(raw)
    if not m:
        return raw.strip()
    return re.sub(r"\s*-\s*", "-", m.group(1))


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 title-band OCR check for the router's blank-text
    fallback. Anchors on the document's own printed title phrase (a clean,
    non-decorative text line, unlike the table's own shaded header row --
    confirmed directly to OCR cleanly at this DPI on the one known file)."""
    try:
        img = await render_page(pdf_path, 0, dpi=_DPI)
        crop = img.crop((0, int(img.height * 0.10), img.width, int(img.height * 0.20)))
        text = await ocr_text(crop, psm=6)
        return _TITLE_TEXT in text.upper()
    except Exception:
        return False


async def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    n_pages = await page_count(pdf_path)
    for page_i in range(n_pages):
        img = await render_page(pdf_path, page_i, dpi=_DPI)
        gray = np.array(img.convert("L"))
        grid = _detect_table_grid(gray)
        if grid is None:
            continue
        h_lines, v_lines = grid

        for i in range(len(h_lines) - 2):
            ry0, ry1 = h_lines[i + 1], h_lines[i + 2]
            cells = [await _cell_text(img, v_lines, j, ry0, ry1, col)
                     for j, col in enumerate(CANONICAL_COLUMNS)]

            pn = _clean_alnum(cells[0])
            if not pn:
                continue

            rec = {c: "" for c in CANONICAL_COLUMNS}
            rec["PART_NUMBER"] = pn
            rec["SERIAL_NUMBER"] = _clean_alnum(cells[1])
            rec["EVENT_DATE"] = _clean_date(cells[2])
            rec["EVENT_TYPE"] = _clean_word(cells[3])
            rec["AIRCRAFT_REG"] = _clean_alnum(cells[4])
            rec["AIRCRAFT_TYPE"] = _clean_alnum(cells[5])
            rec["MSN"] = _clean_numeric(cells[6])
            rec["LINE_NUMBER"] = _clean_numeric(cells[7])
            rec["CSO"] = _clean_numeric(cells[8])
            rec["CSN"] = _clean_numeric(cells[9])
            rec["_page"] = page_i + 1
            records.append(rec)
    return records
