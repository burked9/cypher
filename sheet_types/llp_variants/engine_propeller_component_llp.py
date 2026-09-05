""""ENGINE PROPELLER & COMPONENT LLP" -- a Pratt & Whitney PW127F twin-engine
life-limited-parts *scrap-tracking* sheet ("ENGINE #1"/"ENGINE #2" header
blocks, each followed by its own ~10-row parts table, disposition always
"Scrap"). Companion propeller/component pages of the same source PDF (a
different report -- "O/H" disposition, "Frequency Hours"/"exp date SB61-7"
columns instead of this report's "Frequency Cycles"/"EN Task") are NOT this
format and are deliberately out of scope here.

No text layer on the one known source file (a clean computer-rendered
spreadsheet-style raster, not a photographed form) -- every page of that PDF
comes back with 0 extracted characters, so this module is reached purely via
`ocr_detect()` below, and renders/OCRs via `shared/ocr_bridge.py`'s async
primitives (`render_page()`/`ocr_text()`/`ocr_words()`), never fitz/
pytesseract directly, so it also runs under the Pyodide/JS bridge.

Layout (values below are illustrative placeholders, not real source values)::

    Report Date <d>   Registration <reg>          [top box, once per file]
    Serial No. <n>     Build Date <d>
    Aircraft TSN <h>   Aircraft CSN <c>

    Date Installed <d>      Engine Model <model>   ENGINE #1
    A/C TSN @ Install <h>   Serial No. <esn>        Limiting Parameters: Cyc
    A/C CSN @ Install <c>   Position <p>            LLP Min <n>
    Eng TSN. @ Install <h>  TSN <h>
    Eng CSN @ Install <c>   CSN <c>
    ... (repeated once per engine -- "ENGINE #2" block below it) ...

    Engine Position | Part | Task | Part No. | Serial No. | Frequency Cycles |
    FCF | Part @ Install Cycles | Engine @ Install Cycles |
    Next Due @ Engine Cycles | Remaining Cycles | % | EN Task | Key
    (~10 data rows per engine, Task always "Scrap", Key numbered 1,2,4-11 --
    the source genuinely skips key=3 on every row seen; not a parsing bug)

Two engine blocks, each its own ruled table with its own repeated column
header -- confirmed by direct pixel inspection (see `_find_table_blocks()`).
The giant vertical "Engine 1"/"Engine 2" label painted down the left edge of
each table is data belonging to no real column here: OCR reads it as
scattered short garbage tokens (confirmed directly: things like a bare
2-letter fragment or a parenthesised fragment, never the same fragment twice)
bleeding into whatever real column happens to sit nearest it, and never as
readable digits worth keeping. Rather than try to read it, this module gets
the engine position far more reliably from each block's own header box
("Position" field, printed as a clean single digit) and stamps that onto
every row from that block; any OCR word whose left-edge sits to the left of
the real "Part" column's own leftmost observed start (confirmed directly
across every row of both blocks: never below x=350 once rescaled off this
module's DPI) is dropped before row-parsing ever sees it, rather than
assigned to a spurious "ENGINE_POSITION data column" that would just be that
garbage.

Row-splitting strategy, and why it's used instead of column-boundary
detection: this table's ruled grid has solid horizontal borders only at each
block's own top/bottom edges (confirmed directly -- no full-width horizontal
darkness at any individual row boundary, unlike a fully gridded table), so
there's no reliable per-row ruling to key off of, and the header labels'
own x-positions don't line up cleanly enough with every row's data to use as
fixed column boundaries either (confirmed directly: a numeric trailing digit
that's actually part of a PART name, e.g. a rotor stage index printed right
after the part description, sits close enough to the neighbouring column's
header label that a simple midpoint-of-header-labels boundary misassigns
it). Instead, each row's own word list is split by FIXED TRAILING COUNT: the
12 columns from Task through Key are always exactly one OCR token each on
every row seen (confirmed directly across all 20 data rows of both engine
blocks), so the last 12 tokens (left-to-right) are always those 12 columns
in their known fixed order, and everything before them -- however many words
-- is the PART description. This sidesteps needing any column-boundary
x-threshold at all for the row body.

Stray vertical-gridline ink is routinely OCR'd as its own bogus token
(a lone "|", "{", "}", etc.) sitting between two real cells -- confirmed
directly, and left uncorrected it silently shifts the fixed-trailing-count
split by one column for that row. Tokens that are pure punctuation with no
letter or digit are dropped before the trailing-12 split for exactly this
reason.

Self-check, not blind trust: every trailing numeric-only field (Key,
Frequency Cycles, and the four Cycles columns) is checked for the presence
of a stray letter before being trusted -- Tesseract occasionally reads a
gridline-bleed-contaminated digit as a short garbage word instead (confirmed
directly on one real cell: a clean "7" came back as a 2-letter garbage
string when OCR'd as part of the whole row, because a thin vertical
gridline sliver immediately to its left fused into the same recognized
word). Any field that fails this check is re-cropped tightly around just
that one OCR word's own bounding box, has any full-cell-height near-solid
vertical stripe (the gridline sliver) painted out, and is re-OCR'd alone
with a digits-only whitelist -- confirmed directly to recover the correct
digit on the one real case found. This mirrors the same
paint-out-the-gridline-before-OCR fix already used by
`part_m_engine_disk_sheet.py` for its own gridline-bleed digit misreads, and
the same crop-tight-then-whitelist-OCR fix `kalstar_engine_llp_status.py`
already uses for its own narrow numeric columns -- reused here rather than
reinvented, since it's the same underlying problem (a vertical rule bleeding
into a numeric cell's OCR).

The FCF column prints a comma decimal separator (e.g. a fixed point like
"1,00" or "1,15") on every row seen; it's normalised to a dot decimal here
to match this project's numeric-field convention elsewhere, rather than kept
as printed.

Known, deliberately-not-"fixed" oddity: the printed EN Task reference code
is a fixed-format string on every row *except* one recurring row (Disc Pwr
Turbine 2) on both engine blocks of the one known file, where the source
itself prints a differently-shaped code (a trailing hyphen substituted where
every other row's code has a run of digits at that position). This isn't an
OCR misread -- confirmed directly, the shape is consistent across both
engine blocks -- so it's captured as printed rather than "corrected" to match
the other rows' pattern.

Header metadata fields (ENGINE_MODEL, ENGINE_SERIAL_NUMBER, ENGINE_POSITION,
DATE_INSTALLED, the AIRCRAFT_*_AT_INSTALL / ENGINE_*_AT_INSTALL cycle
figures, and LLP_MIN_CYCLES) are parsed once per engine block and stamped
onto every row belonging to that block, the same convention used by the
per-engine sibling module `kalstar_engine_llp_status.py`. The aircraft-level
fields (report date, registration, aircraft serial number, build date,
aircraft TSN/CSN) appear exactly once for the whole file (not per engine)
and are stamped onto every row regardless of engine block.

The header word-bucketing x-fraction boundaries below are based on the one
known source file only (this format has a single known real sample) --
unlike `kalstar_engine_llp_status.py`'s equivalent constants, these have NOT
been confirmed stable across multiple files, so treat them as a starting
point to revisit if a second real sample ever surfaces disagreeing values.
"""
from __future__ import annotations
import re

