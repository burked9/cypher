""""OCCM LIST" -- 13-column ruled grid, scanned, page content stored
sideways, snake_case-style column headers.

Confirmed directly on a real corpus file: 0 extractable characters on
every page via pdfplumber (a straight scan). Every page is a
portrait-shaped render whose actual content is a landscape grid drawn
sideways inside it -- same storage artifact as
`aircraft_build_occm_status_rotated_scanned.py` (confirmed directly: the
page's own `/Rotate` attribute reads 0 -- pdfplumber/pymupdf report no
rotation metadata at all -- yet the rendered pixels are rotated 90 degrees;
a scan/export artifact, not a `/Rotate` flag a renderer would apply
automatically). Confirmed directly across the first, several middle, and
the last page of a 10-page real sample file: every page uses the same
sideways orientation and the same rotation direction (rotating the
rendered image 90 degrees clockwise -- `Image.rotate(-90, expand=True)` --
reproduces the correct upright reading orientation each time).

Detected the same way as that sibling module: a rendered page whose pixel
width is smaller than its height is sideways relative to this report's own
landscape-shaped grid, so it gets rotated before anything else runs.

Once upright, every page repeats the same small header box (title, then a
label:value block) directly above a single ruled 13-column grid::

    <operator logo/wordmark>          OCCM LIST      <signature block>
                            A/C     <reg> MSN <n>
                            Date    <DD-Mon-YY>
                            TSN     <n>
                            CSN     <n>

    PN_description | PN | SN | installed_date | installed_position |
    chapter | section | TSN | CSN | TSO | CSO | TSI | CSI

The column-header row's own labels are printed verbatim in snake_case
where multi-word ("PN_description", "installed_date",
"installed_position") -- confirmed directly, an unusual enough phrasing
(this package's other OCCM variants all use plain-English or all-caps
header phrases, never an underscore-joined header label) to serve as this
module's own detection anchor (see `ocr_detect()` below). The operator
wordmark/signature block in the header's top-right corner is confirmed
directly on the real sample file and intentionally NOT extracted into any
column here -- out of scope for this module, and per this project's
data-sensitivity convention no operator name, tail number or MSN is
written anywhere in this file outside the real values pulled from the PDF
into the header-metadata columns at runtime.

Row shape, confirmed directly across the sampled pages: `PN_description`
(free-text component description), `PN` (part number), `SN` (serial
number), `installed_date` (`DD/MM/YYYY`), `installed_position` (a compact
alphanumeric zone/side code), `chapter`/`section` (a 2-digit ATA chapter
plus a 2-3-digit section code), then six time/cycle columns (`TSN`, `CSN`,
`TSO`, `CSO`, `TSI`, `CSI`). A handful of rows on the real sample file
print the literal string "unknowm" (sic -- confirmed directly, present in
the source PDF's own rendered text, not an OCR misread of this module's
own doing) in place of a numeric TSN/CSN/TSO/CSO value; these are left
exactly as extracted rather than "corrected" to "unknown" or blanked, per
this project's "never guess" convention -- they surface as flagged cells
downstream, which is the correct outcome for a value this module cannot
confirm.

Row/column geometry -- pixel-ruling detection, not fixed fractions: this
scan's grid lines are visible but NOT reliably solid across a page's full
height (confirmed directly: a full-height single-threshold column scan
finds almost none of the true dividers, because a small, confirmed
per-page skew of roughly 1 degree -- also confirmed directly by measuring
the outer border's own top-left vs. top-right Y-offset on several sampled
pages -- drifts a true vertical divider's own X-position by tens of
pixels over the page's full height, below the threshold at the far
extremes). Column boundaries are instead found from several independent
short horizontal bands spaced down the page (`_robust_col_lines` below),
each cheap and individually noisy, and only an X-position agreed on by at
least three of those bands is kept -- confirmed directly, side by side
against a manual reading of the real sample file's own column dividers, to
reliably recover the correct 14 boundaries (13 columns) on every sampled
page despite the skew, where any single band alone sometimes did not. Row
boundaries are then found fresh per page from the `chapter` column's own
X-range (a narrow, short, all-digit column -- confirmed directly to OCR/
rule-detect far more cleanly than the free-text `PN_description` column
would for this same purpose).

Per-column OCR uses one whole-column-height `ocr_words()` call per column
per page (not one call per cell), with each returned word bucketed into
the row band (from the `chapter`-column row lines) whose Y-range contains
its own vertical center -- same technique, and the same rationale (a blank
cell should never misalign a row's other columns), as
`occm_components_status_ruled_grid.py`.

Known limitation, confirmed directly against the real sample file and its
own real pipeline run (`occm.normalize_and_validate()`): the six time/
cycle columns' small font is confirmed to OCR a leading "5" digit as one
of a handful of confusable glyphs ("$", "S", a stray "¢") on a
meaningful share of rows, and occasionally appends a stray bracket-shaped
character. The single-character substitutions this module's own
`_TIME_CHAR_MAP` override applies (`$`/`S`/`¢`/`!` -> the digit they
were confirmed, across the sampled pages, to consistently stand in for,
and `(`/`)` stripped as a confirmed border-bleed artifact) are the same
kind of correction this project's own global `OCR_CHAR_MAP` already makes
for other fields (e.g. `O`->`0`, `I`->`1`) -- not a guess at ambiguous
field-splitting, just a confirmed single-glyph OCR substitution scoped to
these six purely-numeric columns. `installed_position` is NOT given the
same treatment: unlike the time/cycle columns it legitimately mixes digits
and letters (its own trailing zone/side code), so a blanket digit-glyph
substitution there risks corrupting a genuine letter -- confirmed directly
that this column's own OCR error rate is higher as a result, left flagged
rather than guessed at, per this project's convention (matches the
documented tradeoff in `occm_components_status_ruled_grid.py`'s own
POSITION column).

Separately, `chapter`/`section` (mapped to this module's own `ATA`/
`SECTION` columns) are confirmed to be this file's own single weakest
column pair: their narrow shared width means a leading "8" digit in
particular is confirmed, directly and repeatedly across the sampled
pages, to OCR as one of several different letters/symbols with no single
consistent substitute (unlike the time/cycle columns' own confirmed,
near-uniform "$"-for-"5" pattern) -- tried directly at 2x/3x upscaling too,
which was confirmed to make this specific column pair's own recognition
worse, not better, so no per-column DPI/scale override is applied here.
Left flagged rather than guessed at, same "never guess" reasoning as
POSITION above. Confirmed directly against this module's own real
pipeline run (`occm.normalize_and_validate()`) on the full real sample
file: about half of all rows carry at least one flagged field, the large
majority of those from this ATA/SECTION pair and POSITION -- elevated
next to some sibling ruled-grid OCR modules in this package, but still
soft-validation flags on genuinely hard-to-read small print, not silently
wrong data, and within this project's accepted range for a confirmed-real,
still-recoverable table.
"""
from __future__ import annotations
import re

