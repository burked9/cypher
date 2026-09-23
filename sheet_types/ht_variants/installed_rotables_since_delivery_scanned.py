"""AMOS "Installed Rotables Since Delivery" report, scanned/OCR-only.

Header (a known file in the corpus)::

    <operator wordmark>    Installed Rotables Since Delivery   <date>/<time>  Page N/M
    Aircraft <tail no.> S/N: <msn>
    [x] Only with req.  [ ] Only without req.   Requirements: All
    A/C Data: <hours>/H, <cycles>/C, Delivery: <date>          ATA-Chapters: All

    AIRCRAFT <tail no.>
    ATA | PART NO. | SERIAL NO. | DESCRIPTION | CON | POS. | LABEL NO. |
        INST-DATE | TAH Inst | TAC Inst | TSI | CSI | TSN | CSN

Distinct from the two closest siblings in this package that share an AMOS
provenance ("produced by AMOS" page footer):

  * `aircraft_rotables_ht_scanned.py` -- title "Aircraft Rotables Report"
    (Iberia MIS), single-line-per-record grid with trailing REQUIREMENT/
    INTERVAL/TOGO/EXPECTED columns and MPD task text. No "Only with req."
    checkbox row.
  * `amos_scanned.py` -- title "Aircraft Equipment List Report", header
    columns ATA|<section>|PART NO.|SERIAL NO.|DESCRIPTION|POS.|RELEASE NO./
    LABEL NO.|INST-DATE|TSN|CSN -- no CON column, no TAH/TAC/TSI/CSI
    columns.

This report's own title ("Installed Rotables Since Delivery") and its
14-column main header (with CON, and with the extra TAH Inst/TAC Inst/TSI/
CSI utilisation columns neither sibling has) don't match either -- checked
directly with both siblings' own `ocr_detect()` against a real file in this
cluster, confirmed both return False.

No embedded text layer on any known page (pdfplumber.extract_text() returns
empty) -- OCR-only end to end, same as the two siblings above.

Nested per-record layout, not a flat grid: each rotable's own single-line
main row (ATA/PART NO/SERIAL NO/DESCRIPTION first line/CON/POS/LABEL NO/
INST-DATE/TAH Inst/TAC Inst/TSI/CSI/TSN/CSN) is immediately followed by one
or more REQUIREMENT continuation blocks -- a "REQUIREMENT | DIM | DUE AT |
INTERVAL | TSR | EXPECTED | TO GO" sub-header ruled row, then one ruled
data row per requirement (DISCARD/SERVICE/GENERAL OVERHAUL/PERIODICAL
CHECK/LIFE LIMIT/RE-PACKING/RESTORATION/OVERHAUL/HYDROSTATIC TEST/etc.).
Those sub-rows sit under a DIFFERENT, narrower internal column split (not
aligned to the main header's own column x-positions) and aren't needed for
this project's downstream use (position fingerprint of HT components per
airframe family) -- same call `amos_scanned.py` makes for its own
REQUIREMENT/TASKCARD continuation lines (see that module's docstring) --
so they are skipped entirely rather than parsed.

Extraction approach: one whole-column OCR pass per main-header column (not
per-cell crops -- this package's own established lesson that per-cell crops
repeatedly fail on legible content). PART_NUMBER's own column is sparse --
populated ONLY on a rotable's own main row, never on a REQUIREMENT
continuation row (those start further right, under DESCRIPTION/CON/POS) --
so PART_NUMBER's own OCR'd word Y-positions, clustered, directly give the
Y-center of every genuine main row on the page with no separate ruled-line
grid search needed. Every other column's words are then assigned to
whichever main-row center is vertically nearest, with a tight window
(<=45px half-height, covering only that one printed line) for the
single-line fields (ATA/SERIAL_NUMBER/CON/POSITION/LABEL_NO/INST_DATE/TSN/
CSN) so a REQUIREMENT sub-row's own text several lines below a main row's
single line is never pulled into it -- and a wider window (<=230px) only
for DESCRIPTION, which genuinely wraps across up to several lines within
one main row's own cell before the REQUIREMENT block starts beneath it.

A content-plausibility gate (`_gate()`, same pattern this package's
`hard_time_components_status_content_gated_scanned.py` sibling uses) drops
any row-slot whose PART_NUMBER and SERIAL_NUMBER are both too degenerate to
be genuine identifiers -- guards against a stray OCR word landing near a
main-row center from neighbouring page furniture and fabricating a phantom
row.
"""
from __future__ import annotations
import re

