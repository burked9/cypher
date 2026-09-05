"""CF34 "LIFE-LIMITED & MAJOR COMPONENT PART RECORD" (form DEF 3420/3422/3431/
3433 family) -- a scanned, hand-annotated engine records sheet with **no text
layer** on the one known source file (0 chars on every page, confirmed via a
direct fitz text-extraction pass -- a photographed/scanned carbon-form, not a
computer-rendered raster). Every page renders and OCRs via
`shared/ocr_bridge.py`'s async primitives (`render_page()`/`ocr_text()`/
`ocr_words()`), which run on fitz+pytesseract locally and on a JS/Tesseract.js
bridge under Pyodide -- see that module's docstring for why the split exists.

One page == one "sheet" of the engine's records package, covering one module
or section's own set of life-limited/major-component part rows (e.g. an
"<module> MODULE" sheet for the compressor/combustion/turbine sections, or a
"<section> ACCESSORY SECTION" sheet with no single-module IIN-NO prefix).
Header block (values below are placeholders, not from any real file)::

    CIRCLE ONE:
    NEW ENGINE            S/N  <esn>                          SECTION <n>
    O/H ENGINE 1..9       P/N  <epn>   <section text>   IIN NO: <n>   SHEET <n> OF <n>
    Module: S/N <module_sn>   TSN <v>  TSO <v>  CSN <v>  CSO <v>  SHOP <v>  W/O NO. <v>
    OPERATOR <v>               DATE OF WORK <v>   FAA/DOT NO. <v>   SIGNATURE/LICENSE <v>

Only the fields with an unambiguous, safely-anchored value are extracted here
(mirroring kalstar_engine_llp_status.py's stated policy) -- ENGINE_MODEL (the
title's own "CF34", not per-file), ENGINE_SERIAL_NUMBER, ENGINE_PART_NUMBER,
SECTION_NAME, MODULE_INNO, SHEET_NO/SHEET_TOTAL. The "Module: S/N" row's own
sub-fields (module S/N, TSN/TSO/CSN/CSO, SHOP, W/O NO.) and the
OPERATOR/DATE OF WORK/FAA-DOT/SIGNATURE row are skipped outright: on the one
known source file every one of those is blank on every page, leaving no real
value anywhere to validate a parsing regex against, and this format shares
kalstar_engine_llp_status.py's documented header-word-interleaving problem
(a flat top-to-bottom OCR read of "Module: S/N ... TSN ... TSO ..." lists the
label row and the value row as separate lines, so a naive regex anchored on
"S/N" immediately followed by its value would silently capture the *next*
column's label -- e.g. "S/N" followed by the literal word "TSN" -- instead of
the real module serial). ENGINE_SERIAL_NUMBER/ENGINE_PART_NUMBER avoid this
trap because on every known page they sit on the SAME line as their own
label, before the first "Module" occurrence in reading order -- confirmed
directly, not assumed -- so parsing is restricted to the text *before* that
first "Module" occurrence.

Row shape: PART_NAME | ITEM_NO (3-digit) | PART_NUMBER | SERIAL_NUMBER, then
6 grouped time-figure columns -- ENGINE_AT_INSTL, ENGINE_AT_RMVL (each an
"AT INSTL"/"AT RMVL" pair of TSN+CSN), PART_AT_INSTL, PART_AT_RMVL (each a
"COMP/PART TIME" AT INSTL/AT RMVL pair of TSN+CSN+TSO), ULTIMATE_LIFE and
EXPIRE (each a TSN+CSN pair) -- then REMARKS. The printed column-group
headers ("ENGINE TIME"/"COMP/PART TIME"/"PART ULTIMATE LIFE"/"ENG. TIME AT
PART EXPIRE") repeat the same TSN/CSN/TSO sub-labels across all 6 groups, so
a naive OCR-then-regex read of the flattened header text cannot tell which
occurrence of "TSN" belongs to which group -- confirmed directly (OCR of the
header block reads back garbled, e.g. "TSN | TSN | CSN | CSN | TSN | TSN" on
one line with no group boundary markers surviving at all). This module never
tries to recover the column grouping from OCR'd header TEXT: the grouping is
fixed by the printed template and is read once, structurally, from the
ruled grid itself (see below), the same way the header's own printed labels
were read directly off the rendered page during development rather than
trusted from a rough first OCR pass (that first pass's own guess at the
legend order turned out not to match the true column boundaries at all).

Grid structure, confirmed by direct pixel inspection against the rendered
page (300dpi) rather than assumed from the OCR text:
  - 12 vertical ruled lines (11 columns) run the full height of the table,
    detected once by scanning column darkness across a wide y-band (0.30-
    0.85 of page height) comfortably inside the table body on every known
    page.
  - The outer ROW boundaries (one per part record) are found from the
    PART_NAME column's own interior width alone: unlike every other column,
    PART_NAME never subdivides internally, so lines detected there are
    exactly the main row grid -- confirmed directly against all 4 known
    pages (bottom-of-header through bottom-of-table). A darkness threshold
    of 0.7 (not the more permissive 0.5 used elsewhere in this module) is
    required here specifically: at 0.5, wrapped 2-line PART_NAME entries
    (e.g. a 2-word component name) produce enough incidental glyph-stroke
    darkness across the column's interior width to register as spurious
    extra "grid lines" a few px apart -- confirmed directly by dumping the
    raw line positions at both thresholds; 0.7 cleanly removes every one of
    those false positives on all 4 known pages while still catching every
    genuine ruled line. The header box above the table (CIRCLE ONE/Module:
    S/N/OPERATOR block) produces a handful of extra lines in the same scan;
    rather than crop it out by a guessed y-offset, `_select_row_chain()`
    (ported from kalstar_engine_llp_status.py) finds this file's own modal
    row-to-row spacing and keeps the longest run close to it, which
    reliably discards the header box's few, non-uniformly-spaced lines
    (confirmed directly: their gaps are actually *smaller* than the modal
    row spacing on every known page, so a naive "denser run wins" rule --
    the one part_m_engine_disk_sheet.py uses successfully for its own
    header/data split -- would pick the WRONG region here; matching this
    file's own modal spacing, not just density, is what's required).
  - A page-wide rotational skew (the same phenomenon
    kalstar_engine_llp_status.py's docstring documents for its own table)
    means the row boundaries detected from the PART_NAME column alone do
    NOT line up with the true row boundaries in the grouped time columns
    further right -- confirmed directly: reusing PART_NAME's row edges
    verbatim for the COMP/PART TIME columns produced a systematic ~1-2
    internal-divider miscount on 3 of the 4 known pages (the skew being
    small enough on the 4th to not matter there, which is exactly the kind
    of file-dependent inconsistency that makes "it usually works" the wrong
    bar). Row edges are therefore also detected independently from the
    REMARKS column (the table's other non-subdividing column, at the
    opposite edge), and every other column's row boundary is interpolated
    between the two by x-position (`_y_at()`, ported from
    kalstar_engine_llp_status.py's own skew fix) -- confirmed directly to
    bring every one of the 4 known pages' internal-divider counts back to
    the expected value with zero mismatches.
  - Within each grouped column's own row band, the internal TSN/CSN(/TSO)
    sub-dividers are ruled lines too -- detected fresh per cell (a narrow,
    cheap local scan) rather than assumed evenly spaced, and cross-checked
    against the expected sub-row count for that column (2 for the
    ENGINE_AT_*/ULTIMATE_LIFE/EXPIRE columns, 3 for the PART_AT_* columns,
    fixed by the printed template, not detected per file). Never guess a
    wrong split: when the detected internal-divider count doesn't match
    what that column's own template position requires, this module does
    NOT force a 2-or-3-way split onto whatever lines it found -- the
    column's own OCR'd text is kept whole in STATUS_TRAIL (prefixed with
    which column it came from) and the row is flagged via `_split_check`
    for manual verification against the source PDF instead.

Known imperfections, left uncorrected rather than patched with a fragile
one-off: several stamped/handwritten annotations (shop signatures, date
stamps) sit inside or beside the REMARKS column on rows that were actually
reworked; REMARKS is extracted as plain OCR text with no attempt to parse
structure out of it, since its content isn't standardized across rows the
same way the numeric TSN/CSN/TSO columns are. Handwritten (not printed)
figures in the time columns are also read through the same digit-only OCR
pass as printed ones -- confirmed to work in every observed case on the one
known source file, but this module makes no special claim about handwriting
recognition accuracy beyond that; a handwritten value that fails its
column's numeric pattern is flagged (never dropped) by the shared cleanup
pipeline like any other field, per this project's soft-validation
convention.
"""
from __future__ import annotations

