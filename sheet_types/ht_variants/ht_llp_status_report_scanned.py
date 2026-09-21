""""Hard Time Components and Life Limited Parts Status Report" -- born-
scanned, full-page-raster PDF, no usable text layer at all (confirmed
directly: `page.get_text()` returns `""` on every page of the sample file,
and `page.get_drawings()` is empty while `page.get_images()` holds exactly
one full-page raster image per page -- the ruled grid visible on render is
baked into that raster image, not vector-drawn). Rendering to an image
shows a clean, sharp, ordinary machine-printed report (not handwritten,
not a noisy photocopy) with a fully ruled ("boxed") grid baked into the
raster on 5 of the sample file's 6 pages, so a per-column-strip OCR pass
anchored on the grid's own ruled divider lines is reliable here, same
technique this package's other plain-ruled-grid scanned variants use
(e.g. `hard_time_components_status_mpd_or_requirement_scanned.py`). The
sample file's own LAST page is a genuinely different, lower-contrast scan
generation (confirmed directly -- a visibly grainier, slightly skewed
photocopy-style raster, at a different pixel size/aspect ratio from the
other 5 pages, with the ruled table sitting at different page margins);
this module locates the table's own header band, data-start Y and left/
right edges structurally on every page rather than assuming a fixed
layout, specifically so that page still extracts (see `_find_table_x_span()`
and `_ocr_column()`'s own docstring notes below for the two page-generation
differences this required handling).

Header block (repeats verbatim near the top of every page -- an operator
wordmark graphic to the left of a tail/MSN line, plus two small label:value
boxes to the right, one for actual utilization, one for a "planning
forecast" that is blank on the sample file)::

    <type>, MSN: <msn>          Hard Time Components and Life Limited
                                 Parts Status Report
    <wordmark graphic>  <tail>, MSN <msn>   Status Report at: <date>
                                             Total A/C Hours: <n>
                                             Total A/C Cycles: <n>
                                             Utilization date: <date>

This module never reads the operator's own wordmark graphic or name --
only the generic report title, the aircraft type/MSN/tail line and the
utilization box are parsed, none of which name the operator.

Main table, three ruled header rows tall (row 1: several single-row-tall
column labels plus 5 grouped headers -- "Limit", "A/C Data", "Component
Data", "A/C", "Remaining"; row 2: "Installed at" under the two Data
groups, "Next Due to" under "A/C"; row 3: the leaf sub-column labels)::

    Pg No | ATA | MP Task | CMM | Part Number | FIN | Description | Action |
    Limit{FH | FC | Time} | Serial Number Fitted | Date of Manufacture |
    Date of last Inspection EASA F1 | Aircraft Installation |
    A/C Data Installed at{FH | FC} | Component Data Installed at{FH | FC} |
    A/C Next Due to{FH | FC | Date} | Remaining{FH | FC | Days}

25 leaf columns. Column X-boundaries below are expressed as a fraction of
the ruled table's OWN detected width (not the rendered page's width -- see
`_COLUMNS`' own docstring note just above it for why) -- derived directly
from a numpy column-darkness scan of the ruled grid's own vertical divider
lines, restricted to the row-3 (leaf-label) header band on the sample
file's page 1 (a divider that only separates a grouped sub-column, e.g.
Limit's own FH/FC/Time split, only spans that bottom band, not the full
3-row header height -- scanning only the row-3 band, which every column's
own divider line passes through regardless of how many header rows it
spans, recovers the complete 26-line/25-column set in one pass; scanning
the full 3-row header band instead over-detects two extra false dividers,
thin vertical strokes inside the bold "A/C Data"/"Component Data" group-
header text itself, confirmed directly by cropping and inspecting that
region). Confirmed against the sample file's other pages.

Row anchor: ATA (a bare 1-2 digit chapter number, occasionally a
dual-chapter "NN/NN" pair, e.g. "24/79" for a component tracked under two
chapters at once) is used as the per-row Y anchor -- confirmed directly on
the sample file to be present, single-line, on every physical ruled row,
including rows whose PG_NO/MP_TASK/CMM/FIN cells are blank. PG_NO by
contrast is only printed once per multi-row component group (blank on
that component's own continuation rows, and occasionally itself a
"<n>.<sub>" compound like "11.1"/"11.2" for a component tracked as two
parallel installed units under one shared page link) and MP_TASK sometimes
holds a "CMM <ref>" string instead of a task code, so neither is used as
the anchor.

Row grain: one row per ruled table row -- unlike several sibling HT
variants, this file's identity cells (PART_NUMBER/FIN/DESCRIPTION/...) are
NOT forward-filled/blanked across a component's own multiple task rows;
confirmed directly on the sample file each ruled row repeats its own
identity cells in full where the source itself repeats them, and leaves a
cell genuinely blank (not merged) where the source does too -- no
forward-fill is applied here to avoid inventing a value the source itself
does not repeat.

Numeric columns (LIMIT_FH/LIMIT_FC/LIMIT_TIME, the four *_FH/*_FC
"Installed at" columns, NEXTDUE_FH/NEXTDUE_FC, REMAINING_FH/REMAINING_FC/
REMAINING_DAYS) print a thousands-grouped value with a plain space
separator (e.g. "48 619") rather than a comma/dot -- OCR tokenizes on
that same whitespace, so each column's own per-row tokens are joined with
a plain space and the shared `clean_cell` pipeline's own `no_spaces` rule
(set in this module's own `_OVERRIDES` below) collapses that back into a
single digit run downstream, rather than re-implementing thousands-group
re-joining locally. A cell reading "n/a" (this report's own not-applicable
marker, printed in an italic serif face) is recognized even through
Tesseract's own common misreadings of the italic "/" (as "l", "1" or "i")
and normalized to a plain lowercase "n/a" before the pattern check, so it
validates cleanly rather than flagging every not-tracked-by-this-basis row
as a bad value -- date columns can legitimately read "n/a" too (e.g. a
component tracked only by FH/FC has no calendar NEXT_DUE date) and get the
same normalization.

Date columns (DATE_OF_MANUFACTURE, LAST_INSPECTION_DATE,
AIRCRAFT_INSTALL_DATE, NEXTDUE_DATE) use this report's own `DD-Mon-YYYY`
format (e.g. "16-Apr-2014") and are sometimes literally "unknown" (seen on
DATE_OF_MANUFACTURE for several rows in the sample file) -- both shapes,
plus "n/a", are accepted by this module's own date pattern.

Sensitivity note: the sample file's last page carries a signature block
(two handwritten signature marks, "Prepared by:"/"Checked by:" captions
and a generic job-title line) below the ruled table, well past that
page's own last real ATA anchor -- since every row this module emits is
built by walking ATA anchors outward to the other columns (never a blind
whole-column scan) and each row's own vertical span is explicitly capped
against its neighbours (see `extract()` below), that signature block never
lines up with an anchor and never enters any output field. No signer name
is captured into any output field.

Known limitation: the sample file's own last page (the different, lower-
contrast scan generation described above) has only ~9 real data rows and
visibly noisier per-character OCR than the other 5 pages even after the
contrast stretch this module applies -- confirmed directly, a small
number of its own MP_TASK/PART_NUMBER free-text cells come back with
scattered character-level noise (e.g. a stray leading punctuation glyph)
that this module does not attempt to fully repair, consistent with this
project's "a dropped/noisy stray artifact is preferred over a confidently-
wrong guessed correction" convention -- those free-text fields carry no
pattern rule in `RULES` to flag on, so a human reviewer should sanity-
check that one page's own MP_TASK/PART_NUMBER values specifically.
"""
from __future__ import annotations
import re

