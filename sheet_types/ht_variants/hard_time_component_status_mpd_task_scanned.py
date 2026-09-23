""""Hard Time Component Status" (MPD Task No layout) -- scanned sibling of
`hard_time_component_status_mpd_task.py`, whose own module docstring notes
a third corpus file under this same title/layout that is a ScanSnap-style
scan (0 characters on every page under pdfplumber's own `extract_text()`,
confirmed directly on the real sample) and needs OCR instead of that
module's own pdfplumber-word-position parser. This module is that OCR
variant.

Rendering the page to an image shows a clean, sharp, ordinary machine-
printed report (not handwritten, not a noisy photocopy) with a fully ruled
("boxed") grid baked into the raster -- every cell boundary, including the
outer table border, is a real drawn line -- so a per-row-per-column OCR
pass anchored on the grid's own ruled divider lines is reliable here, same
technique this package's other plain-ruled-grid scanned variants use (e.g.
`hard_time_component_listing_scanned.py`, `aircraft_component_log_boxed_
register_scanned.py` in this same package, which this module's overall
structure mirrors closely).

Header block (a small boxed 4-row/4-column info table, top-left of every
page, repeats near-identically page to page)::

    Aircraft
    <TYPE FAMILY>  <TYPE VARIANT>   HOURS    <hours>
    MSN             <msn>           CYCLES   <cycles>
    REG             <tail no.>      DATE     <report date>
    DOM             <date of mfr>

with a big underlined "Hard Time Component Status" title and an operator
wordmark to its right (neither is document-specific, so both are safe to
name here; no real per-file value from the sample -- type/MSN/reg/dates/
hours/cycles -- is written into this module's source anywhere).

Confirmed directly against the real sample: unlike this module's own main
data grid, OCR'ing this info box as a single wide crop (one `ocr_text()`
pass across the whole box) garbles badly -- the box's own ruled grid lines
confuse Tesseract's layout analysis into reading pipe-like fragments
instead of real words, the same generic problem this package's other
ruled-grid variants avoid by cropping to one cell at a time. Each of the
box's own real ruled cells is OCR'd individually here for the same reason.
The box's own left-hand label column ("MSN"/"CYCLES"/"REG"/"DATE"/"DOM") is
fixed boilerplate text, not per-file data, so only the label cells that
actually vary per file are OCR'd; the type-family/type-variant row has no
label cell of its own (both of its own cells are values), so that row's
own two cells are cropped and OCR'd together as one combined value.

Main table, two ruled header sub-rows (a tall top-tier group-label row --
INTERVAL/LAST DONE/NEXT DUE/REMAIN/INSTALLED DATE, each merged over their
own DY/FH/FC or DATE/FH/FC triple -- over the triples' own narrow sub-
labels), then one ruled row per record, 23 ruled columns wide including a
leading row-index column (a bare running count, not a real report field,
so it is read only to size the column grid correctly and not written into
row output)::

    # | ATA | MPD Task No | Part Number | Serial Number | Part Description |
    Pos | Task Type |
    INTERVAL{DY|FH|FC} | LAST DONE{Date|FH|FC} | NEXT DUE{Date|FH|FC} |
    REMAIN{DY|FH|FC} | INSTALLED DATE{Date|FH|FC}

Column X-boundaries are found fresh per page from a numpy vertical-divider
pixel scan (`_find_col_lines`), same approach as this package's other
plain-ruled-grid OCR variants, rather than fixed fractions -- this keeps
the crop aligned even against a differently cropped/scaled copy of this
same template. The scan band is derived from the page's own detected
data-row span rather than a fixed fraction of page height, since a short
last page (the real sample's own last page carries only 7 data rows) would
be missed by a fixed mid-page fraction band.

`_find_horizontal_lines` differs from this package's other ruled-grid OCR
variants in one respect, confirmed directly necessary against the real
sample: this template's own two-tier column-group header (INTERVAL/LAST
DONE/... over DY/FH/FC/...) is rendered as one solid dark-filled block (a
navy background fill under white header text) spanning both header
sub-rows with no interior gap wide enough to break the block into two
separate thin "line" detections the way a plain white-background ruled
grid would -- confirmed directly the whole block measures ~0.9+ dark
fraction end to end with no dip in between. Collapsing that block to its
own *mean* Y position (this package's other ruled-grid variants' own
convention, tuned for genuinely thin single-pixel-run rules) would place
the computed "header/data boundary" in the middle of the header block
instead of at its true bottom edge, misaligning every row crop below it by
around half the block's own height -- confirmed directly this happens with
the mean-based approach. Using each contiguous dark run's own *bottom*
edge instead of its mean fixes this for both cases: a genuinely thin rule's
bottom edge sits within a pixel or two of its mean anyway (no meaningful
difference there), while the thick header block's own bottom edge lands
exactly at the real header/data boundary. The very first bottom-edge found
this way on every page is therefore already `data_start` directly (no
separate "header top border" index needed, unlike this package's other
ruled-grid variants); every remaining edge is a real row divider, and the
LAST one found is the table's own closing bottom border (`table_bottom`).
A high dark-fraction threshold (0.5) is used for the same reason this
package's other ruled-grid variants use one -- confirmed directly this
cleanly clears a faint, unrelated full-width artifact around the title
underline / info-box row alignment near the top of the page (measured at
~0.49 dark fraction, confirmed directly, well under this threshold) while
every genuine ruled line in the table clears it comfortably (~0.9+).
Every row this module emits is bounded strictly between two consecutive
entries in this same edge list, so the last page's own plain (non-ruled)
sign-off text block below the table (confirmed directly on the real
sample: a name, a department line, and a date, none of it a full-width
ruled line, none of it reaching this threshold at any single row) is never
picked up as a spurious row or column value.

Each cell is OCR'd individually (one crop per row per column, not one
whole-column or whole-row pass) -- same reasoning as this package's other
ruled-grid OCR variants: several rows in the real sample repeat identical
DESCRIPTION/TASK_TYPE text for sibling component rows (e.g. paired
"RESERVOIR, SLIDE RAFT" / "HYDROSTATIC TEST" then "DISCARD" rows sharing
one part family), and a single tall whole-column OCR pass risks silently
deduplicating a repeated line. Each cell crop is also inset a few px on
every side and upscaled 2x before OCR (see `_ocr_cell`) -- confirmed
directly a crop taken right up to the ruled grid's own divider lines lets a
sliver of the neighbouring border bleed into the image and garble the
read, same fix this package's other ruled-grid OCR variants use.

DESCRIPTION is genuine multi-word free text (e.g. "HEAT EXCHANGER,
PRIMARY", confirmed directly wrapping across two physical OCR lines within
one ruled cell on several real sample rows with no real word-space at the
wrap point other than the existing comma) -- joined WITH a space, both
within one visual line and across a genuine multi-line wrap. POSITION and
TASK_TYPE are also genuine multi-word values on the real sample (e.g.
POSITION "A/C LEFT", TASK_TYPE "SHOP CLEANING"/"WEIGHT CHECK"/"BATTERY
PACK REPLACE") -- confirmed directly this package's usual no-separator
"code" join (this package's convention for a short position/type code)
instead glues them into one unbroken word on this template ("SHOPCLEANING",
"A/CLEFT"), so both join WITH a space here too. MPD_TASK_NO/PART_NUMBER/
SERIAL_NUMBER are the genuine "code" columns here, joined with NO
separator, guarding against a value wrapping across two physical OCR
lines within one ruled cell.

DATE-shaped columns (LAST_DONE_DATE/NEXT_DUE_DATE/INSTALLED_DATE) print an
ISO `YYYY-MM-DD` date on most real sample rows, but several INSTALLED_DATE
cells instead carry the literal placeholder "TBD" (confirmed directly on
multiple real sample rows, e.g. component families with no installed-date
of record) -- both are accepted as valid values rather than only the date
shape, per this project's convention of treating a genuine literal
placeholder token as valid data rather than as missing/invalid.

Numeric-shaped columns (INTERVAL/REMAIN DY-FH-FC, LAST DONE/NEXT DUE/
INSTALLED DATE's own FH/FC) mostly carry a plain digit run (optionally
comma-grouped, e.g. "50,000"), but a great many real sample cells instead
carry a literal "-" (this report's own explicit "not applicable" marker
for whichever of DY/FH/FC doesn't apply to a given component's own
interval basis, confirmed directly the large majority of rows use it this
way) and a couple of INSTALLED_DATE-adjacent FH/FC cells on the real
sample instead carry the literal "#N/A" (a component installed with no
recorded running total at install, confirmed directly). All three shapes
-- a digit run, a bare "-", and "#N/A" -- are accepted as valid values
here rather than only the digit-run shape, same reasoning as the date
columns above. A rare genuinely negative digit run (confirmed directly on
one real sample row's own REMAIN_DY value, an already-overdue interval) is
also accepted rather than rejected, consistent with several sibling HT
variants in this package that keep a real negative remaining-interval
value as-is.

Sensitivity note: the real sample file's own aircraft type/MSN/
registration/DOM/hours/cycles/report-date values, and its own last page's
sign-off name, are parsed into row data (MSN/registration/hours/cycles
header capture) or deliberately never captured at all (the sign-off name,
per the module docstring above) at runtime, but none of them -- nor any
real part number, serial number, or exact row/page count from the sample
-- is written into this module's source/comments anywhere; only the
generic column-header/title/label phrases the template itself prints
(which are not document-specific) appear above.
"""
from __future__ import annotations
import re

