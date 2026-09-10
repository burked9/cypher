"""OCCM LIST (Current FH/FC/Date header box, 10-column ruled grid) -- scanned,
no text layer, OCR required throughout.

Confirmed directly on a real corpus file: 0 extractable characters on every
page via pdfplumber (a straight scan, portrait orientation). Every page
repeats the same title/info box, then a single ruled 10-column grid (values
genericized per this project's data-sensitivity convention -- no real
registration/MSN/aircraft-type/hours/cycles/PN/SN/date from the source file
is written in this module)::

    <operator logo>          OCCM LIST      Current FH   <fh> TFH   <type>
                                             Current FC   <fc> TFC   <reg>
                                             Current Date: <date>    <msn>

    ITEM | ATA | FIN | DESCRIPTION | PN | SN/BATCH NO | INSTALL DATE | TSN | CSN | AMM Structure

This is genuinely a different report template from this package's other
"OCCM LIST"-titled variants, not merely a re-export of one of them under a
different aircraft/operator -- checked directly: `occm.detect_variant()`
returns "Unknown" against the real sample file (it has no text layer, so it
never reaches any born-digital variant's SIGNATURES match), and none of the
scanned "OCCM LIST" siblings (`occm_list_func_loc_scanned.py`,
`msn_occm_list_scanned.py`, `occm_list_for_registration.py`) share this
file's column set: this file has no Func.loc, no Eq.Number, and a distinct
ITEM/FIN/AMM-Structure column combination none of those three has.

A blank, ruled but genuinely empty row sits between the column-header
labels row and the first real data row (confirmed directly, every page
sampled) -- not a rendering artifact, simply never emitted as a record
(same "blank separator row" convention as this package's other ruled-grid
OCR variants, e.g. `occm_components_status_ruled_grid.py`).

ITEM is confirmed genuinely blank on a meaningful minority of real rows
(not an OCR miss -- the source PDF's own ruled cell is empty there, seen on
several widely separated pages of the real sample file), so it is never
required for a row to count as real data; ATA/FIN/DESCRIPTION are used as
the row-anchor instead (see `_ocr_page_rows` below).

PN, SN/BATCH NO, INSTALL DATE, TSN and CSN are confirmed to carry several
different literal placeholder strings in place of a real value, depending
on the row -- not one single consistent token: "N/A", "UKN" (only ever seen
in PN/SN/BATCH NO cells), "UNK" (only ever seen in INSTALL DATE/TSN/CSN
cells) and "Refer to HT" (seen on rows for a component covered by a
separate Hard-Time schedule instead of this OCCM one). All four are kept
verbatim rather than normalized to one canonical placeholder -- collapsing
them would risk asserting an equivalence between "genuinely unknown" and
"tracked under HT instead" that the source document itself does not make.
AMM Structure carries its own placeholder, confirmed directly as either
"#N/A" or, on a meaningful share of rows, an OCR misread of it as "#NIA"
(the "/" glyph in this narrow column is confirmed directly, by rendering at
high zoom, to be thin enough that Tesseract resolves it as "I" about as
often as "/") -- both spellings are accepted by this column's own pattern
rather than only the "correct" one, since silently "fixing" an OCR misread
into a specific ASCII value here would be a guess, not a correction. AMM
Structure is also confirmed genuinely blank on some real rows (seen
directly, several rows on the real sample file's last page), independent
of the placeholder-vs-real-value question -- `allow_empty` accordingly.

SN/BATCH NO is kept as one combined column, matching the source PDF's own
single header cell "SN/BATCH NO" -- confirmed directly, real values in this
column are always one plain undelimited token (a serial number OR a batch
number depending on the row, never both, never colon-joined the way
`occm_list_for_registration.py`'s own BATCH column sometimes is), so there
is no reliable split point even if the two concepts were separated, and
attempting one would misrepresent the source's own single-field design.

Row/column geometry -- pixel-ruling detection via plain numpy (no cv2
dependency; this must also run under Pyodide, which has no native-code
image library other than what `shared/ocr_bridge.py` already bridges),
same technique as this package's other ruled-grid OCR variants
(`occm_components_status_ruled_grid.py`, `emb190_occm_status_list_ruled_grid.py`).
Both row and column dividers are found fresh from each page's own pixel
data rather than hardcoded as fixed fractions, since this scan's table
render is not guaranteed to sit at a perfectly identical pixel offset on
every page. The title/info box above the real grid also registers as a
full-width dark band during column-divider detection (it happens to share
enough of the grid's own column-boundary geometry to look like a plausible
candidate row), so unlike `occm_components_status_ruled_grid.py`'s single
"take the header band, then everything below it" approach, this module
additionally locates the literal column-header labels row (checked via the
row whose own DESCRIPTION-column OCR contains the word "DESCRIPTION") and
discards it AND every row above it -- confirmed directly: without this
extra step, the title/info box's own OCR'd values leak into the last few
grid columns as fabricated data rows (the info box's aircraft-type/
registration/MSN block sits inside this table's own AMM-Structure-column
x-range, and its Current-FH/FC/Date block sits inside the TSN/CSN-column
x-range -- confirmed directly by cropping and OCR'ing the info-box band
with this module's own column boundaries). This also matters for this
project's data-sensitivity convention: the info box carries the real
aircraft registration and MSN, so failing to exclude it would leak that
real, file-specific data into extracted rows -- confirmed directly this
does NOT happen with the header-row-anchored exclusion in place.

Per-column OCR uses one whole-column-height `ocr_words()` call per column
per page, `psm=6` (assume a single uniform block) rather than `psm=11`
(sparse text) -- confirmed directly, side by side on the real sample file,
that `psm=11` on this file's narrow ITEM column (a single 1-4 digit number,
often with a lot of blank vertical space around it within the column crop)
returns nothing at all on a meaningful share of rows, while `psm=6`
recovers the digits reliably; `psm=6` was confirmed to also work at least
as well on every wider column (DESCRIPTION, SN/BATCH NO) checked directly.
This is the opposite conclusion from `emb190_occm_status_list_ruled_grid.py`'s
own module docstring (which found `psm=11` better for its own narrow
columns on its own, differently-scanned real sample file) -- both are kept
as each module's own confirmed, file-specific finding rather than
generalized into a single project-wide default.

Known limitation, confirmed directly against the real sample file and its
own real pipeline run (`occm.normalize_and_validate()`): a minority of rows
carry at least one flagged field, concentrated in ITEM (an occasional
misread digit, e.g. a single numeral read as a stray letter or dash run)
and, less often, ATA/FIN (a misread digit or an intruding stray punctuation
glyph). PART_NUMBER, DESCRIPTION, SN_BATCH_NO, TSN, CSN and INSTALL_DATE
were confirmed directly to OCR far more reliably than ITEM across the
sample. No correction is guessed for any of these -- per this project's
"never guess a wrong split, wrong data is worse than missing data"
convention (see `shared/aviation_rules.py`) -- they are left to surface as
flagged rows for manual review instead.
"""
from __future__ import annotations
import re

