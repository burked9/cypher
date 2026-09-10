"""OCCM Component Status (Posn/Fin ruled grid) -- scanned, no text layer,
OCR required throughout.

Confirmed directly on a real corpus file: 0 extractable characters on every
page via pdfplumber (a straight scan). Every page carries the same header
block, then a single ruled 8-column grid::

    <reg> (<type>)                    DATE       HOURS      CYCLES
    OCCM Component Status             <as-of-date> <hours>  <cycles>

    ATA | Part Number | Serial number | Description | Posn/Fin | Instal Date | TSN | CSN
    <ata> | <pn> | <sn> | <description...> | <posn> | <date> | <tsn> | <csn>

TSN/CSN print as the literal text "O/C" ("on condition") on every row of
the real sample file -- these are on-condition/on-condition-monitoring
components, which by definition never accumulate a numeric hours/cycles
total, so this is expected report content, not a parsing gap. A genuinely
numeric TSN/CSN value is still accepted by this module's own rules in case
another real file of the same template ever carries one.

This report's title line ("OCCM Component Status") is also this project's
existing `occm_component_status_report.py` module's own SIGNATURES entry,
and its column-header phrase overlaps loosely with
`occm_component_status_parent_serial_grid.py`'s own title text. Neither
collides with this module in practice: `occm_component_status_report.py` is
a *born-digital* variant reached only through the router's pdfplumber
SIGNATURES match (its own known source file has a real, if corrupted, text
layer; this module's known source file has none at all, so that match can
never fire here) -- its column shape is also different (NO/ATA/LOCATION/
DESCRIPTION/PART_NUMBER/SERIAL_NUMBER/INSTALL_DATE/TSI/CSI, no POSN/FIN, no
DATE/HOURS/CYCLES box). `occm_component_status_parent_serial_grid.py` is
reached only via its own `ocr_detect()`, anchored on the phrase "PARENT
SERIAL" -- this module's known source file has no PARENT_SERIAL column at
all (confirmed directly), so that anchor never fires here either, and this
module's own `ocr_detect()` below requires the title line PLUS a `<reg>
(<type>)`-shaped first line, a shape that module's own known source file's
header does not carry (its own reg/model/MSN fields print as separate
`Regn.:`/`MSN:` labelled lines, not a parenthesised type on the title line
itself). SIGNATURES is deliberately left empty here (same convention as
that module) since it can never fire through the router's normal pdfplumber
head-text match on a blank-text file; real detection happens only via
`ocr_detect()` below.

OCR approach, confirmed directly, side by side, against the real sample
file:

A whole-page OCR pass (any psm) fails badly on this ruled grid -- entire
rows collapse into garbled blobs, and a per-row pixel-ruling-line scan
(the technique used by this package's other ruled-grid OCR variants, e.g.
`occm_component_status_parent_serial_grid.py`) also fails here: this
particular scan's row-separator rulings are faint/skewed enough on several
pages that a pixel-darkness scan finds the header's own bottom border but
then nothing further -- confirmed directly by a side-by-side pixel-value
inspection of several pages, including ones where the same lines are
plainly visible to the eye. Pixel-grid detection is therefore used only for
the ONE robust anchor it can find reliably on every page (the shaded
column-header band's own bottom edge, via a page-wide row darkness scan --
this band is thick enough to survive any per-page skew that defeats the
thin single-pixel row rulings below it).

Row boundaries are instead recovered from OCR's own text positions, not
pixel rulings: each of the 8 columns is OCR'd as its own full-height ruled
strip (`ocr_words(psm=4)`), and the PART_NUMBER / SERIAL_NUMBER /
INSTALL_DATE columns' own per-line Y-centers (each reasonably distinct
value per row, unlike ATA/TSN/CSN which repeat the same value down dozens
of rows and are prone to a psm=4 pass silently merging consecutive
identical-looking lines) are merged into one master list of row anchors.
Every column's own words are then assigned to the nearest anchor. A cell
left empty by this pass (confirmed directly to happen on a modest fraction
of cells per page, mostly ATA/POSN/CSN) gets one direct fallback OCR call
on its own isolated, autocontrast-enhanced, 3x-upscaled, white-padded crop
-- same fallback technique as
`occm_component_status_parent_serial_grid.py`'s own `_ocr_cell_fallback`.

Column X-boundaries (fraction of page width) were measured directly from
the real rendered page's own ruled vertical-line pixel columns, confirmed
stable (within a handful of px) across the first, several middle, and the
last page of the real sample file. Confirmed directly that the DESCRIPTION,
POSITION, INSTALL_DATE, TSN and CSN columns' own real text sits close
enough to their left ruled border that a plain symmetric inset clips the
leading glyph on some pages (e.g. "XPDR" reads as "PDR", "LRRA" reads as
"RRA") -- each of those column crops is therefore extended a few px INTO
its own left border rather than inset from it (a stray border-line
artifact picked up this way reads as a `|`/`_`-shaped token and is dropped
by the noise-token filter below, so this is a one-sided trade worth making;
the equivalent right-side inset does not need the same treatment, confirmed
directly). ATA is narrow enough that both its own pixel margins need a
bigger, not smaller, inset to clear its ruled borders -- confirmed directly
side by side against several inset widths.

Known limitation, confirmed directly against the real sample file: OCR
quality degrades on a handful of rows per file (a smudged glyph run, or a
row whose own fallback crop still comes back unreadable) -- these surface
as either an empty cell or a cell that fails its own column's validation
pattern downstream, per this project's soft-validation convention (see
`shared/aviation_rules.py`), never silently "corrected" here.
"""
from __future__ import annotations
import re

