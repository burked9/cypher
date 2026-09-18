"""AIRCRAFT SPECIFICATION FILE / "Hard Time Component Status" -- scanned,
full-page-raster PDF, needs a per-column-strip OCR pass end to end (no
usable text layer at all: `page.extract_text()` returns empty on every
page, and `page.rects`/`page.lines`/`page.curves` are all empty while
`page.images` holds exactly one full-page raster image per page -- the
ruled grid visible on render is baked into that raster image, not
vector-drawn, confirmed directly on a real 3-page corpus file).

This shares its title line, "AIRCRAFT SPECIFICATION FILE", with a
completely different, unrelated real corpus file already covered by
`occm_variants/aircraft_spec_file_occm.py` -- that file is an OCCM-flavored
export from the same MIS vendor family with a genuine, directly-extractable
text layer (`ATA_DESCRIPTION`/`POS`/`INST_DATE`/`TSN`/`CSN` columns, parsed
via `pdfplumber.extract_text()`, no OCR at all). No collision in practice:
that sibling module has no `ocr_detect()` of its own, so it never
participates in the router's blank-text-layer OCR-fallback matching this
variant relies on, and this variant's own `SIGNATURES` is deliberately left
empty (never attempted against this file's own blank plain-text layer
either). This variant's `ocr_detect()` additionally requires the
Hard-Time-specific subtitle line, "Hard Time Component Status", alongside
the shared title -- so even a hypothetical future scanned OCCM sibling
using the same title box would not be claimed by this HT-side variant.

Header block (repeats on every page, upper-left corner, plain text, no
box)::

    <tail>-<reg suffix> | <aircraft type> MSN <msn>

...e.g. "<tail-reg> | <type-code> MSN <digits>" on the sample file --
confirmed directly this crop OCRs cleanly and identically on all 3 pages.
Only page 1
additionally carries a boxed title ("AIRCRAFT SPECIFICATION FILE" / "Hard
Time Component Status") and an "Airframe TT"/"Airframe TC" totals row right
below it; pages 2+ go straight from the reg/type/MSN line into the ruled
table, no title box, no TT/TC row (confirmed directly: the yellow
group-header band sits at a different Y offset on page 1 than on every
later page). Since header height is not constant across pages, the data
table's own top Y edge is *not* hardcoded -- it is located per page at
runtime instead (see `_find_data_start_y()` below): find the yellow
group-header band via an RGB scan (its top row's own "Component / Interval
/ Last Done / Next Due / Remarks" band is highlighted bright yellow on
every page), then the next full-width dark horizontal ruled line *after*
the one immediately below that yellow band (that first one is only the top
border of the "ATA / Position / Part-Number / ... / Remarks" column-name
row; skipping straight to it would still OCR the column-name row itself as
if it were a data row, and "Task" reads as a plausible-looking anchor
token). Confirmed directly against a rendered crop on both page 1 (title
box present) and page 2 (no title box) that this lands exactly on the
first real data row's own top edge on each.

Main table, one ruled header row (part of the page's own raster image, not
extractable text), 18 columns::

    ATA | Position | Part-Number | Serial-Number | Description |
    Task Number | Task | Interval{DY,FH,FC} | Last Done{DY,FH,FC} |
    Next Due{DY,FH,FC} | To Go | Remarks

Column X-boundaries below are expressed as fractions of the rendered page's
own width (this project's usual convention for a raster-grid table, see
e.g. `hard_time_day_fhr_cyc_matrix_scanned.py`) -- derived directly from a
numpy column-darkness scan of the ruled grid's own vertical divider lines
on the sample file's page 1.

Row anchoring: TASK is used as the per-row Y anchor -- confirmed directly
on the sample file this column is non-blank on every real data row,
including a component's own second (or third) scheduled-task row under the
same physical unit (e.g. a battery's own "PARTIAL OVERHAUL"-equivalent
"CLEAN" row and its sibling "RESTORATION" row share one ATA/Position/PN/SN/
Description cell, merged across both printed lines, but each still carries
its own Task text). ATA is a weaker anchor candidate elsewhere in this
project's other HT variants (sparse, chapter-code-only-on-first-row), but
confirmed directly here it is *not* sparse -- unlike
`hard_time_day_fhr_cyc_matrix_scanned.py`'s own file, this file's ATA is
present on every physical row exactly where PART_NUMBER/SERIAL_NUMBER/
DESCRIPTION/POSITION are (i.e. blank only on the same continuation rows),
so it is forward-filled alongside those fields rather than captured
best-effort-only.

Row grain: a tracked component instance is usually one physical row, but
ATA/POSITION/PART_NUMBER/SERIAL_NUMBER/DESCRIPTION come back blank on a
second printed line directly below when that line is a second scheduled
task under the very same physical unit (confirmed directly, e.g. an
Emergency Locator Beacon's own "OPERATIONAL CHECK" row and its sibling
"BATTERY REPLACEMENT" row share one merged Component cell but each carries
its own Task Number, Task, Interval, Last Done, Next Due and To Go values).
These are reconstructed with a single forward-fill pass, independently per
field, not reset per page (confirmed directly a component run can span a
page boundary without repeating its own PN/SN/Description on the new
page's first row).

Numeric/date cells (Interval/Last Done/Next Due/To Go) sit behind the same
ruled-cell styling as the rest of the grid; a column's own OCR pass
occasionally picks up stray ruled-border pixels as junk tokens (":", "|",
"_", "=", "—"). Rather than pass these through, each of these columns is
reduced to only its own digit/date-shaped substrings (a plain `\\d[\\d,]+`
scan for the plain-integer columns, `\\d{1,2}[.\\-]\\d{1,2}[.\\-]\\d{2,4}`
for the two calendar-date columns) and non-numeric noise is dropped
outright, per this project's "never guess a wrong split" convention.
NEXT_DUE_DY is a partial exception: this file's own real rows sometimes
round a far-future due date to an abbreviated month-year form instead of a
full calendar date (confirmed directly, e.g. "May-18", "Apr-21", "Nov-26"
on Escape Slide / Cylinder Assy rows alongside plenty of ordinary full
`DD.MM.YYYY` dates elsewhere in the same column) -- so this column accepts
either shape rather than forcing one. TO_GO is also a partial exception:
this file's own real rows hold either a bare day-count integer or an
`HHHHH:MM`-shaped flight-hours-remaining value in the same ruled cell
(confirmed directly, e.g. "20860:21" alongside plain "942" elsewhere in the
same column) -- both shapes are accepted.
"""
from __future__ import annotations
import re