import numpy as np
from PIL import Image

from sheet_types.llp_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, ocr_words

NAME = "Engine Propeller & Component LLP"

# Text-layer signature list deliberately empty -- the one known source file
# has a 0-char text layer on every page (see module docstring); router.py's
# blank-text fallback reaches this module purely through ocr_detect() below.
SIGNATURES: list[str] = []

CANONICAL_COLUMNS = [
    "ENGINE_POSITION",
    "PART",
    "DISPOSITION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "FREQUENCY_CYCLES",
    "FCF",
    "PART_AT_INSTALL_CYCLES",
    "ENGINE_AT_INSTALL_CYCLES",
    "NEXT_DUE_AT_ENGINE_CYCLES",
    "REMAINING_CYCLES",
    "REMAINING_PCT",
    "EN_TASK",
    "KEY",
    # Per-engine header metadata -- same on every row of a given engine
    # block, see module docstring.
    "ENGINE_MODEL",
    "ENGINE_SERIAL_NUMBER",
    "DATE_INSTALLED",
    "AIRCRAFT_TSN_AT_INSTALL",
    "AIRCRAFT_CSN_AT_INSTALL",
    "ENGINE_TSN_AT_INSTALL",
    "ENGINE_CSN_AT_INSTALL",
    "ENGINE_TSN_CURRENT",
    "ENGINE_CSN_CURRENT",
    "LLP_MIN_CYCLES",
    # Aircraft-level metadata -- same on every row of the whole file.
    "REPORT_DATE",
    "AIRCRAFT_REGISTRATION",
    "AIRCRAFT_SERIAL_NUMBER",
    "AIRCRAFT_BUILD_DATE",
    "AIRCRAFT_TSN",
    "AIRCRAFT_CSN",
]

