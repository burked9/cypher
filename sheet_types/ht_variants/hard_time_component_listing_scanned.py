"""Bare "HARD TIME COMPONENT LISTING" report -- full-page-raster PDF, no
usable text layer at all (confirmed directly: pdfplumber `extract_text()`
returns 0 characters on every page of the sample file). Rendering to an
image shows a clean, sharp, ordinary machine-printed report (not
handwritten, not a noisy photocopy) with a fully ruled ("boxed") grid
baked into the raster -- every cell boundary, including the outer table
border, is a real drawn line -- so a per-row-per-column OCR pass anchored
on the grid's own ruled divider lines is reliable here, same technique
this package's other plain-ruled-grid scanned variants use (e.g.
`ht_ruled_grid_mpd_interval_remaining_scanned.py` in this same package,
which this module's overall structure mirrors closely).

Header block (repeats near-identically at the top of every page)::

    <operator wordmark>       HARD TIME COMPONENT LISTING
                                        MSN: <msn>            MODEL: <type>
                                   Fleet/Unit: <reg>          AS OF: <date>
                                        ATT: <hours>          ATC: <cycles>

Unlike some sibling ruled-grid HT variants in this package, this header
block carries no coloured cell fills and no ruled box of its own around
the MSN/MODEL/Fleet-Unit/AS-OF/ATT/ATC lines -- it is plain black-on-white
text, confirmed to OCR cleanly as one combined crop (no need to split
into separate label/value strips the way a coloured info box elsewhere in
this package requires). AIRCRAFT-file-specific values (MSN/registration/
hours/cycles) are parsed into row data at runtime as ordinary functional
header-metadata extraction (same as this project's other per-file header
capture elsewhere in this package) -- none of the sample file's own real
values are written into this module's source.

Every page (including page 1, below its own header block) repeats the
same 18-column ruled column-header row, then one ruled row per record::

    Description | Part Number | Pos. | Serial Number | Install Date |
    Last Accomplished Date | TSLA | CSLA | DSLA |
    SPECIFICATION{Hours | Cycles | Days} | REMAINING{Hours | Cycles | Days} |
    FL | Due Date | Certificate

The 18-column header row itself spans two physical ruled sub-rows (a
top-tier group label -- "SPECIFICATION"/"REMAINING" -- over three
single-tier sub-columns each; the first nine identity/limit columns have
no group label and are a single taller merged header cell). Column
X-boundaries are found fresh per page from a numpy vertical-divider pixel
scan (`_find_col_lines`), same approach as this package's other
plain-ruled-grid OCR variants, rather than fixed fractions -- this keeps
the crop aligned even against a differently cropped/scaled copy of this
same template. The scan band is derived from the page's own detected
data-row span (`_find_horizontal_lines`) rather than a
fixed fraction of page height, since the sample file's own last page
carries only 2 data rows and a fixed mid-page fraction band would miss
the table entirely on a short page like that (confirmed directly).

`_find_horizontal_lines` scans a single FULL-WIDTH divider pass (top of
page to bottom) at a deliberately high dark-fraction threshold (0.55) --
confirmed directly against the real sample this cleanly separates every
genuine ruled line (the header's own top/bottom borders and every row
divider all measure comfortably above 0.6, frequently near 1.0) from
every source of incidental full-width darkness that isn't a ruled line:
the header cell's own shaded/hatched fill and its own column-label text
(both max out under ~0.47 in the sample, confirmed directly per-row), and
-- critically -- a "Prepared by ... <name> ___________" sign-off line's
own underline on the sample file's own last page (a real, wide drawn
rule, not a stray artifact, but only wide enough to reach ~0.43 of the
table's own full width, confirmed directly). A naive lower threshold
(e.g. the ~0.4 this package's other ruled-grid variants use, tuned for a
plain white-background table with no header shading) picks that
underline up as a spurious extra "row" boundary spanning a huge blank gap
plus the signer's own name straight into the last real row's own
CERTIFICATE field -- confirmed directly this happens without the
threshold raised. The very first line found this way on every page is
the page's own outer top rule (well above the header, and unrelated to
the table); the second is the header block's own top border; the third
is the header/data boundary (`data_start`); every line after that is a
real row divider, and the LAST one found is the table's own closing
bottom border (`table_bottom`) -- confirmed directly there are no further
full-width qualifying lines below it anywhere in the sample (the sign-off
underline included, per above). Every row this module emits is bounded
strictly between two consecutive lines in this same list, so that
sign-off underline is never picked up as a row and no signer name is
ever captured into any output field; no name from the sample file's own
sign-off line is written into this module's source either.

Each cell is OCR'd individually (one crop per row per column, not one
whole-column pass down the page) -- confirmed this project's usual
concern applies here too: this template repeats identical DESCRIPTION/
PART_NUMBER text on consecutive rows for several component families in
the sample (e.g. a run of "SMOKE HOOD" / "E28180-10" rows, or paired
"SAFETY VALVE" rows), and Tesseract's own line deduplication can silently
drop a repeated line from a single tall whole-column OCR pass in exactly
that situation -- a fresh single-row crop per cell has no other rows in
it for Tesseract to (wrongly) deduplicate against. Each cell crop is also
inset a few px on every side and upscaled 2x before OCR (see `_ocr_cell`)
-- confirmed directly a crop taken right up to the ruled grid's own
divider lines lets a sliver of the neighbouring border bleed into the
image and garble the read, same fix this package's other ruled-grid OCR
variants use.

Two columns in the sample genuinely wrap their own value across two
physical text lines within one ruled row cell without a real word-space
at the wrap point -- confirmed directly: PART_NUMBER (a long assembly
part number, e.g. a "...A" prefix wrapping onto a lone trailing "D" on
the line below) and SERIAL_NUMBER (an alphanumeric serial wrapping mid-
run onto a short numeric tail on the line below). Both are treated as
"code" columns whose OCR word tokens are joined with NO separator, across
both words on the same visual line and across wrapped lines, so a genuine
two-line wrap reassembles into one unbroken code string rather than
picking up a stray space partway through it. DESCRIPTION and CERTIFICATE
are the opposite case -- genuine multi-word free text (e.g. "MAIN HEAT
EXCHANGER", or a CERTIFICATE cell that itself wraps onto two lines for an
unusually long note, "DELIVERY A/C <reg>, MSN:<msn>" in one sample row)
-- so both are joined WITH a space, both within a visual line and across
wrapped lines.

CERTIFICATE's own value is a genuinely short second line printed toward
the bottom of an otherwise-blank-looking cell on most rows (e.g. plain
"DELIVERY" or "FAA 8130", sitting visually lower than the row's other
single-line columns) -- this is not a special case this module handles
separately; the same generic per-cell top/left token-bucketing used for
every other column naturally picks up wherever within the cell's own
ruled Y-span the text actually sits.

Numeric columns (TSLA/CSLA/DSLA, SPECIFICATION and REMAINING Hours/
Cycles/Days) are reduced to only their own matching digit-run-with-
optional-decimal substring rather than passed through raw, per this
project's "never guess a wrong split" convention -- a dropped stray OCR
artifact (a stray "." or a border-bleed fragment) is preferred over a
confidently-wrong value. DUE_DATE/INSTALL_DATE/LAST_ACCOMPLISHED_DATE are
reduced the same way to a `DD-<3-letter-month>-YY` token; the sample
file's own month abbreviations are inconsistently English/Spanish from
row to row (e.g. "03-Jun-11" alongside "04-Ago-11", "15-Abr-13") -- the
date token pattern only checks for a 3-letter alphabetic run in that
position (it does not validate the abbreviation against either
language's own month list), so this is captured either way without extra
per-language handling.

Sensitivity note: the sample file's own real MSN/registration/aircraft-
type/hours/cycles values are extracted into row data at runtime (ordinary
functional header-metadata capture, same as this project's other per-file
header extraction elsewhere in this package) but are NOT written into
this module's source/comments anywhere -- only the generic column-header/
title/label phrases the template itself prints (which are not
document-specific) appear above.
"""
from __future__ import annotations
import re

