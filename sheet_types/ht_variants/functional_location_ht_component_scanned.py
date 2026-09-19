"""Scanned twin of `functional_location_ht_component.py` -- same "HT-
COMPONENT" MIS export family and same 8-column layout, but the files this
module targets have no extractable text layer at all (confirmed directly
with pdfplumber `extract_text()` on a real sample -- 0 characters on every
page), so that sibling's plain-text token-anchoring parse never has
anything to run against.

Header block (repeats verbatim near the top of every page, same shape as
the born-digital sibling)::

    <A/C REG> HT-COMPONENT A/C FH : <hours> FC : <cycles>
    (Date : <dd.mm.yyyy> Time : <hh:mm:ss>)
    (C OF A)
    Functional Location  Part number  Equipment text  Serial number
        Interval  Unit  Rem.life  End Date

Unlike the born-digital sibling (a plain-text export where only the first
two and last four fields keep a fixed x-position, per that module's own
docstring), the rendered page here is a genuine fully-ruled grid -- every
column boundary is a real drawn vertical line, confirmed directly via a
numpy column-darkness scan of the sample file's own page 1 (see `_COLUMNS`
below) -- so every column, including EQUIPMENT_TEXT, keeps a fixed
x-position throughout and a plain per-column-strip OCR pass is reliable
here, no whitespace-tokenizing/anchor-from-both-ends trick needed.

Row anchor: FUNCTIONAL_LOCATION is used as the per-row Y anchor -- present
on every real data row (confirmed directly: unlike some other HT variants
in this package, this template never leaves it blank on a continuation
row) and shaped distinctively enough (several hyphen-separated alnum
groups) that a structural regex reliably tells a real row's own value
apart from page furniture -- the title/date/"(C OF A)"/column-header lines
and a page's own "Prepared by: <name>" signature footer -- without ever
matching any of those. This is the same reasoning the born-digital
sibling's own docstring gives for skipping that footer line rather than
needing a dedicated regex for it: no name from it is captured into any
output field (confirmed directly on the sample file: the tokens on that
line never match `_ANCHOR_RE`).

Each of the other 7 columns is OCR'd **per row**, one small crop at a
time, rather than once per whole-column strip: confirmed directly on the
sample file that a single OCR pass over an entire tall EQUIPMENT_TEXT
column strip silently drops whole rows whenever the same description text
repeats on consecutive rows (e.g. four consecutive "SERVO CONTROL AILERON
(INB)" rows -- one whole-column pass returned only one of the four,
regardless of which page-segmentation mode was tried), apparently because
consecutive visually-identical lines get merged/deduplicated by Tesseract's
own layout analysis rather than being a font/scan-noise issue. Re-cropped
to each row's own narrow band individually, the exact same text OCRs
correctly and completely every time. FUNCTIONAL_LOCATION itself does not
need this treatment (its own value differs row to row, so no dedup
collision occurs), so it alone is still OCR'd as one whole-column strip
purely to gather anchor Y-positions cheaply.

Each row's own crop window is the midpoint between its own anchor and its
immediate neighbours (extending outward by half the page's own median row
pitch for the first/last row on a page) -- deliberately NOT anchor-to-
page-bottom for the last row on a page: confirmed directly this template's
own last real data row can sit with a wide blank gap above the page's own
"Prepared by: <name>" footer, but capping every row's own window this way
(same convention this package's other per-row-per-column-strip OCR
variants use, see e.g. the row-window sizing in
`ht_ruled_grid_time_limit_columns_scanned.py`) means that footer's own
text is never close enough in Y to any real anchor to be swept into a
row's own field regardless, rather than relying on the size of any one
sample file's own margin.

INTERVAL is a single ruled cell whose printed content is a letter-code
immediately followed by a numeric value with a real visible gap between
them in the rendered raster (e.g. "YAC 4380") -- unlike the born-digital
sibling's own plain-text token stream, where the equivalent value decodes
with no gap at all ("HBB2500", see that module's own docstring). Both are
the same underlying field with the same shape, just rendered differently
by the two export paths, so this module strips the internal whitespace
before validation (an unambiguous, information-preserving normalisation,
not a guessed split) to match the canonical no-space shape the shared
`RULES` (mirrored from the born-digital sibling) expect.

REM_LIFE is printed with a thousands-separator comma in the rendered
raster (e.g. "-1,359") where the born-digital sibling's own plain-text
token never carries one; the comma is stripped before validation for the
same reason as the INTERVAL whitespace above.

Sensitivity note: the confirmed real sample file carries a real aircraft
registration/operator/preparer name in its own header and footer -- none
of that is written into this module's code/comments (only the template's
own generic column-header and section-title phrases, which are not
document-specific). The header's own AC_REG/AC_FH/AC_FC/REPORT_DATE/
REPORT_TIME fields ARE extracted into row data at runtime (same as the
born-digital sibling's own header-metadata capture) -- that is ordinary
functional extraction, not a hardcoded document-specific value in source
code. The footer's own preparer name is never captured into any output
field, confirmed directly against the real sample (see the row-anchor
discussion above).
"""
from __future__ import annotations
import re