import re
from collections import Counter

import numpy as np

from sheet_types.llp_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text

NAME = "CF34 Life-Limited & Major Component Part Record"
# Text-layer signature list is here purely for interface consistency (see
# part_m_engine_disk_sheet.py's own comment on this) -- the one known source
# file has a 0-char text layer on every page, so real detection happens
# entirely through ocr_detect() below. Checked for a textual collision
# against every SIGNATURES list in sheet_types/{occm,ht,llp}.py and every
# existing variant file; no collision found.
SIGNATURES = [
    "LIFE-LIMITED & MAJOR COMPONENT PART RECORD",
]

_DPI = 300
_DARK_THRESH = 130
_ROW_LINE_FRAC = 0.7      # PART_NAME/REMARKS column: main row-grid detection
_DIV_LINE_FRAC = 0.5      # inside a data row: TSN/CSN/TSO sub-divider detection
_N_TABLE_COLS = 11
_BORDER_MARGIN = 10        # px inside a cell to ignore as "that's the row border"

# Column index -> (group label, sub-row keys in top-to-bottom order). Fixed
# by the printed template (see module docstring) -- never detected per file.
_GROUPED_COLS = {
    4: ("ENGINE_AT_INSTL", ("ENGINE_TSN_AT_INSTL", "ENGINE_CSN_AT_INSTL")),
    5: ("ENGINE_AT_RMVL", ("ENGINE_TSN_AT_RMVL", "ENGINE_CSN_AT_RMVL")),
    6: ("PART_AT_INSTL", ("PART_TSN_AT_INSTL", "PART_CSN_AT_INSTL", "PART_TSO_AT_INSTL")),
    7: ("PART_AT_RMVL", ("PART_TSN_AT_RMVL", "PART_CSN_AT_RMVL", "PART_TSO_AT_RMVL")),
    8: ("ULTIMATE_LIFE", ("ULTIMATE_LIFE_TSN", "ULTIMATE_LIFE_CSN")),
    9: ("EXPIRE", ("EXPIRE_TSN", "EXPIRE_CSN")),
}

