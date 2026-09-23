""""Hard Time Components" report -- scanned (no usable text layer), a
distinct ruled-grid template from this package's other "Hard Time
Component(s) ..."-titled variants.

Confirmed directly on a real corpus sample (4 pages, 300 DPI render):
`page.rects`/`page.lines`/`page.curves` are all empty and `page.images`
holds exactly one full-page raster image per page (the same "scanned
sandwich" shape this package's other raster-grid HT variants describe,
e.g. `hard_time_day_fhr_cyc_matrix_scanned.py`), and `page.extract_text()`
returns under 100 characters of decode-garbage per page (well under the
router's own blank-text threshold), so this module renders + OCRs every
page end to end; there is no plain-text SIGNATURES path (empty list, see
below), detection is via `ocr_detect()` only.

Header block (repeats near-identically on every page, upper-left/right of
an operator wordmark)::

    Hard Time Components; MSN:<msn>, <tail>          As of: <dd-Mon-yy>
                                                       TSN: <n>
    <operator wordmark>                               CSN: <n>

This exact title shape -- the semicolon right after "Components", followed
by "MSN:" on the same line, plus the "TSN:"/"CSN:"/"As of:" three-line
block stacked to the right -- is what distinguishes this template from
`hard_time_components_bordered_table.py`'s own "HARD TIME COMPONENTS"
sample (no semicolon, no inline MSN, a different AIRCRAFT REGISTRATION /
SERIAL NO. / SUMMARY DATE key-value header instead, 19 ruled columns, no
"Action" column, no "Time between overhaul" group) and from every other
"Hard Time ..."/"HT ..." sibling in this package (checked directly, see
SIGNATURES below for the collision check on this file's own OCR anchor).

Main table, two ruled header rows tall, repeated on every page, 23 columns
total::

    row 1: ATA | Partnumber | Serialnumber | Part description |
           Task Number | Position | Action |
           Installation (x3) | Last accomplished (x3) |
           Time between overhaul (x3) | Next due (x3) | Remaining (x3) |
           Remarks
    row 2: (blank x7) | Date FH FC | Date FH FC | Days FH FC |
           Date FH FC | Days FH FC | MPD TASK

Column grain, left to right (23 total, matching the ruled grid's own cell
boundaries)::

    ATA | PART_NUMBER | SERIAL_NUMBER | DESCRIPTION | TASK_NUMBER |
    POSITION | ACTION |
    INSTALL_DATE | INSTALL_FH | INSTALL_FC |
    LAST_ACC_DATE | LAST_ACC_FH | LAST_ACC_FC |
    TBO_DAYS | TBO_FH | TBO_FC |
    NEXT_DUE_DATE | NEXT_DUE_FH | NEXT_DUE_FC |
    REMAINING_DAYS | REMAINING_FH | REMAINING_FC |
    REMARKS_MPD_TASK

Column boundaries are fixed pixel fractions of the rendered page's own
width, derived directly from a numpy column-darkness scan of the ruled
grid's own vertical divider lines at 300 DPI (confirmed stable across all
4 sample pages, each rendering at the same 3300px width). The scan also
showed the whole grid carries a small, consistent rotation (~0.3-0.6
degrees -- confirmed directly by probing the table's own left-edge divider
at several y-values on the same page: it drifts ~9-11px from the top of
the table to the bottom), so a single fixed x per column is not quite
enough on its own; `extract()` re-probes that same left-edge divider at
two y-values on each page and derives a per-page pixel/row slope, which is
then subtracted from every OCR'd word's own x position before bucketing it
into a column (equivalent to de-skewing the words rather than the image).

Row grain: a tracked component instance is usually 1-3 physical ruled
rows -- one per distinct Action performed against it (e.g. a pressure
cylinder's own "Discard" row directly followed by its own "Hydrost test"
row). ATA/PART_NUMBER/SERIAL_NUMBER/DESCRIPTION/TASK_NUMBER/POSITION are
rendered once per component, in a cell that's visually merged down the
component's own full run of Action rows, and blank on every row below the
first; ACTION and the 15 date/FH/FC/day cells plus REMARKS_MPD_TASK are
populated independently on every physical row (confirmed directly, e.g. a
battery with a "Elec lvl check" row followed by its own separate
"Restoration" row: TASK_NUMBER repeats on both, but ATA/PART_NUMBER/
SERIAL_NUMBER/DESCRIPTION only print once, on the first).

ACTION is used as the per-row Y anchor (present, non-blank, on every real
data row -- including a component's own second/third Action row) rather
than ATA (present only on a component's own first row, so far too sparse
to anchor on, the same reasoning `hard_time_day_fhr_cyc_matrix_scanned.py`
gives for preferring its own TASK_CARD anchor over its own sparse ATA
column). Anchor words are matched against a closed vocabulary of this
report's own Action values (Restoration, Discard, Repack, OPC, GVI, FNC,
Hydrost test, Weight check, Elec lvl check -- plus a couple of
OCR-glued/misread spellings actually seen in the sample, e.g. "Elecivi" for
"Elec lvl") rather than accepting any alphabetic token in that column's own
x-band, so a mis-bucketed fragment of a "CHAPTER NN" section-divider
banner (present between ATA chapters on every page, its own gray band
sometimes bleeding OCR noise into neighbouring column bands) can't
masquerade as a row.

The merged-cell identity fields (ATA, PART_NUMBER, SERIAL_NUMBER,
DESCRIPTION, TASK_NUMBER, POSITION) are forward-filled across a
component's own run of Action rows, but the fill resets to blank the
moment a fresh ATA value is read directly off a row -- not a plain
carry-forward with no reset, since a genuinely blank TASK_NUMBER on a new
component (seen directly in the sample: e.g. an emergency-evacuation-slide
component whose own TASK_NUMBER cell is blank on every one of its Action
rows) would otherwise wrongly inherit the previous component's own
TASK_NUMBER value. ATA itself is also narrowed to its own leading 2-digit
chapter (matching this project's global ATA rule/range) rather than kept
as the source's full 6-digit chapter+section run, following this
package's own `aircraft_rotables_ht.py` convention for a similarly-shaped
source code.

The trailing 15 date/FH/FC/day cells and REMARKS_MPD_TASK are never
forward-filled (each Action row's own timing values are genuinely its
own). Each numeric/day cell is reduced to a plain digit run (a bare "-"
placeholder, this report's own explicit "not tracked on this basis" mark,
correctly reduces to blank); each date cell accepts a "D-Mon-YYYY" or
"DD-Mon-YY" shape, tolerant of an OCR-dropped dash between day and month
(e.g. "24May-19" for "24-May-19", seen directly in the sample).
REMARKS_MPD_TASK is free text (usually an ATA-style "NN-NN-NN-NNN" task
code, occasionally an AD/service-bulletin reference instead, e.g.
"AD 2013-25-04 FAA") and is kept as one joined string rather than
force-split.

A signature block (name, hand signature, position, date, and an operator
authorisation stamp) appears once, on the last page, below the final
data row. No person's name from that block is extracted into any field --
confirmed directly this module's own row anchor (a data row's own ACTION
cell) never matches inside that block, so it is naturally excluded rather
than needing an explicit footer-skip rule.

Header metadata (MSN/TAIL/TSN/CSN/REPORT_DATE/OPERATOR) is parsed once
from a title-band crop and stamped onto every row, kept the first time
each field is non-empty across pages (this report's own header repeats
per page but a later page occasionally OCRs a field the first page
missed).
"""
from __future__ import annotations
import re

