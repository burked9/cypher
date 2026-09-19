""""<TYPE> <REG> HARD TIME COMPONENTS" report -- full-page-raster PDF, no
usable text layer at all (confirmed directly: `page.get_text()`/pdfplumber
`extract_text()` both return 0 characters on every page of the sample
file). Rendering to an image shows a clean, sharp, ordinary
machine-printed report (not handwritten, not a noisy photocopy) with a
fully ruled ("boxed") grid baked into the raster -- every cell boundary,
including the outer table border, is a real drawn line -- so a
per-row-per-column OCR pass anchored on the grid's own ruled divider
lines is reliable here, same technique this package's other plain-ruled-
grid scanned variants use (e.g. `service_life_limited_components_status_scanned.py`
and `ht_ruled_grid_time_limit_columns_scanned.py` in this same package).

Header block (page 1 only; every other page starts straight into the
column-header row and table data, confirmed directly)::

    <operator wordmark>              <TYPE> <REG> HARD TIME COMPONENTS
    +----------------+------------+
    | Updated        | <DATE>     |
    | THE LATEST     |            |
    | FLIGHT         | <DATE>     |
    | A/C TSN        | <number>   |
    | A/C CSN        | <number>   |
    +----------------+------------+

The title line's own generic "HARD TIME COMPONENTS" phrase (deliberately
NOT followed by "STATUS" -- that's a different, sibling report title used
by several other variants in this package, see `_TITLE_RE` below) sits to
the right of the operator's own wordmark graphic, which this module never
reads. The small info box's own two-column key:value layout (bold italic
white-on-blue labels, black-on-cyan values) does not OCR reliably as one
combined block at any psm tried (confirmed directly -- the coloured
background degrades a whole-box pass badly), but OCRs cleanly once split
into a label-only strip and a value-only strip, each on its own crop
(confirmed directly) -- same "narrow the crop until it reads cleanly"
move this package's other OCR variants use for a difficult region. The
box's own row boundaries are found fresh per page from the box's own
ruled divider lines (`_find_info_box_rows`) rather than hardcoded, and
only the first 4 rows are used even when a stray extra divider is picked
up nearby (the main table's own top border sits close enough below the
box's own bottom border on the sample file that a generous search window
can catch it too -- taking a fixed first-4-rows slice sidesteps needing a
precise cutoff between the two).

Every page (including page 1, below its own header block) repeats the
same 18-column ruled column-header row, then one physical ruled row per
record -- unlike some sibling scanned HT variants in this package, there
is no multi-sub-row merged identity cell here: every row repeats its own
MPD Ref/POS/PART NO/SERIAL NO/DESCRIPTION values in full, even when the
same component carries several different task lines back to back (e.g. a
reheater's own "Clean" row directly followed by its own "Leak Check"
row, both with identical identity columns) -- confirmed directly on the
sample file::

    MPD Ref | POS | PART NO | SERIAL NO | DESCRIPTION | TASK DESCRIPTION |
    INTERVAL{FH | FC | MO/YE/D} | LAST PERFORMED{DATE | FH | FC} |
    NEXT DUE{DATE | FH | FC} | REMAINING{DAYS | FH | FC}

"MPD Ref" is shortened to REF_NO here (matches this package's naming for
the equivalent field in sibling ruled-grid HT variants). "TASK
DESCRIPTION" is kept as its own field (TASK_DESCRIPTION) rather than
folded into DESCRIPTION -- the two are genuinely separate ruled columns
on this template, with DESCRIPTION holding the component's own name
(e.g. "SAFETY VALVE") and TASK_DESCRIPTION holding the maintenance action
(e.g. "RESTORATION", "Clean", "Leak Check").

Column X-boundaries are found fresh per page from a numpy vertical-
divider pixel scan (`_find_col_lines`), same approach as this package's
other plain-ruled-grid OCR variants, rather than fixed fractions -- this
keeps the crop aligned even against a differently cropped/scaled copy of
this same template. The scan band is restricted to a Y-window comfortably
inside the data rows on every page (confirmed directly against both a
page-1-shaped header, which starts lower down the page, and a plain
column-header-only page), so it never depends on which header shape a
given page happens to have.

The 18-column header row itself spans TWO physical ruled sub-rows (a
top-tier group label -- "INTERVAL"/"LAST PERFORMED"/"NEXT DUE"/
"REMAINING" -- over three single-tier sub-columns each; the first six
identity/description columns have no group label and are a single
taller merged header cell). A plain "N-th horizontal line" count can't
tell a page-1-shaped header (extra lines above it, from the info box)
apart from a plain header-only page, so this module does not count from
the top at all -- it instead scans for ruled divider lines strictly
inside the table's OWN column band (`_find_data_start`), which the info
box's own lines never reach (the box is narrower than the full table and
its own partial-width divider lines never cross the darkness threshold
computed across the whole table width, confirmed directly). Exactly
three such lines are found before the first real data row on every page
of the sample, header-box or not (outer top border, the sub-header's own
internal group-label divider, and the header/data boundary) -- the third
one is used as the data-start Y.

Row/column geometry: the outer table border and every internal grid line
render as solid, fully dark pixel runs at 300 DPI on every page checked
in the sample (confirmed directly via a numpy row/column darkness scan),
and every row below the header is an evenly spaced (~98px at 300 DPI)
ruled divider with no missing/merged lines anywhere in the sample. Each
cell is OCR'd individually (one crop per row per column, not one
whole-column pass down the page) -- confirmed directly this is necessary
here, not just a stylistic choice: this template repeats the exact same
DESCRIPTION/TASK_DESCRIPTION/PART_NUMBER text on many consecutive rows
(e.g. a long run of "PORTABLE OXYGEN BOTTLE"/"HYDROSTATIC TEST" rows, or
a repeated "900-700-039-12" part number), and Tesseract's own line
deduplication silently drops a repeated line from a single tall
whole-column OCR pass in exactly that situation -- a fresh single-row
crop per cell has no other rows in it for Tesseract to (wrongly)
deduplicate against, so no row is ever silently lost this way.

REMAINING DAYS/FH/FC (and no other column in the sample) can be negative
-- an overdue task prints its own remaining count with a leading "-"
(e.g. a battery's own "REGULAR CHECK" task past its own interval) -- so
this is the one numeric-token pattern in this module that accepts an
optional leading "-"; every other numeric column is a plain unsigned
digit run in every real row of the sample.

A handful of cells in the sample are a genuine dash "-" printed for "not
applicable" (e.g. INTERVAL FC on a calendar-only task, or NEXT DUE FH/FC
on a days-only task) -- the numeric/date token regexes never match a
bare dash, so these come back as an honest empty string rather than a
stray "-" character, same convention this package's other ruled-grid OCR
variants use.

One irregular row in the sample (a "DISCARD"-task chemical-oxygen-
generator line) prints "REFER ATTACHMENT LIST" spanning what would
otherwise be the DATE/FH/FC sub-columns of a group, rather than actual
per-column values -- this module does not attempt to detect or
specially merge that text back across the group's own three ruled
sub-columns; each sub-column simply gets whatever fragment of that
phrase falls inside its own narrow X-band (often only part of a word, or
nothing at all if it falls exactly on a column boundary), which the
column's own date/numeric-token cleaning then reduces to an honest empty
string. This is this project's usual "never force a wrong split"
handling for a genuinely merged/irregular cell -- no attempt is made to
reassemble the phrase into a single field.

A "Prepared by Maintenance Planning Department  <name> ___________"
sign-off line sits well below the table's own last ruled row on the
sample file's own last page (confirmed directly -- there is a large
blank gap between the table's own closing border and this line, and the
line itself carries no ruled grid of its own at all). Since every row
this module emits is built purely from the ruled grid's own detected
divider lines (never a blind page-bottom scan), that sign-off line is
never picked up as a spurious extra "row" and no signer name is ever
captured into any output field; no name from the sample file's own
sign-off line is written into this module's source either.

Sensitivity note: page 1's header carries a real operator wordmark and
this sample's own real aircraft type/registration/TSN/CSN and report
dates -- none of that is written into this module's code/comments (only
the generic column-header/title/info-box label phrases the template
itself prints, which are not document-specific). The header's
AIRCRAFT_TYPE/AIRCRAFT_REG/REPORT_UPDATED_DATE/LATEST_FLIGHT_DATE/
ACFT_TSN/ACFT_CSN fields ARE extracted into row data at runtime (same as
this project's other per-file header-metadata capture elsewhere in this
package) -- that is ordinary functional extraction, not a hardcoded
document-specific value in source code.
"""
from __future__ import annotations
import re

