"""Latin-American-operator "Hard Time Components Status" report -- born-
scanned, full-page raster PDF, no usable text layer at all (confirmed
directly: `page.get_text()` returns 0 characters on every page of the
sample file, and it is otherwise a clean, sharp, ordinary machine-printed
report -- not handwritten, not a noisy photocopy -- with a fully ruled
("boxed") grid baked into the raster, every cell boundary including the
outer table border a real drawn line, so a per-row-per-column OCR pass
anchored on the grid's own ruled divider lines is reliable here, same
technique this package's other plain-ruled-grid scanned variants use
(e.g. `hard_time_component_listing_scanned.py` in this same package,
which this module's overall row/column-geometry approach mirrors).

Distinct from this project's other "Hard Time Components Status"-titled
variants (checked directly): this file's own title line is the bare,
unqualified phrase "HARD TIME COMPONENTS STATUS" (no "FOR
A/C-REGISTRATION" suffix like `georgian_airways_ht_components_status.py`/
`..._scanned.py`, no "REPORT" suffix like
`hard_time_day_fhr_cyc_matrix_scanned.py`), same as
`hard_time_components_status_mpd_or_requirement_scanned.py` -- but that
sibling's own 15-column grid (NOMENCLATURE / MPD NUMBER OR REQUIREMENT /
APPLICABLE / ... a two-tier "INSTALLATION INFORMATION"/"SERVICE
INFORMATION" grouped header) and its own REGISTER:/SERIAL NUMBER:/REPORT
DATE: header-block layout have no overlap with this file's own single-
tier 15-column grid or its own Aircraft-Model/Serial-Number/Registration
plus Date/TSN/CSN/Rev.n header-block layout (confirmed directly against
that module's source). This module's own detection anchors on the
title phrase combined with this file's own distinctive "MPD Card" column
label plus its own "Instalation" column label (the template's own
spelling, missing the second "l" -- confirmed directly this exact typo
does not appear anywhere else in this package's own ht_variants sources
except as prose in this docstring), a combination checked directly
(grep) against every other module's own SIGNATURES/ocr_detect anchor
text in this package -- unique to this template.

Header block (repeats near-identically at the top of every page, a small
operator wordmark to the left, a second wordmark top-right, three
label/value lines in a plain box to the left of the title, and a further
label/value strip below the title)::

    <wordmark>   Aircraft Model    <type>      <registration>  MSN
                 Serial Number     <msn>          Hard Time Components Status
                 Registration      <reg>                                          <wordmark 2>
                 Date  <dd-mon-yy>   TSN  <hours>   CSN  <cycles>   Rev.<n>

The centred "<registration>  MSN" line above the title is the template's
own running-header caption -- just the tail registration followed by the
literal label "MSN" with no value of its own printed beside it on the
sample file (the actual MSN value is the "Serial Number" field in the
left-hand info box); this module's own header-field parser treats it as
the REGISTRATION source and reuses the info box's own "Serial Number"
field as MSN, rather than trying to parse a non-existent value after the
literal "MSN" label.

Every page repeats the same 15-column ruled column-header row, then one
ruled row per record (confirmed directly identical on all 3 pages of the
sample)::

    ITEM | ATA | MPD Card | Component Description | Part Number |
    Serial Number | Limit | Control | Check | Instalation | Last Insp |
    Time Used | Remaining | Due Date | Document

Unlike some sibling ruled-grid HT variants in this package, this
column-header row is a single tier (no grouped/merged super-header cell)
and is the SAME ruled row height as every data row below it (~38-39px at
300 DPI on the sample) -- so it cannot be told apart from a data row by
height, only by position. The page's own full-width horizontal-divider
scan (`_find_horizontal_lines`) finds, in order: the page's own outer
content-box top border (index 0), the column-header row's own top
border (index 1), the column-header row's own bottom border ==
`data_start` (index 2), every remaining line a real row divider, and the
LAST one found is the table's own closing bottom border (`table_bottom`)
-- confirmed directly this holds on all 3 sample pages including the
short 16-row page 3. Every row this module emits is bounded strictly
between two consecutive lines at index >= 2 in this same list.

Column X-boundaries are found fresh per page from a numpy vertical-
divider pixel scan (`_find_col_lines`) within the page's own detected
data-row span, rather than fixed fractions -- confirmed directly this
keeps the crop aligned against per-page scan skew (the sample file's 3
pages each render at a very slightly different pixel width/height,
+/-6px). A markedly higher dark-fraction threshold than this package's
usual ~0.4-0.5 plain-ruled-grid default is needed here, confirmed
directly why: at the usual threshold the vertical scan across this
file's own tall, dense, 51-row (page 1) data band picks up dozens of
spurious "columns" from incidental vertical alignment of digit strokes
across unrelated rows in the file's own narrow, digit-heavy Limit/Time
Used/Remaining columns (59 spurious groups measured directly on the
sample's page 1 at threshold 0.5, only 16 of which are real column
dividers). Raising the threshold to 0.75 gives exactly the expected 16
groups (15 columns) on every one of the 3 sample pages, including the
short page 3.

OCR approach -- whitelist-per-column, not whole-column, not a plain
unrestricted per-cell pass:

This template's own row pitch is tight (~38px at 300 DPI) with several
genuinely narrow columns (ITEM, ATA are ~74px wide), and a first-pass
implementation using a plain unrestricted per-cell OCR pass (this
package's usual default -- e.g. `hard_time_component_listing_scanned.py`'s
own `_ocr_cell`) was confirmed DIRECTLY, against this real sample file,
to produce badly wrong output on narrow/coded columns: single-digit ITEM
values reading as letters ("1" -> "ze"/"i"/"l" depending on scale/psm,
no combination of upscale factor or PSM mode tried fixed this), MPD_CARD
values consistently substituting a "£" or "§" glyph for digit runs
(every single MPD_CARD cell on the test page corrupted this way), and
PART_NUMBER cells picking up a spurious leading letter/dash token from
the ruled cell border's own antialiasing (e.g. a genuine "024147-000"
reading as "r024147-000"). A whole-page-tall single-column OCR pass (all
51 rows of page 1 in one crop) was also tried directly as an
alternative for ITEM specifically -- Tesseract's own line/paragraph
layout analysis was confirmed to silently under-detect lines within a
long, sparse column with irregular row-to-row gaps (this template's own
blank continuation rows break the expected uniform line pitch), losing
or garbling values well before the bottom of the page -- so this was not
adopted for any column.

The fix confirmed directly to work well on this sample: restrict
Tesseract's own candidate character set to a per-column whitelist via
`ocr_text(..., whitelist=...)` (a real parameter this project's OCR
bridge exposes precisely for this reason -- see `shared/ocr_bridge.py`),
rather than the general unrestricted per-word pass. Excluding
non-plausible glyphs (letters from a numeric column, `£`/`§`/`\`/`<`
from every column) removes almost all of the misreads above outright --
confirmed directly cell-by-cell against a hand-checked sample: MPD_CARD
went from 0/8 correct to 6-7/8 correct, PART_NUMBER from badly garbled on
every row to correct on the large majority, and DUE_DATE-family date
cells from a handful of dropped leading digits to 8/8 correct, all on
the identical crops, whitelist being the only change. `_CELL_CONFIG`
below holds each column's own tuned whitelist/psm/inset/pad/scale (all
confirmed directly against the sample; see comments there for the
remaining specific tuning notes -- e.g. ITEM's own inset is deliberately
SMALLER than every other column's, confirmed directly this specific
column needs a sliver of its own ruled border left in the crop for
Tesseract to reliably resolve an isolated single digit, the opposite of
this package's usual "always fully remove the border" convention).

A residual level of single-character OCR confusion remains even with
the whitelist in place on a minority of cells (e.g. an occasional
genuine digit-for-digit substitution within an otherwise well-formed
number) -- this is the same documented, accepted limitation this
package's other whitelist-OCR HT variants already carry (see
`hard_time_component_status_mpd_task_scanned.py`'s own module docstring
for the equivalent limitation on its own file), not something this
module attempts to silently "correct" by guessing, per this project's
"never guess a wrong split" convention. Two columns' own RULES patterns
are tightened specifically to catch a residual failure mode confirmed
directly during this module's own construction rather than ship it
unflagged: MPD_CARD's own value is validated against this template's own
real `NN-NNN-NN` (optionally `/NN`) shape rather than left unconstrained,
since an uncaught whitelist residual (e.g. a doubled leading digit) still
produces a dash-separated numeric-looking string that would otherwise
slip through unflagged; CONTROL is validated against the closed
DAYS/FH/CYCLES vocabulary this template's own Control column is
confirmed to use throughout the sample (a misread like "Davs" for "Days"
is then flagged rather than silently accepted, since it fails that
pattern); DOCUMENT requires at least 3 whitelisted characters when
non-empty, since a couple of single stray-character OCR artifacts (a
lone "." or "G" where the real cell is blank) were confirmed directly on
the sample and are not plausible real Document values on their own.

No cell on this template's own sample file was found (checked directly,
every column, both by pattern and by eye on a broad manual sample) to
genuinely wrap its own value across two physical text lines within one
ruled row -- every value sits on a single visual line -- so this module,
unlike some sibling ruled-grid HT variants in this package, does not
need a separate multi-line-wrap-joining code path; each cell's OCR
result is used as a single string end to end.

Sensitivity note: the sample file's own real MSN/registration/aircraft-
type/hours/cycles/dates are extracted into row data at runtime (ordinary
functional header-metadata capture, same as this project's other
per-file header extraction elsewhere in this package) but are NOT written
into this module's source/comments anywhere -- only the generic
column-header/title/label phrases the template itself prints (not
document-specific) appear above.
"""
from __future__ import annotations
import re

