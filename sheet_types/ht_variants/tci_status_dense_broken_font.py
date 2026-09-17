""""Time Controlled Items (TCI)" hard-time status -- the same ruled
(bordered), born-digital template as `tci_status_broken_font.py` (identical
23-column layout, identical header block shape: title, FH/FC/Date, Aircraft
Registration), but a distinct real corpus file whose `pdfplumber` text layer
corruption is even more severe: NONE of that sibling module's own confirmed
"survives intact" anchor words (`NOMENCLATURE`, `RESTORATION`, `CLEANING`,
`TASK`, `DISCARD`, `ACCUMULATED`, `MAINTENANCE`) decode cleanly on this file
except `RESTORATION` (confirmed directly: a plain-text grep of this file's
own `extract_text()` output across every page). The page-1 title line,
`Time Controlled Items (TCI)`, does decode cleanly here though -- the
opposite of the sibling file, where the title is scrambled but
`NOMENCLATURE` survives -- so that title phrase is this module's own
SIGNATURES anchor instead (see below for the collision check).

Rendering the page to an image shows the same kind of clean, ordinary ruled
table as the sibling file (confirmed directly), so OCR is used end to end
for every cell value here too, following the same per-row (not per-cell,
not whole-page) OCR strategy as `tci_status_broken_font.py`.

Why this is its own module rather than an extension of
`tci_status_broken_font.py`, despite the identical column layout, and why
row detection here works completely differently from every sibling
"broken font" ruled-grid variant in this package: `page.images` (confirmed
directly) holds exactly one full-page raster image per page, covering the
entire page bounding box, the same "scanned sandwich" signature this
package's other scanned HT variants describe (e.g.
`hard_time_day_fhr_cyc_matrix_scanned.py`). The ruled grid visible when the
page renders is baked into that raster image, NOT vector-drawn -- unlike
the sibling `tci_status_broken_font.py`'s own real sample file, whose
identical-looking grid genuinely is a vector-drawn table
(`extract_tables()`/`page.edges` reconstruct it directly and reliably
there). Here `page.edges` only holds a sparse ~80-90 stray line fragments
per page (confirmed directly) that are NOT a reliable proxy for the
visible grid: most horizontal "rule" fragments only span a handful of the
23 columns (e.g. just NO/ATA/MPD_TASK_NO/QPA, stopping dead before
NOMENCLATURE) even where the rendered image shows an obviously complete,
unbroken row divider running the full table width -- confirmed directly by
cropping and visually inspecting the same y-position both ways. Building
row boundaries from these fragments (this module's own first draft, before
this was diagnosed) silently merged multiple real rows into one -- e.g.
NO 2/3/4 (three visibly distinct, fully independent component records with
different PART_NUMBER/SERIAL_NUMBER/dates each) collapsed into a single
crop, because the genuine dividers between them measured well under any
plausible vector-coverage cutoff.

Column boundaries are still taken from `page.edges`' vertical rules (these
ARE reliable here, confirmed directly: ~90 vertical-edge x-positions
cluster cleanly into the same 23-column layout the sibling module uses,
matching the rendered image's own visible column lines) -- only row
detection needed to change. Row boundaries are instead found directly from
the rendered page image itself, per-page, via a plain numpy darkness scan
restricted to the table's own inner x-range (a page-wide grayscale
threshold at pixel value 150, averaged across each pixel row; any row
whose own average exceeds 50% dark pixels across that x-range is a
candidate rule, and consecutive candidate pixel-rows are merged to one
line position): since the grid IS genuinely drawn (just baked into a
raster, not vector objects), this recovers every one of this file's real
row dividers directly, including the ones `page.edges` only partially
captured -- confirmed directly to correctly split NO 2/3/4 back into three
separate rows, and confirmed across all 7 pages to raise the total
detected row count back in line with each page's own visibly distinct NO
values. A small minority of detected boundaries turn out to be a single
visual rule picked up as two adjacent hits a few points apart (edge
anti-aliasing) rather than a genuine extra divider; these produce a
sub-8-point sliver between them, already excluded by this module's
existing "sliver between near-duplicate cluster centers" skip in
`extract()` (see below), so no genuine row is lost or split by them.

Header block, page 1 only, identical shape to the sibling module::

    <lessor wordmark>
    <aircraft type>, MSN <msn>
    Time Controlled Items (TCI)
    FH <hours>   FC <cycles>   Date <dd-Mon-yy>      Aircraft Registration: <reg>

Main table, one repeated header row per page, 23 ruled columns (identical
to the sibling module)::

    NO | ATA | MPD TASK NO. | Mc Part Number | QPA | NOMENCLATURE |
    PART NUMBER | SERIAL NUMBER | POS | INSTALLED/LAST ACCOMPL. DATE |
    LAST ACCOMPLISHED FH | CRS Form Ref. |
    ACCUMULATED HOURS | ACCUMULATED CYCLES | TASK |
    MAINTENANCE INTERVAL (HOURS | CYCLES | DAYS) | NEXT DUE DATE |
    REMAINING (HOURS | CYCLES | DAYS) | REMARKS

Row grain: identical convention to the sibling module -- one record per
ATA-anchored identity block (NO/ATA/NOMENCLATURE/PART_NUMBER/SERIAL_NUMBER
/POS shared across sub-lines); a minority of components track more than
one interval basis at once (e.g. an engine mount's hours/cycles basis plus
a separate calendar-day "Shop Visit" basis), and those extra sub-lines are
folded into each varying column's own cell text, newline-joined (see
`_JOIN_SEP`), per this project's "ambiguous trailing data goes into a
catch-all field, not force-split" convention.

Known limitation, confirmed directly against this real corpus file: with
23 body columns plus header metadata per record, even a modest per-field
OCR error rate compounds into almost every record carrying at least one
flagged field -- confirmed directly against `sheet_types.ht.extract()` +
`normalize_and_validate()` on the real sample file (81 records, all 81
flagged). This is not itself a sign of a structural bug -- row/column
splitting was checked separately (only 1 of 81 records still shows a
`NO` value with more than one row's digits run together, down from
several before the OCR-layout-retry and image-based row-detection fixes
described above) -- and is in the same range as the sibling module's own
already-accepted real sample file (93.8% of its own records flagged, by
the same measure). Expected to surface as elevated `_issues` flagging
across many columns (not concentrated on any one shape of field) rather
than as silently wrong values feeding downstream analysis -- same soft-
validation convention as the rest of this package.

Header metadata (aircraft type+MSN, registration, report FH/FC/date) is
parsed once from page 1's own header crop via OCR and stamped on every row
of the file, per this project's usual header-metadata convention.

A hand-signed "on behalf of <lessor>" signature block appears below the
ruled table on this file's final page (confirmed directly). It sits well
outside the ruled grid this module reconstructs from `page.edges` (no
column/row rules bound it), so it is never captured as a record and no
name from it is extracted, parsed, or otherwise written anywhere by this
module.
"""
from __future__ import annotations
import re

