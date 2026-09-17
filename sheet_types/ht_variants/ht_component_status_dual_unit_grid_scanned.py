"""HT COMPONENT STATUS -- scanned (full-page raster image, CCITT G4 fax
encoded, no text layer at all -- confirmed directly on the sample file:
`page.get_text()` returns `""` on every page and `page.get_images()` shows
a single full-page `CCITTFaxDecode` image object per page with zero vector
drawings).

Ruled/bordered grid, 15 columns, left to right::

    ATA | TASK | DESCRIPTION | P/N | S/N | POS |
    FREQUENCY | (unit) | DATE OF INSTALLATION | DATE OF RELEASE CERTIFICATE |
    SINCE NEW OR LAST SHOP VISIT | REMAINING | PROYECTED A/C (FH, FC or Date) | (unit) |
    WORK/REMARK

("PROYECTED" is the sheet's own spelling, not a transcription error here.)

Row grain is genuinely two-level and NOT uniform, confirmed directly by
rendering the sample file at 300dpi and inspecting the ruled cell borders
with numpy darkness-fraction scans (not guessed from word positions):
every tracked component prints as one OR MORE physical grid rows sharing
one tracking basis each (typically an "FH" row plus a "DY" row, sometimes
a third "FC" row) -- ATA/TASK/DESCRIPTION/P/N/S/N/POS/the two DATE
columns/WORK-REMARK are rendered as a single cell VERTICALLY MERGED across
however many basis-rows that component has (no inner horizontal rule
inside the merge), while FREQUENCY/unit/SINCE.../REMAINING/PROYECTED
value/unit always carry one distinct value per physical row. Critically,
which of the merge-eligible columns are actually merged for a given
component is not fixed -- confirmed directly on the sample file: most
components merge WORK/REMARK across all of their own basis-rows (e.g. one
"RESTORE" spanning an FH row and a DY row), but at least one component
(ATA 24 "MAIN BATTERY", two S/N instances) prints a DIFFERENT TASK code
and a different WORK/REMARK value ("OVERHAUL" vs "CHECK") on each of its
own two basis-rows while still merging ATA/DESCRIPTION/P/N/S/N/POS across
them. No column's merge behaviour is hard-coded here as a result -- see
`_own_lines()` below.

Column x-boundaries and row y-boundaries are both recovered structurally
from the rendered page raster (numpy darkness-fraction scans along each
axis), never guessed from OCR word positions, per this project's own
"never guess a wrong split" rule for ruled scanned grids:

  * Column x-boundaries: full-height vertical lines (darkness fraction
    over the whole table's own y-span > 0.5), confirmed to reproduce the
    same 15-column layout (16 boundary lines) seen in the column-header
    row on every one of the sample file's 5 pages, with only a few pixels
    of page-to-page scan jitter.
  * A fixed reference x-boundary list (`_REF_COL_X`, averaged from two of
    the sample file's own cleanest pages) is used as a fallback whenever a
    given page's own vertical-line count doesn't match the expected 16 --
    confirmed this only ever happens from a stray extra/missing detection
    right at the page margin, never from an actual layout difference
    between pages.
  * Row y-boundaries: the FREQUENCY column's own horizontal dividers
    (darkness fraction within that column's x-range only) are used as the
    canonical one-row-per-physical-basis-row grid (`_anchor_lines()`),
    confirmed on every page of the sample file to reproduce exactly the
    expected physical row count (cross-checked directly against a manual
    row count from the rendered page images: 37/43/32/44/13 = 169 total
    across the 5 pages).
  * Every OTHER column's own candidate divider lines (same darkness-scan
    method, restricted to that column's own x-range) are then snapped to
    the nearest FREQUENCY-anchor or whole-table-width line within a small
    pixel tolerance, and any candidate that doesn't land near a trusted
    line is DISCARDED. This is required, not cosmetic -- confirmed
    directly on the sample file: the bold sans-serif font used for
    DESCRIPTION/WORK_REMARK text (e.g. "PROTECTIVE BREATHING EQUIPMENT")
    occasionally produces a coincidental near-full-width dark band at the
    vertical midpoint of an otherwise single-row cell, which the naive
    per-column scan misreads as a real divider and which would otherwise
    silently cut that one cell's text in half.

Cell OCR: each column resolves to a small number of distinct row-bands per
page (a merged column has fewer bands than the anchor grid). Each band is
OCR'd once (not once per anchor row) and the same text is reused for every
anchor row that band covers, which is what reproduces the merge behaviour
described above without hard-coding it. Following this project's own
"per-column-strip OCR over whole-row/whole-page OCR" lesson (confirmed
directly: a whole-page or whole-row OCR pass on this file returns
badly garbled text for the FREQUENCY-through-WORK_REMARK columns, e.g.
stray "ee"/"we"/"[3205" tokens in place of real numbers -- see git history
of this module's own development notes), every cell is crops-and-OCR'd
individually:

  * a small inward inset (avoids the ruled border stroke itself being
    OCR'd as stray punctuation) plus a 2x upscale before OCR, confirmed
    directly to fix a case where the un-padded/non-upscaled crop of a
    clean, legible REMAINING column returned only ~20% of its actual
    values (`pytesseract`/Tesseract's own line-segmentation heuristics
    apparently mis-handle a very narrow, tall, uniform-line-height column
    of short numbers without this treatment -- confirmed on this file's
    own REMAINING column, where a whole-column OCR pass without the
    per-band crop found only 8 of 37 known values on page 1 alone, vs.
    37/37 correct with the per-band crop+inset+upscale approach used
    here).
  * DESCRIPTION and WORK_REMARK use `psm=6` (tolerates an internal text
    wrap within one merged cell, e.g. "ENGINE FIRE EXTINGUISHER
    CARTRIDGES" wrapping across two printed lines inside a single ruled
    cell); every other column uses `psm=7` (single line), both confirmed
    directly against the sample file's own rendered cells.

A signature block (name/title/handwritten date) prints below the ruled
table's own bbox on the final page -- confirmed directly it sits well
outside the table's own row/column boundaries computed above, so it is
never captured by the per-cell OCR crops and no name from that block
reaches any output field. The "DATE:" field in the header info box
(top-right of every page) is handwritten cursive and is not extracted by
this parser at all -- per this project's own rule that handwritten data is
not reliably OCR-recoverable, this parser only reads the printed ruled
data table, not that header box.
"""
from __future__ import annotations
import re

