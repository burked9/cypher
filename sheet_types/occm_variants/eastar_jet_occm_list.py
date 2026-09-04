""""<Operator> OC/CM List" — scanned, no text layer, OCR required on every
page. Header block reads roughly::

    <OPERATOR> OC/CM List
    MSN# <n>
    Registration # <tail> As of <yyyy-mm-dd> A/C TSN : <n> A/C CSN : <n>

followed by a ruled data grid with columns ATA | Position | P/N | S/N |
Install Date | Description | Origin, one row per component, e.g.::

    21 | RH | <part number> | <serial number> | 2001-06-28 | RECIRCULATING FAN | TBC

POSITION is genuinely optional -- roughly a third of rows carry no position
code at all (a bare ATA/PN/SN/date/description/origin row), confirmed by
direct inspection across several pages; the rest carry a short position
token (LH/RH/FWD/AFT/INBD/OUTBD/CTR/#<n>/free-text combinations of these).

ORIGIN is a closed 3-value set on every known file -- TBC / UNK / ESR --
confirmed by reading well over 500 rows directly across the full page
range. It OCRs unusually badly even after the grid-line cleanup below (see
`_normalize_origin`): TBC in particular comes back as almost any 3-letter
"T??" token (`TEC`, `TAC`, `TSC`, `TEE`, `TAE`, `TEO`, ...) as the ruled
cell border noise interacts with the B/C glyphs, and UNK regularly picks
up a stray leading glyph (`uUNK`, `wUNK`, `uUuNK`). Canonicalised
below rather than left for the generic per-column pattern flag to catch,
since an un-normalized pass would flag the large majority of rows over
what is actually a clean, fully-recovered closed-vocabulary value.

The ruled grid's horizontal rule lines OCR very badly at a plain
render+OCR pass: a horizontal line running behind or through a cell's
whitespace gets read as a long run of stray letters/underscores
("SSCSCSC~C~CSCSCSCSCSCSCS") that swallows the whitespace between
columns and even fuses adjacent cells into one unrecoverable token --
confirmed directly: a plain 400dpi psm 6 pass (no preprocessing) recovers
only ~34 clean rows out of ~620 on this file. `ocr_words()`-style
coordinate-bucketing (the technique `occm_report_scanned.py` and
`aircraft_rotables_report_scanned.py` use for a similarly noisy grid) was
tried directly and doesn't hold up here either: a fused
border-plus-whitespace glob commonly becomes a single Tesseract "word"
spanning several real columns' width, so its bounding-box centre lands in
one arbitrary column bucket and the row's other columns come back empty --
confirmed by direct inspection of the word boxes at both the default and
`psm=12` (sparse text) settings.

What works: a numpy min/max horizontal filter run on the binarized (grayscale
< 150) page before OCR, sized to the printed rule-line thickness at 400dpi,
which strips the long horizontal runs (rule lines and the noise they cause)
while leaving individual glyph strokes (which are far shorter horizontally)
intact. `ocr_text()` (whole-page, psm 6) on the cleaned image recovers the
data grid essentially intact, including its "|" column borders as literal
pipe characters most of the time -- confirmed directly: this raises the
same file's recovered-row count from ~34 to ~614 out of the ~622 rows
visually present, a page-average column-border and OCR-noise loss rate
under 2%, most of which is corrupted install dates (a digit misread as a
letter breaking the date pattern) rather than lost rows.

Row parsing here is border-aware rather than plain whitespace-token
splitting (unlike aircraft_occm_list_scanned.py's simpler 6-column sibling,
which has no optional column): every border-ish glyph (pipes, brackets,
parens, angle brackets, tildes) is normalized to a single "|" delimiter and
the line is split on that, since the ruled column borders remain the most
reliable structural signal even after cleanup -- a plain whitespace-token
split can't reliably tell where an empty POSITION cell ends and PART_NUMBER
begins. The leading ATA cell is recovered by searching (not anchoring at
column 0) for the first 1-2 digit run in the pre-date cells, since a
misread border character routinely glues an extra stray glyph onto the
very first cell (confirmed directly: "j 21", "j} 23", "j; 24" are all OCR
renderings of a plain "| 21" row start). Whatever text follows those digits
in that same cell, plus any further pre-date cells, are treated as up to
three slots (POSITION / PART_NUMBER / SERIAL_NUMBER, in that order) --
POSITION is dropped only when there are just two slots to fill, keeping
this permissive rather than guessing which slot a stray token belongs to
when the border noise leaves that ambiguous. This is the same "extract
what's structurally recoverable, flag the rest for review" approach
aircraft_occm_list_scanned.py and occm_report_scanned.py both take for
their own noisy grids, applied to a genuinely optional extra column.
"""
from __future__ import annotations
import re

import numpy as np
from PIL import Image

from sheet_types.occm_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, page_count

NAME = "EASTAR JET OC/CM List"

# Deliberately empty -- every known source file has no text layer at all
# (confirmed: 0 chars via pdfplumber on every page). Detection happens via
# ocr_detect() below, which is the only way this variant is ever reached.
SIGNATURES = []

