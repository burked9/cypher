"""On-Component/ Component Monitoring Listing Status -- Engineering Planning
department export, scanned, no text layer, OCR required throughout.

Confirmed directly on a real corpus file (13 pages, 0 extractable chars on
every page via pdfplumber -- a straight scan). Page 1 carries the report
banner and metadata block, which repeats (metadata only, no banner
company-name line) at the same fixed vertical position on every following
page::

    <company> ENGINEERING PLANNING &
    ON-COMPONENT/ COMPONENT MONITORING LISTING STATUS
    As of Date: <date>          AIRFRAME HOURS: <n>     AIRFRAME CYCLES: <n>
    Aircraft Model: <type>      Registration: <reg>

Page 1 ALSO carries a signature/prepared-by block in its top-right corner
(a real person's name above generic job-title lines -- "Asst Manager
Engineering Planning", "Planning Department", "Engineering Division" -- and
the company name repeated once more). That block is confirmed to sit well
outside the header-metadata crop region this module actually OCRs (a
left-hand region ending before the signature block's own left edge, checked
directly against the real sample file) and is never read, parsed, or
recorded anywhere by this module -- no column here carries any person's
name, and none should ever be added for one.

The data table itself starts on page 1 (immediately below the header
metadata, no separate cover-only page as an earlier rough pass of this file
assumed) and continues through the last page. The column-header row
("Item | ATA | Functional Location | Equipment Description | Material |
Serial No. | Equipt | Install Date | TSN Hrs | TSN Cyc | TSI Hrs | TSI Cyc |
Remarks") is confirmed, directly, to reprint at the exact same vertical
fraction of the page (~0.206 x page height) on every page, including page 1
despite its extra banner/signature content above -- so a single fixed
data-region Y-start works unchanged across the whole file.

Per this package's usual approach for a badly-behaved whole-page/whole-row
OCR pass (confirmed directly here too -- a whole-row pass drops or
transposes cells across this table's 13 columns), most columns are OCR'd as
their own full-height ruled strip and every word is assigned to the real
ruled row it falls within (see below), the same general technique as
`msn_occm_list_scanned.py` in this same package, but keyed to the table's
own ruled row lines rather than to a single anchor column's OCR'd
positions.

The row grid itself is recovered directly from the rendered page's own
pixels (a numpy darkfrac scan over the ATA column's X-span, the same
horizontal-ruled-line technique `llp_variants/kalstar_aviation_llp_status.py`
uses in this codebase) rather than estimated from any one column's OCR'd
word positions -- confirmed directly to be both more precise (exact ruled
edges, not an estimated midpoint between two anchors) and necessary: the
ATA column specifically is confirmed, by direct experimentation against the
real sample file, to OCR very badly as a single tall multi-row strip (every
psm tried recovers at most one or two digit-runs out of dozens of visually
identical, perfectly legible "21"/"22"/... cells) -- but the very same
pixels OCR cleanly once cropped down to ONE ruled row at a time, padded with
a white border, and upscaled ~4x before OCR. Confirmed directly, side by
side, on the same cells; the cause isn't confirmed (a repeating short
digit-run over many near-identical short cells seems to confuse the OCR
engine's own internal line/word segmentation when read as one tall block,
distinct from the "wide/thin crop" effect `msn_occm_list_scanned.py` notes
for its own columns), but the fix verified reliably (~96% of ATA cells
recovered directly on the real sample file, the rest left blank and
recovered downstream by `sheet_types/occm.py`'s generic ATA forward-fill),
so ATA alone gets this per-row treatment while every other column keeps the
cheaper single full-height-strip OCR pass.

Column X-boundaries (px @ 300dpi) below are measured directly from the real
rendered page's own ruled vertical-line pixel columns (a >40%-dark column
over the data-grid's Y-span), confirmed stable across the first, a middle,
and the last page of the real sample file.

A data row, columns in order (values genericized -- see this project's
data-sensitivity convention, no real value from the source file is ever
written in this module)::

    <item> | <ata> | <reg>/<zone>/<subsystem>/<pos> | <description text> |
    <pn> | <sn> | <equipt-id> | <dd>/<mm>/<yyyy> | <tsn-hrs> | <tsn-cyc> |
    <tsi-hrs> | <tsi-cyc> | <remarks>

FUNCTIONAL_LOCATION values are themselves slash-delimited codes that embed
the aircraft's own registration as their first segment (confirmed directly
on the real sample file) -- this is genuine source-table content, not
anything this module adds, and is captured as-is like every other cell;
only the separate signature block described above is excluded.

Header metadata (AS_OF_DATE, AIRCRAFT_MODEL, AIRCRAFT_REG, AIRFRAME_HOURS,
AIRFRAME_CYCLES) is parsed once, from the first page it OCRs cleanly on,
and stamped identically onto every row of the file, per this package's usual
header-plus-body OCCM convention (e.g. `msn_occm_list_scanned.py`).
"""
from __future__ import annotations
import re