import numpy as np
from PIL import Image

from sheet_types.ht_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, ocr_words, page_count

NAME = "HT Ruled Grid, MPD Ref / Interval / Last Performed / Next Due / Remaining (Scanned)"

# Deliberately empty -- this file's own plain-text layer is blank on every
# page (see module docstring), so a plain-pdfplumber SIGNATURES phrase can
# never fire. Detected instead via ocr_detect() below, through the
# router's blank-text-layer OCR-fallback path (sheet_types/ht.py's own
# detect_variant()).
SIGNATURES: list[str] = []

CANONICAL_COLUMNS = [
    "REF_NO",
    "POSITION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
    "TASK_DESCRIPTION",
    "INTERVAL_FH",
    "INTERVAL_FC",
    "INTERVAL_MO_YE_D",
    "LAST_PERFORMED_DATE",
    "LAST_PERFORMED_FH",
    "LAST_PERFORMED_FC",
    "NEXT_DUE_DATE",
    "NEXT_DUE_FH",
    "NEXT_DUE_FC",
    "REMAINING_DAYS",
    "REMAINING_FH",
    "REMAINING_FC",
    # Header metadata -- parsed once (page 1) and stamped on every row.
    "AIRCRAFT_TYPE",
    "AIRCRAFT_REG",
    "REPORT_UPDATED_DATE",
    "LATEST_FLIGHT_DATE",
    "ACFT_TSN",
    "ACFT_CSN",
]

