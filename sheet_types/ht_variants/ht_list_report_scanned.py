""""HT LIST REPORT", scanned/OCR-only counterpart of `ht_list_report.py`.

Same report template/title and the same 18-column body layout (NO /
DESCRIPTION / POSITION / PART NUMBER / SERIAL NUMBER, then four TASK groups
-- INSTALL DATE / SINCE LAST / NEXT DUE / INTERVAL, each an FH+FC+DATE (or
FH+FC+DY) triple -- plus REMARK) as that sibling module, but with NO
embedded text layer at all on any known page (`pdfplumber.extract_text()`
and `extract_words()` both return nothing -- confirmed directly, not the
broken-font-but-real-word-boxes case `ht_list_report.py` handles). OCR-only
end to end via `shared/ocr_bridge.py`.

Column geometry (300 DPI, confirmed directly against real rendered pages --
both by a numpy vertical-ruling-line scan of the header row and by visual
inspection of gridline overlays): a fixed x-position table, stable across
every known page. The INSTALL group's own FH sub-column is itself printed
as TWO adjoining ruled cells -- a whole-number-hours cell and a ":MM"
minutes-suffix cell sharing one merged "FH" header label -- confirmed
directly via a zoomed crop of the header block; this module reads both
cells as a single OCR pass (one combined column bound) rather than
introducing a separate minutes column, since the two together are one
logical HH:MM value (matches the header info box's own "TSN 65856:34"
notation).

Row geometry: row height is a highly consistent ~39.75px pitch (confirmed
across all known pages via both ruled-line detection and OCR word-position
sampling), so rows are generated from a fixed-pitch grid anchored on the
bottom edge of the "NO." column-header cell (located per-page via a cheap
OCR pass) rather than from ruled-line detection -- this file's own ruled
lines are inconsistently dark page to page (confirmed directly: a
windowed-darkness row-divider scan that works cleanly on some pages finds
nothing on others at the same threshold), while the row pitch itself never
drifts.

OCR reliability note (confirmed directly, the reason for two deliberate
departures from this package's usual whole-column-OCR convention):
  1. A single whole-column OCR call spanning a tall, sparse, mostly-numeric
     column (e.g. PART_NUMBER, NO) intermittently drops whole runs of rows
     depending on the exact crop height -- confirmed directly: identical
     pixel content, split into shorter per-chunk crops, recovers rows a
     single full-height call silently lost. Every column is therefore OCR'd
     in fixed-height chunks (~300px, ~7-8 rows) rather than one call for the
     whole page.
  2. Words are assigned to the PRE-COMPUTED pitch-grid row nearest their own
     Y-position, never clustered from any one column's own OCR'd word
     positions -- since which rows a given OCR pass returns is itself
     unreliable (see above), anchoring row identity on any single column's
     recovered words would let a dropped word cascade into misaligning
     every following row. A grid slot with no matching word for a given
     column just stays blank instead.

Content-plausibility gate (same pattern as this package's
`hard_time_components_status_content_gated_scanned.py` /
`installed_rotables_since_delivery_scanned.py`): a generated grid row is
kept only if PART_NUMBER or SERIAL_NUMBER reads as a genuine digit-bearing
identifier shape. This drops the leaked column-header row text ("PART
NUMBER", "SERIAL NUMBER", ...), the header info-box lines, and every
trailing blank grid slot generated past the real bottom of the table (the
per-page footer / the last page's own closing signature block), without
needing a separate positional table-bottom cutoff.

Header info-box metadata (A/C Reg / MSN / TSN / CSN / Report Date) repeats
at a fixed position on every page; it's read once via OCR from page 1 and
stamped onto every row, same convention as the sibling module.
"""
from __future__ import annotations
import re

from sheet_types.ht_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_words, page_count

NAME = "HT List Report (Scanned)"

# Deliberately empty -- no text layer on any known page (see module
# docstring). Detected structurally via ocr_detect() below, through the
# router's blank-text-layer OCR-fallback path (sheet_types/ht.py's own
# detect_variant()).
SIGNATURES: list[str] = []

CANONICAL_COLUMNS = [
    "NO",
    "DESCRIPTION",
    "POSITION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "INSTALL_FH",
    "INSTALL_FC",
    "INSTALL_DATE",
    "SINCE_LAST_FH",
    "SINCE_LAST_FC",
    "SINCE_LAST_DATE",
    "NEXT_DUE_FH",
    "NEXT_DUE_FC",
    "NEXT_DUE_DATE",
    "INTERVAL_FH",
    "INTERVAL_FC",
    "INTERVAL_DY",
    "REMARK",
    # Header metadata -- same on every row of a given file.
    "AC_REG",
    "AC_MSN",
    "TSN",
    "CSN",
    "REPORT_DATE",
]

_FH_RE = r"^[\d,]+(?:\s*:\s*\d{1,2})?$"
_NUM_RE = r"^[\d,]+$"
_DATE_RE = r"^\d{4}-\d{1,2}-\d{1,2}$"