import numpy as np
import pdfplumber
from PIL import Image

from sheet_types.ht_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_words, page_count

NAME = "TCI Status (Dense Broken Font, OCR)"

# "Time Controlled Items (TCI)" is this file's own page-1 title line and is
# confirmed to decode correctly through this file's otherwise badly broken
# text layer (present, byte-for-byte, on page 1 -- see module docstring).
# Checked against every SIGNATURES list in occm.py/ht.py/llp.py and every
# existing occm_variants/ht_variants/llp_variants module's own SIGNATURES
# list (including a plain grep for "controlled items" and "TCI"); no
# collision found. Not a substring of, and does not contain as a substring,
# any of this package's several other "TIME CONTROLLED ITEMS ..."/"Time
# Controlled Items ..." entries (all use a different suffix -- "STATUS",
# "REPORT", "CURRENT STATUS" -- never the bare "(TCI)" parenthetical this
# file's own title uses). Also confirmed NOT present in the sibling
# tci_status_broken_font.py module's own real sample file (that file's
# title line is scrambled, not this phrase) -- so this signature cannot
# misroute that file to this module.
SIGNATURES = [
    "TIME CONTROLLED ITEMS (TCI)",
]

CANONICAL_COLUMNS = [
    "NO",
    "ATA",
    "MPD_TASK_NO",
    "MC_PART_NUMBER",
    "QPA",
    "NOMENCLATURE",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "POS",
    "INST_DATE",
    "LAST_ACCOMPLISHED_FH",
    "CRS_FORM_REF",
    "ACC_HOURS",
    "ACC_CYCLES",
    "TASK",
    "INT_HOURS",
    "INT_CYCLES",
    "INT_DAYS",
    "NEXT_DUE_DATE",
    "REM_HOURS",
    "REM_CYCLES",
    "REM_DAYS",
    "REMARKS",
    # Header metadata -- same value stamped on every row of the file.
    "AIRCRAFT_TYPE_MSN",
    "AIRCRAFT_REG",
    "REPORT_FH",
    "REPORT_FC",
    "REPORT_DATE",
]

