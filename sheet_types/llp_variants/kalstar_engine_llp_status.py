"""Kalstar Aviation per-ENGINE LLP status report -- "KALSTAR AVIATION /
ENGINE LIFE LIMITED PARTS STATUS", one page per engine serial number,
listing that engine's own life-limited parts (impellers, discs, HPT
covers, blades, ...). A sibling format to kalstar_aviation_llp_status.py
(same producer/brand, same "Signed by ... Quality Assurance Manager"
footer) but a different report entirely: that one is per-AIRFRAME/leg
(anchored on "LOWER LIMITER" + "AIRCRAFT MSN" together) and uses a
row-numbered-but-unruled layout; this one is per-ENGINE, and its table
*is* a fully ruled grid (solid box borders around every cell, confirmed
by direct pixel inspection -- see `_table_grid()` below).

No text layer on any of the 3 known source files (0 chars, 1 page each,
same producer/QA-signer as the sibling format) -- a clean computer-
rendered raster, not a photographed form.

Header block (values below are illustrative, not from any real file)::

    KALSTAR AVIATION          ENGINE LIFE LIMITED PARTS STATUS
    At Installation | Current (Engine | Aircraft) | Last Shop Visit
    Date: <d>          Engine Type: <model>   Aircraft Type: <type>   Date: <d>
    Total Aircraft Time: <h>   ESN: <esn>       Aircraft Reg: <reg>   Total Engine Time: <h>
    Total Aircraft Cycle: <c>  Date: <d>        MSN: <msn>            Total Engine Cycle: <c>
    Total Engine Time: <h>     Total Engine Time: <h>  Pos: <lh/rh>   Status/Work: <status>
    Total Engine Cycle: <c>    Total Engine Cycle: <c> Date: <d>      Accomplished by: <shop>
    TSLSV: <h>                 TSLSV: <h>       Total Aircraft Time: <h>
    CSLSV: <c>                 CSLSV: <c>       Total Aircraft Cycle: <c>
                                Lower Limiter: <c>

Four column-groups share several IDENTICALLY-worded labels ("Date",
"Total Aircraft/Engine Time/Cycle", "TSLSV", "CSLSV") -- one occurrence
per group (At Installation / Current-Engine / Current-Aircraft / Last
Shop Visit). A naive single flattened-text regex search would only ever
find the FIRST occurrence and silently misattribute every later one.
Worse, this document's own OCR'd reading order doesn't even group by
column -- `ocr_text()`'s row-major scan interleaves column-groups within
one output line (confirmed directly: one recovered line reads
illustratively as "Total Engine Time : <install value> Engine Type :
<model> Aircraft Type : <type> Total Engine Time : <LSV value>" -- three
different "Total Engine Time" instances from three different groups,
none in their logical install/current/LSV order), so even *counting*
occurrences in text order doesn't recover which group a value belongs to.

Fix: use `ocr_words()` (word-level boxes) instead of `ocr_text()` for the
header, and bucket every word into one of the 4 column-groups purely by
its own x-position -- confirmed stable (with margin) across all 3 known
files: column boundaries at x-fractions 0.33 / 0.52 / 0.67 of the full
page width cleanly separate every label in every sample inspected, even
though the table's own column x-positions (see `_table_grid()`) are NOT
stable across files (confirmed directly -- the table's leftmost ruled
line sits at a noticeably different x per file, so those fractions
would be the wrong tool for the *table*; they only work for the header
because the header block's own margins are consistent). Words are then
re-joined into 4 per-column text blocks (top-to-bottom, left-to-right
within each), and each block is searched independently -- so a repeated
label like "TSLSV" only ever appears once per block and there is no
attribution ambiguity left to resolve.

Only labels with an unambiguous, safely-patterned value are extracted
this way (see CANONICAL_COLUMNS below); the "Date" sub-fields for the
Current-Engine and Last-Shop-Visit groups are skipped outright -- on
every known sample they're either blank or a bare "-", and a loose regex
risks swallowing the next label's text as a fake value with nothing to
anchor against, so it's not worth the risk for a low-value field that's
usually empty anyway.

The data grid itself IS a genuine ruled table (unlike the sibling
per-airframe module's docstring claim that ITS table has no reliable
full-width horizontal darkness) -- but the horizontal ruling here turned
out to be invisible to a plain "average darkness across the whole row"
scan (confirmed by direct pixel sampling: max row darkness fraction
across a wide x-band never exceeds ~0.6, even squarely on a visibly
solid black border in the rendered image). The reason, confirmed
directly: a page-wide rotational skew spreads each nominally-horizontal
ruled line across a many-pixel-tall smear when averaged over a WIDE
x-span, diluting any single row's darkness well below a naive threshold
-- the same skew phenomenon the sibling module's docstring describes,
just severe enough here to defeat a full-width scan rather than only
the far-right column. Narrowing the scan to a single column's interior
width (so the local y-drift across that narrow span is negligible)
recovers clean, sharp row-line detection -- confirmed directly, and the
same reasoning the sibling module already applies for ITS OWN row
detection, reused here rather than reinvented.

Column x-positions, unlike the header's, are NOT stable across files
(confirmed directly -- the same "NO" column sits at a different absolute
x per file), so they can't be hardcoded like the header fractions above.
Instead they're detected fresh per file: scanning column-line darkness
over a wide *vertical* band spanning the whole table body (immune to the
row-skew problem since it's summing down each x column, not across a
row) reliably recovers the true 12 vertical grid lines (11 columns) in
every known file. Those freshly-detected column positions then supply
the two narrow interior x-bands the row-detection step needs (first and
second-to-last column), rather than assuming any fixed fraction.

Row heights themselves also vary between files (confirmed directly --
~74px in one file, ~68px in another, ~61px in the third, despite near-
identical page pixel dimensions and DPI) for reasons not otherwise
investigated, so row-line grouping can't assume one fixed row-height
window either (unlike the sibling module, which can, on its own single-
template corpus). `_select_row_chain()` instead finds each file's own
modal line-to-line spacing and keeps the longest run of edges close to
it, discarding both the tight header-internal divider (the "REMAINING
CYCLES" split-header sub-line) and the far-below signature-block noise
without needing a hardcoded absolute row-height range.

Two data-row peculiarities confirmed directly, left as-is rather than
guessed at: SERIAL_NUMBER is not always a real serial -- one recurring
row (an item fitted in multiple physical pieces, e.g. a full blade set)
prints the literal word "VARIOUS" there instead, so SERIAL_NUMBER's
validation pattern allows that specific word rather than rejecting it as
malformed; and the REMARK/status column's vocabulary is not fully known
-- only two distinct values ("ORIGINAL" and one shop-visit outcome word)
were seen across the 3 known files, not enough to safely hardcode a
closed enum, so STATUS is validated as an uppercase word rather than a
fixed pattern list.

Remaining known imperfections, left uncorrected deliberately rather than
patched with a fragile heuristic: SERIAL_NUMBER's O/0 (and similar
letter/digit) ambiguity is not resolved -- the same unresolvable
confusion the sibling module documents for its own serials, and for the
same reason (no per-manufacturer serial reference list to check against).
And a small number of individual cells (an isolated digit or the
low-order metadata ITEM_NO field) still misread occasionally even after
the grid-line/tight-crop fix described above -- confirmed across the 3
known files to be rare (a cell or two per file, never a whole column),
not systematic, and not worth chasing further with format-specific
one-off corrections that risk being wrong in the opposite direction on
a file not yet seen.
"""
from __future__ import annotations
import re
from collections import Counter