CANONICAL_COLUMNS = [
    "PART_NAME", "ITEM_NO", "PART_NUMBER", "SERIAL_NUMBER",
    "ENGINE_TSN_AT_INSTL", "ENGINE_CSN_AT_INSTL",
    "ENGINE_TSN_AT_RMVL", "ENGINE_CSN_AT_RMVL",
    "PART_TSN_AT_INSTL", "PART_CSN_AT_INSTL", "PART_TSO_AT_INSTL",
    "PART_TSN_AT_RMVL", "PART_CSN_AT_RMVL", "PART_TSO_AT_RMVL",
    "ULTIMATE_LIFE_TSN", "ULTIMATE_LIFE_CSN",
    "EXPIRE_TSN", "EXPIRE_CSN",
    "REMARKS",
    "STATUS_TRAIL", "_split_check",
    # File/page-level header metadata, stamped on every row.
    "ENGINE_MODEL", "ENGINE_SERIAL_NUMBER", "ENGINE_PART_NUMBER",
    "SECTION_NAME", "MODULE_INNO", "SHEET_NO", "SHEET_TOTAL",
    "_page",
]

_TIME_RULE = {"pattern": r"^[\d,]*$", "allow_empty": True, "int_range": (0, 100000)}
_OVERRIDES = {
    "ITEM_NO": {"pattern": r"^\d{1,3}$", "allow_empty": True},
    # This form's serial numbers are two-token (a short shop/facility code
    # followed by the actual serial, e.g. "<shop> <serial>") -- confirmed on
    # every row of the one known source file. The shared global SERIAL_NUMBER
    # pattern has no space in it (built for single-token SNs elsewhere in
    # this project), so it must be overridden here or every row on this
    # format flags as bad_format.
    "SERIAL_NUMBER": {"pattern": r"^[A-Z0-9]+(?: [A-Z0-9/\-]+)?$", "allow_empty": True},
    "REMARKS": {"allow_empty": True},
    "STATUS_TRAIL": {"allow_empty": True},
    "_split_check": {"allow_empty": True},
    "ENGINE_MODEL": {"allow_empty": True},
    "ENGINE_SERIAL_NUMBER": {"allow_empty": True},
    "ENGINE_PART_NUMBER": {"allow_empty": True},
    "SECTION_NAME": {"allow_empty": True},
    "MODULE_INNO": {"pattern": r"^\d*$", "allow_empty": True},
    "SHEET_NO": {"pattern": r"^\d*$", "allow_empty": True},
    "SHEET_TOTAL": {"pattern": r"^\d*$", "allow_empty": True},
}
for _cols in _GROUPED_COLS.values():
    for _key in _cols[1]:
        _OVERRIDES[_key] = _TIME_RULE