import numpy as np
from PIL import Image

from sheet_types.ht_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, page_count

NAME = "HT Component Status (Dual-Unit Grid, Scanned)"

# Deliberately empty -- every known source file for this template has no
# text layer at all (confirmed: `page.get_text()` returns "" on every
# page, `page.get_images()` shows a single full-page CCITTFaxDecode image
# per page with zero vector drawings). Detected via ocr_detect() instead.
SIGNATURES: list[str] = []

CANONICAL_COLUMNS = [
    "ATA",
    "TASK",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "POS",
    "FREQUENCY",
    "FREQUENCY_UNIT",
    "DATE_OF_INSTALLATION",
    "DATE_OF_RELEASE_CERTIFICATE",
    "SINCE_NEW_OR_LAST_SHOP_VISIT",
    "REMAINING",
    "PROJECTED",
    "PROJECTED_UNIT",
    "WORK_REMARK",
]

_DATE_RE = r"^\d{1,2}-[A-Za-z]{3}-\d{2,4}$"
_NUM_RE = r"^[\d,]+(?:\.\d+)?$"
_UNIT_RE = r"^(?:FH|DY|FC)$"

_OVERRIDES = {
    "TASK": {"allow_empty": True, "uppercase": True},
    "POS": {"allow_empty": True, "uppercase": True},
    "FREQUENCY": {"pattern": r"^\d+$", "allow_empty": True},
    "FREQUENCY_UNIT": {"pattern": _UNIT_RE, "uppercase": True, "allow_empty": True},
    "DATE_OF_INSTALLATION": {"pattern": _DATE_RE, "allow_empty": True},
    "DATE_OF_RELEASE_CERTIFICATE": {"pattern": _DATE_RE, "allow_empty": True},
    "SINCE_NEW_OR_LAST_SHOP_VISIT": {"pattern": _NUM_RE, "allow_empty": True},
    "REMAINING": {"pattern": _NUM_RE, "allow_empty": True},
    # PROJECTED is either a plain number (FH/FC basis) or a date (DY basis
    # -- e.g. "09-Aug-29"), confirmed directly on the sample file.
    "PROJECTED": {"pattern": _NUM_RE + "|" + _DATE_RE, "allow_empty": True},
    "PROJECTED_UNIT": {"pattern": _UNIT_RE, "uppercase": True, "allow_empty": True},
    "WORK_REMARK": {"allow_empty": True, "uppercase": True},
}
RULES = merged_rules(_OVERRIDES)

