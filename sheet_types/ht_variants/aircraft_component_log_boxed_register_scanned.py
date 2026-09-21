""""AIRCRAFT COMPONENT LOG" report -- full-page-raster PDF, no usable text
layer at all (confirmed directly: pdfplumber `extract_text()` returns 0
characters on every page of the real sample file). Rendering to an image
shows a clean, sharp, ordinary machine-printed report (not handwritten, not
a noisy photocopy) with a fully ruled ("boxed") grid baked into the raster
-- every cell boundary, including the outer table border, is a real drawn
line -- so a per-row-per-column OCR pass anchored on the grid's own ruled
divider lines is reliable here, same technique
`hard_time_component_listing_scanned.py` in this same package uses (this
module's overall structure mirrors it closely; the two templates share the
same TSLA/CSLA/DSLA + SPECIFICATION/REMAINING column group but differ in
title text, header-metadata layout, and column count -- see below).

Header block (repeats near-identically at the top of every page)::

    <operator wordmark>                    AIRCRAFT COMPONENT LOG
                              [ Register ]         AS OF: <date>
                              [  <reg>   ]         ATT. <hours>
                                                    ATC. <cycles>

Unlike `hard_time_component_listing_scanned.py`'s sibling template, the
aircraft registration here is NOT printed as a single "Fleet/Unit: <reg>"
line -- it sits inside its own small two-row ruled box (label "Register"
on top, the actual registration value directly below it), confirmed
directly against the real sample file's own header crop. AS OF / ATT / ATC
are plain "<label> <value>" text to the right of that box, using a literal
period after ATT/ATC (not a colon) on the real sample -- confirmed
directly. Header metadata is parsed into row data at runtime as ordinary
functional per-file extraction (same as this project's other header
capture elsewhere in this package); none of the sample file's own real
values are written into this module's source.

Every page repeats the same 17-column ruled column-header row, then one
ruled row per record::

    Description | Part Number | Serial Number | Install Date |
    Last Accomplished Date | TSLA | CSLA | DSLA |
    SPECIFICATION{Hours | Cycles | Days} | REMAINING{Hours | Cycles | Days} |
    FL | Due Date | Certification

This is the same SPECIFICATION/REMAINING two-tier group-header shape as
`hard_time_component_listing_scanned.py`, but with NO "Pos." column
between Part Number and Serial Number -- confirmed directly against the
real sample file's own header row (13 distinct header labels, 17 ruled
sub-columns once SPECIFICATION/REMAINING's own Hours/Cycles/Days triples
are counted). Column X-boundaries are found fresh per page from a numpy
vertical-divider pixel scan (`_find_col_lines`), same approach as this
package's other plain-ruled-grid OCR variants, rather than fixed
fractions -- this keeps the crop aligned even against a differently
cropped/scaled copy of this same template. The scan band is derived from
the page's own detected data-row span (`_find_horizontal_lines`) rather
than a fixed fraction of page height, since a short last page (the real
sample's own last page carries only a handful of rows) would be missed by
a fixed mid-page fraction band.

`_find_horizontal_lines` scans a single FULL-WIDTH divider pass (top of
page to bottom) at a high dark-fraction threshold (0.55) -- confirmed
directly against the real sample this cleanly separates every genuine
ruled line (the header's own top/bottom borders and every row divider all
measure comfortably above 0.6) from incidental full-width darkness that
isn't a ruled line (the "TO THE BEST OF OUR KNOWLEDGE..." sign-off text
and signature block below the table on the real sample's own last page,
confirmed directly none of it reaches the 0.55 threshold at any single
y-row, since it is a mix of a short text line, a handwritten signature,
and a short name/title line rather than one continuous full-width rule).
The first line found this way on every page is the page's own outer top
rule (well above the header); the second is the header block's own top
border; the third is the header/data boundary (`data_start`); every line
after that is a real row divider, and the LAST one found is the table's
own closing bottom border (`table_bottom`) -- confirmed directly against
the real sample there are no further full-width qualifying lines below it
(the sign-off block included, per above). Every row this module emits is
bounded strictly between two consecutive lines in this same list, so the
sign-off block is never picked up as a row.

Each cell is OCR'd individually (one crop per row per column, not one
whole-column pass down the page) -- same reasoning as
`hard_time_component_listing_scanned.py`: this template repeats identical
DESCRIPTION/PART_NUMBER text on consecutive rows for several component
families in the real sample (e.g. paired "SAFETY VALVE" rows, a run of
"MASK_F-F_QUICK_DONNING" rows, several "VALVE RINSE ASSEMBLY" rows), and a
single tall whole-column OCR pass risks silently deduplicating a repeated
line -- a fresh single-row crop per cell avoids that. Each cell crop is
also inset a few px on every side and upscaled 2x before OCR (see
`_ocr_cell`) -- confirmed directly a crop taken right up to the ruled
grid's own divider lines lets a sliver of the neighbouring border bleed
into the image and garble the read, same fix this package's other
ruled-grid OCR variants use.

DESCRIPTION and CERTIFICATION are genuine multi-word free text (e.g. "OFF
WING RAMP SLIDE LH", "EVACUATION SYSTEMS RESERVOIR AND VALVE", or a
CERTIFICATION cell reading "MATERIAL CERTIFICATION FORM" / "MISCELLANEOUS
WORK SHEET" -- both confirmed on real sample rows) -- joined WITH a space.
PART_NUMBER and SERIAL_NUMBER are treated as "code" columns joined with NO
separator (same convention as the sibling module), guarding against a
long code wrapping across two physical OCR lines within one ruled cell.

Numeric columns (TSLA/CSLA/DSLA, SPECIFICATION and REMAINING Hours/
Cycles/Days) are reduced to only their own matching digit-run-with-
optional-decimal substring rather than passed through raw, per this
project's "never guess a wrong split" convention -- a dropped stray OCR
artifact is preferred over a confidently-wrong value. DUE_DATE/
INSTALL_DATE/LAST_ACCOMPLISHED_DATE are reduced the same way to a
`DD-<3-letter-month>-YY` (or `-YYYY` for DUE_DATE, which prints a 4-digit
year on the real sample, e.g. "5-Feb-12" for INSTALL_DATE-style fields vs
DUE_DATE itself also using a 2-digit year on the real sample -- both
INSTALL_DATE/LAST_ACCOMPLISHED_DATE/DUE_DATE use 2-digit years on the real
sample, confirmed directly; the date token pattern below accepts either
2 or 4 digits so a genuine 4-digit year elsewhere is not rejected).

Sensitivity note: the real sample file's own MSN/registration/AS-OF-date/
ATT/ATC values are extracted into row data at runtime (ordinary functional
per-file header capture, same as this project's other header extraction
elsewhere in this package) but are NOT written into this module's
source/comments anywhere -- only the generic column-header/title/label
phrases the template itself prints (which are not document-specific)
appear above.
"""
from __future__ import annotations
import re

