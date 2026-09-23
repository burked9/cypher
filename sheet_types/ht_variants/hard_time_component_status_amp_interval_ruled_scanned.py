"""CAE Parc Aviation "Hard Time Component Status" ruled grid -- scanned,
rotated (landscape content in a portrait page reported as `page.rotation
== 270` on every page of the sample, confirmed directly via PyMuPDF), no
extractable text layer at all (confirmed directly: pdfplumber
`extract_text()` returns 0 characters on every page), so `SIGNATURES`
below is deliberately empty and detection happens entirely through
`ocr_detect()`.

A plain `render_page()` at any DPI comes out with the table's own rows
running vertically (page dimensions already come out portrait-shaped
post-render, but the raster CONTENT itself is still sideways) -- confirmed
directly this template's own `page.rotation` value does not by itself
produce an upright render the way it does for this package's other
rotated-page scanned variants; an explicit `img.rotate(90, expand=True)`
after every `render_page()` call is what actually puts the header/table
the right way up on every page of the sample (same general move as this
package's other rotated-scan siblings, e.g. `mm510_scanned.py`, just a
different confirmed angle for this specific template).

Header block (once per page, CAE Parc Aviation wordmark/title at top;
page 1 of the sample additionally carries a bordered aircraft-identity
info box -- Aircraft Reg/MSN, Model, ESN's, FH/FC, APU hours/cycles, the
report date -- directly under the title, which later pages omit)::

    CAE Parc Aviation           MSN <msn> Hard Time Component Status
    Aircraft FH: <n>   APU HOURS: <n>   Aircraft Date of Man.: <date>
    Aircraft FC: <n>   APU CYCLES: <n>
    Date: <date>
    ...
    Aircraft Reg / MSN: <reg>/<msn>   Aircraft TSN/CSN: <fh>:<fc>/<fc>
    Aircraft Model: <model>   ESN's #1 ...   ESN's #2 ...

Every page then repeats the same ruled, two-tier-header, 18-column grid,
one ruled row per record (confirmed directly the column count is stable
at 18 across every sampled page of this file)::

    ERJ-190 MPD Task Number | Zone/Position | MPD Maintenance Task
    Description | Type | Part Number | Serial Number |
    Parc Aviation AMP Interval{FH|FC|MO} |
    Component Time at Installation (TSN,CSN/TSO,CSO/TSR,CSR){FH|FC} |
    Component Expiry Date or Last Maintenance Date{DAYS/DATE} |
    Aircraft TSN/CSN at Installation or Last Service{FH|FC|DATE} |
    Next Due{FH|FC|DATE}

The header itself spans two physical ruled sub-rows: a top "group label"
row (several cells span both sub-rows -- Task Number/Zone/Description/
Type/Part Number/Serial Number -- while the four interval/date groups
each show only their own group label in the top row) and a bottom row
that carries the actual per-sub-column labels (Type / FH / FC / MO /
DAYS/DATE / DATE ...). Detecting column X-boundaries against the
COMBINED two-row header band fails outright here -- confirmed directly:
the header's own light-blue cell fill renders at a grayscale luminance
(~175-180) comfortably under even a generous "is this a ruled line" dark
cutoff, so a whole-header-band scan sees the entire filled area as "dark"
and every column collapses into one giant merged run. `_find_col_lines`
therefore scans only the bottom ~38% of the header band (confirmed
directly this always sits entirely within the bottom sub-row, whose own
individual FH/FC/MO/DATE column labels and their ruled boundaries are
real black text/lines against the same fill, not confused with it) at a
low, text-only dark cutoff (80) -- comfortably below the fill's own
luminance -- so only genuine black ink (rule lines, glyphs) registers,
never the coloured fill itself. This one combination reproduced the
template's own known 18-column count (19 dividers) on every sampled page
without needing a broader grid-search, confirmed directly.

Row-divider darkness varies drastically page to page in this file
(confirmed directly against a real sample: some pages' row rules measure
solidly dark, others noticeably fainter). The first approach tried here
was the prominence-based technique validated earlier this session on a
related CAE Parc Aviation template (that session's own scratch
`row_detect.py`) -- a per-row dark-pixel fraction MINUS a local rolling-
median background. Confirmed directly THAT approach fails on a
meaningful subset of this file's own pages: several of this template's
real ruled dividers render as a genuinely wide dark band (roughly 10-16px
tall at 300 DPI, not a crisp 1-2px hairline), and a prominence window
narrow enough to score a hairline peak ends up straddling most of that
wide band on both sides -- the local "background" it subtracts is itself
mostly interior to the real divider, so the divider's own prominence
collapses near zero and gets missed outright. Confirmed directly this
silently merged several consecutive real rows into one on at least one
sample page (their OCR'd fields visibly concatenated together with no
separator -- exactly the row-window-overlap/value-glue failure this
package's other variants are written to avoid), while widening the
prominence background window to compensate just traded that failure for
the opposite one (over-splitting single rows on other pages).

`_detect_row_dividers` instead grid-searches (dark cutoff x absolute
row-darkness-fraction threshold) directly -- same style of small grid
search as `_find_col_lines_adaptive` above, not prominence at all -- and
keeps whichever (dark, frac) combination yields the most candidates that
ALSO clear `_segment_relative_coverage` (the fraction of column segments
where that row's own local darkness beats that segment's own local
background by a relative multiplier). A genuine full-width ruled divider
lights up nearly every column segment this way regardless of its own
absolute darkness or band width, while a text-content row only lights up
the few segments that happen to hold glyphs at that y -- so this check
alone is what screens out false positives as the absolute threshold is
loosened, not the choice of threshold itself. Confirmed directly this
combination reproduces the correct, visually-verified row count on every
sampled page of this file, including the page whose divider bands are
wide enough to have broken the prominence approach. A final min-gap merge
(`_MIN_ROW_GAP`, well under this template's own real row pitch) collapses
any duplicate divider the grid search occasionally finds immediately
beside the header's own bottom border -- confirmed directly this can
otherwise register as a spurious near-zero-height extra "row".

This module deliberately does NOT add a pitch-regularization "fill in a
missed divider using the global row-pitch estimate" stage, unlike an
earlier prototype for a related file in this package's history. Directly
confirmed on this file's own page 5 sample: a genuine two-line-wrapped
task-description row leaves an honest, real gap in the divider spacing
(no missed rule there at all -- the segment-coverage check correctly
scores every candidate row in that gap as near-zero, i.e. plain body
text, not a divider) that is *wider* than the surrounding row pitch. A
naive pitch-based gap-fill would misread that gap as "one divider must be
missing here" and plant a spurious divider straight through real body
text, corrupting that row's own field split -- exactly the failure mode
flagged from a related file earlier this session. Relying only on
segment-coverage-validated peaks (never a global-pitch prior) avoids that
here. The header block's own two sub-rows are also structurally excluded
from ever entering the row-prominence scan at all (it only ever scans
strictly below the header band's own detected bottom edge), so the
header's own internal short row-to-row gaps can never contaminate this
file's row detection either.

Each cell is OCR'd individually (one crop per row per column) with a
small inset and 2x upscale before OCR, and the header/detection
conventions otherwise mirror this package's other plain-ruled-grid OCR
variants (e.g. `hard_time_component_listing_scanned.py`, which this
module's overall structure and cell-OCR/field-cleanup helpers closely
follow) -- see that module's own docstring for the general story on why a
per-cell crop (not a whole-column pass) matters, and why numeric/date
columns are reduced to only their own matching token rather than passed
through raw.

Sensitivity note: the sample file's own real MSN/registration/ESN/hours/
cycles/date values are extracted into row data at runtime as ordinary
per-file header-metadata capture (same as this project's other per-file
header extraction elsewhere in this package) but are NOT written into
this module's source/comments anywhere -- only the generic column-header/
title/label phrases the template itself prints (not document-specific)
appear above.
"""
from __future__ import annotations
import re