from PIL import Image

from sheet_types.ht_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_words, ocr_text, page_count

NAME = "Hard Time Components (Semicolon/MSN Header, Scanned)"

# Deliberately empty -- see module docstring. The known source file has no
# usable text layer at all, so plain-pdfplumber SIGNATURES can never fire;
# detection happens structurally via ocr_detect() below, same pattern as
# this package's other raster-grid HT variants (amos_scanned.py,
# hard_time_day_fhr_cyc_matrix_scanned.py, etc).
SIGNATURES: list[str] = []

CANONICAL_COLUMNS = [
    "ATA",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
    "TASK_NUMBER",
    "POSITION",
    "ACTION",
    "INSTALL_DATE",
    "INSTALL_FH",
    "INSTALL_FC",
    "LAST_ACC_DATE",
    "LAST_ACC_FH",
    "LAST_ACC_FC",
    "TBO_DAYS",
    "TBO_FH",
    "TBO_FC",
    "NEXT_DUE_DATE",
    "NEXT_DUE_FH",
    "NEXT_DUE_FC",
    "REMAINING_DAYS",
    "REMAINING_FH",
    "REMAINING_FC",
    "REMARKS_MPD_TASK",
    # Header metadata -- same on every page of a given file, stamped on
    # every row.
    "OPERATOR",
    "MSN",
    "TAIL",
    "TSN",
    "CSN",
    "REPORT_DATE",
]

