"""APU "LIFE LIMITED PARTS STATUS" sheet -- a per-APU life-limited-parts
inventory for a GTCP131-9B-family APU, referencing an Engine Manual chapter
(e.g. "Engine Manual <chapter> / Revision <n> - <date>"). Confirmed on one
known real source file: single page, landscape, 0-char text layer (a clean
computer-rendered raster with a company logo, not a photographed form) --
this variant is OCR-only, reached purely through `ocr_detect()` below, same
as kalstar_engine_llp_status.py and part_m_engine_disk_sheet.py.

Header layout (values below are placeholders, not from any real file)::

    <operator logo>          LIFE LIMITED PARTS STATUS
                       Engine Manual <chapter> / Revision <n> - <date>
    A/C: <reg> - MSN <msn>
    Type: <apu type>                    +-------------------------+
    ESN: <esn>                           | Last shop visit @       |
    Date: <date>                        +--------+--------+-------+
    Reason for status: <reason>         | TSN | <n>  | TSSV | <n>  |
                                         | CSN | <n>  | CSSV | <n>  |
                                         +--------+--------+-------+
    TSN: <n>
    CSN: <n>

    MODULES | Part Number | Serial Number | Life Limit Cycles | CSN at
    build | CSN total | Available Cycles
    (one row per life-limited module/part -- 4 real rows on the one known
    source file)

TSN/CSN below the box are the APU's current total time/cycles since new;
the boxed "Last shop visit @" figures are the TSN/CSN recorded AT that last
shop visit, and TSSV/CSSV are time/cycles accrued SINCE it -- confirmed
directly on the one known file: TSN == (boxed TSN) + TSSV and
CSN == (boxed CSN) + CSSV, exactly, giving a free header self-check (see
`_header_check` below). There is only ever one physical unit on this sheet
(the APU itself, tracked by ESN) -- no separate "engine" figures exist here
despite the "Engine Manual" chapter reference in the title, which is just
the manual family name APU life-limit data is published under.

A signature block below the table (a "Checked by" line plus a printed
stamp with a name, a title, and the operator's own name) is deliberately
NOT extracted into any column -- it carries no life-limit data and every
one of its fields is a real person's name / real operator name on an
actual source file, which this codebase must never propagate into example
rows or comments (see this module's own commit history / project notes on
why). If a future need arises for a "certified by" column, add it as a
free-text field fed straight from OCR, never hand-hardcoded here.

Extraction strategy, mirroring part_m_engine_disk_sheet.py: detect the
table's own ruled grid directly (near-continuous dark pixel rows/columns)
rather than assume fixed pixel coordinates, since this is a rendered-not-
guaranteed-identical-every-time raster. Confirmed on the one known file:
the table has exactly 8 vertical rules (7 columns: MODULE, PART_NUMBER,
SERIAL_NUMBER, LIFE_LIMIT_CYCLES, CSN_AT_BUILD, CSN_TOTAL,
AVAILABLE_CYCLES) and 6 horizontal rules (1 header band + 4 data rows) --
both counts are asserted in `_detect_table_grid()`; anything else means the
grid detection latched onto the wrong region and every downstream cell
boundary would be garbage, so it returns None rather than guess.

Row cells are OCR'd as a full-width strip per row (not per-cell crops),
with the internal column dividers painted out first -- the same technique
part_m_engine_disk_sheet.py's `_ocr_row_bucketed()` documents finding
necessary on its own scanned grid (per-cell crops there produced
digit-concatenation garbage; full-row-then-bucket-by-x-position did not).
Confirmed necessary here too by direct comparison.

Self-check, not blind trust: on every row of the one known file,
AVAILABLE_CYCLES == LIFE_LIMIT_CYCLES - CSN_TOTAL exactly. Rows that fail
this get `_availability_check` set to a mismatch description instead of
"OK", flagging that row as unverified rather than silently trusting a
misread digit -- the same "never guess a wrong split" principle
part_m_engine_disk_sheet.py's cycle-sum check documents. Likewise the
header box's own arithmetic (TSN == boxed TSN + TSSV, CSN == boxed CSN +
CSSV) is checked and recorded in `_header_check`.

The "Last shop visit @" info box's own column x-positions were confirmed
(on the one known file) to align with the main table's own v_lines[3:8]
(its 4 columns sit directly above the table's CSN_AT_BUILD..
AVAILABLE_CYCLES column group) -- so the box is read using the table's own
detected column lines rather than a second, separately-detected column
grid; only the box's 4 *row* lines need their own (narrow, x-restricted)
detection, since the box's row height and vertical position are not
implied by anything already known. This has only been confirmed on one
source file; if a second file's box columns don't line up the same way,
`_parse_lsv_box()` returns an empty dict rather than misattribute a cell.

One real, uncorrected imperfection observed directly and left as-is:
tesseract sometimes emits stray punctuation (`|`, an em-dash run, `=`,
`«`) at cell edges where the freshly-painted-white divider bar meets
faint anti-aliasing -- `_clean_numeric()`/`_clean_alnum()` strip anything
outside `[0-9A-Za-z\-*]` (or digits-only for numeric cells) rather than try
to special-case every OCR artifact seen; a genuine SERIAL_NUMBER footnote
marker (a trailing `*`, referencing a "not listed in <service bulletin>"
note below the table on the one known file) is deliberately preserved by
that same allow-list rather than stripped as noise.
"""
from __future__ import annotations

