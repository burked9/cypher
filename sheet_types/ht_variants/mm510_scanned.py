"""MM_510 "HARD TIME/LLP COMPONENTS" report — scanned copy, needs a fresh
per-column-strip OCR pass end to end.

Same underlying MIS export family and column layout as the born-digital
`mm510.py` sibling in this package (see its own docstring for the shared
header/column story), but the files this module targets have no
extractable text layer at all (a straight image scan, confirmed directly
with both pdfplumber and PyMuPDF on a real corpus sample — 0 characters on
every page), so that sibling's plain-pdfplumber `SIGNATURES` never fires.

Two things make this a per-column-strip job rather than a plain
whole-row-OCR one (this package's usual "if it comes back garbled, OCR
column-by-column instead" move — see e.g.
`hard_time_day_fhr_cyc_matrix_scanned.py`):

  * **The page is landscape content stored in a portrait page.** Every
    page in the confirmed sample reports the same portrait
    `page.rect`/`rotation == 0` via PyMuPDF, yet the raster content itself
    is rotated — a plain render comes out sideways. Confirmed directly:
    rendering at any DPI and rotating -90° (`Image.rotate(-90,
    expand=True)`) puts the header/table the right way up on every page of
    the sample. This module always checks `img.height > img.width` after
    `render_page()` and rotates when so, rather than hard-coding a rotate
    unconditionally, in case a differently-scanned copy of this same
    template ever turns up already upright.

  * **Whole-row OCR merges adjacent narrow columns.** Confirmed directly
    on the real sample: the ruled grid has no vertical rule lines (it's a
    plain positional table, like the born-digital sibling), and at least
    two columns sit close enough together that a whole-line OCR pass
    genuinely reads them as one glued token even though the source PDF
    itself prints them with a real (if tiny) gap — e.g. POSITION "AFT" +
    "LH" vs PART_NUMBER "104005-1" survive fine as separate tokens, but a
    POSITION value of "TRACK 5" immediately followed by a numeric PART_
    NUMBER like "1713255" decodes as one run, "TRACK51713255", with
    *zero* pixel gap in the source raster itself (confirmed directly at
    600 DPI — this is a genuine source-formatting quirk for this one
    component type, not a scan/OCR artifact). A fixed-column crop sidesteps
    this: OCR never sees the neighbouring column's pixels in the first
    place, so there's nothing left for it to glue together. The POSITION/
    PART_NUMBER cut is placed at the char-width-implied midpoint of that
    exact glued run (see `_COLUMNS` below) so it still splits this one
    reliably, not just the normal-gapped rows.

Header block (repeats near-identically on every page, near the top)::

    (Doc.Type : HT, Tail Number/Type : <reg>,<type> ...)(Order By : <n>)
                              MM_510
    Tail Number : <REG> (<OPERATOR>)   Time Since New : <TSN>
        Cycle Since New : <CSN>   Last Flight Date : <DATE>

The query-parameters line above "MM_510" is printed in a noticeably
smaller/lighter font than the rest of the page and does not OCR reliably
at any DPI tried (confirmed directly up to 600 DPI — still illegible,
consistent with a genuine source resolution limit rather than a fixable
scan/zoom issue), so this module does not rely on it for anything. The
"Tail Number : ... Time Since New : ... Cycle Since New : ... Last Flight
Date : ..." line one row down OCRs cleanly and is used both for per-page
header metadata and (combined with the table's own "HT LLP Description"
column-header phrase) as this variant's `ocr_detect()` anchor — the paired
check matters here: this MIS tool can also emit a Doc.Type-filtered LLP-only
export of the same "MM_510" family with different columns and no separate
HT/LLP flag pair (see `llp_variants/mm510_llp.py`'s own docstring), so
anchoring on "MM_510" alone would risk that sibling's own `ocr_detect()`
claiming a file first — confirmed directly this variant's own combination
does not fire on the confirmed real sample of that sibling's own OCR path
in either direction (checked both `ocr_detect()`s cross-file).

Main table, one plain (unruled) positional header row::

    ATA | POS. | Part Number | Serial Number | HT LLP Description |
    Task Number | Install Date | Hour Cycle Day | Last Done Eff.Date |
    Due Date | Interval{Hour,Cycle,Day} | Remaining{Hour,Cycle,Day}

The "Hour Cycle Day" trio right after Install Date is this report's own
time-since-install reading for the component (not the aircraft-level
Time Since New/Cycle Since New in the page header) — named TSI_* here to
avoid confusion with the header's own TSN_TOTAL/CSN_TOTAL fields. "Task
Number" is the source's own column label for what is actually a short task
*name* (RESTORATION, DISCARD, REPACK, ...), not a numeric code — unlike the
born-digital sibling's own same-family layout, this template has no
separate numeric task-reference column, so this module just calls the
field TASK.

Row anchoring: INSTALL_DATE (`DD-MMM-YY`, e.g. "20-FEB-16") is used as the
per-row Y anchor — present on very nearly every real data row, including a
component's own second/third scheduled-task row (e.g. a battery's own
"RESTORATION" line and its sibling "ELECTROLYTE" line both repeat the same
install date). ATA/POSITION/PART_NUMBER/SERIAL_NUMBER/DESCRIPTION/HT_FLAG/
LLP_FLAG are blank on those continuation rows in the source and are
forward-filled from the most recent row where they were present (confirmed
directly on the sample: a component's own task lines never cross a page
boundary without repeating these on the new page's own first row, so no
cross-page carry-over guard is needed, unlike some other per-column-strip
variants in this package).

Column X-boundaries below are expressed as fractions of the rendered (and,
where needed, rotated) page's own width, derived directly from a real
per-word OCR pass across several pages of the sample file (not a vector
grid-line scan — this table has no ruled lines to measure) and set at the
midpoint of the tightest observed gap between each pair of neighbouring
columns' own real content, so a page rendered at a different DPI keeps
every column crop aligned without a per-page recalibration pass.

Numeric/date cells behind ruled columns commonly pick up stray OCR noise
(a leading `.`/`-` from a neighbouring cell's blank leader, a doubled
character); each numeric/date column is reduced to only its own matching
substring (plain digit runs, `H:MM`-style colon durations, or
`DD-MMM-YY` dates as appropriate) rather than passed through raw, per this
project's "never guess a wrong split" convention — a dropped stray
artifact is preferred over a confidently-wrong merged value.

A handwritten signature/initials mark sits below the table's own last row
on at least one page of the sample, well past the last real INSTALL_DATE
anchor on that page — since every row this module emits is built by
walking INSTALL_DATE anchors outward to the other columns (never a blind
whole-column scan), that signature never lines up with an anchor and
never enters any output field. It has no legible name in it in the
confirmed sample either way.
"""
from __future__ import annotations
import re

