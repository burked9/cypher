""""Hard Time Components Status" (A320 template), scanned/OCR-only.

Header (a known file in the corpus)::

    HARD TIME COMPONENTS STATUS | <tail no.> | <MSN> | <date> | <A/C hours>
    ATA | AMP Ref. | Description | P/N | S/N | Position | Installation Date |
    Requirements | Limits (Calendar/FH/FC) | Last Done at Component
    Utilisation (Date/FH/FC) | Next Due at Aircraft Utilisation (Date/FH/FC) |
    Remaining (Days/FH/FC)

20 ruled columns, no embedded text layer (pdfplumber.extract_text() returns
empty on every known file in this corpus) -- OCR-only end to end.

This variant's design goal is different from a typical first-pass parser:
grid-search row-divider detection on this file's known pages finds exactly
the right NUMBER of dividers per page (confirmed against real, independently
counted row totals across the 4 known pages in the corpus), but a handful of
the resulting row-slots turn out, on inspection, to hold no genuine table
content at all -- either a genuinely blank/rule-adjacent sliver between two
real rows (grid search sometimes plants one divider too many where a tall
wrapped DESCRIPTION crosses a rule), or a row whose identity-field cells
render so faintly that OCR hallucinates plausible-looking letter strings out
of near-blank pixels rather than failing cleanly. Both produce a row dict
that LOOKS like a candidate record but carries no real ATA/AMP_REF/PN/SN
content -- passing it through unflagged fabricates a component that was
never on the page.

_gate() below is a content-plausibility filter applied after OCR, not a
row-detection change: it drops (not flags) any candidate row whose identity
fields (AMP_REF/PN/SN) show no genuine digit-bearing identifier shape AND
whose DESCRIPTION isn't a substantial, letter-heavy multi-word fragment
paired with at least one non-empty identity field. Dropped rows are counted
in `extract()`'s return via the module-level `_last_drop_count` (best-effort
diagnostic, not part of the public record schema) rather than emitted as
records -- see _gate()'s docstring for the exact acceptance rule and the
false-positive check that shaped it (a duplicate/orphan DESCRIPTION-only
sliver next to a real row must NOT pass on description text alone).

Column x-positions are the validated per-page pixel coordinates carried
over from prior extraction attempts on this file (see _KNOWN_COL_LINES
below) rather than freshly grid-searched -- an attempted from-scratch
vertical column detector was tried during this module's development and
produced visibly misaligned columns on live testing, so it was reverted in
favor of the already-validated coordinates.

Cell text is read as ONE ocr_words() call per column per page (not one call
per cell) -- an OCR-quality fix, not a gate concern: a full-column crop
gives Tesseract far more contextual pixels per recognized token than a
individually-cropped, tightly-inset cell does, which is what let legible
rows upstream of the gate stop reading as blank/garbled in the first place.
Each recognized word is then assigned to its nearest row by vertical
distance to that row's mid-line (not by simple y-range membership, which
double-counts words whose box straddles two adjacent row slots on a tall
wrapped row).
"""
from __future__ import annotations
import re

import numpy as np

from sheet_types.ht_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_words, page_count

NAME = "Hard Time Components Status (Content-Gated, Scanned)"
SIGNATURES = []  # structural detection only -- see ocr_detect()

CANONICAL_COLUMNS = [
    "ATA", "AMP_REF", "DESCRIPTION", "PN", "SN", "POSITION", "INSTALL_DATE",
    "REQUIREMENTS",
    "LIMITS_CAL", "LIMITS_FH", "LIMITS_FC",
    "LASTDONE_DATE", "LASTDONE_FH", "LASTDONE_FC",
    "NEXTDUE_DATE", "NEXTDUE_FH", "NEXTDUE_FC",
    "REMAIN_DAYS", "REMAIN_FH", "REMAIN_FC",
]

_OVERRIDES = {c: {"allow_empty": True} for c in CANONICAL_COLUMNS}
_OVERRIDES["ATA"] = {"pattern": r"^\d{1,3}$", "allow_empty": True}
RULES = merged_rules(_OVERRIDES)

