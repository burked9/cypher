"""ON-CONDITION MONITORED COMPONENTS LIST -- scanned/no text layer, per-engine
component listing organized under repeated "CHAPTER <n> - <description>"
section headings, OCR required throughout.

Confirmed directly on a real corpus file (16 pages total via `page_count()`,
0 extractable chars on every page via pdfplumber -- a straight scan). Only
the FIRST 12 pages of that file belong to this report; the remaining pages
are a completely different, unrelated attached document (a distinct
"LRU Component Inventory" listing from a different source system entirely,
confirmed directly by its own title block, which shares nothing with this
module's own title/column layout). This module stops consuming pages the
moment a page's own title block no longer matches this report's title
anchor (see `ocr_detect()`/`_TITLE_RE` below), rather than assuming every
page of a source file belongs to the same template -- a real risk this
project has hit before when multiple reports are concatenated into one PDF.

Header block, confirmed directly, reprints (title line only; the aircraft/
engine metadata line is confirmed present only on the report's own first
page, not on continuation pages)::

    <maintenance org name>
    ON-CONDITION MONITORED COMPONENTS LIST - <LH or RH> ENGINE
    <reg> <type> <msn> TSN: <n> CSN: <n> DATE: <date>
    <LH or RH> ENGINE <engine type> SNo.: <esn> TSN: <n> CSN: <n>

Per this project's data-sensitivity convention, no real organization name,
registration, aircraft type, MSN, TSN/CSN figure, engine type, or engine
serial number is reproduced anywhere in this module -- every value below is
a placeholder token (`<reg>`, `<type>`, `<msn>`, `<esn>`, etc.), confirmed
by re-reading this file line by line against the real sample file's own
content before finishing it.

Column header row (confirmed directly, two physical header lines, heavily
grid-ruled)::

    <ITEM> | COMPONENT DESCRIPTION | COMPONENT DATA | ... | ORIGINAL
    INSTALATION | FORM NECESSARY? | FORM AVAILABLE? | REMARKS
    ... | PART NUMBER | MODEL | MODIF | SERIAL NUMBER | POSITION |
    TSN/TSI/CSN/CSI-shaped group | COMPONENT NECESSARY? (Y OR N) | DATE |
    ENG EH | ENG EC | (Y OR N) | (Y OR N)

Column x-boundaries (px @ 300dpi) below are measured directly from the real
rendered page's own ruled vertical-line pixel columns (grid-line detection
over the data-grid's Y-span), confirmed stable (a few px of jitter, well
inside each column's own width) across the first, several middle, and last
pages of the real sample file's own 12-page report section.

The narrow leading item-number column is confirmed to OCR as pure noise at
every DPI/PSM tried directly against the real file (no legible digit ever
recovered) -- it is not extracted as its own column (no CANONICAL_COLUMNS
entry forces a value that can never be trusted). PART_NUMBER is used as the
per-row anchor instead (same "pick the column that OCRs reliably" principle
as `occm_variants/msn_occm_list_scanned.py`'s own ATA-anchor approach):
confirmed directly that PART_NUMBER OCRs at high confidence (85-90) on
essentially every real row, in contrast to the item-number column's total
noise and the free-text DESCRIPTION column's own occasional low-confidence
words.

The two rightmost sub-header groups covering component TSN/TSI/CSN/CSI (the
"COMPONENT DATA"/"TSO CSO"-labelled block ahead of the Y/N "COMPONENT
NECESSARY?" column) render with confirmed self-contradictory labels across
the two header lines (one line reads "TSO ... CSO ...", the line below it
reads "TSN TSI CSN CSI" over the same four sub-columns) -- genuinely
ambiguous which figure is which even before OCR noise is considered, and a
real data row is confirmed to sometimes carry the literal word "NEW" in
this same group (a newly-installed component with no elapsed time/cycles
yet) rather than a number. Per this project's "never guess a wrong split"
convention, these four sub-columns are folded into one raw STATUS_TRAIL
field (space-joined, unparsed) rather than forced into four separately-
named, individually mis-labelled fields.

CHAPTER is confirmed to print only on its own full-width "CHAPTER <n> -
<description>" section-heading line (not per data row) and is forward-
filled onto every row beneath it, matching this project's established
chapter-organized-report convention (e.g. `occm_status_by_ata_chapter.py`'s
own ATA_CHAPTER handling). The heading line is detected via a dedicated
full-width OCR pass per page (the whole-page/whole-row-width OCR pass used
for chapter detection is confirmed to render this large, sparse heading
text cleanly, unlike the dense data grid itself, which needs the per-column
strip technique below).

Header metadata (aircraft reg/type/MSN/TSN/CSN/date, engine side/type/
serial/TSN/CSN) is parsed once from the first data page's own metadata line
and stamped onto every row, mirroring this project's established header-
plus-body OCCM convention (e.g. `msn_occm_list_scanned.py`'s own header
handling). Each header field's own validation rule is `allow_empty` rather
than pattern-enforced (same reasoning as that module's header fields): a
single stamped value that fails a tight pattern would otherwise flag every
row in the file over one OCR misread in one place, which is not a useful
per-row signal -- genuine per-row corruption is still caught by the row-
level rules.
"""
from __future__ import annotations
import re