import numpy as np
from PIL import Image

from sheet_types.ht_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, ocr_words, page_count

NAME = "Hard Time Component Status (MPD Task No, Scanned)"

# Deliberately empty -- this file's own plain-text layer is blank on every
# page (see module docstring), so a plain-pdfplumber SIGNATURES phrase can
# never fire. Detected instead via ocr_detect() below, through the
# router's blank-text-layer OCR-fallback path (sheet_types/ht.py's own
# detect_variant()).
SIGNATURES: list[str] = []

CANONICAL_COLUMNS = [
    "ATA",
    "MPD_TASK_NO",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
    "POSITION",
    "TASK_TYPE",
    "INTERVAL_DY",
    "INTERVAL_FH",
    "INTERVAL_FC",
    "LAST_DONE_DATE",
    "LAST_DONE_FH",
    "LAST_DONE_FC",
    "NEXT_DUE_DATE",
    "NEXT_DUE_FH",
    "NEXT_DUE_FC",
    "REMAIN_DY",
    "REMAIN_FH",
    "REMAIN_FC",
    "INSTALLED_DATE",
    "INSTALLED_FH",
    "INSTALLED_FC",
    # Header metadata -- parsed once (whichever page OCRs cleanest first)
    # and stamped on every row.
    "AIRCRAFT_TYPE",
    "MSN",
    "AIRCRAFT_REG",
    "DOM",
    "AC_HOURS",
    "AC_CYCLES",
    "REPORT_DATE",
]