import numpy as np
from PIL import Image

from sheet_types.occm_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, ocr_words, page_count

NAME = "OCCM List (PN_description Column Headers, Rotated Scan)"

# This module's known source file has no text layer at all (confirmed via
# pdfplumber -- 0 chars on every page), so these SIGNATURES can never fire
# through occm.py's normal pdfplumber head-text match; real detection
# happens via ocr_detect() below. Deliberately left empty, same convention
# as this package's other purely-OCR variants.
SIGNATURES = []

CANONICAL_COLUMNS = [
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "INSTALL_DATE",
    "POSITION",
    "ATA",
    "SECTION",
    "TSN",
    "CSN",
    "TSO",
    "CSO",
    "TSI",
    "CSI",
    # Header metadata -- parsed once (page 1) and stamped on every row.
    "AIRCRAFT_REG",
    "MSN",
    "REPORT_DATE",
    "AIRCRAFT_TSN",
    "AIRCRAFT_CSN",
]

# Confirmed single-glyph OCR substitutions on this file's own small-font
# time/cycle columns -- see module docstring "Known limitation". Scoped to
# TSN/CSN/TSO/CSO/TSI/CSI only (never POSITION, which legitimately mixes
# letters and digits).
_TIME_CHAR_MAP = {
    "$": "5", "S": "5", "¢": "0", "!": "1",
    "(": "", ")": "",
}
_TIME_RULE = {
    "pattern": r"^\d+$",
    "char_map": _TIME_CHAR_MAP,
    "allow_empty": True,
}

