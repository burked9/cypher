"""OCCM Parts Compliance Status Report -- scanned, no text layer, OCR
required throughout.

Confirmed on a real corpus file (16 pages, 0 extractable chars on every
page via pdfplumber -- a straight scan, landscape ruled grid). Page 1
carries a header block that does NOT repeat on later pages::

    <reg> - OCCM PARTS COMPLIANCE STATUS REPORT   Status Date: <month> <d>, <yyyy>
    <operator wordmark/logo>                      FH: <n>
    <parent-group wordmark/logo>                  FC: <n>

The operator's own name and its parent-group's name are confirmed present
directly on the real sample file, rendered as a small logo/wordmark image
in the top-left of the header block -- intentionally NOT extracted into
any column here (no OCR is attempted over that logo region), and per this
project's data-sensitivity convention neither name is recorded anywhere in
this module. AIRCRAFT_REG, STATUS_DATE, FH and FC are parsed once from
page 1's header text (confirmed to OCR cleanly as a single joined line for
the title/reg/status-date, plus two short separate lines for FH/FC) and
stamped identically onto every row of the file, per this package's usual
header-plus-body convention.

Column header row (confirmed directly, page 1 only -- does NOT reprint on
any later page, unlike several sibling OCCM formats in this package)::

    ATA | P/N | S/N | Description | Installation date | FH at Inst | FC at Inst

A data row, tokens in column order: ATA, PART_NUMBER, SERIAL_NUMBER,
DESCRIPTION, INSTALL_DATE, FH_AT_INSTALL, FC_AT_INSTALL -- confirmed
directly across the first, several middle, and the last page of the real
sample file. ATA is confirmed to print on every single data row (no
forward-fill needed, though the generic post-process still runs as a
safety net). FH_AT_INSTALL / FC_AT_INSTALL cells are confirmed to
legitimately read as a plain "0" or "0,00", as the literal placeholder
"UNK", or (rarely, on one page's rows) the lowercase placeholder "uk" --
none of these are parse failures, and all are accepted by this module's
RULES rather than flagged. Numeric FH_AT_INSTALL values use a
period-thousands/comma-decimal convention (fractional hours, e.g.
"<n>.<nnn>,<nn>"); FC_AT_INSTALL values are whole cycle counts that
instead use a comma as a thousands separator (e.g. "<n>,<nnn>") -- two
different real-world conventions in the same file, confirmed directly, so
both columns are validated with the same loose "digits + separators, or a
known placeholder" pattern rather than a tight one that would fight either
convention.

Page layout, confirmed directly across the whole real sample file: two of
its sixteen pages render portrait-oriented (rotated 90 degrees relative to
every other page's landscape orientation) -- an artifact of how the
originals were fed through a scanner, not a different template. This
module detects that via the rendered image's own aspect ratio (a
narrower-than-tall page) and rotates it 90 degrees before any column-strip
OCR runs, after which its ruled grid's column positions line up with
every other page's to within a few pixels (confirmed directly).

OCR approach, confirmed by direct experimentation against the real sample
file, following the same overall shape as this package's other
scanned-OCCM variants (e.g. `msn_occm_list_scanned.py`) but adapted to
this file's own failure modes:

A whole-page or whole-row-width OCR pass over the data grid comes back
badly corrupted -- confirmed directly, Tesseract fuses several adjacent
ruled columns into a single garbled "word" spanning most of the row width
often enough to make row-width word-bucketing unreliable here. The same
pixels OCR cleanly once cropped down to a single ruled column's own width
(spanning the full column height) -- confirmed directly -- provided the
crop is pulled a few pixels inward off the column's own ruled border lines
first; a crop landing on (or beyond) the border comes back corrupted the
same way a whole-row crop does, the same border-crop effect documented in
`msn_occm_list_scanned.py`'s own docstring. This module therefore OCRs
each of the seven columns as its own inset, full-height strip.

ATA is used as the per-row anchor (rather than Y-clustering every column's
words independently), for the same reason as `msn_occm_list_scanned.py`:
it is a short, high-confidence, near-uniformly-spaced column, more
reliable to anchor on than the free-text DESCRIPTION column or the
occasionally row-split PART_NUMBER/INSTALL_DATE columns. Each of the other
six columns is OCR'd as its own strip, and every resulting word is
assigned to its nearest ATA anchor by Y-distance, within a tolerance below
half the file's real row pitch (confirmed directly, ~38-39px at 300dpi).

FH_AT_INSTALL / FC_AT_INSTALL need one extra step beyond the other
columns: at default settings, a lone "0" data cell in these two columns
Tesseract-reads as one or more "0"/"O"/"o" characters that a plain
comma/period/digit filter would otherwise discard as noise, while a real
multi-digit reading (e.g. "1,116") comes through fine -- confirmed directly,
reproduced identically across many rows. So these two columns are each
OCR'd twice per page (a default word-segmentation pass and a sparse-text
pass) and the results merged per row, keeping whichever reading is more
informative; a run of only zero-like characters is normalized to a plain
"0" rather than dropped.

Known limitation, confirmed directly against the real sample file's final
pages: the file's very last page carries only a short tail of data rows
above a signature/certification block (not part of the tabular data, and
not extracted), and its ruled grid sits at a slightly different position
than every earlier page -- a handful of rows there are noticeably noisier
than the rest of the file (cross-column bleed on OCR misreads). This is
expected to surface as a lower per-row confidence / soft-validation flags
on that page's rows specifically, rather than silently wrong data across
the whole file, per this project's soft-validation convention (see
`shared/aviation_rules.py`).
"""
from __future__ import annotations
import re

