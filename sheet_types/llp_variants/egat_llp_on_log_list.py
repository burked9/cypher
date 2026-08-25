"""EGAT (Evergreen Aviation Technologies, Taiwan) "LLP ON LOG LIST" -- IAE
V2500 engine LLP report, EGAT FORM 7054-01. Confirmed on 2 real files (MSN
1356, ESN V10834 and V10128) -- single page, no text layer (0 chars via
pdfplumber on the V10834 file; a scanned raster in both cases despite one
of the two carrying an unrelated garbled OCR text layer, see below).

IMPORTANT: only V10834 is actually this format. V10128's file of the same
name pattern ("..._Engine LLP Status @ last SV.pdf", same MSN/engine
family, same folder) is a completely different document -- an IHI
Corporation "ENGINE/MODULE LIFE LIMITED PART TIME/CYCLE RECORD" (FORM
MU-006-2), a different table shape (INCOMING/OUTGOING STATUS side by side)
from a different producer. Confirmed by rendering and reading both pages
directly, not by signature text alone. This module's SIGNATURES/ocr_detect
correctly never match it -- it is out of scope for this variant and needs
its own module if it's ever wanted.

Layout of the real EGAT page (confirmed by direct pixel/OCR inspection at
300dpi): a title block ("LLP ON LOG LIST" / "EGAT" logo / ENGINE P/N,
Tracking No., ENGINE S/N, ISSUE DATE line), then one ruled table with
columns MODULE S/N (IAE IIN) | NOMENCLATURE | PART No. | SERIAL No. | TSN |
CSN | REMAIN | LIMIT | REMARK. Two row shapes share that same grid:

  - Module-group header rows (MODULE S/N in {FANMDL, INTMDL, HPCMDL,
    HPTURB, LPTMDL}) -- NOMENCLATURE holds the module's full name spanning
    the row, and a bare "<n>X" life-limit index code (e.g. "45X") lands in
    the REMAIN column position with every other cell blank. These aren't
    LLP part records themselves (no PART No./SERIAL No.), so -- same call
    kalstar_aviation_llp_status.py makes for its own parent-assembly rows
    -- they're captured as running MODULE_GROUP/MODULE_GROUP_CODE context
    propagated onto the real part rows beneath them, not emitted as rows
    of their own.
  - Real LLP-tracked part rows underneath each group header, one per
    life-limited assembly (e.g. "FANDSK | FAN DISK STG.1 | 5A1757 |
    RSTDK38504 | 8063:45 | 5203 | 14797 | 20000 | AS IS").

Grid detection mirrors kalstar_aviation_llp_status.py's darkness-based
approach, simplified because this form has no measurable skew and both
known files render at a consistent DPI: row lines come from the
near-full-width dark-pixel bands: the header row (with "MODULE S/N" etc.)
happens to have the same full 9-column vertical-line set as the real data
rows, so it doubles as the column-position anchor -- picking the row band
with the most detected vertical dividers, same idea as
kalstar_aviation_llp_status.py's `_table_grid`, rather than hard-coding
column x-fractions that would drift on a differently-scaled render.

OCR per cell (psm 7, ~300dpi) is clean on this crisp computer-rendered
form -- text glyphs are large and the grid lines are thin and solid --
except that a cell's own ruled left border regularly gets read as a
leading "|" (or occasionally "_"/"~") glued onto the real text
("| RRD7206" for "RRD7206"); stripped uniformly per cell before any
column-specific parsing, the same border-glyph problem
sriwijaya_b737_occm.py's `_BORDER_RE` handles for its own noisy grid.

A handful of purely-numeric cells (TSN/CSN/REMAIN/LIFE_LIMIT) come back
empty under psm 7 despite an unambiguous crop -- confirmed by saving the
exact failing crop and re-running it standalone, not a cropping-boundary
bug. psm 8 recovers them every time but mangles multi-word text cells by
dropping inter-word spaces, so `_ocr_numeric_cell` tries psm 7 first and
falls back to psm 8 only on that empty result, only for numeric columns.

Verified against both real files (25/25 LLP part rows recovered on
V10834, matching a direct visual read of the source page). Two residual,
left uncorrected rather than guessed at: (1) a left-margin handwritten
annotation mark (a small circle) bleeds a stray leading glyph into
MODULE_SN on 2 of 25 rows ("-- BCRROS", "a LT4DSK") -- caught by this
module's own MODULE_SN pattern rule so `_issues` flags it, rather than
silently keeping a corrupted code; and (2) a couple of PART_NUMBER/
MODULE_SN cells pick up a single extra or substituted character
("5R0159" read as "5RO0159", "9T12RD" read as "$T12RD") that still
satisfies the generic alnum PART_NUMBER/MODULE_SN patterns and so isn't
flagged -- the same class of uncorrected ambiguity
kalstar_aviation_llp_status.py documents for its own SERIAL_NUMBER O/0
and 5/S confusion, for the same reason: no per-airframe PN/code master
list exists here to check against.
"""
from __future__ import annotations
import re

