"""OCCM List, "MSN<n> OCCM List" title -- scanned, no text layer, OCR
required throughout.

Confirmed on a real corpus file (15 pages, 0 extractable chars on every page
via pdfplumber -- a straight scan). Page 1 carries a small boxed header
block, confirmed to repeat verbatim on every following page::

    MSN<n> OCCM List                              <operator logo/wordmark>
    A/C Reg.: <reg>          A/C MSN:<n>
    A/C TSN: <n>             Status Date: <date>
    A/C CSN: <n>             A/C Manufacture Date:<date>

The operator logo/wordmark (top-right of the header box) is confirmed
directly on the real sample file and intentionally NOT extracted into any
column here -- out of scope for this module, and per this project's
data-sensitivity convention no operator name is recorded anywhere below.
The title line's leading "MSN<n>" has no space between the literal "MSN"
and the digit run -- confirmed directly and used both as this module's
`ocr_detect()` anchor and as a fallback source for the MSN column (see
`_TITLE_RE` below); this distinguishes it from every other sibling
title phrase in this package that also combines "MSN" and "OCCM" (checked
directly, e.g. one sibling's own title reads "MSN <n> OCCM COMPONENT
INVENTORY" and another's reads "OCCM SUMMARY LIST MSN <n>" -- both carry a
space after "MSN" and/or place "OCCM" before "MSN", neither of which this
title does).

Column header row (confirmed directly, reprints on every page directly
under the metadata box)::

    ATA | Description | PN | SN | FIN | INSTALL TIME

A data row, tokens in column order: ATA, DESCRIPTION, PART_NUMBER,
SERIAL_NUMBER, FIN, INSTALL_DATE -- confirmed directly across the first,
several middle, and the last page of the real sample file, e.g. (row shape
only, values genericized)::

    <ata> | <description text> | <pn> | <sn> | <fin> | <yyyy>/<m>/<d>

Unlike several sibling OCCM formats in this package that print ATA only on
the first row of each chapter run, ATA is confirmed to print on every
single row of this file (no forward-fill needed). FIN is confirmed
sometimes blank on real rows (seen on the real sample file's last page) --
kept `allow_empty` accordingly. INSTALL TIME values are shaped
`<yyyy>/<m-or-mm>/<d-or-dd>` (no zero-padding enforced by the source),
confirmed directly across many rows.

OCR approach -- confirmed by direct experimentation against the real
sample file, and notably different from this package's usual whole-page/
whole-row word-bucketing technique:

A whole-page or whole-row-width OCR pass (either `ocr_text()` or
`ocr_words()`, at every PSM tried) on this file's data grid comes back
badly corrupted -- confirmed directly, reproduced identically via a raw
`tesseract` CLI pass on a saved crop, so it is not an artifact of how this
project's OCR bridge calls the engine. The very same pixels, however, OCR
cleanly once cropped down to a single ruled COLUMN's own width (spanning
the full column height) and upscaled ~2x before OCR -- confirmed directly,
side by side, on the same rows. The cause isn't confirmed (a wide/thin
crop aspect ratio confusing the OCR engine's own internal page-segmentation
heuristics is the leading suspect, given the row-width crop and the
column-width crop are pixel-identical content otherwise), but the fix
verified reliably, so this module extracts one column strip at a time
rather than one row/page at a time.

Column X-boundaries (px @ 300dpi) below are measured directly from the
real rendered page's own ruled vertical-line pixel columns (a >50%-dark
column over the data-grid's Y-span), confirmed stable across the first,
second, and last pages of the real sample file.

Row anchoring: ATA is used as the per-row anchor rather than Y-clustering
every column's words independently, because the narrow ATA column strip
OCRs at very high confidence (>90, confirmed directly) with one clean
digit-run word per row, spaced at a near-uniform pitch -- a much more
reliable anchor than trying to Y-cluster the free-text DESCRIPTION column
or the frequently row-split PART_NUMBER/INSTALL_DATE columns directly.
Each of the other five columns is OCR'd as its own strip, and every
resulting word is assigned to its nearest ATA anchor (by Y-distance,
within a tolerance below half the file's real row pitch) -- this also
transparently handles the file's occasional taller, wrapped-DESCRIPTION
row (confirmed directly on a real page, e.g. a two-line component
description) without any special-case code, since a wrapped line's second
half still lands closer to the same row's ATA anchor than to the next
row's.

Known limitation, confirmed directly against the real sample file: a
handful of PART_NUMBER/INSTALL_DATE cells are themselves split by the OCR
engine into two adjacent word-boxes with no real space in the source
(e.g. a compact date rendering as two boxes) -- these are rejoined with no
separator per column (DESCRIPTION is the only column joined with spaces,
being genuine free text), which recovers most of these correctly but is a
best-effort fix, not a guarantee. Separately, on the rare row where the
ATA anchor itself is misread badly enough to not resemble a bare 1-3 digit
number, that row's other cells have no anchor to attach to and are lost
rather than guessed onto a neighboring row -- both are expected to surface
as a lower row count / soft-validation flags rather than silently wrong
data, per this project's soft-validation convention (see
`shared/aviation_rules.py`).
"""
from __future__ import annotations
import re