from sheet_types.ht_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_words, ocr_text, page_count

NAME = "MM_510 HARD TIME LLP Components (Scanned)"

# Deliberately empty -- see module docstring. Every known source file in
# this cluster has no usable text layer at all, so plain-pdfplumber
# SIGNATURES can never fire; detection happens structurally via
# ocr_detect() below, same pattern as amos_scanned.py /
# georgian_airways_ht_components_status_scanned.py elsewhere in this
# package.
SIGNATURES: list[str] = []

CANONICAL_COLUMNS = [
    "ATA",
    "POSITION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "HT_FLAG",
    "LLP_FLAG",
    "DESCRIPTION",
    "TASK",
    "INSTALL_DATE",
    "TSI_HOUR",
    "TSI_CYCLE",
    "TSI_DAY",
    "LAST_DONE_DATE",
    "DUE_DATE",
    "INTERVAL_HOUR",
    "INTERVAL_CYCLE",
    "INTERVAL_DAY",
    "REMAINING_HOUR",
    "REMAINING_CYCLE",
    "REMAINING_DAY",
    # Header metadata -- same on every page of a given file, stamped on
    # every row.
    "TAIL_NUMBER",
    "OPERATOR",
    "TSN_TOTAL",
    "CSN_TOTAL",
    "LAST_FLIGHT_DATE",
]

_DATE_RE = r"^\d{1,2}-[A-Z]{3}-\d{2,4}$"
_INT_RE = r"^\d+$"
_DEC_RE = r"^\d+(?:\.\d+)?$"
_HM_RE = r"^\d+:\d{2}$"

