"""Born-scanned "TIME CONTROLLED COMPONENTS" report -- full-page-raster
PDF, no usable text layer at all (confirmed directly: `page.get_text()`
returns empty on every page of the sample file). Rendering to an image
shows a clean, sharp, ordinary machine-printed report (not handwritten,
not a noisy photocopy) with a fully ruled ("boxed") grid baked into the
raster -- every cell boundary is a real drawn line, not just whitespace --
so a per-column-strip OCR pass anchored on the grid's own horizontal
divider lines is reliable here.

Header block (page 1 only; repeats on no other page of the sample --
confirmed directly, pages 2-5 start straight into table data with no
header at all, sometimes mid-way through a row carried over from the
previous page's bottom)::

    <wordmark graphic>   MODEL :     <type>       AS OF DATE: <date>    PREPARED BY :
                          REG. NO. :  <tail>       AC HOURS :  <hrs>    EXAMINED BY :
                          SERIAL NO.: <msn>        AC CYCLES : <cyc>    DATE :

                             TIME CONTROLLED COMPONENTS

    REF NO. | DESCRIPTION | Part Number | Serial Number | Inst. Date | POSITION |
    Time Limit | Last Work Date/MFG Time on Inst | Used Time | Remaining to Shop
    Visit | Due Date | TASK | REMARKS

PREPARED BY / EXAMINED BY / DATE are blank sign-off fields on the sample
file (never filled in) and are deliberately NOT captured into any output
field -- this project's convention of never extracting a signature block
(see e.g. `hard_time_components_status_mpd_or_requirement_scanned.py`'s
own sensitivity note), applied here even though the sample happens to be
blank, since a filled-in copy of this same template could carry a real
name there.

13-column ruled grid, X-boundaries confirmed directly via a numpy
column-darkness scan of the ruled grid's own vertical divider lines on
the sample file's page 1 (matches the printed header labels exactly, see
`_COLUMNS` below). DESCRIPTION cells are bilingual (an English label over
a Chinese translation, e.g. "SKIN AIR OUTL VLV" / "蒙皮空气出口活门",
sharing a single grid row) -- both lines are OCR'd and joined into one
field verbatim; Tesseract's non-CJK-trained pass on the Chinese line
typically comes back as noise, which is accepted rather than special-cased
(no attempt to run a second, CJK-trained OCR pass), since the English
line carries the same identifying information and downstream validation
never pattern-checks DESCRIPTION.

Row grain: one physical ruled row per record, which is NOT the same as
one row per component -- a single component (REF NO/DESCRIPTION/PART
NUMBER/SERIAL NUMBER/Inst. Date/POSITION) is very often tracked against
two or three different limit bases (e.g. an escape-slide assembly's own
"36 MOS" overhaul row directly above its "180 MOS" 15-year-check row) and
the ruled grid only draws a divider between those TIME LIMIT-through-
REMARKS sub-rows -- the identity columns (REF NO through POSITION) are a
single taller merged cell spanning the whole component's own block, with
no internal divider and the identity text printed only once, on the
block's own first physical row. Confirmed directly on the sample file
(e.g. "MRS 25-62-103 / ESCAPE SLIDE ASSY-FWD / D30664-709 / M9747 /
2016/12/10 / 7500MM" prints once, above both its own "36 MOS .../OVERHAUL"
and "180 MOS .../1 YR Above 15 Yrs" sub-rows). Each of the 6 identity
columns is therefore forward-filled independently from the most recent
row on which it was non-blank -- this also transparently handles a
component's block being split across a page boundary (confirmed directly:
the sample's own "MRS 25-62-107 / OFF-WING ESCAPE SLIDE" block's "36 MOS"
sub-row is the last row on page 1, its "180 MOS" sub-row is the first row
on page 2, and the page-2 row carries no identity text of its own at all).

Row anchor: rather than anchor on any one column's OCR'd text (this file's
own component blocks are irregular enough -- see below -- that no single
column is reliably non-blank on every real row), row boundaries are read
directly off the ruled grid's own horizontal divider lines via a numpy
row-darkness scan restricted to the TIME LIMIT-through-DUE DATE column
band (x-fraction ~0.538-0.831) -- that band is fully ruled (a real drawn
line) on every physical row of the sample, including rows whose TIME
LIMIT/TASK cells are entirely blank (e.g. a "YAW DAMPER ACTUATOR" row
whose only populated cells are TASK="INSPECTOR" and REMARKS). This is a
grid-geometry anchor, not a text anchor, so it is unaffected by which
column(s) happen to be blank on a given row.

Known irregular block, deliberately NOT force-split: the sample file's
"TRIM HORIZONTAL STAB. ACTUATOR" component (REF NO "27-44-501") spans a
6-sub-row block straddling the page 2/3 boundary, whose own POSITION/TIME
LIMIT columns carry nested MPD sub-task reference codes and repeat/interval
notes instead of this template's usual plain interval value, with a long
free-text Chinese REMARKS paragraph on most of its own sub-rows. The
grid-line row anchor still finds this block's own true ruled row
boundaries correctly (it does not depend on TIME LIMIT/TASK content
shape), so each of its sub-rows is still extracted as its own record, with
whatever text actually falls inside each column's own X-band captured
verbatim -- no attempt is made to semantically reinterpret this block's
own irregular column usage, per this project's "never force a wrong
split" convention for irregular merges.

Sensitivity note: page 1's header carries a real operator name/logo and
this sample's own real tail number, MSN and dates -- none of that is
written into this module's code/comments (only the generic column-header
and section-title phrases the template itself prints, which are not
document-specific). The header's AIRCRAFT_REG/AIRCRAFT_MSN/etc. fields
ARE extracted into row data at runtime (same as this project's other
per-file header-metadata capture, e.g. the MPD-or-Requirement sibling
above) -- that is ordinary functional extraction, not a hardcoded
document-specific value in source code. No signer name was present on the
sample file's own PREPARED BY/EXAMINED BY fields to check; those fields
are not captured into any output column regardless (see above).
"""
from __future__ import annotations
import re

