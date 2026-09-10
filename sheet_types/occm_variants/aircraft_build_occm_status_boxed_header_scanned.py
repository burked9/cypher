"""Aircraft Build OCCM Status -- scanned, boxed identity-header variant.

Same underlying report template, and the same ruled ATA/Position/Zone/Part
Number/Description/Serial/Last Movement/Batch Number/Unit/Since New-Fit-
Overhaul-Repair data grid, as `aircraft_build_occm_status_scanned.py`
(confirmed directly by rendering a real sample file and comparing side by
side against that module's own documented layout) -- this module's own
known source file reuses that sibling's row-bucketing and record-assembly
logic unchanged (imported below, not duplicated) for the data grid itself.
Three confirmed differences are what earn this its own module rather than
just being routed to the sibling as-is:

1. Header identity block is a genuine two-row *table* (a shaded label row
   -- "Aircraft Reg / Model / MSN / Manufacture Date / Airframe TSN /
   Airframe CSN / Last Flight Date / Last Flight" -- directly followed by
   the values row), not the sibling's own single plain OCR text line
   confirmed directly on its file. OCR-ing the two rows together, or
   together with the surrounding title/option-line text above them (the
   sibling's own approach, which assumes the values sit on the very next
   line after the title), was confirmed directly to fail outright on this
   module's own known source file -- default Tesseract page segmentation
   returns nothing usable across that combined span (checked directly at
   multiple `psm` settings), apparently confused by the shaded label row
   sitting in between. OCR-ing the values row alone, tightly cropped,
   was confirmed directly to read cleanly and completely instead -- so
   this module locates that row itself via the shaded band's own pixel
   footprint (see `_find_label_bands()`) rather than assuming a fixed line
   offset from the title.
2. ZONE cell prints as a two-part decimal code (one digit, a literal ".",
   then two digits) on this module's own known source file, confirmed
   directly by rendering and reading real rows -- not the sibling's own
   plain 1-4 digit code. Same override already used by
   `aircraft_build_occm_status_rotated_scanned.py` for the same confirmed
   reason; the plain digit-only shape is kept as a fallback alternative
   here too rather than dropped, matching that module's own convention.
   That module's own ZONE/PART_NUMBER-merge fix (`_split_zone_partnumber`,
   imported directly here rather than duplicated) applies unchanged too:
   confirmed directly on this module's own known source file, the ZONE and
   PART_NUMBER cells occasionally OCR as a single glued token for the same
   reason as that module's own known source file (no OCR-visible space
   between the cells), landing entirely in the PART_NUMBER bucket with
   ZONE left empty -- the same confirmed-unambiguous "single digit, '.',
   two digits" prefix is safe to peel off here too.
3. POSITION occasionally carries a leading "#" (e.g. a gear-position code
   distinguishing several wheel/brake assemblies on the same ATA line, or
   a lone "#2" on an unrelated cabin-equipment row), confirmed directly by
   rendering and reading real rows -- neither sibling module's own known
   source file uses this form. RULES adds it as an optional prefix on top
   of the sibling's own POSITION shape (see RULES override below) rather
   than loosening the shape rule generally.

Column x-bucket boundaries, row-grouping, ATA/Position-cell splitting, and
the Days/Hours/Landings three-line-per-component assembly are all reused
directly from the sibling module (confirmed directly: this module's own
known source file's rendered grid lines up with the sibling's own
`_BOUNDS` table to within a few pixels, both known source files rendering
at the same 300 DPI and page size) -- only header parsing and the ZONE/
POSITION rules differ here.

SIGNATURES is deliberately empty for the same reason as both siblings:
known source file has 0 pdfplumber-extractable characters on every page,
so this is only ever reached via `ocr_detect()`'s blank-text fallback in
the router. Checked directly (grep across every SIGNATURES list in
sheet_types/{occm,ht,llp}.py and every existing occm_variants/ht_variants/
llp_variants file): no other module's own SIGNATURES entry is the bare
"AIRCRAFT BUILD" phrase either sibling anchors on.

This module's own `ocr_detect()` requires the confirmed-distinctive shaded
"Aircraft Reg" label text in addition to the shared "AIRCRAFT BUILD" title
anchor, specifically so it does not also fire on either sibling's own known
source file (neither of which carries this boxed label row, per point 1
above) -- and it is registered ahead of both siblings in the router's
VARIANTS list (detection returns the first match) so that, should a future
file happen to satisfy both this module's and a sibling's own `ocr_detect`,
the more specific boxed-header check here wins rather than falling through
to a sibling's plain-line header parse, which would silently stamp garbage
metadata onto every row (confirmed directly: this was the actual failure
mode when this module's own known source file was first run through the
sibling module's own header parser -- every row's AIRCRAFT_REG/
AIRCRAFT_TYPE/MSN came back as unrelated OCR noise from the title/option
line above the box, not the real identity values, since that parser's own
"take the line right after the title" assumption doesn't hold here).
"""
from __future__ import annotations