_INT_RULE = {"pattern": r"^[\d,]*$", "allow_empty": True,
             "int_range": (0, 90000), "int_range_review": (0, 60000)}
_DATE_RULE = {"pattern": r"^(\d{1,2}-[A-Za-z]{3,9}-\d{2,4})?$", "allow_empty": True}
_OVERRIDES = {
    "ENGINE_POSITION":           {"pattern": r"^[12]?$", "allow_empty": True},
    "DISPOSITION":               {"pattern": r"^[A-Z]*$", "uppercase": True, "allow_empty": True},
    "FREQUENCY_CYCLES":          _INT_RULE,
    "FCF":                       {"pattern": r"^\d*\.?\d*$", "allow_empty": True},
    "PART_AT_INSTALL_CYCLES":    _INT_RULE,
    "ENGINE_AT_INSTALL_CYCLES":  _INT_RULE,
    "NEXT_DUE_AT_ENGINE_CYCLES": _INT_RULE,
    "REMAINING_CYCLES":          _INT_RULE,
    "REMAINING_PCT":             {"pattern": r"^\d{1,3}%?$", "allow_empty": True},
    "EN_TASK":                   {"pattern": r"^[A-Z0-9\-]*$", "uppercase": True, "allow_empty": True},
    "KEY":                       {"pattern": r"^\d{1,3}$", "allow_empty": True},
    "ENGINE_MODEL":              {"pattern": r"^[A-Z0-9\-]*$", "uppercase": True, "allow_empty": True},
    # Soft pattern (letters-then-digits) rather than a bare alnum check --
    # deliberately narrow enough to flag (not silently accept) the one
    # known-hard OCR cell on the single real source file, where this cell's
    # thin internal cell-boundary ink split the true value into two OCR
    # tokens and left a garbled read behind (see module docstring on
    # gridline-bleed splits) -- flagged for manual verification against
    # the source PDF rather than guessed at further.
    "ENGINE_SERIAL_NUMBER":      {"pattern": r"^[A-Z]{1,4}\d{2,8}$", "uppercase": True, "allow_empty": True},
    "DATE_INSTALLED":            _DATE_RULE,
    "AIRCRAFT_TSN_AT_INSTALL":   _INT_RULE,
    "AIRCRAFT_CSN_AT_INSTALL":   _INT_RULE,
    "ENGINE_TSN_AT_INSTALL":     _INT_RULE,
    "ENGINE_CSN_AT_INSTALL":     _INT_RULE,
    "ENGINE_TSN_CURRENT":        _INT_RULE,
    "ENGINE_CSN_CURRENT":        _INT_RULE,
    "LLP_MIN_CYCLES":            _INT_RULE,
    "REPORT_DATE":               _DATE_RULE,
    "AIRCRAFT_REGISTRATION":     {"pattern": r"^[A-Z0-9\-]*$", "uppercase": True, "allow_empty": True},
    "AIRCRAFT_SERIAL_NUMBER":    {"allow_empty": True},
    "AIRCRAFT_BUILD_DATE":       _DATE_RULE,
    "AIRCRAFT_TSN":              _INT_RULE,
    "AIRCRAFT_CSN":              _INT_RULE,
}
RULES = merged_rules(_OVERRIDES)

_DPI = 300
_DARK_THRESH = 150
_ROW_DARK_FRAC = 0.3
_MIN_BLOCK_GAP = 300     # px -- see module docstring on why blocks are found
                         # by gap size rather than fixed row-height math.
_HEADER_FLOOR_FRAC = 0.30  # header info boxes end well above this fraction
                            # of page height on the one known file; used
                            # only to skip past them when hunting for the
                            # table blocks' own top border.

# Header-info word-bucketing boundaries (x-fraction of page width) and
# per-engine-block y-fraction split -- see module docstring's caveat that
# these are based on the single known source file only.
_HDR_COL_FRACS = (0.227, 0.483, 0.710)
_HDR_ROW_FRAC = 0.181
_HDR_BAND_FRAC = 0.32  # header info region sits above this fraction of page
                       # height on the one known file (well below the table).

