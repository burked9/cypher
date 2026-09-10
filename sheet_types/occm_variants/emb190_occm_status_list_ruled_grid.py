"""EMB-190 "OC/CM Status List" -- plain 9-column ruled grid, scanned, no
text layer, OCR required throughout.

Confirmed directly on a real sample file: 0 extractable characters on
every page via pdfplumber (a straight scan, no text layer at all).
Page 1 carries a title block::

    EMB-190
    (Ref. <ref code>)

    OC/CM Status List

...followed immediately by the data grid; every later page repeats the
same 9-column ruled grid with no title block at all (confirmed directly:
page 1's own title-band anchor text is absent from every later page
sampled). Column-header row (page 1 only, shaded band; confirmed directly,
including its own two-row "COMPONENT" group-label band above the trailing
four numeric columns)::

    ATA | COMPONENT P/N | COMPONENT DESCRIPTION | POSITION | Install Date | TSI | CSI | TSN | CSN

A data row, tokens in column order: ATA (2-digit chapter), PART_NUMBER,
DESCRIPTION (free text, sometimes wraps to two visual lines within one
ruled row -- still a single cell, not a second row: confirmed directly, no
internal ruling separates the two visual lines), POSITION (a short
zone/side/instance code -- confirmed directly to range from a bare 1-3
char code ("LH", "1", "001") to a multi-word compound ("RH WING", "CENT
FUS", "INB LH E"), or genuinely blank on some rows, e.g. the VHF antenna
row on the real sample file), INSTALL_DATE (M/D/YYYY), then four numeric
counters TSI/CSI/TSN/CSN (per the column-header's own group label
"COMPONENT" spanning all four -- times/cycles since install and total
times/cycles; occasionally the literal placeholder "UNK" in place of a
number, confirmed directly).

Row/column geometry -- pixel-ruling detection via plain numpy (no cv2
dependency; this must also run under Pyodide, which has no native-code
image library other than what `shared/ocr_bridge.py` already bridges),
same technique as `occm_components_status_ruled_grid.py` in this same
package. Both row boundaries (horizontal rules) and column boundaries
(vertical rules) are found fresh from each page's own pixel data rather
than hardcoded as fixed fractions of the page box: confirmed directly, the
real sample file's table is NOT positioned at a consistent x-offset from
page to page (the last page's own table spans a visibly wider, differently
-offset x-range than page 1's -- confirmed directly by comparing detected
column-divider positions between the two), so a per-page fresh detection
is required, not a one-time detection reused across every page.

Column-divider detection tries successive candidate horizontal-rule
"anchor" bands from the top of the page down (skipping the title-block
text on page 1, which also registers a dark run but yields fewer than the
expected 10 column dividers when sampled) rather than assuming the first
dark horizontal band is the real header/column-divider row, since only
page 1 has a title block ahead of the real grid. A near-duplicate pair of
adjacent divider lines (confirmed directly: the source table renders a
double-ruled border between the PART_NUMBER and DESCRIPTION columns,
~6-26px apart depending on page) is merged into one column boundary via a
wide merge-gap, or the column count would come out one high and silently
misalign every column from DESCRIPTION onward.

Per-column OCR uses one whole-column-height `ocr_words()` call per column
per page (not one call per cell): confirmed directly to be both faster and
more accurate here than per-cell calls, since a blank POSITION cell (see
above) would otherwise silently shift a naive per-column line-index
alignment out of sync with its sibling columns -- each returned word is
instead bucketed into the row band (from the row-ruling detection) whose
Y-range center is nearest to the word's own vertical center, so an empty
cell in one column never misaligns that row's other columns. `psm=11`
(sparse text, no layout assumption) is used rather than `psm=6` (assume a
single uniform block): confirmed directly, side by side on the real sample
file, `psm=6` on a tall, mostly-blank single-token column (POSITION, ATA)
hallucinates long runs of border/dash noise across the whole column height
instead of returning the isolated short words actually present, while
`psm=11` recovers them correctly; `psm=11` was confirmed to work equally
well on the wider, denser DESCRIPTION column too, so one `psm` setting is
used for every column rather than varying it per column. Each column crop
insets a fixed margin in from its own detected divider lines on both
sides (and top/bottom) before OCR: confirmed directly, including even a
sliver of the divider ruling itself in the crop (a ~2-4px anti-aliased
line) causes Tesseract to return nothing at all for that whole column
rather than degraded text.

A pseudo-row consisting of the column-header labels themselves (page 1
only) is dropped rather than emitted as a data record (checked for the
literal word "DESCRIPTION" appearing in that row's own DESCRIPTION/
PART_NUMBER/ATA cells, which never occurs in genuine part-description
text). A row with no content recovered in ATA, PART_NUMBER, or
DESCRIPTION at all is also dropped, same convention as
`occm_components_status_ruled_grid.py`'s own blank-separator-row handling.

Known limitation, confirmed directly against the real sample file and its
own real pipeline run (`occm.normalize_and_validate()`): roughly three in
four rows (803 of 1059 real extracted rows, all 25 pages) carry at least
one flagged field, and the ATA column is by far the dominant cause (902 of
those flags). Root cause confirmed directly by rendering the ATA column at
high zoom (up to 800 DPI native re-render, well past this module's own
400 DPI extraction pass): the source scan's ATA digits themselves render
as a visibly blocky, low-effective-resolution glyph in this narrow column
even at that zoom -- re-rendering at higher DPI or upscaling the crop
brings no new real detail, it just upsamples the same blockiness, so
Tesseract frequently resolves only one of the two ATA digits correctly (a
bare "2" instead of "23", or a similarly-shaped wrong second digit). A
digit-only OCR whitelist was tried directly as a possible fix and
rejected: it does make Tesseract return a plausible-looking two-digit
value far more often, but confirmed directly against real rows with a
known ground-truth ATA, it does so by force-fitting a wrong second digit
into range (e.g. reading a real "23" as "20") rather than by resolving the
character correctly -- silently plausible-but-wrong data, which is worse
than the current, visibly-flagged behaviour, per this project's "never
guess a wrong split, wrong data is worse than missing data" convention
(see `shared/aviation_rules.py`). This is the same category of confirmed,
accepted degradation as `occm_components_status_ruled_grid.py`'s own
documented POSITION-column small-font limitation in this same package --
just concentrated in ATA (present on every row) rather than spread across
a field that's sometimes blank, hence the higher overall flag share here.
PART_NUMBER and DESCRIPTION were confirmed directly to OCR far more
reliably than ATA across the sample.

OCR on this scan quality also frequently drops the "/" separators in
INSTALL_DATE (or misreads other characters in PART_NUMBER), and
POSITION's own compound codes (e.g. "RH WING") are sometimes read as only
their first token. INSTALL_DATE, POSITION, TSI, CSI, TSN and CSN are
therefore validated with loose, allow-empty rules rather than strict
ones -- forcing a strict pattern on fields this noisy would flag OCR noise
rather than signal.
"""
from __future__ import annotations
import re

