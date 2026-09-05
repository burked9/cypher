"""Lufthansa Technik AERO scanned engine LLP "Life Limited Parts, <module>"
status sheet -- this module handles specifically the **Fan Module** variant
of that sheet.

Every page is a single flat scanned/rasterized image with **no text layer**
(confirmed directly: `page.get_text()` returns "" and `page.get_drawings()`
returns zero vector elements on every page of the one known source file --
the whole page is `page.get_images()`-only, i.e. a raster picture, not a
vector-drawn form), so this module renders each page and OCRs it via
`shared/ocr_bridge.py`'s async primitives (`render_page()`/`ocr_text()`/
`ocr_words()`) rather than touching fitz/pytesseract directly -- see that
module's docstring for why the local/Pyodide split exists.

Confirmed directly by rendering every page of the one known source file (5
pages total, checked page count first): this producer emits one *whole*
multi-page PDF per engine shop visit, with one page per engine module --
observed titles "Life Limited Parts, Fan Module" / "... Core Module" /
"... HPT Rotor Assy" / "... LPT Module" / "... Static Structures", each its
own standalone "Page 1 of 1" report sharing one common header block (issue
date, engine serial number, work order, customer work order, engine
TSN/CSN). This module claims ONLY the Fan Module page(s) of such a PDF --
the other module titles are a different table shape/row count each and are
out of scope here. Because the module title (not page position) is what
identifies the right page, and nothing here guarantees the Fan Module page
is always first, both `ocr_detect()` and `extract()` scan every page of the
PDF (via `page_count()`) for the title phrase rather than assuming page 0 --
confirmed necessary in principle even though the one known sample happens to
have it as page 1 of 5.

The Fan Module page's own table is small and fixed in shape (confirmed on
the one known sample, and structurally expected to stay small: a fan module
only has so many life-limited parts): 2 data rows ("Fan Disc & Shaft" and
"Shaft, Fan Drive"), under a genuinely ruled grid (dark borders, confirmed
by direct pixel-darkness sampling -- not a caller-assumed guess) of 12
columns / 13 vertical divider lines:

    Description | P/N | S/N | CSN | Life Limit | Cycles Left  <- "Off Log" group
                 | P/N | S/N | CSN | Life Limit | Cycles Left  <- "On Log" group
    | Remarks

"Off Log" and "On Log" are printed as their own super-header row spanning
the 5 columns beneath each, confirmed directly by rendering and pixel-
inspecting the header band -- this is NOT the ambiguous "can't tell which
side is which" case some sibling LLP modules' docstrings describe: the
sheet itself labels the two groups unambiguously, so the canonical columns
below are named `_OFF_LOG` / `_ON_LOG` (not a guessed `_2` suffix) with full
confidence. REMARKS is free text (only the single value "Same" seen on the
one known sample, appearing to assert Off Log == On Log for that row) --
its full vocabulary isn't known from one sample, so it's captured as-is
rather than validated against a closed enum, mirroring how sibling LLP
modules treat their own single-sample "status word" columns.

Self-check, not blind trust: when REMARKS reads "Same", the Off Log and On
Log values are expected to be identical. `_offlog_onlog_check` records "OK"
when they in fact match, or a MISMATCH message (verify against the source
PDF) when they don't -- the same non-guessing pattern
`part_m_engine_disk_sheet.py` uses for its own cycles-sum self-check, rather
than silently trusting either side. When REMARKS is anything else, the
check is marked SKIPPED (no claim to verify).

Extraction strategy: detect the ruled grid directly via numpy dark-pixel
scanning (row lines from a full-width darkness scan, column lines from a
darkness scan restricted to the y-band from the column-header row down to
the table's bottom border -- restricting the y-band matters: scanning the
full page width at column-detection thresholds picks up 2 extra spurious
"columns" from digit-glyph darkness that happens to line up down a whole
data-row band on this file's identical Off/On Log values, confirmed
directly by comparing a 0.5 vs 0.9 row-darkness-fraction threshold at each
candidate line -- true grid lines read ~1.0 (dark for the *entire* band
height), the 2 false positives read ~0.5 (dark for only about half of it,
i.e. only one data row's glyphs, not a real full-height rule); the higher
0.9 threshold cleanly discards them). The header super-row ("Off Log"/"On
Log", spanning 2 wide cells) and the column-name sub-header row are both
fixed by this producer's template, so -- mirroring
`part_m_engine_disk_sheet.py`'s own `h_lines[2:-1], h_lines[3:]` convention
for its analogous 2-header-row layout -- the first 2 detected row-bands are
always skipped rather than re-detected per file, while the *number* of data
rows below them is never hardcoded (found dynamically from however many
row-boundary lines the grid detector actually returns).

Each of the 12 grid cells reads cleanly with a plain padded crop + psm 7 on
the one known sample (confirmed directly, cell by cell) -- no tight-bbox
glyph re-cropping was needed here, unlike the noisier scans some sibling
modules document; this looks like a clean computer-rendered raster rather
than a photographed form, so the simpler crop is used and not over-built
against a problem not actually observed.

Header metadata (Issue Date, Engine Serial Number, AERO Work Order,
Customer Work Order, Engine TSN/CSN) sits in a left-hand block that
OCR-interleaves with the centered title and the right-hand letterhead logo
when the whole header band is OCR'd as one wide strip (confirmed directly:
a whole-width OCR pass drops the "Issue Date" line's content entirely and
scrambles other lines) -- the same multi-column interleaving problem
`kalstar_engine_llp_status.py` documents for its own 4-column header. Fixed
the same way in spirit: crop the left metadata block, the centered title (+
"Module S/N"), and the "Engine TSN / CSN" line as 3 separate narrower OCR
passes instead of one whole-width pass, each of which reads cleanly
(confirmed directly against the one known sample).

Known limitation: only one real source file (one engine, one shop visit)
has been checked. Column x-positions, row heights, and the header crop
bands above are taken from that file only -- if a second real file ever
shows different column/row pixel positions (as several sibling LLP modules'
docstrings note happens across their own multi-file corpora), the
crop-band constants below would need to be re-verified rather than assumed
stable.
"""
from __future__ import annotations
import re

