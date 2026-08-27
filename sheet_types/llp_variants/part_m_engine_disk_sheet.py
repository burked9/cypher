"""Part M Aviation Ireland — scanned engine LLP "Life Limited Parts (Engine
Disk Sheets) Time/Cycle Record".

Every page is a single flat scanned image with **no text layer**, so this
module renders each page and OCRs it via `shared/ocr_bridge.py`'s async
primitives (`render_page()`/`ocr_text()`/`ocr_words()`), which run on
fitz+pytesseract locally and on a JS/Tesseract.js bridge under Pyodide —
see that module's docstring for why the split exists.

Row shape: a MODULE section header (e.g. "HPC ROTOR MODULE") followed by one
row per component — DESCRIPTION, PART_NUMBER, SERIAL_NUMBER, then 4
rating-specific cycle limiters, 4 rating-specific cycle counts + a total, then
4 rating-specific remaining-cycles figures. Confirmed on two real source
files: the 4th rating's label varies per engine ("-7B24/3" vs "-A"), so
columns are named positionally (R1..R4) and the actual printed label is
captured per-record in RATING_4_LABEL etc.

Extraction strategy: detect the ruled grid directly (this is a photographed/
scanned table, not vector-drawn lines pdfplumber could see) by finding rows
and columns of near-continuous dark pixels, then OCR each cell independently.
Whole-row OCR reconstruction (the approach `levels/L3_ocr/extract.py` uses for
OCCM) was tried first and rejected: it assumes an ATA/ZONE row anchor this
sheet doesn't have, and even a from-scratch per-cell pass produced wrong
digits often enough (confirmed by hand against the source scans) that it
cannot be trusted blind.

Self-check, not blind trust: CYCLES_R1+R2+R3+R4 must equal TOTAL_CYCLES — this
held on every single row of both known source files, regardless of which
ratings apply to that part, making it a reliable, domain-independent signal
that a cell OCR'd wrong. Rows that fail it get `_cycles_sum_check` set to a
description of the mismatch instead of "OK", and should be treated as
unverified until someone checks them against the source PDF. This is a
best-effort OCR module on a genuinely hard scanned layout, not a substitute
for that check.

Known finding, not a bug: the "-5C4" rating's REMAINING figure is *never*
derivable from LIMIT-TOTAL on this sheet (confirmed wrong on nearly every row
that carries a numeric -5C4 limiter, across both known files) — Part M
evidently tracks it against some other basis not shown here. Never try to
re-derive REMAINING_R3; take the printed figure as authoritative.
"""
from __future__ import annotations

import re

import numpy as np
from PIL import ImageDraw

from sheet_types.llp_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, ocr_words

NAME = "Part M Engine Disk Sheet"

# No text layer ever exists on the known source files, so these will never
# actually fire through the router's normal text-signature match — they're
# here for interface consistency and in case a born-digital version of the
# same template ever turns up. Real detection happens via ocr_detect() below.
SIGNATURES = [
    "LIFE LIMITED PARTS (ENGINE DISK SHEETS)",
    "PART M AVIATION IRELAND",
]

_RATING_COLS = ["LIMITER_R1", "LIMITER_R2", "LIMITER_R3", "LIMITER_R4",
                "CYCLES_R1", "CYCLES_R2", "CYCLES_R3", "CYCLES_R4",
                "REMAINING_R1", "REMAINING_R2", "REMAINING_R3", "REMAINING_R4"]

CANONICAL_COLUMNS = [
    "MODULE", "DESCRIPTION", "PART_NUMBER", "SERIAL_NUMBER",
    *_RATING_COLS[0:4], *_RATING_COLS[4:8], "TOTAL_CYCLES", *_RATING_COLS[8:12],
    "RATING_1_LABEL", "RATING_2_LABEL", "RATING_3_LABEL", "RATING_4_LABEL",
    "ENGINE_MODEL", "ENGINE_SERIAL_NO", "REF_DATE", "ENG_TSN", "ENG_CSN",
    "TSSV", "CSSV", "INSTALLED_MSN", "INSTALLED_POSITION", "OPERATING_POWER_LBF",
]

_CYCLE_RULE = {"pattern": r"^(\d+|-|N/L)$", "allow_empty": True}
_OVERRIDES = {c: _CYCLE_RULE for c in [*_RATING_COLS, "TOTAL_CYCLES"]}
RULES = merged_rules(_OVERRIDES)