from PIL import Image

from sheet_types.occm_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, ocr_words, page_count

NAME = "OCCM Parts Compliance Status Report (Scanned)"

# This module's known source file has no text layer at all (confirmed via
# pdfplumber -- 0 chars on every page), so these SIGNATURES can never fire
# through occm.py's normal pdfplumber head-text match; real detection
# happens via ocr_detect() below. Deliberately left empty, same convention
# as this package's other purely-OCR variants.
SIGNATURES = []

CANONICAL_COLUMNS = [
    "ATA",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
    "INSTALL_DATE",
    "FH_AT_INSTALL",
    "FC_AT_INSTALL",
    # Header metadata, parsed once (page 1) and stamped on every row.
    "AIRCRAFT_REG",
    "STATUS_DATE",
    "FH",
    "FC",
]

# FH_AT_INSTALL / FC_AT_INSTALL cells are legitimately a plain integer, a
# decimal with either thousands convention seen in this file (see module
# docstring), the literal placeholder "UNK", or (rarely) lowercase "uk" --
# none of these are parse failures, so the pattern accepts all of them
# case-insensitively rather than flagging every zero/placeholder row.
_LOOSE_NUM_RULE = {"pattern": r"(?i)^(?:[\d.,]+|unk|uk)$", "allow_empty": True}