import numpy as np
from PIL import Image

from sheet_types.ht_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_words, ocr_text, page_count

NAME = "Aircraft Specification File HTC Status (Scanned)"

# Deliberately empty: this file's own plain-text layer is blank on every
# page (see module docstring), so a plain-text SIGNATURES phrase would
# never be checked against real page content anyway. Detected instead via
# `ocr_detect()` below, through the router's blank-text-layer OCR-fallback
# path (`sheet_types/ht.py`'s own `detect_variant()`).
SIGNATURES: list[str] = []

CANONICAL_COLUMNS = [
    "ATA",
    "POSITION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
    "TASK_NUMBER",
    "TASK",
    "INTERVAL_DY",
    "INTERVAL_FH",
    "INTERVAL_FC",
    "LAST_DONE_DY",
    "LAST_DONE_FH",
    "LAST_DONE_FC",
    "NEXT_DUE_DY",
    "NEXT_DUE_FH",
    "NEXT_DUE_FC",
    "TO_GO",
    "REMARKS",
    # Header metadata -- same on every page of a given file (TT/TC only
    # ever found on page 1, see module docstring), stamped on every row.
    "AIRCRAFT_REG",
    "AIRCRAFT_TYPE",
    "MSN",
    "AIRFRAME_TT",
    "AIRFRAME_TC",
]

_DATE_RE = r"^\d{1,2}[.\-]\d{1,2}[.\-]\d{2,4}$"
_MON_YR_RE = r"^[A-Za-z]{3}-\d{2}$"
_NUM_RE = r"^-?[\d,]+$"
_TO_GO_RE = r"^-?[\d,]+(?::\d{1,2})?$"