_ROW_LABEL_COLS = ["DESCRIPTION", "PART_NUMBER", "SERIAL_NUMBER", *_RATING_COLS[0:4],
                    *_RATING_COLS[4:8], "TOTAL_CYCLES", *_RATING_COLS[8:12]]


async def _render_page0(pdf_path: str, dpi: int = 300):
    return await render_page(pdf_path, 0, dpi=dpi)


def _collapse_and_dedup(idx: np.ndarray, merge_dist: int = 15) -> list[int]:
    """Collapse a run of adjacent dark rows/cols into one line position, then
    merge lines still within `merge_dist` px of each other (thick/double-drawn
    rules otherwise get detected twice, silently corrupting every downstream
    cell boundary)."""
    if len(idx) == 0:
        return []
    out, run = [], [int(idx[0])]
    for i in idx[1:]:
        if i - run[-1] <= 2:
            run.append(int(i))
        else:
            out.append(int(np.mean(run)))
            run = [int(i)]
    out.append(int(np.mean(run)))
    merged = [out[0]]
    for x in out[1:]:
        if x - merged[-1] <= merge_dist:
            merged[-1] = int((merged[-1] + x) / 2)
        else:
            merged.append(x)
    return merged


def _longest_dense_run(lines: list[int], max_gap: int = 150, min_run: int = 10) -> tuple[int, int] | None:
    """The data table is a dense run of closely-spaced ruled lines; the header
    info-box above it has the same kind of ruled lines but sparser. Find the
    longest run of consecutive lines whose gaps all stay under `max_gap`,
    rather than hardcoding where the table starts."""
    if len(lines) < min_run:
        return None
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
    if best_len < min_run:
        return None
    return lines[best_start], lines[best_start + best_len]


def _detect_table_grid(gray: np.ndarray) -> tuple[list[int], list[int]] | None:
    dark = gray < 128
    h, w = gray.shape
    full_h_lines = _collapse_and_dedup(np.where(dark.mean(axis=1) > 0.55)[0])
    band = _longest_dense_run(full_h_lines)
    if band is None:
        return None
    y0, y1 = band
    v_lines = _collapse_and_dedup(np.where(dark[y0:y1, :].mean(axis=0) > 0.5)[0])
    h_lines = _collapse_and_dedup(np.where(dark[:, v_lines[0]:v_lines[-1]].mean(axis=1) > 0.5)[0])
    h_lines = [y for y in h_lines if y0 - 5 <= y <= y1 + 5]
    if len(v_lines) != 17:
        # 16 data columns -> 17 dividing rules, always. Anything else means
        # the grid detection latched onto the wrong region (or a double-drawn
        # rule slipped past dedup) and every downstream cell boundary would
        # be garbage.
        return None
    return v_lines, h_lines


_JUNK_RE = re.compile(r"[^A-Za-z0-9/.\- ]")


def _clean_numeric_token(raw: str) -> str:
    """Post-OCR cleanup for a cell expected to be a cycle count, a limiter,
    or one of the sheet's two "not applicable" markers. Strips gridline-bleed
    punctuation before checking for the special tokens, since those come back
    from Tesseract as things like "| NL" or "' N/L" far more often than the
    clean literal string."""
    stripped = _JUNK_RE.sub("", raw).strip()
    upper = stripped.upper().replace(" ", "")
    if upper in ("NL", "N/L"):
        return "N/L"
    if stripped in ("-", "") or upper in ("", "-"):
        digits = re.sub(r"[^0-9]", "", raw)
        return digits if digits else "-"
    digits = re.sub(r"[^0-9]", "", stripped)
    return digits if digits else stripped


def _clean_text_token(raw: str) -> str:
    return _JUNK_RE.sub("", raw).strip()