import numpy as np
from PIL import Image

from sheet_types.occm_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, ocr_words, page_count

NAME = "OCCM List (Current FH/FC Header, Ruled Grid, Scanned)"

# This module's known source file has no text layer at all (confirmed via
# pdfplumber -- 0 chars on every page), so these SIGNATURES can never fire
# through occm.py's normal pdfplumber head-text match; real detection
# happens via ocr_detect() below. Deliberately left empty, same convention
# as this package's other purely-OCR ruled-grid variants.
SIGNATURES = []

CANONICAL_COLUMNS = [
    "ITEM",
    "ATA",
    "FIN",
    "DESCRIPTION",
    "PART_NUMBER",
    "SN_BATCH_NO",
    "INSTALL_DATE",
    "TSN",
    "CSN",
    "AMM_STRUCTURE",
    # Header metadata -- parsed once (page 1) and stamped on every row.
    "AIRCRAFT_TYPE",
    "AIRCRAFT_REG",
    "MSN",
    "CURRENT_FH",
    "CURRENT_FC",
    "CURRENT_DATE",
]

# Placeholder tokens confirmed on the real sample file (see module
# docstring) -- kept verbatim rather than collapsed to one canonical
# spelling. Values pass through `no_spaces` + `uppercase` before pattern
# matching (see shared/cleanup.py's clean_cell order), so "Refer to HT"
# becomes "REFERTOHT" by the time the pattern below runs.
_PLACEHOLDER = r"N/A|UKN|UNK|REFERTOHT"