# ---------------------------------------------------------------------------
# Row-divider grid search (validated separately from the content gate: on
# the 4 known pages this finds exactly the right divider COUNT -- 39/35/28
# (well, page-count-dependent) dividers bracketing 38/33/26/12 row-slots --
# see this module's docstring for why row-slot count alone isn't sufficient
# evidence that every slot holds real content).
# ---------------------------------------------------------------------------
_WIN = 4
_DARKS = (120, 140, 160, 180, 200, 220, 240, 253)
_FRACS = (0.2, 0.25, 0.3, 0.35, 0.4, 0.5, 0.6, 0.7)


def _windowed_dark(arr: np.ndarray, dark: int) -> np.ndarray:
    h, w = arr.shape
    m = arr < dark
    out = np.zeros_like(m)
    for y in range(h):
        y1 = min(h, y + _WIN)
        out[y] = m[y:y1].any(axis=0)
    return out


def _raw_peaks(wm, x0, x1, y_lo, y_hi, frac_thresh, merge_px=6):
    frac = wm[y_lo:y_hi, x0:x1].mean(axis=1)
    ys = np.where(frac > frac_thresh)[0]
    groups = []
    for y in ys:
        if groups and y - groups[-1][-1] <= merge_px:
            groups[-1].append(y)
        else:
            groups.append([y])
    return [y_lo + int(np.mean(g)) for g in groups]


def _seg_rel_coverage(wm, y, col_lines, half=4, inset=4, bg_half=12, rel_mult=1.6):
    h, w = wm.shape
    y0, y1 = max(0, y - half), min(h, y + half + 1)
    by0, by1 = max(0, y - bg_half), min(h, y + bg_half + 1)
    hits = total = 0
    for cx0, cx1 in zip(col_lines[:-1], col_lines[1:]):
        sx0, sx1 = cx0 + inset, cx1 - inset
        if sx1 <= sx0:
            continue
        total += 1
        local = wm[y0:y1, sx0:sx1].mean()
        bg = wm[by0:by1, sx0:sx1].mean()
        if local > max(bg * rel_mult, 0.15):
            hits += 1
    return hits / total if total else 0.0


# Column x-positions (21 ruled lines bracketing the 20 canonical columns),
# read directly off this file's known pages at 300 DPI -- validated across
# several prior extraction attempts against rendered crops (see this
# module's docstring). An attempted from-scratch vertical grid-search
# replacement (transposing _row_dividers' horizontal logic onto the X axis)
# was tried here and PRODUCED MISALIGNED COLUMNS on live testing (ATA/
# AMP_REF/DESCRIPTION cells shifted by roughly one column, corrupting
# otherwise-legible rows) -- reverted in favor of these validated
# coordinates rather than ship an unvalidated column-detector. A page whose
# index isn't in this table (i.e. beyond the 4 known pages) falls back to
# the nearest known page's column set, which only matters if this exact
# file ever grows extra pages.
_KNOWN_COL_LINES = {
    0: [238, 331, 476, 650, 824, 1022, 1129, 1260, 1421, 1552, 1682, 1813, 1944, 2142, 2273, 2403, 2534, 2664, 2812, 2947, 3095],
    1: [255, 348, 492, 666, 839, 1036, 1143, 1273, 1433, 1564, 1694, 1825, 1956, 2154, 2284, 2414, 2545, 2675, 2822, 2957, 3105],
    2: [237, 331, 476, 650, 823, 1023, 1130, 1261, 1421, 1552, 1683, 1814, 1946, 2144, 2275, 2405, 2536, 2666, 2814, 2949, 3097],
    3: [251, 343, 487, 661, 834, 1031, 1137, 1268, 1428, 1559, 1689, 1820, 1951, 2149, 2279, 2410, 2540, 2671, 2818, 2953, 3100],
}


def _col_lines_for_page(page_index: int, prev_col_lines: list[int] | None) -> list[int] | None:
    if page_index in _KNOWN_COL_LINES:
        return _KNOWN_COL_LINES[page_index]
    return prev_col_lines


def _table_top(words_top_band: list[dict], fallback: int) -> int:
    for w in words_top_band:
        if w["text"].strip().upper() == "ATA":
            return int(w["top"] + w["height"])
    return fallback