RULES = merged_rules(_OVERRIDES)

_JUNK_RE = re.compile(r"[^A-Za-z0-9/.\- ]")
_DIGITS = "0123456789"


def _clean_text(raw: str) -> str:
    return re.sub(r"\s+", " ", _JUNK_RE.sub(" ", raw)).strip()


def _clean_alnum(raw: str) -> str:
    return re.sub(r"\s+", " ", _JUNK_RE.sub(" ", raw)).strip().upper()


def _clean_digits(raw: str) -> str:
    digits = re.sub(r"[^0-9]", "", raw)
    return digits


def _line_groups(frac: np.ndarray, thresh: float, merge: int = 15) -> list[int]:
    """Group indices where `frac > thresh` into line positions, then merge
    still-close groups (thick/double-drawn rules otherwise get detected
    twice). See module docstring for why the threshold and merge distance
    matter here specifically."""
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
    out = [int(np.mean(g)) for g in groups]
    merged = [out[0]]
    for x in out[1:]:
        if x - merged[-1] <= merge:
            merged[-1] = int((merged[-1] + x) / 2)
        else:
            merged.append(x)
    return merged


def _select_row_chain(edges: list[int]) -> list[int]:
    """Longest run of consecutive edges spaced at this file's own modal
    row height -- ported from kalstar_engine_llp_status.py's identical
    helper (same underlying problem: row height isn't safely hardcodable,
    and the header box's own lines must be discarded without assuming
    they're sparser than the data rows -- see module docstring)."""
    if len(edges) < 2:
        return []
    diffs = [edges[i + 1] - edges[i] for i in range(len(edges) - 1)]
    buckets = Counter(round(d / 5) * 5 for d in diffs if 20 <= d <= 400)
    if not buckets:
        return []
    mode = buckets.most_common(1)[0][0]
    tol = max(10, mode * 0.15)
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


def _y_at(lo: list[int], hi: list[int], x_lo: float, x_hi: float, i: int, x: float) -> int:
    """Skew-corrected row-boundary y-position at column x-center `x`, edge
    index `i` -- ported from kalstar_engine_llp_status.py's identical
    helper. `lo`/`hi` are row edges detected independently at the table's
    left (PART_NAME) and right (REMARKS) interior columns."""
    if x_hi == x_lo:
        return lo[i]
    t = (x - x_lo) / (x_hi - x_lo)
    return int(round(lo[i] + (hi[i] - lo[i]) * t))


def _table_grid(gray: np.ndarray):
    """Returns (v_lines, lo, hi, x_lo, x_hi) or None if the grid can't be
    confirmed. See module docstring for the detection strategy."""
    dark = gray < _DARK_THRESH
    h, w = gray.shape
    band = dark[int(h * 0.30):int(h * 0.85), :]
    v_lines = _line_groups(band.mean(axis=0), 0.5)
    if len(v_lines) != _N_TABLE_COLS + 1:
        return None

    x0, x1 = v_lines[0], v_lines[1]
    col0 = dark[:, x0 + 3:x1 - 3]
    lo_all = _line_groups(col0.mean(axis=1), _ROW_LINE_FRAC)
    lo = _select_row_chain(lo_all)

    x0r, x1r = v_lines[-2], v_lines[-1]
    col_last = dark[:, x0r + 3:x1r - 3]
    hi_all = _line_groups(col_last.mean(axis=1), _ROW_LINE_FRAC)
    hi = _select_row_chain(hi_all)

    if len(lo) < 2 or len(lo) != len(hi):
        return None

    x_lo = (v_lines[0] + v_lines[1]) / 2
    x_hi = (v_lines[-2] + v_lines[-1]) / 2
    return v_lines, lo, hi, x_lo, x_hi