from sheet_types.ht_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_words, ocr_text, page_count

NAME = "Functional Location HT Component (Scanned)"

# Deliberately empty -- this file's own text layer is blank on every page
# (see module docstring), so a plain-pdfplumber SIGNATURES phrase would
# never be checked against real page content anyway. Detected instead via
# ocr_detect() below, through the router's blank-text-layer OCR-fallback
# path (sheet_types/ht.py's own detect_variant()).
SIGNATURES: list[str] = []

CANONICAL_COLUMNS = [
    "FUNCTIONAL_LOCATION",
    "PART_NUMBER",
    "EQUIPMENT_TEXT",
    "SERIAL_NUMBER",
    "INTERVAL",
    "UNIT",
    "REM_LIFE",
    "END_DATE",
    # Header metadata -- same on every row of a given file (mirrors the
    # born-digital sibling's own field names).
    "AC_REG",
    "AC_FH",
    "AC_FC",
    "REPORT_DATE",
    "REPORT_TIME",
]

_NUM_RE = r"^-?\d+(?:\.\d+)?$"
_DATE_RE = r"^\d{2}\.\d{2}\.\d{4}$"

# Same shape as the born-digital sibling's own RULES overrides (mirrored
# deliberately -- this is the same underlying field set), with every field
# additionally allow_empty here since a single-cell OCR miss on this
# template shouldn't flag every row, same convention this package's other
# per-column-strip OCR variants use.
_OVERRIDES = {
    "FUNCTIONAL_LOCATION": {"allow_empty": True},
    "EQUIPMENT_TEXT":      {"allow_empty": True},
    "INTERVAL":            {"pattern": r"^[A-Z0-9]+$", "uppercase": True,
                             "allow_empty": True},
    "UNIT":                {"pattern": r"^(DAY|FH|FC)$", "uppercase": True,
                             "allow_empty": True},
    "REM_LIFE":            {"pattern": r"^-?\d+$", "allow_empty": True},
    "END_DATE":            {"pattern": _DATE_RE, "allow_empty": True},
    "AC_REG":              {"pattern": r"^[A-Z0-9\-]+$", "uppercase": True,
                             "allow_empty": True},
    "AC_FH":               {"pattern": _NUM_RE, "allow_empty": True},
    "AC_FC":               {"pattern": r"^\d+$", "allow_empty": True},
    "REPORT_DATE":         {"pattern": _DATE_RE, "allow_empty": True},
    "REPORT_TIME":         {"pattern": r"^\d{2}:\d{2}:\d{2}$", "allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Column X-boundaries, as a fraction of the rendered page's own width --
# derived directly from a numpy column-darkness scan of the ruled grid's
# own vertical divider lines on the sample file's page 1, and confirmed
# stable (sub-0.001 drift) against the same scan run on three other pages
# of the sample.
_COLUMNS = [
    (0.01408, 0.18103, "FUNCTIONAL_LOCATION"),
    (0.18103, 0.28534, "PART_NUMBER"),
    (0.28534, 0.53362, "EQUIPMENT_TEXT"),
    (0.53362, 0.65287, "SERIAL_NUMBER"),
    (0.65287, 0.73046, "INTERVAL"),
    (0.73046, 0.77443, "UNIT"),
    (0.77443, 0.83937, "REM_LIFE"),
    (0.83937, 0.92443, "END_DATE"),
]

# A row's own FUNCTIONAL_LOCATION value is several hyphen-separated
# alnum groups (e.g. "<PREFIX>-<PREFIX>-21-31-5201-316HL") -- this
# structural shape, not any one file's own specific registration prefix,
# is what the anchor regex matches, so it generalises across any tail's
# own copy of this template. Confirmed directly against the sample file's
# own page-furniture lines (title, date/time, "(C OF A)", column-header
# row, "Prepared by: <name>" footer) -- none of their own OCR'd tokens
# match this shape.
_ANCHOR_RE = re.compile(r"^[A-Z0-9]{2,6}-[A-Z0-9]{2,6}(?:-[A-Z0-9_]{1,8}){2,6}$")

_UNIT_RE = re.compile(r"^(DAY|FH|FC)$")
_UNIT_RE_LOOSE = re.compile(r"(DAY|FH|FC)")
_DATE_TOKEN_RE = re.compile(r"(\d{1,2})\D(\d{1,2})\D(\d{4})")
_INT_TOKEN_RE = re.compile(r"-?[\d,]+")
_CODE_STRIP_CHARS = " _\"'`‘’“”.,;:()[]{}|~=-–—"

_TITLE_RE = re.compile(
    r"(\S+)\s+HT-?COMPONENT\s+A[/I]C\s+FH\s*[:;]\s*([\d.]+)\s+FC\s*[:;]\s*(\d+)",
    re.IGNORECASE,
)
_DATE_TIME_RE = re.compile(r"\(Date\s*[:;]\s*(\S+)\s+Time\s*[:;]\s*([\d:]+)\)", re.IGNORECASE)

_HEADER_FIELDS = ["AC_REG", "AC_FH", "AC_FC", "REPORT_DATE", "REPORT_TIME"]

# Median row pitch fallback (px @ 300 DPI) -- used only to size the
# first/last row's own outward half-window on a page where fewer than 2
# anchors are found (so no real pitch can be measured); derived from the
# sample file's own observed pitch (~67-68px @ 300 DPI).
_DEFAULT_PITCH = 68
_OCR_DPI = 300

# Vertical inset applied to each row's own crop window on both edges --
# confirmed directly on the sample file (checked across all 5 pages) that
# anything under ~8px lets the ruled row-divider line itself bleed into
# the crop and OCR as stray trailing noise (e.g. "FIREX CONT" reading back
# as "FIREX CONT 7"), while anything over ~8px starts clipping real glyph
# tops/descenders badly enough on at least one page of the sample (this
# file's own row pitch is a tight ~67-68px @ 300 DPI, so even a 1px extra
# inset on both edges removes a meaningful fraction of glyph height) to
# garble whole rows rather than just trimming border noise.
_ROW_PAD_PX = 8


def _col_bounds(w: int, name: str) -> tuple[int, int]:
    for lo, hi, col in _COLUMNS:
        if col == name:
            return int(lo * w), int(hi * w)
    raise KeyError(name)


async def _anchor_rows(img) -> list[tuple[int, str]]:
    """Whole-column OCR pass over FUNCTIONAL_LOCATION to gather each real
    data row's own Y anchor -- safe as a single tall-strip pass (unlike
    every other column here) because this file's own value differs row to
    row, so Tesseract's own duplicate-line collapsing (see module
    docstring) never applies to it. Returns (top, text) pairs sorted by
    top -- the text is reused directly as the row's own FUNCTIONAL_LOCATION
    value (see `extract()`) rather than re-OCR'd from a second, narrower
    per-row crop: confirmed directly on the sample file that this
    whole-column psm=11 pass reads this column's own values more reliably
    than the tighter per-row psm=7 crop every other column here uses."""
    w, h = img.size
    x0, x1 = _col_bounds(w, "FUNCTIONAL_LOCATION")
    # Starting the crop a little below the page's own top furniture is
    # enough -- there is no need to dodge the title/date/"(C OF A)" lines
    # precisely, since none of their own tokens match _ANCHOR_RE anyway.
    crop = img.crop((x0, int(h * 0.20), x1, h))
    words = await ocr_words(crop, psm=11, min_conf=-1)
    rows = []
    for wd in words:
        text = str(wd.get("text", "")).strip()
        if _ANCHOR_RE.match(text):
            rows.append((int(h * 0.20) + wd["top"], text))
    return sorted(rows, key=lambda r: r[0])


def _row_windows(anchor_tops: list[float]) -> list[tuple[int, int]]:
    """Each row's own [lo, hi) crop window -- the midpoint between it and
    its neighbours, or half the page's own median pitch beyond the
    first/last anchor (never all the way to the page top/bottom -- see
    module docstring for why the last row's own window is deliberately
    capped this way)."""
    if not anchor_tops:
        return []
    if len(anchor_tops) >= 2:
        gaps = [b - a for a, b in zip(anchor_tops, anchor_tops[1:])]
        pitch = sorted(gaps)[len(gaps) // 2]
    else:
        pitch = _DEFAULT_PITCH
    windows = []
    for i, a in enumerate(anchor_tops):
        lo = anchor_tops[i - 1] if i > 0 else a - pitch
        hi = anchor_tops[i + 1] if i < len(anchor_tops) - 1 else a + pitch
        lo = int((lo + a) / 2)
        hi = int((a + hi) / 2)
        windows.append((lo, hi))
    return windows


async def _ocr_cell(img, name: str, lo: int, hi: int) -> str:
    w = img.width
    x0, x1 = _col_bounds(w, name)
    # A small inward pad on every edge keeps the ruled border lines
    # themselves out of the crop -- confirmed directly on the sample file
    # that a wider pad clips the first glyph of a column that sits flush
    # against its own left border (e.g. FUNCTIONAL_LOCATION/EQUIPMENT_TEXT),
    # while no pad at all lets the border line itself OCR as a stray
    # leading/trailing "I"/"|" token.
    x0 += 6
    x1 -= 6
    lo2 = lo + _ROW_PAD_PX
    hi2 = hi - _ROW_PAD_PX
    if hi2 <= lo2 or x1 <= x0:
        return ""
    crop = img.crop((x0, lo2, x1, hi2))
    text = await ocr_text(crop, psm=7)
    return text.strip()


def _clean(name: str, raw: str) -> str:
    if name == "UNIT":
        # Not anchored (^...$) here -- a right-border-line sliver
        # occasionally survives as trailing junk after a correctly-read
        # "DAY"/"FH"/"FC" token (e.g. "FH |"), confirmed directly on the
        # sample file; searching for the real token anywhere in the
        # cleaned string recovers it rather than leaving the whole cell
        # unmatched over one stray trailing character.
        m = _UNIT_RE_LOOSE.search(raw.strip(_CODE_STRIP_CHARS).upper().replace(" ", ""))
        return m.group(1) if m else raw.strip(_CODE_STRIP_CHARS).upper()
    if name == "REM_LIFE":
        m = _INT_TOKEN_RE.search(raw.replace(" ", ""))
        return m.group(0).replace(",", "") if m else ""
    if name == "END_DATE":
        m = _DATE_TOKEN_RE.search(raw)
        if not m:
            return ""
        dd, mm, yyyy = m.groups()
        return f"{int(dd):02d}.{int(mm):02d}.{yyyy}"
    if name == "INTERVAL":
        # See module docstring -- strip the internal gap between the
        # letter-code and its numeric value to match the born-digital
        # sibling's own canonical no-space shape.
        return re.sub(r"\s+", "", raw.strip(_CODE_STRIP_CHARS)).upper()
    if name in ("FUNCTIONAL_LOCATION", "PART_NUMBER", "SERIAL_NUMBER"):
        # These are always a single token with no internal space in the
        # source (same shape the born-digital sibling's own docstring
        # describes) -- a stray ruled-border-line sliver in the blank
        # remainder of the cell occasionally OCRs as its own separate
        # "word" (e.g. a lone leading "|" from the cell's own left border,
        # or a trailing "— ssi" after a real gap), confirmed directly
        # on the sample file. Keeping only the first token that survives
        # stripping the same border-noise characters drops that noise
        # rather than trying to guess which trailing characters are real
        # -- checking every token (not just the first) matters here since
        # the noise token can come before the real one, not just after it.
        for tok in raw.strip().split(" "):
            cleaned = tok.strip(_CODE_STRIP_CHARS)
            if cleaned:
                return cleaned
        return ""
    if name == "EQUIPMENT_TEXT":
        # Deliberately NOT _CODE_STRIP_CHARS here -- that set includes
        # "()", which this free-text column's own real values sometimes
        # end with (e.g. "SERVO CONTROL AILERON (OUB)"); confirmed
        # directly on the sample file that stripping it ate a genuine
        # trailing ")" off several real rows. Only whitespace is trimmed.
        return " ".join(raw.split())
    return raw.strip()


async def _parse_header(pdf_path: str) -> dict:
    meta = {k: "" for k in _HEADER_FIELDS}
    img = await render_page(pdf_path, 0, dpi=_OCR_DPI)
    w, h = img.size
    crop = img.crop((0, int(h * 0.06), w, int(h * 0.20)))
    text = await ocr_text(crop, psm=6)

    m = _TITLE_RE.search(text)
    if m:
        meta["AC_REG"] = m.group(1).strip(_CODE_STRIP_CHARS).upper()
        meta["AC_FH"] = m.group(2).strip()
        meta["AC_FC"] = m.group(3).strip()
    m2 = _DATE_TIME_RE.search(text)
    if m2:
        meta["REPORT_DATE"] = m2.group(1).strip()
        meta["REPORT_TIME"] = m2.group(2).strip()
    return meta


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback (see
    sheet_types/ht.py) -- this variant's SIGNATURES is deliberately empty
    (see module docstring).

    Requires BOTH the page title's own "HT-COMPONENT" phrase (ASCII
    hyphen, no "STATUS", no leading space -- checked directly against
    ht_component_status_dual_unit_grid_scanned.py's own "HT COMPONENT
    STATUS"/mpd_service_interval_status.py's own "HT ‐ COMPONENT
    STATUS" ocr_detect() anchors, neither a match for this phrase in
    either direction) AND the table's own "Functional Location" column-
    header phrase -- checked against every ocr_detect() anchor and every
    SIGNATURES list in occm.py/ht.py/llp.py and every existing
    occm_variants/ht_variants/llp_variants module (including a plain grep
    for "FUNCTIONAL" and "HT-COMPONENT"); no collision found for this
    specific combination."""
    try:
        img = await render_page(pdf_path, 0, dpi=_OCR_DPI)
        w, h = img.size
        crop = img.crop((0, int(h * 0.06), w, int(h * 0.30)))
        text = (await ocr_text(crop, psm=6)).upper()
        has_title = "HT-COMPONENT" in text or "HT COMPONENT" in text
        has_header = "FUNCTIONAL" in text and "LOCATION" in text
        return has_title and has_header
    except Exception:
        return False


async def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    header_meta = await _parse_header(pdf_path)
    n_pages = await page_count(pdf_path)

    for page_index in range(n_pages):
        img = await render_page(pdf_path, page_index, dpi=_OCR_DPI)

        anchors = await _anchor_rows(img)
        windows = _row_windows([top for top, _ in anchors])

        for (lo, hi), (_, anchor_text) in zip(windows, anchors):
            row: dict[str, str] = {"FUNCTIONAL_LOCATION": anchor_text}
            for _, _, name in _COLUMNS:
                if name == "FUNCTIONAL_LOCATION":
                    continue
                raw = await _ocr_cell(img, name, lo, hi)
                row[name] = _clean(name, raw)

            row["_page"] = page_index + 1
            row.update(header_meta)
            records.append(row)

    return records