import numpy as np

from sheet_types.llp_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, page_count

NAME = "EGAT LLP ON LOG LIST"

# Distinctive to this EGAT engine form -- checked against every existing
# SIGNATURES list in sheet_types/{occm,ht,llp}.py and every
# {occm,ht,llp}_variants/*.py file, no collision found.
SIGNATURES = [
    "LLP ON LOG LIST",
    "EGAT FORM 7054",
]

CANONICAL_COLUMNS = [
    "MODULE_SN",
    "NOMENCLATURE",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "TSN",
    "CSN",
    "REMAIN",
    "LIFE_LIMIT",
    "REMARK",
    "MODULE_GROUP_CODE",
    "MODULE_GROUP",
    "MODULE_LIFE_INDEX",
    # File-level metadata -- same on every row of a given file.
    "ENGINE_PART_NUMBER",
    "TRACKING_NO",
    "ENGINE_SERIAL_NUMBER",
    "ISSUE_DATE",
]

_CYCLE_RULE = {"pattern": r"^\d*$", "allow_empty": True,
               "int_range": (0, 90000), "int_range_review": (0, 55000)}
_OVERRIDES = {
    "TSN":               {"pattern": r"^\d{1,6}(:\d{1,2})?$", "allow_empty": True},
    "CSN":               _CYCLE_RULE,
    "REMAIN":            _CYCLE_RULE,
    "LIFE_LIMIT":        {"pattern": r"^\d*$", "allow_empty": True},
    "MODULE_LIFE_INDEX":  {"pattern": r"^\d{1,3}X$", "allow_empty": True},
    "ENGINE_SERIAL_NUMBER": {"pattern": r"^[A-Z0-9]+$", "uppercase": True},
    "ISSUE_DATE":        {"pattern": r"^[A-Z]{3}/\d{1,2}/\d{4}$"},
    # Every real MODULE_SN code on the known file is a short bare
    # alphanumeric token (FANDSK, 3T8RDS, HPT2AS, ...). This exists mainly
    # to flag -- never drop, per the soft-validation principle -- the
    # stray extra glyph a left-margin handwritten annotation mark
    # sometimes bleeds into this column's crop (confirmed on 2 of 25 real
    # rows: "-- BCRROS", "a LT4DSK"), rather than silently keeping it.
    "MODULE_SN":         {"pattern": r"^[A-Z0-9]{4,8}$", "uppercase": True},
}
RULES = merged_rules(_OVERRIDES)

_DPI = 300
_DARK_THRESH = 220
_ROW_LINE_FRAC = 0.5
_COL_LINE_FRAC = 0.7
_MIN_ROW_HEIGHT = 50

_MODULE_GROUP_CODES = {"FANMDL", "INTMDL", "HPCMDL", "HPTURB", "LPTMDL"}

_ENGINE_PN_RE = re.compile(r"ENGINE\s*P/?N\s*:\s*(\S+)", re.I)
_TRACKING_RE = re.compile(r"Tracking\s*No\.?\s*(\S+)", re.I)
_ENGINE_SN_RE = re.compile(r"ENGINE\s*S/?N\s*:\s*(\S+)", re.I)
_ISSUE_DATE_RE = re.compile(r"ISSUE\s*DATE\s*:\s*(\S+)", re.I)

