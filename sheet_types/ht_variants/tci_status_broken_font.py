""""Time Controlled Items (TCI)" hard-time status -- a real ruled (bordered)
table on a born-digital page, but with a badly corrupted `pdfplumber` text
layer: most cell text decodes to garbage (confirmed directly on a real
corpus file -- e.g. "PART NUMBER" decodes as "PARTI\\IIIIIII!ER", "SERIAL
NUMBER" as "!8SRIAt.NUMBER"), while a handful of header/label words survive
completely intact (e.g. "NOMENCLATURE", "RESTORATION", "CLEANING", "TASK",
"DISCARD", "ACCUMULATED", "MAINTENANCE" -- all found byte-for-byte correct
on at least one of the first 3 pages). This is a different corruption
signature than this package's two other "broken font" variants -- neither
a uniform "(cid:<n>)" total-mapping failure, nor `hard_time_aircraft_
components_status_broken_font.py`'s consistent per-letter substitution --
here whole words are either perfectly fine or badly scrambled, seemingly
depending on which embedded font subset drew them (confirmed directly:
`page.chars` shows different fontnames -- e.g. "Times-Roman" vs
"Helvetica" -- interleaved within the same visual line). Rendering the
page to an image, by contrast, shows a clean, sharp, perfectly ordinary
ruled table (confirmed directly against a real corpus file), so OCR is
used end to end for every cell value; the one surviving clean word
("NOMENCLATURE", this file's own column-header literal) is used only as
this module's plain-text SIGNATURES anchor.

Header block, page 1 only (title/logo block above the ruled table -- not
parsed field-by-field here beyond the anchor check; see header-metadata
handling below for the few fields that are)::

    <lessor wordmark>
    <aircraft type>, MSN <msn>
    Time Controlled Items (TCI)
    FH <hours>   FC <cycles>   Date <dd-Mon-yy>      Aircraft Registration: <reg>

Main table, one repeated header row per page, 23 ruled columns::

    NO | ATA | MPD TASK NO. | Mc Part Number | QPA | NOMENCLATURE |
    PART NUMBER | SERIAL NUMBER | POS | INSTALLED/LAST ACCOMPL. DATE |
    LAST ACCOMPLISHED FH | CRS Form Ref. |
    ACCUMULATED HOURS | ACCUMULATED CYCLES | TASK |
    MAINTENANCE INTERVAL (HOURS | CYCLES | DAYS) | NEXT DUE DATE |
    REMAINING (HOURS | CYCLES | DAYS) | REMARKS

Row grain: normally one row per tracked component/requirement, matching
this file's own "NO" sequence number. A minority of components are
tracked against more than one interval basis at once (e.g. an engine
mount inspected against both an hours/cycles basis and a separate
calendar-day "Shop Visit" basis, or an emergency-oxygen container with a
periodic check plus three separate discard bases) -- on this template
those print as extra ruled sub-lines *within* the same outer row block,
sharing one merged NO/ATA/NOMENCLATURE/PART_NUMBER/SERIAL_NUMBER/POS
(confirmed directly: the ruled grid's own horizontal dividers for those
identity columns span the full sub-block height, while the task-specific
columns get their own internal sub-dividers). Rather than guess which
sub-line's task/date/interval values belong together (risking a wrong
cross-line pairing), this module keeps ATA-anchored row grain -- one
record per identity block -- and folds each varying column's multiple
sub-line values into that column's own cell text, newline-joined (see
`_JOIN_SEP` below); this is the project's documented "ambiguous trailing
data goes into a catch-all field, not force-split" convention applied to
whole columns rather than a single trailing fragment.

Row/column reconstruction approach -- why not `find_tables()`/
`extract_table()` directly: on this file, `find_tables()` fragments a
single visual row into multiple overlapping/duplicate `Table` objects
with incomplete, sometimes complementary, cell coverage (confirmed
directly against a real corpus file: two "row" objects at nearly the same
y-range with disjoint sets of populated columns). Trusting either alone
silently drops columns. Instead this module rebuilds the grid itself from
the page's own raw ruled lines (`page.edges`):

  * Column boundaries: cluster all vertical-edge x0 positions (page-wide,
    2pt tolerance) into ~23 column boundaries.
  * Row boundaries: a horizontal rule only counts as a genuine row
    boundary if its OWN combined x-coverage (unioning same-y segments
    that a column-line crossing split into pieces -- confirmed directly
    this happens on this file) reaches at least 85% of the table's own
    width. A sub-divider that only spans a few interior columns (the
    ragged multi-basis blocks described above) never reaches that
    threshold and is correctly excluded, which is exactly what keeps
    those blocks as one merged row rather than splitting them wrongly.

For each resulting row, the FULL row strip (every column, at once) is
OCR'd in a single pass (`ocr_words()`, not a per-column crop) and each
word is bucketed into its column by x-position -- one OCR call per row
rather than one per cell, since a whole-row pass is far cheaper and this
template's columns are narrow enough that per-cell crops would mostly
just be re-cropping the same handful of words anyway. Within a column,
words are grouped back into their own visual lines (by y-proximity) and
each line's words joined with a space; multiple lines in one cell (either
genuine text wrap, e.g. a long NOMENCLATURE, or the multi-basis merge
described above) are then joined with `_JOIN_SEP` (" / ").

Known limitation, confirmed directly against the real sample file: this
is a fairly low-quality scan/render even before running through OCR --
Tesseract's digit accuracy on the small print is materially worse than
this package's higher-DPI OCR variants (e.g. a handful of NO/ATA/date
values come back visibly wrong, such as a "349"/"352" misread as "349"/
"32"). Kept as-is per this project's soft-validation convention (never
silently corrected/guessed) -- expected to surface as elevated `_issues`
flagging on NO/ATA/date-shaped columns rather than as silently wrong
values feeding downstream analysis.

Header metadata (aircraft type+MSN, registration, report FH/FC/date) is
parsed once from page 1's own header crop via OCR and stamped on every
row of the file, per this project's usual header-metadata convention.
"""
from __future__ import annotations
import re