_FIXED_ROW_FIELDS = [
    "DISPOSITION", "PART_NUMBER", "SERIAL_NUMBER", "FREQUENCY_CYCLES", "FCF",
    "PART_AT_INSTALL_CYCLES", "ENGINE_AT_INSTALL_CYCLES",
    "NEXT_DUE_AT_ENGINE_CYCLES", "REMAINING_CYCLES", "REMAINING_PCT",
    "EN_TASK", "KEY",
]
_N_FIXED = len(_FIXED_ROW_FIELDS)
_PART_MIN_LEFT = 350  # px at _DPI -- see module docstring: every genuine
                      # PART/data token on every row of both known engine
                      # blocks starts at x>=382; every rotated-label
                      # bleed-through garbage token starts at x<=293. This
                      # sits safely between the two with margin either way.

_PUNCT_ONLY_RE = re.compile(r"[|\[\]{}_.,:;]+")
_DIGITS = "0123456789"


def _line_groups(frac: np.ndarray, thresh: float) -> list[tuple[int, int]]:
    idx = np.where(frac > thresh)[0]
    if not len(idx):
        return []
    groups, cur = [], [int(idx[0])]
    for v in idx[1:]:
        if v - cur[-1] <= 3:
            cur.append(int(v))
        else:
            groups.append((cur[0], cur[-1]))
            cur = [int(v)]
    groups.append((cur[0], cur[-1]))
    return groups


def _find_table_blocks(gray: np.ndarray) -> list[tuple[int, int]]:
    """Returns [(data_top, data_bottom), ...] -- the y-range of each engine's
    own data rows. Found by locating the two large gaps between full-width
    dark lines (each engine table's own top/bottom borders), not by assuming
    a fixed row count or row height -- see module docstring."""
    h, _ = gray.shape
    dark = gray < _DARK_THRESH
    rowfrac = dark.mean(axis=1)
    groups = _line_groups(rowfrac, _ROW_DARK_FRAC)
    floor = h * _HEADER_FLOOR_FRAC
    groups = [g for g in groups if g[0] > floor]
    blocks = []
    for i in range(len(groups) - 1):
        if groups[i + 1][0] - groups[i][1] > _MIN_BLOCK_GAP:
            blocks.append((groups[i][1], groups[i + 1][0]))
    return blocks


def _cluster_by_top(words: list[dict], gap: int = 25) -> list[list[dict]]:
    """Group OCR words into rows/lines by top-coordinate proximity --
    same top-proximity-clustering approach `kalstar_engine_llp_status.py`
    uses for its own header text, applied here to the table body instead."""
    if not words:
        return []
    ws = sorted(words, key=lambda d: d["top"])
    clusters = [[ws[0]]]
    for wd in ws[1:]:
        if wd["top"] - clusters[-1][-1]["top"] <= gap:
            clusters[-1].append(wd)
        else:
            clusters.append([wd])
    return clusters


def _cluster_lines(words: list[dict], gap: int = 20) -> str:
    """Re-join a header word-bucket into text, top-to-bottom then
    left-to-right within each line -- mirrors
    `kalstar_engine_llp_status.py`'s own `_cluster_lines()`."""
    if not words:
        return ""
    ws = sorted(words, key=lambda d: d["top"])
    clusters: list[list[dict]] = [[ws[0]]]
    for wd in ws[1:]:
        if wd["top"] - clusters[-1][-1]["top"] <= gap:
            clusters[-1].append(wd)
        else:
            clusters.append([wd])
    return " ".join(
        " ".join(d["text"] for d in sorted(c, key=lambda d: d["left"]))
        for c in clusters
    )


async def _repair_numeric_cell(img, word: dict, whitelist: str = _DIGITS) -> str:
    """Re-OCR a single OCR word's own bounding box in isolation, after
    painting out any near-full-cell-height vertical stripe (a bled-in
    gridline sliver) -- see module docstring's self-check section."""
    pad = 6
    x0 = max(0, word["left"] - pad)
    y0 = max(0, word["top"] - pad)
    x1 = word["left"] + word["width"] + pad
    y1 = word["top"] + word["height"] + pad
    if x1 <= x0 or y1 <= y0:
        return ""
    cell = img.crop((x0, y0, x1, y1))
    arr = np.array(cell.convert("L"))
    dark = arr < 100
    if dark.size:
        colfrac = dark.mean(axis=0)
        strip_cols = np.where(colfrac > 0.85)[0]
        if len(strip_cols):
            rgb = np.array(cell.convert("RGB"))
            for c in strip_cols:
                rgb[:, max(0, c - 1):c + 2] = 255
            cell = Image.fromarray(rgb)
    text = await ocr_text(cell, psm=7, whitelist=whitelist)
    return text.strip()