# Leading/trailing ruled-border misreads glued onto real cell text -- see
# module docstring. Never appears mid-token in this form's cells, unlike a
# real hyphen inside a part/serial number, so trimming only the ends is
# safe.
_BORDER_RE = re.compile(r"^[|_~`'\"\s]+|[|_~`'\"\s]+$")
_HAS_DIGIT_RE = re.compile(r"\d")
_MODULE_INDEX_RE = re.compile(r"(\d{1,3})\s*[Xx]")
_TSN_RE = re.compile(r"(\d{1,6}(?::\d{1,2})?)")
_INT_RE = re.compile(r"(\d+)")


def _clean_cell(raw: str) -> str:
    return _BORDER_RE.sub("", raw).strip()


def _clean_int(raw: str) -> str:
    m = _INT_RE.search(raw)
    return m.group(1) if m else ""


def _line_groups(frac, thresh: float) -> list[int]:
    idx = np.where(frac > thresh)[0]
    if not len(idx):
        return []
    groups, cur = [], [idx[0]]
    for v in idx[1:]:
        if v - cur[-1] <= 3:
            cur.append(v)
        else:
            groups.append(cur)
            cur = [v]
    groups.append(cur)
    return [int(np.mean(g)) for g in groups]


def _table_grid(img):
    """Row lines from near-full-width dark bands; column lines from
    whichever row band shows the most vertical dividers -- on this form
    that's reliably a fully-gridded row (the header row or any real data
    row), never a module-group header row (which has no internal
    dividers in its merged NOMENCLATURE cell). Mirrors
    kalstar_aviation_llp_status.py's `_table_grid`, without that module's
    skew-interpolation step -- no measurable skew on either known file
    here.
    """
    arr = np.array(img.convert("L"))
    dark = arr < _DARK_THRESH
    row_lines = _line_groups(dark.mean(axis=1), _ROW_LINE_FRAC)
    best_xs: list[int] = []
    for y0, y1 in zip(row_lines, row_lines[1:]):
        if y1 - y0 < _MIN_ROW_HEIGHT:
            continue
        xs = _line_groups(dark[y0:y1, :].mean(axis=0), _COL_LINE_FRAC)
        if len(xs) > len(best_xs):
            best_xs = xs
    return row_lines, best_xs


async def _ocr_cell(img, box, psm: int = 7, whitelist: str | None = None, pad: int = 3) -> str:
    x0, y0, x1, y1 = box
    crop = img.crop((x0 + pad, y0 + pad, x1 - pad, y1 - pad))
    text = await ocr_text(crop, psm=psm, whitelist=whitelist)
    return text.strip()


async def _ocr_numeric_cell(img, box, whitelist: str, pad: int = 3) -> str:
    """psm 7 (single text line) is what every other cell on this form
    uses, but on a handful of purely-numeric cells with no letters at all
    it comes back empty despite a clean, unambiguous crop -- confirmed by
    saving the exact crop that failed and re-running it standalone. psm 8
    (single word) recovers those every time, but mangles multi-word text
    cells by dropping the spaces between words, so it's only tried here,
    as a fallback, on cells already known to be numeric-only.
    """
    text = await _ocr_cell(img, box, psm=7, whitelist=whitelist, pad=pad)
    if text:
        return text
    return await _ocr_cell(img, box, psm=8, whitelist=whitelist, pad=pad)