import re

import numpy as np
from PIL import ImageDraw

from sheet_types.llp_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, ocr_words

NAME = "APU LLP Inventory"

# Every known source file has a 0-char text layer (see module docstring) --
# router.py's blank-text fallback reaches this module purely through
# ocr_detect() below, same as kalstar_engine_llp_status.py /
# part_m_engine_disk_sheet.py. Deliberately empty rather than populated with
# a guess, so there is nothing here to collide with any other variant's
# text-signature list.
SIGNATURES: list[str] = []

CANONICAL_COLUMNS = [
    "MODULE",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "LIFE_LIMIT_CYCLES",
    "CSN_AT_BUILD",
    "CSN_TOTAL",
    "AVAILABLE_CYCLES",
    # File-level header metadata -- same on every row of a given file.
    "AIRCRAFT_REG",
    "MSN",
    "APU_TYPE",
    "ESN",
    "STATUS_DATE",
    "REASON_FOR_STATUS",
    "ENGINE_MANUAL_CHAPTER",
    "REVISION",
    "REVISION_DATE",
    "LSV_TSN",
    "LSV_CSN",
    "TSSV",
    "CSSV",
    "TSN",
    "CSN",
]

_INT_RULE = {"pattern": r"^\d*$", "allow_empty": True}
_OVERRIDES = {
    "PART_NUMBER":            {"pattern": r"^[A-Z0-9\-]+$", "uppercase": True, "allow_empty": True},
    "SERIAL_NUMBER":          {"pattern": r"^[A-Z0-9\-]+\*?$", "uppercase": True, "allow_empty": True},
    "LIFE_LIMIT_CYCLES":      _INT_RULE,
    "CSN_AT_BUILD":           _INT_RULE,
    "CSN_TOTAL":              _INT_RULE,
    "AVAILABLE_CYCLES":       _INT_RULE,
    "AIRCRAFT_REG":           {"pattern": r"^[A-Z0-9\-]*$", "uppercase": True, "allow_empty": True},
    "MSN":                    _INT_RULE,
    "APU_TYPE":               {"allow_empty": True},
    "ESN":                    {"pattern": r"^[A-Z0-9\-]*$", "uppercase": True, "allow_empty": True},
    "STATUS_DATE":            {"pattern": r"^(\d{1,2}-[A-Za-z]{3,9}-\d{2,4})?$", "allow_empty": True},
    "REASON_FOR_STATUS":      {"allow_empty": True},
    "ENGINE_MANUAL_CHAPTER":  {"pattern": r"^[\d\-]*$", "allow_empty": True},
    "REVISION":               _INT_RULE,
    "REVISION_DATE":          {"allow_empty": True},
    "LSV_TSN":                _INT_RULE,
    "LSV_CSN":                _INT_RULE,
    "TSSV":                   _INT_RULE,
    "CSSV":                   _INT_RULE,
    "TSN":                    _INT_RULE,
    "CSN":                    _INT_RULE,
}
RULES = merged_rules(_OVERRIDES)

_ROW_COLS = ["MODULE", "PART_NUMBER", "SERIAL_NUMBER", "LIFE_LIMIT_CYCLES",
             "CSN_AT_BUILD", "CSN_TOTAL", "AVAILABLE_CYCLES"]

_N_TABLE_COLS = 7  # MODULES, Part Number, Serial Number, Life Limit Cycles,
                   # CSN at build, CSN total, Available Cycles -- 8 v_lines.

_ALNUM_JUNK_RE = re.compile(r"[^A-Za-z0-9\-*]")
_TEXT_JUNK_RE = re.compile(r"[^A-Za-z0-9 ]")


def _clean_numeric(raw: str) -> str:
    return re.sub(r"[^0-9]", "", raw)