_OVERRIDES = {
    # SECTION has no global default -- a 2-3 digit ATA sub-code, confirmed
    # directly across the sampled pages.
    "SECTION": {"pattern": r"^\d{2,3}$"},
    "INSTALL_DATE": {"pattern": r"^\d{2}/\d{2}/\d{4}$"},
    # Compact alphanumeric zone/side code -- confirmed directly to mix
    # digits and letters (e.g. a numeric prefix plus a 1-3 letter suffix
    # code); loose pattern per module docstring "Known limitation".
    "POSITION": {
        "pattern": r"^[A-Z0-9][A-Z0-9\-/]{0,14}$",
        "uppercase": True,
        "allow_empty": True,
    },
    "TSN": _TIME_RULE, "CSN": _TIME_RULE,
    "TSO": _TIME_RULE, "CSO": _TIME_RULE,
    "TSI": _TIME_RULE, "CSI": _TIME_RULE,
    # Header metadata -- each value is a single figure parsed once (page 1)
    # and stamped identically on every row of the file, so a tight pattern
    # here would either flag every single row over one OCR misread in one
    # place, or none at all -- neither is a useful per-row signal. Same
    # reasoning as this package's other header-plus-body OCCM variants.
    "AIRCRAFT_REG": {"allow_empty": True},
    "MSN": {"allow_empty": True},
    "REPORT_DATE": {"allow_empty": True},
    "AIRCRAFT_TSN": {"allow_empty": True},
    "AIRCRAFT_CSN": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_COLUMN_ORDER = ("DESCRIPTION", "PART_NUMBER", "SERIAL_NUMBER", "INSTALL_DATE",
                  "POSITION", "ATA", "SECTION", "TSN", "CSN", "TSO", "CSO",
                  "TSI", "CSI")
# Free text -- the only column whose OCR words are joined WITH a space.
# Every other column is a compact code/number with no legitimate internal
# space (confirmed directly -- a genuine multi-word OCR split of e.g. a PN
# or date would otherwise silently gain a stray space).
_JOIN_WITH_SPACE = {"DESCRIPTION"}

# --- Pixel-grid detection ---------------------------------------------------
_DARK_PIXEL_THRESH = 180
_HEADER_DARKFRAC_THRESH = 0.5
_HEADER_BAND_MIN_HEIGHT = 3
_HEADER_BAND_MAX_TOP_FRAC = 0.20


def _merge_dark_groups(xs, gap: int) -> list[tuple[int, int]]:
    if len(xs) == 0:
        return []
    groups: list[tuple[int, int]] = []
    start = prev = int(xs[0])
    for x in xs[1:]:
        x = int(x)
        if x - prev > gap:
            groups.append((start, prev))
            start = x
        prev = x
    groups.append((start, prev))
    return groups


def _find_header_band(arr: np.ndarray) -> tuple[int, int] | None:
    """Y-span of the column-header row: its own top and bottom ruled
    borders, found in the top fifth of the page (see module docstring
    'Row/column geometry')."""
    h, _ = arr.shape
    darkfrac = (arr < _DARK_PIXEL_THRESH).mean(axis=1)
    band_top = int(h * _HEADER_BAND_MAX_TOP_FRAC)
    ys = np.where(darkfrac[:band_top] > _HEADER_DARKFRAC_THRESH)[0]
    groups = [g for g in _merge_dark_groups(ys, gap=2) if g[1] - g[0] > _HEADER_BAND_MIN_HEIGHT]
    if len(groups) < 2:
        return None
    return groups[0][0], groups[-1][1]


def _col_lines_band(arr: np.ndarray, y0: int, y1: int, thresh: float) -> list[int]:
    band = arr[y0:y1, :]
    darkfrac = (band < _DARK_PIXEL_THRESH).mean(axis=0)
    xs = np.where(darkfrac > thresh)[0]
    return [(g[0] + g[1]) // 2 for g in _merge_dark_groups(xs, gap=6)]


def _robust_col_lines(arr: np.ndarray, header_bottom: int, n_bands: int = 5,
                       band_h: int = 40, gap_between: int = 260,
                       thresh: float = 0.85) -> list[int]:
    """Column-divider X-centers, agreed on by several independent bands
    spaced down the page -- see module docstring 'Row/column geometry' for
    why a single band (or a naive full-height scan) isn't reliable here."""
    all_pts: list[int] = []
    y = header_bottom + 5
    for _ in range(n_bands):
        all_pts.extend(_col_lines_band(arr, y, y + band_h, thresh))
        y += gap_between
    flat = sorted(all_pts)
    clusters: list[list[int]] = []
    for p in flat:
        if clusters and p - clusters[-1][-1] < 15:
            clusters[-1].append(p)
        else:
            clusters.append([p])
    return [int(np.mean(c)) for c in clusters if len(c) >= 3]


def _find_row_lines(arr: np.ndarray, x0: int, x1: int) -> list[int]:
    """Row-divider Y-centers, found from the narrow `chapter` column's own
    X-range (see module docstring 'Row/column geometry')."""
    sub = arr[:, x0:x1]
    darkfrac = (sub < _DARK_PIXEL_THRESH).mean(axis=1)
    ys = np.where(darkfrac > 0.5)[0]
    return [(g[0] + g[1]) // 2 for g in _merge_dark_groups(ys, gap=2)]


_NOISE_TOKEN_RE = re.compile(r"^[|\[\]_\-—–~=<>`\"'*]+$")
_EDGE_STRIP = " _-|[]=~.\"'`*<>§"


def _clean(text: str) -> str:
    return text.strip(_EDGE_STRIP)


async def _rotate_upright(pdf_path: str, page_index: int, dpi: int):
    """Render one page and correct the sideways-storage artifact described
    in the module docstring -- only rotates when the render itself is
    portrait-shaped (`width < height`), the confirmed signature of this
    report's known sideways-stored files."""
    img = await render_page(pdf_path, page_index, dpi=dpi)
    w, h = img.size
    if w < h:
        img = img.rotate(-90, expand=True)
    return img


async def _ocr_page_rows(img: Image.Image) -> list[dict]:
    arr = np.array(img.convert("L"))
    band = _find_header_band(arr)
    if band is None:
        return []
    _, header_bottom = band
    col_lines = _robust_col_lines(arr, header_bottom)
    if len(col_lines) != len(_COLUMN_ORDER) + 1:
        return []
    ata_idx = _COLUMN_ORDER.index("ATA")
    x0c, x1c = col_lines[ata_idx] + 8, col_lines[ata_idx + 1] - 8
    row_lines = _find_row_lines(arr, x0c, x1c)
    if len(row_lines) < 2:
        return []

    row_bands = list(zip(row_lines[:-1], row_lines[1:]))
    col_bounds = list(zip(col_lines[:-1], col_lines[1:]))
    row_tops = [b[0] for b in row_bands]
    row_bots = [b[1] for b in row_bands]

    records = [dict.fromkeys(_COLUMN_ORDER, "") for _ in row_bands]
    for name, (cx0, cx1) in zip(_COLUMN_ORDER, col_bounds):
        x0, x1 = cx0 + 4, cx1 - 4
        if x1 - x0 < 5:
            continue
        crop = img.crop((x0, row_tops[0] + 2, x1, row_bots[-1] - 1))
        words = await ocr_words(crop, psm=6, min_conf=-1)
        buckets: list[list[tuple[float, str]]] = [[] for _ in row_bands]
        for wd in words:
            text = str(wd.get("text", "")).strip()
            if not text or _NOISE_TOKEN_RE.match(text):
                continue
            word_top = row_tops[0] + 2 + wd["top"]
            word_center = word_top + wd.get("height", 0) / 2
            best_i, best_d = None, float("inf")
            for i, (rt, rb) in enumerate(row_bands):
                d = abs(word_center - (rt + rb) / 2)
                if d < best_d:
                    best_i, best_d = i, d
            if best_i is not None:
                buckets[best_i].append((wd["left"], text))
        sep = " " if name in _JOIN_WITH_SPACE else ""
        for i, toks in enumerate(buckets):
            toks.sort(key=lambda t: t[0])
            records[i][name] = _clean(sep.join(t for _, t in toks))

    out = []
    # Row 0 is the column-header row itself (its own labels get bucketed
    # like any other row by this same per-column pass) -- confirmed
    # directly, always the first row band on every sampled page -- so it
    # is dropped rather than emitted as a data record.
    for i, rec in enumerate(records):
        if i == 0:
            continue
        if not (rec["DESCRIPTION"] or rec["PART_NUMBER"] or rec["SERIAL_NUMBER"]):
            continue
        out.append(rec)
    return out


_AC_RE = re.compile(r"A/?C\s+(\S+)\s+MSN\s+(\d+)", re.IGNORECASE)
_DATE_RE = re.compile(r"\bDate\s+(\S+)", re.IGNORECASE)
_AC_TSN_RE = re.compile(r"\bTSN\s+([\d.]+)", re.IGNORECASE)
_AC_CSN_RE = re.compile(r"\bCSN\s+([\d.]+)", re.IGNORECASE)

_HEADER_FIELDS = ("AIRCRAFT_REG", "MSN", "REPORT_DATE", "AIRCRAFT_TSN", "AIRCRAFT_CSN")


async def _parse_header_meta(img: Image.Image) -> dict:
    """Page-1 label:value box (A/C <reg> MSN <n> / Date <d> / TSN <n> /
    CSN <n>), OCR'd as a single crop -- confirmed directly to read cleanly
    at this psm/crop combination on the real sample file's first page."""
    meta = {k: "" for k in _HEADER_FIELDS}
    w, h = img.size
    crop = img.crop((int(w * 0.42), int(h * 0.02), int(w * 0.62), int(h * 0.135)))
    text = await ocr_text(crop, psm=4)
    m = _AC_RE.search(text)
    if m:
        meta["AIRCRAFT_REG"], meta["MSN"] = m.group(1).upper(), m.group(2)
    m = _DATE_RE.search(text)
    if m:
        meta["REPORT_DATE"] = m.group(1)
    m = _AC_TSN_RE.search(text)
    if m:
        meta["AIRCRAFT_TSN"] = m.group(1)
    m = _AC_CSN_RE.search(text)
    if m:
        meta["AIRCRAFT_CSN"] = m.group(1)
    return meta


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback (see
    sheet_types/occm.py) -- this variant's known source file has no text
    layer at all, so it can never be found through the normal pdfplumber
    head-text match.

    Requires the report's own bare title ("OCCM LIST") together with ITS
    OWN three column-header labels -- "PN description", "installed date"
    and "installed position" (matched with underscore/space collapsed,
    since this report's snake_case header labels were confirmed directly
    to sometimes OCR the joining underscore as a plain space depending on
    render DPI, e.g. "PN_description" vs "PN description") -- each read
    from its own narrow per-column crop (a whole-row-width single OCR pass
    was confirmed directly to garble this header band -- see module
    docstring's 'Row/column geometry' for the same wide/thin-crop effect
    on this file's data rows). Checked directly (grep across every
    SIGNATURES list in sheet_types/{occm,ht,llp}.py and every existing
    occm_variants/ht_variants/llp_variants file, plus every module's own
    ocr_detect() anchor text): a bare "OCCM LIST" title is already known to
    be shared by several sibling "OCCM LIST"-titled variants in this
    package (see e.g. `occm_list_current_fh_fc_ruled_grid.py`'s own
    collision analysis), so it is never used alone here. Combined with
    "INSTALLED DATE": `occm_components_status_ruled_grid.py`'s own anchor
    requires the contiguous substring "INSTALL DATE" (no "ED"), which is
    NOT a substring of "INSTALLED DATE" (the extra "ED" breaks the
    contiguous match), so the two cannot collide.
    `aircraft_kardex_status_broken_font_scanned.py` uses "PN_DESCRIPTION"
    only as an internal CANONICAL_COLUMNS name, never as its own
    SIGNATURES/ocr_detect anchor text (that module's own anchor is
    "AMASIS" + "REPORT KARDEX BY AIRCRAFT" instead), so no collision
    there either."""
    try:
        img = await _rotate_upright(pdf_path, 0, dpi=400)
        w, h = img.size
        arr = np.array(img.convert("L"))
        band = _find_header_band(arr)
        if band is None:
            return False
        top, bottom = band
        col_lines = _robust_col_lines(arr, bottom)
        if len(col_lines) < 6:
            return False

        title_crop = img.crop((0, 0, w, max(0, top - 5)))
        title_text = (await ocr_text(title_crop, psm=6)).upper()
        if "OCCM LIST" not in " ".join(title_text.split()):
            return False

        desc_crop = img.crop((col_lines[0] + 3, max(0, top - 10), col_lines[1] - 3, bottom + 40))
        date_crop = img.crop((col_lines[3] + 3, max(0, top - 20), col_lines[4] - 3, bottom + 20))
        pos_crop = img.crop((col_lines[4] + 3, max(0, top - 20), col_lines[5] - 3, bottom + 20))
        desc_text = (await ocr_text(desc_crop, psm=6)).upper()
        date_text = (await ocr_text(date_crop, psm=6)).upper()
        pos_text = (await ocr_text(pos_crop, psm=6)).upper()

        def _norm(t: str) -> str:
            return " ".join(t.replace("_", " ").split())

        return ("PN DESCRIPTION" in _norm(desc_text)
                and "INSTALLED DATE" in _norm(date_text)
                and "INSTALLED POSITION" in _norm(pos_text))
    except Exception:
        return False


async def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    header_meta = {k: "" for k in _HEADER_FIELDS}
    n_pages = await page_count(pdf_path)
    for page_index in range(n_pages):
        # 400 DPI: confirmed directly to recover the small time/cycle
        # column font meaningfully more reliably than lower DPIs tried,
        # at an acceptable per-page OCR cost (same tradeoff as this
        # package's other small-font ruled-grid OCR variants).
        img = await _rotate_upright(pdf_path, page_index, dpi=400)
        if page_index == 0:
            header_meta = await _parse_header_meta(img)
        page_records = await _ocr_page_rows(img)
        for rec in page_records:
            rec.update(header_meta)
            rec["_page"] = page_index + 1
            records.append(rec)
    return records