import numpy as np
from PIL import Image, ImageOps

from sheet_types.ht_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, page_count

NAME = "Hard Time Components Status (PT Ruled Grid, Scanned)"

# Deliberately empty -- this file's own plain-text layer is blank on every
# page (see module docstring), so a plain-pdfplumber SIGNATURES phrase can
# never fire. Detected instead via ocr_detect() below, through the
# router's blank-text-layer OCR-fallback path (sheet_types/ht.py's own
# detect_variant()).
SIGNATURES: list[str] = []

CANONICAL_COLUMNS = [
    "ITEM",
    "ATA",
    "MPD_CARD",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "LIMIT",
    "CONTROL",
    "CHECK",
    "INSTALATION",
    "LAST_INSP",
    "TIME_USED",
    "REMAINING",
    "DUE_DATE",
    "DOCUMENT",
    # Header metadata -- parsed once (whichever page OCRs cleanest first)
    # and stamped on every row.
    "MSN",
    "REGISTRATION",
    "MODEL",
    "MANUFACTURE_DATE",
    "AS_OF_DATE",
    "TSN",
    "CSN",
    "REV",
]

_DATE_RE = r"^\d{1,2}-[A-Za-z]{3}-\d{2}$"
_NUM_RE = r"^\d+(?:\.\d+)?$"
_ITEM_RE = r"^\d+$"
# This template's own real MPD Card shape, confirmed directly across all
# 3 sample pages: two ATA digits, a 2-3 digit task group, a 2-digit
# sub-task, optionally a trailing "/NN" split-card suffix (e.g.
# "36-030-01/02", confirmed directly on the sample's own last page).
_MPD_CARD_RE = r"^\d{2}-\d{2,3}-\d{2}(?:/\d{2})?$"
# Closed vocabulary -- confirmed directly this template's own Control
# column uses only these 3 values throughout the sample (see module
# docstring).
_CONTROL_RE = r"^(?:DAYS|FH|CYCLES)$"
_DOCUMENT_RE = r"^[A-Z0-9 ./()#-]{3,}$"

