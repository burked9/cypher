"""TRP (Time-Replacement Parts / Hard Time) STATUS -- OCR required, end to
end, because the pdfplumber text layer is not merely broken but doubled: a
per-character position dump (see below) shows two near-identical text runs
stamped at almost the same (x, top) for the same visual line, offset by
only ~1.3pt in `top` -- one run decodes as plain, correct Latin text, the
other decodes through a different (or differently-indexed) embedded font
that maps a large fraction of glyphs to Hangul/CJK/punctuation codepoints
instead of the intended Latin ones. `page.extract_text()` therefore
interleaves the two runs' characters and comes out as an unusable jumble
(duplicated digits, stray Hangul, doubled words) even on rows that render
as a clean, sharp, perfectly ordinary ruled table when rasterised -- this
is a different failure mode than this package's other "broken font" HT
variant (`hard_time_aircraft_components_status_broken_font.py`, a single
inconsistent-per-glyph substitution, no duplication) and than its
total-mapping-failure sibling (`(cid:<n>)` placeholders throughout) --
confirmed directly against a real corpus file (5 pages): no simple
decode table recovers either run cleanly, so OCR is used for every field.

One short fragment -- the title, which OCRs (and, per a spot pdfplumber
check, also happens to decode) as "TRPSTATUS" with no space -- is present,
byte-for-byte via `extract_text()`, on every one of the file's 5 pages, so
plain-text SIGNATURES matching still works despite the rest of the page
being unusable through that same text layer.

Header block, fixed position, repeats near-identically on every page (real
field shapes only, genericised)::

    AIRCRAFT REGISTRATION: <registration>          <operator wordmark>
    AIRCRAFT MODEL TYPE: <type>
    AIRCRAFT SERIAL NUMBER: <msn>
                     TRP STATUS
    AIRCRAFT TSN :  <tsn>            (page 1 only)
    AIRCRAFT CSN :  <csn>            (page 1 only)
    AS of DATE :    <date>           (page 1 only)

Confirmed directly: a wide OCR pass across just the left-hand header
column (excluding the operator wordmark's own x-range, which otherwise
measurably degrades recognition of the neighbouring "AIRCRAFT MODEL TYPE"
line -- confirmed directly, dropping the wordmark out of the crop turns a
misread "B737-800" -> "8737-800" into a correct read) resolves every
header field reliably. TSN/CSN/AS-of-DATE are only printed on page 1, so
header metadata is parsed across every page (first-wins per field, same
convention as this package's other header-plus-body OCR variants) until
complete.

Main table, one header row, 20 columns -- TASK NO. | DESCRIPTION | P/N |
S/N | POSITION | TASK | INTERVAL(HOURS, CYCLES, DAY) | CURRENT COMPONENT
(TSR, CSR) | TASK(PERFORMED DATE, Expire Date) | A/C DATA at INST(HOURS,
CYCLES, DATE) | NEXT DUE of A/C(HOURS, CYCLES, DATE) | REMAINING.

OCR approach: per-column-strip OCR (one `ocr_words()` call per column per
page), not per-row and not whole-page -- same tradeoff this package's
other per-column-strip HT/OCCM variants make. Confirmed directly: a naive
column-width crop (border-to-border) causes Tesseract to badly misread or
drop rows around the ruled vertical border lines themselves (a short
digit-and-dash token like "21-100-00" next to a border is a known
Tesseract confusion -- it reads border fragments as extra glyphs, e.g.
"=" / "|" / "711-100-006" for a real "21-100-00"); trimming each column
crop in by 5px on both sides (comfortably inside the ruled border, at this
module's own 300 DPI) before OCR'ing fixes this -- confirmed directly,
recovers all 27 of page 1's own real rows correctly where the untrimmed
crop recovered well under half of them.

Row anchoring: TASK_NO is used as the per-row Y anchor (a task-code token
matching this file's own real "NN-NNN-NN[-NN]" shape, or the literal
"CMM" -- this report uses "CMM" in place of a task code on a component's
own CMM-interval-driven sibling row, e.g. an Escape Slide's own bottle-
reservoir HST/Discard pair). TASK_NO is always populated (unlike POSITION,
DESCRIPTION, or the several columns this file legitimately leaves blank on
a paired/shared-reading row -- see below), so it anchors more reliably
than any of those. Every other column's OCR'd words are assigned to their
nearest TASK_NO anchor by Y-distance, within a tolerance under half this
file's own row pitch (confirmed directly, ~53-54px @ 300 DPI between
consecutive rows).

Known limitation, confirmed directly against the real sample file: OCR
occasionally misreads the leading "2" of a "21-..." / "23-..." task code
as a similar-shaped glyph ("?", "7") or drops/duplicates a digit --
TASK_NO is kept exactly as OCR'd rather than force-corrected (no fixed
substitution reliably disambiguates a "?" from a genuine stray character
across the file), so a real corpus file is expected to show some rows
flagged on TASK_NO's own pattern check; this is an accepted, visible
signal of this file's own severe encoding/OCR difficulty, not silently
hidden or guessed away. All other columns held up well in the same
direct check.

Several rows share one reading across a task pair printed back-to-back for
the same component (e.g. an "Operatopn check"/"Replace" pair, or an
HST/Discard pair on the same reservoir) -- CURRENT_TSR/CURRENT_CSR,
TASK_PERFORMED_DATE/TASK_EXPIRE_DATE, and the A/C-DATA-at-INST columns are
then genuinely blank on every row but the first of the pair in the source
itself, kept blank here rather than forward-filled, per this project's
"carry the source's own blanks through, don't guess" convention.
REMAINING carries a plain "<n> Day" or "<n> FH" literal, or (for a couple
of real Megaphone Battery rows) the literal phrase "If Green LED is out"
in place of a numeric remaining value -- kept as-is.

A signature block (name, title, employer, handwritten signature/date)
appears below the table on the file's own last page. Confirmed directly:
it sits well outside every column's own Y-range once the last real
TASK_NO anchor has been consumed, so it is never picked up as a row by
construction; no name from it is extracted into any field.
"""
from __future__ import annotations
import re