def _clean_alnum(raw: str) -> str:
    return _ALNUM_JUNK_RE.sub("", raw).upper()


def _clean_module(raw: str) -> str:
    return re.sub(r"\s+", " ", _TEXT_JUNK_RE.sub("", raw)).strip()


def _collapse_and_dedup(idx: np.ndarray, merge_dist: int = 15) -> list[int]:
    """Collapse a run of adjacent dark rows/cols into one line position, then
    merge lines still within `merge_dist` px of each other -- mirrors
    part_m_engine_disk_sheet.py's helper of the same name (thick/double-
    drawn rules otherwise get detected twice, corrupting every downstream
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


def _longest_dense_run(lines: list[int], max_gap: int = 150, min_run: int = 4) -> tuple[int, int] | None:
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
    """Same dense-run-of-ruled-lines strategy as
    part_m_engine_disk_sheet.py's function of the same name, with this
    sheet's own confirmed line counts (8 v_lines / 7 columns, 6 h_lines / 5
    row-bands: 1 header + 4 data rows)."""
    dark = gray < 128
    full_h_lines = _collapse_and_dedup(np.where(dark.mean(axis=1) > 0.55)[0])
    band = _longest_dense_run(full_h_lines)
    if band is None:
        return None
    y0, y1 = band
    v_lines = _collapse_and_dedup(np.where(dark[y0:y1, :].mean(axis=0) > 0.5)[0])
    if len(v_lines) != _N_TABLE_COLS + 1:
        return None
    h_lines = _collapse_and_dedup(np.where(dark[:, v_lines[0]:v_lines[-1]].mean(axis=1) > 0.5)[0])
    h_lines = [y for y in h_lines if y0 - 5 <= y <= y1 + 5]
    if len(h_lines) != 6:
        return None
    return v_lines, h_lines


async def _ocr_row_bucketed(img, v_lines: list[int], ry0: int, ry1: int,
                             pad: int = 2, psm: int = 7) -> list[str]:
    """OCR one full row as a single wide strip, painting out the internal
    column dividers first, then bucket words into columns by known
    x-position -- see module docstring for why this beats per-cell crops
    on this sheet, mirroring part_m_engine_disk_sheet.py's
    `_ocr_row_bucketed()`."""
    strip = img.crop((v_lines[0], ry0 + pad, v_lines[-1], ry1 - pad)).copy()
    draw = ImageDraw.Draw(strip)
    for x in v_lines[1:-1]:
        bar = x - v_lines[0]
        # fill=255 on an RGB image only fills the red channel -- use an
        # explicit (255, 255, 255) white fill (confirmed against the same
        # pitfall documented in part_m_engine_disk_sheet.py).
        draw.rectangle([bar - 3, 0, bar + 3, strip.height], fill=(255, 255, 255))
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


def _detect_lsv_box_hlines(gray: np.ndarray, x0: int, x1: int, table_top: int,
                            search_height: int = 450, thresh: float = 0.35) -> list[int] | None:
    """Find the "Last shop visit @" info box's own 4 row-lines (box top,
    TSN/TSSV row top, CSN/CSSV row top, box bottom) by scanning dark-pixel
    density restricted to the box's own x-range (`x0`:`x1`, confirmed on
    the one known file to align with the main table's v_lines[3:8]) in the
    band directly above the main table's top border. Restricting to the
    box's own (narrower-than-page) x-range is what makes these lines
    detectable at all -- a full-page-width scan (as used for the main
    table) sees this box's lines as far too small a fraction of the row to
    cross any reasonable darkness threshold, confirmed directly."""
    y_top = max(0, table_top - search_height)
    y_bot = table_top - 10  # stop short of the table's own top border
    if y_bot <= y_top:
        return None
    dark = gray < 128
    frac = dark[y_top:y_bot, x0:x1].mean(axis=1)
    idx = np.where(frac > thresh)[0]
    lines = _collapse_and_dedup(idx, merge_dist=10)
    if len(lines) != 4:
        return None
    return [y_top + v for v in lines]


async def _parse_lsv_box(img, v_lines: list[int], table_top: int) -> dict:
    """Read the "Last shop visit @" box's TSN/CSN (at last shop visit) and
    TSSV/CSSV (since last shop visit) figures, reusing the main table's own
    column lines (see module docstring) -- returns {} if the box's own row
    lines can't be confirmed, rather than guess."""
    box_x0, box_x1 = v_lines[3], v_lines[-1]
    box_h = _detect_lsv_box_hlines(np.array(img.convert("L")), box_x0, box_x1, table_top)
    if box_h is None:
        return {}
    box_v = v_lines[3:]  # 5 positions -> 4 columns: label, value, label, value
    meta: dict[str, str] = {}
    field_map = (("LSV_TSN", "TSSV"), ("LSV_CSN", "CSSV"))
    for row_i, (val_key, val2_key) in enumerate(field_map):
        cells = await _ocr_row_bucketed(img, box_v, box_h[row_i + 1], box_h[row_i + 2])
        if len(cells) == 4:
            meta[val_key] = _clean_numeric(cells[1])
            meta[val2_key] = _clean_numeric(cells[3])
    return meta