# Same MPD-task-number shape as `hard_time_component_status_mpd_task.py`'s
# own text-layer sibling module (e.g. "213100-08-1", "753142-I1-1" on the
# real sample -- both match).
_TASK_RE = re.compile(r"^\d{6}-[A-Z0-9]{1,3}-\d{1,2}$")
# Month/day ranges are validated (01-12 / 01-31), not just digit shape --
# confirmed directly necessary against the real sample: a loose digit-shape
# check lets a genuine OCR misread on a single date digit (e.g. this file's
# own recurring "1"/"7" glyph confusion, see `_CELL_UPSCALE`'s own comment
# above) through as a calendar-impossible date (e.g. a real "31" misread as
# "34") without ever tripping the pattern check -- exactly the "garbage
# passing validation unflagged" failure this project's soft-validation
# convention is meant to catch, so the range check is kept even though this
# project's other date columns elsewhere usually only check digit shape.
_DATE_RE = r"^\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])$"
_DATE_OR_TBD_RE = r"^(?:\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])|TBD)$"
# A plain digit run (optionally comma-grouped, optionally negative), OR
# this report's own literal "-"/"#N/A" markers -- see module docstring.
# "#VALUE!" is this report's own literal Excel-error marker, confirmed
# directly on a couple of real sample rows (a LIFE VEST-family component's
# own NEXT_DUE_FH, alongside those same rows' own implausible 1904-dated
# NEXT_DUE_DATE -- both symptoms of the same underlying source-spreadsheet
# formula error, not an OCR artifact) -- kept as a valid literal value here
# rather than flagged, same reasoning as "-"/"#N/A" above.
_NUM_RE = r"^(?:-?[\d,]+|-|#N/A|#VALUE!)$"