def _parse_header(text: str) -> dict:
    meta: dict[str, str] = {}
    for pat, key in (
        (_ENGINE_PN_RE, "ENGINE_PART_NUMBER"),
        (_TRACKING_RE, "TRACKING_NO"),
        (_ENGINE_SN_RE, "ENGINE_SERIAL_NUMBER"),
        (_ISSUE_DATE_RE, "ISSUE_DATE"),
    ):
        m = pat.search(text)
        if m:
            meta[key] = m.group(1).strip().rstrip(".,")
    return meta


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback -- "LLP
    ON LOG LIST" OCRs cleanly in the title block on the one known real
    file even though the data grid below doesn't (see module docstring).

    The EGAT globe logo next to the title does NOT OCR reliably, and does
    so differently per OCR engine -- pytesseract (local) reads it as
    "EG AT" (confirmed), Tesseract.js (in-browser) reads the exact same
    logo as "CYELGAT" (confirmed via a real user's browser). Neither is a
    stable anchor, so this doesn't require the logo text at all -- the
    full "LLP ON LOG LIST" phrase alone already OCRs cleanly on both
    engines and was already checked for collisions across every other
    variant's SIGNATURES in this package (see SIGNATURES above), so it's
    a safe, sufficient anchor by itself.
    """
    try:
        img = await render_page(pdf_path, 0, dpi=_DPI)
        crop = img.crop((0, 0, img.width, int(img.height * 0.15)))
        text = (await ocr_text(crop, psm=6)).upper()
        return "LLP ON LOG LIST" in text
    except Exception:
        return False


async def _extract_page(img, page_num: int, meta: dict) -> list[dict]:
    row_lines, xs = _table_grid(img)
    if len(xs) < 6 or len(row_lines) < 2:
        return []

    async def cell(i: int, j: int, **kw) -> str:
        return await _ocr_cell(img, (xs[j], row_lines[i], xs[j + 1], row_lines[i + 1]), **kw)

    async def numeric_cell(i: int, j: int, whitelist: str) -> str:
        return await _ocr_numeric_cell(img, (xs[j], row_lines[i], xs[j + 1], row_lines[i + 1]), whitelist)

    n_cols = len(xs) - 1
    records: list[dict] = []
    group_code = group_desc = group_index = ""
    for i in range(len(row_lines) - 1):
        if row_lines[i + 1] - row_lines[i] < _MIN_ROW_HEIGHT:
            continue
        module_sn = _clean_cell(await cell(i, 0))
        if not module_sn:
            continue
        part_no = _clean_cell(await cell(i, 2)) if n_cols > 2 else ""

        if module_sn.upper() in _MODULE_GROUP_CODES or not _HAS_DIGIT_RE.search(part_no):
            # Module-group header row -- no PART_NUMBER/SERIAL_NUMBER of its
            # own (see module docstring). Capture context, emit no record.
            group_code = module_sn.upper()
            group_desc = _clean_cell(await cell(i, 1)) if n_cols > 1 else ""
            m = _MODULE_INDEX_RE.search(await cell(i, 6)) if n_cols > 6 else None
            group_index = f"{m.group(1)}X" if m else ""
            continue

        rec = {c: "" for c in CANONICAL_COLUMNS}
        rec["MODULE_SN"] = module_sn
        rec["NOMENCLATURE"] = _clean_cell(await cell(i, 1)) if n_cols > 1 else ""
        rec["PART_NUMBER"] = part_no
        rec["SERIAL_NUMBER"] = _clean_cell(await cell(i, 3)) if n_cols > 3 else ""
        if n_cols > 4:
            tsn_raw = await numeric_cell(i, 4, "0123456789:")
            m = _TSN_RE.search(tsn_raw)
            rec["TSN"] = m.group(1) if m else ""
        if n_cols > 5:
            rec["CSN"] = _clean_int(await numeric_cell(i, 5, "0123456789"))
        if n_cols > 6:
            rec["REMAIN"] = _clean_int(await numeric_cell(i, 6, "0123456789"))
        if n_cols > 7:
            rec["LIFE_LIMIT"] = _clean_int(await numeric_cell(i, 7, "0123456789"))
        if n_cols > 8:
            rec["REMARK"] = _clean_cell(await cell(i, 8))
        rec["MODULE_GROUP_CODE"] = group_code
        rec["MODULE_GROUP"] = group_desc
        rec["MODULE_LIFE_INDEX"] = group_index
        for k, v in meta.items():
            rec[k] = v
        rec["_page"] = page_num
        records.append(rec)
    return records


async def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    n_pages = await page_count(pdf_path)
    for page_index in range(n_pages):
        img = await render_page(pdf_path, page_index, dpi=_DPI)
        header_crop = img.crop((0, 0, img.width, int(img.height * 0.12)))
        header_text = await ocr_text(header_crop, psm=6)
        meta = _parse_header(header_text)
        records.extend(await _extract_page(img, page_index + 1, meta))
    return records