_OVERRIDES = {
    "ITEM": {"pattern": _ITEM_RE, "allow_empty": True},
    "MPD_CARD": {"pattern": _MPD_CARD_RE, "allow_empty": True},
    "DESCRIPTION": {"allow_empty": True, "uppercase": True},
    "PART_NUMBER": {"allow_empty": True},
    "SERIAL_NUMBER": {"allow_empty": True},
    "LIMIT": {"pattern": _NUM_RE, "allow_empty": True},
    "CONTROL": {"pattern": _CONTROL_RE, "allow_empty": True, "uppercase": True},
    "CHECK": {"allow_empty": True, "uppercase": True},
    "INSTALATION": {"pattern": _DATE_RE, "allow_empty": True},
    "LAST_INSP": {"pattern": _DATE_RE, "allow_empty": True},
    "TIME_USED": {"pattern": _NUM_RE, "allow_empty": True},
    "REMAINING": {"pattern": _NUM_RE, "allow_empty": True},
    "DUE_DATE": {"pattern": _DATE_RE, "allow_empty": True},
    "DOCUMENT": {"pattern": _DOCUMENT_RE, "allow_empty": True, "uppercase": True},
    # Header metadata -- a single OCR misread here shouldn't flag every
    # row of the file, same reasoning this package's other header-plus-
    # body OCR variants use.
    "MSN": {"allow_empty": True},
    "REGISTRATION": {"allow_empty": True, "uppercase": True},
    "MODEL": {"allow_empty": True},
    "MANUFACTURE_DATE": {"allow_empty": True},
    "AS_OF_DATE": {"pattern": _DATE_RE, "allow_empty": True},
    "TSN": {"allow_empty": True},
    "CSN": {"allow_empty": True},
    "REV": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_DPI = 300

# Column order matching the ruled grid's own 15 columns, left to right.
_COLUMN_ORDER = [
    "ITEM", "ATA", "MPD_CARD", "DESCRIPTION", "PART_NUMBER", "SERIAL_NUMBER",
    "LIMIT", "CONTROL", "CHECK", "INSTALATION", "LAST_INSP", "TIME_USED",
    "REMAINING", "DUE_DATE", "DOCUMENT",
]
_N_COLUMNS = len(_COLUMN_ORDER)

_UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_LOWER = "abcdefghijklmnopqrstuvwxyz"
_DIGITS = "0123456789"


def _wl(chars: str) -> str:
    """Builds an `ocr_text(..., whitelist=...)` value. `shared/ocr_bridge.py`'s
    own local (non-Pyodide) path hands this string, unquoted, straight
    into pytesseract's own `config=` string, which pytesseract then splits
    with `shlex.split` before invoking the `tesseract` binary -- confirmed
    directly a whitelist containing a bare space (needed on every
    multi-word column below, e.g. DESCRIPTION, DOCUMENT) gets split apart
    there, silently truncating the applied whitelist at the first space
    and -- confirmed directly this is the actual observed effect, not
    just a theoretical risk -- losing every space in that column's own
    OCR'd output as a result (a genuine "Battery ULB, CVR" read back as
    "BatteryULB,CVR" with the bridge's own un-quoted whitelist string,
    fixed by this wrapping). Wrapping the value in literal double-quotes
    here survives `shlex.split` intact on that path (confirmed directly).
    The Pyodide/browser path (`deploy/assets/ocr_bridge.js`) hands this
    same string straight to Tesseract.js's own `tessedit_char_whitelist`
    option with no shell-style parsing at all, so the wrapping quotes
    would just become two literal extra permitted characters there --
    harmless (neither quote char is expected in any of this template's
    own column values) rather than a second bug to work around on that
    path. Only wrapping when a space is actually present keeps every
    other (already-working) whitelist in this module byte-identical to
    before this helper existed."""
    return f'"{chars}"' if " " in chars else chars

# Per-column OCR tuning -- see module docstring "OCR approach" section for
# the full story on why a per-column whitelist (rather than this
# package's usual unrestricted per-cell pass) is needed on this file, and
# why ITEM's own inset differs from every other column's.
#   whitelist: Tesseract candidate character set (ocr_text's own
#              `whitelist` param, see shared/ocr_bridge.py).
#   psm:       7 (single line) for every short, single-token/short-phrase
#              column; 6 (block) for the two columns that can carry a
#              genuine multi-word phrase (DESCRIPTION, DOCUMENT).
#   inset:     px trimmed from each crop edge before OCR, to drop the
#              ruled grid's own border line bleeding into the image --
#              6px for every column except ITEM (2px, see below).
#   pad:       px of white border added back after inset, before any
#              upscale -- confirmed directly this consistently helps
#              Tesseract's own layout analysis on a crop this small.
#   scale:     LANCZOS upscale factor applied after padding.
#   kind:      how `_clean_value` reduces the raw OCR string.
_CELL_CONFIG = {
    "ITEM": dict(whitelist=_DIGITS, psm=7, inset=2, pad=5, scale=1, kind="int"),
    "ATA": dict(whitelist=_DIGITS, psm=7, inset=6, pad=10, scale=1, kind="int"),
    "MPD_CARD": dict(whitelist=_DIGITS + "-/", psm=6, inset=6, pad=15, scale=2, kind="code"),
    "DESCRIPTION": dict(whitelist=_wl(_UPPER + _LOWER + _DIGITS + " ,.()/#-&"),
                         psm=6, inset=6, pad=10, scale=1, kind="text"),
    "PART_NUMBER": dict(whitelist=_UPPER + _LOWER + _DIGITS + "-/",
                         psm=6, inset=6, pad=15, scale=2, kind="code"),
    "SERIAL_NUMBER": dict(whitelist=_wl(_UPPER + _LOWER + _DIGITS + "-/ "),
                           psm=6, inset=6, pad=15, scale=2, kind="code"),
    "LIMIT": dict(whitelist=_DIGITS, psm=7, inset=6, pad=10, scale=1, kind="int"),
    "CONTROL": dict(whitelist=_wl(_UPPER + _LOWER + " "), psm=7, inset=6, pad=10, scale=1, kind="text"),
    "CHECK": dict(whitelist=_wl(_UPPER + _LOWER + " "), psm=7, inset=6, pad=10, scale=1, kind="text"),
    "INSTALATION": dict(whitelist=_UPPER + _LOWER + _DIGITS + "-./",
                         psm=7, inset=6, pad=10, scale=1, kind="date"),
    "LAST_INSP": dict(whitelist=_UPPER + _LOWER + _DIGITS + "-./",
                       psm=7, inset=6, pad=10, scale=1, kind="date"),
    "TIME_USED": dict(whitelist=_DIGITS, psm=7, inset=6, pad=10, scale=1, kind="int"),
    "REMAINING": dict(whitelist=_DIGITS, psm=7, inset=6, pad=10, scale=1, kind="int"),
    "DUE_DATE": dict(whitelist=_UPPER + _LOWER + _DIGITS + "-./",
                      psm=7, inset=6, pad=10, scale=1, kind="date"),
    "DOCUMENT": dict(whitelist=_wl(_UPPER + _LOWER + _DIGITS + " ./()#-"),
                      psm=6, inset=6, pad=10, scale=1, kind="text"),
}

_NUM_TOKEN_RE = re.compile(r"\d+(?:\.\d+)?")
# Either printed date form on this template -- a PT-abbreviated
# `D-mon-YY`/`D.mon.YY` token, or a plain numeric `DD/MM/YYYY` token (see
# module docstring for why both are needed).
_PT_DATE_TOKEN_RE = re.compile(r"(\d{1,2})[-\.]([A-Za-z]{3})[-\.](\d{2,4})")
_NUM_DATE_TOKEN_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")

# Full 12-month Portuguese-abbreviation -> English-3-letter translation
# table (see module docstring) -- built out fully rather than only the
# subset seen on the sample, since a scanned run of dates across a whole
# fleet's HT report is likely to hit every month eventually.
_PT_MONTHS = {
    "jan": "Jan", "fev": "Feb", "mar": "Mar", "abr": "Apr",
    "mai": "May", "jun": "Jun", "jul": "Jul", "ago": "Aug",
    "set": "Sep", "out": "Oct", "nov": "Nov", "dez": "Dec",
}
_NUM_MONTHS = {
    "01": "Jan", "02": "Feb", "03": "Mar", "04": "Apr",
    "05": "May", "06": "Jun", "07": "Jul", "08": "Aug",
    "09": "Sep", "10": "Oct", "11": "Nov", "12": "Dec",
}


def _clean_date(text: str) -> str:
    """Normalises either of this template's own two printed date forms
    (see module docstring) to one consistent `D-Mon-YY` output. Returns
    "" (never a guessed value) if neither form matches."""
    m = _PT_DATE_TOKEN_RE.search(text)
    if m:
        day, mon, year = m.groups()
        mon_en = _PT_MONTHS.get(mon.lower())
        if mon_en:
            yy = year[-2:].zfill(2)
            return f"{day}-{mon_en}-{yy}"
    m = _NUM_DATE_TOKEN_RE.search(text)
    if m:
        day, mon_num, year = m.groups()
        mon_en = _NUM_MONTHS.get(mon_num.zfill(2))
        if mon_en:
            yy = year[-2:]
            return f"{day}-{mon_en}-{yy}"
    return ""


_CODE_STRIP_CHARS = " _\"'`.,;:()[]{}|~="
_TEXT_STRIP_CHARS = " _\"'`.,;:|~="


def _clean_code(text: str) -> str:
    """Picks the real value out of a whitelist-restricted OCR string that
    still carries a spurious extra token -- confirmed directly on the
    sample this happens on a minority of MPD_CARD/PART_NUMBER/
    SERIAL_NUMBER cells even with the column's own whitelist applied (a
    single stray leading letter/digit/dash token from the ruled border's
    own antialiasing, space-separated from the real value by Tesseract's
    own word segmentation). The real value is the token containing a
    digit if any token does (true for every genuine PART_NUMBER/
    MPD_CARD/most SERIAL_NUMBER values on this template); a purely
    alphabetic multi-token result (this template's own literal "SEE
    INVENTORY"/"Not Instal" values, confirmed directly on the sample) is
    kept joined with a single space rather than reduced to one token,
    since neither is a border-bleed artifact."""
    tokens = text.split()
    if not tokens:
        return ""
    digit_tokens = [t for t in tokens if any(c.isdigit() for c in t)]
    if digit_tokens:
        return max(digit_tokens, key=len)
    return " ".join(tokens)


def _clean_value(name: str, raw: str) -> str:
    kind = _CELL_CONFIG[name]["kind"]
    text = raw.strip()
    if kind == "int":
        found = _NUM_TOKEN_RE.findall(text)
        return max(found, key=len) if found else ""
    if kind == "date":
        return _clean_date(text)
    if kind == "code":
        return _clean_code(text).strip(_CODE_STRIP_CHARS)
    # kind == "text" -- collapse internal whitespace, strip stray
    # whitelisted punctuation runs at the ends only. Parens/brackets are
    # deliberately NOT in this strip set (unlike _CODE_STRIP_CHARS) --
    # DOCUMENT's own real values genuinely end in a close-paren on this
    # template (e.g. "SERVICE PART TAG (ALOHA)", confirmed directly on
    # the sample), which _CODE_STRIP_CHARS would wrongly truncate.
    return " ".join(text.split()).strip(_TEXT_STRIP_CHARS)


# Grid-line detection thresholds -- tuned directly against the real
# sample's own 300 DPI render (see module docstring for the full story on
# both thresholds below).
_DARK_PIXEL_THRESH = 200
_LINE_THRESH_FRAC = 0.5
_LINE_MERGE_PX = 8
_COL_THRESH_FRAC = 0.75
_COL_MERGE_PX = 4


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
    """Every genuine ruled horizontal line on the page, full width. Index
    0 is the page's own outer content-box top border, index 1 is the
    column-header row's own top border, index 2 is `data_start`, and
    every remaining entry is a row divider -- the last of which is
    `table_bottom` (see module docstring)."""
    h, w = arr.shape
    return _divider_lines(arr, int(w * 0.01), int(w * 0.98), 0, h)


def _find_col_lines(arr: np.ndarray, y0: int, y1: int) -> list[int]:
    """X-centers of the table's own vertical column dividers, found fresh
    per page within the page's own detected data-row span -- a markedly
    higher threshold than this package's usual plain-ruled-grid default
    is needed here (see module docstring)."""
    h, w = arr.shape
    y0 = max(y0, 0)
    y1 = min(y1, h)
    if y1 <= y0:
        return []
    frac = (arr[y0:y1, :] < _DARK_PIXEL_THRESH).sum(axis=0) / (y1 - y0)
    xs = [x for x in range(w) if frac[x] > _COL_THRESH_FRAC]
    groups: list[list[int]] = []
    for x in xs:
        if groups and x - groups[-1][-1] <= _COL_MERGE_PX:
            groups[-1].append(x)
        else:
            groups.append([x])
    return [int(np.mean(g)) for g in groups]


def _col_bounds_from_lines(col_lines: list[int]) -> dict | None:
    if len(col_lines) < _N_COLUMNS + 1:
        return None
    # Real column dividers are the leftmost N_COLUMNS+1 lines found -- a
    # spurious extra line occasionally picked up well past the table's
    # own real right border is dropped by only taking the first
    # N_COLUMNS+1 (same convention as this package's other ruled-grid OCR
    # variants).
    pairs = list(zip(col_lines[:-1], col_lines[1:]))[:_N_COLUMNS]
    return {name: bounds for name, bounds in zip(_COLUMN_ORDER, pairs)}


async def _ocr_cell(img, name: str, col_bounds: dict, y0: int, y1: int) -> str:
    """Whitelist-restricted single-cell OCR pass -- see module docstring
    "OCR approach" section for why this (rather than this package's usual
    unrestricted per-word pass) is used on this file."""
    x0, x1 = col_bounds[name]
    if y1 <= y0:
        return ""
    cfg = _CELL_CONFIG[name]
    inset = min(cfg["inset"], (x1 - x0) // 2 - 1, (y1 - y0) // 2 - 1)
    inset = max(inset, 0)
    crop = img.crop((x0 + inset, y0 + inset, x1 - inset, y1 - inset))
    if crop.width < 1 or crop.height < 1:
        crop = img.crop((x0, y0, x1, y1))
    if cfg["pad"]:
        crop = ImageOps.expand(crop, border=cfg["pad"], fill=255)
    if cfg["scale"] != 1:
        crop = crop.resize((crop.width * cfg["scale"], crop.height * cfg["scale"]), Image.LANCZOS)
    raw = await ocr_text(crop, psm=cfg["psm"], whitelist=cfg["whitelist"])
    return _clean_value(name, raw)


_HEADER_FIELDS = [
    "MSN", "REGISTRATION", "MODEL", "MANUFACTURE_DATE", "AS_OF_DATE",
    "TSN", "CSN", "REV",
]

# Bare "HARD TIME COMPONENTS STATUS" title, combined with this template's
# own distinctive "MPD Card" / "Instalation" column labels -- checked
# directly (grep) against every SIGNATURES list and every module's own
# SIGNATURES/ocr_detect anchor text in occm.py/ht.py/llp.py and every
# occm_variants/ht_variants/llp_variants module: the bare title phrase
# alone recurs (see module docstring), but this combination does not.
_TITLE_RE = re.compile(r"HARD\s+TIME\s+COMPONENTS\s+STATUS", re.IGNORECASE)
_HEADER_ROW_RE = re.compile(r"MPD\s*CARD.{0,300}INSTALATION", re.IGNORECASE | re.DOTALL)

_MODEL_RE = re.compile(r"craft\s*Model\s*[:\-]?\s*(\S+)", re.IGNORECASE)
_MSN_RE = re.compile(r"Serial\s*Number\s*[:\-]?\s*([\d.]+)", re.IGNORECASE)
_REG_RE = re.compile(r"Registration\s*[:\-]?\s*(\S+)", re.IGNORECASE)
_MANUF_DATE_RE = re.compile(r"Manufactur\w*\s*Date\s*[:\-]?\s*(\S+)", re.IGNORECASE)
_AS_OF_RE = re.compile(r"\bDate\b\s*[:\-]?\s*(\S+)", re.IGNORECASE)
_TSN_RE = re.compile(r"\bTSN\b\s*[:\-]?\s*([\d.]+)", re.IGNORECASE)
_CSN_RE = re.compile(r"\bCSN\b\s*[:\-]?\s*([\d.]+)", re.IGNORECASE)
_REV_RE = re.compile(r"\bRev\.?\s*([A-Za-z0-9]+)", re.IGNORECASE)

# Header/info-block crop -- full page width, from the top down to the
# column-header row's own top border (`data_start`'s predecessor line),
# derived at runtime rather than a fixed fraction since it covers both
# the left-hand info box and the title/Date-TSN-CSN-Rev strip below it in
# one combined OCR pass (see module docstring).
_HEADER_CROP_BOTTOM_FRAC = 0.16


async def _parse_header(img, header_bottom_y: int | None) -> dict:
    meta = {k: "" for k in _HEADER_FIELDS}
    w, h = img.size
    y1 = header_bottom_y if header_bottom_y else int(h * _HEADER_CROP_BOTTOM_FRAC)
    crop = img.crop((0, 0, w, y1))
    text = await ocr_text(crop, psm=6)
    m = _MODEL_RE.search(text)
    if m:
        meta["MODEL"] = m.group(1).strip(_CODE_STRIP_CHARS)
    m = _MSN_RE.search(text)
    if m:
        meta["MSN"] = m.group(1).strip(_CODE_STRIP_CHARS)
    m = _REG_RE.search(text)
    if m:
        meta["REGISTRATION"] = m.group(1).strip(_CODE_STRIP_CHARS).upper()
    m = _MANUF_DATE_RE.search(text)
    if m:
        meta["MANUFACTURE_DATE"] = m.group(1).strip(_CODE_STRIP_CHARS)
    m = _AS_OF_RE.search(text)
    if m:
        meta["AS_OF_DATE"] = _clean_date(m.group(1))
    m = _TSN_RE.search(text)
    if m:
        meta["TSN"] = m.group(1).strip(_CODE_STRIP_CHARS)
    m = _CSN_RE.search(text)
    if m:
        meta["CSN"] = m.group(1).strip(_CODE_STRIP_CHARS)
    m = _REV_RE.search(text)
    if m:
        meta["REV"] = m.group(1).strip(_CODE_STRIP_CHARS)
    return meta


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback (see
    sheet_types/ht.py) -- this variant's SIGNATURES is deliberately empty
    (see module docstring).

    Requires BOTH the bare "HARD TIME COMPONENTS STATUS" title AND the
    ruled grid's own "MPD Card ... Instalation" column-header fragment --
    the paired check matters since the bare title alone recurs elsewhere
    in this package (see module docstring); the combination is unique."""
    try:
        img = await render_page(pdf_path, 0, dpi=_DPI)
        w, h = img.size
        # A full-width title crop was tried directly first and confirmed
        # to garble the title text badly -- the left-hand Aircraft-Model/
        # Serial-Number/Registration info box sits at the same Y range as
        # the title and its own text interleaves with the title's own
        # large centred text under one psm=6 block pass (e.g. "Hard Time
        # Components Status" coming back as "H d Ti C t St t", confirmed
        # directly). Restricting the crop to the title's own X range
        # (between the left info box and the right-hand wordmark) fixes
        # this, confirmed directly against the sample.
        title_crop = img.crop((int(w * 0.30), int(h * 0.02), int(w * 0.78), int(h * 0.11)))
        title_text = await ocr_text(title_crop, psm=6)
        if not _TITLE_RE.search(title_text):
            return False
        arr = np.array(img.convert("L"))
        lines = _find_horizontal_lines(arr)
        if len(lines) < 3:
            return False
        data_start = lines[2]
        header_row_crop = img.crop((0, max(lines[1] - 5, 0), w, data_start + 5))
        header_row_text = (await ocr_text(header_row_crop, psm=6)).upper()
        normed = " ".join(header_row_text.split())
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

        # lines[0] = page's own outer content-box top border,
        # lines[1] = column-header row's own top border,
        # lines[2] = data_start, every remaining entry is a row divider
        # (the last one is the table's own closing bottom border) -- see
        # module docstring "_find_horizontal_lines" paragraph.
        all_lines = _find_horizontal_lines(arr)
        if len(all_lines) < 4:
            continue
        data_start = all_lines[2]
        row_lines = all_lines[2:]
        table_bottom = row_lines[-1]

        if not all(header_meta.values()):
            page_meta = await _parse_header(img, all_lines[1])
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
                row[name] = await _ocr_cell(img, name, col_bounds, y0, y1)
            # A genuinely blank ruled row (confirmed directly: the sample
            # file's own last page carries one empty trailing row inside
            # the ruled grid, below its own last real record but above
            # the table's closing border) is dropped entirely rather than
            # emitted as an all-empty record -- a continuation sub-row
            # (blank ITEM/ATA/MPD_CARD but a real DESCRIPTION/PART_NUMBER/
            # SERIAL_NUMBER, confirmed directly on several sample rows)
            # is never mistaken for this, since it always keeps at least
            # one of those three fields populated.
            if not (row["DESCRIPTION"] or row["PART_NUMBER"] or row["SERIAL_NUMBER"]):
                continue
            row["_page"] = page_index + 1
            row.update(header_meta)
            records.append(row)

    return records
