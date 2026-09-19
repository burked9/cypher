""""Service Life Limited Components Status" report -- full-page-raster
PDF, no usable text layer at all (confirmed directly: `page.get_text()`
returns empty on every page of the sample file via PyMuPDF, matching a
0-character pdfplumber decode too). Rendering to an image shows a clean,
sharp, ordinary machine-printed report (not handwritten, not a noisy
photocopy) with a fully ruled ("boxed") grid baked into the raster --
every cell boundary, including the outer table border, is a real drawn
line -- so a per-column-strip OCR pass anchored on the grid's own
horizontal/vertical divider lines is reliable here, same technique this
package's other plain-ruled-grid scanned variants use (e.g.
`ht_ruled_grid_time_limit_columns_scanned.py` in this same package, and
`occm_variants/occm_components_status_ruled_grid.py`'s own near-identical
page-1 header info-box layout -- same underlying MIS export family,
different report subtype).

Header block (page 1 only)::

    <operator logo>   A/F FH: <fh>     A/C Reg: <reg>     <title box>
                       A/F FC: <fc>    MSN: <msn>
                       Report Date: <date>   A/C Type: <type>

The title box's own text is "<MSN> Service Life Limited Components
Status" -- the leading MSN token is document-specific and not used for
detection (see `ocr_detect()` below, which anchors on the fixed
"Service Life Limited"/"Components Status" phrases either side of it
instead). None of the header info box's own real values (registration,
MSN, hours, cycles, date) are written into this module's source --
only the generic label text the template itself prints.

Every page (including page 1, below its own info box) repeats the same
22-column ruled column-header row, then one physical ruled row per
record -- unlike some sibling scanned HT variants in this package, there
is no multi-sub-row merged identity cell here: every row repeats its own
MPD_TC_NO_REF/DESCRIPTION/CERT_REF/PART_NUMBER/SERIAL_NUMBER/POSITION
values in full, even when a single component is tracked against several
different treatment/limit bases (confirmed directly -- e.g. a component
overhauled on both an hours basis and a separate cycles basis prints as
two full rows, not one merged block)::

    MPD TC No. Ref | DESCRIPTION | FAA Form 8130-3/EASA Form 1 | P/N | S/N |
    POS | TREATMENT | [Hours | Cycles | Days] (INTERVAL/LIFE LIMITS) | DOM |
    Last Treatment Date | INST DATE | [DSR | HSR | CSR] (Current Data) |
    [TSN | CSN] (Original) |
    [Remaining Days | Remaining Hours | Remaining Cycles] (Remaining) |
    REMARKS

DSR/HSR/CSR are this report's own "days/hours/cycles since repair"
current-data trio (paired with the INTERVAL/LIFE LIMITS trio on the
left and the Remaining trio on the right); TSN/CSN are the aircraft's
original total-time/total-cycles-since-new figures, repeated per row.
"MPD TC No. Ref" is shortened to REF_NO here (matches this package's
naming for the equivalent field in sibling ruled-grid HT variants); "FAA
Form 8130-3/EASA Form 1" is shortened to CERT_REF.

Row/column geometry: the outer table border and every internal grid line
(both the column-header row's own sub-dividers and every data row's own
boundary) render as solid, fully dark pixel runs at 300 DPI on every page
checked in the sample -- confirmed directly via a numpy row/column
darkness scan. Column X-boundaries are therefore found fresh per page
from a vertical-divider pixel scan (`_find_col_lines`), same as
`occm_components_status_ruled_grid.py`'s own approach, rather than fixed
fractions -- this keeps the crop aligned even against a differently
cropped scan of the same template.

The column-header row itself is NOT a single-height band: it carries an
extra internal sub-divider (under the INTERVAL/LIFE LIMITS / Current
Data / Original / Remaining group labels) that a plain "N-th horizontal
line" count cannot distinguish from the true header/data boundary, since
page 1 carries additional lines above it (the info box) that pages 2+
don't. Confirmed directly: counting divider lines from the top gives a
DIFFERENT index for the true data-start line depending on whether the
page has the info box or not. This module instead grows a crop downward
from the very first divider line, one candidate boundary at a time,
and OCRs only the narrow POSITION column header cell (short, single
word, and far enough right to avoid the page-1 logo's own text bleeding
into the crop) -- the growing crop's data-start line is the first one
whose accumulated text contains "POS" (`_find_data_start`). This is
cheap (one narrow OCR call per candidate line, only on page load) and
confirmed directly to resolve correctly on every page of the sample,
with and without the info box.

Once past the header, every row boundary is a real, evenly spaced
(~49px at 300 DPI) ruled divider with no missing/merged lines anywhere
in the sample -- confirmed directly against every page's own full
divider-line list (no row gap deviates from the modal pitch anywhere
below the header). The very first row band a naive "prepend data_start,
then rescan from there" approach produces can duplicate the data_start
line itself as a near-zero-height spurious first "row" (the rescan
starting exactly AT data_start re-detects that same divider a few
pixels later) -- this module starts the rescan a few pixels below
data_start instead to avoid that, and the last row on every page is
bounded by the table's own last ruled divider (confirmed well above any
signature block on every page -- the last real divider never comes
anywhere near the "Signed: ... Senior Airworthiness Engineer ..."
sign-off block that sits well below the table's own bottom border, see
below), so no page-bottom whitespace or signature text is ever swept
into the last row.

Per-cell OCR of an actually-blank ruled cell was confirmed directly to
frequently hallucinate a short, low-confidence glyph run rather than
returning nothing (e.g. a blank REF_NO cell reading as "a"/"po", a blank
REMARKS cell reading as "Po") -- this is the same failure mode
`occm_components_status_ruled_grid.py`'s own docstring describes for its
sibling template. Two independent, column-appropriate safeguards handle
it here rather than a single blanket fix (confirmed directly that
neither alone is sufficient): numeric/date columns are reduced to only
their own matching substring (digit runs with optional `,`/`'` thousands
separators, or `D[D][.-]Mon[.-]YY[YY]`-shaped dates) via regex, which
already drops non-numeric/non-date hallucinated noise on its own; REF_NO
and REMARKS (this template's own two columns that are legitimately blank
or dash-only on a real, non-trivial share of rows -- unlike the other
text columns, which are populated on every real row of the sample) are
additionally OCR'd with a raised word-confidence floor (hallucinated
noise on this sample confirmed directly to score well under 60, genuine
short values well over 90) rather than the `min_conf=-1` this package's
other per-column-strip variants default to.

Known limitation, confirmed directly on the real sample: the POSITION
column's own "LH" value is misread by Tesseract as an unrelated short
glyph run ("on"/"oun") on a scattered minority of rows, at a similar
confidence to genuine "RH"/"LH" reads in the same column -- so neither
the numeric/date regex approach nor a confidence floor can distinguish
it from a correct read (both this module's neighbouring "RH" cells and
the misread "LH" cells score in the same 48-58 range). This is accepted
as ordinary scan noise rather than force-corrected: guessing "LH" whenever
POSITION looks unlike a known code would be exactly the kind of
plausible-looking wrong value this project's "never guess a wrong split"
convention exists to avoid; a mis-OCR'd value is left as OCR'd rather than
pattern-corrected, same as `occm_components_status_ruled_grid.py`'s own
documented POSITION-column limitation.

A "Signed: ... / Senior Airworthiness Engineer / ... Engineering
Department" sign-off block sits at the very bottom of every page, well
below the table's own last ruled row on every page of the sample (see
above) -- this module never reads that region at all (rows are built
purely from the table's own detected ruled dividers), so no signer name
is ever captured into any output field, and none is written into this
module's own source either.
"""
from __future__ import annotations
import re