CANONICAL_COLUMNS = [
    "ATA",
    "POSITION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "INSTALL_DATE",
    "DESCRIPTION",
    "ORIGIN",
]

_OVERRIDES = {
    "POSITION": {"allow_empty": True},
    "INSTALL_DATE": {"pattern": r"^\d{4}[-. ]\d{1,2}[-. ]\d{1,2}$",
                      "allow_empty": True},
    # Canonicalised to one of TBC/UNK/ESR by _normalize_origin() below
    # before validation ever sees it -- kept loose (not pattern-enforced)
    # so a genuinely new code on a future export flags for review rather
    # than being silently rejected as invalid.
    "ORIGIN": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# --- grid-line cleanup ------------------------------------------------------

_DPI = 400
# Horizontal run length (px @ 400dpi) beyond which a black-pixel run is
# treated as a printed rule line rather than a glyph stroke -- confirmed
# against the known source file's rule-line thickness and its narrowest
# real glyphs (individual character strokes never form a >45px unbroken
# horizontal run at this DPI, ruled lines always do).
_LINE_WIN = 45
_DARK_THRESH = 150


def _horiz_filter(arr: np.ndarray, win: int, op: str) -> np.ndarray:
    pad = win // 2
    padded = np.pad(arr, ((0, 0), (pad, pad)), mode="constant", constant_values=0)
    windows = np.lib.stride_tricks.sliding_window_view(padded, win, axis=1)
    return getattr(windows, op)(axis=2)


def _strip_rule_lines(img: Image.Image) -> Image.Image:
    """Binarize the page and erase long horizontal black-pixel runs (ruled
    table lines), leaving individual glyph strokes intact -- see module
    docstring. A horizontal min-filter finds pixels that are part of a
    >= `_LINE_WIN`px run; a matching max-filter re-dilates that mask back
    to the run's original extent before zeroing it out."""
    gray = np.array(img.convert("L"))
    bw = (gray < _DARK_THRESH).astype(np.uint8)
    eroded = _horiz_filter(bw, _LINE_WIN, "min")
    mask = _horiz_filter(eroded.astype(np.uint8), _LINE_WIN, "max").astype(bool)
    cleaned = bw.copy()
    cleaned[mask] = 0
    out = 255 - cleaned * 255
    return Image.fromarray(out.astype(np.uint8))


# --- row parsing -------------------------------------------------------------

# Any of these glyphs is a misread of a ruled column border (pipe, bracket,
# paren, angle bracket, tilde) -- normalized to one delimiter before
# splitting, since the OCR'd border character varies row to row.
_BORDER_TO_PIPE_RE = re.compile(r"[|\[\]{}()<>~]+")
_JUNK_RE = re.compile(r"[`*\"'«»‘’“”_.]+")
_ATA_SEARCH_RE = re.compile(r"(\d{1,2})\s*(.*)$")
_DATE_RE = re.compile(r"^\d{4}[-. ]\d{1,2}[-. ]\d{1,2}$")


def _clean_cell(s: str) -> str:
    s = _JUNK_RE.sub(" ", s)
    return " ".join(s.split()).strip(" -,;:")


def _normalize_origin(raw: str) -> str:
    """Canonicalise the closed 3-value ORIGIN vocabulary (TBC/UNK/ESR) out
    of its many OCR renderings -- see module docstring. Anything that
    doesn't fit a known pattern is kept as-is (uppercased, non-letters
    stripped) so normalize_and_validate() flags it for review rather than
    this function silently forcing an unrecognised code into one of the
    three known values."""
    s = re.sub(r"[^A-Za-z]", "", raw).upper()
    if not s:
        return ""
    if "TBC" in s:
        return "TBC"
    if "UNK" in s:
        return "UNK"
    if "ESR" in s:
        return "ESR"
    # TBC's B/C glyphs are the least reliable OCR in this vocabulary --
    # confirmed renderings include TEC/TAC/TSC/TEE/TAE/TEO, none of which
    # contain a literal "TBC" substring above. No other known code in this
    # closed set starts with "T", so any 3-letter T-led token is treated
    # as a TBC misread rather than left unrecognised.
    if len(s) == 3 and s[0] == "T":
        return "TBC"
    return s


def _parse_line(line: str, page_num: int) -> dict | None:
    norm = _BORDER_TO_PIPE_RE.sub("|", line)
    parts = [_clean_cell(p) for p in norm.split("|")]
    while parts and parts[0] == "":
        parts.pop(0)
    while parts and parts[-1] == "":
        parts.pop()
    if len(parts) < 5:
        return None

    date_idx = next((i for i, p in enumerate(parts) if _DATE_RE.match(p)), None)
    if date_idx is None or date_idx < 1:
        return None

    # Find the ATA cell: the first pre-date cell containing a 1-2 digit
    # run, searched for (not anchored at index 0) since a misread border
    # glyph routinely glues an extra stray character onto the very first
    # cell ("j 21", "j} 23" -- see module docstring). The search stops (does
    # not skip past) the first hyphenated cell it meets without a hit --
    # this template's PART_NUMBER is routinely hyphenated (e.g.
    # "1234567-10") and its ATA/POSITION cells never are, so a hyphenated
    # cell is always PART_NUMBER territory. Confirmed necessary on a
    # handful of rows where the real ATA cell ("80") OCRs as the bare word
    # "so" -- no digit at all -- which would otherwise let this search run
    # past it and steal a digit run out of the real PART_NUMBER cell,
    # corrupting both fields. Leaving ATA unset here (rather than guessing)
    # keeps PART_NUMBER intact and gives forward_fill_ata() a shot at
    # recovering ATA from the surrounding rows instead.
    ata_idx = ata = residue = None
    for i in range(date_idx):
        if "-" in parts[i]:
            break
        m = _ATA_SEARCH_RE.search(parts[i])
        if m:
            ata_idx, ata, residue = i, m.group(1), m.group(2).strip()
            break

    # Everything between the ATA cell and the date is up to three slots:
    # POSITION (optional) / PART_NUMBER / SERIAL_NUMBER. Any residue text
    # left over in the ATA cell itself (see above) is treated as the
    # leading slot, since it's almost always POSITION text that lost its
    # own leading border. When no ATA cell was found at all, every
    # pre-date cell is used as-is (nothing consumed as ATA).
    if ata_idx is None:
        # One further narrow, confirmed-specific correction: the real ATA
        # "80" consistently OCRs as the bare word "so" on this file's
        # chapter-80 rows (no digit survives at all) -- "SO" is not a
        # POSITION code seen anywhere else in this template (LH/RH/AFT/
        # FWD/INBD/OUTBD/CTR/#<n>/CAP/FO and combinations thereof, never a
        # bare "SO"), so it's safe to recognise specifically rather than
        # leave these rows' ATA empty when the fix is this unambiguous.
        if parts and parts[0].strip().upper() == "SO":
            ata = "80"
            pre = list(parts[1:date_idx])
        else:
            ata = ""
            pre = list(parts[:date_idx])
    else:
        pre = list(parts[ata_idx + 1:date_idx])
        if residue:
            pre = [residue] + pre
    # Drop interior blanks -- these are near-always double-pipe noise from
    # the grid-line cleanup rather than a genuinely blank PART_NUMBER/
    # SERIAL_NUMBER (only POSITION is ever legitimately blank, and a truly
    # blank POSITION cell never leaves a stray "" entry in `pre` -- its own
    # border pair simply doesn't survive OCR at all, see module docstring).
    pre = [p for p in pre if p]
    if len(pre) >= 3:
        position, part_number = pre[0], pre[1]
        serial_number = " ".join(pre[2:])
    elif len(pre) == 2:
        position, part_number, serial_number = "", pre[0], pre[1]
    elif len(pre) == 1:
        position, part_number, serial_number = "", pre[0], ""
    else:
        position, part_number, serial_number = "", "", ""

    post = parts[date_idx + 1:]
    if not post:
        return None
    origin = _normalize_origin(post[-1])
    description = " ".join(post[:-1]).strip()
    if not description:
        return None

    return {
        "ATA": ata,
        "POSITION": position,
        "PART_NUMBER": part_number,
        "SERIAL_NUMBER": serial_number,
        "INSTALL_DATE": parts[date_idx],
        "DESCRIPTION": description,
        "ORIGIN": origin,
        "_page": page_num,
    }


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback -- every
    known source file has no text layer at all (0 chars via pdfplumber on
    every page), so this is the only way this variant is ever reached.

    Checks for "EASTAR" together with "LIST" in the header crop rather than
    the full "OC/CM LIST" title phrase, since the "/" glyph OCRs
    inconsistently even at this cheap pass (seen rendering as "OCICM",
    "OCCM", "OCI/CM" across different pages/DPIs) while "EASTAR" itself is
    unique to this operator's export and OCRs reliably. Checked for
    collisions against every SIGNATURES list in sheet_types/{occm,ht,llp}.py
    and every existing variant's ocr_detect anchor -- "EASTAR" appears
    nowhere else in the package. In particular, aircraft_occm_list_scanned.py
    (built earlier this session, covering a differently-shaped "Aircraft
    OC/CM List" title with no operator prefix and no POSITION column)
    anchors on the literal phrase "AIRCRAFT OC/CM LIST", which this file's
    header never renders -- no shadowing in either direction.
    """
    try:
        img = await render_page(pdf_path, 0, dpi=300)
        w, h = img.size
        crop = img.crop((0, 0, w, int(h * 0.15)))
        text = (await ocr_text(crop, psm=6)).upper()
        return "EASTAR" in text and "LIST" in text
    except Exception:
        return False


async def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    n_pages = await page_count(pdf_path)
    for page_index in range(n_pages):
        img = await render_page(pdf_path, page_index, dpi=_DPI)
        cleaned = _strip_rule_lines(img)
        text = await ocr_text(cleaned, psm=6)
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            rec = _parse_line(line, page_index + 1)
            if rec is not None:
                records.append(rec)
    return records