import numpy as np
from PIL import Image

from sheet_types.occm_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, ocr_words, page_count

NAME = "EMB-190 OC/CM Status List (Ruled Grid, Scanned)"

# This module's known source file has no text layer at all (confirmed via
# pdfplumber -- 0 chars on every page), so these SIGNATURES can never fire
# through occm.py's normal pdfplumber head-text match; real detection
# happens via ocr_detect() below. Kept anyway, per this project's
# convention, as a documented anchor / safety net for any future
# born-digital re-export of the same template.
#
# "OC/CM STATUS LIST" (with the slash, no "COMPONENTS") is checked for
# collisions directly (grep across every SIGNATURES list in
# sheet_types/{occm,ht,llp}.py and every existing occm_variants/
# ht_variants/llp_variants file): occm.py's own top-level "OC/CM STATUS"
# entry (routing to oc_cm_status_report.py) is a prefix substring of this
# phrase, but that module has no `ocr_detect()` of its own, so it can
# never fire through the router's OCR-fallback loop this module relies on
# (only born-digital pdfplumber matching, which this scanned-only source
# file never reaches). Every other sibling phrase containing "STATUS
# LIST" in this package (occm_status_list.py's "OCCM COMPONENTS STATUS
# LIST", msn_components_status_list.py's "OC&CM COMPONENTS STATUS LIST",
# occm_status_list_type_model_header.py's "OCCM STATUS LIST") has the word
# "OCCM" (no slash) or "COMPONENTS" in it -- neither is a substring of
# (nor contains) this module's own slash-bearing, COMPONENTS-free phrase.
SIGNATURES = [
    "OC/CM STATUS LIST",
]