import numpy as np

from sheet_types.ht_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, ocr_words, page_count

NAME = "Service Life Limited Components Status (Scanned)"

# Deliberately empty -- this file's own text layer is blank on every page
# (see module docstring), so a plain-pdfplumber SIGNATURES phrase can
# never fire. Detected instead via ocr_detect() below, through the
# router's blank-text-layer OCR-fallback path (sheet_types/ht.py's own
# detect_variant()).
SIGNATURES: list[str] = []

CANONICAL_COLUMNS = [
    "REF_NO",
    "DESCRIPTION",
    "CERT_REF",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "POSITION",
    "TREATMENT",
    "LIMIT_HOURS",
    "LIMIT_CYCLES",
    "LIMIT_DAYS",
    "DOM",
    "LAST_TREATMENT_DATE",
    "INST_DATE",
    "DSR",
    "HSR",
    "CSR",
    "TSN",
    "CSN",
    "REMAINING_DAYS",
    "REMAINING_HOURS",
    "REMAINING_CYCLES",
    "REMARKS",
    # Header metadata -- parsed once (page 1) and stamped on every row.
    "AIRCRAFT_REG",
    "AIRCRAFT_MSN",
    "AIRCRAFT_TYPE",
    "AIRCRAFT_FH",
    "AIRCRAFT_FC",
    "REPORT_DATE",
]