import pdfplumber

from sheet_types.ht_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_words, page_count

NAME = "TCI Status (Broken Font, OCR)"

# "NOMENCLATURE" is this file's own column-header literal and is confirmed
# to decode correctly through the file's otherwise badly broken text
# layer (present, byte-for-byte, on page 1 itself -- see module
# docstring). Checked against every SIGNATURES list in occm.py/ht.py/
# llp.py and every existing occm_variants/ht_variants/llp_variants
# module's own SIGNATURES list; no collision found today. It is a plain
# English word and therefore not a strongly distinctive anchor on its
# own -- kept as a single entry (not paired with another generic word,
# which would only widen the false-positive surface, not narrow it)
# because it is the one fragment confirmed to survive this file's own
# corruption; a future look-alike template sharing this exact column
# header would need its own investigation regardless.
SIGNATURES = [
    "NOMENCLATURE",
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
_MIN_FULL_WIDTH_FRACTION = 0.85
_UPSCALE = 2


def _cluster(values: list[float], tol: float = 2.0) -> list[float]:
    vals = sorted(values)
    groups: list[list[float]] = [[vals[0]]]
    for v in vals[1:]:
        if v - groups[-1][-1] <= tol:
            groups[-1].append(v)
        else:
            groups.append([v])
    return [sum(g) / len(g) for g in groups]


def _get_grid(page) -> tuple[list[float], list[float]]:
    """Column x-boundaries and row y-boundaries, rebuilt from the page's
    own ruled lines rather than trusting `find_tables()`'s row/table
    grouping directly -- see module docstring."""
    vxs = [e["x0"] for e in page.edges if e["orientation"] == "v"]
    if not vxs:
        return [], []
    xcols = _cluster(vxs, 2.0)
    x0, x1 = xcols[0], xcols[-1]
    width = x1 - x0
    if width <= 0:
        return xcols, []

    hedges = [e for e in page.edges if e["orientation"] == "h"]
    groups: dict[int, list[dict]] = {}
    for e in hedges:
        key = round(e["top"] / 1.5)
        groups.setdefault(key, []).append(e)

    good_ys = []
    for es in groups.values():
        spans = sorted((e["x0"], e["x1"]) for e in es)
        merged: list[list[float]] = []
        for s0, s1 in spans:
            if merged and s0 <= merged[-1][1] + 1.0:
                merged[-1][1] = max(merged[-1][1], s1)
            else:
                merged.append([s0, s1])
        covered = sum(b - a for a, b in merged)
        if covered >= _MIN_FULL_WIDTH_FRACTION * width:
            good_ys.append(sum(e["top"] for e in es) / len(es))

    ys = _cluster(good_ys, 2.0) if good_ys else []
    return xcols, ys


# A stray fragment of the ruled grid (a vertical column rule, or a corner
# where a horizontal and vertical rule cross) is occasionally picked up by
# OCR as its own spurious "word" sitting right at a cell's edge, or fused
# onto the start/end of a real word with no space (confirmed directly
# against a real corpus file: e.g. "| la" for "21", "[at" for "21"). None
# of these characters is ever a legitimate leading/trailing character of a
# value on this template, so a whole word made of nothing else is dropped
# outright, and any surviving line is stripped of a leading/trailing run
# of them -- per this project's "never guess a wrong split" rule, this
# only ever removes border noise, never reshapes the real characters in
# between.
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
        return "TIME CONTROLLED ITEMS" in text or "NOMENCLATURE" in text
    except Exception:
        return False


async def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    header_meta = await _parse_header_meta(pdf_path)

    n_pages = await page_count(pdf_path)
    with pdfplumber.open(pdf_path) as pdf:
        for page_index in range(min(n_pages, len(pdf.pages))):
            page = pdf.pages[page_index]
            xcols, ys = _get_grid(page)
            if len(xcols) < 2 or len(ys) < 2:
                continue

            img = await render_page(pdf_path, page_index, dpi=DPI)
            x0, x1 = xcols[0], xcols[-1]

            for yi in range(len(ys) - 1):
                y0, y1 = ys[yi], ys[yi + 1]
                if y1 - y0 < 8:
                    # Sliver between near-duplicate cluster centers -- not
                    # a real row.
                    continue
                crop = img.crop((x0 * _SCALE, y0 * _SCALE, x1 * _SCALE, y1 * _SCALE))
                # This source scan's own print is small and low-resolution
                # even at 300dpi (confirmed directly by rendering a single
                # cell and visually inspecting it) -- a further 2x upscale
                # measurably improved both row-boundary OCR and digit
                # accuracy on the real corpus file, same tradeoff several
                # sibling OCR variants in this package make (e.g.
                # `hard_time_aircraft_components_status_broken_font.py`'s
                # own per-column `scale` parameter).
                crop = crop.resize((crop.width * _UPSCALE, crop.height * _UPSCALE))
                words = await ocr_words(crop, psm=6, min_conf=-1)
                vals = _bucket_words(words, xcols, x0, upscale=_UPSCALE)
                if not any(v.strip() for v in vals):
                    continue
                # NO must carry at least one digit to count as a genuine
                # data row -- excludes the page title/logo block and the
                # repeated column-header row, neither of which has a
                # numeric NO. Never guessed/reconstructed when absent on
                # a genuine data row (see module docstring's OCR-quality
                # limitation) -- left blank and caught by this column's
                # own soft-validation pattern instead.
                if not re.search(r"\d", vals[0]):
                    continue
                rec = dict(zip(CANONICAL_COLUMNS[: len(vals)], vals))
                rec["_page"] = page_index + 1
                rec.update(header_meta)
                records.append(rec)

    return records