import numpy as np

from sheet_types.llp_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, page_count

NAME = "Lufthansa Technik AERO Fan Module LLP Status"

# Text-layer signature list deliberately empty -- the one known source file
# has a 0-char text layer on every page (see module docstring); real
# detection happens via ocr_detect() below, mirroring
# kalstar_engine_llp_status.py's own empty SIGNATURES for the same reason.
SIGNATURES: list[str] = []

_OFF_ON_FIELDS = ["PART_NUMBER", "SERIAL_NUMBER", "CSN", "LIFE_LIMIT", "CYCLES_LEFT"]

CANONICAL_COLUMNS = [
    "DESCRIPTION",
    *[f"{f}_OFF_LOG" for f in _OFF_ON_FIELDS],
    *[f"{f}_ON_LOG" for f in _OFF_ON_FIELDS],
    "REMARKS",
    # File-level (Issue Date/ESN/work orders/engine TSN-CSN) and page-level
    # (Module S/N) metadata -- same on every row of a given page.
    "ISSUE_DATE",
    "ENGINE_SERIAL_NUMBER",
    "WORK_ORDER",
    "CUSTOMER_WORK_ORDER",
    "ENGINE_TSN",
    "ENGINE_CSN",
    "MODULE_SERIAL_NUMBER",
]

_PN_RULE = {
    "pattern": r"^[A-Z0-9](?:[A-Z0-9\-]*[A-Z0-9])?$",
    "uppercase": True,
    "no_spaces": True,
    "allow_empty": True,
}
_SN_RULE = {
    "pattern": r"^[A-Z0-9](?:[A-Z0-9\-]*[A-Z0-9])?$",
    "uppercase": True,
    "no_spaces": True,
    "allow_empty": True,
}
_INT_RULE = {"pattern": r"^[\d,]*$", "allow_empty": True, "int_range": (0, 100000)}
_DATE_RULE = {"pattern": r"^(\d{1,2}\.[A-Za-z]{3,9}\.\d{4})?$", "allow_empty": True}

_OVERRIDES = {
    "DESCRIPTION": {"allow_empty": True},
    "REMARKS": {"allow_empty": True},
    "ISSUE_DATE": _DATE_RULE,
    "ENGINE_SERIAL_NUMBER": {"allow_empty": True},
    "WORK_ORDER": {"pattern": r"^[\d ]*$", "allow_empty": True},
    "CUSTOMER_WORK_ORDER": {"pattern": r"^[A-Z0-9\-]*$", "uppercase": True, "allow_empty": True},
    "ENGINE_TSN": _INT_RULE,
    "ENGINE_CSN": _INT_RULE,
    "MODULE_SERIAL_NUMBER": {"pattern": r"^[A-Z0-9\-]*$", "uppercase": True, "allow_empty": True},
}
for _f in _OFF_ON_FIELDS:
    _OVERRIDES[f"{_f}_OFF_LOG"] = _PN_RULE if _f == "PART_NUMBER" else (
        _SN_RULE if _f == "SERIAL_NUMBER" else _INT_RULE)
    _OVERRIDES[f"{_f}_ON_LOG"] = _OVERRIDES[f"{_f}_OFF_LOG"]
RULES = merged_rules(_OVERRIDES)

_DPI = 300
_DARK_THRESH = 220
_ROW_LINE_FRAC = 0.5
_COL_LINE_FRAC = 0.9
_N_TABLE_COLS = 12  # Description, (P/N,S/N,CSN,Life Limit,Cycles Left) x2, Remarks