from PIL import Image

from sheet_types.occm_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, ocr_words, page_count

NAME = "OCCM List (MSN-Prefixed Title, Scanned)"

# This module's known source file has no text layer at all (confirmed via
# pdfplumber -- 0 chars on every page), so these SIGNATURES can never fire
# through occm.py's normal pdfplumber head-text match; real detection
# happens via ocr_detect() below. Deliberately left empty, same convention
# as this package's other purely-OCR variants (e.g.
# `occm_list_func_loc_scanned.py`).
SIGNATURES = []

CANONICAL_COLUMNS = [
    "ATA",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "FIN",
    "INSTALL_DATE",
    # Header metadata, parsed once (page 1) and stamped on every row.
    "AIRCRAFT_REG",
    "MSN",
    "AC_TSN",
    "AC_CSN",
    "MFG_DATE",
    "REPORT_DATE",
]

_OVERRIDES = {
    # Global FIN rule has no allow_empty -- confirmed directly that real
    # rows on this file sometimes carry a blank FIN cell (seen on the real
    # sample file's last page).
    "FIN": {"allow_empty": True},
    "INSTALL_DATE": {
        "pattern": r"^\d{4}/\d{1,2}/\d{1,2}$",
        "allow_empty": True,
    },
    # Header metadata -- each value is a single figure parsed once and
    # stamped identically on every row of the file, so a tight pattern here
    # would either flag every single row over one OCR misread in one
    # place, or none at all -- neither is a useful per-row signal. Genuine
    # per-row corruption is still caught by the row-level rules above. Same
    # reasoning as this package's other header-plus-body OCCM variants
    # (e.g. `component_list_occm_airframe.py`'s own header fields).
    "AIRCRAFT_REG": {"allow_empty": True},
    "MSN": {"allow_empty": True},
    "AC_TSN": {"allow_empty": True},
    "AC_CSN": {"allow_empty": True},
    "MFG_DATE": {"allow_empty": True},
    "REPORT_DATE": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Column X-boundaries (px @ 300dpi), measured directly from the real
# rendered page's own ruled vertical-line pixel columns -- confirmed stable
# across the first, second, and last pages of the real sample file (see
# module docstring). Deliberately kept a few px INSIDE each ruled border
# rather than open-ended/flush against it (unlike this package's usual
# X-bucket convention of `-1e9`/`1e9` sentinel bounds): confirmed directly
# that a full page-height column crop whose edge lands ON (or beyond) the
# table's own outer ruled border line comes back badly corrupted -- the
# very same pixels OCR cleanly once the crop is pulled a few px inward, off
# that border. This is a stronger version of the same "wide/thin crop
# confuses the OCR engine's own segmentation" effect noted in the module
# docstring, specific to a tall crop that also contains a near-full-height
# solid ruled line.
_COLUMNS = [
    (238, 314, "ATA"),
    (322, 1005, "DESCRIPTION"),
    (1013, 1385, "PART_NUMBER"),
    (1393, 1622, "SERIAL_NUMBER"),
    (1630, 1901, "FIN"),
    (1908, 2195, "INSTALL_DATE"),
]
# Compact codes with no legitimate internal space (see module docstring) --
# joined with no separator. DESCRIPTION is genuine free text and is the
# only column joined with spaces.
_JOIN_NOSPACE = {"ATA", "PART_NUMBER", "SERIAL_NUMBER", "FIN", "INSTALL_DATE"}

# Stray ruled-border artifacts occasionally picked up as their own word box
# -- dropped before a row's tokens are joined.
_NOISE_TOKEN_RE = re.compile(r"^[|\[\]_\-—–]+$")

# Row anchor: a bare 1-3 digit ATA chapter code (see module docstring on
# why ATA, not Y-clustering every column independently, anchors each row).
_ATA_TOKEN_RE = re.compile(r"^\d{1,3}$")

# Y-tolerance for assigning a non-ATA column's word to its nearest ATA
# anchor -- measured directly against the real sample file's own row pitch
# (~37px @ 300dpi between consecutive rows); comfortably below half that,
# so a word never gets pulled onto an adjacent row, while still wide enough
# to catch a wrapped second DESCRIPTION line sitting a few px off its row's
# own anchor.
_ANCHOR_TOLERANCE_PX = 18

# Title anchor: "MSN<n> OCCM List" with NO space between "MSN" and the
# digit run (see module docstring on why this distinguishes it from every
# other sibling "MSN"+"OCCM" title phrase in this package -- checked
# directly against every SIGNATURES/ocr_detect anchor in
# sheet_types/{occm,ht,llp}.py and every existing occm_variants file: none
# combines the literal substring "MSN" immediately (no space) followed by
# digits and then "OCCM").
_TITLE_RE = re.compile(r"MSN(\d+)\s*OCCM\s*LIST", re.IGNORECASE)

# Header field patterns -- tolerant of "A/C" OCR'ing as "AIC" (confirmed
# directly, a very common substitution on this real sample file: the
# forward slash is frequently misread as a capital I).
_REG_RE = re.compile(r"A[/I]?C\s*REG\.?:?\s*([A-Z0-9\-]+)", re.IGNORECASE)
_MSN_RE = re.compile(r"A[/I]?C\s*MSN:?\s*(\d+)", re.IGNORECASE)
_TSN_RE = re.compile(r"A[/I]?C\s*TSN:?\s*([\d.]+)", re.IGNORECASE)
_STATUS_DATE_RE = re.compile(r"STATUS\s*DATE:?\s*(\S+)", re.IGNORECASE)
_CSN_RE = re.compile(r"C\s*SN:?\s*(\d+)", re.IGNORECASE)
_MFG_DATE_RE = re.compile(r"MANUFACTURE\s*DATE[:\-]?\s*(\S+)", re.IGNORECASE)

_HEADER_FIELDS = ["AIRCRAFT_REG", "MSN", "AC_TSN", "AC_CSN", "MFG_DATE", "REPORT_DATE"]


def _col_bounds(name: str) -> tuple[float, float]:
    for lo, hi, col in _COLUMNS:
        if col == name:
            return lo, hi
    raise KeyError(name)


async def _ocr_column(img, name: str, y0: int, y1: int, scale: int = 2) -> list[tuple[float, str]]:
    """OCR one column's full-height strip (see module docstring on why a
    column-width crop OCRs far more reliably here than a row-width or
    whole-page crop) and return (top, text) pairs in original-image page
    coordinates."""
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


def _nearest_anchor_idx(top: float, anchors: list[float]) -> int | None:
    best_idx, best_dist = None, None
    for i, a in enumerate(anchors):
        d = abs(top - a)
        if best_dist is None or d < best_dist:
            best_idx, best_dist = i, d
    if best_idx is not None and best_dist <= _ANCHOR_TOLERANCE_PX:
        return best_idx
    return None


def _join(tokens: list[str], col_name: str) -> str:
    sep = "" if col_name in _JOIN_NOSPACE else " "
    return sep.join(tokens).strip(" |[]_-—–")


def _parse_header_text(text: str, meta: dict) -> None:
    for pat, key, upper in (
        (_REG_RE, "AIRCRAFT_REG", True),
        (_MSN_RE, "MSN", False),
        (_TSN_RE, "AC_TSN", False),
        (_STATUS_DATE_RE, "REPORT_DATE", False),
        (_MFG_DATE_RE, "MFG_DATE", False),
    ):
        if meta.get(key):
            continue
        m = pat.search(text)
        if m:
            meta[key] = m.group(1).upper() if upper else m.group(1)
    if not meta.get("MSN"):
        m = _TITLE_RE.search(text)
        if m:
            meta["MSN"] = m.group(1)


async def _parse_csn(img, meta: dict) -> None:
    """A/C CSN's own header cell, OCR'd as its own narrow/upscaled crop --
    confirmed directly that this value is meaningfully less reliable than
    the file's other header fields when read as part of a wider header-block
    pass (the "A/C CSN" line sits directly above the "A/C Manufacture Date"
    line and the two are confirmed to bleed into each other at a whole-block
    OCR pass), so it gets the same per-field treatment as the main data
    grid's columns rather than being trusted from the wider pass."""
    if meta.get("AC_CSN"):
        return
    w, h = img.size
    # Fixed region measured directly against the real sample file's header
    # box (see module docstring) -- the "A/C CSN: <n>" cell, left column,
    # third metadata row.
    crop = img.crop((int(w * 0.094), int(h * 0.109), int(w * 0.33), int(h * 0.117)))
    crop = crop.resize((crop.width * 4, crop.height * 4), Image.LANCZOS)
    text = await ocr_text(crop, psm=7)
    m = _CSN_RE.search(text.upper())
    if m:
        meta["AC_CSN"] = m.group(1)


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback (see
    sheet_types/occm.py) -- this variant's known source file has no text
    layer at all, so it can never be found through the normal pdfplumber
    head-text match.

    Anchors on "MSN<n> OCCM LIST" with no space between "MSN" and the
    digit run (see module docstring for why this is distinguishable from
    every other sibling "MSN"+"OCCM" title phrase in this package)."""
    try:
        img = await render_page(pdf_path, 0, dpi=300)
        w, h = img.size
        crop = img.crop((0, 0, w, int(h * 0.1)))
        text = (await ocr_text(crop, psm=6)).upper()
        return bool(_TITLE_RE.search(text))
    except Exception:
        return False


def _extract_page_rows(columns_words: dict[str, list[tuple[float, str]]]) -> list[dict]:
    ata_tokens = [
        (top, t) for top, t in columns_words["ATA"] if _ATA_TOKEN_RE.match(t)
    ]
    if not ata_tokens:
        return []
    ata_tokens.sort(key=lambda p: p[0])
    anchors = [top for top, _ in ata_tokens]
    ata_values = [t for _, t in ata_tokens]

    buckets: list[dict[str, list[str]]] = [
        {name: [] for _, _, name in _COLUMNS if name != "ATA"} for _ in anchors
    ]
    for col_name in ("DESCRIPTION", "PART_NUMBER", "SERIAL_NUMBER", "FIN", "INSTALL_DATE"):
        for top, text in columns_words[col_name]:
            idx = _nearest_anchor_idx(top, anchors)
            if idx is not None:
                buckets[idx][col_name].append(text)

    rows = []
    for i, ata in enumerate(ata_values):
        b = buckets[i]
        part_number = _join(b["PART_NUMBER"], "PART_NUMBER")
        serial_number = _join(b["SERIAL_NUMBER"], "SERIAL_NUMBER")
        description = _join(b["DESCRIPTION"], "DESCRIPTION")
        if not part_number and not serial_number and not description:
            # No real cell content attached to this ATA anchor at all --
            # almost certainly page furniture (e.g. a stray digit run in
            # a footer/signature block) rather than a genuine data row.
            continue
        rows.append({
            "ATA": ata,
            "DESCRIPTION": description,
            "PART_NUMBER": part_number,
            "SERIAL_NUMBER": serial_number,
            "FIN": _join(b["FIN"], "FIN"),
            "INSTALL_DATE": _join(b["INSTALL_DATE"], "INSTALL_DATE"),
        })
    return rows


async def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    header_meta = {k: "" for k in _HEADER_FIELDS}
    n_pages = await page_count(pdf_path)
    for page_index in range(n_pages):
        img = await render_page(pdf_path, page_index, dpi=300)
        w, h = img.size
        if not header_meta["MSN"] or not header_meta["AC_CSN"]:
            crop = img.crop((0, int(h * 0.055), int(w * 0.68), int(h * 0.125)))
            header_text = await ocr_text(crop, psm=4)
            _parse_header_text(header_text, header_meta)
            await _parse_csn(img, header_meta)

        # Data grid starts just below the repeated column-header row, which
        # sits at the same fixed position on every page (confirmed
        # directly) -- and runs to the bottom of the page; any page
        # furniture below the last real row (page-footer text, the last
        # page's signature block) is filtered out downstream by requiring
        # a bare-digit ATA anchor with at least one attached data cell.
        y0, y1 = int(h * 0.121), h
        columns_words = {}
        for _, _, col_name in _COLUMNS:
            columns_words[col_name] = await _ocr_column(img, col_name, y0, y1)

        for rec in _extract_page_rows(columns_words):
            rec["_page"] = page_index + 1
            rec.update(header_meta)
            records.append(rec)
    return records