def _row_dividers(arr: np.ndarray, col_lines: list[int], top: int) -> list[int]:
    h, w = arr.shape
    x0, x1 = col_lines[0], col_lines[-1]
    best = []
    for dark in _DARKS:
        wm = _windowed_dark(arr, dark)
        for frac in _FRACS:
            peaks = _raw_peaks(wm, x0, x1, top, h, frac)
            strong = [y for y in peaks if _seg_rel_coverage(wm, y, col_lines) > 0.4]
            if len(strong) > len(best):
                best = strong
    divs = sorted(set([top] + best))
    out = [divs[0]]
    for d in divs[1:]:
        if d - out[-1] < 20:
            continue
        out.append(d)
    return out


# ---------------------------------------------------------------------------
# Content-plausibility gate.
# ---------------------------------------------------------------------------
_VARIOUS_RE = re.compile(r"^[\'\"‘’]?\s*various", re.I)


def _digits(s: str) -> int:
    return sum(c.isdigit() for c in s)


def _alnum_ratio(s: str) -> float:
    s2 = s.replace(" ", "")
    if not s2:
        return 0.0
    return sum(c.isalnum() for c in s2) / len(s2)


def _shape_ok(s: str) -> tuple[bool, bool]:
    """Returns (passes, is_various_literal). A field passes if it reads as
    a genuine digit-bearing identifier (>=2 digits, >=55% alnum density,
    >=3 non-space chars) -- e.g. AMP_REF '256652-01-1', PN '63600-545' --
    or if it's the literal 'Various' token (a real, non-numeric SN value
    this report uses for multi-unit components, e.g. life vests)."""
    s = s.strip()
    if not s:
        return False, False
    if _VARIOUS_RE.match(s):
        return True, True
    if _digits(s) < 2 or _alnum_ratio(s) < 0.55 or len(s.replace(" ", "")) < 3:
        return False, False
    return True, False


def _desc_ok(s: str) -> bool:
    """A genuine multi-word, letter-heavy DESCRIPTION fragment -- 'AIR
    RELEASE VALVE', 'RAT ACTUATOR' -- vs. noise. Deliberately NOT sufficient
    on its own (see _gate()): a single common word like 'HEAT' left over
    from a wrapped neighbor row's DESCRIPTION passes a looser version of
    this check and must still be rejected by the overall gate."""
    s = s.strip(" |'\"")
    if not s:
        return False
    compact = s.replace(" ", "")
    letters = sum(c.isalpha() for c in s)
    ratio = letters / max(1, len(compact))
    words = [w for w in s.split() if len(w) >= 2]
    return ratio >= 0.75 and (len(words) >= 3 or len(compact) >= 10)


def _gate(rec: dict) -> bool:
    """True = keep. Two independent paths to acceptance:

    1. MAIN: at least one of AMP_REF/PN/SN individually passes _shape_ok(),
       AND (the combined AMP_REF+PN+SN digit count is >=4, OR one of those
       fields is the literal 'Various'). This is the primary signal -- real
       rows in this report carry a numeric-heavy identifier in at least one
       identity field even when OCR mangles the others.

    2. FALLBACK: DESCRIPTION passes _desc_ok() (a substantial, real-looking
       multi-word fragment) AND at least one of AMP_REF/PN/SN is non-empty
       with at least one digit in it -- catches rows where the identity
       fields are present but too short/degraded to hit the MAIN digit
       threshold (e.g. AMP_REF read as a single stray digit) while a
       neighboring field or DESCRIPTION still carries evidence.

    A description-only row (all three identity fields completely empty)
    is REJECTED even if DESCRIPTION reads perfectly plausibly -- validated
    directly against a true duplicate/orphan case in this file's corpus:
    a "HEAT EXCHANGER" row's tall wrapped DESCRIPTION crossed a rule the
    grid search also (correctly, by its own logic) treated as a divider,
    producing an extra row-slot with a legible-looking 2-word DESCRIPTION
    fragment ('... EXCHANGER,') and completely empty AMP_REF/PN/SN -- a
    DESCRIPTION-alone acceptance rule would have kept it as a phantom
    duplicate of the real row next to it.
    """
    amp, pn, sn = rec.get("AMP_REF", ""), rec.get("PN", ""), rec.get("SN", "")
    desc = rec.get("DESCRIPTION", "")
    amp_ok, amp_var = _shape_ok(amp)
    pn_ok, pn_var = _shape_ok(pn)
    sn_ok, sn_var = _shape_ok(sn)
    shape_hits = sum([amp_ok, pn_ok, sn_ok])
    any_various = amp_var or pn_var or sn_var
    digit_score = _digits(amp) + _digits(pn) + _digits(sn)
    main_ok = shape_hits >= 1 and (digit_score >= 4 or any_various)
    fallback_ok = _desc_ok(desc) and any(_digits(x) >= 1 for x in (amp, pn, sn) if x.strip())
    return main_ok or fallback_ok