async def _parse_header_fields(img, left_x1: int) -> dict:
    """Key:value header fields (A/C reg+MSN, Type, ESN, Date, Reason for
    status) OCR'd as one block and regex-parsed -- a single left-aligned
    column with no repeated labels, so (unlike kalstar_engine_llp_status.py's
    4-column header) there is no attribution ambiguity to resolve here.
    `left_x1` caps the crop's right edge at the "Last shop visit @" box's
    own left edge so this OCR pass never bleeds into the box's content."""
    w, h = img.size
    # Lower bound confirmed against the rendered page to reach through the
    # "Reason for status" line without also reaching the "Last shop visit @"
    # box (kept out entirely by `left_x1`, not by this y bound).
    crop = img.crop((0, int(h * 0.25), left_x1, int(h * 0.41)))
    text = await ocr_text(crop, psm=6)
    meta: dict[str, str] = {}

    def grab(pattern: str, key: str):
        m = re.search(pattern, text, re.I)
        if m:
            meta[key] = m.group(1).strip()

    m = re.search(r"A[/I1]C:?\s*([A-Z0-9\-]+)\s*-\s*MSN\s*(\d+)", text, re.I)
    if m:
        meta["AIRCRAFT_REG"] = m.group(1).strip().upper()
        meta["MSN"] = m.group(2).strip()
    grab(r"Type:?\s*([A-Z0-9 \-]+?)(?:\n|$)", "APU_TYPE")
    grab(r"\bESN:?\s*([A-Z0-9\-]+)", "ESN")
    grab(r"\bDate:?\s*(\d{1,2}-[A-Za-z]{3,9}-\d{2,4})", "STATUS_DATE")
    grab(r"Reason for status:?\s*(.+?)(?:\n|$)", "REASON_FOR_STATUS")
    if "APU_TYPE" in meta:
        meta["APU_TYPE"] = meta["APU_TYPE"].strip()
    return meta


async def _parse_title_block(img) -> dict:
    """The bold title line and the smaller "Engine Manual <chapter> /
    Revision <n> - <date>" line below it must be OCR'd as two SEPARATE
    tight crops, not one combined block -- confirmed directly: combining
    them (or including the operator's logo graphic to the left) reliably
    corrupts the smaller line's digits (e.g. a real chapter/date misread as
    garbage), while a crop isolating just that line alone reads perfectly
    at every psm mode tried. Fractions below were measured against the
    rendered page, not guessed."""
    w, h = img.size
    manual_crop = img.crop((0, int(h * 0.215), w, int(h * 0.25)))
    text = await ocr_text(manual_crop, psm=6)
    meta: dict[str, str] = {}
    m = re.search(r"Engine\s+Manual\s+([\d\-]+)", text, re.I)
    if m:
        meta["ENGINE_MANUAL_CHAPTER"] = m.group(1)
    m = re.search(r"Revision\s+(\d+)\s*-\s*(.+?)\s*$", text, re.I)
    if m:
        meta["REVISION"] = m.group(1)
        meta["REVISION_DATE"] = m.group(2).strip()
    return meta