import numpy as np

from sheet_types.llp_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, ocr_words

NAME = "Kalstar Aviation Engine LLP Status"
# Text-layer signature list deliberately empty -- every known source file
# has a 0-char text layer (see module docstring); router.py's blank-text
# fallback reaches this module purely through ocr_detect() below.
SIGNATURES: list[str] = []

CANONICAL_COLUMNS = [
    "ITEM_NO",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "CYCLE_LIMIT",
    "CSN_FULL",
    "CSN",
    "FCF",
    "REMAINING_CYCLES_EXCL_FCF",
    "REMAINING_CYCLES_INCL_FCF",
    "STATUS",
    # File-level metadata -- same on every row of a given file. See module
    # docstring for why these (and not the skipped "Date" sub-fields) were
    # judged worth extracting.
    "ESN",
    "MSN",
    "AIRCRAFT_REG",
    "AIRCRAFT_TYPE",
    "ENGINE_TYPE",
    "POSITION",
    "REPORT_DATE",
    "AC_TIME_AT_INSTALL",
    "AC_CYCLE_AT_INSTALL",
    "ENGINE_TIME_AT_INSTALL",
    "ENGINE_CYCLE_AT_INSTALL",
    "TSLSV_AT_INSTALL",
    "CSLSV_AT_INSTALL",
    "AC_TIME_CURRENT",
    "AC_CYCLE_CURRENT",
    "ENGINE_TIME_CURRENT",
    "ENGINE_CYCLE_CURRENT",
    "TSLSV_CURRENT",
    "CSLSV_CURRENT",
    "LOWER_LIMITER",
    "LSV_DATE",
    "LSV_ENGINE_TIME",
    "LSV_ENGINE_CYCLE",
    "STATUS_WORK",
    "ACCOMPLISHED_BY",
]