import numpy as np
from PIL import Image

from sheet_types.ht_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, ocr_words, page_count

NAME = "CAE Parc Aviation Hard Time Component Status (AMP Interval, Ruled Grid, Scanned)"

# Deliberately empty -- no extractable text layer on any page (see module
# docstring). Detected instead via ocr_detect() below, through the
# router's blank-text-layer OCR-fallback path (sheet_types/ht.py).
SIGNATURES: list[str] = []

_COLUMN_ORDER = [
    "MPD_TASK_NUMBER",
    "ZONE_POSITION",
    "TASK_DESCRIPTION",
    "TYPE",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "AMP_INTERVAL_FH",
    "AMP_INTERVAL_FC",
    "AMP_INTERVAL_MO",
    "INSTALL_FH",
    "INSTALL_FC",
    "EXPIRY_DAYS_DATE",
    "AC_TSN_AT_INSTALL_FH",
    "AC_CSN_AT_INSTALL_FC",
    "AC_DATE_AT_INSTALL",
    "NEXT_DUE_FH",
    "NEXT_DUE_FC",
    "NEXT_DUE_DATE",
]
_N_COLUMNS = len(_COLUMN_ORDER)

_HEADER_FIELDS = [
    "MSN", "AIRCRAFT_REG", "AIRCRAFT_MODEL", "REPORT_DATE",
    "AIRCRAFT_FH", "AIRCRAFT_FC",
]