async def _parse_current_tsn_csn(img, box_bottom: int, table_top: int) -> dict:
    """The APU's current total TSN/CSN sit as plain (unruled) text between
    the "Last shop visit @" box's bottom and the main table's top border --
    OCR'd as one small block and regex-parsed."""
    w, _ = img.size
    crop = img.crop((0, box_bottom, w, table_top))
    text = await ocr_text(crop, psm=6)
    meta: dict[str, str] = {}
    m = re.search(r"\bTSN:?\s*([\d,]+)", text, re.I)
    if m:
        meta["TSN"] = m.group(1).replace(",", "")
    m = re.search(r"\bCSN:?\s*([\d,]+)", text, re.I)
    if m:
        meta["CSN"] = m.group(1).replace(",", "")
    return meta


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap header-only OCR check the router falls back to when a PDF has
    no usable text layer. Requires BOTH the sheet's title phrase and the
    APU type code together: "LIFE LIMITED PARTS STATUS" alone is a
    substring of thai_landing_gear_llp_status.py's own title phrase
    ("LANDING GEAR LIFE LIMITED PARTS STATUS") and would false-match its
    files if used alone; "GTCP" (a specific APU model family prefix) is
    never going to appear on that or any other known LLP variant's title
    crop, so the AND makes this collision-free regardless of VARIANTS list
    order. Checked directly against every other llp_variants/*.py
    ocr_detect() title phrase; no collision found."""
    try:
        img = await render_page(pdf_path, 0, dpi=300)
        w, h = img.size
        crop = img.crop((0, int(h * 0.16), w, int(h * 0.34)))
        text = (await ocr_text(crop, psm=6)).upper()
        return "LIFE LIMITED PARTS STATUS" in text and "GTCP" in text
    except Exception:
        return False


async def extract(pdf_path: str) -> list[dict]:
    img = await render_page(pdf_path, 0, dpi=300)
    gray = np.array(img.convert("L"))
    grid = _detect_table_grid(gray)
    if grid is None:
        return []
    v_lines, h_lines = grid
    table_top = h_lines[0]

    title_meta = await _parse_title_block(img)
    field_meta = await _parse_header_fields(img, v_lines[3])
    lsv_meta = await _parse_lsv_box(img, v_lines, table_top)
    box_bottom = None
    if lsv_meta:
        box_h = _detect_lsv_box_hlines(gray, v_lines[3], v_lines[-1], table_top)
        if box_h:
            box_bottom = box_h[-1]
    # Fall back to a fixed offset above the table if the box itself wasn't
    # confirmed -- still keeps the current-TSN/CSN crop well clear of the
    # header field lines above it on the one known file's layout.
    tsn_csn_meta = await _parse_current_tsn_csn(
        img, box_bottom if box_bottom is not None else table_top - 160, table_top)

    meta: dict[str, str] = {}
    meta.update(title_meta)
    meta.update(field_meta)
    meta.update(lsv_meta)
    meta.update(tsn_csn_meta)

    # Header self-check: TSN/CSN below the box must equal the boxed
    # (at-last-shop-visit) figure plus the since-shop-visit figure --
    # confirmed exact on the one known file. Flag rather than trust blindly
    # if a digit misread breaks the arithmetic.
    header_check = "SKIPPED: insufficient fields to verify"
    try:
        if all(k in meta for k in ("TSN", "LSV_TSN", "TSSV", "CSN", "LSV_CSN", "CSSV")):
            tsn_ok = int(meta["TSN"]) == int(meta["LSV_TSN"]) + int(meta["TSSV"])
            csn_ok = int(meta["CSN"]) == int(meta["LSV_CSN"]) + int(meta["CSSV"])
            header_check = "OK" if (tsn_ok and csn_ok) else (
                "MISMATCH: TSN/CSN do not equal last-shop-visit figure + since-shop-visit figure "
                "- verify against source PDF")
    except ValueError:
        header_check = "UNPARSEABLE: non-numeric header cycle field - verify against source PDF"
    meta["_header_check"] = header_check

    records: list[dict] = []
    for ry0, ry1 in zip(h_lines[1:-1], h_lines[2:]):
        cells = await _ocr_row_bucketed(img, v_lines, ry0, ry1)
        module = _clean_module(cells[0])
        if not module:
            continue
        pn = _clean_alnum(cells[1])
        sn = _clean_alnum(cells[2])
        numeric_vals = [_clean_numeric(c) for c in cells[3:7]]
        rec = dict(zip(_ROW_COLS, [module, pn, sn, *numeric_vals]))
        rec.update(meta)

        limit, csn_total, available = (rec.get("LIFE_LIMIT_CYCLES"), rec.get("CSN_TOTAL"),
                                        rec.get("AVAILABLE_CYCLES"))
        if all(v not in (None, "") for v in (limit, csn_total, available)):
            try:
                expected = int(limit) - int(csn_total)
                actual = int(available)
                rec["_availability_check"] = (
                    "OK" if expected == actual
                    else f"MISMATCH: LIFE_LIMIT_CYCLES-CSN_TOTAL={expected}, "
                         f"AVAILABLE_CYCLES printed as {actual} - verify against source PDF"
                )
            except ValueError:
                rec["_availability_check"] = "UNPARSEABLE: non-numeric cycle cell - verify against source PDF"
        else:
            rec["_availability_check"] = "SKIPPED: empty cycle cell - verify against source PDF"

        records.append(rec)
    return records