async def _cell_text(img, x0: int, x1: int, y0: int, y1: int, pad: int = 4,
                      psm: int = 7, whitelist: str | None = None) -> str:
    if y1 - y0 <= 2 * pad or x1 - x0 <= 2 * pad:
        return ""
    crop = img.crop((x0 + pad, y0 + pad, x1 - pad, y1 - pad))
    return (await ocr_text(crop, psm=psm, whitelist=whitelist)).strip()


def _cell_dividers(dark: np.ndarray, x0: int, x1: int, ry0: int, ry1: int) -> list[int]:
    strip = dark[ry0:ry1, x0 + 3:x1 - 3]
    if strip.shape[0] <= 2 * _BORDER_MARGIN:
        return []
    lines = _line_groups(strip.mean(axis=1), _DIV_LINE_FRAC, merge=8)
    return [ry0 + l for l in lines if _BORDER_MARGIN < l < (ry1 - ry0 - _BORDER_MARGIN)]


async def _parse_header_metadata(img) -> dict:
    """Header fields extracted -- see module docstring for why the
    Module:S/N-row sub-fields are deliberately skipped."""
    w, h = img.size
    crop = img.crop((0, 0, w, int(h * 0.33)))
    text = re.sub(r"\s+", " ", await ocr_text(crop, psm=6))
    meta: dict[str, str] = {"ENGINE_MODEL": "CF34"}

    # Restrict the S/N and P/N lookups to the text BEFORE the first "Module"
    # occurrence -- see module docstring for why a flat search over the
    # whole header risks matching "Module: S/N"'s own late-arriving,
    # out-of-order value words instead of the real engine-level fields.
    head = text.split("Module", 1)[0]
    m = re.search(r"S[/I]N[\s_:]*([A-Z0-9\-]+)", head)
    if m:
        meta["ENGINE_SERIAL_NUMBER"] = m.group(1)
    m = re.search(r"P[/I]N[\s_:]*([A-Z0-9\-]+)", head)
    if m:
        meta["ENGINE_PART_NUMBER"] = m.group(1)

    m = re.search(r"SHEET\s*(\d+)\s*OF\s*(\d+)", text, re.I)
    if m:
        meta["SHEET_NO"], meta["SHEET_TOTAL"] = m.group(1), m.group(2)

    m = re.search(r"I[I1]N\s*NO\.?\s*:?\s*(\d+)", text, re.I)
    if m:
        meta["MODULE_INNO"] = m.group(1)

    m = re.search(
        r"P[/I]N[\s_:]*[A-Z0-9\-]+\s*[-=~'\"]*\s*(.*?)\s*SHEET\s*\d+\s*OF\s*\d+",
        text, re.I,
    )
    if m:
        raw = re.sub(r"I[I1]N\s*NO\.?\s*:?\s*\d+", "", m.group(1), flags=re.I)
        raw = re.sub(r"[^A-Za-z ]", "", raw).strip().upper()
        if raw:
            meta["SECTION_NAME"] = raw
    return meta


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 header OCR check for the router's blank-text fallback.
    Anchors on the full distinctive title phrase (checked for collision
    against every other LLP variant's own ocr_detect()/SIGNATURES anchor;
    none found -- "CF34" and "LIFE-LIMITED" are otherwise unused)."""
    try:
        img = await render_page(pdf_path, 0, dpi=_DPI)
        w, h = img.size
        crop = img.crop((0, 0, w, int(h * 0.10)))
        text = (await ocr_text(crop, psm=6)).upper()
        return "CF34" in text and "LIFE" in text and "MAJOR COMPONENT" in text
    except Exception:
        return False


async def _extract_page(pdf_path: str, page_index: int) -> list[dict]:
    img = await render_page(pdf_path, page_index, dpi=_DPI)
    gray = np.array(img.convert("L"))
    grid = _table_grid(gray)
    if grid is None:
        return []
    v_lines, lo, hi, x_lo, x_hi = grid
    dark = gray < _DARK_THRESH

    meta = await _parse_header_metadata(img)
    meta["_page"] = page_index + 1

    records: list[dict] = []
    for i in range(len(lo) - 1):
        ry0_pn, ry1_pn = lo[i], lo[i + 1]
        x0, x1 = v_lines[2], v_lines[3]
        xc = (x0 + x1) / 2
        ry0, ry1 = _y_at(lo, hi, x_lo, x_hi, i, xc), _y_at(lo, hi, x_lo, x_hi, i + 1, xc)
        part_number = _clean_alnum(await _cell_text(img, x0, x1, ry0, ry1))
        # Blank template rows (no part fitted) still OCR to a few bytes of
        # noise often enough that "empty string" alone isn't a safe skip
        # test -- confirmed directly against the one known source file,
        # whose blank rows came back as things like "CO"/"IA" from stray
        # gridline/glyph artifacts. Every genuine PART_NUMBER on every known
        # row contains at least one digit (these are aviation part numbers,
        # never bare letters), so requiring one is a cheap, reliable extra
        # filter that doesn't risk rejecting a real row.
        if not part_number or not any(c.isdigit() for c in part_number):
            continue

        rec = {c: "" for c in CANONICAL_COLUMNS}
        rec["PART_NAME"] = _clean_text(
            await _cell_text(img, v_lines[0], v_lines[1], ry0_pn, ry1_pn, psm=6))
        x0, x1 = v_lines[1], v_lines[2]
        xc = (x0 + x1) / 2
        ry0i, ry1i = _y_at(lo, hi, x_lo, x_hi, i, xc), _y_at(lo, hi, x_lo, x_hi, i + 1, xc)
        rec["ITEM_NO"] = _clean_digits(await _cell_text(img, x0, x1, ry0i, ry1i, whitelist=_DIGITS))
        rec["PART_NUMBER"] = part_number
        x0, x1 = v_lines[3], v_lines[4]
        xc = (x0 + x1) / 2
        ry0s, ry1s = _y_at(lo, hi, x_lo, x_hi, i, xc), _y_at(lo, hi, x_lo, x_hi, i + 1, xc)
        rec["SERIAL_NUMBER"] = _clean_alnum(await _cell_text(img, x0, x1, ry0s, ry1s))

        trail: list[str] = []
        split_notes: list[str] = []
        for col_idx, (label, keys) in _GROUPED_COLS.items():
            x0, x1 = v_lines[col_idx], v_lines[col_idx + 1]
            xc = (x0 + x1) / 2
            cry0 = _y_at(lo, hi, x_lo, x_hi, i, xc)
            cry1 = _y_at(lo, hi, x_lo, x_hi, i + 1, xc)
            dividers = _cell_dividers(dark, x0, x1, cry0, cry1)
            expected_dividers = len(keys) - 1
            if len(dividers) == expected_dividers:
                bounds = [cry0, *dividers, cry1]
                for key, (sy0, sy1) in zip(keys, zip(bounds[:-1], bounds[1:])):
                    rec[key] = _clean_digits(
                        await _cell_text(img, x0, x1, sy0, sy1, pad=2, whitelist=_DIGITS))
            else:
                raw = _clean_text(await _cell_text(img, x0, x1, cry0, cry1, pad=2, psm=6))
                if raw:
                    trail.append(f"{label}={raw}")
                split_notes.append(
                    f"{label}: expected {expected_dividers} divider(s), found {len(dividers)}"
                    " - verify against source PDF")

        rec["STATUS_TRAIL"] = "; ".join(trail)
        rec["_split_check"] = "OK" if not split_notes else "; ".join(split_notes)

        x0, x1 = v_lines[10], v_lines[11]
        ry0r, ry1r = hi[i], hi[i + 1]
        rec["REMARKS"] = _clean_text(await _cell_text(img, x0, x1, ry0r, ry1r, psm=6))

        rec.update(meta)
        records.append(rec)
    return records


async def extract(pdf_path: str) -> list[dict]:
    from shared.ocr_bridge import page_count

    n_pages = await page_count(pdf_path)
    records: list[dict] = []
    for p in range(n_pages):
        records.extend(await _extract_page(pdf_path, p))
    return records