import numpy as np
from PIL import Image, ImageOps

from sheet_types.occm_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_words, ocr_text, page_count

NAME = "On-Component/ Component Monitoring Listing Status"

# This module's known source file has no text layer at all (confirmed via
# pdfplumber -- 0 chars on every page), so these SIGNATURES can never fire
# through occm.py's normal pdfplumber head-text match; real detection
# happens via ocr_detect() below. Deliberately left empty, same convention
# as this package's other purely-OCR variants (e.g.
# `occm_list_func_loc_scanned.py`).
SIGNATURES = []

CANONICAL_COLUMNS = [
    "ITEM",
    "ATA",
    "FUNCTIONAL_LOCATION",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "EQUIPMENT_NUMBER",
    "INSTALL_DATE",
    "TSN_HOURS",
    "TSN_CYCLES",
    "TSI_HOURS",
    "TSI_CYCLES",
    "REMARKS",
    # Header metadata, parsed once and stamped on every row.
    "AS_OF_DATE",
    "AIRCRAFT_MODEL",
    "AIRCRAFT_REG",
    "AIRFRAME_HOURS",
    "AIRFRAME_CYCLES",
]

_HOURS_RULE = {"pattern": r"^\d+(\.\d+)?$", "allow_empty": True}
_CYC_RULE = {"pattern": r"^\d+$", "allow_empty": True}
_OVERRIDES = {
    "ITEM": {"pattern": r"^\d{1,4}$"},
    # A handful of ATA cells still come back blank even with the per-row OCR
    # pass this module uses (see module docstring) -- allow_empty so those
    # don't drop the row, since `sheet_types/occm.py`'s generic forward-fill
    # (any CANONICAL_COLUMNS with "ATA") recovers a blank cell from the same
    # chapter run's earlier rows anyway.
    "ATA": {"allow_empty": True},
    "FUNCTIONAL_LOCATION": {
        "pattern": r"^[A-Z0-9\-]+(?:/[A-Z0-9_\-]+){2,4}$",
        "uppercase": True,
    },
    "EQUIPMENT_NUMBER": {"pattern": r"^\d{3,8}$", "allow_empty": True},
    "INSTALL_DATE": {"pattern": r"^\d{2}/\d{2}/\d{4}$", "allow_empty": True},
    "TSN_HOURS": _HOURS_RULE, "TSN_CYCLES": _CYC_RULE,
    "TSI_HOURS": _HOURS_RULE, "TSI_CYCLES": _CYC_RULE,
    # REMARKS is confirmed blank on the large majority of real rows.
    "REMARKS": {"allow_empty": True},
    # Header metadata -- each value is a single figure parsed once and
    # stamped identically on every row of the file, so a tight pattern here
    # would either flag every single row over one OCR misread in one place,
    # or none at all -- neither is a useful per-row signal. Genuine per-row
    # corruption is still caught by the row-level rules above. Same
    # reasoning as this package's other header-plus-body OCCM variants
    # (e.g. `msn_occm_list_scanned.py`'s own header fields).
    "AS_OF_DATE": {"allow_empty": True},
    "AIRCRAFT_MODEL": {"allow_empty": True},
    "AIRCRAFT_REG": {"allow_empty": True},
    "AIRFRAME_HOURS": {"allow_empty": True},
    "AIRFRAME_CYCLES": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Column X-boundaries (px @ 300dpi), measured directly from the real
# rendered page's own ruled vertical-line pixel columns -- confirmed stable
# across the first, a middle, and the last page of the real sample file
# (see module docstring). ATA is handled separately, per-row (see
# `_ocr_ata_cell` below), but keeps its own entry here for the row-grid scan
# and for a narrower, safely-inset crop within its own ruled bounds.
_COLUMNS = [
    (90, 180, "ITEM"),
    (180, 270, "ATA"),
    (270, 703, "FUNCTIONAL_LOCATION"),
    (703, 1181, "DESCRIPTION"),
    (1181, 1469, "PART_NUMBER"),
    (1469, 1718, "SERIAL_NUMBER"),
    (1718, 1969, "EQUIPMENT_NUMBER"),
    (1969, 2227, "INSTALL_DATE"),
    (2227, 2458, "TSN_HOURS"),
    (2458, 2684, "TSN_CYCLES"),
    (2684, 2916, "TSI_HOURS"),
    (2916, 3094, "TSI_CYCLES"),
    (3094, 3381, "REMARKS"),
]
# Columns OCR'd as a single full-height strip, then bucketed into ruled rows
# (everything except ATA, which gets its own per-row crop -- see above).
_STRIP_COLUMNS = [name for _, _, name in _COLUMNS if name != "ATA"]
# DESCRIPTION and REMARKS are genuine free text and may wrap across more
# than one OCR word/line -- joined with spaces. Every other column is a
# compact code/figure, confirmed to print as a single token per row on the
# real sample file, but still joined with no separator as a safety net
# against an occasional OCR word-split.
_JOIN_SPACE = {"DESCRIPTION", "REMARKS"}

# The column-header row ("Item | ATA | ...") reprints at this same fraction
# of page height on every page, confirmed directly (measured at ~0.206 on
# the first, second, and last page of the real sample file, including page
# 1 despite its extra banner/signature content above it) -- so a single
# fixed data-region start works unchanged across the whole file.
_DATA_Y0_FRAC = 0.225
_DATA_Y1_FRAC = 0.93
# Header metadata block sits between the title line and the column-header
# row, confined to the left ~65% of the page width -- confirmed directly
# that the real sample file's signature block (top-right corner, page 1
# only) sits entirely to the right of this crop, so it is never OCR'd here.
_HEADER_Y0_FRAC = 0.14
_HEADER_Y1_FRAC = 0.225
_HEADER_X1_FRAC = 0.65

# Row-grid detection: a pixel row counts as part of a ruled horizontal line
# once at least this fraction of the ATA column's own width is dark.
_LINE_DARKFRAC_THRESH = 0.5
_DARK_PIXEL_THRESH = 150
# Stray ruled-border artifacts occasionally picked up as their own word box.
_NOISE_TOKEN_RE = re.compile(r"^[|\[\]_\-—–]+$")

_AS_OF_DATE_RE = re.compile(r"AS\s*OF\s*DATE:?\s*(\d{1,2}/\d{1,2}/\d{4})", re.IGNORECASE)
_MODEL_RE = re.compile(r"AIRCRAFT\s*MODEL:?\s*(\S+)", re.IGNORECASE)
_REG_RE = re.compile(r"REGISTRATION:?\s*(\S+)", re.IGNORECASE)
_HOURS_RE = re.compile(r"AIRFRAME\s*HOURS:?\s*([\d.,]+)", re.IGNORECASE)
_CYCLES_RE = re.compile(r"AIRFRAME\s*CYCLES:?\s*(\d+)", re.IGNORECASE)
_ATA_DIGITS_RE = re.compile(r"(\d{2,3})")

_HEADER_FIELDS = [
    "AS_OF_DATE", "AIRCRAFT_MODEL", "AIRCRAFT_REG",
    "AIRFRAME_HOURS", "AIRFRAME_CYCLES",
]

# Title anchor for ocr_detect() -- checked directly (grep across every
# SIGNATURES list in sheet_types/{occm,ht,llp}.py and every existing
# occm_variants/ht_variants/llp_variants file): this phrase appears nowhere
# else, and is not a substring of (nor contains) any other variant's own
# SIGNATURES/ocr_detect anchor.
_TITLE_RE = re.compile(r"COMPONENT\s+MONITORING\s+LISTING\s+STATUS", re.IGNORECASE)


def _col_bounds(name: str) -> tuple[int, int]:
    for lo, hi, col in _COLUMNS:
        if col == name:
            return lo, hi
    raise KeyError(name)


def _find_row_bounds(img, y0: int, y1: int) -> list[tuple[int, int]]:
    """Recover the table's own ruled row boundaries directly from the page
    image (see module docstring) -- a numpy darkfrac scan over the ATA
    column's own X-span, the same horizontal-ruled-line technique
    `llp_variants/kalstar_aviation_llp_status.py` uses in this codebase.
    Returns consecutive (top, bottom) pixel pairs, one per real table row
    (correctly wider for a two-line-wrapped DESCRIPTION row, since the ruled
    line either side of it is further apart on the real page)."""
    lo, hi = _col_bounds("ATA")
    arr = np.array(img.convert("L"))
    band = arr[y0:y1, lo:hi]
    darkfrac = (band < _DARK_PIXEL_THRESH).mean(axis=1)
    lines: list[int] = []
    in_run = False
    run_start = 0
    for i, v in enumerate(darkfrac):
        if v > _LINE_DARKFRAC_THRESH and not in_run:
            in_run = True
            run_start = i
        elif v <= _LINE_DARKFRAC_THRESH and in_run:
            in_run = False
            lines.append(y0 + (run_start + i) // 2)
    if in_run:
        lines.append(y0 + (run_start + len(darkfrac)) // 2)
    return list(zip(lines, lines[1:]))


async def _ocr_ata_cell(img, top: int, bot: int) -> str:
    """OCR a single ruled ATA cell (see module docstring on why this column
    alone needs a per-row crop rather than the cheaper full-strip pass every
    other column uses). A few px inset off the ruled lines themselves, a
    white padding border, and a 4x upscale are all confirmed directly,
    side-by-side against the real sample file, to be necessary -- dropping
    any one of the three reproduces the bad multi-row-strip failure mode."""
    lo, hi = _col_bounds("ATA")
    inset_lo, inset_hi = lo + 5, hi - 5
    top_i, bot_i = top + 3, bot - 3
    if bot_i - top_i < 5 or inset_hi - inset_lo < 5:
        return ""
    crop = img.crop((inset_lo, top_i, inset_hi, bot_i))
    crop = crop.resize((crop.width * 4, crop.height * 4), Image.LANCZOS)
    padded = ImageOps.expand(crop, border=20, fill=(255, 255, 255))
    text = await ocr_text(padded, psm=6)
    m = _ATA_DIGITS_RE.search(text)
    return m.group(1) if m else ""


async def _ocr_column(img, name: str, y0: int, y1: int, scale: int = 2) -> list[tuple[float, str]]:
    """OCR one column's full-height strip and return (top, text) pairs in
    original-image page coordinates."""
    lo, hi = _col_bounds(name)
    x0 = max(0, int(lo))
    x1 = min(img.width, int(hi))
    crop = img.crop((x0, y0, x1, y1))
    if scale != 1:
        crop = crop.resize((crop.width * scale, crop.height * scale), Image.LANCZOS)
    words = await ocr_words(crop, psm=6, min_conf=-1)
    out = []
    for w in words:
        text = str(w.get("text", "")).strip()
        if not text or _NOISE_TOKEN_RE.match(text):
            continue
        out.append((y0 + w["top"] / scale, text))
    return out


def _row_idx_for(top: float, row_bounds: list[tuple[int, int]]) -> int | None:
    """Which real ruled row a column-strip word's Y-position falls inside --
    exact containment against the table's own ruled boundaries (see
    `_find_row_bounds`), not a fixed-pixel tolerance, so a taller
    two-line-wrapped row is handled the same way as every ordinary row."""
    for i, (rtop, rbot) in enumerate(row_bounds):
        if rtop <= top <= rbot:
            return i
    return None


def _join(tokens: list[str], col_name: str) -> str:
    sep = " " if col_name in _JOIN_SPACE else ""
    return sep.join(tokens).strip(" |[]_-—–")


def _parse_header_text(text: str, meta: dict) -> None:
    for pat, key in (
        (_AS_OF_DATE_RE, "AS_OF_DATE"),
        (_MODEL_RE, "AIRCRAFT_MODEL"),
        (_REG_RE, "AIRCRAFT_REG"),
        (_HOURS_RE, "AIRFRAME_HOURS"),
        (_CYCLES_RE, "AIRFRAME_CYCLES"),
    ):
        if meta.get(key):
            continue
        m = pat.search(text)
        if m:
            meta[key] = m.group(1)


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback (see
    sheet_types/occm.py) -- this variant's known source file has no text
    layer at all, so it can never be found through the normal pdfplumber
    head-text match.

    Anchors on the report's own title-line phrase, confirmed directly
    (see module docstring)."""
    try:
        img = await render_page(pdf_path, 0, dpi=300)
        w, h = img.size
        crop = img.crop((0, 0, w, int(h * 0.14)))
        text = await ocr_text(crop, psm=6)
        return bool(_TITLE_RE.search(text))
    except Exception:
        return False


def _extract_page_rows(
    columns_words: dict[str, list[tuple[float, str]]],
    row_bounds: list[tuple[int, int]],
    ata_values: list[str],
) -> list[dict]:
    if not row_bounds:
        return []

    buckets: list[dict[str, list[str]]] = [
        {name: [] for name in _STRIP_COLUMNS} for _ in row_bounds
    ]
    for col_name in _STRIP_COLUMNS:
        for top, text in columns_words[col_name]:
            idx = _row_idx_for(top, row_bounds)
            if idx is not None:
                buckets[idx][col_name].append(text)

    rows = []
    for i in range(len(row_bounds)):
        b = buckets[i]
        item = _join(b["ITEM"], "ITEM")
        floc = _join(b["FUNCTIONAL_LOCATION"], "FUNCTIONAL_LOCATION")
        description = _join(b["DESCRIPTION"], "DESCRIPTION")
        part_number = _join(b["PART_NUMBER"], "PART_NUMBER")
        serial_number = _join(b["SERIAL_NUMBER"], "SERIAL_NUMBER")
        if not item and not floc and not description and not part_number and not serial_number:
            # No real cell content attached to this ruled row at all --
            # almost certainly page furniture (e.g. the column-header row
            # itself, if it ever lands inside the scanned Y-range) rather
            # than a genuine data row.
            continue
        rows.append({
            "ITEM": item,
            "ATA": ata_values[i] if i < len(ata_values) else "",
            "FUNCTIONAL_LOCATION": floc,
            "DESCRIPTION": description,
            "PART_NUMBER": part_number,
            "SERIAL_NUMBER": serial_number,
            "EQUIPMENT_NUMBER": _join(b["EQUIPMENT_NUMBER"], "EQUIPMENT_NUMBER"),
            "INSTALL_DATE": _join(b["INSTALL_DATE"], "INSTALL_DATE"),
            "TSN_HOURS": _join(b["TSN_HOURS"], "TSN_HOURS"),
            "TSN_CYCLES": _join(b["TSN_CYCLES"], "TSN_CYCLES"),
            "TSI_HOURS": _join(b["TSI_HOURS"], "TSI_HOURS"),
            "TSI_CYCLES": _join(b["TSI_CYCLES"], "TSI_CYCLES"),
            "REMARKS": _join(b["REMARKS"], "REMARKS"),
        })
    return rows


async def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    header_meta = {k: "" for k in _HEADER_FIELDS}
    n_pages = await page_count(pdf_path)
    for page_index in range(n_pages):
        img = await render_page(pdf_path, page_index, dpi=300)
        w, h = img.size

        if not all(header_meta.values()):
            crop = img.crop((0, int(h * _HEADER_Y0_FRAC), int(w * _HEADER_X1_FRAC),
                              int(h * _HEADER_Y1_FRAC)))
            header_text = await ocr_text(crop, psm=4)
            _parse_header_text(header_text, header_meta)

        y0, y1 = int(h * _DATA_Y0_FRAC), int(h * _DATA_Y1_FRAC)
        row_bounds = _find_row_bounds(img, y0, y1)

        columns_words = {}
        for col_name in _STRIP_COLUMNS:
            columns_words[col_name] = await _ocr_column(img, col_name, y0, y1)

        ata_values = [await _ocr_ata_cell(img, top, bot) for top, bot in row_bounds]

        for rec in _extract_page_rows(columns_words, row_bounds, ata_values):
            rec["_page"] = page_index + 1
            rec.update(header_meta)
            records.append(rec)
    return records