_LETTER_RE = re.compile(r"[A-Za-z]")
_DIGIT_RE = re.compile(r"\d+")


async def _clean_int_token(img, word: dict) -> str:
    """Extract a digit-only value from a fixed-numeric-column OCR word,
    re-OCR'ing the cell in isolation only when the raw token contains a
    letter (a sign the whole-row OCR pass mis-split it with adjacent
    gridline ink) -- see module docstring."""
    raw = word["text"]
    if not _LETTER_RE.search(raw):
        m = _DIGIT_RE.search(raw.replace(",", ""))
        if m:
            return m.group(0)
    repaired = await _repair_numeric_cell(img, word, whitelist=_DIGITS)
    m = _DIGIT_RE.search(repaired)
    if m:
        return m.group(0)
    return re.sub(r"[^\d]", "", raw)


def _clean_fcf(raw: str) -> str:
    m = re.search(r"\d+[,.]?\d*", raw)
    return m.group(0).replace(",", ".") if m else ""


def _clean_pct(raw: str) -> str:
    m = re.search(r"(\d{1,3})\s*%", raw)
    return f"{m.group(1)}%" if m else ""


def _strip_junk(raw: str) -> str:
    """Drop leading non-alnum characters -- gridline-bleed artefacts like a
    stray leading `|`/`{`/`}` seen on this format's Part No./Serial
    No./Task/EN Task cells (see module docstring)."""
    return re.sub(r"^[^A-Za-z0-9]+", "", raw).strip()


# (regex, canonical-column) pairs applied to each header word-bucket's own
# re-joined text -- mirrors kalstar_engine_llp_status.py's _HDR_FIELDS. The
# label/value separator (_SEP) is deliberately NOT a greedy `\D*` --
# confirmed directly that `\D*` is the wrong tool here: several of this
# format's own values start with a LETTER (e.g. the engine model, the
# engine serial number, the aircraft registration), and a greedy \D* skips
# straight over those letters hunting for the first digit, silently
# swallowing a downstream field's digits instead (e.g. "Engine Model"
# resolving to the model string's own trailing digits with its leading
# letters chopped off, or "Registration" resolving to a completely
# different field's numeric value found later in the same reconstructed
# text block). _SEP only ever crosses whitespace/punctuation and, at most,
# ONE short (<=3 letter) garbage token -- confirmed directly that this
# header box's own thin decorative underlines/box-edges occasionally OCR
# as a stray short garbage word (e.g. a 2-letter fragment) wedged between a
# label and its real value on this one known file -- never a whole second
# real word, so capping it at 3 letters can't accidentally swallow a
# genuine short value. The punctuation class also covers stray
# gridline/box-edge-bleed characters (`|`, `;`, braces) seen wedged in the
# same way elsewhere on this one known file (see the table-body docstring
# section above on gridline-bleed tokens -- the header boxes have thin
# rules too and produce the same kind of noise).
_SEP_CHARS = r"[\s:;_.\-–—|{}\[\]]*"
_SEP = _SEP_CHARS + r"(?:[A-Za-z]{1,3}\s+)?" + _SEP_CHARS