import numpy as np
from PIL import Image

from sheet_types.ht_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_words, ocr_text, page_count

NAME = "HT Ruled Grid, Time Limit / Remaining to Shop Visit Columns (Scanned)"

# Deliberately empty: this file's own plain-text layer is blank on every
# page (see module docstring), so a plain-text SIGNATURES phrase would
# never be checked against real page content anyway. Detected instead via
# `ocr_detect()` below, through the router's blank-text-layer OCR-fallback
# path (`sheet_types/ht.py`'s own `detect_variant()`).
SIGNATURES: list[str] = []

CANONICAL_COLUMNS = [
    "REF_NO",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "INST_DATE",
    "POSITION",
    "TIME_LIMIT",
    "LAST_WORK_DATE",
    "USED_TIME",
    "REMAINING_TO_SHOP_VISIT",
    "DUE_DATE",
    "TASK",
    "REMARKS",
    # Header metadata -- same on every page of a given file, stamped on
    # every row (see module docstring for the header block layout).
    "AIRCRAFT_MODEL",
    "AIRCRAFT_REG",
    "AIRCRAFT_MSN",
    "AS_OF_DATE",
    "ACFT_HOURS",
    "ACFT_CYCLES",
]

# Every column allow_empty -- a single OCR misread or a genuinely blank
# source cell (e.g. a component whose TIME LIMIT basis doesn't apply,
# see module docstring) shouldn't flag every row, same convention this
# package's other per-column-strip OCR variants use.
_OVERRIDES = {
    "REF_NO": {"allow_empty": True},
    "DESCRIPTION": {"allow_empty": True, "uppercase": True},
    "PART_NUMBER": {"allow_empty": True},
    "SERIAL_NUMBER": {"allow_empty": True},
    "INST_DATE": {"allow_empty": True},
    "POSITION": {"allow_empty": True, "uppercase": True},
    "TIME_LIMIT": {"allow_empty": True},
    "LAST_WORK_DATE": {"allow_empty": True},
    "USED_TIME": {"allow_empty": True},
    "REMAINING_TO_SHOP_VISIT": {"allow_empty": True},
    "DUE_DATE": {"allow_empty": True},
    "TASK": {"allow_empty": True},
    "REMARKS": {"allow_empty": True},
    "AIRCRAFT_MODEL": {"allow_empty": True},
    "AIRCRAFT_REG": {"allow_empty": True},
    "AIRCRAFT_MSN": {"allow_empty": True},
    "AS_OF_DATE": {"allow_empty": True},
    "ACFT_HOURS": {"allow_empty": True},
    "ACFT_CYCLES": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Column X-boundaries, as a fraction of the rendered page's own width --
# derived directly from a numpy column-darkness scan of the ruled grid's
# own vertical divider lines on the sample file's page 1 (confirmed
# against a rendered crop with the boundaries drawn in, and against pages
# 2-5's own column alignment).
_COLUMNS = [
    (0.00609, 0.07203, "REF_NO"),
    (0.07203, 0.20822, "DESCRIPTION"),
    (0.20822, 0.29495, "PART_NUMBER"),
    (0.29495, 0.37535, "SERIAL_NUMBER"),
    (0.37535, 0.44459, "INST_DATE"),
    (0.44459, 0.53792, "POSITION"),
    (0.53792, 0.61476, "TIME_LIMIT"),
    (0.61476, 0.67892, "LAST_WORK_DATE"),
    (0.67892, 0.72508, "USED_TIME"),
    (0.72508, 0.78088, "REMAINING_TO_SHOP_VISIT"),
    (0.78088, 0.83160, "DUE_DATE"),
    (0.83160, 0.91605, "TASK"),
    (0.91605, 0.99366, "REMARKS"),
]

# Row-anchor scan band: TIME LIMIT through DUE DATE -- fully ruled (a real
# drawn horizontal line) on every physical row of the sample, including
# rows whose own cells there are blank (see module docstring). Deliberately
# excludes the REF_NO/DESCRIPTION/.../POSITION identity-cell band, whose
# horizontal dividers are absent wherever a component's block spans
# multiple sub-rows (that's the whole point of using this band instead).
_ROW_ANCHOR_X0 = _COLUMNS[6][0]
_ROW_ANCHOR_X1 = _COLUMNS[10][1]

_IDENTITY_COLUMNS = [
    "REF_NO", "DESCRIPTION", "PART_NUMBER", "SERIAL_NUMBER", "INST_DATE", "POSITION",
]
_NON_IDENTITY_COLUMNS = [name for _, _, name in _COLUMNS if name not in _IDENTITY_COLUMNS]

# Group-anchor scan band: REF_NO through POSITION -- these 6 columns are a
# single TALLER merged cell spanning a whole component's own multi-sub-row
# block, with identity text printed once, vertically centred across the
# whole block (see module docstring). A divider line only appears in this
# band at a genuine block boundary. Confirmed directly this is a STRICT
# SUBSET of the row-anchor band's own divider lines (every group boundary
# is also a row boundary, just not every row boundary is a group
# boundary) -- cropping each identity column to its own row-level Y-band
# (as if it were an ordinary un-merged cell) truncates a multi-line block's
# identity text top/bottom and produces OCR garbage on both halves;
# cropping to the full group band instead OCR's the whole merged cell in
# one pass.
_GROUP_ANCHOR_X0 = _COLUMNS[0][0]
_GROUP_ANCHOR_X1 = _COLUMNS[5][1]

_HEADER_FIELDS = [
    "AIRCRAFT_MODEL", "AIRCRAFT_REG", "AIRCRAFT_MSN",
    "AS_OF_DATE", "ACFT_HOURS", "ACFT_CYCLES",
]

_MODEL_RE = re.compile(r"MODEL\s*:\s*(\S+)", re.IGNORECASE)
_REG_RE = re.compile(r"REG\.?\s*NO\.?\s*:\s*(\S+)", re.IGNORECASE)
_MSN_RE = re.compile(r"SERIAL\s*NO\.?\s*:\s*(\S+)", re.IGNORECASE)
_AS_OF_DATE_RE = re.compile(r"AS\s*OF\s*DATE\s*:\s*(\S+)", re.IGNORECASE)
_ACFT_HOURS_RE = re.compile(r"AC\s*HOURS\s*:\s*(\S+)", re.IGNORECASE)
_ACFT_CYCLES_RE = re.compile(r"AC\s*CYCLES\s*:\s*(\S+)", re.IGNORECASE)

_TITLE_RE = re.compile(r"TIME\s+CONTROLLED\s+COMPONENTS(?!\s+STATUS)", re.IGNORECASE)
# This template's own distinctive column-header fragment -- "Inst. Date"
# immediately followed by "Time Limit" is this file's own ruled-table
# header line, confirmed to OCR cleanly and contiguously (unlike the
# wrapped, two-line "Remaining to Shop Visit" header a few columns over,
# which OCR reliably garbles). Checked against every SIGNATURES list in
# occm.py/ht.py/llp.py and every existing occm_variants/ht_variants/
# llp_variants module's own SIGNATURES list, plus a plain grep for "INST
# DATE"/"INST. DATE" and "TIME LIMIT"; several other modules use one of
# those two phrases individually but none combines them contiguously.
_SUBTITLE_RE = re.compile(r"INST\.?\s*DATE\s+TIME\s+LIMIT", re.IGNORECASE)

# A ruled-border sliver at a column's own left/right edge occasionally OCRs
# as a lone punctuation "word" -- dropped before joining a cell's tokens,
# same convention as this package's other ruled-grid OCR variants.
_PURE_PUNCT_RE = re.compile(r"^[|_=~—\-:;.,]+$")
_CODE_STRIP_CHARS = " _\"'`‘’“”.,;:()[]{}|~=—"

# Same-row divider-line merge tolerance, expressed as a fraction of the
# rendered page's own height -- adjacent detected dark pixels within this
# gap collapse into a single divider line.
_LINE_MERGE_PX = 4
_DARK_THRESHOLD = 200
_ROW_DARK_FRAC_MIN = 0.6

# Two words on the same printed line can come back from Tesseract with
# slightly different (or tied/reversed) "top" values -- bucketed into
# lines first, then ordered left-to-right within each line, same
# convention as this package's other ruled-grid OCR variants.
_LINE_BUCKET_PX = 8


def _col_bounds(w: int, name: str) -> tuple[int, int]:
    for lo, hi, col in _COLUMNS:
        if col == name:
            return int(lo * w), int(hi * w)
    raise KeyError(name)


def _row_dark_frac(arr: np.ndarray, x0: int, x1: int) -> np.ndarray:
    sub = arr[:, x0:x1]
    dark = sub < _DARK_THRESHOLD
    return dark.sum(axis=1) / sub.shape[1]


def _divider_lines(arr: np.ndarray, x0: int, x1: int, y_lo: int = 0, y_hi: int | None = None) -> list[int]:
    h = arr.shape[0]
    if y_hi is None:
        y_hi = h
    frac = _row_dark_frac(arr, x0, x1)
    ys = [y for y in range(y_lo, y_hi) if frac[y] > _ROW_DARK_FRAC_MIN]
    groups: list[list[int]] = []
    for y in ys:
        if groups and y - groups[-1][-1] <= _LINE_MERGE_PX:
            groups[-1].append(y)
        else:
            groups.append([y])
    return [int(np.mean(g)) for g in groups]


def _find_header_lines(img) -> list[int]:
    """Page 1's own header-box + title + column-header row divider Y
    positions. Not hardcoded -- located at runtime via the ruled grid's own
    full-width divider lines in the page's own top ~30%, since a few pixels
    of scan-to-scan skew shift this slightly (same reasoning this
    package's other raster-grid HT variants use). Expects 4 full-width
    dividers above the first data row on a page-1-shaped header (info-box
    top, info-box bottom/title-bar top, title-bar bottom/column-header top,
    column-header bottom) -- confirmed directly against a rendered crop
    with the boundaries drawn in."""
    arr = np.array(img.convert("L"))
    h, w = arr.shape
    x0, x1 = int(_COLUMNS[0][0] * w), int(_COLUMNS[-1][1] * w)
    return _divider_lines(arr, x0, x1, y_lo=0, y_hi=int(h * 0.3))


def _find_data_start(img) -> int:
    """Top of the first real data row on page 1 (see `_find_header_lines`).
    Falls back to a conservative page-fraction estimate if fewer than 4
    header dividers are found (e.g. a differently-cropped scan of this same
    template)."""
    lines = _find_header_lines(img)
    if len(lines) >= 4:
        return lines[3]
    return int(img.height * 0.28)


async def _ocr_column(img, name: str, y0: int, y1: int, scale: int = 2) -> list[tuple[float, float, str]]:
    x0, x1 = _col_bounds(img.width, name)
    if y1 <= y0:
        return []
    crop = img.crop((x0, y0, x1, y1))
    if scale != 1:
        crop = crop.resize((crop.width * scale, crop.height * scale), Image.LANCZOS)

    def _to_tokens(words) -> list[tuple[float, float, str]]:
        out = []
        for wd in words:
            text = str(wd.get("text", "")).strip()
            if not text or _PURE_PUNCT_RE.match(text):
                continue
            top = y0 + wd["top"] / scale
            left = wd.get("left", 0) / scale
            out.append((top, left, text))
        return out

    tokens = _to_tokens(await ocr_words(crop, psm=6, min_conf=-1))
    if tokens:
        return tokens
    # Fallback: psm=6 (uniform block) confirmed directly to return NOTHING
    # at all on a short, sparse, single-short-number cell (e.g. a
    # USED_TIME/REMAINING_TO_SHOP_VISIT value like "53" sitting alone in an
    # otherwise-blank ~180px-wide crop) even though the digits are clearly
    # legible in the source raster -- Tesseract's own block-segmentation
    # step drops it rather than misreading it. psm=8 (treat the crop as a
    # single word) recovers it reliably on the same cells where psm=6
    # found nothing; tried second (not first) since psm=6 is the more
    # reliable choice whenever it DOES find something (correct multi-token
    # ordering for a wrapped 2-line cell, which psm=8 does not attempt).
    return _to_tokens(await ocr_words(crop, psm=8, min_conf=-1))


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
    if name in ("REF_NO", "PART_NUMBER", "SERIAL_NUMBER", "POSITION"):
        text = text.strip(_CODE_STRIP_CHARS)
    if name in ("USED_TIME", "REMAINING_TO_SHOP_VISIT"):
        # These two columns are pure integer counts in every real row of
        # the sample (never a unit, letter or punctuation) -- confirmed
        # directly. The psm=8 single-word OCR fallback these short, sparse
        # cells often need (see `_ocr_column`'s own docstring) occasionally
        # attaches stray fringe punctuation/letters around a correctly-read
        # digit run (e.g. "67" misread as "*67s"); stripping to digits-only
        # recovers the real value rather than leaving the noisy raw token
        # in an otherwise strictly-numeric field. A cell that OCR's as pure
        # noise with no digit run at all (rare) becomes an honest empty
        # string instead of a misleading non-numeric token.
        text = "".join(ch for ch in text if ch.isdigit())
    return text


async def _parse_header(img, data_start: int) -> dict:
    meta = {k: "" for k in _HEADER_FIELDS}
    w, h = img.size
    crop = img.crop((0, 0, w, max(data_start, 1)))
    crop = crop.resize((crop.width * 2, crop.height * 2), Image.LANCZOS)
    text = await ocr_text(crop, psm=6)

    def grab(rx: re.Pattern) -> str:
        m = rx.search(text)
        return m.group(1).strip(_CODE_STRIP_CHARS) if m else ""

    meta["AIRCRAFT_MODEL"] = grab(_MODEL_RE)
    meta["AIRCRAFT_REG"] = grab(_REG_RE)
    meta["AIRCRAFT_MSN"] = grab(_MSN_RE)
    meta["AS_OF_DATE"] = grab(_AS_OF_DATE_RE)
    meta["ACFT_HOURS"] = grab(_ACFT_HOURS_RE)
    meta["ACFT_CYCLES"] = grab(_ACFT_CYCLES_RE)
    return meta


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback.
    Requires BOTH this file's own bare title line ("TIME CONTROLLED
    COMPONENTS", NOT followed by "STATUS" -- that's the different, sibling
    `time_controlled_components_status.py` template) AND its own
    distinctive "Inst. Date Time Limit" column-header fragment (see
    `_SUBTITLE_RE` above for the collision check).

    The title and column-header rows are OCR'd as two SEPARATE crops,
    isolated via `_find_header_lines()`, rather than one combined pass over
    the whole top-of-page region -- confirmed directly on the sample file
    that a single psm=6 pass over the combined logo/info-box/title/column-
    header block scrambles reading order badly enough that the title line
    is dropped entirely (the info-box's own 3-column PREPARED BY/EXAMINED
    BY/DATE labels interleave with it); each row OCR's cleanly once
    isolated to its own narrow Y-band."""
    try:
        img = await render_page(pdf_path, 0, dpi=300)
        lines = _find_header_lines(img)
        if len(lines) < 4:
            return False
        w = img.width
        title_crop = img.crop((0, lines[1], w, lines[2]))
        header_crop = img.crop((0, lines[2], w, lines[3]))
        title_text = await ocr_text(title_crop, psm=7)
        header_text = await ocr_text(header_crop, psm=6)
        return bool(_TITLE_RE.search(title_text) and _SUBTITLE_RE.search(header_text))
    except Exception:
        return False


async def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    header_meta = {k: "" for k in _HEADER_FIELDS}
    # Most recently seen non-blank identity block -- carries across a page
    # boundary too (a block's own identity text is printed once, on its
    # first physical row, and can therefore sit on the PREVIOUS page when
    # the block's own later sub-rows spill onto this one; see module
    # docstring). Maintained outside the per-page loop for exactly that
    # reason.
    identity: dict[str, str] = {k: "" for k in _IDENTITY_COLUMNS}
    n_pages = await page_count(pdf_path)

    for page_index in range(n_pages):
        img = await render_page(pdf_path, page_index, dpi=300)
        w, h = img.size
        arr = np.array(img.convert("L"))

        data_start = _find_data_start(img) if page_index == 0 else 0

        if page_index == 0 and not all(header_meta.values()):
            header_meta = await _parse_header(img, data_start)

        # Fine row grain -- one ruled sub-row per output record (see
        # _ROW_ANCHOR_X0/X1 above).
        rx0 = int(_ROW_ANCHOR_X0 * w)
        rx1 = int(_ROW_ANCHOR_X1 * w)
        row_lines = _divider_lines(arr, rx0, rx1, y_lo=data_start, y_hi=h)
        # Tolerance guards against `_divider_lines`' own first detected line
        # sitting a pixel or two below `data_start` (rounding at the group/
        # row scans' own slightly different X-bands) -- without it, a
        # near-zero-height spurious first "row" gets inserted between
        # data_start and that first real line.
        if row_lines and row_lines[0] - data_start > _LINE_MERGE_PX:
            row_lines = [data_start] + row_lines
        if len(row_lines) < 2:
            continue

        # Coarse group grain -- one merged identity block per component,
        # a strict subset of row_lines (see _GROUP_ANCHOR_X0/X1 above).
        gx0 = int(_GROUP_ANCHOR_X0 * w)
        gx1 = int(_GROUP_ANCHOR_X1 * w)
        group_lines = _divider_lines(arr, gx0, gx1, y_lo=data_start, y_hi=h)
        if group_lines and group_lines[0] - data_start > _LINE_MERGE_PX:
            group_lines = [data_start] + group_lines
        if not group_lines or group_lines[-1] < row_lines[-1]:
            group_lines = group_lines + [row_lines[-1]]

        # OCR each identity column once PER GROUP (its own full merged-cell
        # Y-span), not once per fine sub-row -- both for correctness (see
        # module docstring) and because it's far fewer OCR calls.
        group_identity: list[dict[str, str]] = []
        for gi in range(len(group_lines) - 1):
            glo, ghi = group_lines[gi], group_lines[gi + 1]
            block: dict[str, str] = {}
            for name in _IDENTITY_COLUMNS:
                toks = await _ocr_column(img, name, glo, ghi)
                block[name] = _clean_field(name, toks)
            group_identity.append(block)

        gi = 0
        for i in range(len(row_lines) - 1):
            lo, hi = row_lines[i], row_lines[i + 1]
            while gi < len(group_lines) - 2 and group_lines[gi + 1] <= lo:
                gi += 1

            row: dict[str, str] = {}
            for name in _NON_IDENTITY_COLUMNS:
                # OCR'd per-row-per-column, one crop at a time -- confirmed
                # directly that a single psm=6 pass over a whole tall
                # column crop (spanning every sub-row on the page at once)
                # drops the large majority of short numeric tokens (e.g.
                # USED_TIME/REMAINING_TO_SHOP_VISIT figures like "10824" /
                # "7176"), recognising only a handful of the larger/denser
                # DATE-shaped values -- Tesseract's own page/line
                # segmentation degrades badly on a crop this tall and
                # sparse. A fresh, narrow single-row crop per cell OCR's
                # reliably (confirmed directly on the same cells) at the
                # cost of many more OCR calls, same tradeoff this
                # project's other ruled-grid OCR variants make for a
                # merged/irregular cell (see e.g. the per-group identity
                # OCR just above).
                toks = await _ocr_column(img, name, lo, hi)
                row[name] = _clean_field(name, toks)

            block = group_identity[gi] if gi < len(group_identity) else {k: "" for k in _IDENTITY_COLUMNS}
            # REF_NO is this file's own reliable "genuine new component"
            # signal (printed on every real block's own first row, even
            # when e.g. POSITION is legitimately blank for that
            # component) -- gates a wholesale replace of `identity`
            # rather than a per-field merge, so a real block's own
            # legitimately-blank field (POSITION, most often) is kept
            # blank instead of wrongly inheriting the PREVIOUS block's
            # value for that same field. A blank REF_NO means this
            # group's own crop carried no identity text at all (a
            # page-boundary continuation, see module docstring), so the
            # entire previous block carries forward unchanged.
            if block["REF_NO"]:
                identity = dict(block)
            for k in _IDENTITY_COLUMNS:
                row[k] = identity[k]

            row["_page"] = page_index + 1
            row.update(header_meta)
            records.append(row)

    return records