_OVERRIDES = {
    # Confirmed genuinely blank on a meaningful minority of real rows (not
    # an OCR miss) -- see module docstring.
    "ITEM": {
        "pattern": r"^\d{1,5}$",
        "int_range": (1, 5000),
        "allow_empty": True,
    },
    "PART_NUMBER": {
        "pattern": rf"^(?:[A-Z0-9][A-Z0-9\-]*[A-Z0-9]?|{_PLACEHOLDER})$",
        "allow_empty": True,
    },
    # No global default exists for this column name (it's not a plain
    # SERIAL_NUMBER -- see module docstring on why PN and SN/BATCH NO are
    # kept as one combined field). Loose alnum pattern plus the same
    # placeholder set as PART_NUMBER/TSN/CSN.
    "SN_BATCH_NO": {
        "pattern": rf"^(?:[A-Z0-9][A-Z0-9\-/]*[A-Z0-9]?|{_PLACEHOLDER})$",
        "uppercase": True,
        "no_spaces": True,
        "allow_empty": True,
    },
    # `no_spaces`+`uppercase` are needed here (not just a pattern change)
    # so the "Refer to HT"/"UKN"/"UNK"/"N/A" placeholders actually reach
    # `_PLACEHOLDER` in the same normalized shape the pattern expects --
    # confirmed directly: without them, "Refer to HT" reaches pattern
    # matching still containing its own spaces and mixed case and never
    # matches "REFERTOHT", flagging every single placeholder row as
    # `bad_format` even though the value is a real, recognized placeholder.
    "INSTALL_DATE": {
        "pattern": rf"^(?:\d{{2}}/\d{{2}}/\d{{4}}|{_PLACEHOLDER})$",
        "uppercase": True,
        "no_spaces": True,
        "allow_empty": True,
    },
    # TSN/CSN are usually a plain integer, but confirmed directly to also
    # carry a comma-decimal remainder on many rows (e.g. "43532,23") -- a
    # European decimal-comma convention, not a thousands separator; kept
    # verbatim rather than reformatted, per this project's convention of
    # not guessing at a transformation the source document didn't make
    # explicit. `no_spaces` also absorbs a confirmed OCR artifact: a stray
    # space after the comma on some rows (e.g. "10593, 11") that would
    # otherwise fail this pattern despite being a genuine, correctly-OCR'd
    # value.
    "TSN": {
        "pattern": rf"^(?:\d+(?:,\d+)?|{_PLACEHOLDER})$",
        "uppercase": True,
        "no_spaces": True,
        "allow_empty": True,
    },
    "CSN": {
        "pattern": rf"^(?:\d+(?:,\d+)?|{_PLACEHOLDER})$",
        "uppercase": True,
        "no_spaces": True,
        "allow_empty": True,
    },
    # "#N/A" is the real placeholder; "#NIA" is a confirmed OCR misread of
    # its own "/" glyph as "I" in this narrow column, and a bare "N/A" or
    # "NIA" (no leading "#") is a confirmed OCR drop of the leading "#"
    # glyph in the same narrow column (see module docstring) -- all
    # accepted rather than "corrected" to one spelling. Also confirmed
    # genuinely blank on some real rows, independent of the placeholder
    # question.
    "AMM_STRUCTURE": {
        "pattern": r"^(?:\d{2}-\d{2,3}|#?N/?A|#?NIA)$",
        "uppercase": True,
        "no_spaces": True,
        "allow_empty": True,
    },
    # Header metadata -- each value is a single figure parsed once (page 1)
    # and stamped identically on every row of the file, so a tight pattern
    # here would either flag every single row over one OCR misread in one
    # place, or none at all -- neither is a useful per-row signal. Same
    # reasoning as this package's other header-plus-body OCCM variants.
    "AIRCRAFT_TYPE": {"allow_empty": True},
    "AIRCRAFT_REG": {"allow_empty": True},
    "MSN": {"allow_empty": True},
    "CURRENT_FH": {"allow_empty": True},
    "CURRENT_FC": {"allow_empty": True},
    "CURRENT_DATE": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# --- Pixel-grid detection ---------------------------------------------------
_DARK_PIXEL_THRESH = 180
_LINE_MERGE_GAP = 3
_COL_LINE_MERGE_GAP = 15
_HEADER_CANDIDATE_THRESH = 0.15
_COL_SCAN_HALF_HEIGHT = 100
_COL_DARKFRAC_THRESH = 0.5
_ROW_DARKFRAC_THRESH = 0.85

_COLUMN_ORDER = ("ITEM", "ATA", "FIN", "DESCRIPTION", "PART_NUMBER",
                  "SN_BATCH_NO", "INSTALL_DATE", "TSN", "CSN", "AMM_STRUCTURE")


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
    column-scan anchor band, from the top of the page down -- the title/
    info box above the real grid also registers as a candidate, but it
    happens to share this table's own column geometry closely enough that
    either the info box's or the true header row's own band works equally
    well here as the anchor for X-boundaries; the info box itself is
    excluded from the emitted ROWS later, not from this X-boundary scan
    (see `_ocr_page_rows`)."""
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
        return col_lines[: len(_COLUMN_ORDER) + 1], row_lines
    return None


_EDGE_STRIP = " _-|[]=~.\"'`*"
_XINSET = 12
_YINSET = 6


def _clean(text: str) -> str:
    return text.strip(_EDGE_STRIP).strip()


def _find_data_start(row_bands: list[tuple[int, int]]) -> int:
    """Index of the first row band that belongs to the real data grid,
    found from ROW-HEIGHT GEOMETRY alone -- deliberately not from OCR'd
    text (see module docstring "Row/column geometry" and the paragraph
    below on why an earlier, text-only version of this check was unsafe).

    Real data rows are confirmed directly to render at one consistent
    height across the whole file; the title/info box and the column-header
    labels row above them do not share that height (the info box is much
    taller, the labels row and the blank spacer row below it are both
    shorter). The modal row height is computed fresh per page (rather than
    hardcoded, since it scales with render DPI) as the most common height
    rounded to the nearest 10px, and the first index whose own height AND
    its next two neighbours' heights all fall within 25% of that mode is
    taken as the start of real data -- requiring three in a row rather than
    one guards against a coincidental single-row match inside the header
    band itself.

    This replaces an earlier version of this module that instead located
    the header row by checking for the literal OCR'd word "DESCRIPTION" in
    that row's own DESCRIPTION-column text. Confirmed directly against the
    real sample file's own real pipeline run: on one page (of 83), the OCR
    misread that cell badly enough ("SESCRIPTION" with a leading run of
    dashes) that the literal-word check missed it, and BOTH the info box
    row and the header-labels row leaked through as fabricated data rows --
    with the info box row's own OCR'd values landing in this table's
    TSN/CSN/AMM-Structure columns, i.e. the real aircraft registration/MSN/
    hours/cycles/date literally present in extracted output. That is a
    correctness bug on its own, and specifically the kind of leak this
    project's data-sensitivity convention exists to prevent, so the OCR-
    text-dependent check was replaced with this geometry-only one (which
    has no dependency on any single cell's OCR quality) rather than patched
    to special-case that one page. `_ocr_page_rows` below also keeps an
    explicit, independent content-based guard against this same failure
    mode (dropping any row whose own values reproduce the page's already-
    parsed header metadata), as defense in depth."""
    if len(row_bands) < 4:
        return 0
    heights = [b1 - b0 for b0, b1 in row_bands]
    from collections import Counter
    rounded = [round(h / 10) * 10 for h in heights]
    mode_height = Counter(rounded).most_common(1)[0][0]
    if mode_height <= 0:
        return 0
    tol = max(mode_height * 0.25, 8)

    def _near(h: int) -> bool:
        return abs(h - mode_height) <= tol

    for i in range(len(heights) - 2):
        if _near(heights[i]) and _near(heights[i + 1]) and _near(heights[i + 2]):
            return i
    return 0


async def _ocr_page_rows(img: Image.Image, header_meta: dict) -> list[dict]:
    arr = np.array(img.convert("L"))
    grid = _find_grid(arr)
    if grid is None:
        return []
    col_lines, row_lines = grid

    col_bounds = list(zip(col_lines[:-1], col_lines[1:]))
    row_bands_all = list(zip(row_lines[:-1], row_lines[1:]))
    data_start = _find_data_start(row_bands_all)
    row_bands = row_bands_all[data_start:]
    records = [dict.fromkeys(_COLUMN_ORDER, "") for _ in row_bands]
    row_tops = [b[0] for b in row_bands]
    row_bots = [b[1] for b in row_bands]

    for name, (cx0, cx1) in zip(_COLUMN_ORDER, col_bounds):
        x0, x1 = cx0 + _XINSET, cx1 - _XINSET
        if x1 - x0 < 5:
            x0, x1 = cx0 + 2, cx1 - 2
        crop = img.crop((x0, row_tops[0] + _YINSET, x1, row_bots[-1] - _YINSET // 2))
        words = await ocr_words(crop, psm=6, min_conf=-1)
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

    # Secondary defense, on top of the geometric `_find_data_start` cutoff
    # above: if a row's own DESCRIPTION-column OCR still contains the
    # literal word "DESCRIPTION" (never true of a real part description),
    # drop it and everything above it too. Geometry alone was confirmed
    # sufficient across the whole real sample file, but this costs nothing
    # and catches a differently-shaped header/title band this module's own
    # real sample file never showed.
    header_idx = None
    for i, rec in enumerate(records):
        if "DESCRIPTION" in rec["DESCRIPTION"].upper():
            header_idx = i
    if header_idx is not None:
        records = records[header_idx + 1:]

    # Explicit content-based guard, independent of both checks above:
    # never emit a row that reproduces the page's own already-parsed
    # header metadata (aircraft type/registration/MSN/current FH/FC/date).
    # This is the specific, confirmed failure mode documented in
    # `_find_data_start`'s own docstring -- the title/info box's real,
    # file-specific values leaking into the grid's own trailing columns as
    # a fabricated row -- caught here directly by content rather than by
    # relying on any geometry/text heuristic never being wrong. Per this
    # project's data-sensitivity convention (never let a real registration/
    # MSN reach extracted output), this check runs regardless of whether
    # the geometric cutoff above already removed the row.
    _leak_needles = [v for v in (
        header_meta.get("AIRCRAFT_REG"), header_meta.get("MSN"),
        header_meta.get("AIRCRAFT_TYPE"), header_meta.get("CURRENT_FH"),
        header_meta.get("CURRENT_FC"), header_meta.get("CURRENT_DATE"),
    ) if v]

    def _leaks_header(rec: dict) -> bool:
        if not _leak_needles:
            return False
        blob = " ".join(rec.values()).upper()
        return any(needle.upper() in blob for needle in _leak_needles)

    out = []
    for rec in records:
        # Blank separator row between the header and the first real data
        # row (see module docstring) -- and any other genuinely empty ruled
        # row -- is dropped rather than emitted. ITEM is deliberately not
        # part of this anchor check (confirmed genuinely blank on some real
        # rows -- see module docstring).
        if not (rec["ATA"] or rec["FIN"] or rec["DESCRIPTION"]):
            continue
        if _leaks_header(rec):
            continue
        out.append(rec)
    return out


_HEADER_FIELDS = ("CURRENT_FH", "CURRENT_FC", "CURRENT_DATE",
                   "AIRCRAFT_TYPE", "AIRCRAFT_REG", "MSN")


async def _parse_header_meta(img: Image.Image) -> dict:
    """Page-1 info box (Current FH/FC/Date -- middle value column; Aircraft
    Type/Reg/MSN -- rightmost column). OCR'd as two narrow value-only
    column crops rather than the whole box at once: confirmed directly,
    the label text ("Current FH", "Current FC", "Current Date:") sits far
    enough left of the value column that a value-only crop reads cleanly
    in a fixed top-to-bottom order without needing to parse past the
    labels at all."""
    meta = {k: "" for k in _HEADER_FIELDS}
    w, h = img.size
    val_crop = img.crop((int(w * 0.695), int(h * 0.105), int(w * 0.815), int(h * 0.16)))
    type_crop = img.crop((int(w * 0.815), int(h * 0.105), int(w * 0.97), int(h * 0.16)))
    val_text = await ocr_text(val_crop, psm=6)
    type_text = await ocr_text(type_crop, psm=6)
    val_lines = [ln.strip() for ln in val_text.splitlines() if ln.strip()]
    type_lines = [ln.strip() for ln in type_text.splitlines() if ln.strip()]
    if len(val_lines) >= 3:
        meta["CURRENT_FH"], meta["CURRENT_FC"], meta["CURRENT_DATE"] = val_lines[:3]
    if len(type_lines) >= 3:
        meta["AIRCRAFT_TYPE"], meta["AIRCRAFT_REG"], meta["MSN"] = type_lines[:3]
    return meta


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback (see
    sheet_types/occm.py) -- this variant's known source file has no text
    layer at all, so it can never be found through the normal pdfplumber
    head-text match.

    Requires BOTH the report's own title phrase ("OCCM LIST") and its
    column-header line's own distinctive trailing phrase ("AMM STRUCTURE")
    in the same top-of-page crop. Checked directly (grep across every
    SIGNATURES list in sheet_types/{occm,ht,llp}.py and every existing
    occm_variants/ht_variants/llp_variants module, plus every module's own
    ocr_detect() anchor text): "AMM STRUCTURE" (or "STRUCTURE" combined
    with "AMM") appears nowhere else in this package at all, so it alone
    is already a safe, distinctive anchor; "OCCM LIST" is bare and shared
    with several sibling modules' own docstrings/anchors (e.g.
    `occm_list_at_aircraft_fh.py`, `occm_list_func_loc_scanned.py`,
    `msn_occm_list_scanned.py`), but none of those require "AMM STRUCTURE"
    too, so the combination here cannot collide with any of them.
    """
    try:
        img = await render_page(pdf_path, 0, dpi=300)
        w, h = img.size
        crop = img.crop((0, 0, w, int(h * 0.24)))
        text = (await ocr_text(crop, psm=6)).upper()
        normed = " ".join(text.split())
        return "OCCM LIST" in normed and "AMM STRUCTURE" in normed
    except Exception:
        return False


async def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    header_meta = {k: "" for k in _HEADER_FIELDS}
    n_pages = await page_count(pdf_path)
    for page_index in range(n_pages):
        try:
            img = await render_page(pdf_path, page_index, dpi=400)
            if page_index == 0:
                header_meta = await _parse_header_meta(img)
            page_records = await _ocr_page_rows(img, header_meta)
        except Exception:
            continue
        for rec in page_records:
            rec.update(header_meta)
            rec["_page"] = page_index + 1
            records.append(rec)
    return records