from sheet_types.ht_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_words, page_count

NAME = "Installed Rotables Since Delivery (Scanned)"

# Deliberately empty -- no text layer on any known page (see module
# docstring). Detected structurally via ocr_detect() below, through the
# router's blank-text-layer OCR-fallback path (sheet_types/ht.py's own
# detect_variant()).
SIGNATURES: list[str] = []

CANONICAL_COLUMNS = [
    "ATA",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
    "POSITION",
    "LABEL_NO",
    "INST_DATE",
    "TSN",
    "CSN",
]

_OVERRIDES = {
    "ATA": {"pattern": r"^\d{2}(-\d{1,3})?$", "int_range": None, "allow_empty": True},
    "PART_NUMBER": {"allow_empty": True},
    "SERIAL_NUMBER": {"allow_empty": True},
    "DESCRIPTION": {"allow_empty": True},
    "POSITION": {"allow_empty": True, "uppercase": True},
    "LABEL_NO": {"allow_empty": True},
    "INST_DATE": {"allow_empty": True},
    "TSN": {"allow_empty": True},
    "CSN": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Main-header column x-bounds at 300 DPI. TAH Inst/TAC Inst/TSI/CSI are not
# kept (see module docstring); CON is also dropped -- its own column is too
# narrow (~100px) for reliable whole-column OCR at this DPI, and unlike the
# other dropped columns it's a short 1-3 letter code, so OCR noise from it
# would otherwise pass this project's own CON-shaped validation pattern
# looking clean while actually being wrong -- confirmed directly on a real
# extraction attempt during this module's development (garbage tokens like
# "RT"/"ial"/"oT" reading as plausible 1-3 letter codes). Derived from the
# header row's own OCR'd word left-edges on a known file, cross-checked
# against a numpy vertical-ruled-line scan over the ATA/PART NO./SERIAL
# NO./DESCRIPTION span (that portion's own dividers land at
# ~178/354/678/1002/1391 on every known page -- confirmed directly, stable
# across pages).
_COL_BOUNDS = {
    "ATA": (178, 354),
    "PART_NUMBER": (354, 678),
    "SERIAL_NUMBER": (678, 1002),
    "DESCRIPTION": (1002, 1391),
    "POSITION": (1490, 1750),
    "LABEL_NO": (1750, 2065),
    "INST_DATE": (2065, 2280),
    "TSN": (2990, 3190),
    "CSN": (3190, 3380),
}
# Single-line fields -- tight half-window so a REQUIREMENT sub-row's own
# text (several lines below) is never pulled into a main row.
_TIGHT_HALF = 45
# DESCRIPTION genuinely wraps across several lines within one main row's
# own cell -- wider window, but still well short of reaching a REQUIREMENT
# sub-header several rows below on a densely-packed record.
_DESC_HALF = 230

_BORDER_RE = re.compile(r"[|\[\]<>=~()`*\"'«»''""–—]+")
_SEP_RUN_RE = re.compile(r"_{2,}|\.{3,}|-{3,}")
_EDGE_STRIP = " _-|[]=~.\"'"


def _clean(text: str) -> str:
    s = _SEP_RUN_RE.sub(" ", _BORDER_RE.sub(" ", text))
    return " ".join(s.split()).strip(_EDGE_STRIP)


_TABLE_TOP = 690  # header row itself (ATA/PART NO./.../CSN) starts here on
# every known page -- the aircraft-header block above it (tail no., "Only
# with req." checkbox, A/C Data line) sits at a fixed position on every
# page of this template and must never be OCR'd into a column, or its own
# text (which regularly contains digits, e.g. "A/C Data: 36330:37 / H")
# fabricates phantom PART_NUMBER/SERIAL_NUMBER rows -- confirmed directly
# this happens without the cutoff.


async def _ocr_column(img, x0: int, x1: int) -> list[dict]:
    if x1 <= x0:
        return []
    crop = img.crop((x0, _TABLE_TOP, x1, img.height))
    words = await ocr_words(crop, psm=6, min_conf=-1)
    out = []
    for w in words:
        text = str(w["text"]).strip()
        if not text:
            continue
        out.append({"text": text, "top": _TABLE_TOP + float(w["top"]), "height": float(w["height"])})
    return out


def _row_centers_from_part_number(words: list[dict]) -> list[float]:
    """PART_NUMBER's own column is populated ONLY on a rotable's own main
    row (see module docstring) -- cluster its OCR'd words by Y-gap to get
    one center per genuine main row, with no separate ruled-line search."""
    if not words:
        return []
    ws = sorted(words, key=lambda w: w["top"])
    median_h = sorted(w["height"] for w in ws)[len(ws) // 2] or 20.0
    clusters: list[list[dict]] = [[ws[0]]]
    for w in ws[1:]:
        if w["top"] - clusters[-1][-1]["top"] > median_h * 0.7:
            clusters.append([w])
        else:
            clusters[-1].append(w)
    return [sum(c["top"] + c["height"] / 2 for c in cl) / len(cl) for cl in clusters]


def _assign(words: list[dict], centers: list[float], half: float) -> list[str]:
    buckets: list[list[str]] = [[] for _ in centers]
    for w in words:
        wc = w["top"] + w["height"] * 0.3
        best_i, best_d = None, None
        for i, c in enumerate(centers):
            d = abs(c - wc)
            if d <= half and (best_d is None or d < best_d):
                best_i, best_d = i, d
        if best_i is not None:
            buckets[best_i].append(w["text"])
    return [_clean(" ".join(b)) for b in buckets]


_ID_RE = re.compile(r"[A-Z0-9]")


def _shape_ok(s: str) -> bool:
    s2 = s.strip()
    if len(s2.replace(" ", "")) < 2:
        return False
    alnum = sum(c.isalnum() for c in s2)
    return alnum / max(1, len(s2.replace(" ", ""))) >= 0.6 and any(c.isdigit() for c in s2)


def _gate(rec: dict) -> bool:
    """Keep a row-slot only if PART_NUMBER or SERIAL_NUMBER looks like a
    genuine identifier -- guards against a stray OCR word landing near a
    main-row center and fabricating a phantom record (same idea as
    hard_time_components_status_content_gated_scanned.py's own gate)."""
    return _shape_ok(rec.get("PART_NUMBER", "")) or _shape_ok(rec.get("SERIAL_NUMBER", ""))


async def _extract_page(img, page_num: int) -> list[dict]:
    col_words: dict[str, list[dict]] = {}
    for name, (x0, x1) in _COL_BOUNDS.items():
        col_words[name] = await _ocr_column(img, x0, x1)

    centers = _row_centers_from_part_number(col_words["PART_NUMBER"])
    if not centers:
        return []

    per_col_values: dict[str, list[str]] = {}
    for name, words in col_words.items():
        half = _DESC_HALF if name == "DESCRIPTION" else _TIGHT_HALF
        per_col_values[name] = _assign(words, centers, half)

    records = []
    for i in range(len(centers)):
        rec = {name: per_col_values[name][i] for name in _COL_BOUNDS}
        rec["_page"] = page_num
        if _gate(rec):
            records.append(rec)
    return records


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text-layer fallback
    (see sheet_types/ht.py). Anchors on the report's own title phrase plus
    the "Only with req." checkbox line that sits directly under the
    aircraft header on every known file -- checked directly against this
    package's two closest siblings (aircraft_rotables_ht_scanned.py,
    amos_scanned.py): neither shares this exact title phrase, so this is a
    safe discriminator between all three."""
    try:
        img = await render_page(pdf_path, 0, dpi=300)
        w, h = img.size
        crop = img.crop((0, 0, w, int(h * 0.3)))
        words = await ocr_words(crop, psm=6, min_conf=-1)
        text = re.sub(r"\s+", " ", " ".join(str(x["text"]) for x in words)).upper()
    except Exception:
        return False
    return ("INSTALLED" in text and "ROTABLES" in text and "DELIVERY" in text)


async def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    n_pages = await page_count(pdf_path)
    for page_index in range(n_pages):
        img = await render_page(pdf_path, page_index, dpi=300)
        records.extend(await _extract_page(img, page_index + 1))
    return records