CANONICAL_COLUMNS = _COLUMN_ORDER + _HEADER_FIELDS

_DATE_RE = r"^\d{1,2}[-\.][A-Za-z]{3}[-\.]\d{2,4}$"
_NUM_RE = r"^\d+(?:\.\d+)?$"

_OVERRIDES = {
    "MPD_TASK_NUMBER": {"allow_empty": True},
    "ZONE_POSITION": {"allow_empty": True, "uppercase": True},
    "TASK_DESCRIPTION": {"allow_empty": True, "uppercase": True},
    "TYPE": {"allow_empty": True, "uppercase": True},
    "PART_NUMBER": {"allow_empty": True},
    "SERIAL_NUMBER": {"allow_empty": True},
    "AMP_INTERVAL_FH": {"pattern": _NUM_RE, "allow_empty": True},
    "AMP_INTERVAL_FC": {"pattern": _NUM_RE, "allow_empty": True},
    "AMP_INTERVAL_MO": {"pattern": _NUM_RE, "allow_empty": True},
    "INSTALL_FH": {"pattern": _NUM_RE, "allow_empty": True},
    "INSTALL_FC": {"pattern": _NUM_RE, "allow_empty": True},
    "EXPIRY_DAYS_DATE": {"pattern": _DATE_RE, "allow_empty": True},
    "AC_TSN_AT_INSTALL_FH": {"pattern": _NUM_RE, "allow_empty": True},
    "AC_CSN_AT_INSTALL_FC": {"pattern": _NUM_RE, "allow_empty": True},
    "AC_DATE_AT_INSTALL": {"pattern": _DATE_RE, "allow_empty": True},
    "NEXT_DUE_FH": {"pattern": _NUM_RE, "allow_empty": True},
    "NEXT_DUE_FC": {"pattern": _NUM_RE, "allow_empty": True},
    "NEXT_DUE_DATE": {"pattern": _DATE_RE, "allow_empty": True},
    # Header metadata -- a single OCR misread here shouldn't flag every
    # row of the file, same reasoning this package's other header-plus-
    # body OCR variants use.
    "MSN": {"allow_empty": True},
    "AIRCRAFT_REG": {"allow_empty": True, "uppercase": True},
    "AIRCRAFT_MODEL": {"allow_empty": True, "uppercase": True},
    "REPORT_DATE": {"allow_empty": True},
    "AIRCRAFT_FH": {"allow_empty": True},
    "AIRCRAFT_FC": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_DPI = 300

# Genuine multi-word free text -- joined WITH a space.
_TEXT_JOIN_COLS = {"TASK_DESCRIPTION"}
# "Code" columns -- joined with NO separator (a wrapped part/serial number
# reassembles into one unbroken string rather than picking up a stray
# mid-token space), same convention as this package's other ruled-grid OCR
# variants.
_CODE_COLS = {"MPD_TASK_NUMBER", "PART_NUMBER", "SERIAL_NUMBER", "ZONE_POSITION", "TYPE"}
_CODE_STRIP_CHARS = " _\"'`‘’“”.,;:()[]{}|~="
_NUM_COLS = {
    "AMP_INTERVAL_FH", "AMP_INTERVAL_FC", "AMP_INTERVAL_MO",
    "INSTALL_FH", "INSTALL_FC",
    "AC_TSN_AT_INSTALL_FH", "AC_CSN_AT_INSTALL_FC",
    "NEXT_DUE_FH", "NEXT_DUE_FC",
}
_DATE_COLS = {"EXPIRY_DAYS_DATE", "AC_DATE_AT_INSTALL", "NEXT_DUE_DATE"}
_NUM_TOKEN_RE = re.compile(r"\d+(?:\.\d+)?")
_DATE_TOKEN_RE = re.compile(r"\d{1,2}[-\.][A-Za-z]{3}[-\.]\d{2,4}")

# Column grid-line detection -- see module docstring for why the scan is
# restricted to the bottom slice of the header band at a low, text-only
# dark cutoff (avoids the header's own coloured fill).
_HEADER_FILL_B_MINUS_R = 10
_HEADER_FILL_B_MIN = 150
_HEADER_FILL_R_MAX = 230
_HEADER_FILL_ROW_FRAC = 0.3
_SUBHEADER_BAND_START = 0.62  # fraction into the header band where the
                               # bottom (per-sub-column) row reliably starts
_COL_DARKS = (80, 100, 120, 140, 160, 180)
_COL_FRACS = (0.3, 0.4, 0.5, 0.6, 0.7)
_EXPECT_COL_DIVIDERS = _N_COLUMNS + 1

# Row-divider prominence/segment-coverage tuning (see module docstring).
# Row-rule darkness varies drastically page to page in this file
# (confirmed directly: some pages' rules need a dark cutoff as strict as
# 200 to avoid false positives, others need as loose as 253 -- a rule
# genuinely lighter than ordinary body text ink -- before it registers at
# all). Rather than one fixed cutoff, `_detect_row_dividers` grid-searches
# this small candidate list per page and keeps whichever cutoff yields the
# MOST segment-coverage-validated dividers: a too-strict cutoff misses
# real (but faint) dividers outright (confirmed directly this understates
# the count), while a too-loose cutoff that starts picking up stray body
# text instead is still screened out by the relative (local-vs-own-
# background) segment-coverage check, so it doesn't independently inflate
# the count the way a missed real divider deflates it -- more validated
# dividers at a looser cutoff is genuine signal, not noise, confirmed
# directly against this file's own real page samples.
_ROW_DARK_CANDIDATES = (180, 200, 215, 230, 245, 253)
_ROW_FRAC_CANDIDATES = (0.2, 0.25, 0.3, 0.35, 0.4, 0.5)
_ROW_MERGE_PX = 6
_SEG_COVERAGE_THRESH = 0.4
_SEG_HALF = 3
_SEG_INSET = 4
_SEG_BG_HALF = 10
_SEG_REL_MULT = 1.6
# Real row pitch on every sampled page is comfortably >80px -- a divider
# closer than this to the previous one is a duplicate detection (most
# often the header's own bottom border re-found a second time immediately
# below itself), not a genuine extra row (see module docstring).
_MIN_ROW_GAP = 20

_CELL_INSET_PX = 6
_CELL_UPSCALE = 2


def _rotate_upright(img: Image.Image) -> Image.Image:
    """This template's own confirmed fix -- see module docstring."""
    return img.rotate(90, expand=True)


def _header_band(img: Image.Image) -> tuple[int, int] | None:
    """Y-span of the ruled table's own two-tier coloured-fill header row,
    found by colour (light-blue fill) rather than a fixed page fraction --
    the sample's own page 1 carries an extra aircraft-identity info box
    above the table that later pages omit, so a fixed fraction would only
    work for some pages (confirmed directly)."""
    arr = np.array(img)
    r = arr[:, :, 0].astype(int)
    b = arr[:, :, 2].astype(int)
    blueish = (b > r + _HEADER_FILL_B_MINUS_R) & (b > _HEADER_FILL_B_MIN) & (r < _HEADER_FILL_R_MAX)
    frac = blueish.mean(axis=1)
    ys = np.where(frac > _HEADER_FILL_ROW_FRAC)[0]
    if len(ys) == 0:
        return None
    return int(ys.min()), int(ys.max())


def _find_col_lines(arr: np.ndarray, y0: int, y1: int, dark: int, thresh_frac: float,
                     merge_px: int = 4) -> list[int]:
    h, w = arr.shape
    if y1 <= y0:
        return []
    frac = (arr[y0:y1, :] < dark).sum(axis=0) / (y1 - y0)
    xs = [x for x in range(w) if frac[x] > thresh_frac]
    groups: list[list[int]] = []
    for x in xs:
        if groups and x - groups[-1][-1] <= merge_px:
            groups[-1].append(x)
        else:
            groups.append([x])
    return [int(np.mean(g)) for g in groups]


def _find_col_lines_adaptive(arr: np.ndarray, hy0: int, hy1: int) -> list[int] | None:
    ry0 = int(hy0 + (hy1 - hy0) * _SUBHEADER_BAND_START)
    ry1 = hy1
    for dark in _COL_DARKS:
        for frac in _COL_FRACS:
            cl = _find_col_lines(arr, ry0, ry1, dark, frac)
            if len(cl) == _EXPECT_COL_DIVIDERS:
                return cl
    return None


def _segment_relative_coverage(arr: np.ndarray, y: int, col_lines: list[int], dark: int,
                                half: int = _SEG_HALF, inset: int = _SEG_INSET,
                                bg_half: int = _SEG_BG_HALF, rel_mult: float = _SEG_REL_MULT) -> float:
    """Fraction of column segments where row `y`'s own local darkness
    beats that segment's own local background by `rel_mult` -- a genuine
    full-width ruled divider lights up nearly every segment this way; a
    text-content row only lights up the few segments that happen to hold
    glyphs at that y (see module docstring)."""
    h, w = arr.shape
    y0, y1 = max(0, y - half), min(h, y + half + 1)
    by0, by1 = max(0, y - bg_half), min(h, y + bg_half + 1)
    hits = 0
    total = 0
    for cx0, cx1 in zip(col_lines[:-1], col_lines[1:]):
        sx0, sx1 = cx0 + inset, cx1 - inset
        if sx1 <= sx0:
            continue
        total += 1
        local = (arr[y0:y1, sx0:sx1] < dark).mean()
        bg = (arr[by0:by1, sx0:sx1] < dark).mean()
        if local > max(bg * rel_mult, 0.15):
            hits += 1
    return hits / total if total else 0.0


def _raw_row_peaks(arr: np.ndarray, x0: int, x1: int, y_lo: int, y_hi: int,
                    dark: int, frac_thresh: float, merge_px: int = _ROW_MERGE_PX) -> list[int]:
    frac = (arr[y_lo:y_hi, x0:x1] < dark).sum(axis=1) / (x1 - x0)
    ys = np.where(frac > frac_thresh)[0]
    groups: list[list[int]] = []
    for y in ys:
        if groups and y - groups[-1][-1] <= merge_px:
            groups[-1].append(y)
        else:
            groups.append([y])
    return [y_lo + int(np.mean(g)) for g in groups]


def _merge_close_dividers(divs: list[int], min_gap: int = _MIN_ROW_GAP) -> list[int]:
    divs = sorted(divs)
    out = [divs[0]]
    for d in divs[1:]:
        if d - out[-1] < min_gap:
            continue
        out.append(d)
    return out


def _detect_row_dividers(arr: np.ndarray, col_lines: list[int], table_top: int) -> list[int]:
    """Row dividers strictly below `table_top` (the header band's own
    detected bottom edge) -- the header's own two sub-rows never enter
    this scan at all, so they can never contaminate it. No pitch-based
    gap-fill (see module docstring for why). See module docstring for why
    this grid-searches a raw (dark, frac_thresh) darkness threshold rather
    than a prominence peak."""
    h, w = arr.shape
    x0, x1 = col_lines[0], col_lines[-1]

    best_strong: list[int] = []
    for dark in _ROW_DARK_CANDIDATES:
        for frac_thresh in _ROW_FRAC_CANDIDATES:
            peaks = _raw_row_peaks(arr, x0, x1, table_top, h, dark, frac_thresh)
            strong = [y for y in peaks
                      if _segment_relative_coverage(arr, y, col_lines, dark) > _SEG_COVERAGE_THRESH]
            if len(strong) > len(best_strong):
                best_strong = strong
    # table_top itself is the header band's own confirmed bottom border --
    # always a real divider (the header/data boundary) even on a page
    # whose data area is short enough that no raw peak lands close enough
    # to re-find it as its own candidate (confirmed directly on this
    # file's own last, single-row page). The min-gap merge below then
    # drops a duplicate near-header candidate rather than keeping it as a
    # spurious extra "row" (see module docstring).
    return _merge_close_dividers(sorted(set([table_top] + best_strong)))


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


# Bare title anchor -- checked directly (grep) against every SIGNATURES
# list in occm.py/ht.py/llp.py and every occm_variants/ht_variants/
# llp_variants module's own SIGNATURES/ocr_detect anchor text: no other
# module in this package anchors on the "PARC AVIATION" + "HARD TIME
# COMPONENT STATUS" combination.
_TITLE_RE = re.compile(r"PARC\s+AVIATION", re.IGNORECASE)
_SUBTITLE_RE = re.compile(r"HARD\s+TIME\s+COMPONENT\s+STATUS", re.IGNORECASE)
# This template's own distinctive column-header fragment -- also checked
# directly (grep), unique to this module.
# Loose (unordered) word-presence check rather than a tight adjacency
# regex -- confirmed directly this header row's own OCR reads the group
# label row and the per-sub-column row interleaved out of their visual
# left-to-right cell order when crop'd and OCR'd as one combined text
# block (no per-cell crop at detection time), so "MPD" and "Task Number"
# do not reliably end up adjacent in the OCR'd string even though they
# are adjacent on the page -- checking each word's own presence avoids
# that false negative.
_HEADER_WORDS_RE = [re.compile(r"\bMPD\b", re.IGNORECASE), re.compile(r"\bTask\b", re.IGNORECASE)]

_MSN_RE = re.compile(r"MSN[/:\s]+(\S+)", re.IGNORECASE)
_REG_RE = re.compile(r"Reg\s*/\s*MSN\s*:?\s*([A-Z0-9\-]+)\s*/", re.IGNORECASE)
_MODEL_RE = re.compile(r"Aircraft\s+Model\s*:\s*(\S+)", re.IGNORECASE)
_DATE_RE_HDR = re.compile(r"\bDate\s*:\s*(\S+)", re.IGNORECASE)
_FH_RE = re.compile(r"Aircraft\s+FH\s*:\s*(\S+)", re.IGNORECASE)
_FC_RE = re.compile(r"Aircraft\s+FC\s*:\s*(\S+)", re.IGNORECASE)


async def _parse_header(img: Image.Image, hy0: int) -> dict:
    """Aircraft-identity metadata -- only present as a distinct info box
    on the sample's own page 1 (confirmed directly; later pages go
    straight from the title into the ruled grid), so this is only worth
    calling while any field is still unfilled."""
    meta = {k: "" for k in _HEADER_FIELDS}
    w, h = img.size
    crop = img.crop((0, 0, w, max(hy0, 1)))
    text = await ocr_text(crop, psm=6)
    for key, rx in (
        ("MSN", _MSN_RE), ("AIRCRAFT_REG", _REG_RE), ("AIRCRAFT_MODEL", _MODEL_RE),
        ("REPORT_DATE", _DATE_RE_HDR), ("AIRCRAFT_FH", _FH_RE), ("AIRCRAFT_FC", _FC_RE),
    ):
        m = rx.search(text)
        if m:
            meta[key] = m.group(1).strip(_CODE_STRIP_CHARS)
    return meta


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback (see
    sheet_types/ht.py) -- SIGNATURES is deliberately empty (see module
    docstring).

    Requires the "PARC AVIATION" wordmark/title AND the "HARD TIME
    COMPONENT STATUS" subtitle AND the ruled grid's own "MPD ... Task
    Number" column-header fragment -- the triple check matters since any
    one alone could plausibly recur elsewhere in this package (several
    other HT variants use "HARD TIME COMPONENT STATUS" alone, see module
    docstring)."""
    try:
        img = await render_page(pdf_path, 0, dpi=_DPI)
        img = _rotate_upright(img)
        w, h = img.size
        title_crop = img.crop((0, 0, w, int(h * 0.1)))
        title_text = await ocr_text(title_crop, psm=6)
        if not (_TITLE_RE.search(title_text) and _SUBTITLE_RE.search(title_text)):
            return False
        hb = _header_band(img)
        if hb is None:
            return False
        hy0, hy1 = hb
        header_row_crop = img.crop((0, max(hy0 - 10, 0), w, hy1))
        header_row_text = await ocr_text(header_row_crop, psm=6)
        return all(rx.search(header_row_text) for rx in _HEADER_WORDS_RE)
    except Exception:
        return False


async def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    header_meta = {k: "" for k in _HEADER_FIELDS}
    n_pages = await page_count(pdf_path)

    for page_index in range(n_pages):
        img = await render_page(pdf_path, page_index, dpi=_DPI)
        img = _rotate_upright(img)
        arr = np.array(img.convert("L"))

        hb = _header_band(img)
        if hb is None:
            continue
        hy0, hy1 = hb

        if not all(header_meta.values()):
            page_meta = await _parse_header(img, hy0)
            for k, v in page_meta.items():
                if v and not header_meta[k]:
                    header_meta[k] = v

        col_lines = _find_col_lines_adaptive(arr, hy0, hy1)
        if col_lines is None:
            continue
        col_bounds = _col_bounds_from_lines(col_lines)
        if col_bounds is None:
            continue

        row_lines = _detect_row_dividers(arr, col_lines, hy1)
        if len(row_lines) < 2:
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