CANONICAL_COLUMNS = [
    "ATA",
    "PART_NUMBER",
    "DESCRIPTION",
    "POSITION",
    "INSTALL_DATE",
    "TSI",
    "CSI",
    "TSN",
    "CSN",
]

_OVERRIDES = {
    # Compact zone/side/instance code -- confirmed directly to range from a
    # bare 1-3 char code up to a multi-word compound, or genuinely blank on
    # some rows (see module docstring). Loose pattern rather than a strict
    # closed set: a strict pattern here would flag noise, not signal, on
    # this scan quality.
    "POSITION": {
        "pattern": r"^[A-Z0-9][A-Z0-9 /\-]{0,20}$",
        "uppercase": True,
        "allow_empty": True,
    },
    # Real dates on this file are M/D/YYYY, but OCR frequently drops the
    # "/" separators entirely on this scan quality (confirmed directly) --
    # no pattern enforced, so a garbled-but-present read is preserved
    # verbatim (for visual cross-check against the source page) rather
    # than flagged as noise.
    "INSTALL_DATE": {"allow_empty": True},
    # Free counters -- digits or the literal placeholder "UNK" (see module
    # docstring); no pattern enforced for the same reason as INSTALL_DATE.
    "TSI": {"allow_empty": True},
    "CSI": {"allow_empty": True},
    "TSN": {"allow_empty": True},
    "CSN": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# --- Pixel-grid detection ---------------------------------------------------
_DARK_PIXEL_THRESH = 180
_LINE_MERGE_GAP = 3
# Column-divider double-ruling merge gap -- wide enough to merge the
# confirmed ~6-26px near-duplicate pair between PART_NUMBER and
# DESCRIPTION (see module docstring) into a single boundary.
_COL_LINE_MERGE_GAP = 30
_HEADER_CANDIDATE_THRESH = 0.15
_COL_SCAN_HALF_HEIGHT = 100
_COL_DARKFRAC_THRESH = 0.5
_ROW_DARKFRAC_THRESH = 0.85

_COLUMN_ORDER = ("ATA", "PART_NUMBER", "DESCRIPTION", "POSITION",
                  "INSTALL_DATE", "TSI", "CSI", "TSN", "CSN")


def _merge_dark_groups(ys: np.ndarray, gap: int) -> list[tuple[int, int]]:
    if len(ys) == 0:
        return []
    groups: list[tuple[int, int]] = []
    start = prev = int(ys[0])
    for y in ys[1:]:
        y = int(y)
        if y - prev > gap:
            groups.append((start, prev))
            start = y
        prev = y
    groups.append((start, prev))
    return groups


def _find_grid(arr: np.ndarray) -> tuple[list[int], list[int]] | None:
    """Find this page's own column-divider x-centers and row-divider
    y-centers fresh from its pixel data (see module docstring "Row/column
    geometry"). Tries successive horizontal dark-run candidates as the
    column-scan anchor band, from the top of the page down, since only
    page 1 has a title block ahead of the real grid (which registers its
    own dark run but never yields >=10 column dividers when sampled)."""
    h, w = arr.shape
    darkfrac_full = (arr < _DARK_PIXEL_THRESH).mean(axis=1)
    cand = np.where(darkfrac_full > _HEADER_CANDIDATE_THRESH)[0]
    if len(cand) == 0:
        return None
    for g0, _g1 in _merge_dark_groups(cand, gap=5):
        y0, y1 = max(0, g0 - _COL_SCAN_HALF_HEIGHT), g0 + _COL_SCAN_HALF_HEIGHT
        band = arr[y0:y1, :]
        darkfrac_col = (band < _DARK_PIXEL_THRESH).mean(axis=0)
        xs = np.where(darkfrac_col > _COL_DARKFRAC_THRESH)[0]
        col_groups = _merge_dark_groups(xs, gap=_COL_LINE_MERGE_GAP)
        col_lines = [(a + b) // 2 for a, b in col_groups]
        if len(col_lines) < len(_COLUMN_ORDER) + 1:
            continue
        x0, x1 = col_lines[0], col_lines[-1]
        sub = arr[:, x0 + 3:x1 - 3]
        darkfrac_row = (sub < _DARK_PIXEL_THRESH).mean(axis=1)
        ys = np.where(darkfrac_row > _ROW_DARKFRAC_THRESH)[0]
        row_groups = _merge_dark_groups(ys, gap=_LINE_MERGE_GAP)
        row_lines = [(a + b) // 2 for a, b in row_groups]
        if len(row_lines) < 3:
            continue
        return col_lines[:len(_COLUMN_ORDER) + 1], row_lines
    return None


_EDGE_STRIP = " _-|[]=~.\"'`*"
_XINSET = 16
_YINSET = 8


def _clean(text: str) -> str:
    return text.strip(_EDGE_STRIP).strip()


async def _ocr_page_rows(img: Image.Image) -> list[dict]:
    arr = np.array(img.convert("L"))
    grid = _find_grid(arr)
    if grid is None:
        return []
    col_lines, row_lines = grid

    col_bounds = list(zip(col_lines[:-1], col_lines[1:]))
    row_bands = list(zip(row_lines[:-1], row_lines[1:]))
    records = [dict.fromkeys(_COLUMN_ORDER, "") for _ in row_bands]
    row_tops = [b[0] for b in row_bands]
    row_bots = [b[1] for b in row_bands]

    for name, (cx0, cx1) in zip(_COLUMN_ORDER, col_bounds):
        x0, x1 = cx0 + _XINSET, cx1 - _XINSET
        if x1 - x0 < 5:
            x0, x1 = cx0 + 2, cx1 - 2
        crop = img.crop((x0, row_tops[0] + _YINSET, x1, row_bots[-1] - _YINSET // 2))
        words = await ocr_words(crop, psm=11, min_conf=-1)
        buckets: list[list[tuple[float, str]]] = [[] for _ in row_bands]
        for wd in words:
            text = str(wd.get("text", "")).strip()
            if not text:
                continue
            word_top = row_tops[0] + _YINSET + wd["top"]
            word_center = word_top + wd.get("height", 0) / 2
            best_i, best_d = None, float("inf")
            for i, (rt, rb) in enumerate(row_bands):
                center = (rt + rb) / 2
                d = abs(word_center - center)
                if d < best_d:
                    best_i, best_d = i, d
            if best_i is not None:
                buckets[best_i].append((wd["left"], text))
        for i, toks in enumerate(buckets):
            toks.sort(key=lambda t: t[0])
            records[i][name] = _clean(" ".join(t for _, t in toks))

    out = []
    for rec in records:
        blob = f"{rec['ATA']} {rec['PART_NUMBER']} {rec['DESCRIPTION']}".upper()
        # Column-header pseudo-row (page 1 only) -- see module docstring.
        if "DESCRIPTION" in blob:
            continue
        if not (rec["ATA"] or rec["PART_NUMBER"] or rec["DESCRIPTION"]):
            continue
        out.append(rec)
    return out


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback (see
    sheet_types/occm.py) -- this variant's known source file has no text
    layer at all, so it can never be found through the normal pdfplumber
    head-text match.

    Requires BOTH the aircraft-model title line ("EMB-190") and the
    report's own subtitle line ("OC/CM Status List") in the same
    top-of-page crop -- checked directly (grep across every SIGNATURES
    list in sheet_types/{occm,ht,llp}.py and every existing
    occm_variants/ht_variants/llp_variants module, plus every module's own
    ocr_detect() anchor text): no other module's own SIGNATURES/
    ocr_detect anchor requires this exact combination, and neither
    "EMB-190" nor "OC/CM STATUS LIST" appears standalone as any other
    module's own anchor phrase either.
    """
    try:
        img = await render_page(pdf_path, 0, dpi=300)
        w, h = img.size
        title_crop = img.crop((0, 0, w, int(h * 0.20)))
        text = (await ocr_text(title_crop, psm=6)).upper()
        normed = " ".join(text.split())
        return "EMB-190" in normed and "STATUS LIST" in normed and "OC/CM" in normed
    except Exception:
        return False


async def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    n_pages = await page_count(pdf_path)
    for page_index in range(n_pages):
        try:
            img = await render_page(pdf_path, page_index, dpi=400)
            page_records = await _ocr_page_rows(img)
        except Exception:
            continue
        for rec in page_records:
            rec["_page"] = page_index + 1
            records.append(rec)
    return records