import numpy as np
from PIL import Image

from sheet_types.ht_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, ocr_words, page_count

NAME = "Aircraft Component Log (Boxed Register, Scanned)"

# Deliberately empty -- this file's own plain-text layer is blank on every
# page (see module docstring), so a plain-pdfplumber SIGNATURES phrase can
# never fire. Detected instead via ocr_detect() below, through the
# router's blank-text-layer OCR-fallback path (sheet_types/ht.py's own
# detect_variant()).
SIGNATURES: list[str] = []

CANONICAL_COLUMNS = [
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "INSTALL_DATE",
    "LAST_ACCOMPLISHED_DATE",
    "TSLA",
    "CSLA",
    "DSLA",
    "SPEC_HOURS",
    "SPEC_CYCLES",
    "SPEC_DAYS",
    "REMAINING_HOURS",
    "REMAINING_CYCLES",
    "REMAINING_DAYS",
    "FL",
    "DUE_DATE",
    "CERTIFICATION",
    # Header metadata -- parsed once (whichever page OCRs cleanest first)
    # and stamped on every row.
    "REGISTER",
    "AS_OF_DATE",
    "ATT",
    "ATC",
]

_DATE_RE = r"^\d{1,2}[-\.][A-Za-z]{3}[-\.]\d{2,4}$"
_NUM_RE = r"^\d+(?:\.\d+)?$"