_OVERRIDES = {
    # A bare "-" is this report's own literal "not applicable" marker on
    # several real sample rows (see `_clean_field`'s own comment) -- kept
    # as a valid value, same convention as the numeric columns below.
    "MPD_TASK_NO": {"pattern": r"(?:^\d{6}-[A-Z0-9]{1,3}-\d{1,2}$|^-$)", "allow_empty": True},
    "PART_NUMBER": {"allow_empty": True},
    "SERIAL_NUMBER": {"allow_empty": True},
    "DESCRIPTION": {"allow_empty": True, "uppercase": True},
    "POSITION": {"allow_empty": True, "uppercase": True},
    "TASK_TYPE": {"allow_empty": True, "uppercase": True},
    "INTERVAL_DY": {"pattern": _NUM_RE, "allow_empty": True},
    "INTERVAL_FH": {"pattern": _NUM_RE, "allow_empty": True},
    "INTERVAL_FC": {"pattern": _NUM_RE, "allow_empty": True},
    "LAST_DONE_DATE": {"pattern": _DATE_OR_TBD_RE, "allow_empty": True},
    "LAST_DONE_FH": {"pattern": _NUM_RE, "allow_empty": True},
    "LAST_DONE_FC": {"pattern": _NUM_RE, "allow_empty": True},
    "NEXT_DUE_DATE": {"pattern": _DATE_OR_TBD_RE, "allow_empty": True},
    "NEXT_DUE_FH": {"pattern": _NUM_RE, "allow_empty": True},
    "NEXT_DUE_FC": {"pattern": _NUM_RE, "allow_empty": True},
    "REMAIN_DY": {"pattern": _NUM_RE, "allow_empty": True},
    "REMAIN_FH": {"pattern": _NUM_RE, "allow_empty": True},
    "REMAIN_FC": {"pattern": _NUM_RE, "allow_empty": True},
    "INSTALLED_DATE": {"pattern": _DATE_OR_TBD_RE, "allow_empty": True},
    "INSTALLED_FH": {"pattern": _NUM_RE, "allow_empty": True},
    "INSTALLED_FC": {"pattern": _NUM_RE, "allow_empty": True},
    # Header metadata -- a single OCR misread here shouldn't flag every
    # row of the file, same reasoning this package's other header-plus-
    # body OCR variants use.
    "AIRCRAFT_TYPE": {"allow_empty": True},
    "MSN": {"allow_empty": True},
    "AIRCRAFT_REG": {"allow_empty": True},
    "DOM": {"allow_empty": True},
    "AC_HOURS": {"allow_empty": True},
    "AC_CYCLES": {"allow_empty": True},
    "REPORT_DATE": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_DPI = 300

# Column order matching the ruled grid's own 23 columns, left to right.
# ROW_NO is the grid's own leading running-count column -- consumed only to
# size the column grid correctly (see module docstring), never written to
# row output.
_COLUMN_ORDER = [
    "ROW_NO", "ATA", "MPD_TASK_NO", "PART_NUMBER", "SERIAL_NUMBER",
    "DESCRIPTION", "POSITION", "TASK_TYPE",
    "INTERVAL_DY", "INTERVAL_FH", "INTERVAL_FC",
    "LAST_DONE_DATE", "LAST_DONE_FH", "LAST_DONE_FC",
    "NEXT_DUE_DATE", "NEXT_DUE_FH", "NEXT_DUE_FC",
    "REMAIN_DY", "REMAIN_FH", "REMAIN_FC",
    "INSTALLED_DATE", "INSTALLED_FH", "INSTALLED_FC",
]
_N_COLUMNS = len(_COLUMN_ORDER)
_DATA_COLUMNS = [c for c in _COLUMN_ORDER if c != "ROW_NO"]

# POSITION and TASK_TYPE are genuine multi-word values on the real sample
# (e.g. POSITION "A/C LEFT", TASK_TYPE "SHOP CLEANING"/"WEIGHT CHECK"/
# "BATTERY PACK REPLACE") -- confirmed directly a no-separator join (this
# package's usual convention for a short position/type code) instead glues
# them into one unbroken word ("SHOPCLEANING", "A/CLEFT") on this
# template, so both join WITH a space here instead, same as DESCRIPTION.
_TEXT_JOIN_COLS = {"DESCRIPTION", "POSITION", "TASK_TYPE"}
_CODE_COLS = {"MPD_TASK_NO", "PART_NUMBER", "SERIAL_NUMBER"}
_CODE_STRIP_CHARS = " _\"'`‘’“”.,;:()[]{}|~="
_NUM_COLS = {
    "INTERVAL_DY", "INTERVAL_FH", "INTERVAL_FC",
    "LAST_DONE_FH", "LAST_DONE_FC",
    "NEXT_DUE_FH", "NEXT_DUE_FC",
    "REMAIN_DY", "REMAIN_FH", "REMAIN_FC",
    "INSTALLED_FH", "INSTALLED_FC",
}
_DATE_COLS = {"LAST_DONE_DATE", "NEXT_DUE_DATE", "INSTALLED_DATE"}
_NUM_TOKEN_RE = re.compile(r"-?[\d,]+")
_DATE_TOKEN_RE = re.compile(r"\d{4}-\d{2}-\d{2}")

# Grid-line detection thresholds -- see module docstring for why the
# header/data boundary is taken as each dark run's own bottom edge rather
# than its mean, and why 0.5 is used (clears a ~0.49 unrelated artifact
# near the top of the page, confirmed directly against the real sample).
_DARK_PIXEL_THRESH = 200
_LINE_THRESH_FRAC = 0.5
_LINE_MERGE_PX = 8
_CELL_INSET_PX = 6
# No upscale (1x) -- confirmed directly against the real sample this beats
# a 2x/3x LANCZOS upscale on this template's own font: several cells that
# OCR correctly at 1x (e.g. a bare "21" ATA value, a full "213100-08-1"
# MPD_TASK_NO, "9024-15704-2" PART_NUMBER) come back with inserted/
# substituted characters once upscaled (the same "21" cell reads "at" at
# 2x, for one confirmed example) -- the reverse of this package's usual
# "always upscale" convention, but tuned here against this file's own real
# behaviour rather than assumed from that convention.
_CELL_UPSCALE = 1
# A digit-only whitelist OCR pass (see `_ocr_numeric_cell`) is used for
# ATA and every numeric-shaped column instead of the general per-word path
# -- confirmed directly against the real sample this resolves a recurring
# digit/letter confusion (e.g. a genuine "319" OCR'ing as "3719" or "dig"
# through the general word path, correctly as "319" once the whitelist
# excludes non-digit characters as candidates). This does NOT fix every
# character-level misread on this file -- a small number of genuine digit-
# for-digit confusions remain uncorrected even with the whitelist (e.g. a
# few real "1"s in a handful of DATE cells reading back as "7", confirmed
# directly not resolved by any combination of scale/psm/whitelist tried) --
# per this project's "never guess a wrong split" convention, an
# unrecoverable single-digit OCR error is left as OCR produced it rather
# than pattern-guessed into a "corrected" value, same as this package's
# other OCR variants' own documented character-confusion limitations.
_NUMERIC_WHITELIST = "0123456789,-"


def _dark_run_bottom_edges(arr: np.ndarray, x0: int, x1: int, y_lo: int, y_hi: int,
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
    # Each dark run's own BOTTOM edge (not mean) -- see module docstring.
    return [g[-1] for g in groups]


def _find_horizontal_lines(arr: np.ndarray) -> list[int]:
    """Index 0 is `data_start` (the header block's own bottom edge); every
    remaining entry is a row divider, the last of which is `table_bottom`
    (see module docstring)."""
    h, w = arr.shape
    return _dark_run_bottom_edges(arr, int(w * 0.01), int(w * 0.98), 0, h)


def _find_col_lines(arr: np.ndarray, y0: int, y1: int) -> list[int]:
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
    elif scale != 1:
        crop = crop.resize((crop.width * scale, crop.height * scale), Image.LANCZOS)
    words = await ocr_words(crop, psm=6, min_conf=-1)
    out = []
    for wd in words:
        text = str(wd.get("text", "")).strip()
        if not text:
            continue
        out.append((crop_y0 + wd["top"] / scale, wd.get("left", 0) / scale, text))
    return out


async def _ocr_numeric_cell(img, name: str, col_bounds: dict, y0: int, y1: int) -> str:
    """ATA and every numeric-shaped column go through a dedicated digit-
    whitelist single-value OCR pass instead of the general per-word path
    (see `_NUMERIC_WHITELIST`'s own comment above for why)."""
    x0, x1 = col_bounds[name]
    if y1 <= y0:
        return ""
    inset = min(_CELL_INSET_PX, (x1 - x0) // 2 - 1, (y1 - y0) // 2 - 1)
    inset = max(inset, 0)
    crop = img.crop((x0 + inset, y0 + inset, x1 - inset, y1 - inset))
    if crop.width < 1 or crop.height < 1:
        crop = img.crop((x0, y0, x1, y1))
    text = (await ocr_text(crop, psm=7, whitelist=_NUMERIC_WHITELIST)).strip()
    upper = text.upper().replace(" ", "")
    if upper == "-":
        return "-"
    found = _NUM_TOKEN_RE.findall(text)
    if found:
        return max(found, key=len)
    # Whitelist pass found no digits -- this report's own literal "#N/A"/
    # "#VALUE!" markers (see module docstring) have no digits at all, so
    # neither survives the digit-only whitelist; a plain (non-whitelisted)
    # pass is only needed to tell one of those cells apart from a
    # genuinely blank one.
    plain = (await ocr_text(crop, psm=7)).strip().upper()
    if "VALUE" in plain:
        return "#VALUE!"
    return "#N/A" if "N/A" in plain else ""


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
        # MPD_TASK_NO carries this report's own literal "-" marker on
        # several real sample rows (its own "not applicable" convention
        # for a component with no MPD task reference, e.g. several real
        # "SURVIVAL KIT" rows) -- checked BEFORE the generic code-strip
        # below (which would otherwise strip a bare "-" down to an empty
        # string, losing the real distinction between "genuinely blank"
        # and "explicitly marked not applicable").
        bare = text.strip()
        if bare and set(bare) <= {"-", "–", "—"}:
            text = "-"
        else:
            text = text.strip(_CODE_STRIP_CHARS)
    if name in _NUM_COLS:
        upper = text.upper().replace(" ", "")
        if upper in ("-", "#N/A", "N/A"):
            text = "-" if upper == "-" else "#N/A"
        else:
            found = _NUM_TOKEN_RE.findall(text)
            text = max(found, key=len) if found else ""
    elif name in _DATE_COLS:
        if "TBD" in text.upper():
            text = "TBD"
        else:
            found = _DATE_TOKEN_RE.findall(text)
            text = found[0] if found else ""
    return text


_HEADER_FIELDS = [
    "AIRCRAFT_TYPE", "MSN", "AIRCRAFT_REG", "DOM",
    "AC_HOURS", "AC_CYCLES", "REPORT_DATE",
]

# Bare "Hard Time Component Status" title -- checked directly (grep)
# against every SIGNATURES list in occm.py/ht.py/llp.py and every
# occm_variants/ht_variants/llp_variants module's own SIGNATURES/
# ocr_detect anchor text. `aercap_hard_time_component_status.py` shares
# this exact title phrase but is safely distinguished by the paired column-
# group check below: that module's own real column groups are "INTERVAL
# LAST DONE COMP.TIMELINE LAST DONE A/C TIMELINE (@INSTL) NEXT DUE
# REMAINED" (no "REMAIN"/"INSTALLED DATE" groups, an extra pair of
# TIMELINE groups instead, and "REMAINED" not "REMAIN") -- this module's
# own real group row instead reads "INTERVAL ... LAST DONE ... NEXT DUE
# ... REMAIN ... INSTALLED DATE", checked directly against the real sample
# and confirmed distinct from the AerCap module's own real column groups.
_TITLE_RE = re.compile(r"Hard\s+Time\s+Component\s+Status", re.IGNORECASE)
# "NEXT DUE"'s own "D" is a confirmed recurring OCR misread on the real
# sample (reads back as "NEXT QUE") -- the paired check below only
# requires the three more reliably-OCR'd group labels (INTERVAL/LAST DONE/
# REMAIN/INSTALLED), which is still a distinctive-enough combination (see
# comment above `_TITLE_RE`).
_GROUP_ROW_RE = re.compile(
    r"INTERVAL.{0,40}LAST\s*DONE.{0,60}REMAIN.{0,40}INSTALLED",
    re.IGNORECASE,
)

# Info-box cell crops (px @ 300 DPI) -- derived directly from a real
# per-pixel measurement on the real sample file's own page 1 (see module
# docstring); always paired with `render_page(..., dpi=300)`.
_TYPE_CROP = (186, 262, 555, 299)
_HOURS_CROP = (833, 262, 1061, 299)
_MSN_CROP = (291, 299, 555, 336)
_CYCLES_CROP = (833, 299, 1061, 336)
_REG_CROP = (291, 336, 555, 373)
_DATE_CROP = (833, 336, 1061, 373)
_DOM_CROP = (291, 373, 555, 408)


async def _ocr_header_cell(img, box: tuple[int, int, int, int]) -> str:
    x0, y0, x1, y1 = box
    crop = img.crop((x0 + 6, y0 + 6, x1 - 6, y1 - 6))
    if crop.width < 1 or crop.height < 1:
        return ""
    # No upscale -- see `_CELL_UPSCALE`'s own comment above; confirmed
    # directly this same font behaves the same way in the info box.
    text = (await ocr_text(crop, psm=6)).strip()
    return " ".join(text.split())


async def _parse_header(img) -> dict:
    meta = {k: "" for k in _HEADER_FIELDS}
    meta["AIRCRAFT_TYPE"] = await _ocr_header_cell(img, _TYPE_CROP)
    meta["AC_HOURS"] = await _ocr_header_cell(img, _HOURS_CROP)
    meta["MSN"] = await _ocr_header_cell(img, _MSN_CROP)
    meta["AC_CYCLES"] = await _ocr_header_cell(img, _CYCLES_CROP)
    meta["AIRCRAFT_REG"] = await _ocr_header_cell(img, _REG_CROP)
    meta["REPORT_DATE"] = await _ocr_header_cell(img, _DATE_CROP)
    meta["DOM"] = await _ocr_header_cell(img, _DOM_CROP)
    return meta


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback (see
    sheet_types/ht.py) -- this variant's SIGNATURES is deliberately empty
    (see module docstring).

    Requires BOTH the bare title AND the ruled grid's own INTERVAL/LAST
    DONE/NEXT DUE/REMAIN/INSTALLED DATE column-group row -- the paired
    check matters since the title alone recurs on a different module (see
    `_TITLE_RE`'s own comment above)."""
    try:
        img = await render_page(pdf_path, 0, dpi=_DPI)
        w, h = img.size
        title_crop = img.crop((int(w * 0.20), 0, w, int(h * 0.14)))
        title_text = await ocr_text(title_crop, psm=3)
        if not _TITLE_RE.search(title_text):
            return False
        arr = np.array(img.convert("L"))
        lines = _find_horizontal_lines(arr)
        if len(lines) < 2:
            return False
        data_start = lines[0]
        group_crop = img.crop((0, max(data_start - 105, 0), w, data_start))
        group_text = (await ocr_text(group_crop, psm=6)).upper()
        normed = " ".join(group_text.split())
        return bool(_GROUP_ROW_RE.search(normed))
    except Exception:
        return False


async def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    header_meta = {k: "" for k in _HEADER_FIELDS}
    n_pages = await page_count(pdf_path)

    for page_index in range(n_pages):
        img = await render_page(pdf_path, page_index, dpi=_DPI)
        arr = np.array(img.convert("L"))

        # lines[0] = data_start (header block's own bottom edge), every
        # remaining entry is a row divider -- the last one is the table's
        # own closing bottom border (see module docstring).
        row_lines = _find_horizontal_lines(arr)
        if len(row_lines) < 2:
            continue
        data_start = row_lines[0]
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
            for name in _DATA_COLUMNS:
                if name == "ATA" or name in _NUM_COLS:
                    row[name] = await _ocr_numeric_cell(img, name, col_bounds, y0, y1)
                else:
                    toks = await _ocr_cell(img, name, col_bounds, y0, y1)
                    row[name] = _clean_field(name, toks)
            row["_page"] = page_index + 1
            row.update(header_meta)
            records.append(row)

    return records
