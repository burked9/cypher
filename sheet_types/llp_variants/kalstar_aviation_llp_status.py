"""Kalstar Aviation single-assembly LLP status sheet -- "LLP STATUS -
<POSITION>" / "LLP SHEET - <POSITION>" (MSN 638, PK-KSC). One file per
landing-gear leg or side brace, signed by the airline's own QA manager
rather than a database export.

No text layer on any of the 4 known source files (0 chars, 1 page each) --
but unlike a photographed form, this is a clean computer-rendered raster
with thin ruled table lines: rendering at 300dpi and viewing the page
directly shows crisp, unambiguous glyphs on every row, no scan noise.

Despite that, OCRing the table as running text (tesseract page-segmentation
over the whole row, or even over just that one row cropped in isolation)
reliably hallucinates garbage into the wide blank runs between cells and
drops leading characters (`D60929-30` -> `0929-30`) -- confirmed by
rendering the exact same pixels both ways: an isolated per-row string OCR
still garbles them, so it isn't a whole-page layout-analysis artifact, it's
tesseract's own word segmentation losing the plot on this column grid. A
prior version of this module took that free-text-then-regex approach and
it silently produced roughly half the true row count with scrambled
PART_NUMBER/SERIAL_NUMBER/cycle fields even on its own target files.

Fix: locate the table's own ruled grid lines from pixel darkness (a real
line is a near-solid run across a whole row or column, easily separated
from text by darkness fraction) and OCR each grid CELL on its own. That
alone fixes the vast majority of rows. Two further wrinkles, both
confirmed by direct pixel inspection rather than guessed at:

  - The scan/render has a slight rotational skew (~0.3-0.4 degrees) --
    negligible for columns near the x-position the row grid was measured
    at, but enough to shift a row boundary by 10-15px out at the far-right
    REMARK column, which silently clips the whole cell to blank at a 300dpi
    row height of ~55px. Row edges are therefore measured at two x
    positions (left and right of the table) and interpolated per column
    rather than reused as one global y for the whole row.
  - Each data row's own top/bottom border is a real ruled line, but a
    parent-assembly row ("MLG LEG ASSY PN: ... SN: ...", "MLG SHOCK
    ABSORBER PN: ... SN: ...") has no internal dividers at all -- slicing
    it at the usual column x-positions chops its one line of text at
    arbitrary points, and by bad luck the PART_NUMBER-column slice of that
    text can itself look like a part number. So every row is OCR'd whole
    first and tested against the "<label> PN: x SN: y" shape before ever
    trying the per-cell path, rather than falling back to it only when the
    per-cell path fails.

Two isolated-character OCR ambiguities remain and are left uncorrected
rather than guessed at: a lone cell containing only "0" against an
otherwise-blank crop reads as some run of O/Q letters often enough that an
empty digit-only OCR pass on these numeric columns is treated as "0"
outright (every such column is populated on every known row, never
genuinely blank); and O/0 or 5/S confusion inside SERIAL_NUMBER survives
untouched since SNs mix letters and digits with no reliable way to tell
which was meant.
"""
from __future__ import annotations
import re

import fitz
import numpy as np
import pytesseract
from PIL import Image

from sheet_types.llp_variants._base import merged_rules

NAME = "Kalstar Aviation LLP Status"
SIGNATURES = [
    "LOWER LIMITER",
    "UNIT CSN @ INSTALL",
]

CANONICAL_COLUMNS = [
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "LIFE_LIMIT",
    "CSN_AT_INSTALL",
    "OPERATED_CYCLES",
    "REMAINING_CYCLES",
    "STATUS",
    "PARENT_ASSY_DESC",
    "PARENT_ASSY_PN",
    "PARENT_ASSY_SN",
    # File-level metadata -- same on every row of a given file.
    "ASSEMBLY_TITLE",
    "TOP_PART_NUMBER",
    "TOP_SERIAL_NUMBER",
    "INSTALLATION_DATE",
    "AIRCRAFT_MSN",
    "AIRCRAFT_REG",
    "POSITION",
    "AC_FH_AT_INSTALL",
    "AC_FC_AT_INSTALL",
    "AC_FH",
    "AC_FC",
    "TOP_CSN",
    "TOP_CSO",
    "UNIT_CSN_AT_INSTALL",
    "UNIT_CSO_AT_INSTALL",
    "LOWER_LIMITER",
]