from PIL import Image

from sheet_types.ht_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, ocr_words, page_count

NAME = "TRP Status (Dual-Layer Font, Scanned)"

# See module docstring -- "TRPSTATUS" (title, no space) is confirmed
# present via plain `extract_text()` on every page of the real corpus
# file, despite the rest of the page's text layer being unusable. Checked
# against every SIGNATURES list in occm.py/ht.py/llp.py and every existing
# occm_variants/ht_variants/llp_variants module's own SIGNATURES list (plus
# a plain grep for "TRP STATUS"/"TRPSTATUS"); no collision found.
SIGNATURES = [
    "TRPSTATUS",
]

CANONICAL_COLUMNS = [
    "TASK_NO",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "POSITION",
    "TASK",
    "INTERVAL_HOURS",
    "INTERVAL_CYCLES",
    "INTERVAL_DAY",
    "CURRENT_TSR",
    "CURRENT_CSR",
    "TASK_PERFORMED_DATE",
    "TASK_EXPIRE_DATE",
    "ACDATA_HOURS",
    "ACDATA_CYCLES",
    "ACDATA_DATE",
    "NEXTDUE_HOURS",
    "NEXTDUE_CYCLES",
    "NEXTDUE_DATE",
    "REMAINING",
    # Header metadata -- parsed across pages (page 1 only carries
    # TSN/CSN/REPORT_DATE) and stamped on every row.
    "AIRCRAFT_REG",
    "AIRCRAFT_TYPE",
    "MSN",
    "AC_TSN",
    "AC_CSN",
    "REPORT_DATE",
]