_DATE_RE = r"^\d{1,2}[.\-][A-Za-z]{3}[.\-]\d{2,4}$"
# Digit run with optional `,`/`'` thousands separators AND an optional
# decimal point -- TSN/CSN in particular are frequently printed with one
# decimal place (e.g. "13945.2"); the other numeric columns in this
# template are plain integers in every row of the sample, but allowing an
# optional trailing decimal here is harmless for them (a genuine integer
# never has a stray "." to match) and avoids a real bug confirmed
# directly during validation: an earlier version of this pattern/token
# regex (digits + separators only, no ".") silently truncated every
# TSN/CSN decimal value at the decimal point instead of just flagging it.
_NUM_RE = r"^\d[\d,'.]*$"

_OVERRIDES = {
    # Blank/dash-only on a real share of rows (see module docstring) --
    # loose pattern, allow_empty.
    "REF_NO": {"allow_empty": True},
    "DESCRIPTION": {"allow_empty": True, "uppercase": True},
    "CERT_REF": {"allow_empty": True},
    "PART_NUMBER": {"allow_empty": True},
    "SERIAL_NUMBER": {"allow_empty": True},
    # See module docstring "Known limitation" -- loose pattern, the
    # confirmed OCR weak point in this module.
    "POSITION": {"allow_empty": True, "uppercase": True},
    "TREATMENT": {"allow_empty": True, "uppercase": True},
    "LIMIT_HOURS": {"pattern": _NUM_RE, "allow_empty": True},
    "LIMIT_CYCLES": {"pattern": _NUM_RE, "allow_empty": True},
    "LIMIT_DAYS": {"pattern": _NUM_RE, "allow_empty": True},
    "DOM": {"pattern": _DATE_RE, "allow_empty": True},
    "LAST_TREATMENT_DATE": {"pattern": _DATE_RE, "allow_empty": True},
    "INST_DATE": {"pattern": _DATE_RE, "allow_empty": True},
    "DSR": {"pattern": _NUM_RE, "allow_empty": True},
    "HSR": {"pattern": _NUM_RE, "allow_empty": True},
    "CSR": {"pattern": _NUM_RE, "allow_empty": True},
    "TSN": {"pattern": _NUM_RE, "allow_empty": True},
    "CSN": {"pattern": _NUM_RE, "allow_empty": True},
    "REMAINING_DAYS": {"pattern": _NUM_RE, "allow_empty": True},
    "REMAINING_HOURS": {"pattern": _NUM_RE, "allow_empty": True},
    "REMAINING_CYCLES": {"pattern": _NUM_RE, "allow_empty": True},
    "REMARKS": {"allow_empty": True},
    # Header metadata -- a single OCR misread here shouldn't flag every
    # row of the file, same reasoning this package's other header-plus-
    # body OCR variants use.
    "AIRCRAFT_REG": {"allow_empty": True},
    "AIRCRAFT_MSN": {"allow_empty": True},
    "AIRCRAFT_TYPE": {"allow_empty": True},
    "AIRCRAFT_FH": {"allow_empty": True},
    "AIRCRAFT_FC": {"allow_empty": True},
    "REPORT_DATE": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_DPI = 300

# Column order matching the ruled grid's own 22 columns, left to right.
_COLUMN_ORDER = [
    "REF_NO", "DESCRIPTION", "CERT_REF", "PART_NUMBER", "SERIAL_NUMBER",
    "POSITION", "TREATMENT", "LIMIT_HOURS", "LIMIT_CYCLES", "LIMIT_DAYS",
    "DOM", "LAST_TREATMENT_DATE", "INST_DATE", "DSR", "HSR", "CSR", "TSN",
    "CSN", "REMAINING_DAYS", "REMAINING_HOURS", "REMAINING_CYCLES",
    "REMARKS",
]

_TEXT_JOIN_COLS = {"DESCRIPTION", "TREATMENT", "REMARKS"}
_CODE_COLS = {"REF_NO", "PART_NUMBER", "SERIAL_NUMBER", "POSITION", "CERT_REF"}
_CODE_STRIP_CHARS = " _\"'`‘’“”.,;:()[]{}|~="
_NUM_COLS = {"LIMIT_HOURS", "LIMIT_CYCLES", "LIMIT_DAYS", "DSR", "HSR", "CSR",
             "TSN", "CSN", "REMAINING_DAYS", "REMAINING_HOURS",
             "REMAINING_CYCLES"}
_DATE_COLS = {"DOM", "LAST_TREATMENT_DATE", "INST_DATE"}
_NUM_TOKEN_RE = re.compile(r"\d[\d,'.]*")
_DATE_TOKEN_RE = re.compile(r"\d{1,2}[.\-][A-Za-z]{3}[.\-]\d{2,4}")

# Blank/dash-only cells in these two columns were confirmed directly to
# hallucinate low-confidence noise far more often than this template's
# other (always-populated) text columns -- see module docstring.
_LOW_CONF_FLOOR = {"REF_NO": 60, "REMARKS": 60}

# Grid-line detection thresholds -- tuned directly against the real
# sample's own 300 DPI render (see module docstring "Row/column
# geometry"). The outer border and every internal divider render fully
# solid (dark fraction close to 1.0); a lower threshold with a fairly
# generous merge gap absorbs the occasional anti-aliased/partial line
# without merging two genuinely adjacent rows (~49px apart at this DPI).
_DARK_PIXEL_THRESH = 200
_LINE_THRESH_FRAC = 0.45
_LINE_MERGE_PX = 10
# Header search window and post-header row-rescan offset -- see module
# docstring for why the rescan starts a few px below data_start rather
# than exactly at it.
_HEADER_SEARCH_MAX_Y = 800
_ROW_RESCAN_OFFSET_PX = 5


def _divider_lines(arr: np.ndarray, x0: int, x1: int, y_lo: int, y_hi: int) -> list[int]:
    frac = (arr[:, x0:x1] < _DARK_PIXEL_THRESH).sum(axis=1) / (x1 - x0)
    ys = [y for y in range(y_lo, y_hi) if frac[y] > _LINE_THRESH_FRAC]
    groups: list[list[int]] = []
    for y in ys:
        if groups and y - groups[-1][-1] <= _LINE_MERGE_PX:
            groups[-1].append(y)
        else:
            groups.append([y])
    return [int(np.mean(g)) for g in groups]


def _find_col_lines(arr: np.ndarray) -> list[int]:
    """X-centers of the table's 23 vertical column dividers (22 columns),
    found fresh per page from a full-height-band vertical darkness scan
    (see module docstring)."""
    h, w = arr.shape
    y0, y1 = int(h * 0.15), int(h * 0.85)
    frac = (arr[y0:y1, :] < _DARK_PIXEL_THRESH).sum(axis=0) / (y1 - y0)
    xs = [x for x in range(w) if frac[x] > 0.5]
    groups: list[list[int]] = []
    for x in xs:
        if groups and x - groups[-1][-1] <= 4:
            groups[-1].append(x)
        else:
            groups.append([x])
    return [int(np.mean(g)) for g in groups]


async def _find_data_start(img, arr: np.ndarray, col_bounds: dict) -> tuple[int | None, list[int]]:
    """First row-divider Y below the (possibly two-tier) column-header
    row -- see module docstring for why a plain line-index count can't
    distinguish this from the header's own internal sub-divider."""
    w = img.width
    y_hi = min(_HEADER_SEARCH_MAX_Y, img.height)
    lines = _divider_lines(arr, col_bounds["REF_NO"][0], col_bounds["REMARKS"][1], 100, y_hi)
    if not lines:
        return None, lines
    x0, x1 = col_bounds["POSITION"]
    for j in range(1, len(lines)):
        crop = img.crop((x0, lines[0] + 2, x1, lines[j] - 2))
        txt = (await ocr_text(crop, psm=6)).strip().upper()
        if "POS" in txt:
            return lines[j], lines
    return None, lines


async def _ocr_column(img, name: str, col_bounds: dict, y0: int, y1: int) -> list[tuple[float, float, str]]:
    x0, x1 = col_bounds[name]
    if y1 <= y0:
        return []
    crop = img.crop((x0, y0, x1, y1))
    min_conf = _LOW_CONF_FLOOR.get(name, -1)
    words = await ocr_words(crop, psm=6, min_conf=min_conf)
    out = []
    for wd in words:
        text = str(wd.get("text", "")).strip()
        if not text:
            continue
        out.append((y0 + wd["top"], wd.get("left", 0), text))
    return out


def _clean_field(name: str, tokens: list[tuple[float, float, str]]) -> str:
    lines: list[list[tuple[float, float, str]]] = []
    for top, left, text in sorted(tokens, key=lambda t: t[0]):
        if lines and abs(top - lines[-1][0][0]) <= 12:
            lines[-1].append((top, left, text))
        else:
            lines.append([(top, left, text)])
    ordered = [[t for _, _, t in sorted(line, key=lambda x: x[1])] for line in lines]
    if name in _TEXT_JOIN_COLS:
        text = " ".join(" ".join(line) for line in ordered)
    else:
        text = "".join("".join(line) for line in ordered)
    if name in _CODE_COLS:
        text = text.strip(_CODE_STRIP_CHARS)
    if name in _NUM_COLS:
        found = _NUM_TOKEN_RE.findall(text)
        text = max(found, key=len) if found else ""
    if name in _DATE_COLS:
        found = _DATE_TOKEN_RE.findall(text)
        text = found[0] if found else ""
    return text


_HEADER_FIELDS = ["AIRCRAFT_REG", "AIRCRAFT_MSN", "AIRCRAFT_TYPE",
                  "AIRCRAFT_FH", "AIRCRAFT_FC", "REPORT_DATE"]

_REG_RE = re.compile(r"A/C\s*Reg:?\s*([A-Z0-9\-]+)", re.IGNORECASE)
_MSN_RE = re.compile(r"MSN:?\s*(\S+)", re.IGNORECASE)
_TYPE_RE = re.compile(r"A/C\s*Type:?\s*(\S+)", re.IGNORECASE)
_FH_RE = re.compile(r"A/F\s*FH\s*([\d,]+)", re.IGNORECASE)
_FC_RE = re.compile(r"A/F\s*FC\s*([\d,]+)", re.IGNORECASE)
_RPT_DATE_RE = re.compile(r"Report\s*Date\s*(\S+)", re.IGNORECASE)


async def _parse_header(img) -> dict:
    """Page-1 info box (A/F FH / A/F FC / Report Date -- left box; A/C Reg
    / MSN / A/C Type -- right box) -- confirmed directly to OCR cleanly as
    one combined label:value crop at this psm (unlike
    `occm_components_status_ruled_grid.py`'s own sibling box, whose two
    label columns interleave at that module's own narrower crop width and
    need splitting into value-only strips instead)."""
    meta = {k: "" for k in _HEADER_FIELDS}
    w, h = img.size
    crop = img.crop((int(w * 0.20), int(h * 0.105), int(w * 0.50), int(h * 0.16)))
    text = await ocr_text(crop, psm=6)

    def grab(rx: re.Pattern) -> str:
        m = rx.search(text)
        return m.group(1).strip() if m else ""

    meta["AIRCRAFT_REG"] = grab(_REG_RE)
    meta["AIRCRAFT_MSN"] = grab(_MSN_RE)
    meta["AIRCRAFT_TYPE"] = grab(_TYPE_RE)
    meta["AIRCRAFT_FH"] = grab(_FH_RE)
    meta["AIRCRAFT_FC"] = grab(_FC_RE)
    meta["REPORT_DATE"] = grab(_RPT_DATE_RE)
    return meta


def _col_bounds_from_lines(col_lines: list[int]) -> dict | None:
    if len(col_lines) < len(_COLUMN_ORDER) + 1:
        return None
    pairs = list(zip(col_lines[:-1], col_lines[1:]))[: len(_COLUMN_ORDER)]
    return {name: bounds for name, bounds in zip(_COLUMN_ORDER, pairs)}


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback (see
    sheet_types/ht.py) -- this variant's SIGNATURES is deliberately empty
    (see module docstring).

    Requires BOTH halves of the title box's own fixed phrase ("SERVICE
    LIFE LIMITED" and "COMPONENTS STATUS", either side of the
    document-specific MSN token that sits between them -- see module
    docstring) present in the same crop. Checked directly (grep) against
    every SIGNATURES list in sheet_types/{occm,ht,llp}.py and every
    existing occm_variants/ht_variants/llp_variants module's own
    SIGNATURES/ocr_detect anchor text: no collision found for either
    phrase, individually or combined.
    """
    try:
        img = await render_page(pdf_path, 0, dpi=_DPI)
        w, h = img.size
        crop = img.crop((int(w * 0.45), int(h * 0.09), int(w * 0.92), int(h * 0.18)))
        text = (await ocr_text(crop, psm=6)).upper()
        normed = " ".join(text.split())
        return "SERVICE LIFE LIMITED" in normed and "COMPONENTS STATUS" in normed
    except Exception:
        return False


async def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    header_meta = {k: "" for k in _HEADER_FIELDS}
    n_pages = await page_count(pdf_path)

    for page_index in range(n_pages):
        img = await render_page(pdf_path, page_index, dpi=_DPI)
        arr = np.array(img.convert("L"))

        col_lines = _find_col_lines(arr)
        col_bounds = _col_bounds_from_lines(col_lines)
        if col_bounds is None:
            continue

        if page_index == 0:
            header_meta = await _parse_header(img)

        data_start, _ = await _find_data_start(img, arr, col_bounds)
        if data_start is None:
            continue

        extra = _divider_lines(arr, col_bounds["REF_NO"][0], col_bounds["REMARKS"][1],
                                data_start + _ROW_RESCAN_OFFSET_PX, img.height)
        row_lines = [data_start] + extra
        if len(row_lines) < 2:
            continue

        for i in range(len(row_lines) - 1):
            y0, y1 = row_lines[i], row_lines[i + 1]
            row: dict[str, str] = {}
            for name in _COLUMN_ORDER:
                toks = await _ocr_column(img, name, col_bounds, y0, y1)
                row[name] = _clean_field(name, toks)
            row["_page"] = page_index + 1
            row.update(header_meta)
            records.append(row)

    return records