_COL_NAMES = [
    "ATA", "TASK", "DESCRIPTION", "PART_NUMBER", "SERIAL_NUMBER", "POS",
    "FREQUENCY", "FREQUENCY_UNIT", "DATE_OF_INSTALLATION",
    "DATE_OF_RELEASE_CERTIFICATE", "SINCE_NEW_OR_LAST_SHOP_VISIT",
    "REMAINING", "PROJECTED", "PROJECTED_UNIT", "WORK_REMARK",
]
# Averaged from the sample file's own pages 1-2 vertical-line detections
# at 300dpi (page-to-page jitter is within a few px); used only as a
# fallback when a given page's own detection doesn't find exactly 16
# boundary lines.
_REF_COL_X = [80, 150, 309, 691, 957, 1232, 1351, 1452, 1531, 1783, 2021,
              2261, 2476, 2699, 2756, 3102]

_MULTILINE_COLS = {"DESCRIPTION", "WORK_REMARK"}

_BORDER_RE = re.compile(r"[|\[\]<>=~`]+")
_EDGE_STRIP = " _-|[]=~.\"'"


def _clean_cell_text(s: str) -> str:
    s = _BORDER_RE.sub(" ", s)
    s = " ".join(s.split())
    return s.strip(_EDGE_STRIP)


def _cluster(ys, gap: int = 3) -> list[int]:
    if len(ys) == 0:
        return []
    clusters: list[list[int]] = []
    cur = [ys[0]]
    for y in ys[1:]:
        if y - cur[-1] <= gap:
            cur.append(y)
        else:
            clusters.append(cur)
            cur = [y]
    clusters.append(cur)
    return [int(np.mean(c)) for c in clusters]


def _hlines(dark, x0: int, x1: int, y0: int, y1: int, thresh: float = 0.6) -> list[int]:
    sub = dark[y0:y1, x0:x1]
    if sub.size == 0:
        return []
    row_frac = sub.mean(axis=1)
    ys = np.where(row_frac > thresh)[0] + y0
    return _cluster(ys)


def _vlines(dark, y0: int, y1: int, thresh: float = 0.5) -> list[int]:
    sub = dark[y0:y1, :]
    col_frac = sub.mean(axis=0)
    xs = np.where(col_frac > thresh)[0]
    return _cluster(xs)


def _snap_to_trusted(lines: list[int], trusted: list[int], tol: int = 6) -> list[int]:
    out = []
    for y in lines:
        match = min(trusted, key=lambda t: abs(t - y), default=None)
        if match is not None and abs(match - y) <= tol:
            out.append(match)
    return sorted(set(out))


def _column_bounds(dark, top: int, bottom: int) -> list[tuple[str, int, int]]:
    vlines = _vlines(dark, top, bottom + 1)
    col_x = vlines if len(vlines) == len(_REF_COL_X) else _REF_COL_X
    return list(zip(_COL_NAMES, col_x[:-1], col_x[1:]))


def _table_extent(dark) -> tuple[list[int], int, int, int]:
    row_frac = dark.mean(axis=1)
    hlines = np.where(row_frac > 0.5)[0]
    wide = _cluster(hlines)
    top, bottom = wide[0], wide[-1]
    header_bottom = wide[1] if len(wide) > 1 else top
    return wide, top, bottom, header_bottom


def _own_lines(dark, x0: int, x1: int, header_bottom: int, bottom: int,
                anchor: list[int], trusted: list[int]) -> list[int]:
    lines = _hlines(dark, x0, x1, header_bottom - 3, bottom + 1)
    lines = _snap_to_trusted(lines, trusted)
    if not lines or lines[0] != anchor[0]:
        lines = [anchor[0]] + lines
    if not lines or lines[-1] != anchor[-1]:
        lines = lines + [anchor[-1]]
    return sorted(set(lines))