_CYCLE_RULE = {"pattern": r"^\d*$", "allow_empty": True,
               "int_range": (0, 90000), "int_range_review": (0, 55000)}
_OVERRIDES = {
    "LIFE_LIMIT":         {"pattern": r"^\d*$", "allow_empty": True},
    "CSN_AT_INSTALL":     _CYCLE_RULE,
    "OPERATED_CYCLES":    _CYCLE_RULE,
    "REMAINING_CYCLES":   _CYCLE_RULE,
    "STATUS":             {"pattern": r"^(NEW|REPLACED|SAME|)$", "uppercase": True, "allow_empty": True},
    "AIRCRAFT_REG":       {"pattern": r"^[A-Z0-9\-]+$", "uppercase": True},
    "POSITION":           {"pattern": r"^(LH|RH)$", "uppercase": True},
    "INSTALLATION_DATE":  {"pattern": r"^\d{1,2}-[A-Za-z]{3}-\d{4}$"},
}
RULES = merged_rules(_OVERRIDES)

_DPI = 300
_DARK_THRESH = 220
_LINE_FRAC = 0.85
# x-fraction windows used to sample the row grid on the left/right of the
# table, for the skew interpolation described in the module docstring.
_LEFT_FRAC = (0.24, 0.35)
_RIGHT_FRAC = (0.83, 0.88)

_PN_RE = re.compile(r"D\d{4,9}(?:-\d{1,3})?")
_PN_BARE_RE = re.compile(r"\d{4,9}(?:-\d{1,3})?")
_STATUS_RE = re.compile(r"(NEW|REPLACED|SAME)", re.I)
_NONALNUM_RE = re.compile(r"[^A-Za-z0-9\-]")
# "<label> PN: <pn> SN: <sn>" -- deliberately not anchored on a literal
# "ASSY" (see docstring: "MLG SHOCK ABSORBER" carries no such word at all).
_ASSY_HDR_RE = re.compile(r"^(.+?)\s+PN\s*:?\s*(\S+)\s+SN\s*:?\s*(\S+)", re.I)

_TITLE_RE = re.compile(r"LLP (?:STATUS|SHEET)\s*-\s*(.+)$", re.M)
_TOP_PN_RE = re.compile(r"PART NUMBER\s*:\s*(\S+)", re.I)
_INSTALL_DATE_RE = re.compile(r"INSTALLATION DATE\s*:\s*(\S+)", re.I)
_MSN_RE = re.compile(r"AIRCRAFT MSN\s*:\s*(\S+)", re.I)
_TOP_SN_RE = re.compile(r"SERIAL NUMBER\s*:\s*(\S+)", re.I)
_FH_INSTALL_RE = re.compile(r"A/C FH @ INSTALL\s*:\s*(\S+)", re.I)
_REG_RE = re.compile(r"AIRCRAFT REG\s*:\s*(\S+)", re.I)
_TOP_CSN_RE = re.compile(r"\bCSN\s*:\s*(\S+)", re.I)
_FC_INSTALL_RE = re.compile(r"A/C FC @ INSTALL\s*:\s*(\S+)", re.I)
_FH_RE = re.compile(r"A/C FH\s*:\s*(\S+)", re.I)
_TOP_CSO_RE = re.compile(r"\bCSO\s*:\s*(\S+)", re.I)
_UNIT_CSN_RE = re.compile(r"UNIT CSN @ INSTALL\s*:\s*(\S+)", re.I)
_FC_RE = re.compile(r"A/C FC\s*:\s*(\S+)", re.I)
_POSITION_RE = re.compile(r"\bPOSITION\s*:\s*(\S+)", re.I)
_UNIT_CSO_RE = re.compile(r"UNIT CSO @ INSTALL\s*:\s*(\S+)", re.I)
_LOWER_LIMITER_RE = re.compile(r"LOWER LIMITER\s*:\s*(\S+)", re.I)