_AIRCRAFT_FIELDS = (
    (re.compile(r"Report\s*Date" + _SEP + r"(\d{1,2}-[A-Za-z]{3,9}-\d{2,4})", re.I), "REPORT_DATE"),
    (re.compile(r"Registration" + _SEP + r"([A-Z0-9\-]+)", re.I), "AIRCRAFT_REGISTRATION"),
    (re.compile(r"Serial\s*No\.?" + _SEP + r"(\d+)", re.I), "AIRCRAFT_SERIAL_NUMBER"),
    (re.compile(r"Build\s*[Dd]ate" + _SEP + r"(\d{1,2}-[A-Za-z]{3,9}-\d{2,4})", re.I), "AIRCRAFT_BUILD_DATE"),
    (re.compile(r"Aircraft\s*TSN" + _SEP + r"([\d,]+)", re.I), "AIRCRAFT_TSN"),
    (re.compile(r"Aircraft\s*CSN" + _SEP + r"([\d,]+)", re.I), "AIRCRAFT_CSN"),
)
_INSTALL_FIELDS = (
    (re.compile(r"Date\s*Installed" + _SEP + r"(\d{1,2}-[A-Za-z]{3,9}-\d{2,4})", re.I), "DATE_INSTALLED"),
    (re.compile(r"A/?C\s*TSN\s*@?\s*Install" + _SEP + r"([\d,]+)", re.I), "AIRCRAFT_TSN_AT_INSTALL"),
    (re.compile(r"A/?C\s*CSN\s*@?\s*Install" + _SEP + r"([\d,]+)", re.I), "AIRCRAFT_CSN_AT_INSTALL"),
    (re.compile(r"Eng\s*TSN\.?\s*@?\s*Install" + _SEP + r"([\d,]+)", re.I), "ENGINE_TSN_AT_INSTALL"),
    (re.compile(r"Eng\s*CSN\s*@?\s*Install" + _SEP + r"([\d,]+)", re.I), "ENGINE_CSN_AT_INSTALL"),
)
_ENGINE_FIELDS = (
    (re.compile(r"Engine\s*Model" + _SEP + r"([A-Z0-9\-]+)", re.I), "ENGINE_MODEL"),
    (re.compile(r"Serial\s*No\.?" + _SEP + r"([A-Z0-9]+(?:\s+[A-Z0-9]+)?)", re.I), "ENGINE_SERIAL_NUMBER"),
    (re.compile(r"Position" + _SEP + r"(\d+)", re.I), "ENGINE_POSITION"),
    (re.compile(r"\bTSN\b" + _SEP + r"([\d,]+)", re.I), "ENGINE_TSN_CURRENT"),
    (re.compile(r"\bCSN\b" + _SEP + r"([\d,]+)", re.I), "ENGINE_CSN_CURRENT"),
)
_LLP_FIELDS = (
    # "LL" is occasionally OCR'd as "LI" on this one known file (confirmed
    # directly on one of its two LLP-Min boxes) -- tolerate both spellings
    # rather than require an exact "LLP" match.
    (re.compile(r"L[IL]P\s*Min" + _SEP + r"([\d,]+)", re.I), "LLP_MIN_CYCLES"),
)

# Header words taller than this are the giant rotated "1"/"2" engine-number
# glyph painted beside each info box (confirmed directly: ~90px tall vs.
# ~25-50px for every genuine label/value word at this DPI) -- dropped before
# clustering/bucketing since it otherwise bridges two genuinely separate
# header lines into one falsely-merged text block (its y-position sits
# between them) and contributes no real field value of its own.
_HDR_WORD_MAX_HEIGHT = 70