async def _parse_header_metadata(img) -> dict:
    """The info box above the table (engine model/serial, ref date, TSN/CSN,
    TSSV/CSSV, installed MSN/position/power) is OCR'd as one block and
    regex-parsed rather than grid-detected — its layout is simpler and more
    variable than the main table, and these fields are cross-checked less
    critically than the per-part cycle figures."""
    w, h = img.size
    # Bounds measured against the rendered page (0.212-0.298 of height held
    # the full metadata box on both known files), not guessed -- the first
    # attempt at this crop (0.10-0.20) sat entirely above the real box and
    # every field silently came back empty.
    crop = img.crop((int(w * 0.02), int(h * 0.20), int(w * 0.99), int(h * 0.30)))
    text = await ocr_text(crop, psm=6)
    meta: dict[str, str] = {}

    def grab(pattern: str, key: str, cast=str):
        m = re.search(pattern, text, re.I)
        if m:
            val = m.group(1).strip().replace(",", "")
            try:
                meta[key] = cast(val)
            except ValueError:
                meta[key] = val

    grab(r"ENGINE MODEL:?\s*([A-Z0-9\-]+)", "ENGINE_MODEL")
    grab(r"ENGINE SERIAL NO:?\s*(\d+)", "ENGINE_SERIAL_NO")
    grab(r"Ref\s*Date:?\s*([\d\-A-Za-z]+)", "REF_DATE")
    grab(r"ENG\s*TSN:?\s*([\d,]+)", "ENG_TSN", int)
    grab(r"ENG\s*CSN:?\s*([\d,]+)", "ENG_CSN", int)
    grab(r"TSSV:?\s*([\d,]+)", "TSSV", int)
    grab(r"CSSV:?\s*([\d,]+)", "CSSV", int)
    grab(r"Installed\s*In\s*MSN:?\s*(\d+)", "INSTALLED_MSN")
    grab(r"Installed\s*Position:?\s*(#?\w+)", "INSTALLED_POSITION")
    grab(r"Operating\s*Power:?\s*([\d,]+)", "OPERATING_POWER_LBF", int)
    return meta


async def _ocr_row_bucketed(img, v_lines: list[int], ry0: int, ry1: int,
                             pad: int = 2, psm: int = 7) -> list[str]:
    """OCR one full row as a single wide strip and bucket words into columns
    by known x-position, instead of cropping each of the 16 columns
    separately.

    Confirmed by direct comparison on a real row: the exact same pixels read
    perfectly (every value correct) as one wide strip, but splitting into 16
    narrow per-cell crops — each left with only ~24px of usable height after
    padding — produced digit-concatenation garbage (e.g. "18230" misread as
    "48230"). Tesseract needs the surrounding row context; the column
    boundaries are already known precisely from grid detection, so bucketing
    by x-position after a full-row OCR keeps that precision without paying
    the per-cell-crop cost.
    """
    strip = img.crop((v_lines[0], ry0 + pad, v_lines[-1], ry1 - pad)).copy()
    # Internal column dividers are now inside the strip (only top/bottom got
    # padded away) and Tesseract reads each one as a spurious digit-like
    # mark that fuses onto the adjacent number -- confirmed by hand, this is
    # exactly what turned "20000" into "270000". Paint them out before OCR;
    # full-row context is still what we're after, not the divider ink.
    draw = ImageDraw.Draw(strip)
    for x in v_lines[1:-1]:
        bar = x - v_lines[0]
        # NOTE: fill=255 on an RGB image silently paints (255, 0, 0) -- solid
        # red, not white (confirmed directly: PIL only fills the first
        # channel). That red bar was reading as a dark value once Tesseract
        # converted to grayscale internally, which is exactly what was
        # producing spurious symbols at every column boundary.
        draw.rectangle([bar - 3, 0, bar + 3, strip.height], fill=(255, 255, 255))
    # min_conf=-1: the pre-migration pytesseract.image_to_data() DataFrame
    # path never filtered by confidence at all (only dropna(text) + a blank-
    # text check) -- ocr_words()'s own default (conf > 30) would silently
    # drop legitimate-but-low-confidence digits that the old code kept, on
    # exactly the kind of noisy scan this module's docstring already
    # documents (digit-concatenation misreads, gridline-bleed punctuation).
    # This module's own _clean_numeric_token()/_cycles_sum_check already
    # catch and flag garbage downstream, so keeping every recognized word
    # here (like the old code did) rather than dropping some of them is the
    # behavior-preserving choice.
    words = await ocr_words(strip, psm=psm, min_conf=-1)
    n_cols = len(v_lines) - 1
    buckets: list[list[tuple[int, str]]] = [[] for _ in range(n_cols)]
    for word in words:
        x_center = v_lines[0] + word["left"] + word["width"] / 2
        for i in range(n_cols):
            if v_lines[i] <= x_center < v_lines[i + 1]:
                buckets[i].append((int(word["left"]), str(word["text"])))
                break
    cells = []
    for bucket in buckets:
        bucket.sort(key=lambda t: t[0])
        cells.append(re.sub(r"\s+", " ", " ".join(t[1] for t in bucket)).strip())
    return cells