import numpy as np
from PIL import Image, ImageOps

from sheet_types.ht_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_words, ocr_text, page_count

NAME = "Hard Time Components and Life Limited Parts Status Report (Scanned)"

# Deliberately empty -- this file's own plain-text layer is blank on every
# page (see module docstring), so a plain-pdfplumber SIGNATURES phrase
# would never be checked against real page content anyway. Detected
# instead via ocr_detect() below, through the router's blank-text-layer
# OCR-fallback path (sheet_types/ht.py's own detect_variant()).
SIGNATURES: list[str] = []

CANONICAL_COLUMNS = [
    "PG_NO",
    "ATA",
    "MP_TASK",
    "CMM",
    "PART_NUMBER",
    "FIN",
    "DESCRIPTION",
    "ACTION",
    "LIMIT_FH",
    "LIMIT_FC",
    "LIMIT_TIME",
    "SERIAL_NUMBER",
    "DATE_OF_MANUFACTURE",
    "LAST_INSPECTION_DATE",
    "AIRCRAFT_INSTALL_DATE",
    "ACDATA_INSTALLED_FH",
    "ACDATA_INSTALLED_FC",
    "COMPDATA_INSTALLED_FH",
    "COMPDATA_INSTALLED_FC",
    "NEXTDUE_FH",
    "NEXTDUE_FC",
    "NEXTDUE_DATE",
    "REMAINING_FH",
    "REMAINING_FC",
    "REMAINING_DAYS",
    # Header metadata -- same on every page of a given file, stamped on
    # every row.
    "AIRCRAFT_TYPE",
    "AIRCRAFT_MSN",
    "TAIL_NUMBER",
    "REPORT_DATE",
    "TOTAL_AC_HOURS",
    "TOTAL_AC_CYCLES",
    "UTILIZATION_DATE",
]