import numpy as np
from PIL import Image

from sheet_types.ht_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, ocr_words, page_count

NAME = "Hard Time Component Listing (Scanned)"

# Deliberately empty -- this file's own plain-text layer is blank on every
# page (see module docstring), so a plain-pdfplumber SIGNATURES phrase can
# never fire. Detected instead via ocr_detect() below, through the
# router's blank-text-layer OCR-fallback path (sheet_types/ht.py's own
# detect_variant()).
SIGNATURES: list[str] = []

CANONICAL_COLUMNS = [
    "DESCRIPTION",
    "PART_NUMBER",
    "POSITION",
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
    "CERTIFICATE",
    # Header metadata -- parsed once (whichever page OCRs cleanest first)
    # and stamped on every row.
    "MSN",
    "MODEL",
    "FLEET_UNIT",
    "AS_OF_DATE",
    "ATT",
    "ATC",
]

_DATE_RE = r"^\d{1,2}[-\.][A-Za-z]{3}[-\.]\d{2,4}$"
_NUM_RE = r"^\d+(?:\.\d+)?$"

_OVERRIDES = {
    "PART_NUMBER": {"allow_empty": True},
    "POSITION": {"allow_empty": True, "uppercase": True},
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
    "CERTIFICATE": {"allow_empty": True, "uppercase": True},
    # Header metadata -- a single OCR misread here shouldn't flag every
    # row of the file, same reasoning this package's other header-plus-
    # body OCR variants use.
    "MSN": {"allow_empty": True},
    "MODEL": {"allow_empty": True},
    "FLEET_UNIT": {"allow_empty": True, "uppercase": True},
    "AS_OF_DATE": {"allow_empty": True},
    "ATT": {"allow_empty": True},
    "ATC": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_DPI = 300

# Column order matching the ruled grid's own 18 columns, left to right.
_COLUMN_ORDER = [
    "DESCRIPTION", "PART_NUMBER", "POSITION", "SERIAL_NUMBER",
    "INSTALL_DATE", "LAST_ACCOMPLISHED_DATE",
    "TSLA", "CSLA", "DSLA",
    "SPEC_HOURS", "SPEC_CYCLES", "SPEC_DAYS",
    "REMAINING_HOURS", "REMAINING_CYCLES", "REMAINING_DAYS",
    "FL", "DUE_DATE", "CERTIFICATE",
]
_N_COLUMNS = len(_COLUMN_ORDER)

# Genuine multi-word free text -- joined WITH a space, both within one
# visual line and across a genuine multi-line wrap (see module docstring).
_TEXT_JOIN_COLS = {"DESCRIPTION", "CERTIFICATE"}
# "Code" columns (part/serial numbers, position codes) -- joined with NO
# separator, so a two-line wrap (confirmed on PART_NUMBER/SERIAL_NUMBER in
# the sample, see module docstring) reassembles into one unbroken string.
_CODE_COLS = {"PART_NUMBER", "SERIAL_NUMBER", "POSITION"}
_CODE_STRIP_CHARS = " _\"'`‘’“”.,;:()[]{}|~="
_NUM_COLS = {
    "TSLA", "CSLA", "DSLA", "SPEC_HOURS", "SPEC_CYCLES", "SPEC_DAYS",
    "REMAINING_HOURS", "REMAINING_CYCLES", "REMAINING_DAYS",
}
_DATE_COLS = {"INSTALL_DATE", "LAST_ACCOMPLISHED_DATE", "DUE_DATE"}
_NUM_TOKEN_RE = re.compile(r"\d+(?:\.\d+)?")
_DATE_TOKEN_RE = re.compile(r"\d{1,2}[-\.][A-Za-z]{3}[-\.]\d{2,4}")

# Grid-line detection thresholds -- tuned directly against the real
# sample's own 300 DPI render (see module docstring "_find_horizontal_
# lines" paragraph for the full story on why the threshold sits at 0.55).
_DARK_PIXEL_THRESH = 200
_LINE_THRESH_FRAC = 0.55
_LINE_MERGE_PX = 8
# A line this close to the very top of the page is the page's own outer
# top rule, not part of the table (see module docstring).
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
    fraction of page height -- see module docstring for why a short last
    page needs this)."""
    h, w = arr.shape
    y0 = max(y0, 0)
    y1 = min(y1, h)
    if y1 <= y0:
        return []
    frac = (arr[y0:y1, :] < _DARK_PIXEL_THRESH).sum(axis=0) / (y1 - y0)
    xs = [x for x in range(w) if frac[x] > 0.5]
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
    # edge (well past the table's own real right border) is dropped by
    # only taking the first N_COLUMNS+1 (confirmed directly against the
    # sample: the table's own real right border is always among the
    # leftmost N_COLUMNS+1 lines found, never the dropped trailing one).
    pairs = list(zip(col_lines[:-1], col_lines[1:]))[:_N_COLUMNS]
    return {name: bounds for name, bounds in zip(_COLUMN_ORDER, pairs)}


async def _ocr_cell(img, name: str, col_bounds: dict, y0: int, y1: int) -> list[tuple[float, float, str]]:
    x0, x1 = col_bounds[name]
    if y1 <= y0:
        return []
    # Insetting a few px on every side before OCR, plus a 2x upscale --
    # confirmed directly this matters: a crop taken right up to the ruled
    # grid's own divider lines lets a sliver of the neighbouring border
    # bleed into the image and garble the read.
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


_HEADER_FIELDS = ["MSN", "MODEL", "FLEET_UNIT", "AS_OF_DATE", "ATT", "ATC"]

# Bare "HARD TIME COMPONENT LISTING" title -- checked directly (grep)
# against every SIGNATURES list in occm.py/ht.py/llp.py and every
# occm_variants/ht_variants/llp_variants module's own SIGNATURES/
# ocr_detect anchor text: no other module in this package anchors on this
# exact phrase (a couple of occm_variants module docstrings use the
# generic English phrase "component listing" in prose, not as an anchor).
_TITLE_RE = re.compile(r"HARD\s+TIME\s+COMPONENT\s+LISTING", re.IGNORECASE)

_MSN_RE = re.compile(r"MSN\s*:\s*(\S+)", re.IGNORECASE)
_MODEL_RE = re.compile(r"MODEL\s*:\s*(\S+)", re.IGNORECASE)
_FLEET_UNIT_RE = re.compile(r"Fleet\s*/?\s*Unit\s*:\s*(\S+)", re.IGNORECASE)
_AS_OF_RE = re.compile(r"AS\s*OF\s*:\s*(\S+)", re.IGNORECASE)
_ATT_RE = re.compile(r"\bATT\s*:\s*(\S+)", re.IGNORECASE)
_ATC_RE = re.compile(r"\bATC\s*:\s*(\S+)", re.IGNORECASE)

# This template's own distinctive column-header fragment -- TSLA/CSLA/DSLA
# together is checked directly (grep) against every SIGNATURES list in
# occm.py/ht.py/llp.py and every occm_variants/ht_variants/llp_variants
# module's own SIGNATURES/ocr_detect anchor text; no other module anchors
# on these. Combined with the title phrase above so neither alone has to
# be a unique anchor on its own.
_HEADER_ROW_RE = re.compile(r"TSLA.{0,20}CSLA.{0,20}DSLA", re.IGNORECASE)

# Header/info-block crop, as fractions of the page -- to the right of the
# operator wordmark, above the table (derived directly from a real
# per-pixel measurement on the sample file's page 1).
_HEADER_CROP = (0.20, 0.0, 1.0, 0.14)


async def _parse_header(img) -> dict:
    meta = {k: "" for k in _HEADER_FIELDS}
    w, h = img.size
    x0, y0, x1, y1 = _HEADER_CROP
    crop = img.crop((int(w * x0), int(h * y0), int(w * x1), int(h * y1)))
    text = await ocr_text(crop, psm=6)
    for key, rx in (
        ("MSN", _MSN_RE), ("MODEL", _MODEL_RE), ("FLEET_UNIT", _FLEET_UNIT_RE),
        ("AS_OF_DATE", _AS_OF_RE), ("ATT", _ATT_RE), ("ATC", _ATC_RE),
    ):
        m = rx.search(text)
        if m:
            meta[key] = m.group(1).strip(_CODE_STRIP_CHARS)
    return meta


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback (see
    sheet_types/ht.py) -- this variant's SIGNATURES is deliberately empty
    (see module docstring).

    Requires BOTH the bare "HARD TIME COMPONENT LISTING" title AND the
    ruled grid's own "TSLA ... CSLA ... DSLA" column-header fragment --
    the paired check matters since either alone could plausibly recur
    elsewhere; the combination is what this package's SIGNATURES/
    ocr_detect grep check (see module docstring) confirmed is unique to
    this template."""
    try:
        img = await render_page(pdf_path, 0, dpi=_DPI)
        w, h = img.size
        title_crop = img.crop((int(w * 0.20), 0, w, int(h * 0.06)))
        title_text = await ocr_text(title_crop, psm=6)
        if not _TITLE_RE.search(title_text):
            return False
        arr = np.array(img.convert("L"))
        lines = _find_horizontal_lines(arr)
        if len(lines) < 2:
            return False
        data_start = lines[1]
        header_crop = img.crop((0, max(data_start - 60, 0), w, data_start))
        header_text = (await ocr_text(header_crop, psm=6)).upper()
        normed = " ".join(header_text.split())
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
        # table's own closing bottom border) -- see module docstring
        # "_find_horizontal_lines" for why a single high-threshold
        # full-width scan gives all of this in one pass, safely excluding
        # the last page's own sign-off underline.
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