from PIL import Image

from sheet_types.occm_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, ocr_words, page_count

NAME = "On-Condition Monitored Components List (Engine, Scanned)"

# This module's known source file has no text layer at all (confirmed via
# pdfplumber -- 0 chars on every page of its own report section), so these
# SIGNATURES can never fire through occm.py's normal pdfplumber head-text
# match; real detection happens via ocr_detect() below. Deliberately left
# empty, same convention as this package's other purely-OCR variants (e.g.
# `msn_occm_list_scanned.py`, `occm_list_func_loc_scanned.py`). Per this
# project's data-sensitivity convention, the real maintenance organization
# name seen on the real sample file is never written here (or anywhere else
# in this module) -- only the generic report-title phrase is used as an
# anchor.
SIGNATURES = []

CANONICAL_COLUMNS = [
    "CHAPTER",
    "DESCRIPTION",
    "PART_NUMBER",
    "MODEL",
    "MODIF",
    "SERIAL_NUMBER",
    "POSITION",
    "STATUS_TRAIL",
    "COMPONENT_NECESSARY",
    "INSTALL_DATE",
    "ENGINE_HOURS_AT_INSTALL",
    "ENGINE_CYCLES_AT_INSTALL",
    "FORM_NECESSARY",
    "FORM_AVAILABLE",
    "REMARKS",
    # Header metadata, parsed once (first data page) and stamped on every row.
    "AIRCRAFT_REG",
    "AIRCRAFT_TYPE",
    "MSN",
    "AIRCRAFT_TSN",
    "AIRCRAFT_CSN",
    "REPORT_DATE",
    "ENGINE_SIDE",
    "ENGINE_TYPE",
    "ENGINE_SERIAL_NUMBER",
    "ENGINE_TSN",
    "ENGINE_CSN",
]

_HEADER_FIELDS = [
    "AIRCRAFT_REG", "AIRCRAFT_TYPE", "MSN", "AIRCRAFT_TSN", "AIRCRAFT_CSN",
    "REPORT_DATE", "ENGINE_SIDE", "ENGINE_TYPE", "ENGINE_SERIAL_NUMBER",
    "ENGINE_TSN", "ENGINE_CSN",
]