_NUM_OR_NA_RE = r"^-?\d+$|^n/a$"
# Every date column can legitimately read "n/a" too (e.g. a component
# tracked only by FH/FC has no calendar NEXT_DUE date) -- confirmed
# directly on the sample file.
_DATE_RE = r"^\d{1,2}-[A-Za-z]{3}-\d{2,4}$|^unknown$|^n/a$"

_OVERRIDES = {
    # PG_NO is occasionally a "<n>.<sub>" compound (e.g. "11.1"/"11.2" for
    # a component tracked as two parallel installed units under one page
    # link) -- confirmed directly on the sample file.
    "PG_NO":                  {"allow_empty": True, "pattern": r"^\d+(\.\d+)?$"},
    # int_range explicitly cleared (set None): the GLOBAL_RULES default
    # ATA entry's own (20, 83) range assumes a single-chapter value, but
    # this report's own dual-chapter "NN/NN" shape (e.g. "24/79") is a
    # valid real value here (see module docstring) and isn't a bare int
    # for that range check to parse in the first place.
    "ATA":                    {"allow_empty": True, "pattern": r"^\d{2}(/\d{2})?$",
                               "int_range": None},
    "MP_TASK":                {"allow_empty": True, "uppercase": True},
    "CMM":                    {"allow_empty": True, "uppercase": True},
    "PART_NUMBER":            {"allow_empty": True, "uppercase": True},
    "FIN":                    {"allow_empty": True, "uppercase": True},
    "DESCRIPTION":            {"allow_empty": True},
    "ACTION":                 {"allow_empty": True},
    "LIMIT_FH":               {"allow_empty": True, "no_spaces": True, "pattern": _NUM_OR_NA_RE},
    "LIMIT_FC":               {"allow_empty": True, "no_spaces": True, "pattern": _NUM_OR_NA_RE},
    "LIMIT_TIME":             {"allow_empty": True, "no_spaces": True, "pattern": _NUM_OR_NA_RE},
    "SERIAL_NUMBER":          {"allow_empty": True, "uppercase": True},
    "DATE_OF_MANUFACTURE":    {"allow_empty": True, "pattern": _DATE_RE},
    "LAST_INSPECTION_DATE":   {"allow_empty": True, "pattern": _DATE_RE},
    "AIRCRAFT_INSTALL_DATE":  {"allow_empty": True, "pattern": _DATE_RE},
    "ACDATA_INSTALLED_FH":    {"allow_empty": True, "no_spaces": True, "pattern": _NUM_OR_NA_RE},
    "ACDATA_INSTALLED_FC":    {"allow_empty": True, "no_spaces": True, "pattern": _NUM_OR_NA_RE},
    "COMPDATA_INSTALLED_FH":  {"allow_empty": True, "no_spaces": True, "pattern": _NUM_OR_NA_RE},
    "COMPDATA_INSTALLED_FC":  {"allow_empty": True, "no_spaces": True, "pattern": _NUM_OR_NA_RE},
    "NEXTDUE_FH":             {"allow_empty": True, "no_spaces": True, "pattern": _NUM_OR_NA_RE},
    "NEXTDUE_FC":             {"allow_empty": True, "no_spaces": True, "pattern": _NUM_OR_NA_RE},
    "NEXTDUE_DATE":           {"allow_empty": True, "pattern": _DATE_RE},
    "REMAINING_FH":           {"allow_empty": True, "no_spaces": True, "pattern": _NUM_OR_NA_RE},
    "REMAINING_FC":           {"allow_empty": True, "no_spaces": True, "pattern": _NUM_OR_NA_RE},
    "REMAINING_DAYS":         {"allow_empty": True, "no_spaces": True, "pattern": _NUM_OR_NA_RE},
    # Header metadata -- a single OCR misread here shouldn't flag every
    # row of the file, same reasoning this package's other header-plus-body
    # OCR variants use.
    "AIRCRAFT_TYPE":          {"allow_empty": True},
    "AIRCRAFT_MSN":           {"allow_empty": True},
    "TAIL_NUMBER":            {"allow_empty": True},
    "REPORT_DATE":            {"allow_empty": True},
    "TOTAL_AC_HOURS":         {"allow_empty": True},
    "TOTAL_AC_CYCLES":        {"allow_empty": True},
    "UTILIZATION_DATE":       {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Column X-boundaries, as a fraction of the ruled table's OWN detected
# width (not the rendered page's width -- see `_find_table_x_span()`
# below) -- derived directly from a numpy column-darkness scan of the
# ruled grid's own vertical divider lines, restricted to the row-3 (leaf
# column label) header band, on the sample file's page 1 (see module
# docstring for why that band specifically). Table-relative rather than
# page-relative because the sample file's own last page is a genuinely
# different scan generation from the other 5 (see module docstring) -- a
# page-width-relative fraction set calibrated on the other 5 pages lands
# off by several hundred px on that one, while a table-width-relative set
# transfers cleanly since `_find_table_x_span()` re-locates this page's
# own actual table left/right edges structurally every time.
_COLUMNS = [
    (0.000000, 0.022763, "PG_NO"),
    (0.022763, 0.042365, "ATA"),
    (0.042365, 0.087259, "MP_TASK"),
    (0.087259, 0.117610, "CMM"),
    (0.117610, 0.175782, "PART_NUMBER"),
    (0.175782, 0.211192, "FIN"),
    (0.211192, 0.298451, "DESCRIPTION"),
    (0.298451, 0.395194, "ACTION"),
    (0.395194, 0.427442, "LIMIT_FH"),
    (0.427442, 0.451786, "LIMIT_FC"),
    (0.451786, 0.480556, "LIMIT_TIME"),
    (0.480556, 0.539994, "SERIAL_NUMBER"),
    (0.539994, 0.584572, "DATE_OF_MANUFACTURE"),
    (0.584572, 0.629466, "LAST_INSPECTION_DATE"),
    (0.629466, 0.676573, "AIRCRAFT_INSTALL_DATE"),
    (0.676573, 0.703446, "ACDATA_INSTALLED_FH"),
    (0.703446, 0.731268, "ACDATA_INSTALLED_FC"),
    (0.731268, 0.760670, "COMPDATA_INSTALLED_FH"),
    (0.760670, 0.787227, "COMPDATA_INSTALLED_FC"),
    (0.787227, 0.821372, "NEXTDUE_FH"),
    (0.821372, 0.848561, "NEXTDUE_FC"),
    (0.848561, 0.895036, "NEXTDUE_DATE"),
    (0.895036, 0.930130, "REMAINING_FH"),
    (0.930130, 0.966488, "REMAINING_FC"),
    (0.966488, 1.000000, "REMAINING_DAYS"),
]

_ANCHOR_COL = "ATA"
# A single stray leading punctuation glyph (e.g. "§7" for "57", confirmed
# directly on the sample file's own lower-contrast last page) is tolerated
# ahead of the real 2-digit chapter -- the rest of the token must still be
# a clean "NN" or "NN/NN" shape, so this doesn't loosen the anchor enough
# to match arbitrary OCR noise elsewhere.
_ANCHOR_RE = re.compile(r"^\W?\d{2}(/\d{2})?$")

_HEADER_FIELDS = [
    "AIRCRAFT_TYPE", "AIRCRAFT_MSN", "TAIL_NUMBER", "REPORT_DATE",
    "TOTAL_AC_HOURS", "TOTAL_AC_CYCLES", "UTILIZATION_DATE",
]

_NUMERIC_COLS = {
    "LIMIT_FH", "LIMIT_FC", "LIMIT_TIME",
    "ACDATA_INSTALLED_FH", "ACDATA_INSTALLED_FC",
    "COMPDATA_INSTALLED_FH", "COMPDATA_INSTALLED_FC",
    "NEXTDUE_FH", "NEXTDUE_FC",
    "REMAINING_FH", "REMAINING_FC", "REMAINING_DAYS",
}
# Date columns can also legitimately read "n/a" (see _DATE_RE's own
# docstring note) -- normalized through the same _NA_RE glyph-substitution
# check the numeric columns use, in `_clean_field()` below.
_DATE_COLS = {
    "DATE_OF_MANUFACTURE", "LAST_INSPECTION_DATE", "AIRCRAFT_INSTALL_DATE",
    "NEXTDUE_DATE",
}
_CODE_COLS = {"PG_NO", "ATA", "MP_TASK", "CMM", "PART_NUMBER", "FIN", "SERIAL_NUMBER"}
_CODE_STRIP_CHARS = " _\"'`‘’“”.,;:()[]{}|~=—-"
# A ruled-border sliver at a column's own left/right edge occasionally OCRs
# as a lone punctuation "word" ("|", "_", "=", "—") floating at the same Y
# as a real text row -- dropped before joining a cell's tokens, since no
# genuine value in this file is pure punctuation.
_PURE_PUNCT_RE = re.compile(r"^[|_=~—\-:;.,]+$")
# Tesseract very reliably misreads this template's own italic "/" in "n/a"
# as an "l", "1" or "i" (confirmed directly across the sample file: these
# are the single most common non-"n/a" readings of this cell by a wide
# margin) -- a deterministic glyph substitution, not a guessed split, so
# all shapes normalize to the same "n/a" marker.
_NA_RE = re.compile(r"^n\s*[/l1i]?\s*a\.?$", re.IGNORECASE)
# Tesseract occasionally misreads a bold "Y" in a PART_NUMBER/SERIAL_NUMBER
# cell as the yen sign (confirmed directly on the sample file, e.g. a
# "IY14287" serial reading "1¥14287") -- a deterministic glyph
# substitution, not a guessed split, so it's normalized before the shared
# pattern check rather than left to flag every such row.
_YEN_RE = re.compile("[¥]")

# Same-line word-bucketing tolerance -- see
# hard_time_components_status_mpd_or_requirement_scanned.py's own
# `_LINE_BUCKET_PX` docstring note for why bucketing (not a bare sort by
# "top") is needed to keep a wrapped multi-word cell's own word order
# intact.
_LINE_BUCKET_PX = 10


def _col_bounds(table_x0: int, table_x1: int, name: str) -> tuple[int, int]:
    width = table_x1 - table_x0
    for lo, hi, col in _COLUMNS:
        if col == name:
            return table_x0 + int(lo * width), table_x0 + int(hi * width)
    raise KeyError(name)


# Ruled grid-line pixels are near-black on every page of the sample file
# (confirmed directly, values in the 0-50 range even on the lower-contrast
# last page -- see module docstring), while this file's own highlighted-
# row fill colours (e.g. a green "Megaphone Batteries" block) render as a
# noticeably lighter grey once converted to 8-bit luminance (~170-180) --
# comfortably above this threshold. A looser threshold (<200) picks up
# those shaded rows as if they were solid border lines, which wrongly
# swallows the real header/data-row boundary line immediately above one
# into one giant merged "group" spanning the whole shaded block (confirmed
# directly on the sample file's 3rd page, whose first real data row is
# immediately followed by 3 highlighted rows within the same top-of-page
# search window used below).
_BORDER_DARK_THRESHOLD = 120
# Tried loosest-last -- see `_find_header_and_data_y()`'s own docstring
# note for why a single fixed darkness fraction doesn't fit both page
# generations in the sample file.
_DARK_ROW_THRESHOLDS = [0.5, 0.35, 0.2, 0.1]


def _find_header_and_data_y(img) -> tuple[int, int]:
    """Locate this page's own header-metadata-box bottom Y (top of the
    ruled table) and the ruled table's own 3-row header block bottom Y (top
    of the first real data row). Not hardcoded -- a few pixels of
    page-to-page render skew are enough to misalign a fixed constant
    against this file's own fairly tight row pitch, same reasoning this
    package's other raster-grid HT variants use (e.g.
    `hard_time_components_status_mpd_or_requirement_scanned.py`); the
    sample file's own last page additionally renders at a visibly lower
    contrast than the other 5 (see module docstring), needing a looser
    darkness fraction to pick up its own thinner-looking border lines --
    `_DARK_ROW_THRESHOLDS` is tried loosest-last rather than hardcoding a
    single value that fits only one page generation or the other."""
    arr = np.array(img.convert("L"))
    h, w = arr.shape
    dark = arr < _BORDER_DARK_THRESHOLD
    frac = dark.sum(axis=1) / w
    groups: list[list[int]] = []
    for thresh in _DARK_ROW_THRESHOLDS:
        ys = [y for y in range(0, int(h * 0.3)) if frac[y] > thresh]
        groups = []
        for y in ys:
            if groups and y - groups[-1][-1] <= 3:
                groups[-1].append(y)
            else:
                groups.append([y])
        if len(groups) >= 3:
            break
    if not groups:
        return int(h * 0.12), int(h * 0.185)
    header_top = groups[0][0]
    # Three groups expected above the first data row on this file's own
    # layout: the table's own top border, the divider between the group
    # header row and the leaf column-label row, and the leaf row's own
    # bottom border (confirmed directly on the sample file's page 1 and
    # cross-checked on further pages, including the differently-scanned
    # last one).
    data_start = groups[2][-1] + 2 if len(groups) > 2 else groups[-1][-1] + 2
    return header_top, data_start


def _find_table_x_span(img, header_top: int, data_start: int) -> tuple[int, int]:
    """Locate this page's own ruled table left/right edge X-positions,
    structurally, from the header block's own Y-band -- see `_COLUMNS`'
    own docstring note for why this module keys column boundaries off the
    table's own detected width rather than a fixed page-width fraction."""
    arr = np.array(img.convert("L"))
    w = arr.shape[1]
    band = arr[header_top:max(data_start, header_top + 1), :] < 200
    if band.shape[0] == 0:
        return int(w * 0.02), int(w * 0.98)
    colfrac = band.sum(axis=0) / band.shape[0]
    xs = np.where(colfrac > 0.15)[0]
    if len(xs) == 0:
        return int(w * 0.02), int(w * 0.98)
    return int(xs.min()), int(xs.max())


async def _ocr_column(img, name: str, y0: int, y1: int, table_x0: int, table_x1: int,
                       scale: int = 2) -> list[tuple[float, float, str]]:
    x0, x1 = _col_bounds(table_x0, table_x1, name)
    # A few px inset keeps the column's own ruled border lines out of the
    # crop -- otherwise they occasionally OCR as a stray punctuation token
    # right at the cell edge (see _PURE_PUNCT_RE below, kept as a second,
    # belt-and-braces filter).
    x0, x1 = x0 + 3, max(x0 + 4, x1 - 3)
    crop = img.crop((x0, y0, x1, y1)).convert("L")
    # The sample file's own last page is a visibly lower-contrast scan
    # generation than the other 5 (see module docstring) -- a plain
    # autocontrast stretch (clipping the extreme 1% of each tail) recovers
    # much cleaner glyph edges there, confirmed directly (a "57" ATA cell
    # that misread as "§7" reads correctly after this stretch), and is a
    # no-op in practice on the other, already highly-contrasted pages, so
    # it is applied unconditionally rather than gated on which page this
    # is.
    crop = ImageOps.autocontrast(crop, cutoff=1)
    if scale != 1:
        crop = crop.resize((crop.width * scale, crop.height * scale), Image.LANCZOS)
    # psm=6 ("assume a uniform block of text") reads only the crop's own
    # first line correctly and garbles every line below it on this file's
    # own tall, narrow single-column strips with MANY short rows
    # (confirmed directly -- a column crop spanning a standard page's full
    # ~30-row body comes back as mostly noise past line 1 at psm=6, while
    # psm=4, "assume a single column of text of variable sizes", reads the
    # same crop cleanly end to end). The sample file's own last page is the
    # opposite case, though -- confirmed directly: its own much shorter,
    # ~9-row column crop reads cleanly at psm=6/11 but comes back almost
    # entirely blank at psm=4 (Tesseract's column-segmentation step
    # apparently needs more lines to lock onto before psm=4's layout
    # analysis kicks in reliably). Rather than pick one psm per file (either
    # choice drops a whole page somewhere in the sample), psm=4 is tried
    # first and psm=6 is used as a fallback specifically when psm=4 comes
    # back suspiciously empty for a crop tall enough to plausibly hold
    # several rows.
    words = await ocr_words(crop, psm=4, min_conf=-1)
    if len(words) < 3 and (y1 - y0) > 150:
        words = await ocr_words(crop, psm=6, min_conf=-1)
    out = []
    for wd in words:
        text = str(wd.get("text", "")).strip()
        if not text or _PURE_PUNCT_RE.match(text):
            continue
        top = y0 + wd["top"] / scale
        left = wd.get("left", 0) / scale
        out.append((top, left, text))
    return out


def _clean_field(name: str, tokens: list[tuple[float, float, str]]) -> str:
    lines: list[list[tuple[float, float, str]]] = []
    for top, left, text in sorted(tokens, key=lambda item: item[0]):
        if lines and abs(top - lines[-1][0][0]) <= _LINE_BUCKET_PX:
            lines[-1].append((top, left, text))
        else:
            lines.append([(top, left, text)])
    ordered_lines = [
        [text for _, _, text in sorted(line, key=lambda item: item[1])]
        for line in lines
    ]
    text = " ".join(" ".join(line) for line in ordered_lines)

    if name == "ATA":
        # A single stray leading punctuation glyph is possible on the
        # anchor token itself (see _ANCHOR_RE's own docstring note) -- keep
        # only the real "NN"/"NN/NN" chapter shape, not whatever noise
        # character preceded it.
        m = re.search(r"\d{2}(/\d{2})?", text)
        return m.group(0) if m else text.strip(_CODE_STRIP_CHARS)

    if name in _NUMERIC_COLS or name in _DATE_COLS:
        if _NA_RE.match(text.replace(" ", "")):
            return "n/a"
        # Thousands-grouped values use a plain space separator (e.g.
        # "48 619") -- the shared clean_cell pipeline's own `no_spaces`
        # rule (set in this module's own RULES) collapses that back into
        # one digit run downstream, so the space is deliberately kept here
        # rather than stripped locally (see module docstring).
        return text.strip(_CODE_STRIP_CHARS)

    if name in _CODE_COLS:
        text = _YEN_RE.sub("Y", text)
        text = text.strip(_CODE_STRIP_CHARS)
    return text


_TYPE_MSN_RE = re.compile(r"([A-Za-z][\w\- ]*\d[\w\-]*),?\s*MSN\D{0,3}0*(\d+)", re.IGNORECASE)
_TAIL_RE = re.compile(r"\b([A-Z]{1,2}-[A-Z0-9]{3,6}),?\s*MSN\D{0,3}0*(\d+)", re.IGNORECASE)
_REPORT_DATE_RE = re.compile(r"Status Report at:?\s*([\d./-]+)", re.IGNORECASE)
_TOTAL_HOURS_RE = re.compile(r"Total\s*A/?C\s*Hours:?\s*([\d,. ]+?)(?=\s|$)", re.IGNORECASE)
_TOTAL_CYCLES_RE = re.compile(r"Total\s*A/?C\s*Cycles:?\s*([\d,. ]+?)(?=\s|$)", re.IGNORECASE)
_UTIL_DATE_RE = re.compile(r"Utilization date:?\s*([\d./-]+)", re.IGNORECASE)

_TITLE_RE = re.compile(
    r"HARD\s+TIME\s+COMPONENTS\s+AND\s+LIFE\s+LIMITED\s+PARTS\s+STATUS\s+REPORT",
    re.IGNORECASE,
)
_MP_TASK_RE = re.compile(r"MP\s+TASK", re.IGNORECASE)
_CMM_RE = re.compile(r"\bCMM\b", re.IGNORECASE)


async def _parse_header(img) -> dict:
    meta = {k: "" for k in _HEADER_FIELDS}
    w, h = img.size
    header_top, _ = _find_header_and_data_y(img)
    crop = img.crop((0, 0, w, max(header_top, 1)))
    crop = crop.resize((crop.width * 2, crop.height * 2), Image.LANCZOS)
    text = await ocr_text(crop, psm=6)

    m = _TYPE_MSN_RE.search(text)
    if m:
        meta["AIRCRAFT_TYPE"] = m.group(1).strip(_CODE_STRIP_CHARS)
        meta["AIRCRAFT_MSN"] = m.group(2).strip()
    m = _TAIL_RE.search(text)
    if m:
        meta["TAIL_NUMBER"] = m.group(1).strip()
        if not meta["AIRCRAFT_MSN"]:
            meta["AIRCRAFT_MSN"] = m.group(2).strip()
    m = _REPORT_DATE_RE.search(text)
    if m:
        meta["REPORT_DATE"] = m.group(1).strip(_CODE_STRIP_CHARS)
    m = _TOTAL_HOURS_RE.search(text)
    if m:
        meta["TOTAL_AC_HOURS"] = re.sub(r"\s+", "", m.group(1))
    m = _TOTAL_CYCLES_RE.search(text)
    if m:
        meta["TOTAL_AC_CYCLES"] = re.sub(r"\s+", "", m.group(1))
    m = _UTIL_DATE_RE.search(text)
    if m:
        meta["UTILIZATION_DATE"] = m.group(1).strip(_CODE_STRIP_CHARS)
    return meta


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback (see
    sheet_types/ht.py) -- this variant's SIGNATURES is deliberately empty
    (see module docstring).

    Requires BOTH this file's own full report title ("Hard Time Components
    and Life Limited Parts Status Report") AND the "MP Task"/"CMM" column-
    header pair -- checked directly with a plain grep for "MP TASK" and for
    the title's own "LIFE LIMITED PARTS STATUS" fragment across every
    SIGNATURES/ocr_detect anchor in sheet_types/ht_variants and
    sheet_types/llp_variants; the closest matches found
    (`apu_llp_inventory.py`, `kalstar_engine_llp_status.py`,
    `pw4056_pw4060_dual_rating_llp_status.py`,
    `thai_landing_gear_llp_status.py`) all key on the bare "LIFE LIMITED
    PARTS STATUS" phrase without the "HARD TIME COMPONENTS AND ... REPORT"
    wrapper this file always has, and none of them pair it with "MP TASK"."""
    try:
        img = await render_page(pdf_path, 0, dpi=300)
        w, h = img.size
        title_crop = img.crop((0, 0, w, int(h * 0.14)))
        title_text = (await ocr_text(title_crop, psm=6)).upper()
        if not _TITLE_RE.search(title_text):
            return False
        # The column-header row itself (bold text on an orange fill) does
        # not OCR reliably inside a wide whole-page-width crop at the
        # title's own scale -- confirmed directly, a combined title+header
        # crop garbles this row into noise on the sample file even though
        # the title line above it reads cleanly. Narrowing to just the
        # header row's own Y-band (located structurally, not hardcoded --
        # see `_find_header_and_data_y()`) and upscaling 2x fixes this.
        header_top, data_start = _find_header_and_data_y(img)
        header_crop = img.crop((0, header_top, w, data_start))
        header_crop = header_crop.resize(
            (header_crop.width * 2, header_crop.height * 2), Image.LANCZOS)
        header_text = (await ocr_text(header_crop, psm=6)).upper()
        return bool(_MP_TASK_RE.search(header_text) and _CMM_RE.search(header_text))
    except Exception:
        return False


async def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    header_meta = {k: "" for k in _HEADER_FIELDS}
    n_pages = await page_count(pdf_path)

    for page_index in range(n_pages):
        img = await render_page(pdf_path, page_index, dpi=300)
        h = img.height

        if not all(header_meta.values()):
            page_meta = await _parse_header(img)
            for k, v in page_meta.items():
                if v and not header_meta[k]:
                    header_meta[k] = v

        header_top, data_start = _find_header_and_data_y(img)
        table_x0, table_x1 = _find_table_x_span(img, header_top, data_start)

        col_words: dict[str, list[tuple[float, float, str]]] = {}
        for _, _, name in _COLUMNS:
            col_words[name] = await _ocr_column(img, name, data_start, h, table_x0, table_x1)

        anchor_words = sorted(col_words[_ANCHOR_COL], key=lambda item: item[0])
        clustered: list[float] = []
        for top, _left, text in anchor_words:
            if not _ANCHOR_RE.match(text):
                continue
            if clustered and top - clustered[-1] <= 6:
                continue
            clustered.append(top)

        # Assign every other column's words to the nearest row by midpoint
        # boundary, not a fixed +/- tolerance window -- this file's rows
        # vary a lot in height (a plain single-line row next to a 3-line
        # wrapped ACTION cell, e.g. "O/H" + two NOTE* lines), so a fixed
        # window can't fit both without either cutting off a tall row's
        # wrapped text or bleeding a short row's text into its neighbour.
        # The LAST row on a page has no next anchor to cap it against; a
        # naive "extend to the page bottom" bound would sweep in whatever
        # sits below the ruled table -- on this file's own last page, a
        # signature block that must never end up in any output field (see
        # module docstring's sensitivity note). The last row's own bottom
        # bound instead mirrors the gap to ITS OWN previous row, falling
        # back to a small fixed pad on a page with only one detected row.
        bounds: list[tuple[float, float]] = []
        for i, atop in enumerate(clustered):
            lo = data_start if i == 0 else (clustered[i - 1] + atop) / 2
            if i < len(clustered) - 1:
                hi = (atop + clustered[i + 1]) / 2
            elif i > 0:
                hi = min(h, atop + (atop - clustered[i - 1]) / 2)
            else:
                hi = min(h, atop + h * 0.02)
            bounds.append((lo, hi))

        for (lo, hi), atop in zip(bounds, clustered):
            row: dict[str, str] = {}
            for _, _, name in _COLUMNS:
                toks = [(top, left, text) for top, left, text in col_words[name]
                        if lo <= top < hi]
                row[name] = _clean_field(name, toks)
            row["_page"] = page_index + 1
            row.update(header_meta)
            records.append(row)

    return records