async def _parse_page(img) -> list[dict]:
    gray = np.array(img.convert("L"))
    dark = gray < 128

    wide, top, bottom, header_bottom = _table_extent(dark)
    if bottom - top < 20:
        return []

    cols = _column_bounds(dark, top, bottom)
    col_x0 = dict((n, x0) for n, x0, _ in cols)
    col_x1 = dict((n, x1) for n, _, x1 in cols)

    anchor = _hlines(dark, col_x0["FREQUENCY"], col_x1["FREQUENCY"],
                      header_bottom - 3, bottom + 1)
    if not anchor or anchor[0] > header_bottom + 5:
        anchor = [header_bottom] + anchor
    if not anchor or anchor[-1] < bottom - 5:
        anchor = anchor + [bottom]
    trusted = sorted(set(anchor) | set(wide))

    own_lines: dict[str, list[int]] = {}
    for name, x0, x1 in cols:
        if name == "FREQUENCY":
            own_lines[name] = anchor
            continue
        own_lines[name] = _own_lines(dark, x0, x1, header_bottom, bottom, anchor, trusted)

    band_text: dict[tuple[str, int, int], str] = {}
    for name, x0, x1 in cols:
        lines = own_lines[name]
        psm = 6 if name in _MULTILINE_COLS else 7
        for i in range(len(lines) - 1):
            lo, hi = lines[i], lines[i + 1]
            if hi - lo < 16:
                band_text[(name, lo, hi)] = ""
                continue
            inset = 8
            crop = img.crop((x0 + inset, lo + inset, x1 - inset, hi - inset))
            if crop.width <= 0 or crop.height <= 0:
                band_text[(name, lo, hi)] = ""
                continue
            crop = crop.resize((crop.width * 2, crop.height * 2), Image.LANCZOS)
            txt = (await ocr_text(crop, psm=psm)).strip()
            band_text[(name, lo, hi)] = _clean_cell_text(txt)

    def lookup(name: str, yc: float) -> str:
        lines = own_lines[name]
        for i in range(len(lines) - 1):
            lo, hi = lines[i], lines[i + 1]
            if lo <= yc <= hi:
                return band_text.get((name, lo, hi), "")
        return ""

    records = []
    for i in range(len(anchor) - 1):
        lo, hi = anchor[i], anchor[i + 1]
        yc = (lo + hi) / 2
        rec = {
            name: (band_text.get((name, lo, hi), "") if name == "FREQUENCY"
                   else lookup(name, yc))
            for name in _COL_NAMES
        }
        records.append(rec)
    return records


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback (see
    sheet_types/ht.py) -- this variant's SIGNATURES is deliberately empty
    (see module docstring).

    Anchors on the report title ("HT COMPONENT STATUS") plus the
    "PROYECTED" column-header word (this sheet's own misspelling of
    "PROJECTED") -- checked against every SIGNATURES list in
    occm.py/ht.py/llp.py and every occm_variants/ht_variants/llp_variants
    module's own SIGNATURES list, plus every other module's own
    `ocr_detect()` anchor text, plus a plain grep across the entire
    project tree for "PROYECTED"; no occurrence found anywhere else. Not a
    substring of, and does not contain as a substring,
    mpd_service_interval_status.py's own "HT ‐ COMPONENT STATUS" (that
    phrase uses a U+2010 hyphen between "HT" and "COMPONENT" plus no
    space; this file's own title has a plain space and no hyphen at all)
    or functional_location_ht_component.py's own "HT-COMPONENT" (ASCII
    hyphen, no "STATUS", no space)."""
    try:
        img = await render_page(pdf_path, 0, dpi=300)
        w, h = img.size
        # Two separate targeted crops rather than one wide pass -- confirmed
        # directly on the sample file that a single wide psm=6 pass over
        # both the title band and the column-header row merges/garbles text
        # from the AIRCRAFT/SERIAL#/MODEL/... info box that sits to the
        # right of the title at the same page height, dropping "PROYECTED"
        # entirely; each of these two narrower crops OCRs cleanly on its
        # own instead.
        title_crop = img.crop((0, int(h * 0.14), int(w * 0.6), int(h * 0.20)))
        title_text = (await ocr_text(title_crop, psm=6)).upper()
        if "COMPONENT STATUS" not in title_text:
            return False
        proj_crop = img.crop((int(w * 0.735), int(h * 0.225), int(w * 0.84), int(h * 0.28)))
        proj_text = (await ocr_text(proj_crop, psm=6)).upper()
        return "PROYECTED" in proj_text
    except Exception:
        return False


async def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    n_pages = await page_count(pdf_path)
    for page_index in range(n_pages):
        img = await render_page(pdf_path, page_index, dpi=300)
        records.extend(await _parse_page(img))
    return records