import numpy as np

from sheet_types.occm_variants import aircraft_build_occm_status_scanned as _base
from sheet_types.occm_variants.aircraft_build_occm_status_rotated_scanned import (
    _split_zone_partnumber,
)
from shared.ocr_bridge import render_page, ocr_text, page_count

NAME = "Aircraft Build OCCM Status (Boxed Header Scan)"

# Deliberately empty -- see module docstring.
SIGNATURES = []

# Same column set and row-assembly logic as the sibling -- both parse the
# same underlying report template, just via a differently-shaped header.
CANONICAL_COLUMNS = _base.CANONICAL_COLUMNS

# Own copy of the sibling's RULES (not a shared reference -- mutating it in
# place would also change the sibling module's validation), with the same
# decimal-ZONE override as the rotated sibling (see module docstring point 2).
RULES = dict(_base.RULES)
RULES["ZONE"] = {**RULES.get("ZONE", {}), "pattern": r"^\d{1,2}\.\d{1,2}$|^\d{1,4}$"}
# POSITION: confirmed directly on the real sample file that a "#<n>" or
# "#<n>-<code>" position form is genuinely used for some rows (e.g. wheel/
# brake assemblies distinguished by gear position, "#1"/"#2"/etc, and a
# lone "#2" on a cabin-equipment row) -- neither sibling module's own known
# source file uses this leading "#" form, so it's added here rather than in
# the shared base, as an optional prefix on top of the sibling's own shape
# rather than a full replacement (still rejects anything that wasn't
# already a valid POSITION value once the optional "#" is stripped).
RULES["POSITION"] = {**RULES.get("POSITION", {}), "pattern": r"^#?[A-Z0-9][A-Z0-9\-]{0,9}$"}

# Blue-ish pixel test for the shaded label/header-row bands: this report's
# own shading consistently reads as a B channel well above R (confirmed
# directly across the identity-box label row and the data-grid's own
# column-header row on the real sample file), which a plain grayscale
# darkfrac test (the technique other modules in this package use for a
# black-ruled header, e.g. `occm_component_status_posn_fin.py`) would not
# distinguish from ordinary black text.
_BLUE_DELTA_THRESH = 40
_BAND_COUNT_THRESH = 1000  # min blue-ish pixels in a row to count as "in a shaded band"
_MIN_BAND_HEIGHT = 20
_SEARCH_HEIGHT_FRAC = 0.30  # identity box + table header both confirmed within top 30%
_ROW_PAD = 10  # inset off each band boundary -- confirmed to avoid the ruled border noise