_OVERRIDES = {
    "ATA": {"allow_empty": True},
    "POSITION": {"allow_empty": True, "uppercase": True},
    "PART_NUMBER": {"allow_empty": True},
    "SERIAL_NUMBER": {"allow_empty": True},
    "DESCRIPTION": {"allow_empty": True},
    "TASK_NUMBER": {"allow_empty": True},
    "TASK": {"allow_empty": True, "uppercase": True},
    "INTERVAL_DY": {"pattern": _NUM_RE, "allow_empty": True},
    "INTERVAL_FH": {"pattern": _NUM_RE, "allow_empty": True},
    "INTERVAL_FC": {"pattern": _NUM_RE, "allow_empty": True},
    "LAST_DONE_DY": {"pattern": _DATE_RE, "allow_empty": True},
    "LAST_DONE_FH": {"pattern": _NUM_RE, "allow_empty": True},
    "LAST_DONE_FC": {"pattern": _NUM_RE, "allow_empty": True},
    "NEXT_DUE_DY": {"pattern": rf"(?:{_DATE_RE[1:-1]}|{_MON_YR_RE[1:-1]})",
                     "allow_empty": True},
    "NEXT_DUE_FH": {"pattern": _NUM_RE, "allow_empty": True},
    "NEXT_DUE_FC": {"pattern": _NUM_RE, "allow_empty": True},
    "TO_GO": {"pattern": _TO_GO_RE, "allow_empty": True},
    "REMARKS": {"allow_empty": True},
    # Header metadata -- a single OCR misread here shouldn't flag every
    # row of the file, same reasoning this package's other header-plus-body
    # OCR variants use.
    "AIRCRAFT_REG": {"allow_empty": True},
    "AIRCRAFT_TYPE": {"allow_empty": True},
    "MSN": {"allow_empty": True},
    "AIRFRAME_TT": {"allow_empty": True},
    "AIRFRAME_TC": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Column X-boundaries, as a fraction of the rendered page's own width --
# derived directly from a numpy column-darkness scan of page 1's own ruled
# grid (see module docstring).
_COLUMNS = [
    (0.06057, 0.10610, "ATA"),
    (0.10610, 0.14687, "POSITION"),
    (0.14687, 0.20467, "PART_NUMBER"),
    (0.20467, 0.26089, "SERIAL_NUMBER"),
    (0.26089, 0.38480, "DESCRIPTION"),
    (0.38480, 0.42557, "TASK_NUMBER"),
    (0.42557, 0.50831, "TASK"),
    (0.50831, 0.53880, "INTERVAL_DY"),
    (0.53880, 0.56928, "INTERVAL_FH"),
    (0.56928, 0.60016, "INTERVAL_FC"),
    (0.60016, 0.64014, "LAST_DONE_DY"),
    (0.64014, 0.67736, "LAST_DONE_FH"),
    (0.67736, 0.70784, "LAST_DONE_FC"),
    (0.70784, 0.74584, "NEXT_DUE_DY"),
    (0.74584, 0.77949, "NEXT_DUE_FH"),
    (0.77949, 0.80998, "NEXT_DUE_FC"),
    (0.80998, 0.84086, "TO_GO"),
    (0.84086, 0.90895, "REMARKS"),
]

_JOIN_SPACE = {"DESCRIPTION", "TASK", "POSITION", "REMARKS"}

_NUMERIC_COLS = {
    "INTERVAL_DY", "INTERVAL_FH", "INTERVAL_FC",
    "LAST_DONE_FH", "LAST_DONE_FC",
    "NEXT_DUE_FH", "NEXT_DUE_FC",
}
_DATE_COLS = {"LAST_DONE_DY"}
_DATE_OR_MONYR_COLS = {"NEXT_DUE_DY"}
_TO_GO_COLS = {"TO_GO"}

_NUM_TOKEN_RE = re.compile(r"-?[\d,]{1,}")
_DATE_TOKEN_RE = re.compile(r"\d{1,2}[.\-]\d{1,2}[.\-]\d{2,4}")
_MON_YR_TOKEN_RE = re.compile(r"[A-Za-z]{3}-\d{2}")
_TO_GO_TOKEN_RE = re.compile(r"-?[\d,]{1,}(?::\d{1,2})?")

# Short alnum "codes" (PN/SN/task-number refs), not free text -- stray
# leading/trailing OCR noise chars (a stray "_", an errant ruled-border
# pipe) are stripped from the joined value's own ends rather than passed
# through.
_CODE_COLS = {"PART_NUMBER", "SERIAL_NUMBER", "TASK_NUMBER", "ATA"}
_CODE_STRIP_CHARS = " _\"'`‘’“”.,;:()[]{}|~=—-" + "—"
# ATA/PART_NUMBER/etc genuinely end in a real "-" sometimes (e.g. a PN like
# "731376A" never does, but stripping a trailing real dash from a genuine
# PN would be wrong) -- confirmed directly no real PN/SN/TASK_NUMBER value
# in the sample file starts or ends with "-", so this strip set is safe
# here without a narrower carve-out.

# Row anchor tolerance: measured directly against this file's own row
# pitch at 300 DPI render (~28.5px between consecutive single-line rows);
# comfortably under half that, to avoid bleeding a neighbouring row's own
# value into this one, while still tolerant of a short word-wrap (e.g.
# "FWD CABIN" / "RH" on two lines within one taller merged row).
_ANCHOR_TOLERANCE_PX = 14

_FILLABLE = ("ATA", "POSITION", "PART_NUMBER", "SERIAL_NUMBER", "DESCRIPTION")

_HEADER_FIELDS = ["AIRCRAFT_REG", "AIRCRAFT_TYPE", "MSN", "AIRFRAME_TT", "AIRFRAME_TC"]

# "<reg> | <type> MSN <msn>", e.g. "<tail-reg> | <type-code> MSN <digits>".
_REG_TYPE_MSN_RE = re.compile(
    r"([A-Z0-9\-]{3,10})\s*\|\s*([A-Z0-9\-]{3,12})\s+MSN\s+(\S+)", re.IGNORECASE)

_TITLE_RE = re.compile(r"AIRCRAFT SPECIFICATION FILE", re.IGNORECASE)
_SUBTITLE_RE = re.compile(r"HARD\s*TIME\s*COMPONENT\s*STATUS", re.IGNORECASE)


def _col_bounds(w: int, name: str) -> tuple[int, int]:
    for lo, hi, col in _COLUMNS:
        if col == name:
            return int(lo * w), int(hi * w)
    raise KeyError(name)


def _find_data_start_y(img) -> int:
    """Locate the Y pixel where the ruled data table actually starts on
    this page (see module docstring -- header height is not constant
    across pages, so this can't be a fixed constant)."""
    arr_rgb = np.array(img.convert("RGB"))
    h, w, _ = arr_rgb.shape
    top = arr_rgb[: int(h * 0.4)]
    yellow = (top[:, :, 0] > 200) & (top[:, :, 1] > 200) & (top[:, :, 2] < 120)
    row_yellow = yellow.sum(axis=1)
    ys = np.where(row_yellow > w * 0.3)[0]
    if len(ys) == 0:
        return int(h * 0.08)
    yellow_end = int(ys.max())

    gray = np.array(img.convert("L"))
    row_dark = (gray < 150).sum(axis=1)
    thresh = w * 0.7
    lo = yellow_end
    hi = min(yellow_end + 300, h)
    cand = [y for y in range(lo, hi) if row_dark[y] > thresh]
    if not cand:
        return yellow_end + 40

    groups: list[list[int]] = [[cand[0]]]
    for y in cand[1:]:
        if y - groups[-1][-1] <= 3:
            groups[-1].append(y)
        else:
            groups.append([y])

    # First group is the top border of the "ATA / Position / ..." column-
    # name row (often the same line as the yellow band's own bottom
    # border); the *second* group is that row's own bottom border, i.e.
    # the real data start (confirmed directly against a rendered crop --
    # see module docstring).
    target = groups[1] if len(groups) > 1 else groups[0]
    return target[-1] + 2


async def _ocr_column(img, name: str, y0: int, y1: int, scale: int = 2) -> list[tuple[float, str]]:
    x0, x1 = _col_bounds(img.width, name)
    crop = img.crop((x0, y0, x1, y1))
    if scale != 1:
        crop = crop.resize((crop.width * scale, crop.height * scale), Image.LANCZOS)
    words = await ocr_words(crop, psm=6, min_conf=-1)
    out = []
    for w in words:
        text = str(w.get("text", "")).strip()
        if not text:
            continue
        out.append((y0 + w["top"] / scale, text))
    return out


def _best_numeric(found: list[str]) -> str:
    seen = list(dict.fromkeys(found))
    if not seen:
        return ""
    return max(seen, key=len)


# A ruled-border sliver at a column's own left/right edge occasionally OCRs
# as a lone punctuation "word" ("|", "_", "=", "—") floating at the
# same Y as a real text row -- dropped before joining a free-text cell's
# tokens, since no genuine Task/Description/Position/Remarks word in this
# file is pure punctuation.
_PURE_PUNCT_RE = re.compile(r"^[|_=~—\-:;.,]+$")


def _clean_field(name: str, tokens: list[str]) -> str:
    if name in _NUMERIC_COLS:
        found: list[str] = []
        for t in tokens:
            found.extend(_NUM_TOKEN_RE.findall(t))
        return _best_numeric(found)
    if name in _DATE_COLS:
        found = []
        for t in tokens:
            found.extend(_DATE_TOKEN_RE.findall(t))
        found = list(dict.fromkeys(found))
        return " ".join(found)
    if name in _DATE_OR_MONYR_COLS:
        found = []
        for t in tokens:
            found.extend(_DATE_TOKEN_RE.findall(t))
            found.extend(_MON_YR_TOKEN_RE.findall(t))
        found = list(dict.fromkeys(found))
        if len(found) > 1:
            return _best_numeric(found)
        return " ".join(found)
    if name in _TO_GO_COLS:
        found = []
        for t in tokens:
            found.extend(_TO_GO_TOKEN_RE.findall(t))
        return _best_numeric(found)
    if name in _JOIN_SPACE:
        tokens = [t for t in tokens if not _PURE_PUNCT_RE.match(t)]
    sep = " " if name in _JOIN_SPACE else ""
    text = sep.join(tokens)
    if name in _CODE_COLS:
        text = text.strip(_CODE_STRIP_CHARS)
    return text


async def _parse_header(img, page_index: int) -> dict:
    meta = {k: "" for k in _HEADER_FIELDS}
    w, h = img.size

    async def line(y0: int, y1: int, x0: int, x1: int, psm: int = 6) -> str:
        crop = img.crop((x0, y0, x1, y1))
        crop = crop.resize((crop.width * 2, crop.height * 2), Image.LANCZOS)
        return (await ocr_text(crop, psm=psm)).strip()

    reg_line = await line(int(0.0112 * h), int(0.0504 * h), 0, int(0.3563 * w))
    m = _REG_TYPE_MSN_RE.search(reg_line.replace("\n", " "))
    if m:
        meta["AIRCRAFT_REG"] = m.group(1)
        meta["AIRCRAFT_TYPE"] = m.group(2)
        meta["MSN"] = m.group(3)

    if page_index == 0:
        tt = await line(int(0.1081 * h), int(0.1289 * h),
                         int(0.10610 * w), int(0.14687 * w), psm=7)
        tt = tt.strip(_CODE_STRIP_CHARS)
        if tt:
            meta["AIRFRAME_TT"] = tt
        tc = await line(int(0.1081 * h), int(0.1289 * h),
                         int(0.26089 * w), int(0.38480 * w), psm=7)
        tc = tc.strip(_CODE_STRIP_CHARS)
        if tc:
            meta["AIRFRAME_TC"] = tc

    return meta


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback. Both
    the shared "AIRCRAFT SPECIFICATION FILE" title AND the Hard-Time-
    specific "Hard Time Component Status" subtitle must be found, so this
    doesn't fire for a hypothetical scanned OCCM/LLP sibling sharing the
    same title box (see module docstring)."""
    try:
        img = await render_page(pdf_path, 0, dpi=300)
        w, h = img.size
        crop = img.crop((0, int(0.0611 * h), w, int(0.1076 * h)))
        text = (await ocr_text(crop, psm=6)).upper()
        return bool(_TITLE_RE.search(text) and _SUBTITLE_RE.search(text))
    except Exception:
        return False


async def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    header_meta = {k: "" for k in _HEADER_FIELDS}
    n_pages = await page_count(pdf_path)

    for page_index in range(n_pages):
        img = await render_page(pdf_path, page_index, dpi=300)
        h = img.height

        if not all(header_meta.values()):
            page_meta = await _parse_header(img, page_index)
            for k, v in page_meta.items():
                if v and not header_meta[k]:
                    header_meta[k] = v

        y0 = _find_data_start_y(img)

        col_words: dict[str, list[tuple[float, str]]] = {}
        for _, _, name in _COLUMNS:
            col_words[name] = await _ocr_column(img, name, y0, h)

        anchors = sorted(top for top, text in col_words["TASK"] if text)
        # Cluster anchors within tolerance so multi-word Task cells
        # ("BATTERY REPLACEMENT") collapse to one row anchor rather than two.
        clustered: list[float] = []
        for top in anchors:
            if clustered and abs(top - clustered[-1]) <= _ANCHOR_TOLERANCE_PX:
                continue
            clustered.append(top)

        cur = {f: "" for f in _FILLABLE}
        for atop in clustered:
            row: dict[str, str] = {}
            for _, _, name in _COLUMNS:
                toks = [text for top, text in col_words[name]
                        if abs(top - atop) <= _ANCHOR_TOLERANCE_PX]
                row[name] = _clean_field(name, toks)

            # ATA is the reliable "new component starts here" signal in
            # this file (present on a component's own first printed row,
            # blank on a continuation row for its own second/third
            # scheduled task -- confirmed directly, see module docstring).
            # Forward-fill only applies on a genuine continuation row;
            # otherwise this row's own (possibly OCR-blank) values stand
            # on their own rather than silently inheriting the *previous,
            # different* component's PN/SN/Description merely because this
            # row's own OCR pass happened to miss one of those cells.
            if row["ATA"]:
                cur = {f: row[f] for f in _FILLABLE}
            else:
                for f in _FILLABLE:
                    if row[f]:
                        cur[f] = row[f]
                    else:
                        row[f] = cur[f]

            row["_page"] = page_index + 1
            row.update(header_meta)
            records.append(row)

    return records