# Crop bands (fraction of page width/height), confirmed directly against
# the one known source file's rendered page -- see module docstring's
# "Known limitation" note.
_TITLE_CROP = (0.35, 0.0, 0.80, 0.10)      # x0, y0, x1, y1
_LEFT_HDR_CROP = (0.0, 0.0, 0.35, 0.20)
_TSN_CSN_CROP = (0.0, 0.18, 1.0, 0.25)

_TITLE_RE = re.compile(r"LIFE\s+LIMITED\s+PARTS,?\s*FAN\s+MODULE", re.I)
_ISSUE_DATE_RE = re.compile(r"Issue\s*Date\s*:?\s*(\d{1,2}\.[A-Za-z]{3,9}\.\d{4})", re.I)
_ESN_RE = re.compile(r"Engine\s*Serial\s*Number\s*:?\s*(\S+)", re.I)
_WO_RE = re.compile(r"Work\s*Order\s*:?\s*([\d][\d ]*\d|\d)", re.I)
_CWO_RE = re.compile(r"Customer\s*Work\s*Order\s*:?\s*(\S+)", re.I)
_TSN_CSN_RE = re.compile(r"Engine\s*TSN\s*/\s*CSN\s*:?\s*([\d,]+)\s*/\s*([\d,]+)", re.I)
_MODULE_SN_RE = re.compile(r"Module\s*S\s*/\s*N\s*:?\s*(\S+)", re.I)


def _crop_frac(img, box):
    w, h = img.size
    x0, y0, x1, y1 = box
    return img.crop((int(w * x0), int(h * y0), int(w * x1), int(h * y1)))


async def _read_title(img) -> str:
    return await ocr_text(_crop_frac(img, _TITLE_CROP), psm=6)


def _first_work_order(text: str) -> str | None:
    """The AERO Work Order and Customer Work Order lines both contain the
    substring "Work Order" (the 2nd is literally "Customer Work Order").
    The AERO one is the first "Work Order" occurrence in the left-header
    block's own top-to-bottom reading order (confirmed directly), so take
    the first regex match whose preceding ~15 characters do NOT contain
    "Customer" -- more defensive than relying on plain first-match order
    alone if a future file's OCR ever reorders the two lines."""
    for m in _WO_RE.finditer(text):
        preceding = text[max(0, m.start() - 15):m.start()]
        if "customer" not in preceding.lower():
            return re.sub(r"\s+", " ", m.group(1)).strip()
    return None


async def _parse_header(img) -> dict:
    meta: dict[str, str] = {}

    title_text = await _read_title(img)
    m = _MODULE_SN_RE.search(title_text)
    if m:
        meta["MODULE_SERIAL_NUMBER"] = m.group(1).strip()

    left_text = await ocr_text(_crop_frac(img, _LEFT_HDR_CROP), psm=6)
    m = _ISSUE_DATE_RE.search(left_text)
    if m:
        meta["ISSUE_DATE"] = m.group(1).strip()
    m = _ESN_RE.search(left_text)
    if m:
        meta["ENGINE_SERIAL_NUMBER"] = m.group(1).strip()
    wo = _first_work_order(left_text)
    if wo:
        meta["WORK_ORDER"] = wo
    m = _CWO_RE.search(left_text)
    if m:
        meta["CUSTOMER_WORK_ORDER"] = m.group(1).strip()

    tsn_text = await ocr_text(_crop_frac(img, _TSN_CSN_CROP), psm=6)
    m = _TSN_CSN_RE.search(tsn_text)
    if m:
        meta["ENGINE_TSN"] = m.group(1).replace(",", "")
        meta["ENGINE_CSN"] = m.group(2).replace(",", "")

    return meta


def _line_positions(frac: np.ndarray, thresh: float) -> list[int]:
    idx = np.where(frac > thresh)[0]
    if not len(idx):
        return []
    groups, cur = [], [int(idx[0])]
    for v in idx[1:]:
        if v - cur[-1] <= 3:
            cur.append(int(v))
        else:
            groups.append(cur)
            cur = [int(v)]
    groups.append(cur)
    return [int(np.mean(g)) for g in groups]


def _longest_dense_run(lines: list[int], max_gap: int = 200, min_lines: int = 4) -> list[int]:
    """The data table is a dense run of closely-spaced ruled lines; the lone
    divider under the Issue-Date/ESN/Work-Order block sits well above it
    (confirmed directly: ~260px gap vs ~60-160px between the table's own
    lines). Find the longest run of consecutive lines whose gaps all stay
    under `max_gap`, rather than hardcoding where the table starts."""
    if len(lines) < min_lines:
        return []
    gaps = [b - a for a, b in zip(lines[:-1], lines[1:])]
    best_start, best_len, cur_start, cur_len = 0, 0, 0, 0
    for i, g in enumerate(gaps):
        if g < max_gap:
            if cur_len == 0:
                cur_start = i
            cur_len += 1
        else:
            if cur_len > best_len:
                best_start, best_len = cur_start, cur_len
            cur_len = 0
    if cur_len > best_len:
        best_start, best_len = cur_start, cur_len
    if best_len + 1 < min_lines:
        return []
    return lines[best_start:best_start + best_len + 1]


