"""SAS Component "Part list based on Drawing <n>" -- a delivery/transfer
parts record for one landing-gear component (title block reads "SAS
COMPONENT" / "Part list based on Drawing <drawing-no> Rev <rev>"), NOT a
per-leg status snapshot like sas_drawing_item_llp.py and not a flat PN/SN
event log like llp_pn_sn_event_log.py -- this format lists, for ONE gear
assembly, every sub-part that was on it as RECEIVED versus what it carried
when DELIVERED back out, side by side on the same row.

Confirmed directly against the one known source file (single scanned page,
0-char text layer -- a clean computer-rendered raster form, not a
photographed one): a header info-block, one ruled data table, then a
Remarks legend + signature block that must NOT be read as table rows.

Header info-block (values below are illustrative placeholders, not real
values from the source file)::

    SAS COMPONENT
    Part list based on Drawing <drawing_no> Rev <rev_letter>
    A/C Type            Landing Gear Report   From customer         Work order / Customer order. <wo> / <order>
    <ac_type>                                  <customer_code>
                         Received Gear                              Delivered Gear              Customer ref <customer_code>
    <gear_leg>  P/N <pn>          S/N <sn>     P/N <pn>              S/N <sn>

"Landing Gear Report" and "Received Gear"/"Delivered Gear" are fixed
labels, not values -- confirmed against the rendered page, not guessed.
The gear-leg code (e.g. the nose/left-main/right-main abbreviation printed
in the leftmost cell of the P/N-S/N row) and the two whole-assembly P/N+S/N
pairs (Received vs Delivered) are file-level metadata, stamped on every
row, alongside A/C Type, the customer code ("From customer" / "Customer
ref" print the same code on the one known file, captured as one field),
and the two work-order-style numbers.

Data table (11 vertical bands, confirmed directly by column-line
detection -- see `_detect_table_grid()` -- and cross-checked against the
column header row's own printed text, which reads left to right)::

    Part Nomenclature | Part Number | Serial Number | Remark | (blank) |
    Part Number | Serial Number | Operator | Life Limit | Total Cycles | Remark

The blank 5th band carries no header label and is always empty on the one
known file -- a visual spacer between the "as received" group (columns
2-4) and the "as delivered" group (columns 6-11), not a data column, and
is skipped rather than mapped to a canonical field. The two Part
Number/Serial Number pairs are genuinely NOT always equal row-to-row --
confirmed directly: several rows show the same PN on both sides but a
DIFFERENT serial (the physical piece was swapped during the shop visit),
so RECEIVED and DELIVERED must be kept in separate columns rather than
merged or deduplicated. A "Note 1" remark rows also show a delivered
Serial Number of "---" (a literal dash placeholder) where the source
explains those items are "delivered as single items with separate CRS"
rather than tracked serials -- left as-is (not blanked, not guessed at)
since it is a real printed value, not an OCR artifact.

Life Limit / Total Cycles print with a thousands-separating space and a
trailing " C" unit suffix (e.g. an illustrative "75 000 C", "16 968 C",
"0 C") -- `_clean_cycles()` strips both, keeping digits only.

Grid detection: column x-positions are detected fresh per file (dense
vertical-line scan restricted to a y-band inside the table, per
eastar_jet_occm_list.py's grid-line technique), NOT hardcoded, since nothing
here suggests these x-positions are stable across a producer's other
files. An outer decorative page frame and the header info-block above the
table both carry their own ruled lines in roughly the same x-range, which
would corrupt column detection if included -- restricting the scan to a
y-band that starts below the header info-block and ends above the Remarks
legend (confirmed directly against the rendered page) avoids both.

Row y-positions are likewise detected fresh (not hardcoded row-height
assumptions): unlike the uniform-row-height tables this package's other
grid-based variants describe, several rows here wrap their Part
Nomenclature text onto 2 lines and are visibly TALLER than single-line
rows (confirmed directly: row heights alternate between roughly 43px and
83px at 300dpi on the one known file) with no single modal spacing to
lock onto. Row lines are instead found via `_longest_dense_run()`-style
gap-tolerant chaining (ported from part_m_engine_disk_sheet.py): any run
of consecutive horizontal lines whose gaps all stay under a generous
ceiling is accepted as the table body, regardless of each individual gap's
exact size. Line detection itself uses two narrow interior-column x-bands
(not the full row width) so a row's own blank cells (the unlabeled spacer
column, an empty Remark) don't dilute the row's average darkness below
threshold -- confirmed directly this dilution otherwise drops real row
lines. The two bands' detected positions differ by a small, consistent
offset across the whole table (confirmed directly, a few px at 300dpi) --
a genuine page skew, not noise -- so row top/bottom for a given row index
is taken as the average of both bands' own edge at that index, rather than
either band alone.

Each row is OCR'd as one wide strip (not per-cell crops) with the interior
column dividers painted out before recognition -- the same tight-row-height
tradeoff this package's other ruled-grid variants document (see
part_m_engine_disk_sheet.py's `_ocr_row_bucketed()` docstring: a per-cell
crop on a single-line-tall row leaves too little vertical context for
reliable recognition). Recognized words are then bucketed into the 11
column bands purely by x-position and re-joined top-to-bottom,
left-to-right within each band (clusters by vertical proximity first, then
sorts left-to-right within a cluster -- ported from
kalstar_engine_llp_status.py's `_cluster_lines()` -- rather than a flat
left-to-right sort, since a wrapped 2-line Part Nomenclature cell would
otherwise have its second line's words interleaved with the first line's
by x-position alone).

Known limitation, left unresolved rather than guessed at: only one source
file of this exact format has been seen, so header field positions (the
x-fraction word-bucketing boundaries used for A/C Type vs "From customer"
in the info-block) are confirmed stable only on that one file, not across
a producer's whole corpus of this template. One row on the known file
(a steering-related item) also carries a handwritten annotation
overlapping the printed Delivered Part Number / Serial Number / Operator
cells -- confirmed directly this is genuine handwriting, not a print
artifact -- and is read as-is (whatever OCR recovers from that cell,
correct or not) rather than special-cased, per this project's
never-guess-a-wrong-split convention; RULES' pattern validation will flag
that row's affected cells as `_issues` for a human to check against the
source scan rather than silently accepting a possibly-wrong OCR read.
"""
from __future__ import annotations