_DATE_RE = r"^\d{1,2}-[A-Za-z]{3}-\d{2,4}$"
_NA_NUM_RE = r"^(?:[\d,.]+|NA)$"
_NUM_RE = r"^[\d,.]+$"

_OVERRIDES = {
    "NO": {"pattern": r"^\d+$", "allow_empty": True},
    "MPD_TASK_NO": {"allow_empty": True},
    "MC_PART_NUMBER": {"allow_empty": True},
    "QPA": {"pattern": r"^\d+$", "allow_empty": True},
    "POS": {"allow_empty": True},
    "INST_DATE": {"pattern": _DATE_RE, "allow_empty": True},
    "LAST_ACCOMPLISHED_FH": {"pattern": _NA_NUM_RE, "allow_empty": True},
    "CRS_FORM_REF": {"allow_empty": True},
    "ACC_HOURS": {"pattern": _NA_NUM_RE, "allow_empty": True},
    "ACC_CYCLES": {"pattern": _NA_NUM_RE, "allow_empty": True},
    "TASK": {"allow_empty": True},
    "INT_HOURS": {"pattern": _NA_NUM_RE, "allow_empty": True},
    "INT_CYCLES": {"pattern": _NA_NUM_RE, "allow_empty": True},
    "INT_DAYS": {"pattern": _NA_NUM_RE, "allow_empty": True},
    "NEXT_DUE_DATE": {"pattern": _DATE_RE + r"|^NA$", "allow_empty": True},
    "REM_HOURS": {"pattern": _NA_NUM_RE, "allow_empty": True},
    "REM_CYCLES": {"pattern": _NA_NUM_RE, "allow_empty": True},
    "REM_DAYS": {"pattern": _NA_NUM_RE, "allow_empty": True},
    "REMARKS": {"allow_empty": True},
    # Header metadata -- one value per file, stamped on every row; a tight
    # per-row pattern would either flag every row over one OCR misread in
    # one place or none at all, same reasoning this package's other
    # header-plus-body OCR variants use.
    "AIRCRAFT_TYPE_MSN": {"allow_empty": True},
    "AIRCRAFT_REG": {"allow_empty": True},
    "REPORT_FH": {"allow_empty": True},
    "REPORT_FC": {"allow_empty": True},
    "REPORT_DATE": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

DPI = 300
_SCALE = DPI / 72.0
_JOIN_SEP = " / "
_UPSCALE = 2
# Darkness scan parameters for image-based row detection (see module
# docstring) -- a pixel darker than this (0-255 grayscale) counts as
# "ink"; a pixel-row where more than this fraction of the table's own
# inner width is ink is a candidate ruled-line position. Both confirmed
# directly against this file's own rendered pages to cleanly pick out
# every real row divider (including the ones `page.edges` only partially
# captures) without also firing on ordinary body text (whose own
# per-pixel-row ink fraction, even for a bold header line, stays well
# under this threshold on every page checked).
_DARK_PIXEL_VALUE = 150
_ROW_LINE_FRACTION = 0.35
# A run of consecutive candidate pixel-rows shorter than this (in source
# PDF points, not rendered pixels) is noise, not a rule -- kept generous
# since a genuine ruled line is normally only 1-2 points thick.
_MIN_RULE_RUN_PT = 0.15
# Below this many OCR'd words, a row crop is retried at a different PSM
# (see `extract()`) -- this file's own rows normally return well over a
# dozen words each, so a handful is already a clear sign of a layout-
# analysis failure, not a genuinely sparse row.
_MIN_WORDS_BEFORE_RETRY = 5


def _cluster(values: list[float], tol: float = 2.0) -> list[float]:
    vals = sorted(values)
    groups: list[list[float]] = [[vals[0]]]
    for v in vals[1:]:
        if v - groups[-1][-1] <= tol:
            groups[-1].append(v)
        else:
            groups.append([v])
    return [sum(g) / len(g) for g in groups]


def _get_columns(page) -> list[float]:
    """Column x-boundaries, rebuilt from the page's own vertical ruled
    lines (`page.edges`) -- confirmed directly to be reliable on this file
    even though the matching horizontal rules are not (see module
    docstring): the file's ~90 vertical-edge x-positions cluster cleanly
    into the same 23-column layout the sibling `tci_status_broken_font.py`
    module uses. A pair of isolated, non-grid vertical marks near the
    page's physical left/right edges (confirmed directly, no matching
    evenly-spaced sibling rules the way genuine column dividers have) are
    dropped by keeping only clustered positions within the widest single
    merged horizontal-rule span found anywhere on the page -- that span
    reliably matches the true inner-grid width even though most
    individual horizontal rules on this file are only partial (see
    docstring)."""
    vxs = [e["x0"] for e in page.edges if e["orientation"] == "v"]
    if not vxs:
        return []
    xcols_all = _cluster(vxs, 2.0)

    hedges = [e for e in page.edges if e["orientation"] == "h"]
    groups: dict[int, list[dict]] = {}
    for e in hedges:
        key = round(e["top"] / 1.5)
        groups.setdefault(key, []).append(e)

    inner_x0, inner_x1, max_span_w = None, None, 0.0
    for _key, es in groups.items():
        spans = sorted((e["x0"], e["x1"]) for e in es)
        merged: list[list[float]] = []
        for s0, s1 in spans:
            if merged and s0 <= merged[-1][1] + 1.0:
                merged[-1][1] = max(merged[-1][1], s1)
            else:
                merged.append([s0, s1])
        for s0, s1 in merged:
            if s1 - s0 > max_span_w:
                max_span_w = s1 - s0
                inner_x0, inner_x1 = s0, s1

    if inner_x0 is None:
        return xcols_all
    return [x for x in xcols_all if inner_x0 - 3 <= x <= inner_x1 + 3]


def _rows_from_image(img: Image.Image, x0: float, x1: float, dpi: int) -> list[float]:
    """Row y-boundaries (in PDF points), found directly from the rendered
    page image rather than from `page.edges` -- see module docstring for
    why: this file's ruled grid is baked into a full-page raster image,
    and the incidental vector line fragments `page.edges` also holds are
    not a reliable proxy for it. `x0`/`x1` (in points) restrict the scan
    to the table's own inner column range, from `_get_columns`."""
    scale = dpi / 72.0
    arr = np.asarray(img.convert("L"))
    h = arr.shape[0]
    px0, px1 = int(round(x0 * scale)), int(round(x1 * scale))
    px0 = max(px0, 0)
    px1 = min(px1, arr.shape[1])
    if px1 <= px0:
        return []
    dark = arr[:, px0:px1] < _DARK_PIXEL_VALUE
    row_frac = dark.mean(axis=1)

    min_run_px = max(1, int(_MIN_RULE_RUN_PT * scale))
    ys: list[float] = []
    run_start = None
    for y in range(h):
        if row_frac[y] > _ROW_LINE_FRACTION:
            if run_start is None:
                run_start = y
        elif run_start is not None:
            if y - run_start >= min_run_px:
                ys.append(((run_start + y - 1) / 2.0) / scale)
            run_start = None
    if run_start is not None and h - run_start >= min_run_px:
        ys.append(((run_start + h - 1) / 2.0) / scale)
    return ys


# A stray fragment of the ruled grid (a vertical column rule, or a corner
# where a horizontal and vertical rule cross) is occasionally picked up by
# OCR as its own spurious "word" sitting right at a cell's edge, or fused
# onto the start/end of a real word with no space -- same noise pattern as
# the sibling module's own real sample file. None of these characters is
# ever a legitimate leading/trailing character of a value on this
# template, so a whole word made of nothing else is dropped outright, and
# any surviving line is stripped of a leading/trailing run of them -- per
# this project's "never guess a wrong split" rule, this only ever removes
# border noise, never reshapes the real characters in between.
_NOISE_ONLY_RE = re.compile(r"^[|\[\]{}_~\-–—.,\"'`]+$")
_NOISE_EDGE_CHARS = "|[]{}_~-–—.,\"'` "


def _bucket_words(words: list[dict], xcols: list[float], crop_x0: float,
                   upscale: int = 1) -> list[str]:
    n = len(xcols) - 1
    buckets: list[list[dict]] = [[] for _ in range(n)]
    for w in words:
        text = str(w.get("text", "")).strip()
        if not text or _NOISE_ONLY_RE.match(text):
            continue
        wx = crop_x0 + (w["left"] + w["width"] / 2) / (_SCALE * upscale)
        for i in range(n):
            if xcols[i] <= wx <= xcols[i + 1]:
                buckets[i].append(w)
                break

    out = []
    for b in buckets:
        if not b:
            out.append("")
            continue
        lines: dict[int, list[dict]] = {}
        for w in b:
            key = round(w["top"] / 12)
            lines.setdefault(key, []).append(w)
        line_texts = []
        for k in sorted(lines):
            ws = sorted(lines[k], key=lambda w: w["left"])
            line_text = " ".join(w["text"] for w in ws).strip(_NOISE_EDGE_CHARS)
            if line_text:
                line_texts.append(line_text)
        out.append(_JOIN_SEP.join(line_texts))
    return out


_TYPE_MSN_RE = re.compile(r"([A-Za-z][A-Za-z0-9\- ]{2,20},?\s*MSN\s*\d+)", re.I)
_REG_RE = re.compile(r"Registration:?\s*([A-Z0-9\-]+)", re.I)
_FH_RE = re.compile(r"\bFH\s+([\d,.\-]+)")
_FC_RE = re.compile(r"\bF[CG]\s+([\d,.\-]+)")
_DATE_HDR_RE = re.compile(r"\bDate\s+([\dA-Za-z\-]+)")


async def _parse_header_meta(pdf_path: str) -> dict[str, str]:
    meta = {
        "AIRCRAFT_TYPE_MSN": "",
        "AIRCRAFT_REG": "",
        "REPORT_FH": "",
        "REPORT_FC": "",
        "REPORT_DATE": "",
    }
    try:
        img = await render_page(pdf_path, 0, dpi=DPI)
        w, h = img.size
        crop = img.crop((0, 0, w, int(h * 0.18)))
        words = await ocr_words(crop, psm=6, min_conf=-1)
        text = " ".join(w_["text"] for w_ in words)
    except Exception:
        return meta

    m = _TYPE_MSN_RE.search(text)
    if m:
        meta["AIRCRAFT_TYPE_MSN"] = m.group(1).strip()
    m = _REG_RE.search(text)
    if m:
        meta["AIRCRAFT_REG"] = m.group(1).strip()
    m = _FH_RE.search(text)
    if m:
        meta["REPORT_FH"] = m.group(1).strip()
    m = _FC_RE.search(text)
    if m:
        meta["REPORT_FC"] = m.group(1).strip()
    m = _DATE_HDR_RE.search(text)
    if m:
        meta["REPORT_DATE"] = m.group(1).strip()
    return meta


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback. Not
    expected to fire for the known source file -- its text layer is never
    blank (see module docstring), so it is found via plain-text
    SIGNATURES instead. Kept for interface consistency and in case a more
    severely corrupted copy of this template turns up with an unusably
    short text layer."""
    try:
        img = await render_page(pdf_path, 0, dpi=DPI)
        w, h = img.size
        crop = img.crop((0, 0, w, int(h * 0.3)))
        words = await ocr_words(crop, psm=6, min_conf=-1)
        text = " ".join(w_["text"] for w_ in words).upper()
        return "TIME CONTROLLED ITEMS" in text
    except Exception:
        return False


async def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    header_meta = await _parse_header_meta(pdf_path)

    n_pages = await page_count(pdf_path)
    with pdfplumber.open(pdf_path) as pdf:
        for page_index in range(min(n_pages, len(pdf.pages))):
            page = pdf.pages[page_index]
            xcols = _get_columns(page)
            if len(xcols) < 2:
                continue

            img = await render_page(pdf_path, page_index, dpi=DPI)
            x0, x1 = xcols[0], xcols[-1]
            ys = _rows_from_image(img, x0, x1, DPI)
            if len(ys) < 2:
                continue

            for yi in range(len(ys) - 1):
                y0, y1 = ys[yi], ys[yi + 1]
                if y1 - y0 < 8:
                    # Sliver between near-duplicate cluster centers -- not
                    # a real row.
                    continue
                crop = img.crop((x0 * _SCALE, y0 * _SCALE, x1 * _SCALE, y1 * _SCALE))
                # Same low-resolution small print as the sibling module's
                # own real sample file (confirmed directly by rendering a
                # single cell and visually inspecting it) -- a further 2x
                # upscale measurably improved both row-boundary OCR and
                # digit accuracy here too.
                crop = crop.resize((crop.width * _UPSCALE, crop.height * _UPSCALE))
                words = await ocr_words(crop, psm=6, min_conf=-1)
                if len(words) < _MIN_WORDS_BEFORE_RETRY:
                    # Tesseract's psm=6 (uniform block) layout analysis
                    # occasionally fails outright on this file's own very
                    # wide, short row crops -- confirmed directly: some
                    # rows return only 1-2 words at psm=6 despite the
                    # rendered crop being clearly legible and dense with
                    # text, while the same crop at psm=4 (single column of
                    # variable-size text) reliably returns the full row.
                    # psm=6 is still tried first since it usually returns
                    # slightly more words than psm=4 when it doesn't
                    # outright fail (confirmed directly on this file's own
                    # sample rows) -- this is a fallback for its rare
                    # failure mode, not a wholesale switch.
                    retry_words = await ocr_words(crop, psm=4, min_conf=-1)
                    if len(retry_words) > len(words):
                        words = retry_words
                vals = _bucket_words(words, xcols, x0, upscale=_UPSCALE)
                if not any(v.strip() for v in vals):
                    continue
                # NO must carry at least one digit to count as a genuine
                # data row -- excludes the page title/logo block and the
                # repeated column-header row, neither of which has a
                # numeric NO. Never guessed/reconstructed when absent on a
                # genuine data row -- left blank and caught by this
                # column's own soft-validation pattern instead.
                if not re.search(r"\d", vals[0]):
                    continue
                rec = dict(zip(CANONICAL_COLUMNS[: len(vals)], vals))
                rec["_page"] = page_index + 1
                rec.update(header_meta)
                records.append(rec)

    return records