_OVERRIDES = {
    "NO": {"pattern": r"^\d+$", "allow_empty": True},
    "POSITION": {"allow_empty": True},
    "PART_NUMBER": {"allow_empty": True},
    "SERIAL_NUMBER": {"allow_empty": True},
    "INSTALL_FH": {"pattern": _FH_RE, "allow_empty": True},
    "INSTALL_FC": {"pattern": _NUM_RE, "allow_empty": True},
    "INSTALL_DATE": {"pattern": _DATE_RE, "allow_empty": True},
    "SINCE_LAST_FH": {"pattern": _FH_RE, "allow_empty": True},
    "SINCE_LAST_FC": {"pattern": _NUM_RE, "allow_empty": True},
    "SINCE_LAST_DATE": {"pattern": _DATE_RE, "allow_empty": True},
    "NEXT_DUE_FH": {"pattern": _FH_RE, "allow_empty": True},
    "NEXT_DUE_FC": {"pattern": _NUM_RE, "allow_empty": True},
    "NEXT_DUE_DATE": {"pattern": _DATE_RE, "allow_empty": True},
    "INTERVAL_FH": {"pattern": _FH_RE, "allow_empty": True},
    "INTERVAL_FC": {"pattern": _NUM_RE, "allow_empty": True},
    # Free text on calendar-life rows (e.g. "Until EXP. Date") as well as a
    # plain day count -- never forced numeric (mirrors the sibling module).
    "INTERVAL_DY": {"allow_empty": True},
    "REMARK": {"allow_empty": True},
    "AC_REG": {"allow_empty": True, "uppercase": True},
    "AC_MSN": {"allow_empty": True},
    "TSN": {"allow_empty": True},
    "CSN": {"allow_empty": True},
    "REPORT_DATE": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# ---------------------------------------------------------------------------
# Column geometry (pixel x-positions at 300 DPI) -- see module docstring.
# ---------------------------------------------------------------------------
_COL_LINES = [237, 340, 712, 971, 1102, 1243, 1332, 1389, 1479, 1513, 1546,
              1599, 1657, 1689, 1778, 1853, 1885, 2005, 2172]
_DATA_COLUMNS = [
    "NO", "DESCRIPTION", "POSITION", "PART_NUMBER", "SERIAL_NUMBER",
    "INSTALL_FH", "INSTALL_FC", "INSTALL_DATE",
    "SINCE_LAST_FH", "SINCE_LAST_FC", "SINCE_LAST_DATE",
    "NEXT_DUE_FH", "NEXT_DUE_FC", "NEXT_DUE_DATE",
    "INTERVAL_FH", "INTERVAL_FC", "INTERVAL_DY",
    "REMARK",
]
_COL_BOUNDS = {name: (_COL_LINES[i], _COL_LINES[i + 1]) for i, name in enumerate(_DATA_COLUMNS)}

# Wide, multi-word text columns read better at psm 6 (uniform block); every
# other column here is short/sparse/numeric-ish and reads far more
# completely at psm 11 (sparse text, no single-block assumption) --
# confirmed directly, psm 6 on the narrow numeric columns intermittently
# returns almost nothing across a multi-row crop even though the same
# pixels are clearly legible.
_WIDE_COLUMNS = {"DESCRIPTION", "POSITION", "REMARK"}

_PITCH = 39.75
_CHUNK = 300
_MAX_ROWS = 90


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


async def _find_table_top(img) -> float:
    """Locate the bottom edge of the 'NO.' column-header cell -- the true
    start of row 1 -- via a cheap OCR pass restricted to the NO column's own
    x-range. Tracks page 1's extra title line correctly (it pushes this
    boundary down) since it's derived from each page's own rendered
    content rather than a single fixed guess."""
    x0, x1 = _COL_LINES[0], _COL_LINES[1]
    crop = img.crop((x0, 380, x1, 700))
    try:
        words = await ocr_words(crop, psm=11, min_conf=-1)
    except Exception:
        words = []
    for w in words:
        if str(w["text"]).strip().upper().startswith("NO"):
            return 380 + float(w["top"]) + float(w["height"]) + 6
    return 505.0


async def _ocr_column(img, name: str, x0: int, x1: int, top: float, bottom: int) -> list[dict]:
    psm = 6 if name in _WIDE_COLUMNS else 11
    out: list[dict] = []
    y = top
    while y < bottom:
        y1 = min(bottom, y + _CHUNK)
        crop = img.crop((x0, int(y), x1, int(y1)))
        words = await ocr_words(crop, psm=psm, min_conf=-1)
        for w in words:
            t = str(w["text"]).strip()
            if not t:
                continue
            out.append({"text": t, "top": y + float(w["top"]), "height": float(w["height"])})
        y = y1
    return out


def _assign_to_grid(words: list[dict], row_top0: float, n_rows: int, pitch: float) -> list[str]:
    """Bucket words into the pre-computed pitch-grid row whose band they
    fall in -- see module docstring for why this (not clustering words
    into ad-hoc row centers) is used here."""
    buckets: list[list[str]] = [[] for _ in range(n_rows)]
    for w in words:
        wc = w["top"] + w["height"] * 0.3
        idx = int((wc - row_top0) // pitch)
        if 0 <= idx < n_rows:
            buckets[idx].append(w["text"])
    return [_clean(" ".join(b)) for b in buckets]


_ID_SHAPE_RE = re.compile(r"[A-Z0-9]")


def _shape_ok(s: str) -> bool:
    s2 = s.strip()
    if len(s2.replace(" ", "")) < 2:
        return False
    alnum = sum(c.isalnum() for c in s2)
    return alnum / max(1, len(s2.replace(" ", ""))) >= 0.55 and sum(c.isdigit() for c in s2) >= 2


def _gate(rec: dict) -> bool:
    """Keep a generated grid row only if PART_NUMBER or SERIAL_NUMBER reads
    as a genuine digit-bearing identifier -- drops leaked column-header
    text, the header info-box lines, and blank trailing grid slots past the
    real bottom of the table (see module docstring)."""
    return _shape_ok(rec.get("PART_NUMBER", "")) or _shape_ok(rec.get("SERIAL_NUMBER", ""))


_META_RE = {
    "AC_REG": re.compile(r"REG\s*[:;]?\s*([A-Z0-9\-]{4,10})", re.I),
    "AC_MSN": re.compile(r"MSN\s*[:;]?\s*(\d{3,6})", re.I),
    "TSN": re.compile(r"\bTSN\s+([\d:,.]+)", re.I),
    "CSN": re.compile(r"\bCSN\s+([\d:,.]+)", re.I),
    "REPORT_DATE": re.compile(r"REPORT\s*DATE\s+([\d\-A-Z]+)", re.I),
}


async def _parse_meta(img) -> dict:
    meta = {k: "" for k in _META_RE}
    try:
        crop = img.crop((0, 380, 950, 560))
        words = await ocr_words(crop, psm=6, min_conf=-1)
        text = " ".join(str(w["text"]) for w in words)
    except Exception:
        return meta
    for field, rx in _META_RE.items():
        m = rx.search(text)
        if m:
            meta[field] = m.group(1).strip()
    return meta


async def _extract_page(img, page_num: int, meta: dict) -> list[dict]:
    top = await _find_table_top(img)
    bottom = img.height
    n_rows = min(_MAX_ROWS, max(0, int((bottom - top) // _PITCH)))
    if n_rows == 0:
        return []
    col_words: dict[str, list[dict]] = {}
    for name, (x0, x1) in _COL_BOUNDS.items():
        col_words[name] = await _ocr_column(img, name, x0, x1, top, bottom)
    per_col = {name: _assign_to_grid(words, top, n_rows, _PITCH) for name, words in col_words.items()}

    records = []
    for i in range(n_rows):
        rec = {name: per_col[name][i] for name in _DATA_COLUMNS}
        if not _gate(rec):
            continue
        rec.update(meta)
        rec["_page"] = page_num
        records.append(rec)
    return records


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text-layer fallback
    (see sheet_types/ht.py). Anchors on this report's own generic title
    phrase plus its four TASK-group column headers -- checked directly
    against every other ht_variants module's own SIGNATURES/ocr_detect
    anchor text; no collision found. `ht_list_report.py` (this module's
    born-digital sibling) claims the same title phrase as a plain-text
    SIGNATURES entry, but that only ever matches through the router's
    real-text-layer path -- this file has no text layer at all, so the two
    never compete for the same document."""
    try:
        img = await render_page(pdf_path, 0, dpi=300)
        w, h = img.size
        # Title block -- confirmed directly this specific band (below the
        # blank top margin, above the header info-box) is what OCRs cleanly
        # at psm 6; a full-page-top crop starting at y=0 pulls in enough
        # blank margin to make Tesseract mis-segment the title itself.
        title_crop = img.crop((0, 280, w, 650))
        title_words = await ocr_words(title_crop, psm=6, min_conf=-1)
        title_text = re.sub(r"\s+", " ", " ".join(str(x["text"]) for x in title_words)).upper()
        # Column-header group labels ("TASK" / "INSTALL DATE" / "SINCE
        # LAST" / "NEXT DUE" / "INTERVAL") -- confirmed directly these OCR
        # cleanly at psm 4/11 restricted to their own row band, but badly
        # garbled at psm 6 (this file's own established quirk -- see module
        # docstring) or over a wider/taller crop.
        col_crop = img.crop((1000, 480, 2200, 620))
        col_words = await ocr_words(col_crop, psm=11, min_conf=-1)
        col_text = re.sub(r"\s+", " ", " ".join(str(x["text"]) for x in col_words)).upper()
    except Exception:
        return False
    has_title = "HT LIST REPORT" in title_text
    has_cols = ("INSTALL DATE" in col_text) and ("SINCE LAST" in col_text) and ("NEXT DUE" in col_text)
    return has_title and has_cols


async def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    n_pages = await page_count(pdf_path)
    meta: dict = {k: "" for k in _META_RE}
    for page_index in range(n_pages):
        img = await render_page(pdf_path, page_index, dpi=300)
        if page_index == 0:
            meta = await _parse_meta(img)
        records.extend(await _extract_page(img, page_index + 1, meta))
    return records