_OVERRIDES = {
    "INSTALL_DATE": {
        "pattern": r"^\d{1,2}\.\d{1,2}\.\d{2,4}$",
        "allow_empty": True,
    },
    "FH_AT_INSTALL": _LOOSE_NUM_RULE,
    "FC_AT_INSTALL": _LOOSE_NUM_RULE,
    # Header metadata -- each value is a single figure parsed once and
    # stamped identically on every row of the file, so a tight pattern here
    # would either flag every single row over one OCR misread in one
    # place, or none at all -- neither is a useful per-row signal (same
    # reasoning as this package's other header-plus-body OCCM variants,
    # e.g. `msn_occm_list_scanned.py`'s own header fields).
    "AIRCRAFT_REG": {"pattern": r"^[A-Z0-9\-]+$", "allow_empty": True},
    "STATUS_DATE": {"allow_empty": True},
    "FH": {"pattern": r"^[\d:.,]+$", "allow_empty": True},
    "FC": {"pattern": r"^[\d:.,]+$", "allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_HEADER_FIELDS = ["AIRCRAFT_REG", "STATUS_DATE", "FH", "FC"]

# Column X-boundaries (px @ 300dpi), measured directly from the real
# rendered page's own ruled vertical-line pixel columns (a >=90%-dark
# column over the data-grid's Y-span) -- confirmed stable across the
# first, several middle, and last pages of the real sample file, including
# after the two portrait pages are rotated upright (see module
# docstring). Each bound is pulled 8px inward from the measured border
# position rather than flush against it -- confirmed directly that a
# full-height column crop whose edge lands ON the table's own ruled
# border comes back badly corrupted, the very same pixels OCR cleanly a
# few px inward (same effect documented in
# `msn_occm_list_scanned.py`'s own docstring).
_INSET = 8
_RAW_BOUNDS = [
    (220, 389, "ATA"),
    (389, 740, "PART_NUMBER"),
    (740, 1185, "SERIAL_NUMBER"),
    (1185, 1888, "DESCRIPTION"),
    (1888, 2198, "INSTALL_DATE"),
    (2198, 2403, "FH_AT_INSTALL"),
    (2403, 2696, "FC_AT_INSTALL"),
]
_COLUMNS = [(lo + _INSET, hi - _INSET, name) for lo, hi, name in _RAW_BOUNDS]

# Row anchor: a bare 1-3 digit ATA chapter code, restricted to this
# package's usual chapter range -- keeps a stray OCR digit run elsewhere
# in the ATA strip from creating a bogus anchor row.
_ATA_RANGE = (20, 83)

# Y-tolerance for assigning a non-ATA column's word to its nearest ATA
# anchor -- measured directly against the real sample file's own row pitch
# (~38-39px @ 300dpi between consecutive rows); comfortably below half
# that, so a word never gets pulled onto an adjacent row.
_ANCHOR_TOLERANCE_PX = 18

# Columns whose tokens are joined with no separator when a cell's text is
# split across more than one OCR word box (compact codes with no
# legitimate internal space) -- DESCRIPTION is genuine free text and is
# the only column joined with spaces.
_JOIN_NOSPACE = {"ATA", "PART_NUMBER", "SERIAL_NUMBER", "INSTALL_DATE"}

_ZERO_RUN_RE = re.compile(r"^[Oo0]+$")
_NUM_STRIP_RE = re.compile(r"[^0-9.,]")

_TITLE_RE = re.compile(
    r"([A-Z0-9\-]{4,8})\s*-\s*OCCM\s+PARTS\s+COMPLIANCE\s+STATUS\s+REPORT",
    re.IGNORECASE,
)
_STATUS_DATE_RE = re.compile(r"Status\s*Date:?\s*(.+)$", re.IGNORECASE)
_FH_RE = re.compile(r"\bFH:?\s*([0-9:.,]+)", re.IGNORECASE)
_FC_RE = re.compile(r"\bFC:?\s*([0-9:.,]+)", re.IGNORECASE)


def _clean_num_token(raw: str) -> str | None:
    """Filter/normalize one OCR word from FH_AT_INSTALL/FC_AT_INSTALL (see
    module docstring on why these two columns need this rather than the
    plain digit/separator filter every other numeric-ish column gets).
    Returns None for tokens that carry no usable signal at all (pure
    border/segmentation noise)."""
    t = raw.strip()
    if not t:
        return None
    if t.upper() == "UNK":
        return "UNK"
    if t.lower() == "uk":
        return "uk"
    if _ZERO_RUN_RE.match(t):
        return "0"
    t2 = _NUM_STRIP_RE.sub("", t)
    if not t2 or not any(c.isdigit() for c in t2):
        return None
    return t2


async def _ocr_column(img, x0: int, x1: int, y0: int, y1: int,
                       psm: int = 6, scale: int = 1) -> list[tuple[float, str]]:
    """OCR one column's full-height strip (see module docstring on why a
    column-width crop OCRs far more reliably here than a row-width or
    whole-page crop) and return (top, text) pairs in original-image page
    coordinates."""
    crop = img.crop((x0, y0, x1, y1))
    if scale != 1:
        crop = crop.resize((crop.width * scale, crop.height * scale), Image.LANCZOS)
    words = await ocr_words(crop, psm=psm, min_conf=-1)
    out = []
    for w in words:
        text = str(w.get("text", "")).strip()
        if not text:
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
    if not tokens:
        return ""
    if col_name in _JOIN_NOSPACE:
        return "".join(tokens)
    # Numeric-ish columns: keep the single most informative reading rather
    # than concatenating (see module docstring -- both an OCR pass's own
    # "0"-run and a real multi-digit reading can land on the same anchor).
    if col_name in ("FH_AT_INSTALL", "FC_AT_INSTALL"):
        return max(tokens, key=len)
    return " ".join(tokens)


def _parse_header_text(text: str, meta: dict) -> None:
    # Parsed one line at a time (rather than one collapsed blob) so that
    # STATUS_DATE's capture can't run past its own line onto the next
    # line's logo-area OCR noise -- confirmed directly that the real
    # sample file's header OCRs as three separate lines (title+status-date,
    # then FH:, then FC:, each on its own line), each already whitespace-
    # collapsed within itself before matching.
    for raw_line in text.splitlines():
        line = " ".join(raw_line.split())
        if not line:
            continue
        if not meta.get("AIRCRAFT_REG"):
            m = _TITLE_RE.search(line)
            if m:
                meta["AIRCRAFT_REG"] = m.group(1).upper()
        if not meta.get("STATUS_DATE"):
            m = _STATUS_DATE_RE.search(line)
            if m:
                meta["STATUS_DATE"] = m.group(1).strip()
        if not meta.get("FH"):
            m = _FH_RE.search(line)
            if m:
                meta["FH"] = m.group(1)
        if not meta.get("FC"):
            m = _FC_RE.search(line)
            if m:
                meta["FC"] = m.group(1)


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback (see
    sheet_types/occm.py) -- this variant's known source file has no text
    layer at all, so it can never be found through the normal pdfplumber
    head-text match.

    Anchors on the report's own title phrase "OCCM PARTS COMPLIANCE STATUS
    REPORT" (checked directly, grep across every SIGNATURES list in
    sheet_types/{occm,ht,llp}.py and every existing occm_variants file:
    the phrase "PARTS COMPLIANCE" / "COMPLIANCE STATUS" appears nowhere
    else, and is not a substring of, nor contains, any other variant's own
    SIGNATURES/ocr_detect anchor)."""
    try:
        img = await render_page(pdf_path, 0, dpi=300)
        if img.width < img.height:
            img = img.rotate(90, expand=True)
        w, h = img.size
        crop = img.crop((0, 0, w, int(h * 0.14)))
        text = (await ocr_text(crop, psm=6)).upper()
        return "OCCM PARTS COMPLIANCE STATUS REPORT" in " ".join(text.split())
    except Exception:
        return False


async def _parse_page(img, y0: int) -> list[dict]:
    w, h = img.size
    y1 = h
    col_tokens: dict[str, list[tuple[float, str]]] = {}
    for x0, x1, name in _COLUMNS:
        if name in ("FH_AT_INSTALL", "FC_AT_INSTALL"):
            # Two passes merged (see module docstring): a default
            # word-segmentation pass and a sparse-text pass each catch
            # readings the other one misses.
            pass_a = await _ocr_column(img, x0, x1, y0, y1, psm=6, scale=1)
            pass_b = await _ocr_column(img, x0, x1, y0, y1, psm=11, scale=1)
            toks = []
            for top, text in pass_a + pass_b:
                cleaned = _clean_num_token(text)
                if cleaned is not None:
                    toks.append((top, cleaned))
            col_tokens[name] = toks
        else:
            col_tokens[name] = await _ocr_column(img, x0, x1, y0, y1, psm=6, scale=2)

    anchors: list[tuple[float, str]] = []
    for top, text in col_tokens["ATA"]:
        digits = re.sub(r"[^0-9]", "", text)
        if digits and len(digits) <= 3:
            try:
                n = int(digits)
            except ValueError:
                continue
            if _ATA_RANGE[0] <= n <= _ATA_RANGE[1]:
                anchors.append((top, digits))
    if not anchors:
        return []
    anchors.sort(key=lambda p: p[0])
    anchor_tops = [top for top, _ in anchors]
    ata_values = [d for _, d in anchors]

    other_cols = [name for _, _, name in _COLUMNS if name != "ATA"]
    buckets: list[dict[str, list[str]]] = [
        {name: [] for name in other_cols} for _ in anchors
    ]
    for name in other_cols:
        for top, text in col_tokens[name]:
            idx = _nearest_anchor_idx(top, anchor_tops)
            if idx is not None:
                buckets[idx][name].append(text)

    rows = []
    for i, ata in enumerate(ata_values):
        b = buckets[i]
        description = _join(b["DESCRIPTION"], "DESCRIPTION")
        part_number = _join(b["PART_NUMBER"], "PART_NUMBER")
        serial_number = _join(b["SERIAL_NUMBER"], "SERIAL_NUMBER")
        if not description and not part_number and not serial_number:
            # No real cell content attached to this ATA anchor at all --
            # almost certainly page furniture rather than a genuine row.
            continue
        rows.append({
            "ATA": ata,
            "PART_NUMBER": part_number,
            "SERIAL_NUMBER": serial_number,
            "DESCRIPTION": description,
            "INSTALL_DATE": _join(b["INSTALL_DATE"], "INSTALL_DATE"),
            "FH_AT_INSTALL": _join(b["FH_AT_INSTALL"], "FH_AT_INSTALL"),
            "FC_AT_INSTALL": _join(b["FC_AT_INSTALL"], "FC_AT_INSTALL"),
        })
    return rows


async def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    header_meta = {k: "" for k in _HEADER_FIELDS}
    n_pages = await page_count(pdf_path)
    for page_index in range(n_pages):
        img = await render_page(pdf_path, page_index, dpi=300)
        if img.width < img.height:
            # Two of the real source file's sixteen pages render portrait
            # (a scanner-feed artifact, see module docstring) -- rotate
            # upright before any column-strip OCR runs.
            img = img.rotate(90, expand=True)
        w, h = img.size

        if page_index == 0:
            header_crop = img.crop((0, 0, w, int(h * 0.20)))
            header_text = await ocr_text(header_crop, psm=6)
            _parse_header_text(header_text, header_meta)
            # Data grid (below the title/status block and the repeated
            # column-header row) starts at a fixed fraction of page 1
            # only -- confirmed directly against the real sample file.
            data_y0 = int(h * 0.205)
        else:
            # No header or column-header row repeats on later pages (see
            # module docstring) -- the data grid runs almost to the top,
            # with a small margin skipped for the page's own top border.
            data_y0 = int(h * 0.03)

        for rec in await _parse_page(img, data_y0):
            rec["_page"] = page_index + 1
            rec.update(header_meta)
            records.append(rec)
    return records