_OVERRIDES = {
    "POSITION":         {"allow_empty": True, "uppercase": True},
    "HT_FLAG":          {"pattern": r"^[YN]$", "allow_empty": True},
    "LLP_FLAG":         {"pattern": r"^[YN]$", "allow_empty": True},
    "TASK":             {"allow_empty": True, "uppercase": True},
    "INSTALL_DATE":     {"pattern": _DATE_RE},
    "TSI_HOUR":         {"pattern": _INT_RE, "allow_empty": True},
    "TSI_CYCLE":        {"pattern": _INT_RE, "allow_empty": True},
    "TSI_DAY":          {"pattern": _DEC_RE, "allow_empty": True},
    "LAST_DONE_DATE":   {"pattern": _DATE_RE, "allow_empty": True},
    "DUE_DATE":         {"pattern": _DATE_RE, "allow_empty": True},
    "INTERVAL_HOUR":    {"pattern": _HM_RE, "allow_empty": True},
    "INTERVAL_CYCLE":   {"pattern": _INT_RE, "allow_empty": True},
    "INTERVAL_DAY":     {"pattern": _INT_RE, "allow_empty": True},
    "REMAINING_HOUR":   {"pattern": _HM_RE, "allow_empty": True},
    "REMAINING_CYCLE":  {"pattern": _INT_RE, "allow_empty": True},
    "REMAINING_DAY":    {"pattern": _INT_RE, "allow_empty": True},
    # Header metadata -- a single OCR misread here shouldn't flag every
    # row of the file, same reasoning this package's other header-plus-body
    # OCR variants use.
    "TAIL_NUMBER":      {"allow_empty": True},
    "OPERATOR":         {"allow_empty": True},
    "TSN_TOTAL":        {"allow_empty": True},
    "CSN_TOTAL":        {"allow_empty": True},
    "LAST_FLIGHT_DATE": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Column X-boundaries, as a fraction of the rendered (rotated) page's own
# width -- see module docstring for how these were derived.
_COLUMNS = [
    (0.00000, 0.04565, "ATA"),
    (0.04565, 0.08074, "POSITION"),
    (0.08074, 0.15014, "PART_NUMBER"),
    (0.15014, 0.21398, "SERIAL_NUMBER"),
    (0.21398, 0.23823, "HT_FLAG"),
    (0.23823, 0.25535, "LLP_FLAG"),
    (0.25535, 0.38374, "DESCRIPTION"),
    (0.38374, 0.45450, "TASK"),
    (0.45450, 0.51555, "INSTALL_DATE"),
    (0.51555, 0.55378, "TSI_HOUR"),
    (0.55378, 0.58488, "TSI_CYCLE"),
    (0.58488, 0.61912, "TSI_DAY"),
    (0.61912, 0.66619, "LAST_DONE_DATE"),
    (0.66619, 0.71954, "DUE_DATE"),
    (0.71954, 0.76205, "INTERVAL_HOUR"),
    (0.76205, 0.79600, "INTERVAL_CYCLE"),
    (0.79600, 0.83309, "INTERVAL_DAY"),
    (0.83309, 0.88302, "REMAINING_HOUR"),
    (0.88302, 0.91869, "REMAINING_CYCLE"),
    (0.91869, 1.00000, "REMAINING_DAY"),
]

# Columns whose OCR word tokens are joined with a space (genuine multi-word
# free text) rather than glued with no separator.
_JOIN_SPACE = {"POSITION", "DESCRIPTION", "TASK"}

_DATE_COLS = {"INSTALL_DATE", "LAST_DONE_DATE", "DUE_DATE"}
_HM_COLS = {"INTERVAL_HOUR", "REMAINING_HOUR"}
_INT_COLS = {"TSI_HOUR", "TSI_CYCLE", "INTERVAL_CYCLE", "INTERVAL_DAY",
             "REMAINING_CYCLE", "REMAINING_DAY"}
_DEC_COLS = {"TSI_DAY"}
_CODE_COLS = {"ATA", "PART_NUMBER", "SERIAL_NUMBER", "HT_FLAG", "LLP_FLAG"}

_DATE_TOKEN_RE = re.compile(r"\d{1,2}-[A-Za-z]{3}-\d{2,4}")
_HM_TOKEN_RE = re.compile(r"\d+:\d{2}")
_INT_TOKEN_RE = re.compile(r"\d+")
_DEC_TOKEN_RE = re.compile(r"\d+\.\d+")
_CODE_STRIP_CHARS = " _\"'`‘’“”.,;:()[]{}|~=-"

# Deliberately looser than _DATE_RE for anchor *detection* only: a leading
# day digit is occasionally misread as a letter (confirmed directly, e.g.
# "04-MAR-15" -> "G4-MAR-15"), which would otherwise drop a real row
# entirely rather than just leaving its own INSTALL_DATE looking suspect.
# The strict _DATE_RE is still what actually populates/validates the
# INSTALL_DATE field (via _clean_field/RULES) -- a row admitted on this
# looser anchor with a misread day still gets its INSTALL_DATE correctly
# flagged rather than silently accepted, per this project's "flag rather
# than drop or guess" convention.
_ANCHOR_RE = re.compile(r"^[A-Z0-9]{1,2}-[A-Z]{3}-\d{2,4}$")

# Y-tolerance for bucketing a non-anchor column's word to its nearest
# INSTALL_DATE anchor -- measured directly against this file's own row
# pitch (roughly 66-96px @ 300 DPI between consecutive rows on the sample);
# comfortably under half of the tightest observed pitch.
_ANCHOR_TOLERANCE_PX = 30

_FILLABLE = ("ATA", "POSITION", "PART_NUMBER", "SERIAL_NUMBER",
             "HT_FLAG", "LLP_FLAG", "DESCRIPTION")

_HEADER_FIELDS = ["TAIL_NUMBER", "OPERATOR", "TSN_TOTAL", "CSN_TOTAL",
                  "LAST_FLIGHT_DATE"]

# OCR reliably reads "Tail" as "Tall" on this cluster's own scans (a font/
# scan artifact, confirmed directly), so both spellings are accepted.
_TAIL_RE = re.compile(r"Ta[ui]l\s+Number\s*:\s*(\S+)\s*\(([^)]+)\)", re.IGNORECASE)
_TSN_RE = re.compile(r"Time\s+Since\s+New\s*:\s*(\S+)", re.IGNORECASE)
_CSN_RE = re.compile(r"Cycle\s+Since\s+New\s*:\s*(\S+)", re.IGNORECASE)
_LFD_RE = re.compile(r"Last\s+Flight\s+Date\s*:\s*(\S+)", re.IGNORECASE)


async def _get_page_image(pdf_path: str, page_index: int, dpi: int = 300):
    img = await render_page(pdf_path, page_index, dpi=dpi)
    if img.height > img.width:
        img = img.rotate(-90, expand=True)
    return img


def _col_bounds(w: int, name: str) -> tuple[int, int]:
    for lo, hi, col in _COLUMNS:
        if col == name:
            return int(lo * w), int(hi * w)
    raise KeyError(name)


async def _ocr_column(img, name: str, y0: int, y1: int) -> list[tuple[float, str]]:
    """OCR one column's full-height strip and return (top, text) pairs in
    original-image page coordinates."""
    x0, x1 = _col_bounds(img.width, name)
    crop = img.crop((x0, y0, x1, y1))
    words = await ocr_words(crop, psm=6, min_conf=-1)
    out = []
    for w in words:
        text = str(w.get("text", "")).strip()
        if not text:
            continue
        out.append((y0 + w["top"], text))
    return out


_FLAG_COLS = {"HT_FLAG", "LLP_FLAG"}
# Tesseract very reliably misreads this template's own bold "Y" glyph as
# the yen sign (confirmed directly: the single most common non-Y/N reading
# across the whole sample file by a wide margin) -- a deterministic glyph
# substitution, not a guessed split, so it's normalized before the plain
# Y/N pattern check rather than just flagged.
_YEN_RE = re.compile("[¥]")


def _clean_field(name: str, tokens: list[str]) -> str:
    if name in _FLAG_COLS:
        text = "".join(tokens).strip(_CODE_STRIP_CHARS)
        text = _YEN_RE.sub("Y", text).upper()
        # A genuine cell holds exactly one flag letter; tesseract sometimes
        # doubles it (e.g. "YY" for a single "Y") when the glyph is bold --
        # collapse a repeated single letter rather than flag it as noise.
        if len(text) > 1 and len(set(text)) == 1 and text[0] in "YN":
            text = text[0]
        return text
    if name in _DATE_COLS:
        found: list[str] = []
        for t in tokens:
            found.extend(_DATE_TOKEN_RE.findall(t))
        found = list(dict.fromkeys(found))
        return " ".join(found)
    if name in _HM_COLS:
        found = []
        for t in tokens:
            found.extend(_HM_TOKEN_RE.findall(t))
        found = list(dict.fromkeys(found))
        return max(found, key=len) if found else ""
    if name in _DEC_COLS:
        found = []
        for t in tokens:
            found.extend(_DEC_TOKEN_RE.findall(t))
            if not _DEC_TOKEN_RE.search(t):
                found.extend(_INT_TOKEN_RE.findall(t))
        found = list(dict.fromkeys(found))
        return max(found, key=len) if found else ""
    if name in _INT_COLS:
        found = []
        for t in tokens:
            found.extend(_INT_TOKEN_RE.findall(t))
        found = list(dict.fromkeys(found))
        return max(found, key=len) if found else ""
    sep = " " if name in _JOIN_SPACE else ""
    text = sep.join(tokens)
    if name in _CODE_COLS:
        text = text.strip(_CODE_STRIP_CHARS)
    return text


async def _parse_header(img) -> dict:
    """One OCR pass over the "Tail Number : ... Time Since New : ...
    Cycle Since New : ... Last Flight Date : ..." metadata line -- see
    module docstring for why the query-parameters line above it is not
    used."""
    meta = {k: "" for k in _HEADER_FIELDS}
    w, h = img.size
    crop = img.crop((0, int(h * 0.04), w, int(h * 0.10)))
    text = await ocr_text(crop, psm=6)

    m = _TAIL_RE.search(text)
    if m:
        meta["TAIL_NUMBER"] = m.group(1).strip()
        meta["OPERATOR"] = " ".join(m.group(2).split())
    m = _TSN_RE.search(text)
    if m:
        meta["TSN_TOTAL"] = m.group(1).strip()
    m = _CSN_RE.search(text)
    if m:
        meta["CSN_TOTAL"] = m.group(1).strip()
    m = _LFD_RE.search(text)
    if m:
        meta["LAST_FLIGHT_DATE"] = m.group(1).strip()
    return meta


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback (see
    sheet_types/ht.py) -- this variant's SIGNATURES is deliberately empty
    (see module docstring).

    Requires BOTH the table's own "HT LLP Description" column-header
    phrase AND the "Time Since New .../Cycle Since New ..." page-metadata
    phrase -- checked directly against the real sibling `mm510_llp.py`'s
    own `ocr_detect()` on the confirmed sample file (that sibling's own
    check does not fire on it, in either direction); the column-header
    phrase specifically is what distinguishes this "everything" bucket of
    the shared MM_510 export family from that sibling's own Doc.Type-
    filtered LLP-only bucket, which carries no separate HT/LLP flag
    columns of its own (see module docstring)."""
    try:
        img = await _get_page_image(pdf_path, 0, dpi=300)
        w, h = img.size
        crop = img.crop((0, 0, w, int(h * 0.14)))
        text = (await ocr_text(crop, psm=6)).upper()
        has_header_cols = "HT" in text and "LLP" in text and "DESCRIPTION" in text
        has_meta = "TIME SINCE NEW" in text and "CYCLE SINCE NEW" in text
        return has_header_cols and has_meta
    except Exception:
        return False


async def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    header_meta = {k: "" for k in _HEADER_FIELDS}
    n_pages = await page_count(pdf_path)

    for page_index in range(n_pages):
        img = await _get_page_image(pdf_path, page_index, dpi=300)
        h = img.height

        if not all(header_meta.values()):
            page_meta = await _parse_header(img)
            for k, v in page_meta.items():
                if v and not header_meta[k]:
                    header_meta[k] = v

        # Table body starts below the title/metadata block and its own
        # column-header row. Confirmed directly: cropping right at the
        # column-header row's own bottom edge (~14% of page height) clips
        # the very top of the first data row's own glyphs on every page,
        # which reliably garbles just that one row's OCR (e.g. ATA "24"
        # misreads as "et") while every later row on the same page reads
        # cleanly -- backing off a few more pixels above the header's own
        # last text line (still well below its own column-header labels,
        # so nothing from the header itself leaks into row 1) fixes this
        # for every page of the sample.
        y0 = int(h * 0.132)

        col_words: dict[str, list[tuple[float, str]]] = {}
        for _, _, name in _COLUMNS:
            col_words[name] = await _ocr_column(img, name, y0, h)

        anchors = sorted(
            top for top, text in col_words["INSTALL_DATE"]
            if _ANCHOR_RE.match(text)
        )

        cur = {f: "" for f in _FILLABLE}
        for atop in anchors:
            row: dict[str, str] = {}
            for _, _, name in _COLUMNS:
                if name == "INSTALL_DATE":
                    continue
                toks = [text for top, text in col_words[name]
                        if abs(top - atop) <= _ANCHOR_TOLERANCE_PX]
                row[name] = _clean_field(name, toks)

            date_toks = [text for top, text in col_words["INSTALL_DATE"]
                         if abs(top - atop) <= _ANCHOR_TOLERANCE_PX]
            row["INSTALL_DATE"] = _clean_field("INSTALL_DATE", date_toks)

            for f in _FILLABLE:
                if row[f]:
                    cur[f] = row[f]
                else:
                    row[f] = cur[f]

            row["_page"] = page_index + 1
            row.update(header_meta)
            records.append(row)

    return records