_DATE_RE = r"^\d{1,2}[.\-][A-Za-z]{3}[.\-]\d{2,4}$"
# Plain unsigned digit run, optional thousands separator -- every numeric
# column except REMAINING_* in the sample.
_NUM_RE = r"^\d[\d,]*$"
# REMAINING_* alone can carry a leading "-" for an overdue task (see
# module docstring).
_SIGNED_NUM_RE = r"^-?\d[\d,]*$"

_OVERRIDES = {
    "REF_NO": {"allow_empty": True},
    "POSITION": {"allow_empty": True, "uppercase": True},
    "PART_NUMBER": {"allow_empty": True},
    "SERIAL_NUMBER": {"allow_empty": True},
    "DESCRIPTION": {"allow_empty": True, "uppercase": True},
    "TASK_DESCRIPTION": {"allow_empty": True, "uppercase": True},
    "INTERVAL_FH": {"pattern": _NUM_RE, "allow_empty": True},
    "INTERVAL_FC": {"pattern": _NUM_RE, "allow_empty": True},
    "INTERVAL_MO_YE_D": {"pattern": _NUM_RE, "allow_empty": True},
    "LAST_PERFORMED_DATE": {"pattern": _DATE_RE, "allow_empty": True},
    "LAST_PERFORMED_FH": {"pattern": _NUM_RE, "allow_empty": True},
    "LAST_PERFORMED_FC": {"pattern": _NUM_RE, "allow_empty": True},
    "NEXT_DUE_DATE": {"pattern": _DATE_RE, "allow_empty": True},
    "NEXT_DUE_FH": {"pattern": _NUM_RE, "allow_empty": True},
    "NEXT_DUE_FC": {"pattern": _NUM_RE, "allow_empty": True},
    "REMAINING_DAYS": {"pattern": _SIGNED_NUM_RE, "allow_empty": True},
    "REMAINING_FH": {"pattern": _SIGNED_NUM_RE, "allow_empty": True},
    "REMAINING_FC": {"pattern": _SIGNED_NUM_RE, "allow_empty": True},
    # Header metadata -- a single OCR misread here shouldn't flag every
    # row of the file, same reasoning this package's other header-plus-
    # body OCR variants use.
    "AIRCRAFT_TYPE": {"allow_empty": True},
    "AIRCRAFT_REG": {"allow_empty": True},
    "REPORT_UPDATED_DATE": {"allow_empty": True},
    "LATEST_FLIGHT_DATE": {"allow_empty": True},
    "ACFT_TSN": {"allow_empty": True},
    "ACFT_CSN": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_DPI = 300

# Column order matching the ruled grid's own 18 columns, left to right.
_COLUMN_ORDER = [
    "REF_NO", "POSITION", "PART_NUMBER", "SERIAL_NUMBER", "DESCRIPTION",
    "TASK_DESCRIPTION",
    "INTERVAL_FH", "INTERVAL_FC", "INTERVAL_MO_YE_D",
    "LAST_PERFORMED_DATE", "LAST_PERFORMED_FH", "LAST_PERFORMED_FC",
    "NEXT_DUE_DATE", "NEXT_DUE_FH", "NEXT_DUE_FC",
    "REMAINING_DAYS", "REMAINING_FH", "REMAINING_FC",
]

_TEXT_JOIN_COLS = {"DESCRIPTION", "TASK_DESCRIPTION"}
_CODE_COLS = {"REF_NO", "PART_NUMBER", "SERIAL_NUMBER", "POSITION"}
_CODE_STRIP_CHARS = " _\"'`‘’“”.,;:()[]{}|~="
_UNSIGNED_NUM_COLS = {
    "INTERVAL_FH", "INTERVAL_FC", "INTERVAL_MO_YE_D",
    "LAST_PERFORMED_FH", "LAST_PERFORMED_FC", "NEXT_DUE_FH", "NEXT_DUE_FC",
}
_SIGNED_NUM_COLS = {"REMAINING_DAYS", "REMAINING_FH", "REMAINING_FC"}
_DATE_COLS = {"LAST_PERFORMED_DATE", "NEXT_DUE_DATE"}
_UNSIGNED_NUM_TOKEN_RE = re.compile(r"\d[\d,]*")
_SIGNED_NUM_TOKEN_RE = re.compile(r"-?\d[\d,]*")
_DATE_TOKEN_RE = re.compile(r"\d{1,2}[.\-][A-Za-z]{3}[.\-]\d{2,4}")

# Grid-line detection thresholds -- tuned directly against the real
# sample's own 300 DPI render (see module docstring "Row/column
# geometry"). The outer border and every internal divider render fully
# solid (dark fraction close to 1.0).
_DARK_PIXEL_THRESH = 200
_LINE_THRESH_FRAC = 0.5
_LINE_MERGE_PX = 6
# Column-line scan band, as a fraction of page height -- comfortably
# inside the data rows on both a page-1-shaped header (which starts
# lower down the page, see module docstring) and a plain header-only
# page, confirmed directly against both shapes in the sample.
_COL_SCAN_Y0_FRAC = 0.40
_COL_SCAN_Y1_FRAC = 0.75
# Header search window for _find_data_start -- see module docstring.
_HEADER_SEARCH_MAX_Y_FRAC = 0.40
_ROW_RESCAN_OFFSET_PX = 5
# Per-cell OCR crop tuning -- see `_ocr_cell`'s own docstring/comment for
# why the inset matters (grid-line bleed into the crop). Tuned directly
# against the real sample's own 300 DPI render.
_CELL_INSET_PX = 6
_CELL_UPSCALE = 2

_N_COLUMNS = len(_COLUMN_ORDER)


def _divider_lines(arr: np.ndarray, x0: int, x1: int, y_lo: int, y_hi: int,
                    dark_thresh: int = _DARK_PIXEL_THRESH) -> list[int]:
    frac = (arr[:, x0:x1] < dark_thresh).sum(axis=1) / (x1 - x0)
    ys = [y for y in range(y_lo, y_hi) if frac[y] > _LINE_THRESH_FRAC]
    groups: list[list[int]] = []
    for y in ys:
        if groups and y - groups[-1][-1] <= _LINE_MERGE_PX:
            groups[-1].append(y)
        else:
            groups.append([y])
    return [int(np.mean(g)) for g in groups]


def _find_col_lines(arr: np.ndarray) -> list[int]:
    """X-centers of the table's 19 vertical column dividers (18 columns),
    found fresh per page from a data-row-band vertical darkness scan (see
    module docstring)."""
    h, w = arr.shape
    y0, y1 = int(h * _COL_SCAN_Y0_FRAC), int(h * _COL_SCAN_Y1_FRAC)
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
    pairs = list(zip(col_lines[:-1], col_lines[1:]))[:_N_COLUMNS]
    return {name: bounds for name, bounds in zip(_COLUMN_ORDER, pairs)}


def _find_data_start(arr: np.ndarray, col_bounds: dict) -> int | None:
    """Top of the first real data row -- the third ruled divider found
    strictly inside the table's own column band, in the page's own top
    region (see module docstring for why a plain line-index count from
    the very top of the page can't be used instead)."""
    h = arr.shape[0]
    x0, x1 = col_bounds["REF_NO"][0], col_bounds["REMAINING_FC"][1]
    y_hi = int(h * _HEADER_SEARCH_MAX_Y_FRAC)
    lines = _divider_lines(arr, x0, x1, 0, y_hi)
    if len(lines) < 3:
        return None
    return lines[2]


async def _ocr_cell(img, name: str, col_bounds: dict, y0: int, y1: int) -> list[tuple[float, float, str]]:
    x0, x1 = col_bounds[name]
    if y1 <= y0:
        return []
    # Insetting a few px on every side before OCR -- confirmed directly
    # this matters a lot, not just tidiness: a crop taken right up to the
    # ruled grid's own divider lines lets a sliver of the neighbouring
    # border bleed into the image, which Tesseract reads as a stray
    # glyph fragment and blends into the real text (e.g. a genuine "R/H"
    # cell misread as "co"/"UH"/"PA" depending on exactly how much of the
    # line crept in) -- confirmed directly this single change (plus the
    # 2x upscale below) fixes every one of a 12-row sample of previously
    # misread POSITION cells on the real sample file, with no separate
    # per-column special-casing needed.
    inset = min(_CELL_INSET_PX, (x1 - x0) // 2 - 1, (y1 - y0) // 2 - 1)
    inset = max(inset, 0)
    crop_y0 = y0 + inset
    scale = _CELL_UPSCALE
    crop = img.crop((x0 + inset, crop_y0, x1 - inset, y1 - inset))
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
        # Coordinates are in the (inset + upscaled) crop's own pixel
        # space -- divide back down by the upscale factor and re-add the
        # inset's own page-space offset so `_clean_field`'s line-bucketing
        # tolerance (tuned in original page-space pixels) still applies
        # correctly regardless of which inset/scale branch ran above.
        out.append((crop_y0 + wd["top"] / scale, wd.get("left", 0) / scale, text))
    return out


def _clean_field(name: str, tokens: list[tuple[float, float, str]]) -> str:
    lines: list[list[tuple[float, float, str]]] = []
    for top, left, text in sorted(tokens, key=lambda t: t[0]):
        if lines and abs(top - lines[-1][0][0]) <= 12:
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
    if name in _UNSIGNED_NUM_COLS:
        found = _UNSIGNED_NUM_TOKEN_RE.findall(text)
        text = max(found, key=len) if found else ""
    elif name in _SIGNED_NUM_COLS:
        found = _SIGNED_NUM_TOKEN_RE.findall(text)
        text = max(found, key=len) if found else ""
    elif name in _DATE_COLS:
        found = _DATE_TOKEN_RE.findall(text)
        text = found[0] if found else ""
    return text


_HEADER_FIELDS = ["AIRCRAFT_TYPE", "AIRCRAFT_REG", "REPORT_UPDATED_DATE",
                  "LATEST_FLIGHT_DATE", "ACFT_TSN", "ACFT_CSN"]

# Bare "HARD TIME COMPONENTS" title, deliberately NOT followed by
# "STATUS" (that longer phrase belongs to several other, structurally
# different variants elsewhere in this package -- checked directly (grep)
# against every SIGNATURES list in occm.py/ht.py/llp.py and every
# occm_variants/ht_variants/llp_variants module's own SIGNATURES/
# ocr_detect anchor text: no other module anchors on this bare,
# un-suffixed phrase). TYPE/REG are captured from the same line as
# ordinary functional header-metadata extraction (not hardcoded values).
_TITLE_RE = re.compile(
    r"(?P<type>\S+(?:\s+\S+)*?)\s+(?P<reg>[A-Z0-9][A-Z0-9\-]{2,9})"
    r"\s+HARD\s+TIME\s+COMPONENTS(?!\s+STATUS)",
    re.IGNORECASE,
)

# Info-box crop bounds, as fractions of the page's own width/height --
# derived directly from a real per-pixel measurement on the sample file's
# page 1 (see module docstring for why the box is OCR'd as two separate
# label/value strips rather than one combined pass).
_BOX_X0_FRAC, _BOX_LABEL_X1_FRAC, _BOX_X1_FRAC = 0.1097, 0.1966, 0.2836
_BOX_Y0_FRAC, _BOX_Y1_FRAC = 0.10, 0.40
# Unlike the main table (a plain white background), this box's own cell
# fills are a solid mid-blue (labels) / pale cyan (values) -- confirmed
# directly that the main table's own dark-pixel threshold (tuned for a
# white background) reads the blue label cells as "dark" across their
# whole area and merges what should be 5 separate divider lines into 2,
# so the box's own row-divider scan uses a stricter threshold that only
# the real black ruled border lines cross, not the coloured cell fills.
_BOX_DARK_THRESH = 100


async def _find_info_box_rows(img) -> list[int]:
    arr = np.array(img.convert("L"))
    w, h = img.size
    x0 = int(_BOX_X0_FRAC * w)
    x1 = int(_BOX_X1_FRAC * w)
    y0 = int(_BOX_Y0_FRAC * h)
    y1 = int(_BOX_Y1_FRAC * h)
    return _divider_lines(arr, x0, x1, y0, y1, dark_thresh=_BOX_DARK_THRESH)


async def _parse_info_box(img) -> dict:
    """Page-1 "Updated / THE LATEST FLIGHT / A/C TSN / A/C CSN" info box
    -- see module docstring for why each of its 4 rows is OCR'd as a
    separate label/value crop pair rather than one whole-box pass."""
    meta = {"REPORT_UPDATED_DATE": "", "LATEST_FLIGHT_DATE": "",
            "ACFT_TSN": "", "ACFT_CSN": ""}
    lines = await _find_info_box_rows(img)
    # Only the box's own first 4 rows are used, even if a stray extra
    # divider is picked up nearby (see module docstring).
    if len(lines) < 5:
        return meta
    w = img.width
    label_x0, label_x1 = int(_BOX_X0_FRAC * w), int(_BOX_LABEL_X1_FRAC * w)
    value_x0, value_x1 = int(_BOX_LABEL_X1_FRAC * w), int(_BOX_X1_FRAC * w)
    keys = ["REPORT_UPDATED_DATE", "LATEST_FLIGHT_DATE", "ACFT_TSN", "ACFT_CSN"]
    for i, key in enumerate(keys):
        y0, y1 = lines[i], lines[i + 1]
        value_crop = img.crop((value_x0, y0, value_x1, y1))
        text = (await ocr_text(value_crop, psm=6)).strip()
        text = text.strip(_CODE_STRIP_CHARS + "\n")
        meta[key] = text
    return meta


async def _parse_title(img) -> dict:
    meta = {"AIRCRAFT_TYPE": "", "AIRCRAFT_REG": ""}
    w, h = img.size
    crop = img.crop((int(w * 0.40), int(h * 0.14), w, int(h * 0.19)))
    text = await ocr_text(crop, psm=7)
    m = _TITLE_RE.search(text)
    if m:
        meta["AIRCRAFT_TYPE"] = " ".join(m.group("type").split())
        meta["AIRCRAFT_REG"] = m.group("reg").strip()
    return meta


async def _parse_header(img) -> dict:
    meta = {k: "" for k in _HEADER_FIELDS}
    meta.update(await _parse_title(img))
    meta.update(await _parse_info_box(img))
    return meta


# This template's own distinctive column-header fragment -- checked
# directly (grep) against every SIGNATURES list in occm.py/ht.py/llp.py
# and every occm_variants/ht_variants/llp_variants module's own
# SIGNATURES/ocr_detect anchor text; combined with the title phrase above
# so neither alone has to be a unique anchor on its own.
_HEADER_ROW_RE = re.compile(r"MPD\s*REF.{0,60}TASK\s+DESCRIPTION", re.IGNORECASE)


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback (see
    sheet_types/ht.py) -- this variant's SIGNATURES is deliberately empty
    (see module docstring).

    Requires BOTH the bare "<TYPE> <REG> HARD TIME COMPONENTS" title
    (not "...COMPONENTS STATUS") AND the ruled grid's own "MPD Ref ...
    TASK DESCRIPTION" column-header row fragment -- the paired check
    matters since "HARD TIME COMPONENTS" alone is also a substring of
    several other variants' own title text elsewhere in this package
    (those all carry the longer "...STATUS" suffix, already excluded by
    the negative lookahead in `_TITLE_RE`, but the combined check is kept
    anyway as a second, independent signal)."""
    try:
        img = await render_page(pdf_path, 0, dpi=_DPI)
        w, h = img.size
        title_crop = img.crop((int(w * 0.40), int(h * 0.14), w, int(h * 0.19)))
        title_text = await ocr_text(title_crop, psm=7)
        if not _TITLE_RE.search(title_text):
            return False
        arr = np.array(img.convert("L"))
        col_lines = _find_col_lines(arr)
        col_bounds = _col_bounds_from_lines(col_lines)
        if col_bounds is None:
            return False
        data_start = _find_data_start(arr, col_bounds)
        if data_start is None:
            return False
        header_crop = img.crop((col_bounds["REF_NO"][0], max(data_start - 100, 0),
                                 col_bounds["REMAINING_FC"][1], data_start))
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

        col_lines = _find_col_lines(arr)
        col_bounds = _col_bounds_from_lines(col_lines)
        if col_bounds is None:
            continue

        if page_index == 0 and not all(header_meta.values()):
            header_meta = await _parse_header(img)

        data_start = _find_data_start(arr, col_bounds)
        if data_start is None:
            continue

        # Row boundaries are the ruled grid's own horizontal divider
        # lines below the header -- the table's own last row is bounded
        # by its own closing border, well above any sign-off line (see
        # module docstring), so no explicit last-row cap is needed.
        extra = _divider_lines(arr, col_bounds["REF_NO"][0], col_bounds["REMAINING_FC"][1],
                                data_start + _ROW_RESCAN_OFFSET_PX, img.height)
        row_lines = [data_start] + extra
        if len(row_lines) < 2:
            continue

        for i in range(len(row_lines) - 1):
            y0, y1 = row_lines[i], row_lines[i + 1]
            row: dict[str, str] = {}
            for name in _COLUMN_ORDER:
                # OCR'd per-row-per-column, one crop at a time -- see
                # module docstring "Row/column geometry" for why a
                # whole-column-per-page pass is unsafe on this template.
                toks = await _ocr_cell(img, name, col_bounds, y0, y1)
                row[name] = _clean_field(name, toks)
            row["_page"] = page_index + 1
            row.update(header_meta)
            records.append(row)

    return records