_OVERRIDES = {
    "CHAPTER": {"pattern": r"^CHAPTER\s+\d+\b.*$", "uppercase": True, "allow_empty": True},
    "MODEL": {"allow_empty": True},
    "MODIF": {"allow_empty": True},
    "POSITION": {"allow_empty": True},
    # Genuinely ambiguous grouped raw text (see module docstring) -- kept
    # loose rather than pattern-enforced.
    "STATUS_TRAIL": {"allow_empty": True},
    "COMPONENT_NECESSARY": {"pattern": r"^[YN]$", "uppercase": True, "allow_empty": True},
    "INSTALL_DATE": {"pattern": r"^\d{1,2}-[A-Za-z]{3}-\d{2,4}$", "allow_empty": True},
    "ENGINE_HOURS_AT_INSTALL": {"pattern": r"^[\d.,]+$", "allow_empty": True},
    "ENGINE_CYCLES_AT_INSTALL": {"pattern": r"^\d+$", "allow_empty": True},
    "FORM_NECESSARY": {"pattern": r"^[YN]$", "uppercase": True, "allow_empty": True},
    "FORM_AVAILABLE": {"pattern": r"^[YN]$", "uppercase": True, "allow_empty": True},
    "REMARKS": {"allow_empty": True},
    # Header metadata -- each value is a single figure parsed once and
    # stamped identically on every row of the file (see module docstring on
    # why these are `allow_empty` rather than pattern-enforced).
    "AIRCRAFT_REG": {"allow_empty": True},
    "AIRCRAFT_TYPE": {"allow_empty": True},
    "MSN": {"allow_empty": True},
    "AIRCRAFT_TSN": {"allow_empty": True},
    "AIRCRAFT_CSN": {"allow_empty": True},
    "REPORT_DATE": {"allow_empty": True},
    "ENGINE_SIDE": {"pattern": r"^(LH|RH)$", "uppercase": True, "allow_empty": True},
    "ENGINE_TYPE": {"allow_empty": True},
    "ENGINE_SERIAL_NUMBER": {"allow_empty": True},
    "ENGINE_TSN": {"allow_empty": True},
    "ENGINE_CSN": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Column x-boundaries (px @ 300dpi), measured directly from the real
# rendered page's own ruled vertical-line pixel columns -- confirmed stable
# across the first, several middle, and last pages of the real sample
# file's own report section (see module docstring). The leading item-number
# column (roughly 109-181px) is deliberately excluded -- confirmed pure OCR
# noise, never extracted (see module docstring).
_COLUMNS = [
    (181, 768, "DESCRIPTION"),
    (768, 1091, "PART_NUMBER"),
    (1091, 1251, "MODEL"),
    (1251, 1381, "MODIF"),
    (1381, 1594, "SERIAL_NUMBER"),
    (1594, 1756, "POSITION"),
    # Folds the four ambiguous TSN/TSI/CSN/CSI-labelled sub-columns into one
    # raw strip (see module docstring).
    (1756, 2282, "STATUS_TRAIL"),
    (2282, 2465, "COMPONENT_NECESSARY"),
    (2465, 2581, "INSTALL_DATE"),
    (2581, 2714, "ENGINE_HOURS_AT_INSTALL"),
    (2714, 2845, "ENGINE_CYCLES_AT_INSTALL"),
    (2845, 3029, "FORM_NECESSARY"),
    (3029, 3217, "FORM_AVAILABLE"),
    (3217, 3430, "REMARKS"),
]
_FIELD_NAMES = [name for _, _, name in _COLUMNS]
# Compact codes with no legitimate internal space -- joined with no
# separator. DESCRIPTION and STATUS_TRAIL are the only columns joined with
# spaces (genuine free text / a raw multi-token group respectively).
_JOIN_NOSPACE = {
    "PART_NUMBER", "MODEL", "MODIF", "SERIAL_NUMBER", "POSITION",
    "COMPONENT_NECESSARY", "INSTALL_DATE", "ENGINE_HOURS_AT_INSTALL",
    "ENGINE_CYCLES_AT_INSTALL", "FORM_NECESSARY", "FORM_AVAILABLE", "REMARKS",
}

# Stray ruled-border artifacts occasionally picked up as their own word box
# -- dropped before a row's tokens are joined.
_NOISE_TOKEN_RE = re.compile(r"^[|\[\]_\-—–.,]+$")

# Row anchor: PART_NUMBER OCRs reliably on this file (see module docstring)
# -- an alphanumeric token of realistic PN length, with at least one digit,
# distinguishes a real PN from stray punctuation/noise tokens without
# assuming any particular PN shape (this file's own PNs mix pure-digit-dash
# and alnum-with-letter-run shapes).
_PN_TOKEN_RE = re.compile(r"^(?=[A-Z0-9\-]{5,20}$)(?=.*\d)[A-Z0-9\-]+$")

# Y-tolerance for assigning a non-anchor column's word to its nearest
# PART_NUMBER anchor -- measured directly against the real sample file's own
# row pitch (~62-63px @ 300dpi between consecutive rows); comfortably below
# half that.
_ANCHOR_TOLERANCE_PX = 28

# Title anchor: the report's own generic title phrase (no organization name
# -- see module docstring). Checked directly against every SIGNATURES/
# ocr_detect anchor in sheet_types/{occm,ht,llp}.py and every existing
# occm_variants file: the phrase appears nowhere else.
_TITLE_RE = re.compile(
    r"ON.CONDITION\s+MONITORED\s+COMPONENTS\s+LIST\s*-?\s*(LH|RH)\s+ENGINE",
    re.IGNORECASE,
)

_CHAPTER_RE = re.compile(r"CHAPTER\s+\d+\s*-\s*.+", re.IGNORECASE)

# Aircraft metadata line: <reg> <type (may contain spaces/hyphens)> <msn>
# TSN: <n> CSN: <n> DATE: <date>. TYPE is free-form between REG and the
# long MSN digit run, so it is captured non-greedily rather than assumed to
# be a single token (confirmed directly the real sample file's own type
# designation contains an internal space).
_AC_META_RE = re.compile(
    r"(?P<reg>[A-Z][A-Z0-9\-]{3,10})\s+(?P<type>.+?)\s+(?P<msn>\d{5,10})\s+"
    r"TSN:?\s*(?P<tsn>[\d.,]+)\s+CSN:?\s*(?P<csn>\d+)\s+DATE:?\s*(?P<date>\S+)",
    re.IGNORECASE,
)
_ENGINE_META_RE = re.compile(
    r"(?P<side>LH|RH)\s+ENGINE\s+(?P<type>\S+)\s+S\s*No\.?:?\s*(?P<esn>\d+)\s+"
    r"TSN:?\s*(?P<tsn>[\d.,]+)\s+CSN:?\s*(?P<csn>\d+)",
    re.IGNORECASE,
)


def _col_bounds(name: str) -> tuple[int, int]:
    for lo, hi, col in _COLUMNS:
        if col == name:
            return lo, hi
    raise KeyError(name)


async def _ocr_column(img, name: str, y0: int, y1: int, scale: int = 2) -> list[tuple[float, str]]:
    """OCR one column's full-height strip and return (top, text) pairs in
    original-image page coordinates -- same column-strip technique as
    `msn_occm_list_scanned.py` (confirmed directly this file's own dense,
    heavily-ruled grid needs the same per-column approach; a whole-row or
    whole-page OCR pass comes back badly corrupted on the data grid).

    Pulled a few px INSIDE each measured ruled boundary rather than flush
    against it -- confirmed directly that a crop edge landing ON (or past)
    this file's own narrow Y/N and date-cell ruled borders otherwise lets a
    neighboring column's text bleed in (observed directly: a chunk of the
    adjacent INSTALL_DATE cell's digits appearing fused onto the same row's
    COMPONENT_NECESSARY value with no separator), the same "pull inward off
    the border" fix that module's own column crops use."""
    lo, hi = _col_bounds(name)
    inset = 6
    x0 = max(0, int(lo) + inset)
    x1 = min(img.width, int(hi) - inset)
    crop = img.crop((x0, y0, x1, y1))
    if scale != 1:
        crop = crop.resize((crop.width * scale, crop.height * scale), Image.LANCZOS)
    words = await ocr_words(crop, psm=6, min_conf=-1)
    out = []
    for w in words:
        text = str(w.get("text", "")).strip()
        if not text or _NOISE_TOKEN_RE.match(text):
            continue
        out.append((y0 + w["top"] / scale, text))
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
    sep = "" if col_name in _JOIN_NOSPACE else " "
    return sep.join(tokens).strip(" |[]_-—–")


async def _detect_chapters(img, y0: int, y1: int) -> list[tuple[float, str]]:
    """Full-width OCR pass to find "CHAPTER <n> - <description>" section-
    heading lines and their Y position -- these render as large, sparse
    text spanning from the item-number column through the DESCRIPTION
    column, distinguishable from the dense per-cell grid around them.

    Confirmed directly that a single whole-column-height OCR pass (like the
    per-data-column strips above) reliably finds only the FIRST heading on
    a page and silently misses any later one -- the tall crop's many ruled
    lines defeat `--psm 6`'s "uniform block" layout assumption partway down
    (confirmed by testing progressively shorter crop heights directly: a
    single ~150px-tall band spanning a couple of table rows OCRs every
    heading inside it cleanly, while a ~2000px whole-page-height crop
    starting at the identical Y OCRs only its first ~60px reliably). So
    this scans the page in short, overlapping horizontal bands instead (the
    overlap guards against a heading line landing exactly on a band
    boundary and being clipped) -- more OCR calls per page, but each is
    small/cheap and this is only run once per page, not per column.

    A conf>=30 floor (this project's normal `ocr_words()` default, restored
    here explicitly since the per-column data strips above intentionally
    disable it) drops the low-confidence noise words that otherwise bleed
    in from the unreliable item-number column and adjacent data rows."""
    w = img.width
    band_h, stride = 150, 100
    out: list[tuple[float, str]] = []
    seen_tops: set[int] = set()
    y = y0
    while y < y1:
        y2 = min(y1, y + band_h)
        crop = img.crop((0, y, w, y2))
        words = await ocr_words(crop, psm=6, min_conf=30)
        lines: dict[int, list[tuple[float, str]]] = {}
        for wd in words:
            key = int(wd["top"]) // 20
            lines.setdefault(key, []).append((wd["left"], wd["text"]))
        for key, toks in lines.items():
            toks.sort(key=lambda t: t[0])
            text = " ".join(t for _, t in toks)
            m = _CHAPTER_RE.search(text.upper())
            if m:
                top = y + key * 20
                # De-dupe near-identical hits from overlapping bands (same
                # heading line caught by two consecutive windows).
                if not any(abs(top - t) < 20 for t in seen_tops):
                    seen_tops.add(top)
                    out.append((top, m.group(0).strip()))
        y += stride
    out.sort(key=lambda p: p[0])
    return out


def _chapter_for(top: float, chapters: list[tuple[float, str]], carry: str) -> str:
    current = carry
    for c_top, text in chapters:
        if c_top <= top:
            current = text
        else:
            break
    return current


def _extract_page_rows(columns_words: dict[str, list[tuple[float, str]]],
                        chapters: list[tuple[float, str]],
                        carry_chapter: str) -> tuple[list[dict], str]:
    pn_tokens = [
        (top, t) for top, t in columns_words["PART_NUMBER"] if _PN_TOKEN_RE.match(t)
    ]
    if not pn_tokens:
        return [], carry_chapter
    pn_tokens.sort(key=lambda p: p[0])
    anchors = [top for top, _ in pn_tokens]
    pn_values = [t for _, t in pn_tokens]

    buckets: list[dict[str, list[str]]] = [
        {name: [] for name in _FIELD_NAMES if name != "PART_NUMBER"} for _ in anchors
    ]
    for col_name in _FIELD_NAMES:
        if col_name == "PART_NUMBER":
            continue
        for top, text in columns_words[col_name]:
            idx = _nearest_anchor_idx(top, anchors)
            if idx is not None:
                buckets[idx][col_name].append(text)

    rows = []
    last_chapter = carry_chapter
    for i, pn in enumerate(pn_values):
        b = buckets[i]
        row = {"PART_NUMBER": pn}
        for col_name in _FIELD_NAMES:
            if col_name == "PART_NUMBER":
                continue
            row[col_name] = _join(b[col_name], col_name)
        chapter = _chapter_for(anchors[i], chapters, last_chapter)
        last_chapter = chapter
        row["CHAPTER"] = chapter
        rows.append(row)
    return rows, last_chapter


def _parse_header_text(text: str, meta: dict) -> None:
    if not meta.get("AIRCRAFT_REG"):
        m = _AC_META_RE.search(text)
        if m:
            meta["AIRCRAFT_REG"] = m.group("reg").upper()
            meta["AIRCRAFT_TYPE"] = m.group("type").upper().strip()
            meta["MSN"] = m.group("msn")
            meta["AIRCRAFT_TSN"] = m.group("tsn").replace(",", ".")
            meta["AIRCRAFT_CSN"] = m.group("csn")
            meta["REPORT_DATE"] = m.group("date")
    if not meta.get("ENGINE_SIDE"):
        m = _ENGINE_META_RE.search(text)
        if m:
            meta["ENGINE_SIDE"] = m.group("side").upper()
            meta["ENGINE_TYPE"] = m.group("type")
            meta["ENGINE_SERIAL_NUMBER"] = m.group("esn")
            meta["ENGINE_TSN"] = m.group("tsn").replace(",", ".")
            meta["ENGINE_CSN"] = m.group("csn")


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback -- this
    variant's known source file has no text layer at all, so it can never
    be found through the normal pdfplumber head-text match.

    Anchors on the report's own generic title phrase (no organization name
    -- see module docstring)."""
    try:
        img = await render_page(pdf_path, 0, dpi=300)
        w, h = img.size
        crop = img.crop((0, 0, w, int(h * 0.15)))
        text = await ocr_text(crop, psm=6)
        return bool(_TITLE_RE.search(text))
    except Exception:
        return False


async def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    header_meta = {k: "" for k in _HEADER_FIELDS}
    carry_chapter = ""
    n_pages = await page_count(pdf_path)
    for page_index in range(n_pages):
        img = await render_page(pdf_path, page_index, dpi=300)
        w, h = img.size

        title_crop = img.crop((0, 0, w, int(h * 0.15)))
        title_text = await ocr_text(title_crop, psm=6)
        if not _TITLE_RE.search(title_text):
            # This page's own title no longer matches this report -- a
            # different, unrelated attached document starts here (confirmed
            # directly on the real sample file, see module docstring). Stop
            # rather than mis-parsing a completely different row shape
            # through this module's own column mapping.
            break

        if not header_meta["AIRCRAFT_REG"] or not header_meta["ENGINE_SIDE"]:
            meta_crop = img.crop((0, int(h * 0.16), w, int(h * 0.23)))
            meta_text = await ocr_text(meta_crop, psm=4)
            _parse_header_text(meta_text, header_meta)

        # Data grid starts just below the two-line column-header block,
        # which sits at the same fixed position on every page (confirmed
        # directly), and runs to the bottom of the page.
        y0, y1 = int(h * 0.29), h
        chapters = await _detect_chapters(img, y0, y1)

        columns_words: dict[str, list[tuple[float, str]]] = {}
        for name in _FIELD_NAMES:
            columns_words[name] = await _ocr_column(img, name, y0, y1)

        rows, carry_chapter = _extract_page_rows(columns_words, chapters, carry_chapter)
        for row in rows:
            row["_page"] = page_index + 1
            row.update(header_meta)
            records.append(row)
    return records