# ---------------------------------------------------------------------------
# Extraction.
# ---------------------------------------------------------------------------
_COLUMN_ORDER = CANONICAL_COLUMNS


def _merge_words(words: list[dict]) -> str:
    return " ".join(w["text"] for w in sorted(words, key=lambda w: w["top"])).strip()


async def _ocr_column(img, x0: int, x1: int, y0: int, y1: int) -> list[dict]:
    if x1 <= x0 or y1 <= y0:
        return []
    crop = img.crop((x0, y0, x1, y1))
    words = await ocr_words(crop, psm=6, min_conf=-1)
    out = []
    for w in words:
        out.append({
            "text": str(w["text"]).strip(),
            "top": y0 + float(w["top"]),
            "height": float(w["height"]),
        })
    return [w for w in out if w["text"]]


async def _extract_page(img, page_index: int, page_num: int, prev_col_lines: list[int] | None):
    arr = np.array(img.convert("L"))
    h, w = arr.shape

    header_words = await ocr_words(img.crop((0, 300, w, 900)), psm=6, min_conf=-1)
    header_words = [{"text": str(x["text"]), "top": 300 + float(x["top"]), "height": float(x["height"])}
                     for x in header_words]

    col_lines = _col_lines_for_page(page_index, prev_col_lines)
    if col_lines is None:
        return [], None, 0

    top = _table_top(header_words, fallback=350)
    rows = _row_dividers(arr, col_lines, top)
    if len(rows) < 2:
        return [], col_lines, 0

    col_bounds = list(zip(col_lines[:-1], col_lines[1:]))[:20]
    y_bottom = min(h, rows[-1] + 40)

    col_words: dict[str, list[dict]] = {}
    for name, (x0, x1) in zip(_COLUMN_ORDER, col_bounds):
        col_words[name] = await _ocr_column(img, x0, x1, rows[0], y_bottom)

    row_centers = [(rows[i] + rows[i + 1]) / 2 for i in range(len(rows) - 1)]
    slots = [{"_page": page_num, "_y0": rows[i], "_y1": rows[i + 1]} for i in range(len(rows) - 1)]
    for name in _COLUMN_ORDER:
        for slot in slots:
            slot[name] = []
        for wd in col_words[name]:
            wc = wd["top"] + wd["height"] * 0.3
            best_i = min(range(len(row_centers)), key=lambda i: abs(row_centers[i] - wc))
            slots[best_i][name].append(wd)

    records, dropped = [], 0
    for slot in slots:
        rec = {"_page": slot["_page"]}
        for name in _COLUMN_ORDER:
            rec[name] = _merge_words(slot[name])
        if _gate(rec):
            records.append(rec)
        else:
            dropped += 1
    return records, col_lines, dropped


async def ocr_detect(pdf_path: str) -> bool:
    try:
        img = await render_page(pdf_path, 0, dpi=300)
        words = await ocr_words(img.crop((0, 0, img.width, 545)), psm=6, min_conf=-1)
        text = " ".join(str(w["text"]) for w in words).upper()
    except Exception:
        return False
    has_title = "HARD TIME COMPONENTS STATUS" in re.sub(r"\s+", " ", text)
    has_cols = ("UTILISATION" in text) and ("NEXT DUE" in re.sub(r"\s+", " ", text) or "NEXTDUE" in text)
    return has_title and has_cols


async def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    n_pages = await page_count(pdf_path)
    col_lines = None
    total_dropped = 0
    for page_index in range(n_pages):
        img = await render_page(pdf_path, page_index, dpi=300)
        page_records, col_lines, dropped = await _extract_page(img, page_index, page_index + 1, col_lines)
        records.extend(page_records)
        total_dropped += dropped
    global _last_drop_count
    _last_drop_count = total_dropped
    return records


# Best-effort diagnostic only (not part of the public record schema) --
# number of candidate row-slots the gate dropped on the most recent
# extract() call, for logging/debugging.
_last_drop_count = 0
