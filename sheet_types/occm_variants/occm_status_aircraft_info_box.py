"""OCCM Status -- "Aircraft Information" box header layout, scanned, no text
layer, OCR required throughout.

Confirmed on a real corpus file: 0 extractable characters on every page via
pdfplumber (a straight scan). Every page (title page included) repeats an
identical top-of-page layout, e.g. (values genericized per this project's
data-sensitivity convention -- no real registration/MSN/dates/hours/cycles
from the source file is ever written in this module)::

    +-----------------------------------+
    | Aircraft Information               |
    | TYPE | <type>   | F/H | <hours>    |    <operator logo>   OCCM STATUS
    | MSN  | <msn>    | F/C | <cycles>   |
    | REG  | <reg>    | DATE| <date>     |
    | DOM  | <date>   | REV | <rev>      |
    +-----------------------------------+
    ATA | Material Description | P/N | S/N | Install Date | TSN | CSN | Remark
    <ata>| <description...>     |<pn> |<sn> | <yyyy-mm-dd> |<n>  |<n>  |<text>

The small "Aircraft Information" box (top-left, a fixed 5-row x 4-column
ruled grid: a title row plus TYPE/F-H, MSN/F-C, REG/DATE, DOM/REV rows) and
an operator logo + "OCCM STATUS" title (top-right) are confirmed to repeat
identically on every page. The operator logo is intentionally NOT extracted
into any column here -- out of scope for this module, and per this
project's data-sensitivity convention no operator name is recorded anywhere
below. The eight info-box values (TYPE, MSN, REG, DOM, F/H, F/C, DATE, REV)
are parsed once from page 1 and stamped identically onto every row, per this
package's usual header-plus-body OCCM convention.

Column header row (confirmed directly, reprints on every page directly
below the info box)::

    ATA | Material Description | P/N | S/N | Install Date | TSN | CSN | Remark

A data row, tokens in column order: ATA, DESCRIPTION, PART_NUMBER,
SERIAL_NUMBER, INSTALL_DATE, TSN, CSN, REMARK -- confirmed directly across
the first, several middle, and the last page of the real sample file. ATA
prints on every single row (no forward-fill needed). REMARK is confirmed to
carry more than one distinct shape across real rows (a short certification-
basis code, or a longer free-text note), so it is kept as free text rather
than a constrained enum.

The very last page of the real sample file ends the data grid with a
signature block below it (a person's name and job title) -- confirmed
directly NOT extracted into any column: this module's row acceptance
requires a plausible ATA chapter digit run recovered from the ATA column's
own cell (see `_clean_ata` below), which the signature block's own text
never produces, so that block is simply dropped as page furniture along
with any other non-table text, the same "no real cell content attached"
convention this package's other grid-based OCCM variants use.

OCR approach -- confirmed directly, side by side, against the real sample
file rather than assumed, and following this package's established fix for
a badly-behaved whole-page/whole-row OCR pass against a densely ruled grid
(see e.g. `occm_component_status_parent_serial_grid.py`,
`msn_occm_list_scanned.py`): a whole-page OCR pass on this file's data grid
comes back badly corrupted (entire rows collapse into a handful of garbled
blobs), confirmed directly, while the very same pixels OCR cleanly once
cropped to a single ruled column's own full-height strip. The table's own
ruled row boundaries are recovered directly from pixels (a numpy darkfrac
scan down the ATA column's own X-span), and each of the 8 columns is OCR'd
as its own full-height strip (`ocr_words(psm=4)`), bucketing every
recognized word into the real ruled row it falls within by Y-position. Any
cell still empty after that pass gets one direct fallback OCR call on its
own isolated crop (a few px inset off its own ruled boundary, 3x upscaled,
white-padded, `psm=6`) -- confirmed directly to recover cells the psm=4
full-strip pass misses (in particular, the narrow ATA column's own digit
cells, which the psm=4 pass returns nothing for on this file at all --
confirmed directly -- but which resolve cleanly via psm=6 on the same
pixels, matching the same per-psm quirk documented in
`msn_occm_list_scanned.py`'s own module docstring).

A further finding, confirmed directly on the real sample file and specific
to this template: the LAST data row on every page except the file's own
final page has no ruled bottom border rendered before the page's physical
edge (the table's row grid is generated without per-page-break awareness,
so the final row on a page-break simply runs to the page's bottom margin
with no closing rule) -- confirmed directly by OCR'ing the gap between the
last detected ruled line and that page's own footer text ("Page N of M"),
which recovers a genuine, fully-legible data row every time. This module
therefore always probes for one extra "unbordered" row below the last
ruled line found (bounded by a safety margin well above the footer text),
and OCRs it the same way as every ruled row; it is silently discarded
afterwards if no plausible ATA digit run is recovered from it (the normal
row-acceptance rule above), which is what naturally happens on the file's
own final page (nothing but whitespace, then the signature block, follows
the last real ruled row there).

Column X-boundaries (fraction of page width) and the info-box's own row/
column boundaries are measured directly from the real rendered page's own
ruled-line pixel positions, confirmed stable across the first, several
middle, and the last page of the real sample file.
"""
from __future__ import annotations
import re