def _table_grid(gray: np.ndarray):
    """Returns (row_lines, col_lines) or (None, []) if the grid can't be
    confirmed. row_lines includes the 2 fixed header-row boundaries
    followed by however many data-row boundaries were actually found (see
    module docstring); col_lines has _N_TABLE_COLS + 1 entries."""
    dark = gray < _DARK_THRESH
    full_frac = dark.mean(axis=1)
    all_h = _line_positions(full_frac, _ROW_LINE_FRAC)
    row_lines = _longest_dense_run(all_h)
    if len(row_lines) < 4:
        return None, []

    y0, y1 = row_lines[1], row_lines[-1]
    col_frac = dark[y0:y1, :].mean(axis=0)
    col_lines = _line_positions(col_frac, _COL_LINE_FRAC)
    if len(col_lines) != _N_TABLE_COLS + 1:
        return None, []
    return row_lines, col_lines


async def _cell_text(img, col_lines, y0, y1, col_j, pad=5, psm=7, whitelist=None) -> str:
    x0, x1 = col_lines[col_j], col_lines[col_j + 1]
    crop = img.crop((x0 + pad, y0 + pad, x1 - pad, y1 - pad))
    text = await ocr_text(crop, psm=psm, whitelist=whitelist)
    return text.strip()


_DIGITS = "0123456789"


async def _extract_row(img, col_lines, y0, y1) -> dict:
    rec = {c: "" for c in CANONICAL_COLUMNS}
    rec["DESCRIPTION"] = await _cell_text(img, col_lines, y0, y1, 0)
    for i, field in enumerate(_OFF_ON_FIELDS):
        numeric = field in ("CSN", "LIFE_LIMIT", "CYCLES_LEFT")
        rec[f"{field}_OFF_LOG"] = await _cell_text(
            img, col_lines, y0, y1, 1 + i, whitelist=_DIGITS if numeric else None)
    for i, field in enumerate(_OFF_ON_FIELDS):
        numeric = field in ("CSN", "LIFE_LIMIT", "CYCLES_LEFT")
        rec[f"{field}_ON_LOG"] = await _cell_text(
            img, col_lines, y0, y1, 6 + i, whitelist=_DIGITS if numeric else None)
    rec["REMARKS"] = await _cell_text(img, col_lines, y0, y1, 11)

    if rec["REMARKS"].strip().upper() == "SAME":
        match = all(
            rec[f"{f}_OFF_LOG"] == rec[f"{f}_ON_LOG"] for f in _OFF_ON_FIELDS)
        rec["_offlog_onlog_check"] = (
            "OK" if match
            else "MISMATCH: REMARKS says 'Same' but Off Log/On Log values "
                 "differ - verify against source PDF")
    else:
        rec["_offlog_onlog_check"] = "SKIPPED: REMARKS not 'Same' - no cross-check basis"
    return rec


async def _find_fan_module_pages(pdf_path: str) -> list[tuple[int, object]]:
    """Returns [(page_index, rendered_image), ...] for every page whose
    title OCRs as the Fan Module sheet. Scans every page rather than
    assuming page 0 -- see module docstring."""
    n_pages = await page_count(pdf_path)
    hits = []
    for i in range(n_pages):
        img = await render_page(pdf_path, i, dpi=_DPI)
        title_text = await _read_title(img)
        if _TITLE_RE.search(title_text):
            hits.append((i, img))
    return hits


async def ocr_detect(pdf_path: str) -> bool:
    """Router's blank-text fallback check. Scans every page (see module
    docstring) for the Fan Module title phrase; cheap per page since only a
    small title-band crop is OCR'd, not the whole page."""
    try:
        hits = await _find_fan_module_pages(pdf_path)
        return bool(hits)
    except Exception:
        return False


async def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    for page_idx, img in await _find_fan_module_pages(pdf_path):
        meta = await _parse_header(img)
        gray = np.array(img.convert("L"))
        row_lines, col_lines = _table_grid(gray)
        if row_lines is None:
            continue
        for ry0, ry1 in zip(row_lines[2:-1], row_lines[3:]):
            rec = await _extract_row(img, col_lines, ry0, ry1)
            if not rec["DESCRIPTION"] and not rec["PART_NUMBER_OFF_LOG"]:
                continue
            for k, v in meta.items():
                rec[k] = v
            rec["_page"] = page_idx + 1
            records.append(rec)
    return records