import re

import numpy as np
from PIL import ImageDraw

from sheet_types.llp_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, ocr_words

NAME = "SAS Component Drawing Parts List"

# Text-layer signatures kept for interface consistency only -- the one known
# source file has a 0-char text layer (a clean computer-rendered raster, not
# a photographed form), so these will never actually fire through the
# router's pdfplumber-based text match. Real detection is ocr_detect() below.
# Checked for collisions against every SIGNATURES list in
# sheet_types/{occm,ht,llp}.py and every existing variant file (including
# sas_drawing_item_llp.py -- a different SAS format entirely, SIGNATURES
# ["When Airframe CSN:", "Drawing Item"] -- and llp_pn_sn_event_log.py, the
# separate flat PN/SN event-log format built the same day for a
# similarly-named source file; that module's own anchor phrase is "LIFE
# LIMITED PARTS BY PN AND SN", which is unrelated to and does not collide
# with either phrase below): no collision found.
SIGNATURES = [
    "SAS COMPONENT",
    "Part list based on Drawing",
]

CANONICAL_COLUMNS = [
    "PART_NOMENCLATURE",
    "PN_RECEIVED",
    "SN_RECEIVED",
    "REMARK_RECEIVED",
    "PN_DELIVERED",
    "SN_DELIVERED",
    "OPERATOR",
    "LIFE_LIMIT",
    "TOTAL_CYCLES",
    "REMARK_DELIVERED",
    # File-level metadata -- same on every row of a given file.
    "AC_TYPE",
    "CUSTOMER_CODE",
    "WORK_ORDER",
    "CUSTOMER_ORDER",
    "DRAWING_NUMBER",
    "DRAWING_REV",
    "GEAR_LEG",
    "COMPONENT_PN_RECEIVED",
    "COMPONENT_SN_RECEIVED",
    "COMPONENT_PN_DELIVERED",
    "COMPONENT_SN_DELIVERED",
]

_PN_RULE = {
    "pattern": r"^[A-Z0-9](?:[A-Z0-9\-]*[A-Z0-9])?$",
    "uppercase": True,
    "no_spaces": True,
}
# Serial numbers here are a genuine mix of alphanumeric shop serials and the
# literal "-" placeholder Note-1 rows print for a delivered serial that was
# never tracked (see module docstring) -- allow both rather than rejecting
# the dash as malformed.
_SN_RULE = {"pattern": r"^([A-Z0-9\-]+|-)$", "uppercase": True, "allow_empty": True}
_CYCLES_RULE = {"pattern": r"^\d*$", "allow_empty": True, "int_range": (0, 90000)}
_REMARK_RULE = {"allow_empty": True}