import numpy as np
from PIL import Image, ImageOps

from sheet_types.occm_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, ocr_words, page_count

NAME = "OCCM Status (Aircraft Information Box, Scanned)"

# This module's known source file has no text layer at all (confirmed via
# pdfplumber -- 0 chars on every page), so these SIGNATURES can never fire
# through occm.py's normal pdfplumber head-text match; real detection
# happens via ocr_detect() below. Deliberately left empty, same convention
# as this package's other purely-OCR variants (e.g.
# `occm_component_status_parent_serial_grid.py`).
SIGNATURES = []

CANONICAL_COLUMNS = [
    "ATA",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "INSTALL_DATE",
    "TSN",
    "CSN",
    "REMARK",
    # Info-box header metadata, parsed once (page 1) and stamped on every row.
    "AIRCRAFT_TYPE",
    "MSN",
    "AIRCRAFT_REG",
    "MFG_DATE",
    "AC_FH",
    "AC_FC",
    "REPORT_DATE",
    "REVISION",
]

_AMOUNT_RULE = {"pattern": r"^[\d,]{2,10}$", "allow_empty": True}
_DATE_RULE = {"pattern": r"^\d{4}-\d{1,2}-\d{1,2}$", "allow_empty": True}

_OVERRIDES = {
    "PART_NUMBER": {"allow_empty": True},
    "SERIAL_NUMBER": {"allow_empty": True},
    "INSTALL_DATE": _DATE_RULE,
    "TSN": _AMOUNT_RULE,
    "CSN": _AMOUNT_RULE,
    # Confirmed to carry more than one distinct shape on the real sample
    # file (a short certification-basis code like "EASA"/"FAA"/"AIR", or a
    # longer free-text note like "Will be replaced (RTS)") -- kept as free
    # text rather than a constrained enum, per this package's usual REMARK
    # convention (see e.g. `on_condition_cm_components_list.py`).
    "REMARK": {"allow_empty": True},
    # Info-box metadata -- each value is a single figure parsed once and
    # stamped identically on every row of the file, so a tight pattern here
    # would either flag every single row over one OCR misread in one place,
    # or none at all -- neither is a useful per-row signal. Genuine per-row
    # corruption is still caught by the row-level rules above. Same
    # reasoning as this package's other header-plus-body OCCM variants
    # (e.g. `occm_component_status_parent_serial_grid.py`'s own header
    # fields).
    "AIRCRAFT_TYPE": {"allow_empty": True},
    "MSN": {"allow_empty": True},
    "AIRCRAFT_REG": {"allow_empty": True},
    "MFG_DATE": {"allow_empty": True},
    "AC_FH": {"allow_empty": True},
    "AC_FC": {"allow_empty": True},
    "REPORT_DATE": {"allow_empty": True},
    "REVISION": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Data-grid column X-boundaries (fraction of page width), measured directly
# from the real rendered page's own ruled vertical-line pixel columns --
# confirmed stable across the first, several middle, and the last page of
# the real sample file.
_COLUMNS: list[tuple[str, float, float]] = [
    ("ATA", 0.0553, 0.1119),
    ("DESCRIPTION", 0.1119, 0.3311),
    ("PART_NUMBER", 0.3311, 0.4303),
    ("SERIAL_NUMBER", 0.4303, 0.5303),
    ("INSTALL_DATE", 0.5303, 0.6129),
    ("TSN", 0.6129, 0.6876),
    ("CSN", 0.6876, 0.7621),
    ("REMARK", 0.7621, 0.8894),
]
_JOIN_WITH_SPACE = {"DESCRIPTION", "REMARK"}

# Info-box (top-left "Aircraft Information" grid) column X-boundaries
# (fraction of page width) -- label/value pairs, two side-by-side field
# groups. Measured directly from the real rendered page's own ruled
# vertical-line pixel columns; note the box's own left edge coincides with
# the data grid's own ATA column left edge (0.0553) -- both are the same
# outer table border.
_INFO_LABEL1_X = (0.0553, 0.1115)
_INFO_VALUE1_X = (0.1115, 0.1888)
_INFO_LABEL2_X = (0.1888, 0.2508)
_INFO_VALUE2_X = (0.2508, 0.3308)

# Info-box field -> (row index within the box's own 5 ruled rows [0 = title
# row], value-column pair) -- row 1 is TYPE/F-H, row 2 is MSN/F-C, row 3 is
# REG/DATE, row 4 is DOM/REV, confirmed directly against the real sample
# file's own box layout.
_INFO_FIELDS: list[tuple[int, tuple[float, float], str]] = [
    (1, _INFO_VALUE1_X, "AIRCRAFT_TYPE"),
    (1, _INFO_VALUE2_X, "AC_FH"),
    (2, _INFO_VALUE1_X, "MSN"),
    (2, _INFO_VALUE2_X, "AC_FC"),
    (3, _INFO_VALUE1_X, "AIRCRAFT_REG"),
    (3, _INFO_VALUE2_X, "REPORT_DATE"),
    (4, _INFO_VALUE1_X, "MFG_DATE"),
    (4, _INFO_VALUE2_X, "REVISION"),
]
_HEADER_FIELDS = [name for _, _, name in _INFO_FIELDS]

# Row-grid detection (data grid and info box alike): a pixel row counts as
# part of a ruled horizontal line once at least this fraction of the ATA
# column's own width is dark.
_LINE_DARKFRAC_THRESH = 0.6
_DARK_PIXEL_THRESH = 150
# Consecutive dark-row hits within this many px are the same ruled line.
_LINE_MERGE_GAP = 3
# A candidate data row taller than this multiple of the page's own median
# row height is a real gap (end of table on that page, e.g. before a
# signature block), not a genuine row -- excluded before OCR.
_MAX_ROW_HEIGHT_RATIO = 1.6
_DEFAULT_ROW_HEIGHT_PX = 68  # measured directly at 300dpi, used only as a
                             # fallback when too few ruled lines are found.
# Safety margin above a page's own footer text ("Page N of M") within which
# the final "unbordered last row" probe (see module docstring) is never
# extended -- measured directly to sit comfortably below any real data row
# but above the footer on the real sample file.
_FOOTER_MARGIN_PX = 110
# A few px of slack added past each strip's own ruled edges before OCR --
# cropping exactly on the ruled line clips a whisker of glyph pixels and can
# make OCR give up on the whole strip (same convention as
# `occm_component_status_parent_serial_grid.py`).
_STRIP_PAD = 6

_NOISE_TOKEN_RE = re.compile(r"^[|\[\]_\-—–~=<>`\"'*]+$")
_EDGE_STRIP = " _-|[]=~.\"'`*"
# A real ATA cell is a bare 2-3 digit chapter code within the plausible
# range; this doubles as the row-acceptance filter that drops page
# furniture (the repeated column-header row, and -- on the file's own final
# page -- the trailing signature block) -- see module docstring.
_ATA_DIGITS_RE = re.compile(r"\d{2,3}")
_ATA_RANGE = (20, 83)

# ocr_detect() anchors: "OCCM STATUS" is this report's own title-line
# phrase; "AIRCRAFT INFORMATION" is the info-box's own title-cell phrase.
# Checked directly (grep across every SIGNATURES list in
# sheet_types/{occm,ht,llp}.py and every existing occm_variants/
# ht_variants/llp_variants file): "AIRCRAFT INFORMATION" appears nowhere
# else in this package. "OCCM STATUS" alone IS also standard_occm.py's own
# SIGNATURES entry, but that module is a *born-digital* variant reached
# only through the router's pdfplumber text-match path (its known source
# file has a real text layer); this module's own known source file has no
# text layer at all, so it is only ever reached via this ocr_detect()
# fallback, which the router only calls once the pdfplumber SIGNATURES loop
# has already failed to match anything -- the two therefore cannot collide
# on the same file (same reasoning documented in
# `occm_component_status_parent_serial_grid.py`'s own docstring for its
# analogous "OCCM COMPONENT STATUS" / occm_component_status_report.py
# case). Requiring BOTH phrases together (rather than either alone) is a
# further safety margin specific to this module.
_TITLE_RE = re.compile(r"OCCM\s+STATUS", re.IGNORECASE)
_INFO_TITLE_RE = re.compile(r"AIRCRAFT\s+INFORMATION", re.IGNORECASE)


def _find_row_lines(arr: np.ndarray, x0: int, x1: int) -> list[int]:
    """Recover ruled horizontal-line Y-positions directly from the page
    image -- a numpy darkfrac scan over the ATA column's own X-span (also
    the info-box's own left-hand column X-span, see module docstring)."""
    band = arr[:, x0:x1]
    darkfrac = (band < _DARK_PIXEL_THRESH).mean(axis=1)
    rows_dark = np.where(darkfrac > _LINE_DARKFRAC_THRESH)[0]
    if len(rows_dark) == 0:
        return []
    lines: list[int] = []
    cur = [int(rows_dark[0])]
    for r in rows_dark[1:]:
        r = int(r)
        if r - cur[-1] <= _LINE_MERGE_GAP:
            cur.append(r)
        else:
            lines.append((cur[0] + cur[-1]) // 2)
            cur = [r]
    lines.append((cur[0] + cur[-1]) // 2)
    return lines


def _clean_token(text: str) -> str:
    return text.strip(_EDGE_STRIP).strip()


def _clean_ata(text: str) -> str:
    """Extract a plausible 2-3 digit ATA chapter from a (possibly noisy)
    OCR'd cell -- see module docstring on why this doubles as the row-
    acceptance filter."""
    m = _ATA_DIGITS_RE.search(text)
    if not m:
        return ""
    digits = m.group(0)
    if len(digits) == 3:
        digits = digits[:2]
    if _ATA_RANGE[0] <= int(digits) <= _ATA_RANGE[1]:
        return digits
    return ""


async def _ocr_cell_fallback(img, x0: int, x1: int, top: int, bot: int) -> str:
    """Direct per-cell OCR fallback for a table cell still empty after the
    full-column-strip pass -- confirmed directly to recover cells the
    cheaper pass misses on this file (in particular, the narrow ATA
    column's own digit cells, see module docstring)."""
    x0i, x1i = x0 + 4, x1 - 4
    y0i, y1i = top + 2, bot - 2
    if x1i - x0i < 5 or y1i - y0i < 5:
        return ""
    crop = img.crop((x0i, y0i, x1i, y1i))
    crop = crop.resize((crop.width * 3, crop.height * 3), Image.LANCZOS)
    padded = ImageOps.expand(crop, border=20, fill=(255, 255, 255))
    text = await ocr_text(padded, psm=6)
    return _clean_token(" ".join(text.split()))


def _join(tokens: list[str], col_name: str) -> str:
    sep = " " if col_name in _JOIN_WITH_SPACE else ""
    return _clean_token(sep.join(tokens))


async def _extract_data_rows(img, arr: np.ndarray) -> list[dict]:
    w, h = img.size
    ata_x0, ata_x1 = int(w * _COLUMNS[0][1]), int(w * _COLUMNS[0][2])
    lines = _find_row_lines(arr, ata_x0, ata_x1)
    if len(lines) < 7:
        # No recognizable info-box + column-header + data-row ruling on
        # this page at all -- nothing to extract.
        return []

    # lines[0:6] are the info box's own 5 ruled rows (title + 4 field
    # rows); lines[5] is the info box's bottom edge / column-header row's
    # own top edge; lines[6] is the column-header row's own bottom edge /
    # first real data row's top edge (see module docstring).
    data_lines = lines[6:]
    if len(data_lines) < 2:
        return []
    row_bounds = list(zip(data_lines, data_lines[1:]))
    heights = [b - a for a, b in row_bounds]
    med = float(np.median(heights)) if heights else _DEFAULT_ROW_HEIGHT_PX
    row_bounds = [(a, b) for a, b in row_bounds if (b - a) <= med * _MAX_ROW_HEIGHT_RATIO]

    # Probe for one further "unbordered" row below the last ruled line
    # found (see module docstring) -- bounded well clear of the page's own
    # footer text. Silently contributes nothing if there's no real row
    # there (the row-acceptance ATA filter below drops it).
    last_bottom = row_bounds[-1][1] if row_bounds else data_lines[-1]
    footer_limit = h - _FOOTER_MARGIN_PX
    probe_bottom = int(min(footer_limit, last_bottom + med + _STRIP_PAD))
    if probe_bottom - last_bottom > med * 0.5:
        row_bounds.append((last_bottom, probe_bottom))

    if not row_bounds:
        return []

    buckets: list[dict[str, list[str]]] = [{} for _ in row_bounds]
    y0, y1 = row_bounds[0][0] - _STRIP_PAD, row_bounds[-1][1] + _STRIP_PAD
    for name, f0, f1 in _COLUMNS:
        cx0, cx1 = int(w * f0), int(w * f1)
        crop = img.crop((cx0, max(0, y0), cx1, min(h, y1)))
        # The ATA column is narrow enough that Tesseract's own multi-column
        # layout analysis (psm=4, used for every other column) returns
        # nothing at all for it on this file -- confirmed directly, a
        # single-digit-column-width crop pathology distinct from (but
        # related to) the "wide/thin crop" one documented in
        # `msn_occm_list_scanned.py`'s own module docstring. psm=6 (assume
        # a single uniform text block) recovers this column's full-height
        # strip reliably instead -- confirmed directly across the first,
        # several middle, and the last page of the real sample file.
        psm = 6 if name == "ATA" else 4
        words = await ocr_words(crop, psm=psm, min_conf=-1)
        strip_top = max(0, y0)
        for wd in words:
            text = str(wd.get("text", "")).strip()
            if not text or _NOISE_TOKEN_RE.match(text):
                continue
            top = strip_top + wd["top"]
            for i, (rt, rb) in enumerate(row_bounds):
                if rt <= top <= rb:
                    buckets[i].setdefault(name, []).append(text)
                    break

    # Fallback pass: direct per-cell OCR for any cell still empty after the
    # full-strip pass (see module docstring).
    for name, f0, f1 in _COLUMNS:
        cx0, cx1 = int(w * f0), int(w * f1)
        for i, (rt, rb) in enumerate(row_bounds):
            if name in buckets[i]:
                continue
            text = await _ocr_cell_fallback(img, cx0, cx1, rt, rb)
            if text and not _NOISE_TOKEN_RE.match(text):
                buckets[i][name] = [text]

    rows = []
    for i in range(len(row_bounds)):
        b = buckets[i]
        ata = _clean_ata(" ".join(b.get("ATA", [])))
        description = _join(b.get("DESCRIPTION", []), "DESCRIPTION")
        part_number = _join(b.get("PART_NUMBER", []), "PART_NUMBER")
        serial_number = _join(b.get("SERIAL_NUMBER", []), "SERIAL_NUMBER")
        if not ata:
            # No plausible ATA chapter recovered -- page furniture (the
            # repeated column-header row, or the final page's own trailing
            # signature block), not a genuine data row. See module
            # docstring.
            continue
        if not description and not part_number and not serial_number:
            continue
        rows.append({
            "ATA": ata,
            "DESCRIPTION": description,
            "PART_NUMBER": part_number,
            "SERIAL_NUMBER": serial_number,
            "INSTALL_DATE": _join(b.get("INSTALL_DATE", []), "INSTALL_DATE"),
            "TSN": _join(b.get("TSN", []), "TSN"),
            "CSN": _join(b.get("CSN", []), "CSN"),
            "REMARK": _join(b.get("REMARK", []), "REMARK"),
        })
    return rows


async def _parse_info_box(img, arr: np.ndarray, meta: dict) -> None:
    """Parse the 8 "Aircraft Information" box field values from page 1's
    own ruled 5-row x 4-column grid (see module docstring) -- each field's
    own value cell is OCR'd individually (a whole-box pass is badly
    corrupted by the box's own ruled grid lines, the same wide/thin-crop
    pathology documented across this package's other grid-based OCCM
    variants), upscaled 2x for a cleaner read."""
    if all(meta.get(k) for k in _HEADER_FIELDS):
        return
    w, h = img.size
    label_x0, label_x1 = int(w * _COLUMNS[0][1]), int(w * _COLUMNS[0][2])
    lines = _find_row_lines(arr, label_x0, label_x1)
    if len(lines) < 6:
        return
    box_rows = list(zip(lines[:6], lines[1:6]))  # 5 rows: title + 4 fields
    for row_idx, (vx0, vx1), field in _INFO_FIELDS:
        if meta.get(field) or row_idx >= len(box_rows):
            continue
        rt, rb = box_rows[row_idx]
        x0i, x1i = int(w * vx0) + 5, int(w * vx1) - 5
        y0i, y1i = rt + 5, rb - 5
        if x1i - x0i < 5 or y1i - y0i < 5:
            continue
        crop = img.crop((x0i, y0i, x1i, y1i))
        crop = crop.resize((crop.width * 2, crop.height * 2), Image.LANCZOS)
        text = await ocr_text(crop, psm=7)
        value = _clean_token(text)
        if value:
            meta[field] = value


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback (see
    sheet_types/occm.py) -- this variant's known source file has no text
    layer at all, so it can never be found through the normal pdfplumber
    head-text match.

    Requires BOTH the report's own title phrase ("OCCM STATUS") and the
    info-box's own title-cell phrase ("AIRCRAFT INFORMATION") -- see module
    docstring on why this combination is a safe, non-colliding anchor. The
    info-box title cell is located the same way `_parse_info_box()` locates
    every other info-box field below (a ruled-line scan, not a fixed
    fraction of page height) -- confirmed directly that a fixed-fraction
    crop for this specific cell is too sensitive to page-to-page pixel
    jitter to OCR reliably, unlike the report's own large bold title text
    above, which tolerates a generous fixed-fraction crop just fine."""
    try:
        img = await render_page(pdf_path, 0, dpi=300)
        w, h = img.size
        title_crop = img.crop((0, 0, w, int(h * 0.15)))
        title_text = (await ocr_text(title_crop, psm=6)).upper()
        if not _TITLE_RE.search(title_text):
            return False
        arr = np.array(img.convert("L"))
        label_x0, label_x1 = int(w * _COLUMNS[0][1]), int(w * _COLUMNS[0][2])
        lines = _find_row_lines(arr, label_x0, label_x1)
        if len(lines) < 2:
            return False
        rt, rb = lines[0], lines[1]
        title_box_x1 = int(w * _INFO_VALUE2_X[1])
        crop = img.crop((label_x0 + 5, rt + 5, title_box_x1, rb - 5))
        crop = crop.resize((crop.width * 2, crop.height * 2), Image.LANCZOS)
        info_text = (await ocr_text(crop, psm=7)).upper()
        return bool(_INFO_TITLE_RE.search(info_text))
    except Exception:
        return False


async def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    header_meta = {k: "" for k in _HEADER_FIELDS}
    n_pages = await page_count(pdf_path)
    for page_index in range(n_pages):
        img = await render_page(pdf_path, page_index, dpi=300)
        arr = np.array(img.convert("L"))
        await _parse_info_box(img, arr, header_meta)
        for rec in await _extract_data_rows(img, arr):
            rec["_page"] = page_index + 1
            rec.update(header_meta)
            records.append(rec)
    return records