async def _parse_rating_labels(img, v_lines: list[int], h_lines: list[int]) -> dict:
    """Read the 4 rating labels once from the CYCLE LIMITERS sub-header band
    (the 2nd row-band) rather than assume they match the other known file —
    confirmed to vary per engine (e.g. "-7B24/3" vs "-A"). psm 6 (block, not
    single line) since these header cells wrap onto 2-3 lines."""
    cells = await _ocr_row_bucketed(img, v_lines, h_lines[1], h_lines[2], psm=6)
    labels = {}
    for i, key in enumerate(("RATING_1_LABEL", "RATING_2_LABEL", "RATING_3_LABEL", "RATING_4_LABEL")):
        txt = re.sub(r"LIMIT\s*@", "", cells[3 + i], flags=re.I).strip()
        labels[key] = txt if txt else f"R{i + 1}"
    return labels


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap header-only OCR check the router falls back to when a PDF has no
    usable text layer. Deliberately narrow (title + letterhead only) so a
    false match is unlikely and the cost stays low for the common case where
    this variant doesn't apply."""
    try:
        # 300dpi, not a cheaper lower res: confirmed by testing 150/200/300
        # side by side that "PART M" OCRs as "PARTMG"/"PARTM" (the logo's
        # swoosh graphic bleeds into the text) below 300dpi. Avoided the
        # fragile fix of chasing that specific misread and dropped "PART M"
        # entirely -- it's also a common EASA Part-M regulatory reference in
        # unrelated aviation documents generally, so it was a weak anchor
        # either way. "LIFE LIMITED PARTS" + "ENGINE DISK SHEETS" both read
        # cleanly at all three DPIs tested and are far more specific to this
        # exact template.
        img = await _render_page0(pdf_path, dpi=300)
        w, h = img.size
        # Letterhead + title band sits at roughly y=0.14-0.23 of page height
        # (confirmed against the rendered page, not guessed) -- cutting
        # through it vertically produces garbage OCR.
        crop = img.crop((0, int(h * 0.14), w, int(h * 0.23)))
        text = (await ocr_text(crop, psm=6)).upper()
        return "LIFE LIMITED PARTS" in text and "ENGINE DISK SHEETS" in text
    except Exception:
        return False


async def extract(pdf_path: str) -> list[dict]:
    img = await _render_page0(pdf_path, dpi=300)
    gray = np.array(img.convert("L"))
    grid = _detect_table_grid(gray)
    if grid is None:
        return []
    v_lines, h_lines = grid

    meta = await _parse_header_metadata(img)
    rating_labels = await _parse_rating_labels(img, v_lines, h_lines)

    records: list[dict] = []
    current_module = None
    # First 2 row-bands are the two header rows (super-header + sub-header) --
    # skip both, so start the (start, end) pairing from index 2, not 1.
    for ry0, ry1 in zip(h_lines[2:-1], h_lines[3:]):
        cells = await _ocr_row_bucketed(img, v_lines, ry0, ry1)
        desc = _clean_text_token(cells[0])
        if not desc:
            continue
        if "MODULE" in desc.upper():
            current_module = desc.upper()
            continue

        pn = _clean_text_token(cells[1])
        sn = _clean_text_token(cells[2])
        numeric_vals = [_clean_numeric_token(c) for c in cells[3:]]
        # numeric_vals order: LIMITER_R1..R4, CYCLES_R1..R4, TOTAL_CYCLES, REMAINING_R1..R4
        rec = dict(zip(_ROW_LABEL_COLS, [desc, pn, sn, *numeric_vals]))
        rec["MODULE"] = current_module or ""
        rec.update(rating_labels)
        rec.update(meta)

        cycles = [rec.get(f"CYCLES_R{n}") for n in (1, 2, 3, 4)]
        if all(c not in (None, "-", "N/L", "") for c in cycles):
            try:
                cycle_sum = sum(int(c) for c in cycles)
                total = int(rec.get("TOTAL_CYCLES", ""))
                rec["_cycles_sum_check"] = (
                    "OK" if cycle_sum == total
                    else f"MISMATCH: cycles sum to {cycle_sum}, TOTAL_CYCLES printed as {total} - verify against source PDF"
                )
            except ValueError:
                rec["_cycles_sum_check"] = "UNPARSEABLE: non-numeric cycle cell - verify against source PDF"
        else:
            rec["_cycles_sum_check"] = "SKIPPED: empty cycle cell - verify against source PDF"

        records.append(rec)
    return records