_OVERRIDES = {
    "PART_NOMENCLATURE": {"uppercase": True},
    "PN_RECEIVED": _PN_RULE,
    "SN_RECEIVED": _SN_RULE,
    "REMARK_RECEIVED": _REMARK_RULE,
    "PN_DELIVERED": _PN_RULE,
    "SN_DELIVERED": _SN_RULE,
    "OPERATOR": {"pattern": r"^[A-Z0-9]*$", "uppercase": True, "allow_empty": True},
    "LIFE_LIMIT": _CYCLES_RULE,
    "TOTAL_CYCLES": _CYCLES_RULE,
    "REMARK_DELIVERED": _REMARK_RULE,
    "AC_TYPE": {"allow_empty": True},
    "CUSTOMER_CODE": {"pattern": r"^[A-Z0-9]*$", "uppercase": True, "allow_empty": True},
    "WORK_ORDER": {"pattern": r"^\d*$", "allow_empty": True},
    "CUSTOMER_ORDER": {"pattern": r"^\d*$", "allow_empty": True},
    "DRAWING_NUMBER": {"allow_empty": True},
    "DRAWING_REV": {"pattern": r"^[A-Z0-9]*$", "uppercase": True, "allow_empty": True},
    "GEAR_LEG": {"allow_empty": True},
    "COMPONENT_PN_RECEIVED": _PN_RULE,
    "COMPONENT_SN_RECEIVED": {"allow_empty": True},
    "COMPONENT_PN_DELIVERED": _PN_RULE,
    "COMPONENT_SN_DELIVERED": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_DPI = 300
_DARK_THRESH = 150  # pixel value below this counts as "ink" for grid detection

# Table body y-band as a fraction of full page height -- confirmed directly
# against the rendered page on the one known file to sit below the header
# info-block and above the Remarks legend / signature block. Not the exact
# table bounds (those are detected fresh within this band), just a search
# window that keeps the header info-block's own ruled lines and the
# signature block out of the scan.
_TABLE_Y_BAND = (0.30, 0.68)
_N_TABLE_COLS = 11  # Part Nomenclature, PN/SN/Remark (received), blank
                     # spacer, PN/SN/Operator/Life Limit/Total Cycles/Remark
                     # (delivered) -- see module docstring.
_PAGE_MARGIN = 30  # px at 300dpi -- drops the outer decorative page frame's
                    # own vertical lines from column detection (mirrors
                    # llp_pn_sn_event_log.py's own page-frame guard).

_TITLE_TEXT = "SAS COMPONENT"
_SUBTITLE_TEXT = "PART LIST BASED ON DRAWING"


def _line_groups(frac: np.ndarray, thresh: float, gap: int = 3) -> list[int]:
    idx = np.where(frac > thresh)[0]
    if not len(idx):
        return []
    groups, cur = [], [int(idx[0])]
    for v in idx[1:]:
        if v - cur[-1] <= gap:
            cur.append(int(v))
        else:
            groups.append(cur)
            cur = [int(v)]
    groups.append(cur)
    return [int(np.mean(g)) for g in groups]


def _merge_close(lines: list[int], dist: int) -> list[int]:
    """Collapse lines still within `dist` px of each other -- a thick or
    double-drawn rule, or (for the row-detection bands) a stray sub-divider
    inside the header row, otherwise gets counted as two separate lines."""
    if not lines:
        return []
    out = [lines[0]]
    for x in lines[1:]:
        if x - out[-1] <= dist:
            out[-1] = (out[-1] + x) // 2
        else:
            out.append(x)
    return out


def _longest_dense_run(lines: list[int], max_gap: int = 150, min_run: int = 10) -> list[int] | None:
    """Longest run of consecutive lines whose gaps all stay under `max_gap`
    -- ported from part_m_engine_disk_sheet.py. Needed here (rather than a
    fixed modal row-height run, as kalstar_engine_llp_status.py uses)
    because this format's row heights are NOT uniform: several rows wrap
    their Part Nomenclature text onto 2 lines and are visibly taller than
    single-line rows (see module docstring)."""
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
    return lines[best_start:best_start + best_len + 1]


def _detect_columns(dark: np.ndarray) -> list[int] | None:
    h, w = dark.shape
    y0, y1 = int(h * _TABLE_Y_BAND[0]), int(h * _TABLE_Y_BAND[1])
    col_frac = dark[y0:y1, :].mean(axis=0)
    cols = _merge_close(_line_groups(col_frac, 0.55), dist=45)
    cols = [c for c in cols if _PAGE_MARGIN < c < w - _PAGE_MARGIN]
    if len(cols) != _N_TABLE_COLS + 1:
        # Wrong column count means the scan latched onto the wrong region
        # (or a page frame/header-block line slipped past the margin/y-band
        # guards) -- every downstream cell boundary would be garbage.
        return None
    return cols


def _detect_rows(dark: np.ndarray, col_xs: list[int]) -> tuple[list[int], list[int]] | None:
    """Returns (left_band_lines, right_band_lines) -- row edge y-positions
    sampled at two interior columns (mirrors kalstar_engine_llp_status.py's
    skew-aware row detection), long enough to include the header row plus
    every data row. Returns None if a clean dense run can't be confirmed."""
    h, w = dark.shape
    y0, y1 = int(h * _TABLE_Y_BAND[0]), int(h * _TABLE_Y_BAND[1])
    bands = []
    for j in (1, len(col_xs) - 2):
        x0, x1 = col_xs[j] + 10, col_xs[j + 1] - 10
        frac = dark[:, x0:x1].mean(axis=1)
        lines = _merge_close(_line_groups(frac, 0.5), dist=25)
        lines = [l for l in lines if y0 - 60 < l < y1 + 60]
        run = _longest_dense_run(lines)
        if run is None:
            return None
        bands.append(run)
    left, right = bands
    if len(left) != len(right) or len(left) < 3:
        return None
    return left, right


async def _row_words(img, y_top: int, y_bot: int, col_xs: list[int], pad: int = 2, psm: int = 6):
    strip = img.crop((col_xs[0], y_top + pad, col_xs[-1], y_bot - pad)).copy()
    draw = ImageDraw.Draw(strip)
    for x in col_xs[1:-1]:
        bar = x - col_xs[0]
        # fill=255 on an RGB image only fills the red channel (confirmed
        # directly, same pitfall documented in
        # part_m_engine_disk_sheet.py's _ocr_row_bucketed()) -- use an
        # explicit white RGB triple.
        draw.rectangle([bar - 3, 0, bar + 3, strip.height], fill=(255, 255, 255))
    return await ocr_words(strip, psm=psm, min_conf=-1), col_xs[0]


def _cluster_and_join(words: list[dict], gap: int = 18) -> str:
    """Re-join a column's OCR'd words in genuine top-to-bottom,
    left-to-right reading order -- ported from
    kalstar_engine_llp_status.py's `_cluster_lines()`. A flat left-to-right
    sort (part_m_engine_disk_sheet.py's approach) is not safe here for a
    2-line-wrapped Part Nomenclature cell: the second line's words would
    interleave with the first line's by x-position alone."""
    if not words:
        return ""
    ws = sorted(words, key=lambda d: d["top"])
    clusters: list[list[dict]] = [[ws[0]]]
    for wd in ws[1:]:
        if wd["top"] - clusters[-1][-1]["top"] <= gap:
            clusters[-1].append(wd)
        else:
            clusters.append([wd])
    return " ".join(
        " ".join(str(d["text"]) for d in sorted(c, key=lambda d: d["left"]))
        for c in clusters
    )


def _bucket_row(words: list[dict], x_offset: int, col_xs: list[int]) -> list[str]:
    n_cols = len(col_xs) - 1
    buckets: list[list[dict]] = [[] for _ in range(n_cols)]
    for wd in words:
        x_center = x_offset + wd["left"] + wd["width"] / 2
        for i in range(n_cols):
            if col_xs[i] <= x_center < col_xs[i + 1]:
                buckets[i].append(wd)
                break
    return [_cluster_and_join(b) for b in buckets]


_JUNK_RE = re.compile(r"[^A-Za-z0-9/.\- ]")


def _clean_text(raw: str) -> str:
    return _JUNK_RE.sub("", raw).strip()


def _clean_cycles(raw: str) -> str:
    """Life Limit / Total Cycles print with a thousands-separating space and
    a trailing unit suffix (e.g. an illustrative "75 000 C") -- keep digits
    only."""
    digits = re.sub(r"[^0-9]", "", raw)
    return digits


def _clean_sn(raw: str) -> str:
    cleaned = _clean_text(raw).upper()
    if cleaned in ("--", "---", "----"):
        return "-"
    return cleaned


_HDR_FIELD_RE = {
    "DRAWING": re.compile(r"Drawing\s+(\S+)\s+Rev[_\s]*(\S+)", re.I),
    "ORDERS": re.compile(r"order\.?\s*(\d{4,10})\s*/\s*(\d{4,10})", re.I),
    "CUSTOMER_REF": re.compile(r"Customer\s*ref\.?\s*([A-Z0-9]+)", re.I),
    "GEAR_ROW": re.compile(
        r"([A-Za-z]+)\s+P.?N\s+([A-Z0-9\-]+)\s+S.?N\s+([A-Z0-9\-]+)\s+"
        r"P.?N\s+([A-Z0-9\-]+)\s+S.?N\s+([A-Z0-9\-]+)", re.I),
}


async def _parse_header(img) -> dict:
    w, h = img.size
    meta: dict[str, str] = {c: "" for c in [
        "AC_TYPE", "CUSTOMER_CODE", "WORK_ORDER", "CUSTOMER_ORDER",
        "DRAWING_NUMBER", "DRAWING_REV", "GEAR_LEG",
        "COMPONENT_PN_RECEIVED", "COMPONENT_SN_RECEIVED",
        "COMPONENT_PN_DELIVERED", "COMPONENT_SN_DELIVERED",
    ]}

    # Whole info-block as text -- covers the drawing/rev line, the work
    # order/customer order line (same physical text line on the one known
    # file), and the gear-leg + component P/N-S/N row.
    block = img.crop((0, int(h * 0.10), w, int(h * 0.28)))
    text = await ocr_text(block, psm=6)

    m = _HDR_FIELD_RE["DRAWING"].search(text)
    if m:
        meta["DRAWING_NUMBER"] = m.group(1).strip()
        meta["DRAWING_REV"] = m.group(2).strip().upper()

    m = _HDR_FIELD_RE["ORDERS"].search(text)
    if m:
        meta["WORK_ORDER"] = m.group(1)
        meta["CUSTOMER_ORDER"] = m.group(2)

    for line in text.splitlines():
        line = line.strip()
        m = _HDR_FIELD_RE["GEAR_ROW"].match(line)
        if m:
            meta["GEAR_LEG"] = m.group(1).strip().upper()
            meta["COMPONENT_PN_RECEIVED"] = m.group(2).strip().upper()
            meta["COMPONENT_SN_RECEIVED"] = m.group(3).strip().upper()
            meta["COMPONENT_PN_DELIVERED"] = m.group(4).strip().upper()
            meta["COMPONENT_SN_DELIVERED"] = m.group(5).strip().upper()
            break

    # A/C Type and "From customer" print as a label row followed by a
    # value row on the one known file, with the values landing under their
    # own label's x-position -- bucket by word x rather than assume a fixed
    # token order in the OCR'd line (confirmed directly the "Received
    # Gear"/"Delivered Gear"/"Customer ref" row between them frequently
    # OCRs too poorly to use as a text anchor). A crop tightly framing just
    # the value row starves tesseract of vertical context and degrades to
    # garbage (confirmed directly) -- so OCR a taller band that also
    # includes the label row above, then discard that row's words by
    # filtering on each word's own absolute y-position (confirmed directly
    # against this file's own word boxes: label row prints ~0.173-0.182 of
    # page height, the value row ~0.192-0.194) rather than by crop bounds
    # alone. x-fraction boundaries below likewise confirmed directly
    # against this file's own word boxes; single-file limitation noted in
    # the module docstring.
    band_y0 = int(h * 0.15)
    label_band = img.crop((0, band_y0, w, int(h * 0.23)))
    words = await ocr_words(label_band, psm=6)
    value_words = [wd for wd in words if 0.185 * h <= band_y0 + wd["top"] < 0.201 * h]
    ac_type_words = [wd for wd in value_words if wd["left"] < int(w * 0.22)]
    cust_words = [wd for wd in value_words if int(w * 0.22) <= wd["left"] < int(w * 0.45)]
    if ac_type_words:
        meta["AC_TYPE"] = _clean_text(_cluster_and_join(ac_type_words)).upper()
    if cust_words:
        meta["CUSTOMER_CODE"] = _clean_text(_cluster_and_join(cust_words)).upper()

    if not meta["CUSTOMER_CODE"]:
        m = _HDR_FIELD_RE["CUSTOMER_REF"].search(text)
        if m:
            meta["CUSTOMER_CODE"] = m.group(1).strip().upper()

    return meta


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 title-band OCR check for the router's blank-text
    fallback. Requires both the title ("SAS COMPONENT") and the subtitle
    phrase ("Part list based on Drawing") together -- checked directly
    against llp_pn_sn_event_log.py's own ocr_detect() anchor phrase ("LIFE
    LIMITED PARTS BY PN AND SN") and sas_drawing_item_llp.py's text-layer
    SIGNATURES: neither collides.

    Crop band confirmed directly against the one known file's own word
    boxes: the title line itself prints at ~0.11-0.13 of page height (below
    a stray top-margin scan artifact at ~0.0-0.10) and the subtitle line at
    ~0.15-0.16 -- a crop stopping at 0.11 (as this band originally did)
    clips the title line's own baseline and misses the subtitle line
    entirely, so ocr_detect() never actually fired. 0.18 clears both with
    margin and still stops well above the header info-block's data rows."""
    try:
        img = await render_page(pdf_path, 0, dpi=_DPI)
        w, h = img.size
        crop = img.crop((0, 0, w, int(h * 0.18)))
        text = (await ocr_text(crop, psm=6)).upper()
        return _TITLE_TEXT in text and _SUBTITLE_TEXT in text
    except Exception:
        return False


async def _find_header_row_idx(img, left: list[int], right: list[int], col_xs: list[int]) -> int | None:
    """Row-line detection (`_detect_rows()`) occasionally picks up one extra
    spurious edge from the header info-block immediately above the table
    (confirmed directly: its own ruled lines sit close enough above the
    table's own top border that a merge-distance tolerant enough to dedupe
    double-drawn table rules doesn't always also swallow that one), which
    would silently shift every row index by one and read the column-header
    row itself as if it were a data row. Rather than assume a fixed offset,
    anchor on the column-header row's own text ("Part Nomenclature") --
    whichever candidate row OCRs to that phrase in its first column is the
    header row, and every row after it is real data."""
    for i in range(0, min(3, len(left) - 1)):
        y_top = (left[i] + right[i]) // 2
        y_bot = (left[i + 1] + right[i + 1]) // 2
        crop = img.crop((col_xs[0], y_top + 2, col_xs[1], y_bot - 2))
        text = (await ocr_text(crop, psm=6)).upper()
        if "NOMENCLATURE" in text:
            return i
    return None


async def extract(pdf_path: str) -> list[dict]:
    img = await render_page(pdf_path, 0, dpi=_DPI)
    gray = np.array(img.convert("L"))
    dark = gray < _DARK_THRESH

    col_xs = _detect_columns(dark)
    if col_xs is None:
        return []
    rows = _detect_rows(dark, col_xs)
    if rows is None:
        return []
    left, right = rows

    header_idx = await _find_header_row_idx(img, left, right, col_xs)
    if header_idx is None:
        # Couldn't confirm which row is the column-header row -- rather
        # than guess an offset, fall back to assuming the first row band is
        # it (true on the one known file whenever _detect_rows() doesn't
        # pick up the extra info-block edge described above).
        header_idx = 0

    meta = await _parse_header(img)

    records: list[dict] = []
    for i in range(header_idx + 1, len(left) - 1):
        y_top = (left[i] + right[i]) // 2
        y_bot = (left[i + 1] + right[i + 1]) // 2
        words, x_off = await _row_words(img, y_top, y_bot, col_xs)
        cells = _bucket_row(words, x_off, col_xs)

        nomenclature = _clean_text(cells[0]).upper()
        if not nomenclature:
            continue

        rec = {c: "" for c in CANONICAL_COLUMNS}
        rec["PART_NOMENCLATURE"] = nomenclature
        rec["PN_RECEIVED"] = _clean_text(cells[1]).upper()
        rec["SN_RECEIVED"] = _clean_sn(cells[2])
        rec["REMARK_RECEIVED"] = _clean_text(cells[3])
        # cells[4] is the unlabeled blank spacer column -- deliberately
        # skipped, see module docstring.
        rec["PN_DELIVERED"] = _clean_text(cells[5]).upper()
        rec["SN_DELIVERED"] = _clean_sn(cells[6])
        rec["OPERATOR"] = _clean_text(cells[7]).upper()
        rec["LIFE_LIMIT"] = _clean_cycles(cells[8])
        rec["TOTAL_CYCLES"] = _clean_cycles(cells[9])
        rec["REMARK_DELIVERED"] = _clean_text(cells[10])
        rec.update(meta)
        rec["_page"] = 1
        records.append(rec)

    return records