# Optional trailing "," tolerated -- a confirmed recurring OCR artifact on
# this file's own date cells (a stray comma picked up from the ruled
# border immediately right of the cell), not a real part of the value.
_DATE_RE = r"^\d{1,2}-[A-Za-z]{3}-\d{2,4},?$"
# The literal phrase "If Green LED is out" (Megaphone Battery rows'
# own real Interval/Next-Due value -- see module docstring) OCR's with
# inconsistent spacing/wrapping; accepted with or without spaces rather
# than force-normalised.
_LED_LITERAL_RE = r"(?i:^IF\s*GREEN\s*LED\s*IS\s*OUT$)"
# A blank/"." cell is genuinely common here (see module docstring -- a
# shared-reading row pair leaves most of these columns blank on the
# second row); allow_empty throughout rather than forward-filled.
_NUM_RE = r"^[\d,.]+$"
# CURRENT_TSR and ACDATA_HOURS carry a real "<hours> :<sub-hours>" shape in
# the source (confirmed directly against a real corpus file, e.g.
# "1011 :53", "63371 :19" -- an hours-plus-fractional-remainder reading,
# not an OCR artifact: it recurs consistently, at the same sub-column
# offset, across every row that has a CURRENT COMPONENT / A/C DATA at INST
# reading at all). Every other numeric column in this table (CSR, all
# three CYCLES columns, both other HOURS columns) is a genuinely plain
# integer with no such sub-part.
# The ":" separator itself OCR's inconsistently on this file -- confirmed
# directly, also seen as "-" ("1011-53") and "°" ("3671°31") for the same
# real ":" on other rows of the same column. All three are tolerated here
# (a lone "-" or "°" is never itself a legitimate part of a plain hours
# reading in this column, so this doesn't mask a genuinely different kind
# of bad value).
_HOURS_COLON_RE = r"^[\d,.]+(?:\s*[:\-°]\s*\d+)?$"