_INT_RULE = {"pattern": r"^[\d,]*$", "allow_empty": True,
             "int_range": (0, 90000), "int_range_review": (0, 55000)}
_HOUR_RULE = {"pattern": r"^[\d,]*\.?\d*$", "allow_empty": True}
_DATE_RULE = {"pattern": r"^(\d{1,2}-[A-Za-z]{3,9}-\d{2,4}|-)?$", "allow_empty": True}
_OVERRIDES = {
    "ITEM_NO":                    {"pattern": r"^\d{1,3}$", "allow_empty": True},
    "SERIAL_NUMBER":              {"pattern": r"^([A-Z0-9]+|VARIOUS)$", "uppercase": True},
    "CYCLE_LIMIT":                _INT_RULE,
    "CSN_FULL":                   _INT_RULE,
    "CSN":                        _INT_RULE,
    "FCF":                        {"pattern": r"^\d*\.?\d*$", "allow_empty": True},
    "REMAINING_CYCLES_EXCL_FCF":  _INT_RULE,
    "REMAINING_CYCLES_INCL_FCF":  _INT_RULE,
    "STATUS":                     {"pattern": r"^[A-Z ]*$", "uppercase": True, "allow_empty": True},
    "ESN":                        {"allow_empty": True},
    "MSN":                        {"allow_empty": True},
    "AIRCRAFT_REG":               {"pattern": r"^[A-Z0-9\-]*$", "uppercase": True, "allow_empty": True},
    "AIRCRAFT_TYPE":              {"allow_empty": True},
    "ENGINE_TYPE":                {"allow_empty": True},
    "POSITION":                   {"pattern": r"^(LH|RH)?$", "uppercase": True, "allow_empty": True},
    "REPORT_DATE":                _DATE_RULE,
    "AC_TIME_AT_INSTALL":         _HOUR_RULE,
    "AC_CYCLE_AT_INSTALL":        _INT_RULE,
    "ENGINE_TIME_AT_INSTALL":     _HOUR_RULE,
    "ENGINE_CYCLE_AT_INSTALL":    _INT_RULE,
    "TSLSV_AT_INSTALL":           _HOUR_RULE,
    "CSLSV_AT_INSTALL":           _INT_RULE,
    "AC_TIME_CURRENT":            _HOUR_RULE,
    "AC_CYCLE_CURRENT":           _INT_RULE,
    "ENGINE_TIME_CURRENT":        _HOUR_RULE,
    "ENGINE_CYCLE_CURRENT":       _INT_RULE,
    "TSLSV_CURRENT":              _HOUR_RULE,
    "CSLSV_CURRENT":              _INT_RULE,
    "LOWER_LIMITER":              _INT_RULE,
    "LSV_DATE":                   _DATE_RULE,
    "LSV_ENGINE_TIME":            _HOUR_RULE,
    "LSV_ENGINE_CYCLE":           _INT_RULE,
    "STATUS_WORK":                {"allow_empty": True},
    "ACCOMPLISHED_BY":            {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_DPI = 300
_DARK_THRESH = 220
_LINE_FRAC = 0.85
_COL_FRAC = 0.5
# Table body search band (fraction of full page height) used only to
# locate the table's own column x-positions -- comfortably wide enough to
# contain the whole 10-row grid on every known file without also reaching
# the signature block below it (see module docstring).
_TABLE_Y_BAND = (0.30, 0.75)
_N_TABLE_COLS = 11  # NO, DESCRIPTION, PN, SN, CYCLE LIMIT, CSN FULL, CSN,
                     # F.C.F, REMAINING EXCL FCF, REMAINING INCL FCF, REMARK

# Header word-bucketing boundaries (x-fraction of page width) -- confirmed
# stable *with margin* across all 3 known files (worst-case gaps: ~0.10 for
# the col0/col1 boundary, ~0.04 for col1/col2, ~0.015 for col2/col3) by
# directly comparing every word's own x-fraction across all 3 files, not
# just guessed from one. See module docstring for why these can be
# hardcoded while the table's own column x-positions cannot. The
# col2/col3 boundary in particular must sit above 0.688 (the rightmost
# col2 value observed) and below 0.703 (the leftmost col3 value observed)
# -- a value below ~0.69 here (0.67 was tried first and confirmed wrong)
# misattributes col2's own Aircraft Type/Reg/MSN/Pos values into col3.
_HDR_COL_FRACS = (0.33, 0.52, 0.695)

_TITLE_TEXT = "ENGINE LIFE LIMITED PARTS STATUS"

_PN_RE = re.compile(r"\d{4,9}(?:-\d{1,3})?")
_NUM_RE = re.compile(r"[\d,]+\.?\d*")
_ALNUM_RE = re.compile(r"[A-Za-z0-9\-]+")


def _line_groups(frac: np.ndarray, thresh: float) -> list[int]:
    idx = np.where(frac > thresh)[0]
    if not len(idx):
        return []
    groups, cur = [], [idx[0]]
    for v in idx[1:]:
        if v - cur[-1] <= 3:
            cur.append(v)
        else:
            groups.append(cur)
            cur = [v]
    groups.append(cur)
    return [int(np.mean(g)) for g in groups]


def _select_row_chain(edges: list[int]) -> list[int]:
    """Longest run of consecutive edges spaced at this file's own modal
    row height -- see module docstring for why the row height itself
    can't be hardcoded across files."""
    if len(edges) < 2:
        return []
    diffs = [edges[i + 1] - edges[i] for i in range(len(edges) - 1)]
    buckets = Counter(round(d / 5) * 5 for d in diffs if 20 <= d <= 150)
    if not buckets:
        return []
    mode = buckets.most_common(1)[0][0]
    tol = max(6, mode * 0.15)
    best_run: list[int] = []
    cur_run = [edges[0]]
    for i, d in enumerate(diffs):
        if abs(d - mode) <= tol:
            cur_run.append(edges[i + 1])
        else:
            if len(cur_run) > len(best_run):
                best_run = cur_run
            cur_run = [edges[i + 1]]
    if len(cur_run) > len(best_run):
        best_run = cur_run
    return best_run


def _y_at(edges, i: int, x: float) -> int:
    lo, hi, x_lo, x_hi = edges
    if x_hi == x_lo:
        return lo[i]
    t = (x - x_lo) / (x_hi - x_lo)
    return int(round(lo[i] + (hi[i] - lo[i]) * t))


def _table_grid(arr: np.ndarray):
    """Returns ((lo, hi, x_lo, x_hi), col_xs) -- lo/hi are the row edge
    y-positions sampled at the table's own left/right interior columns
    (for skew interpolation, mirroring kalstar_aviation_llp_status.py's
    _table_grid()), col_xs are the 12 vertical grid-line x-positions (11
    columns). Returns (None, []) if the grid can't be confirmed."""
    dark = arr < _DARK_THRESH
    h, w = arr.shape
    y0, y1 = int(h * _TABLE_Y_BAND[0]), int(h * _TABLE_Y_BAND[1])
    col_xs = _line_groups(dark[y0:y1, :].mean(axis=0), _COL_FRAC)
    if len(col_xs) != _N_TABLE_COLS + 1:
        return None, []

    lx0, lx1 = col_xs[0] + 3, col_xs[1] - 3
    rx0, rx1 = col_xs[-3] + 3, col_xs[-2] - 3
    lo_all = _line_groups(dark[:, lx0:lx1].mean(axis=1), _LINE_FRAC)
    hi_all = _line_groups(dark[:, rx0:rx1].mean(axis=1), _LINE_FRAC)
    lo = _select_row_chain(lo_all)
    hi = _select_row_chain(hi_all)
    if len(lo) < 2 or len(lo) != len(hi):
        return None, []

    x_lo = (lx0 + lx1) / 2
    x_hi = (rx0 + rx1) / 2
    return (lo, hi, x_lo, x_hi), col_xs


# Strict darkness threshold used only for locating a cell's own glyph
# bounding box (never for grid-line detection, which uses _DARK_THRESH)
# -- see module docstring's note on tight-cropping numeric cells.
_GLYPH_DARK_THRESH = 100
_GLYPH_MARGIN = 8


def _tight_crop(cell_img):
    """Crop a table cell down to its own glyph bounding box (+ margin),
    or return None for a genuinely blank cell.

    Confirmed directly: passing tesseract the full cell box reliably
    fails on this format's narrower numeric columns (CSN FULL / CSN /
    F.C.F / REMAINING CYCLES) -- e.g. a cell containing only a clean,
    correctly-cropped "2" glyph against a wide blank field returns an
    empty string at every page-segmentation mode tried. The same glyph,
    re-cropped tightly around just its own dark pixels (using a strict
    threshold well below the grid-line detection one, since this only
    needs to find solid ink, not faint ruled lines) with a small margin,
    is read correctly by every mode. Wider cells (DESCRIPTION, REMARK)
    aren't affected by this bug in practice but tightening them too is
    harmless -- their own text simply becomes the bounding box.

    This alone wasn't sufficient, though: with only a small (4px) initial
    pad on the raw cell box, a sliver of the column's own LEFT vertical
    grid line routinely survived into the glyph bbox -- confirmed
    directly by dumping the dark-pixel mask, which showed a persistent
    thin dark strip spanning nearly the cell's full height right at the
    left edge. Because that stripe is tall (not an isolated speck), it
    doesn't get filtered out by the bbox itself, and dragging it into the
    crop widened a single "1" glyph enough that tesseract consistently
    misread it as "4" (both standalone and as the leading digit of a
    multi-digit number, e.g. a genuine "14998" read back as "44998" on
    every affected cell). Widening `_cell_text()`'s own initial pad from
    4 to 10px (comfortably larger than the observed grid-line remnant,
    still well inside these columns' ~200-300px width) excludes it before
    the tight-bbox pass ever runs -- confirmed to fix every one of the
    misreads found this way across all 3 known files."""
    arr = np.array(cell_img.convert("L"))
    dark = arr < _GLYPH_DARK_THRESH
    if not dark.any():
        return None
    rows = np.where(dark.any(axis=1))[0]
    cols = np.where(dark.any(axis=0))[0]
    y0 = max(0, int(rows.min()) - _GLYPH_MARGIN)
    y1 = min(arr.shape[0], int(rows.max()) + _GLYPH_MARGIN)
    x0 = max(0, int(cols.min()) - _GLYPH_MARGIN)
    x1 = min(arr.shape[1], int(cols.max()) + _GLYPH_MARGIN)
    return cell_img.crop((x0, y0, x1, y1))


async def _cell_text(img, edges, col_xs, row_i: int, col_j: int, pad: int = 10,
                      psm: int = 7, whitelist: str | None = None) -> str:
    xc = (col_xs[col_j] + col_xs[col_j + 1]) / 2
    y0, y1 = _y_at(edges, row_i, xc), _y_at(edges, row_i + 1, xc)
    x0, x1 = col_xs[col_j], col_xs[col_j + 1]
    cell_img = img.crop((x0 + pad, y0 + pad, x1 - pad, y1 - pad))
    tight = _tight_crop(cell_img)
    if tight is None:
        return ""
    text = await ocr_text(tight, psm=psm, whitelist=whitelist)
    return text.strip()


def _clean_numeric(raw: str) -> str:
    m = _NUM_RE.search(raw)
    return re.sub(r",", "", m.group(0)) if m else ""


def _clean_pn(raw: str) -> str:
    m = _PN_RE.search(raw)
    return m.group(0) if m else ""


def _clean_alnum(raw: str) -> str:
    m = _ALNUM_RE.search(raw.upper())
    return m.group(0) if m else ""


# (regex, canonical-column) pairs applied to each header column-group's
# own re-joined text block -- see module docstring for why per-group
# bucketing (not a single flattened-text search) is required here.
_HDR_FIELDS = (
    (  # col 0: At Installation
        (re.compile(r"Date\s*:?\s*(\d{1,2}-[A-Za-z]{3,9}-\d{2,4})", re.I), "REPORT_DATE"),
        (re.compile(r"Total\s+Aircraft\s+Time\s*:?\s*([\d,]+\.?\d*)", re.I), "AC_TIME_AT_INSTALL"),
        (re.compile(r"Total\s+Aircraft\s+Cycle\s*:?\s*([\d,]+)", re.I), "AC_CYCLE_AT_INSTALL"),
        (re.compile(r"Total\s+Engine\s+Time\s*:?\s*([\d,]+\.?\d*)", re.I), "ENGINE_TIME_AT_INSTALL"),
        (re.compile(r"Total\s+Engine\s+Cycle\s*:?\s*([\d,]+)", re.I), "ENGINE_CYCLE_AT_INSTALL"),
        (re.compile(r"TSLSV\s*:?\s*([\d,]+\.?\d*)", re.I), "TSLSV_AT_INSTALL"),
        (re.compile(r"CSLSV\s*:?\s*([\d,]+)", re.I), "CSLSV_AT_INSTALL"),
    ),
    (  # col 1: Current -- Engine
        (re.compile(r"Engine\s+Type\s*:?\s*(\S+)", re.I), "ENGINE_TYPE"),
        (re.compile(r"\bESN\s*:?\s*(\S+)", re.I), "ESN"),
        (re.compile(r"Total\s+Engine\s+Time\s*:?\s*([\d,]+\.?\d*)", re.I), "ENGINE_TIME_CURRENT"),
        (re.compile(r"Total\s+Engine\s+Cycle\s*:?\s*([\d,]+)", re.I), "ENGINE_CYCLE_CURRENT"),
        (re.compile(r"TSLSV\s*:?\s*([\d,]+\.?\d*)", re.I), "TSLSV_CURRENT"),
        (re.compile(r"CSLSV\s*:?\s*([\d,]+)", re.I), "CSLSV_CURRENT"),
        (re.compile(r"Lower\s+Limiter\s*:?\s*([\d,]+)", re.I), "LOWER_LIMITER"),
    ),
    (  # col 2: Current -- Aircraft
        (re.compile(r"Aircraft\s+Type\s*:?\s*(\S+)", re.I), "AIRCRAFT_TYPE"),
        (re.compile(r"Aircraft\s+Reg\s*:?\s*(\S+)", re.I), "AIRCRAFT_REG"),
        (re.compile(r"\bMSN\s*:?\s*(\S+)", re.I), "MSN"),
        (re.compile(r"\bPos\s*:?\s*(\S+)", re.I), "POSITION"),
        (re.compile(r"Total\s+Aircraft\s+Time\s*:?\s*([\d,]+\.?\d*)", re.I), "AC_TIME_CURRENT"),
        (re.compile(r"Total\s+Aircraft\s+Cycle\s*:?\s*([\d,]+)", re.I), "AC_CYCLE_CURRENT"),
    ),
    (  # col 3: Last Shop Visit
        (re.compile(r"Date\s*:?\s*(\d{1,2}-[A-Za-z]{3,9}-\d{2,4}|-)", re.I), "LSV_DATE"),
        (re.compile(r"Total\s+Engine\s+Time\s*:?\s*([\d,]+\.?\d*)", re.I), "LSV_ENGINE_TIME"),
        (re.compile(r"Total\s+Engine\s+Cycle\s*:?\s*([\d,]+)", re.I), "LSV_ENGINE_CYCLE"),
        (re.compile(r"Status\s*/?\s*Work\s*:?\s*(\S+)", re.I), "STATUS_WORK"),
        (re.compile(r"Accomplished\s+by\s*:?\s*(\S+(?:\s+\S+)?)", re.I), "ACCOMPLISHED_BY"),
    ),
)


def _cluster_lines(words: list[dict], gap: int = 20) -> str:
    """Re-join a column-group's words into text, in genuine top-to-bottom
    reading order. Sorting words by raw `top` alone is NOT safe here --
    confirmed directly: two words on the same printed line routinely
    report `top` several px apart (baseline/cap-height jitter, italics),
    enough to scramble the order of two ADJACENT physical lines (e.g. a
    label's value ends up sorted before its own label). Clustering by a
    generous top-proximity gap first, then sorting left-to-right only
    *within* each resulting cluster, recovers the correct field-by-field
    order -- verified directly against all 3 known files' header text
    after this fix (each field regex below now matches its own true
    value, where the naive sort produced e.g. "ESN : Date" -- a
    downstream field's label swallowed as this field's value)."""
    if not words:
        return ""
    ws = sorted(words, key=lambda d: d["top"])
    clusters: list[list[dict]] = [[ws[0]]]
    for wd in ws[1:]:
        if wd["top"] - clusters[-1][-1]["top"] <= gap:
            clusters[-1].append(wd)
        else:
            clusters.append([wd])
    return " ".join(
        " ".join(d["text"] for d in sorted(c, key=lambda d: d["left"]))
        for c in clusters
    )


async def _parse_header(img) -> dict:
    w = img.width
    crop = img.crop((0, 0, w, int(img.height * 0.40)))
    words = await ocr_words(crop, psm=6)

    buckets: list[list[dict]] = [[], [], [], []]
    b1, b2, b3 = (f * w for f in _HDR_COL_FRACS)
    for wd in words:
        x = wd["left"]
        if x < b1:
            idx = 0
        elif x < b2:
            idx = 1
        elif x < b3:
            idx = 2
        else:
            idx = 3
        buckets[idx].append(wd)

    meta: dict[str, str] = {}
    for idx, group_fields in enumerate(_HDR_FIELDS):
        text = _cluster_lines(buckets[idx])
        for pat, key in group_fields:
            m = pat.search(text)
            if m:
                meta[key] = m.group(1).strip()
    return meta


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 header OCR check for the router's blank-text fallback.
    Anchors on this format's title phrase alone -- checked directly
    against kalstar_aviation_llp_status.py's own ocr_detect() (which
    requires "LOWER LIMITER" + "AIRCRAFT MSN" together) on all 3 known
    files for this format: it returns False on every one, so there is no
    competition between the two modules despite both being Kalstar
    Aviation LLP reports and this format's header ALSO containing a
    "Lower Limiter :" figure (it just never also contains the literal
    phrase "AIRCRAFT MSN" -- this format prints "MSN" and "Aircraft"
    Type/Reg as separate, non-adjacent labels, confirmed by direct OCR
    inspection)."""
    try:
        img = await render_page(pdf_path, 0, dpi=_DPI)
        crop = img.crop((0, 0, img.width, int(img.height * 0.20)))
        text = await ocr_text(crop, psm=6)
        return _TITLE_TEXT in text.upper()
    except Exception:
        return False


async def extract(pdf_path: str) -> list[dict]:
    img = await render_page(pdf_path, 0, dpi=_DPI)
    meta = await _parse_header(img)

    arr = np.array(img.convert("L"))
    edges, col_xs = _table_grid(arr)
    if edges is None:
        return []
    lo = edges[0]

    _DIGITS = "0123456789"
    _DECIMAL = "0123456789."
    records: list[dict] = []
    for i in range(len(lo) - 1):
        pn = _clean_pn(await _cell_text(img, edges, col_xs, i, 2))
        if not pn:
            continue

        rec = {c: "" for c in CANONICAL_COLUMNS}
        rec["ITEM_NO"] = _clean_numeric(await _cell_text(img, edges, col_xs, i, 0, whitelist=_DIGITS))
        rec["DESCRIPTION"] = (await _cell_text(img, edges, col_xs, i, 1)).strip()
        rec["PART_NUMBER"] = pn
        rec["SERIAL_NUMBER"] = _clean_alnum(await _cell_text(img, edges, col_xs, i, 3))
        rec["CYCLE_LIMIT"] = _clean_numeric(await _cell_text(img, edges, col_xs, i, 4, whitelist=_DIGITS))
        rec["CSN_FULL"] = _clean_numeric(await _cell_text(img, edges, col_xs, i, 5, whitelist=_DIGITS))
        rec["CSN"] = _clean_numeric(await _cell_text(img, edges, col_xs, i, 6, whitelist=_DIGITS))
        rec["FCF"] = _clean_numeric(await _cell_text(img, edges, col_xs, i, 7, whitelist=_DECIMAL))
        rec["REMAINING_CYCLES_EXCL_FCF"] = _clean_numeric(
            await _cell_text(img, edges, col_xs, i, 8, whitelist=_DIGITS))
        rec["REMAINING_CYCLES_INCL_FCF"] = _clean_numeric(
            await _cell_text(img, edges, col_xs, i, 9, whitelist=_DIGITS))
        rec["STATUS"] = (await _cell_text(img, edges, col_xs, i, 10)).strip().upper()
        for k, v in meta.items():
            rec[k] = v
        rec["_page"] = 1
        records.append(rec)
    return records