_OVERRIDES = {
    "PART_NUMBER": {"allow_empty": True},
    "SERIAL_NUMBER": {"allow_empty": True},
    "DESCRIPTION": {"allow_empty": True, "uppercase": True},
    "INSTALL_DATE": {"pattern": _DATE_RE, "allow_empty": True},
    "LAST_ACCOMPLISHED_DATE": {"pattern": _DATE_RE, "allow_empty": True},
    "TSLA": {"pattern": _NUM_RE, "allow_empty": True},
    "CSLA": {"pattern": _NUM_RE, "allow_empty": True},
    "DSLA": {"pattern": _NUM_RE, "allow_empty": True},
    "SPEC_HOURS": {"pattern": _NUM_RE, "allow_empty": True},
    "SPEC_CYCLES": {"pattern": _NUM_RE, "allow_empty": True},
    "SPEC_DAYS": {"pattern": _NUM_RE, "allow_empty": True},
    "REMAINING_HOURS": {"pattern": _NUM_RE, "allow_empty": True},
    "REMAINING_CYCLES": {"pattern": _NUM_RE, "allow_empty": True},
    "REMAINING_DAYS": {"pattern": _NUM_RE, "allow_empty": True},
    "FL": {"allow_empty": True},
    "DUE_DATE": {"pattern": _DATE_RE, "allow_empty": True},
    "CERTIFICATION": {"allow_empty": True, "uppercase": True},
    # Header metadata -- a single OCR misread here shouldn't flag every
    # row of the file, same reasoning this package's other header-plus-
    # body OCR variants use.
    "REGISTER": {"allow_empty": True, "uppercase": True},
    "AS_OF_DATE": {"allow_empty": True},
    "ATT": {"allow_empty": True},
    "ATC": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_DPI = 300

# Column order matching the ruled grid's own 17 columns, left to right --
# no POSITION column on this template (see module docstring).
_COLUMN_ORDER = [
    "DESCRIPTION", "PART_NUMBER", "SERIAL_NUMBER",
    "INSTALL_DATE", "LAST_ACCOMPLISHED_DATE",
    "TSLA", "CSLA", "DSLA",
    "SPEC_HOURS", "SPEC_CYCLES", "SPEC_DAYS",
    "REMAINING_HOURS", "REMAINING_CYCLES", "REMAINING_DAYS",
    "FL", "DUE_DATE", "CERTIFICATION",
]
_N_COLUMNS = len(_COLUMN_ORDER)

# Genuine multi-word free text -- joined WITH a space, both within one
# visual line and across a genuine multi-line wrap.
_TEXT_JOIN_COLS = {"DESCRIPTION", "CERTIFICATION"}
# "Code" columns (part/serial numbers) -- joined with NO separator, so a
# two-line wrap reassembles into one unbroken string rather than picking
# up a stray space partway through it.
_CODE_COLS = {"PART_NUMBER", "SERIAL_NUMBER"}
_CODE_STRIP_CHARS = " _\"'`‘’“”.,;:()[]{}|~="
_NUM_COLS = {
    "TSLA", "CSLA", "DSLA", "SPEC_HOURS", "SPEC_CYCLES", "SPEC_DAYS",
    "REMAINING_HOURS", "REMAINING_CYCLES", "REMAINING_DAYS",
}
_DATE_COLS = {"INSTALL_DATE", "LAST_ACCOMPLISHED_DATE", "DUE_DATE"}
_NUM_TOKEN_RE = re.compile(r"\d+(?:\.\d+)?")
_DATE_TOKEN_RE = re.compile(r"\d{1,2}[-\.][A-Za-z]{3}[-\.]\d{2,4}")

# Grid-line detection thresholds -- confirmed directly against the real
# sample's own 300 DPI render. Row-divider darkness is NOT uniform across
# this template's own pages (confirmed directly: page 1's/page 3's own
# row dividers measure ~0.55-0.79 dark-fraction, but page 2's own real
# row dividers on the same real file measure only ~0.29-0.53, with the
# single weakest one (between a "STANDBY ALTIMETER" and a "PORTABLE
# CYLINDER ASSEMBLY" row on the real sample -- confirmed directly, real
# component names not written elsewhere in this module) at just 0.45 --
# a lighter print/scan pass on that one page, not a different template),
# so the threshold sits lower, at 0.40, than the 0.55 used by the
# otherwise-similar `hard_time_component_listing_scanned.py` sibling
# module. Confirmed directly this is still safely clear of every non-row
# full-width darkness source on the real sample: every genuine within-row
# text line's own dark-fraction peaks under ~0.23 (confirmed directly
# scanning the full page profile), and the last page's own "TO THE BEST
# OF OUR KNOWLEDGE..." sign-off text plus handwritten signature plus
# signer name/title block measures only ~0.15 dark-fraction at its
# darkest single row (unlike the sibling module's own sample file, this
# template's sign-off block is not a full-width printed/ruled line, so it
# was never a threshold risk here in the first place). A too-low
# threshold would risk merging two genuine rows into one output record
# (a row-window-overlap bug) -- 0.40 was chosen as the lowest threshold
# that still resolves the confirmed-weakest real divider on the real
# sample, not lower.
_DARK_PIXEL_THRESH = 200
_LINE_THRESH_FRAC = 0.40
_LINE_MERGE_PX = 8
# A line this close to the very top of the page is the page's own outer
# top rule, not part of the table.
_PAGE_TOP_RULE_MAX_Y = 20
# Per-cell OCR crop tuning -- see `_ocr_cell` for why the inset matters
# (grid-line bleed into the crop).
_CELL_INSET_PX = 6
_CELL_UPSCALE = 2


def _divider_lines(arr: np.ndarray, x0: int, x1: int, y_lo: int, y_hi: int,
                    dark_thresh: int = _DARK_PIXEL_THRESH,
                    thresh_frac: float = _LINE_THRESH_FRAC,
                    merge_px: int = _LINE_MERGE_PX) -> list[int]:
    y_lo = max(y_lo, 0)
    y_hi = min(y_hi, arr.shape[0])
    if y_hi <= y_lo or x1 <= x0:
        return []
    frac = (arr[y_lo:y_hi, x0:x1] < dark_thresh).sum(axis=1) / (x1 - x0)
    ys = [y_lo + i for i in range(len(frac)) if frac[i] > thresh_frac]
    groups: list[list[int]] = []
    for y in ys:
        if groups and y - groups[-1][-1] <= merge_px:
            groups[-1].append(y)
        else:
            groups.append([y])
    return [int(np.mean(g)) for g in groups]


def _find_horizontal_lines(arr: np.ndarray) -> list[int]:
    """Every genuine ruled horizontal line on the page, full width, high-
    threshold (see module docstring). Index 0 is the header block's own
    top border, index 1 is `data_start`, and every remaining line is a
    row divider -- the last of which is `table_bottom`."""
    h, w = arr.shape
    lines = _divider_lines(arr, int(w * 0.01), int(w * 0.98), 0, h)
    return [y for y in lines if y > _PAGE_TOP_RULE_MAX_Y]


def _find_col_lines(arr: np.ndarray, y0: int, y1: int) -> list[int]:
    """X-centers of the table's own vertical column dividers, found fresh
    per page within the page's own detected data-row span (not a fixed
    fraction of page height -- a short last page needs this).

    Threshold confirmed directly against the real sample: same lighter-
    print-pass page (see `_LINE_THRESH_FRAC` docstring) that has weaker
    row dividers also has weaker column dividers -- its own real vertical
    lines measure only ~0.41-0.55 dark-fraction of the row-span height
    (vs. ~0.5+ comfortably on the other two pages), so 0.3 is used here
    (all three pages independently resolve to the expected 18 dividers /
    17 columns at this threshold, confirmed directly)."""
    h, w = arr.shape
    y0 = max(y0, 0)
    y1 = min(y1, h)
    if y1 <= y0:
        return []
    frac = (arr[y0:y1, :] < _DARK_PIXEL_THRESH).sum(axis=0) / (y1 - y0)
    xs = [x for x in range(w) if frac[x] > 0.3]
    groups: list[list[int]] = []
    for x in xs:
        if groups and x - groups[-1][-1] <= 4:
            groups[-1].append(x)
        else:
            groups.append([x])
    return [int(np.mean(g)) for g in groups]


def _col_bounds_from_lines(col_lines: list[int]) -> dict | None:
    if len(col_lines) < _N_COLUMNS + 1:
        return None
    # Real column dividers are the leftmost N_COLUMNS+1 lines found -- a
    # spurious extra line occasionally picked up near the far right page
    # edge is dropped by only taking the first N_COLUMNS+1, same
    # convention as `hard_time_component_listing_scanned.py`.
    pairs = list(zip(col_lines[:-1], col_lines[1:]))[:_N_COLUMNS]
    return {name: bounds for name, bounds in zip(_COLUMN_ORDER, pairs)}


async def _ocr_cell(img, name: str, col_bounds: dict, y0: int, y1: int) -> list[tuple[float, float, str]]:
    x0, x1 = col_bounds[name]
    if y1 <= y0:
        return []
    inset = min(_CELL_INSET_PX, (x1 - x0) // 2 - 1, (y1 - y0) // 2 - 1)
    inset = max(inset, 0)
    scale = _CELL_UPSCALE
    crop = img.crop((x0 + inset, y0 + inset, x1 - inset, y1 - inset))
    crop_y0 = y0 + inset
    if crop.width < 1 or crop.height < 1:
        crop = img.crop((x0, y0, x1, y1))
        crop_y0 = y0
        scale = 1
    else:
        crop = crop.resize((crop.width * scale, crop.height * scale), Image.LANCZOS)
    words = await ocr_words(crop, psm=6, min_conf=-1)
    out = []
    for wd in words:
        text = str(wd.get("text", "")).strip()
        if not text:
            continue
        out.append((crop_y0 + wd["top"] / scale, wd.get("left", 0) / scale, text))
    return out


def _clean_field(name: str, tokens: list[tuple[float, float, str]]) -> str:
    lines: list[list[tuple[float, float, str]]] = []
    for top, left, text in sorted(tokens, key=lambda t: t[0]):
        if lines and abs(top - lines[-1][0][0]) <= 14:
            lines[-1].append((top, left, text))
        else:
            lines.append([(top, left, text)])
    ordered = [[t for _, _, t in sorted(line, key=lambda x: x[1])] for line in lines]
    if name in _TEXT_JOIN_COLS:
        text = " ".join(" ".join(line) for line in ordered)
    else:
        text = "".join("".join(line) for line in ordered)
    if name in _CODE_COLS:
        text = text.strip(_CODE_STRIP_CHARS)
    if name in _NUM_COLS:
        found = _NUM_TOKEN_RE.findall(text)
        text = max(found, key=len) if found else ""
    elif name in _DATE_COLS:
        found = _DATE_TOKEN_RE.findall(text)
        text = found[0] if found else ""
    return text


_HEADER_FIELDS = ["REGISTER", "AS_OF_DATE", "ATT", "ATC"]

# Bare "AIRCRAFT COMPONENT LOG" title -- checked directly (grep) against
# every SIGNATURES list in occm.py/ht.py/llp.py and every
# occm_variants/ht_variants/llp_variants module's own SIGNATURES/
# ocr_detect anchor text: the only other module referencing this phrase is
# ht_aircraft_component_log.py, whose own title is the distinct "HT
# Aircraft Component LOG" and which is a real-text-layer-only module (no
# ocr_detect(), sync extract() only) -- it is never probed by the router's
# blank-text-layer OCR fallback, so it can never collide with this
# module's own ocr_detect() at runtime.
_TITLE_RE = re.compile(r"\bAIRCRAFT\s+COMPONENT\s+LOG\b", re.IGNORECASE)

_REGISTER_RE = re.compile(r"Register[\s\n]+([A-Z0-9]{3,8})", re.IGNORECASE)
# OCR of the real sample's own separator punctuation after AS OF/ATT/ATC is
# inconsistent -- a printed colon/period is confirmed to sometimes misread
# as a semicolon or comma instead (e.g. a printed "AS OF: <date>" OCR'ing
# as "AS OF; <date>", or a printed "ATC. <n>" OCR'ing as "ATC, <n>") -- all
# of :.,; are accepted here as the same separator rather than risking a
# missed match on a genuine but OCR-mangled punctuation mark. No real
# sample value is written into this comment.
_AS_OF_RE = re.compile(r"AS\s*OF\s*[:.,;]?\s*([A-Za-z]{3,9}\s*\d{1,2}\s*,?\s*\d{4})", re.IGNORECASE)
_ATT_RE = re.compile(r"\bATT\s*[:.,;]?\s*([\d,]+\.?\d*)", re.IGNORECASE)
_ATC_RE = re.compile(r"\bATC\s*[:.,;]?\s*([\d,]+)", re.IGNORECASE)

# This template's own distinctive column-header fragment -- TSLA/CSLA/DSLA
# together is checked directly (grep) against every SIGNATURES list in
# occm.py/ht.py/llp.py and every occm_variants/ht_variants/llp_variants
# module's own SIGNATURES/ocr_detect anchor text; the only other module
# anchoring on it is `hard_time_component_listing_scanned.py`, which is
# safely distinguished from this one by the paired title check below (its
# own title is "HARD TIME COMPONENT LISTING", not "AIRCRAFT COMPONENT
# LOG").
_HEADER_ROW_RE = re.compile(r"TSLA.{0,20}CSLA.{0,20}DSLA", re.IGNORECASE)

# Header/info-block crop, as fractions of the page -- to the right of the
# operator wordmark, above the table (derived directly from a real
# per-pixel measurement on the sample file's page 1).
_HEADER_CROP = (0.42, 0.0, 1.0, 0.09)


async def _parse_header(img) -> dict:
    meta = {k: "" for k in _HEADER_FIELDS}
    w, h = img.size
    x0, y0, x1, y1 = _HEADER_CROP
    crop = img.crop((int(w * x0), int(h * y0), int(w * x1), int(h * y1)))
    text = await ocr_text(crop, psm=6)
    for key, rx in (
        ("REGISTER", _REGISTER_RE), ("AS_OF_DATE", _AS_OF_RE),
        ("ATT", _ATT_RE), ("ATC", _ATC_RE),
    ):
        m = rx.search(text)
        if m:
            meta[key] = m.group(1).strip(_CODE_STRIP_CHARS)
    return meta


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback (see
    sheet_types/ht.py) -- this variant's SIGNATURES is deliberately empty
    (see module docstring).

    Requires BOTH the bare "AIRCRAFT COMPONENT LOG" title AND the ruled
    grid's own TSLA/CSLA/DSLA column-header cells -- the paired check
    matters since either alone could plausibly recur elsewhere (see the
    two anchor comments above `_TITLE_RE`/`_HEADER_ROW_RE`). The
    TSLA/CSLA/DSLA cells are OCR'd individually (one crop per header
    cell, upscaled, same technique `_ocr_cell` uses for data rows) rather
    than as one whole-row band -- confirmed directly a single wide OCR
    pass across the full ruled header row (with its many close-together
    vertical divider lines) garbles adjacent narrow cells like CSLA/DSLA
    even though each cell reads perfectly cleanly on its own."""
    try:
        img = await render_page(pdf_path, 0, dpi=_DPI)
        w, h = img.size
        title_crop = img.crop((int(w * 0.15), 0, w, int(h * 0.09)))
        title_text = await ocr_text(title_crop, psm=6)
        if not _TITLE_RE.search(title_text):
            return False
        arr = np.array(img.convert("L"))
        lines = _find_horizontal_lines(arr)
        if len(lines) < 3:
            return False
        data_start = lines[1]
        table_bottom = lines[-1]
        col_lines = _find_col_lines(arr, data_start + 5, table_bottom - 5)
        col_bounds = _col_bounds_from_lines(col_lines)
        if col_bounds is None:
            return False
        y0, y1 = max(data_start - 100, 0), data_start
        found = ""
        for name in ("TSLA", "CSLA", "DSLA"):
            x0, x1 = col_bounds[name]
            inset = min(4, (x1 - x0) // 2 - 1, (y1 - y0) // 2 - 1)
            inset = max(inset, 0)
            crop = img.crop((x0 + inset, y0 + inset, x1 - inset, y1 - inset))
            if crop.width < 1 or crop.height < 1:
                continue
            crop = crop.resize((crop.width * 3, crop.height * 3), Image.LANCZOS)
            found += (await ocr_text(crop, psm=6)).upper() + " "
        normed = " ".join(found.split())
        return bool(_HEADER_ROW_RE.search(normed))
    except Exception:
        return False


async def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    header_meta = {k: "" for k in _HEADER_FIELDS}
    n_pages = await page_count(pdf_path)

    for page_index in range(n_pages):
        img = await render_page(pdf_path, page_index, dpi=_DPI)
        arr = np.array(img.convert("L"))

        # lines[0] = header block's own top border, lines[1] = data_start,
        # every remaining entry is a row divider (the last one is the
        # table's own closing bottom border).
        row_lines = _find_horizontal_lines(arr)
        if len(row_lines) < 3:
            continue
        data_start = row_lines[1]
        row_lines = row_lines[1:]
        table_bottom = row_lines[-1]

        if not all(header_meta.values()):
            page_meta = await _parse_header(img)
            for k, v in page_meta.items():
                if v and not header_meta[k]:
                    header_meta[k] = v

        col_lines = _find_col_lines(arr, data_start + 5, table_bottom - 5)
        col_bounds = _col_bounds_from_lines(col_lines)
        if col_bounds is None:
            continue

        for i in range(len(row_lines) - 1):
            y0, y1 = row_lines[i], row_lines[i + 1]
            row: dict[str, str] = {}
            for name in _COLUMN_ORDER:
                toks = await _ocr_cell(img, name, col_bounds, y0, y1)
                row[name] = _clean_field(name, toks)
            row["_page"] = page_index + 1
            row.update(header_meta)
            records.append(row)

    return records