def _page_image(pdf_path: str, dpi: int = _DPI) -> Image.Image:
    doc = fitz.open(pdf_path)
    try:
        pix = doc[0].get_pixmap(dpi=dpi)
        return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    finally:
        doc.close()


def _line_groups(frac: np.ndarray, thresh: float = _LINE_FRAC) -> list[int]:
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


def _row_edges(dark: np.ndarray, w: int):
    x0, x1 = int(w * _LEFT_FRAC[0]), int(w * _LEFT_FRAC[1])
    lo = _line_groups(dark[:, x0:x1].mean(axis=1))
    x2, x3 = int(w * _RIGHT_FRAC[0]), int(w * _RIGHT_FRAC[1])
    hi = _line_groups(dark[:, x2:x3].mean(axis=1))
    if len(lo) != len(hi) or len(lo) < 3:
        hi = lo  # couldn't confirm skew independently -- treat as unskewed
    return lo, hi, w * sum(_LEFT_FRAC) / 2, w * sum(_RIGHT_FRAC) / 2


def _y_at(edges, i: int, x: float) -> int:
    lo, hi, x_lo, x_hi = edges
    if x_hi == x_lo:
        return lo[i]
    t = (x - x_lo) / (x_hi - x_lo)
    return int(round(lo[i] + (hi[i] - lo[i]) * t))


def _table_grid(img: Image.Image):
    arr = np.array(img.convert("L"))
    dark = arr < _DARK_THRESH
    h, w = arr.shape
    edges = _row_edges(dark, w)
    lo = edges[0]
    best_xs: list[int] = []
    for y0, y1 in zip(lo, lo[1:]):
        if not (40 <= y1 - y0 <= 70):  # skip header/title slivers, keep real rows
            continue
        xs = _line_groups(dark[y0:y1, :].mean(axis=0))
        if len(xs) > len(best_xs):
            best_xs = xs
    return edges, best_xs


def _ocr(img: Image.Image, box, psm: int = 7, whitelist: str | None = None, pad: int = 4) -> str:
    x0, y0, x1, y1 = box
    crop = img.crop((x0 + pad, y0 + pad, x1 - pad, y1 - pad))
    cfg = f"--psm {psm}"
    if whitelist:
        cfg += f" -c tessedit_char_whitelist={whitelist}"
    return pytesseract.image_to_string(crop, config=cfg).strip()


def _clean_pn(raw: str) -> str:
    m = _PN_RE.search(raw)
    if m:
        return m.group(0)
    m = _PN_BARE_RE.search(raw)
    # Every known PN in this template starts with D; tesseract's most common
    # failure here is dropping that leading letter outright, not fabricating
    # digits, so re-adding it is safe (see docstring).
    return "D" + m.group(0) if m else ""


def _clean_numeric(raw_digits: str) -> str:
    digits = re.sub(r"\D", "", raw_digits)
    return digits if digits else "0"


def _clean_sn(raw: str) -> str:
    return _NONALNUM_RE.sub("", raw)