def _find_label_bands(arr: np.ndarray) -> list[tuple[int, int]]:
    """Contiguous Y-ranges of shaded (blue-ish) rows in the top portion of
    the page, in top-to-bottom order. Same grouping technique as
    `occm_component_status_posn_fin.py`'s own `_find_header_bottom()`, just
    keyed on color instead of darkness."""
    h = arr.shape[0]
    search_h = int(h * _SEARCH_HEIGHT_FRAC)
    band = arr[:search_h]
    blue_mask = (band[:, :, 2].astype(int) - band[:, :, 0].astype(int)) > _BLUE_DELTA_THRESH
    row_counts = blue_mask.sum(axis=1)
    bands: list[tuple[int, int]] = []
    in_band = False
    start = 0
    for y in range(search_h):
        if row_counts[y] > _BAND_COUNT_THRESH and not in_band:
            in_band, start = True, y
        elif row_counts[y] <= _BAND_COUNT_THRESH and in_band:
            in_band = False
            if y - start >= _MIN_BAND_HEIGHT:
                bands.append((start, y))
    if in_band and search_h - start >= _MIN_BAND_HEIGHT:
        bands.append((start, search_h))
    return bands


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 check for the router's blank-text fallback: the shared
    "AIRCRAFT BUILD" title anchor (see module docstring), plus this
    module's own distinctive shaded identity-label row -- confirmed
    directly not present on either sibling's own known source file, so
    this can't steal their files even though all three modules share the
    same bare title anchor and are otherwise reached the same way."""
    try:
        img = await render_page(pdf_path, 0, dpi=300)
        w, h = img.size
        # Same crop height as the sibling modules' own title check -- a
        # narrower crop was confirmed directly to garble the title's own
        # OCR ("AI RCRAFT BUILD", extra space) on this module's own known
        # sample file, apparently because a smaller surrounding context
        # confuses Tesseract's layout analysis on this title's stylised
        # font; this wider band reproduces the sibling modules' own
        # confirmed-clean read instead.
        title_crop = img.crop((0, 0, w, int(h * 0.22)))
        title_text = (await ocr_text(title_crop, psm=6)).upper()
        if "AIRCRAFT BUILD" not in title_text:
            return False
        arr = np.array(img.convert("RGB"))
        bands = _find_label_bands(arr)
        if not bands:
            return False
        top, bot = bands[0]
        label_crop = img.crop((0, top + _ROW_PAD // 2, w, bot))
        label_text = (await ocr_text(label_crop, psm=6)).upper()
        return "AIRCRAFT REG" in label_text
    except Exception:
        return False


_HEADER_KEYS = [
    "AIRCRAFT_REG", "AIRCRAFT_TYPE", "MSN", "MANUFACTURE_DATE",
    "AIRFRAME_TSN", "AIRFRAME_CSN", "LAST_FLIGHT_DATE", "LAST_FLIGHT_NUMBER",
]
_HEADER_STRIP = " |,[]{}()"


async def _parse_header(pdf_path: str) -> dict:
    """Parse the identity table's values row once from page 1 and return it
    for stamping onto every row -- see module docstring point 1. Locates
    the values row as the gap directly below the shaded label row's own
    pixel band, rather than assuming a fixed line offset from the title
    (confirmed directly: OCR-ing the label row and values row together, or
    either together with the title/option-line text above, fails outright;
    isolating just the values row reads cleanly)."""
    meta = {k: "" for k in _HEADER_KEYS}
    try:
        img = await render_page(pdf_path, 0, dpi=300)
        w, h = img.size
        arr = np.array(img.convert("RGB"))
        bands = _find_label_bands(arr)
    except Exception:
        return meta
    if len(bands) < 2:
        return meta
    # First band is the identity table's own shaded label row; second band
    # is the data grid's own shaded column-header row (confirmed directly
    # on the real sample file) -- the values row is the gap between them.
    label_bot = bands[0][1]
    next_band_top = bands[1][0]
    if next_band_top - label_bot < 2 * _ROW_PAD:
        return meta
    crop = img.crop((0, label_bot + _ROW_PAD, w, next_band_top - _ROW_PAD))
    try:
        text = await ocr_text(crop, psm=4)
    except Exception:
        return meta
    tokens = [t.strip(_HEADER_STRIP) for t in text.split()]
    tokens = [t for t in tokens if t]
    if len(tokens) < 3:
        return meta
    for key, tok in zip(_HEADER_KEYS, tokens):
        meta[key] = tok
    return meta


async def extract(pdf_path: str) -> list[dict]:
    header_meta = await _parse_header(pdf_path)
    records: list[dict] = []
    n_pages = await page_count(pdf_path)
    for page_index in range(n_pages):
        img = await render_page(pdf_path, page_index, dpi=300)
        page_records = await _base._parse_page(img, page_index + 1)
        for rec in page_records:
            _split_zone_partnumber(rec)
            rec.update(header_meta)
        records.extend(page_records)
    return records