_OVERRIDES = {
    # See module docstring -- OCR misreads TASK_NO's leading digit often
    # enough on this real corpus file that a real run is expected to show
    # some rows flagged here; kept as a real (not loosened) pattern check
    # rather than silently widened, so that signal stays visible.
    # Confirmed directly against a real corpus file: the middle segment is
    # usually 3 digits ("21-100-00") but a real 2-digit shape also recurs
    # ("29-30-00", "32-23-00") -- both are genuine source shapes, not OCR
    # noise (their own DESCRIPTION/PART_NUMBER/dates around them are clean).
    "TASK_NO": {"pattern": r"^\d{2}-\d{2,3}-\d{2}(-\d{2})?$|^CMM$"},
    # PART_NUMBER/SERIAL_NUMBER repeat blank on a component's own sibling
    # task rows -- confirmed directly against a real corpus file: an
    # "Escape Slide" section's own Restoration/Operational-check/
    # Functional-Check/HST/Discard/Replace rows share one P/N+S/N pair,
    # vertically merged in the source and printed only on the group's
    # first row. allow_empty rather than forward-filled, same convention
    # as the reference broken-font HT variant's own POSITION field --
    # carry the source's own blank cells through rather than guess.
    "PART_NUMBER": {"allow_empty": True},
    # A real "#<digits>" SN shape recurs on several real rows (confirmed
    # directly, e.g. a Lavatory Waste Drain Ball-Valve's own "#043184") --
    # "#" is genuine source punctuation here, not OCR noise, so the
    # leading-char charset is widened to allow it. "¥" is kept in the
    # charset too: a confirmed recurring OCR misread of "Y" on this file's
    # own "IYnnnnn" reservoir SNs (not fixed via a blind char_map
    # substitution, since ¥ isn't reliably only ever a misread Y anywhere
    # else in this project's shared OCR_CHAR_MAP).
    "SERIAL_NUMBER": {
        "allow_empty": True,
        "pattern": r"^#?[A-Z0-9/¥](?:[A-Z0-9\-/¥]*[A-Z0-9/¥])?$",
    },
    "POSITION": {"allow_empty": True},
    "TASK": {"allow_empty": True},
    "INTERVAL_HOURS": {"pattern": _NUM_RE, "allow_empty": True},
    "INTERVAL_CYCLES": {"pattern": _NUM_RE, "allow_empty": True},
    # Genuinely heterogeneous: a plain year count ("3Y"), a flight-hour/
    # -cycle interval ("16000FH"), "At batt change", "At change", "0", or
    # blank -- loose charset check rather than a fixed shape, same
    # reasoning as the reference broken-font HT variant's MPD_AD_MFG_REF.
    "INTERVAL_DAY": {"pattern": r"^[\dA-Za-z,.\s’']+$", "allow_empty": True},
    "CURRENT_TSR": {"pattern": _HOURS_COLON_RE, "allow_empty": True},
    "CURRENT_CSR": {"pattern": _NUM_RE, "allow_empty": True},
    "TASK_PERFORMED_DATE": {"pattern": _DATE_RE, "allow_empty": True},
    "TASK_EXPIRE_DATE": {"pattern": _DATE_RE, "allow_empty": True},
    "ACDATA_HOURS": {"pattern": _HOURS_COLON_RE, "allow_empty": True},
    "ACDATA_CYCLES": {"pattern": _NUM_RE, "allow_empty": True},
    "ACDATA_DATE": {"pattern": _DATE_RE, "allow_empty": True},
    "NEXTDUE_HOURS": {"pattern": _NUM_RE, "allow_empty": True},
    "NEXTDUE_CYCLES": {"pattern": _NUM_RE, "allow_empty": True},
    # Real Megaphone Battery rows print the literal phrase "If Green LED
    # is out" in place of a date here too (see module docstring/
    # _LED_LITERAL_RE) -- accepted alongside the normal date shape.
    "NEXTDUE_DATE": {"pattern": f"{_DATE_RE}|{_LED_LITERAL_RE}", "allow_empty": True},
    # "<n> Day" / "<n> FH" / "<n> FC", or the literal phrase
    # "If Green LED is out" on a couple of real Megaphone Battery rows
    # (see module docstring) -- loose charset check, not force-split.
    "REMAINING": {"pattern": r"^[\dA-Za-z,.\s]+$", "allow_empty": True},
    # Header metadata -- same value stamped on every row of the file, so a
    # tight per-row pattern here would either flag every row over one OCR
    # misread in one place, or none at all -- same reasoning this
    # package's other header-plus-body OCR variants use.
    "AIRCRAFT_REG": {"allow_empty": True},
    "AIRCRAFT_TYPE": {"allow_empty": True},
    "MSN": {"allow_empty": True},
    "AC_TSN": {"allow_empty": True},
    "AC_CSN": {"allow_empty": True},
    "REPORT_DATE": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Column X-boundaries (px @ 300 DPI), trimmed 5px in from each ruled
# border on both sides (see module docstring for why the trim matters).
# Always paired with `render_page(..., dpi=300)`, never a different DPI,
# so these stay valid. Derived directly from this report's own real
# ruled-column border positions (confirmed directly across the first, a
# middle, and the last page of a real corpus file; stable across all of
# them, within a couple of px).
_COLUMNS = [
    (163, 308, "TASK_NO"),
    (318, 686, "DESCRIPTION"),
    (696, 881, "PART_NUMBER"),
    (891, 1076, "SERIAL_NUMBER"),
    (1086, 1249, "POSITION"),
    (1259, 1409, "TASK"),
    (1419, 1515, "INTERVAL_HOURS"),
    (1525, 1633, "INTERVAL_CYCLES"),
    (1643, 1762, "INTERVAL_DAY"),
    (1772, 1928, "CURRENT_TSR"),
    (1938, 2040, "CURRENT_CSR"),
    (2050, 2223, "TASK_PERFORMED_DATE"),
    (2233, 2348, "TASK_EXPIRE_DATE"),
    (2358, 2489, "ACDATA_HOURS"),
    (2499, 2608, "ACDATA_CYCLES"),
    (2618, 2770, "ACDATA_DATE"),
    (2780, 2908, "NEXTDUE_HOURS"),
    (2918, 3026, "NEXTDUE_CYCLES"),
    (3036, 3153, "NEXTDUE_DATE"),
    (3163, 3338, "REMAINING"),
]
# Genuine multi-word free text -- joined with a single space. Every other
# column is a genuinely space-free source value, joined with no separator.
_JOIN_SPACE = {"DESCRIPTION", "POSITION", "TASK", "INTERVAL_DAY", "REMAINING"}

# Stray ruled-border artifacts occasionally picked up as their own word box
# despite the 5px trim.
_NOISE_TOKEN_RE = re.compile(r"^[|\[\]_\-—–.]+$")

# Row anchor: a task-code token, or the literal "CMM" (see module
# docstring for why TASK_NO, not DESCRIPTION or POSITION, anchors each
# row). Loosened vs. the RULES pattern check above -- an anchor token only
# needs to look enough like a task code to seed a row; the RULES pattern
# is what actually flags an OCR-garbled one for a human, per this
# project's "never silently fix, still validate" convention.
_ANCHOR_RE = re.compile(r"^[\d?]{1,2}-\d{2,3}-\d{2}(-\d{2})?$|^CMM$", re.IGNORECASE)

# Y-tolerance for assigning a non-anchor column's word to its nearest
# TASK_NO anchor -- measured directly against this file's own row pitch
# (~53-54px @ 300dpi between consecutive rows); comfortably under half
# that.
_ANCHOR_TOLERANCE_PX = 24

# Header field regexes -- run against a wide OCR pass over just the
# left-hand header column (see module docstring for why the operator
# wordmark's own x-range is excluded from that crop).
_REG_RE = re.compile(r"REGISTRATION\s*:?\s*([A-Z0-9\-]+)")
_TYPE_RE = re.compile(r"MODEL\s*TYPE\s*:?\s*([A-Z0-9\-]+)")
_MSN_RE = re.compile(r"SERIAL\s*NUMBER\s*:?\s*(\d+)")
_TSN_RE = re.compile(r"AIRCRAFT\s*TSN\s*:?\s*([\d,.]+)")
_CSN_RE = re.compile(r"AIRCRAFT\s*CSN\s*:?\s*([\d,.]+)")
_DATE_RE_HDR = re.compile(r"AS\s*of\s*DATE\s*:?\s*(\S+\s+\d{1,2},?\s*\d{2,4})", re.IGNORECASE)

_HEADER_FIELDS = ["AIRCRAFT_REG", "AIRCRAFT_TYPE", "MSN", "AC_TSN", "AC_CSN", "REPORT_DATE"]

# Data grid starts just below the fixed-position column-header row, which
# sits at the same pixel offset on every page of a real corpus file
# (confirmed directly; the header block above the table -- registration/
# type/MSN/title, plus TSN/CSN/AS-of-DATE on page 1 only -- is fixed
# height whether or not those last three lines are present, since page 1
# still lines up with every other page's own table start).
_TABLE_TOP_PX = 618


def _col_bounds(name: str) -> tuple[int, int]:
    for lo, hi, col in _COLUMNS:
        if col == name:
            return lo, hi
    raise KeyError(name)


async def _ocr_column(img, name: str, y0: int, y1: int) -> list[tuple[float, str]]:
    """OCR one column's full-height (5px-trimmed) strip and return
    (top, text) pairs in original-image page coordinates (see module
    docstring for why the trim matters)."""
    lo, hi = _col_bounds(name)
    x0 = max(0, int(lo))
    x1 = min(img.width, int(hi))
    crop = img.crop((x0, y0, x1, y1))
    words = await ocr_words(crop, psm=6, min_conf=-1)
    out = []
    for w in words:
        text = str(w.get("text", "")).strip()
        if not text or _NOISE_TOKEN_RE.match(text):
            continue
        out.append((y0 + w["top"], text))
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
    sep = " " if col_name in _JOIN_SPACE else ""
    return sep.join(tokens).strip(" |[]_-—–")


def _parse_header_text(text: str, meta: dict) -> None:
    upper = text.upper()
    for pat, key in (
        (_REG_RE, "AIRCRAFT_REG"),
        (_TYPE_RE, "AIRCRAFT_TYPE"),
        (_MSN_RE, "MSN"),
        (_TSN_RE, "AC_TSN"),
        (_CSN_RE, "AC_CSN"),
    ):
        if meta.get(key):
            continue
        m = pat.search(upper)
        if m:
            meta[key] = m.group(1)
    if not meta.get("REPORT_DATE"):
        m = _DATE_RE_HDR.search(text)
        if m:
            meta["REPORT_DATE"] = m.group(1).strip()


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback. Not
    expected to fire for the known source file (its text layer is never
    blank -- see module docstring; it's found via plain-text SIGNATURES
    instead), kept for interface consistency and in case a more severely
    corrupted copy of this template turns up with an unusably short text
    layer."""
    try:
        img = await render_page(pdf_path, 0, dpi=300)
        w, h = img.size
        crop = img.crop((0, 0, w, int(h * 0.22)))
        text = (await ocr_text(crop, psm=6)).upper()
        return "TRP STATUS" in text or "TRPSTATUS" in text.replace(" ", "")
    except Exception:
        return False


def _extract_page_rows(columns_words: dict[str, list[tuple[float, str]]]) -> list[dict]:
    anchor_tokens = [
        (top, t) for top, t in columns_words["TASK_NO"] if _ANCHOR_RE.match(t)
    ]
    if not anchor_tokens:
        return []
    anchor_tokens.sort(key=lambda p: p[0])
    anchors = [top for top, _ in anchor_tokens]
    task_no_values = [t for _, t in anchor_tokens]

    other_cols = [name for _, _, name in _COLUMNS if name != "TASK_NO"]
    buckets: list[dict[str, list[str]]] = [{name: [] for name in other_cols} for _ in anchors]
    for col_name in other_cols:
        for top, text in columns_words[col_name]:
            idx = _nearest_anchor_idx(top, anchors)
            if idx is not None:
                buckets[idx][col_name].append(text)

    rows = []
    for i, task_no in enumerate(task_no_values):
        b = buckets[i]
        description = _join(b["DESCRIPTION"], "DESCRIPTION")
        part_number = _join(b["PART_NUMBER"], "PART_NUMBER")
        serial_number = _join(b["SERIAL_NUMBER"], "SERIAL_NUMBER")
        if not description and not part_number and not serial_number:
            # No real cell content attached to this anchor at all --
            # almost certainly page furniture rather than a genuine data
            # row (see module docstring's row-anchoring section).
            continue
        rows.append({
            "TASK_NO": task_no,
            "DESCRIPTION": description,
            "PART_NUMBER": part_number,
            "SERIAL_NUMBER": serial_number,
            "POSITION": _join(b["POSITION"], "POSITION"),
            "TASK": _join(b["TASK"], "TASK"),
            "INTERVAL_HOURS": _join(b["INTERVAL_HOURS"], "INTERVAL_HOURS"),
            "INTERVAL_CYCLES": _join(b["INTERVAL_CYCLES"], "INTERVAL_CYCLES"),
            "INTERVAL_DAY": _join(b["INTERVAL_DAY"], "INTERVAL_DAY"),
            "CURRENT_TSR": _join(b["CURRENT_TSR"], "CURRENT_TSR"),
            "CURRENT_CSR": _join(b["CURRENT_CSR"], "CURRENT_CSR"),
            "TASK_PERFORMED_DATE": _join(b["TASK_PERFORMED_DATE"], "TASK_PERFORMED_DATE"),
            "TASK_EXPIRE_DATE": _join(b["TASK_EXPIRE_DATE"], "TASK_EXPIRE_DATE"),
            "ACDATA_HOURS": _join(b["ACDATA_HOURS"], "ACDATA_HOURS"),
            "ACDATA_CYCLES": _join(b["ACDATA_CYCLES"], "ACDATA_CYCLES"),
            "ACDATA_DATE": _join(b["ACDATA_DATE"], "ACDATA_DATE"),
            "NEXTDUE_HOURS": _join(b["NEXTDUE_HOURS"], "NEXTDUE_HOURS"),
            "NEXTDUE_CYCLES": _join(b["NEXTDUE_CYCLES"], "NEXTDUE_CYCLES"),
            "NEXTDUE_DATE": _join(b["NEXTDUE_DATE"], "NEXTDUE_DATE"),
            "REMAINING": _join(b["REMAINING"], "REMAINING"),
        })
    return rows


async def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    header_meta = {k: "" for k in _HEADER_FIELDS}
    n_pages = await page_count(pdf_path)
    for page_index in range(n_pages):
        img = await render_page(pdf_path, page_index, dpi=300)
        w, h = img.size

        if not all(header_meta.values()):
            # Left-hand header column only -- see module docstring for why
            # excluding the operator wordmark's own x-range (right side)
            # measurably improves recognition of the neighbouring text.
            crop = img.crop((0, 0, min(w, 1400), _TABLE_TOP_PX))
            header_text = await ocr_text(crop, psm=6)
            _parse_header_text(header_text, header_meta)

        columns_words = {}
        for _, _, col_name in _COLUMNS:
            columns_words[col_name] = await _ocr_column(img, col_name, _TABLE_TOP_PX, h)

        for rec in _extract_page_rows(columns_words):
            rec["_page"] = page_index + 1
            rec.update(header_meta)
            records.append(rec)
    return records