import numpy as np
from PIL import Image, ImageOps

from sheet_types.occm_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, ocr_words, page_count

NAME = "OCCM Component Status (Posn/Fin Ruled Grid, Scanned)"

# This module's known source file has no text layer at all (confirmed via
# pdfplumber -- 0 chars on every page), so these SIGNATURES can never fire
# through occm.py's normal pdfplumber head-text match; real detection
# happens via ocr_detect() below. Deliberately left empty, same convention
# as this package's other purely-OCR ruled-grid variants (see module
# docstring for the collision analysis against the two other modules that
# share this report's generic title text).
SIGNATURES = []

CANONICAL_COLUMNS = [
    "ATA",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
    "POSITION",
    "INSTALL_DATE",
    "TSN",
    "CSN",
    # Header metadata, parsed once (page 1) and stamped on every row.
    "AIRCRAFT_REG",
    "AC_MODEL",
    "AS_OF_DATE",
    "AIRCRAFT_HOURS",
    "AIRCRAFT_CYCLES",
]

# TSN/CSN print as the literal "O/C" on every row of the real sample file
# (see module docstring) -- a genuine numeric value is also accepted, in
# case another real file of this same template carries one.
_OC_OR_NUM_RULE = {
    "pattern": r"^(?:O/C|\d+(?:\.\d+)?)$",
    "uppercase": True,
    "allow_empty": True,
}
_OVERRIDES = {
    # No global default exists for POSITION -- a compact side/zone/instance
    # code on most rows (e.g. a bare "#1"/"#2", a zone mnemonic, "ENG #1"),
    # confirmed to sometimes be blank on the real sample file (components
    # with no distinct install position).
    "POSITION": {
        "pattern": r"^[A-Z0-9#][A-Z0-9 /#\-]{0,20}$",
        "uppercase": True,
        "allow_empty": True,
    },
    # Real dates on this file are "D[D]-Mon-YY"; loose on the month/year
    # width to tolerate OCR noise rather than reject a genuinely valid date.
    "INSTALL_DATE": {
        "pattern": r"^\d{1,2}-[A-Za-z]{2,4}-\d{2,4}$",
        "allow_empty": True,
    },
    "TSN": _OC_OR_NUM_RULE,
    "CSN": _OC_OR_NUM_RULE,
    # Header metadata -- each value is a single figure parsed once (page 1)
    # and stamped identically on every row of the file, so a tight pattern
    # here would either flag every single row over one OCR misread in one
    # place, or none at all -- neither is a useful per-row signal. Same
    # reasoning as this package's other header-plus-body OCCM variants.
    "AIRCRAFT_REG": {"allow_empty": True},
    "AC_MODEL": {"allow_empty": True},
    "AS_OF_DATE": {"allow_empty": True},
    "AIRCRAFT_HOURS": {"allow_empty": True},
    "AIRCRAFT_CYCLES": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Column X-boundaries (fraction of page width), measured directly from the
# real rendered page's own ruled vertical-line pixel columns -- confirmed
# stable across the first, several middle, and the last page of the real
# sample file (see module docstring).
_COL_FRACS: list[tuple[str, float, float]] = [
    ("ATA", 0.052, 0.100),
    ("PART_NUMBER", 0.100, 0.230),
    ("SERIAL_NUMBER", 0.230, 0.354),
    ("DESCRIPTION", 0.354, 0.576),
    ("POSITION", 0.576, 0.661),
    ("INSTALL_DATE", 0.661, 0.756),
    ("TSN", 0.756, 0.849),
    ("CSN", 0.849, 0.944),
]

# Per-column horizontal crop margins. Most columns extend a few px INTO
# their own left ruled border (negative left pad) rather than inset from
# it -- confirmed directly that a plain symmetric inset clips the leading
# glyph of the real column text on some pages (see module docstring). ATA
# is narrow enough that both margins instead need a bigger inset to clear
# its own ruled borders cleanly.
_LEFT_PAD_DEFAULT = -8
_RIGHT_INSET_DEFAULT = 5
_LEFT_PAD_OVERRIDE = {"ATA": 20}
_RIGHT_INSET_OVERRIDE = {"ATA": 20}

# Row-anchor columns: PART_NUMBER/SERIAL_NUMBER/INSTALL_DATE carry a mostly
# distinct value per row (unlike ATA/TSN/CSN, which repeat the same value
# down dozens of consecutive rows and are prone to a psm=4 pass merging
# consecutive identical-looking lines together) -- see module docstring.
_ANCHOR_COLUMNS = ("PART_NUMBER", "SERIAL_NUMBER", "INSTALL_DATE")

# Border/rule-artifact tokens that occasionally get picked up as their own
# OCR word box when a column crop is extended past its ruled border (see
# module docstring) -- dropped before a bucket's words are joined.
_NOISE_TOKEN_RE = re.compile(r"^[|\[\]_\-—–~=<>`\"'*]+$")
_EDGE_STRIP = " _-|[]=~.\"'`*"

# Row-detection: a pixel row counts as part of the shaded column-header
# band once at least this fraction of the FULL page width is dark. This
# band is thick (tens of px) and survives per-page skew that defeats the
# thin single-pixel row rulings below it (see module docstring) -- it is
# the only pixel-grid anchor this module relies on.
_HEADER_DARKFRAC_THRESH = 0.5
_DARK_PIXEL_THRESH = 150
_LINE_MERGE_GAP = 3
_HEADER_BAND_MIN_HEIGHT = 15
_HEADER_BAND_MAX_TOP_FRAC = 0.3

# Chain-merge tolerance for the anchor columns' own per-line Y-centers into
# one master list of row-center candidates, and for merging near-duplicate
# centers found by more than one anchor column for the same real row.
_ANCHOR_CLUSTER_TOL = 12
_ANCHOR_MERGE_TOL = 20
# Nearest-row assignment tolerance for every other column's own words.
_ROW_ASSIGN_TOL = 22

_REG_MODEL_RE = re.compile(r"([A-Z0-9\-]{3,8})\s*\(([A-Z0-9\-]+)\)")
_DATE_HOURS_CYCLES_RE = re.compile(
    r"(\d{1,2}-[A-Za-z]{3}-\d{2,4})[\s|]+([\d,]+)[\s|]+([\d,]+)"
)

_HEADER_FIELDS = ["AIRCRAFT_REG", "AC_MODEL", "AS_OF_DATE", "AIRCRAFT_HOURS", "AIRCRAFT_CYCLES"]


def _clean(text: str) -> str:
    return text.strip(_EDGE_STRIP).strip()


def _find_header_bottom(arr: np.ndarray) -> int | None:
    """Bottom Y of the shaded column-header band -- the one pixel-grid
    anchor this module relies on (see module docstring 'Row boundaries')."""
    h, w = arr.shape
    darkfrac = (arr < _DARK_PIXEL_THRESH).mean(axis=1)
    ys = np.where(darkfrac > _HEADER_DARKFRAC_THRESH)[0]
    if len(ys) == 0:
        return None
    groups: list[tuple[int, int]] = []
    start = prev = int(ys[0])
    for y in ys[1:]:
        y = int(y)
        if y - prev > _LINE_MERGE_GAP:
            groups.append((start, prev))
            start = y
        prev = y
    groups.append((start, prev))
    thick = [g for g in groups
             if g[1] - g[0] > _HEADER_BAND_MIN_HEIGHT and g[0] < h * _HEADER_BAND_MAX_TOP_FRAC]
    if not thick:
        return None
    return thick[-1][1]


def _cluster_tops(tops: list[float], tol: float) -> list[float]:
    if not tops:
        return []
    tops = sorted(tops)
    groups: list[list[float]] = [[tops[0]]]
    for t in tops[1:]:
        if t - groups[-1][-1] <= tol:
            groups[-1].append(t)
        else:
            groups.append([t])
    return [sum(g) / len(g) for g in groups]


def _nearest_row(top: float, centers: list[float]) -> tuple[int | None, float]:
    best_i, best_d = None, float("inf")
    for i, c in enumerate(centers):
        d = abs(top - c)
        if d < best_d:
            best_i, best_d = i, d
    return best_i, best_d


async def _ocr_cell_fallback(img, x0: int, x1: int, top: float, bot: float) -> str:
    """Direct per-cell OCR fallback for a table cell left empty by the
    column-strip pass (see module docstring) -- insets a few px off the
    cell's own estimated boundary, upscales 3x, and pads with white before
    OCR, same technique as
    `occm_component_status_parent_serial_grid.py`'s own fallback."""
    x0i, x1i = x0 + 4, x1 - 4
    y0i, y1i = int(top) + 2, int(bot) - 2
    if x1i - x0i < 5 or y1i - y0i < 5:
        return ""
    crop = img.crop((x0i, y0i, x1i, y1i)).convert("L")
    crop = ImageOps.autocontrast(crop)
    crop = crop.resize((crop.width * 3, crop.height * 3), Image.LANCZOS)
    padded = ImageOps.expand(crop, border=20, fill=255)
    text = await ocr_text(padded, psm=6)
    return _clean(" ".join(text.split()))


def _parse_header_text(title_text: str, box_text: str, meta: dict) -> None:
    if not meta.get("AIRCRAFT_REG"):
        m = _REG_MODEL_RE.search(title_text.upper())
        if m:
            meta["AIRCRAFT_REG"] = m.group(1)
            meta["AC_MODEL"] = m.group(2)
    if not meta.get("AS_OF_DATE"):
        m = _DATE_HOURS_CYCLES_RE.search(box_text)
        if m:
            meta["AS_OF_DATE"] = m.group(1)
            meta["AIRCRAFT_HOURS"] = m.group(2)
            meta["AIRCRAFT_CYCLES"] = m.group(3)


async def _ocr_page_rows(img) -> list[dict]:
    arr = np.array(img.convert("L"))
    h, w = arr.shape
    header_bottom = _find_header_bottom(arr)
    if header_bottom is None:
        return []
    y0 = header_bottom + 2
    y1 = int(h * 0.92)  # stop short of any page-footer/signature artwork

    col_words: dict[str, list[dict]] = {}
    for name, f0, f1 in _COL_FRACS:
        lp = _LEFT_PAD_OVERRIDE.get(name, _LEFT_PAD_DEFAULT)
        ri = _RIGHT_INSET_OVERRIDE.get(name, _RIGHT_INSET_DEFAULT)
        x0, x1 = int(w * f0) + lp, int(w * f1) - ri
        crop = img.crop((x0, y0, x1, y1))
        words = await ocr_words(crop, psm=4, min_conf=-1)
        cw = []
        for wd in words:
            text = str(wd.get("text", "")).strip()
            if not text or _NOISE_TOKEN_RE.match(text):
                continue
            cw.append({"top": y0 + wd["top"], "left": x0 + wd["left"], "text": text})
        col_words[name] = cw

    anchor_tops: list[float] = []
    for colname in _ANCHOR_COLUMNS:
        tops = [wd["top"] for wd in col_words[colname]]
        anchor_tops.extend(_cluster_tops(tops, _ANCHOR_CLUSTER_TOL))
    centers = _cluster_tops(anchor_tops, _ANCHOR_MERGE_TOL)
    if not centers:
        return []

    buckets: list[dict[str, list[tuple[float, str]]]] = [dict() for _ in centers]
    for name, _, _ in _COL_FRACS:
        for wd in col_words[name]:
            idx, dist = _nearest_row(wd["top"], centers)
            if idx is None or dist > _ROW_ASSIGN_TOL:
                continue
            buckets[idx].setdefault(name, []).append((wd["left"], wd["text"]))

    gaps = [centers[i + 1] - centers[i] for i in range(len(centers) - 1)]
    med_gap = sorted(gaps)[len(gaps) // 2] if gaps else 40.0
    half = med_gap / 2 * 1.05

    records = []
    for i, b in enumerate(buckets):
        rec = {}
        for name, f0, f1 in _COL_FRACS:
            toks = sorted(b.get(name, []), key=lambda t: t[0])
            text = _clean(" ".join(t for _, t in toks))
            if not text:
                cx0, cx1 = int(w * f0), int(w * f1)
                text = await _ocr_cell_fallback(img, cx0, cx1, centers[i] - half, centers[i] + half)
            rec[name] = text
        if not (rec["PART_NUMBER"] or rec["SERIAL_NUMBER"]):
            # No real cell content attached to this row-anchor at all --
            # almost certainly page furniture rather than a genuine row.
            continue
        records.append(rec)
    return records


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback (see
    sheet_types/occm.py) -- this variant's known source file has no text
    layer at all, so it can never be found through the normal pdfplumber
    head-text match.

    Requires BOTH the report's own title-line phrase ("Component Status")
    and a `<reg> (<type>)`-shaped first line in the same title-band crop --
    see module docstring for why this combination does not collide with
    either of this package's two other "OCCM Component Status"-titled
    modules. Checked directly (grep across every SIGNATURES list in
    sheet_types/{occm,ht,llp}.py and every existing occm_variants/
    ht_variants/llp_variants module): no other module's own SIGNATURES/
    ocr_detect anchor requires this same combination.
    """
    try:
        img = await render_page(pdf_path, 0, dpi=300)
        w, h = img.size
        crop = img.crop((0, 0, int(w * 0.65), int(h * 0.16)))
        text = await ocr_text(crop, psm=6)
        has_title = "COMPONENT STATUS" in text.upper()
        has_reg_model = bool(_REG_MODEL_RE.search(text.upper()))
        return has_title and has_reg_model
    except Exception:
        return False


async def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    header_meta = {k: "" for k in _HEADER_FIELDS}
    n_pages = await page_count(pdf_path)
    for page_index in range(n_pages):
        img = await render_page(pdf_path, page_index, dpi=300)
        if page_index == 0:
            w, h = img.size
            title_crop = img.crop((0, 0, int(w * 0.65), int(h * 0.16)))
            title_text = await ocr_text(title_crop, psm=6)
            box_crop = img.crop((int(w * 0.60), int(h * 0.03), w, int(h * 0.16)))
            box_text = await ocr_text(box_crop, psm=6)
            _parse_header_text(title_text, box_text, header_meta)
        page_records = await _ocr_page_rows(img)
        for rec in page_records:
            rec.update(header_meta)
            rec["_page"] = page_index + 1
            records.append(rec)
    return records