async def _parse_header(img) -> tuple[dict, list[dict]]:
    """Returns (aircraft_meta, [engine0_meta, engine1_meta]) -- the
    aircraft-level box appears once; the install/engine/LLP-min boxes
    appear once per engine block, bucketed by x-fraction (column) and
    y-fraction (engine block), same bucketing approach
    kalstar_engine_llp_status.py uses for its own 4-column header."""
    w, h = img.size
    crop = img.crop((0, 0, w, int(h * _HDR_BAND_FRAC)))
    words = await ocr_words(crop, psm=6, min_conf=-1)
    words = [wd for wd in words if wd["height"] <= _HDR_WORD_MAX_HEIGHT]

    b0, b1, b2 = (f * w for f in _HDR_COL_FRACS)
    row_split = h * _HDR_ROW_FRAC
    buckets: dict[tuple[int, int], list[dict]] = {
        (c, r): [] for c in range(4) for r in range(2)
    }
    for wd in words:
        x, y = wd["left"], wd["top"]
        col = 0 if x < b0 else 1 if x < b1 else 2 if x < b2 else 3
        row = 0 if y < row_split else 1
        buckets[(col, row)].append(wd)

    aircraft_meta: dict[str, str] = {}
    text = _cluster_lines(buckets[(0, 0)])
    for pat, key in _AIRCRAFT_FIELDS:
        m = pat.search(text)
        if m:
            aircraft_meta[key] = m.group(1).strip()

    engine_metas = []
    for row in (0, 1):
        meta: dict[str, str] = {}
        for col, fields in ((1, _INSTALL_FIELDS), (2, _ENGINE_FIELDS), (3, _LLP_FIELDS)):
            text = _cluster_lines(buckets[(col, row)])
            for pat, key in fields:
                m = pat.search(text)
                if m:
                    meta[key] = re.sub(r"\s+", "", m.group(1).strip())
        engine_metas.append(meta)
    return aircraft_meta, engine_metas


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 header OCR check for the router's blank-text fallback.
    Anchors on this table's own distinctive column-header phrase rather
    than a page title (the source workbook's own title text is not
    reliably present as rendered page content -- confirmed directly)."""
    try:
        img = await render_page(pdf_path, 0, dpi=_DPI)
        crop = img.crop((0, int(img.height * 0.32), img.width, int(img.height * 0.40)))
        text = (await ocr_text(crop, psm=6)).upper()
        text = text.replace("\n", " ")
        return "ENGINE @ INSTALL" in text and "REMAINING" in text and "EN TASK" in text
    except Exception:
        return False


async def extract(pdf_path: str) -> list[dict]:
    img = await render_page(pdf_path, 0, dpi=_DPI)
    w, _ = img.size
    gray = np.array(img.convert("L"))

    blocks = _find_table_blocks(gray)
    if len(blocks) != 2:
        # Never guess which rows belong to which engine if the two-block
        # structure this format always has can't be confirmed -- see
        # module docstring.
        return []

    aircraft_meta, engine_metas = await _parse_header(img)

    records: list[dict] = []
    for (data_top, data_bottom), engine_meta in zip(blocks, engine_metas):
        crop = img.crop((0, data_top, w, data_bottom))
        words = await ocr_words(crop, psm=6, min_conf=-1)
        for wd in words:
            wd["top"] += data_top  # back to full-page coordinates
        words = [wd for wd in words if wd["left"] >= _PART_MIN_LEFT]
        clusters = _cluster_by_top(words, gap=25)

        for cluster in clusters:
            toks = sorted(cluster, key=lambda d: d["left"])
            toks = [t for t in toks if not _PUNCT_ONLY_RE.fullmatch(t["text"])]
            if len(toks) < _N_FIXED + 1:
                continue
            part_toks = toks[: len(toks) - _N_FIXED]
            fixed_toks = toks[len(toks) - _N_FIXED :]

            rec = {c: "" for c in CANONICAL_COLUMNS}
            rec["PART"] = " ".join(t["text"] for t in part_toks).strip()
            fixed = dict(zip(_FIXED_ROW_FIELDS, fixed_toks))

            rec["DISPOSITION"] = _strip_junk(fixed["DISPOSITION"]["text"]).upper()
            rec["PART_NUMBER"] = _strip_junk(fixed["PART_NUMBER"]["text"])
            rec["SERIAL_NUMBER"] = _strip_junk(fixed["SERIAL_NUMBER"]["text"])
            rec["FREQUENCY_CYCLES"] = await _clean_int_token(img, fixed["FREQUENCY_CYCLES"])
            rec["FCF"] = _clean_fcf(fixed["FCF"]["text"])
            rec["PART_AT_INSTALL_CYCLES"] = await _clean_int_token(img, fixed["PART_AT_INSTALL_CYCLES"])
            rec["ENGINE_AT_INSTALL_CYCLES"] = await _clean_int_token(img, fixed["ENGINE_AT_INSTALL_CYCLES"])
            rec["NEXT_DUE_AT_ENGINE_CYCLES"] = await _clean_int_token(img, fixed["NEXT_DUE_AT_ENGINE_CYCLES"])
            rec["REMAINING_CYCLES"] = await _clean_int_token(img, fixed["REMAINING_CYCLES"])
            rec["REMAINING_PCT"] = _clean_pct(fixed["REMAINING_PCT"]["text"])
            rec["EN_TASK"] = _strip_junk(fixed["EN_TASK"]["text"]).upper()
            rec["KEY"] = await _clean_int_token(img, fixed["KEY"])

            for k, v in aircraft_meta.items():
                rec[k] = v
            for k, v in engine_meta.items():
                rec[k] = v
            rec["_page"] = 1
            records.append(rec)

    return records