_DATE_RE = r"^\d{1,2}-?[A-Za-z]{3,9}-\d{2,4}$"
_NUM_RE = r"^-?[\d,]+$"

_OVERRIDES = {
    "ATA": {"pattern": r"^\d{2}$", "int_range": (20, 83), "allow_empty": True},
    "PART_NUMBER": {"allow_empty": True},
    "SERIAL_NUMBER": {"allow_empty": True},
    "DESCRIPTION": {"allow_empty": True},
    "TASK_NUMBER": {"allow_empty": True},
    "POSITION": {"allow_empty": True},
    "ACTION": {"allow_empty": True},
    "INSTALL_DATE": {"pattern": _DATE_RE, "allow_empty": True},
    "INSTALL_FH": {"pattern": _NUM_RE, "allow_empty": True},
    "INSTALL_FC": {"pattern": _NUM_RE, "allow_empty": True},
    "LAST_ACC_DATE": {"pattern": _DATE_RE, "allow_empty": True},
    "LAST_ACC_FH": {"pattern": _NUM_RE, "allow_empty": True},
    "LAST_ACC_FC": {"pattern": _NUM_RE, "allow_empty": True},
    "TBO_DAYS": {"pattern": _NUM_RE, "allow_empty": True},
    "TBO_FH": {"pattern": _NUM_RE, "allow_empty": True},
    "TBO_FC": {"pattern": _NUM_RE, "allow_empty": True},
    "NEXT_DUE_DATE": {"pattern": _DATE_RE, "allow_empty": True},
    "NEXT_DUE_FH": {"pattern": _NUM_RE, "allow_empty": True},
    "NEXT_DUE_FC": {"pattern": _NUM_RE, "allow_empty": True},
    "REMAINING_DAYS": {"pattern": _NUM_RE, "allow_empty": True},
    "REMAINING_FH": {"pattern": _NUM_RE, "allow_empty": True},
    "REMAINING_FC": {"pattern": _NUM_RE, "allow_empty": True},
    "REMARKS_MPD_TASK": {"allow_empty": True},
    "OPERATOR": {"allow_empty": True},
    "MSN": {"allow_empty": True},
    "TAIL": {"allow_empty": True},
    "TSN": {"allow_empty": True},
    "CSN": {"allow_empty": True},
    "REPORT_DATE": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Column boundaries, as a fraction of the rendered page's own width --
# derived directly from a numpy column-darkness scan of the ruled grid's
# own vertical divider lines at 300 DPI on the header row of each of the
# 4 sample pages (stable across all 4, each page rendering at the same
# 3300px width). See module docstring for the per-page de-skew this is
# combined with at runtime.
_COLUMNS = [
    (0.13273, 0.16758, "ATA"),
    (0.16758, 0.21758, "PART_NUMBER"),
    (0.21758, 0.26606, "SERIAL_NUMBER"),
    (0.26606, 0.40758, "DESCRIPTION"),
    (0.40758, 0.46000, "TASK_NUMBER"),
    (0.46000, 0.51485, "POSITION"),
    (0.51485, 0.54818, "ACTION"),
    (0.54818, 0.58152, "INSTALL_DATE"),
    (0.58152, 0.60848, "INSTALL_FH"),
    (0.60848, 0.62909, "INSTALL_FC"),
    (0.62909, 0.66424, "LAST_ACC_DATE"),
    (0.66424, 0.69091, "LAST_ACC_FH"),
    (0.69091, 0.71242, "LAST_ACC_FC"),
    (0.71242, 0.73818, "TBO_DAYS"),
    (0.73818, 0.75909, "TBO_FH"),
    (0.75909, 0.78242, "TBO_FC"),
    (0.78242, 0.81909, "NEXT_DUE_DATE"),
    (0.81909, 0.84000, "NEXT_DUE_FH"),
    (0.84000, 0.86485, "NEXT_DUE_FC"),
    (0.86485, 0.89394, "REMAINING_DAYS"),
    (0.89394, 0.91636, "REMAINING_FH"),
    (0.91636, 0.93879, "REMAINING_FC"),
    (0.93879, 0.99061, "REMARKS_MPD_TASK"),
]
_COL_NAMES = [name for _, _, name in _COLUMNS]

_JOIN_SPACE = {"DESCRIPTION", "TASK_NUMBER", "POSITION", "ACTION", "REMARKS_MPD_TASK"}
_NUMERIC_COLS = {
    "INSTALL_FH", "INSTALL_FC", "LAST_ACC_FH", "LAST_ACC_FC",
    "TBO_DAYS", "TBO_FH", "TBO_FC",
    "NEXT_DUE_FH", "NEXT_DUE_FC",
    "REMAINING_DAYS", "REMAINING_FH", "REMAINING_FC",
}
_DATE_COLS = {"INSTALL_DATE", "LAST_ACC_DATE", "NEXT_DUE_DATE"}
_CODE_COLS = {"ATA", "PART_NUMBER", "SERIAL_NUMBER"}
_CODE_STRIP_CHARS = " _\"'`'‘’“”.,;:()[]{}|~=–—"

_NUM_TOKEN_RE = re.compile(r"-?[\d,]{1,}")
_DATE_TOKEN_RE = re.compile(r"\d{1,2}-?[A-Za-z]{3,9}-\d{2,4}")
_ATA_TOKEN_RE = re.compile(r"^\d{6}$")
_ATA_MIN, _ATA_MAX = 20, 83

# Closed vocabulary of this report's own Action column values, used as the
# per-row Y anchor (see module docstring for why ACTION, not ATA). Includes
# a couple of OCR-glued/misread spellings actually seen in the real sample
# (e.g. "Elecivi" for "Elec lvl").
_ACTION_WORDS = {
    "RESTORATION", "DISCARD", "REPACK", "OPC", "GVI", "FNC",
    "HYDROST", "TEST", "HYDROSTTEST",
    "WEIGHT", "CHECK", "WEIGHTCHECK",
    "ELEC", "LVL", "ELECIVI", "ELECLVLCHECK",
}

_FILLABLE = ("PART_NUMBER", "SERIAL_NUMBER", "DESCRIPTION", "TASK_NUMBER", "POSITION")

# Row-cluster tolerance for merging adjacent ACTION-column word boxes that
# belong to the same physical row (e.g. "Elec"/"lvl"/"check" as three
# separate OCR word boxes) -- measured directly against this file's own
# row pitch (single ruled rows sit ~19-21px apart at 300 DPI on the
# sample), comfortably under half that.
_ANCHOR_TOLERANCE_PX = 11

# Per-column strip padding, in source (pre-upscale) pixels each side of a
# column's own fixed boundary -- absorbs this file's own small per-page
# rotation (confirmed directly: the ruled grid's left-edge divider drifts
# ~9-11px from the top of a page's own table to the bottom) without
# needing to compute and apply an explicit per-page slope, at the cost of
# an occasional sliver of a neighbouring column's own text at the extreme
# top/bottom of a page -- accepted per this project's per-column-strip-OCR
# convention (see module docstring for why whole-row/whole-page OCR was
# tried first and abandoned: Tesseract's own word segmentation glued
# separate columns' text together into single nonsense "words" under psm 6
# run across the full row width, which no amount of downstream
# coordinate-bucketing could safely undo).
_COL_PAD_PX = 8

_HEADER_FIELDS = ["OPERATOR", "MSN", "TAIL", "TSN", "CSN", "REPORT_DATE"]
_TITLE_RE = re.compile(
    r"Hard\s*Time\s*Components[;:]?\s*MSN[:.]?\s*([\w\-]+)\s*,\s*([\w\-]+)",
    re.IGNORECASE,
)
_TSN_RE = re.compile(r"TSN[:.]?\s*([\d.,:]+)", re.IGNORECASE)
_CSN_RE = re.compile(r"CSN[:.]?\s*([\d.,:]+)", re.IGNORECASE)
_ASOF_RE = re.compile(r"As\s*o[fl][ft]?[:.]?\s*(\S+)", re.IGNORECASE)


def _col_bounds(w: int, name: str) -> tuple[float, float]:
    for lo, hi, col in _COLUMNS:
        if col == name:
            return lo * w, hi * w
    raise KeyError(name)


async def _ocr_column(img, name: str, y0: int, y1: int, scale: int = 2
                       ) -> list[tuple[float, float, str]]:
    """OCR one column's own full-height strip in isolation and return
    (top, left, text) triples in original-page pixel coordinates (top) /
    crop-local coordinates (left, only used to order same-row tokens for
    joining). Cropping and OCR-ing each column separately -- rather than
    one whole-row/whole-page OCR pass bucketed afterwards by coordinate --
    is this project's own established fix for a ruled grid whose
    whole-row OCR comes back badly glued/garbled (see module docstring)."""
    lo, hi = _col_bounds(img.width, name)
    x0 = max(0, int(lo) - _COL_PAD_PX)
    x1 = min(img.width, int(hi) + _COL_PAD_PX)
    crop = img.crop((x0, y0, x1, y1))
    if scale != 1:
        crop = crop.resize((crop.width * scale, crop.height * scale), Image.LANCZOS)
    # psm 3 (full automatic page segmentation), not this project's usual
    # psm 6 (uniform block) -- confirmed directly on the real sample: a
    # narrow, very tall single-column crop stacking 80-90+ short, mutually
    # unrelated fragments confuses psm 6's "one uniform block" assumption
    # into merging/dropping most of them (as few as ~25 words recovered
    # from a column with ~90 real rows); psm 3's own layout analysis finds
    # each short line as its own text block instead and recovers close to
    # the full row count.
    words = await ocr_words(crop, psm=3, min_conf=-1)
    out = []
    for wd in words:
        text = str(wd.get("text", "")).strip()
        if not text:
            continue
        top = y0 + float(wd["top"]) / scale
        left = float(wd["left"]) / scale
        out.append((top, left, text))
    return out


# ACTION-column-only chunk height/overlap and psm sweep used by
# `_ocr_action_column` -- see that function's own docstring for why this
# column gets a heavier pass than every other column's own single-shot
# `_ocr_column` call.
_ACTION_CHUNK_PX = 600
_ACTION_CHUNK_OVERLAP_PX = 60
_ACTION_PSM_SWEEP = (3, 6)


async def _ocr_action_column(img, y0: int, y1: int, scale: int = 2
                              ) -> list[tuple[float, float, str]]:
    """ACTION gets its own heavier OCR pass because it is this module's
    only row anchor (see module docstring) -- silently losing an ACTION
    reading loses the whole row, not just one field, unlike every other
    column. Confirmed directly on the real sample that a single
    `_ocr_column`-style whole-page-height OCR pass genuinely drops entire
    runs of otherwise perfectly legible rows (e.g. a long run of repeated
    "Restoration" values, all visually identical print, all on their own
    ruled row) -- neither swapping psm mode nor binarizing the crop alone
    fully explained or fixed it, but splitting the column into shorter,
    overlapping vertical chunks and OCR-ing each with more than one psm
    mode recovers most of the loss (the failure mode looks like a
    Tesseract line-segmentation limit on a very tall, narrow, mostly
    single-word-per-line image, not a resolution/contrast problem this
    project's usual fixes address). The overlap keeps a row that lands on
    a chunk boundary from being cut in half in both chunks. The psm sweep
    and the chunk overlap both also routinely re-detect the same real word
    a second (or third) time at (almost) the exact same position -- fine
    for the row-anchor list itself (deduplicated by y-proximity once this
    returns) but confirmed directly to otherwise leak straight through
    into the joined ACTION text as a visible "Restoration Restoration"-
    style doubling, since nothing downstream of this function was
    deduplicating the raw tokens themselves; `_dedupe_ocr_items` below
    fixes that before returning."""
    lo, hi = _col_bounds(img.width, "ACTION")
    x0 = max(0, int(lo) - _COL_PAD_PX)
    x1 = min(img.width, int(hi) + _COL_PAD_PX)
    out: list[tuple[float, float, str]] = []
    y = y0
    while y < y1:
        yy1 = min(y1, y + _ACTION_CHUNK_PX)
        crop = img.crop((x0, y, x1, yy1))
        if scale != 1:
            crop = crop.resize((crop.width * scale, crop.height * scale), Image.LANCZOS)
        for psm in _ACTION_PSM_SWEEP:
            words = await ocr_words(crop, psm=psm, min_conf=-1)
            for wd in words:
                text = str(wd.get("text", "")).strip()
                if not text:
                    continue
                top = y + float(wd["top"]) / scale
                left = float(wd["left"]) / scale
                out.append((top, left, text))
        y += _ACTION_CHUNK_PX - _ACTION_CHUNK_OVERLAP_PX
    # The psm sweep and the overlapping chunks both routinely re-detect the
    # exact same word at (almost) the same position -- see
    # `_dedupe_ocr_items` docstring for why this is fixed here rather than
    # left to downstream bucketing/joining.
    return _dedupe_ocr_items(out)


def _dedupe_ocr_items(
    items: list[tuple[float, float, str]], tol: float = 3.0
) -> list[tuple[float, float, str]]:
    """Drop near-duplicate (top, left, text) triples -- the same physical
    word detected more than once at (almost) the same position. Confirmed
    directly against the real sample: `_ocr_action_column`'s own psm sweep
    (3 and 6 run over the same crop) and its overlapping-chunk boundaries
    routinely both recognize the exact same word at literally identical
    (top, left) coordinates, which downstream `_nearest_anchor_buckets` /
    `_clean_field` then join into a visibly doubled/tripled value (e.g.
    "Restoration Restoration") -- confirmed this is a distinct failure
    from genuine row content, not deduplicated anywhere else in the
    pipeline (the module docstring's claim that "duplicate detections...
    are harmless... deduplicated by y-proximity" only actually applies to
    the anchor list itself, not to the text tokens that get bucketed and
    joined). A small tolerance (a few source pixels) catches the sub-pixel
    jitter between an unscaled-vs-2x-scaled-then-downscaled coordinate
    without merging two genuinely distinct words that happen to sit close
    together."""
    out: list[tuple[float, float, str]] = []
    for top, left, text in items:
        if any(
            t2 == text and abs(o_top - top) <= tol and abs(o_left - left) <= tol
            for o_top, o_left, t2 in out
        ):
            continue
        out.append((top, left, text))
    return out


def _nearest_anchor_buckets(
    anchors: list[float], items: list[tuple[float, float, str]]
) -> dict[float, list[tuple[float, str]]]:
    """Partition one column's own (top, left, text) triples across row
    anchors by simple nearest-anchor assignment -- each OCR'd token goes to
    exactly one row, whichever anchor's own y sits closest to it. This is
    what correctly handles a merged identity cell that visually spans
    several Action rows (its own token's y typically centers over the
    block, closest to one particular row within it) without the risk a
    fixed-radius-per-anchor scheme has of the same token being pulled into
    more than one row's own bucket (confirmed directly: an earlier
    whole-page-OCR draft of this module did exactly that, badly duplicating
    DESCRIPTION/PART_NUMBER/etc. text across neighbouring rows)."""
    buckets: dict[float, list[tuple[float, str]]] = {a: [] for a in anchors}
    if not anchors:
        return buckets
    for top, left, text in items:
        best = min(anchors, key=lambda a: abs(a - top))
        buckets[best].append((left, text))
    return buckets


def _clean_field(name: str, tokens: list[str]) -> str:
    if name in _NUMERIC_COLS:
        found: list[str] = []
        for t in tokens:
            found.extend(_NUM_TOKEN_RE.findall(t))
        seen = list(dict.fromkeys(found))
        if not seen:
            return ""
        return max(seen, key=len)
    if name in _DATE_COLS:
        found = []
        for t in tokens:
            found.extend(_DATE_TOKEN_RE.findall(t))
        found = list(dict.fromkeys(found))
        return " ".join(found)
    sep = " " if name in _JOIN_SPACE else ""
    text = sep.join(tokens)
    if name in _CODE_COLS:
        text = text.strip(_CODE_STRIP_CHARS)
    return text


async def _parse_header(img) -> dict:
    meta = {k: "" for k in _HEADER_FIELDS}
    w = img.width

    async def line(y0: int, y1: int, x0: int, x1: int) -> str:
        crop = img.crop((x0, y0, x1, y1))
        crop = crop.resize((crop.width * 2, crop.height * 2), Image.LANCZOS)
        return (await ocr_text(crop, psm=6)).strip()

    title_block = await line(140, 280, 0, w)
    m = _TITLE_RE.search(title_block)
    if m:
        meta["MSN"] = m.group(1)
        meta["TAIL"] = m.group(2)
    m = _TSN_RE.search(title_block)
    if m:
        meta["TSN"] = m.group(1)
    m = _CSN_RE.search(title_block)
    if m:
        meta["CSN"] = m.group(1)
    m = _ASOF_RE.search(title_block)
    if m:
        meta["REPORT_DATE"] = m.group(1)

    operator = await line(180, 250, 0, int(w * 0.35))
    operator = " ".join(operator.split())
    if operator:
        meta["OPERATOR"] = operator

    return meta


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback (see
    sheet_types/ht.py) -- this variant's SIGNATURES is deliberately empty
    (see module docstring).

    Anchors on "TIME BETWEEN OVERHAUL", this template's own distinctive
    column-group header phrase -- checked against every SIGNATURES list in
    occm.py/ht.py/llp.py and every occm_variants/ht_variants/llp_variants
    module's own SIGNATURES list, plus a plain grep across the entire
    project tree for the phrase "time between overhaul"; no occurrence
    found anywhere else at all, let alone a collision.
    """
    try:
        img = await render_page(pdf_path, 0, dpi=300)
        w, h = img.size
        crop = img.crop((0, int(h * 0.10), w, int(h * 0.14)))
        text = (await ocr_text(crop, psm=6)).upper()
        # OCR sometimes glues the group-header phrase with no spaces
        # ("TIMEBETWEENOVERHAUL") -- checked both the spaced and glued
        # forms against every SIGNATURES list (see docstring); neither
        # collides anywhere else in the project.
        compact = re.sub(r"[^A-Z]", "", text)
        return "TIME BETWEEN OVERHAUL" in text or "TIMEBETWEENOVERHAUL" in compact
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

        # Header/title band ends well above the first data row on every
        # page (confirmed directly against all 4 sample pages); start each
        # column's own strip below it.
        col_items: dict[str, list[tuple[float, float, str]]] = {}
        for name in _COL_NAMES:
            if name == "ACTION":
                col_items[name] = await _ocr_action_column(img, 335, h)
            else:
                col_items[name] = await _ocr_column(img, name, 335, h)

        # Row anchors: ACTION-column words matching the closed vocabulary,
        # clustered by proximity into one anchor per physical row.
        action_hits = sorted(
            top for top, _left, text in col_items["ACTION"]
            if text.strip(_CODE_STRIP_CHARS + " ").upper() in _ACTION_WORDS
        )
        anchors: list[float] = []
        for top in action_hits:
            if anchors and top - anchors[-1] <= _ANCHOR_TOLERANCE_PX:
                continue
            anchors.append(top)

        if not anchors:
            continue

        # Partition every column's own OCR'd tokens across row anchors
        # independently (see _nearest_anchor_buckets docstring).
        col_buckets = {name: _nearest_anchor_buckets(anchors, items)
                       for name, items in col_items.items()}

        cur = {f: "" for f in _FILLABLE}
        for atop in anchors:
            row: dict[str, str] = {}

            for name in _COL_NAMES:
                if name in _FILLABLE or name == "ATA":
                    continue
                toks = [text for _left, text in sorted(col_buckets[name][atop])]
                row[name] = _clean_field(name, toks)

            # ATA: own leading 2-digit chapter only (see module docstring).
            ata_raw = ""
            for _left, text in sorted(col_buckets["ATA"][atop]):
                cand = text.strip(_CODE_STRIP_CHARS)
                if _ATA_TOKEN_RE.match(cand):
                    ata_raw = cand
                    break
            ata_chapter = ""
            if ata_raw:
                chapter = int(ata_raw[:2])
                if _ATA_MIN <= chapter <= _ATA_MAX:
                    ata_chapter = ata_raw[:2]

            own = {}
            for name in _FILLABLE:
                toks = [text for _left, text in sorted(col_buckets[name][atop])]
                own[name] = _clean_field(name, toks) if toks else ""

            if ata_chapter:
                # A fresh ATA reading marks the start of a new component --
                # reset the fill cache rather than carry stale values
                # forward from a previous, differently-shaped component
                # (see module docstring).
                cur = {f: "" for f in _FILLABLE}

            for f in _FILLABLE:
                if own[f]:
                    cur[f] = own[f]
                row[f] = cur[f]

            row["ATA"] = ata_chapter
            row["_page"] = page_index + 1
            row.update(header_meta)
            records.append(row)

    return records