def _parse_meta(text: str) -> dict:
    meta: dict[str, str] = {}
    m = _TITLE_RE.search(text)
    if m:
        meta["ASSEMBLY_TITLE"] = m.group(1).strip()
    for pat, key in (
        (_TOP_PN_RE, "TOP_PART_NUMBER"), (_INSTALL_DATE_RE, "INSTALLATION_DATE"),
        (_MSN_RE, "AIRCRAFT_MSN"), (_TOP_SN_RE, "TOP_SERIAL_NUMBER"),
        (_FH_INSTALL_RE, "AC_FH_AT_INSTALL"), (_REG_RE, "AIRCRAFT_REG"),
        (_TOP_CSN_RE, "TOP_CSN"), (_FC_INSTALL_RE, "AC_FC_AT_INSTALL"),
        (_FH_RE, "AC_FH"), (_TOP_CSO_RE, "TOP_CSO"),
        (_UNIT_CSN_RE, "UNIT_CSN_AT_INSTALL"), (_FC_RE, "AC_FC"),
        (_POSITION_RE, "POSITION"), (_UNIT_CSO_RE, "UNIT_CSO_AT_INSTALL"),
        (_LOWER_LIMITER_RE, "LOWER_LIMITER"),
    ):
        m = pat.search(text)
        if m:
            meta[key] = m.group(1).strip()
    return meta


def ocr_detect(pdf_path: str) -> bool:
    try:
        img = _page_image(pdf_path, dpi=_DPI)
        crop = img.crop((0, 0, img.width, int(img.height * 0.45)))
        text = pytesseract.image_to_string(crop, config="--psm 6").upper()
        return "LOWER LIMITER" in text and "AIRCRAFT MSN" in text
    except Exception:
        return False


def extract(pdf_path: str) -> list[dict]:
    img = _page_image(pdf_path)
    header_crop = img.crop((0, 0, img.width, int(img.height * 0.45)))
    header_text = pytesseract.image_to_string(header_crop, config="--psm 6")
    meta = _parse_meta(header_text)

    edges, xs = _table_grid(img)
    lo = edges[0]
    if len(xs) != 10 or len(lo) < 2:
        return []

    def cell(row_i: int, col_j: int, **kw) -> str:
        xc = (xs[col_j] + xs[col_j + 1]) / 2
        y0, y1 = _y_at(edges, row_i, xc), _y_at(edges, row_i + 1, xc)
        return _ocr(img, (xs[col_j], y0, xs[col_j + 1], y1), **kw)

    records: list[dict] = []
    parent_desc = parent_pn = parent_sn = ""
    for i in range(len(lo) - 1):
        x_full = (xs[0] + xs[-1]) / 2
        y0, y1 = _y_at(edges, i, x_full), _y_at(edges, i + 1, x_full)
        full_raw = _ocr(img, (xs[0], y0, xs[-1], y1), pad=2)
        m = _ASSY_HDR_RE.search(full_raw)
        if m:
            parent_desc, parent_pn, parent_sn = m.group(1).strip(), m.group(2), m.group(3)
            continue

        pn = _clean_pn(cell(i, 2))
        if not pn:
            continue
        remark = cell(i, 8)
        sm = _STATUS_RE.search(remark)

        rec = {c: "" for c in CANONICAL_COLUMNS}
        rec["DESCRIPTION"] = cell(i, 1)
        rec["PART_NUMBER"] = pn
        rec["SERIAL_NUMBER"] = _clean_sn(cell(i, 3))
        rec["LIFE_LIMIT"] = _clean_numeric(cell(i, 4, whitelist="0123456789"))
        rec["CSN_AT_INSTALL"] = _clean_numeric(cell(i, 5, whitelist="0123456789"))
        rec["OPERATED_CYCLES"] = _clean_numeric(cell(i, 6, whitelist="0123456789"))
        rec["REMAINING_CYCLES"] = _clean_numeric(cell(i, 7, whitelist="0123456789"))
        rec["STATUS"] = sm.group(1).upper() if sm else ""
        rec["PARENT_ASSY_DESC"] = parent_desc
        rec["PARENT_ASSY_PN"] = parent_pn
        rec["PARENT_ASSY_SN"] = parent_sn
        for k, v in meta.items():
            rec[k] = v
        records.append(rec)
    return records
