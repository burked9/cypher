"""MM_510 "HARD TIME/LLP COMPONENTS" report — scanned copy, A4-proportioned
page variant.

Same underlying MIS export family, header block, and column set as the
`mm510_scanned.py` sibling in this package (see its own docstring for the
shared header/column story, the landscape-in-portrait rotation handling,
the per-column-strip OCR rationale, and the INSTALL_DATE row-anchoring
approach — all of that carries over unchanged here). This sibling exists
because a real corpus file in this same report family renders at A4
page proportions rather than the US-Letter proportions that sibling's own
`_COLUMNS` table was calibrated against.

Confirmed directly on that A4 sample: after the same "rotate -90 if
height > width" normalization the sibling module applies, the rotated
page image comes out with a width:height ratio of roughly 1.41
(matching A4's own 210:297mm ratio), versus roughly 1.29 for a
US-Letter page rotated the same way. Reusing the Letter-calibrated
`_COLUMNS` fractions against an A4-proportioned render is not a small
misalignment — it is off by enough that the first (and narrowest) column,
ATA, lands entirely inside the sibling's own POSITION crop, so every row's
own ATA field comes back empty. The rest of the columns drift by a few
percentage points each, in inconsistent directions (some right, some
left) relative to the sibling's own boundaries, which is more consistent
with the printed table itself being scaled/repositioned as a whole for
the narrower page than with any single uniform offset — recalibrating a
fresh `_COLUMNS` table directly from this page shape's own real OCR word
positions (rather than nudging the existing constants) is what this
module does below.

Detection: this variant's own `ocr_detect()` requires the same paired
header-phrase/metadata check as the sibling (see that module's own
docstring for why the pairing matters) AND a rotated-page aspect ratio
above 1.35 — comfortably between the ~1.29 Letter ratio and ~1.41 A4
ratio confirmed above, so a Letter-shaped file of this same report
family is never claimed by this module, and an A4-shaped one is never
claimed by the sibling's own (aspect-blind) `ocr_detect()` so long as
this module is checked first in the router's `VARIANTS` order.

Column X-boundaries below are fresh, derived directly from a real
per-word OCR pass across several pages of the confirmed A4 sample
(header-label row positions plus several real data rows for the
narrower, more error-prone columns), using the same "midpoint of the
tightest observed gap between neighbouring columns' own real content"
method the sibling's own docstring describes. Two adjustments beyond a
plain midpoint pass, both confirmed directly against this sample:

  * POSITION/PART_NUMBER: a two-word POSITION value (e.g. "FWD LH")
    prints with only a few pixels of gap before the PART_NUMBER value
    that follows it -- close enough that a midpoint-of-average-gap
    boundary cuts through the second position word itself. The boundary
    is placed past that word's own real right edge instead, at the
    (much larger) gap that genuinely separates it from PART_NUMBER's own
    real content.

  * DESCRIPTION/TASK: this pair inherits the sibling's own known soft
    spot -- a long DESCRIPTION value with no TASK value on the same row
    (e.g. "EMERGENCY EVACUATION SL DISCARD") can still print a trailing
    word at an X-position close to where a short, genuine TASK value
    (e.g. "DISCARD" on a different, single-row component) starts. No
    fixed boundary separates these two real uses of the same X-range
    cleanly; the boundary here is placed to keep whole real words intact
    on both sides for the common case rather than to resolve this
    inherent ambiguity, which is the same tradeoff the sibling's own
    calibration already accepts for this report family.

This sample's rows are also not perfectly horizontal -- confirmed
directly by comparing one row's own OCR'd word-top values column by
column: a column's word-top drifts further from that same row's own
INSTALL_DATE word-top the further the column sits from INSTALL_DATE on
the X axis, in a relationship close to linear in each column's own X
position. `_predicted_skew()` below corrects each column's raw top for
this before the anchor-tolerance check runs; see its own comment for
the calibration and the tolerance this makes possible.

HT_FLAG/LLP_FLAG are fixed single-character cells in the source
template (confirmed directly: every genuine value is a lone "Y" or
"N"), but on this A4 scan tesseract's own per-column crop for these two
narrow columns picks up a stray extra character often enough to matter
(confirmed directly, e.g. "YI", "NS", "OOYY") -- almost certainly
antialiased bleed from the adjacent DESCRIPTION column's own leading
glyph at the crop edge, not a second real flag letter. This module's own
`_clean_field()` override takes the first Y/N-like character found
(after the sibling's own yen-glyph substitution) rather than leaving a
mixed token to be flagged as noise, since -- unlike the sibling's more
general-purpose columns -- this column's own true width can never
legitimately hold more than one character. A small residual of LLP_FLAG
values misread to a shape with no literal Y/N substring at all (e.g.
"1F", "I¢") survives this and is correctly left for RULES to flag rather
than guessed at.
"""
from __future__ import annotations
import re

from sheet_types.ht_variants._base import merged_rules
from sheet_types.ht_variants.mm510_scanned import (
    _get_page_image, _col_bounds as _sibling_col_bounds,
    _clean_field as _sibling_clean_field,
    _parse_header, _ANCHOR_RE, _FILLABLE,
    _HEADER_FIELDS, _YEN_RE, _CODE_STRIP_CHARS,
)
from shared.ocr_bridge import ocr_words, ocr_text, page_count

NAME = "MM_510 HARD TIME LLP Components (Scanned, A4)"

# Deliberately empty -- see module docstring. Detection happens
# structurally via ocr_detect() below, same pattern as the sibling
# mm510_scanned.py.
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
    # row of the file, same reasoning the sibling module uses.
    "TAIL_NUMBER":      {"allow_empty": True},
    "OPERATOR":         {"allow_empty": True},
    "TSN_TOTAL":        {"allow_empty": True},
    "CSN_TOTAL":        {"allow_empty": True},
    "LAST_FLIGHT_DATE": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Column X-boundaries, as a fraction of the rendered (rotated) A4 page's
# own width -- see module docstring for how these were derived. Do not
# reuse the sibling module's own _COLUMNS table here; it is calibrated
# for a different (Letter) page proportion and produces empty ATA fields
# on this shape (confirmed directly).
_COLUMNS = [
    (0.00000, 0.07110, "ATA"),
    (0.07110, 0.10890, "POSITION"),
    (0.10890, 0.16280, "PART_NUMBER"),
    (0.16280, 0.22550, "SERIAL_NUMBER"),
    (0.22550, 0.25550, "HT_FLAG"),
    (0.25550, 0.27050, "LLP_FLAG"),
    (0.27050, 0.38800, "DESCRIPTION"),
    (0.38800, 0.45440, "TASK"),
    (0.45440, 0.51430, "INSTALL_DATE"),
    (0.51430, 0.54810, "TSI_HOUR"),
    (0.54810, 0.57680, "TSI_CYCLE"),
    (0.57680, 0.60970, "TSI_DAY"),
    (0.60970, 0.65450, "LAST_DONE_DATE"),
    (0.65450, 0.70510, "DUE_DATE"),
    (0.70510, 0.74300, "INTERVAL_HOUR"),
    (0.74300, 0.77360, "INTERVAL_CYCLE"),
    (0.77360, 0.81060, "INTERVAL_DAY"),
    (0.81060, 0.85210, "REMAINING_HOUR"),
    (0.85210, 0.88350, "REMAINING_CYCLE"),
    (0.88350, 1.00000, "REMAINING_DAY"),
]

_FLAG_COLS = {"HT_FLAG", "LLP_FLAG"}

# HT_FLAG/LLP_FLAG are single-character columns by template definition
# (confirmed directly against the real sample: every genuine value in
# either column is a lone "Y" or "N" glyph). On this A4 scan, tesseract's
# per-column crop for these two narrow columns picks up a stray extra
# character often enough to matter (confirmed directly, e.g. "YI", "NS",
# "OOYY") -- almost certainly antialiased bleed from the adjacent
# DESCRIPTION column's own leading glyph at this column's crop edge,
# since the extra characters are never a second, different real flag
# letter repeated in a structured way. The sibling mm510_scanned.py's own
# _clean_field() only collapses a *repeated single* letter (e.g. "YY" ->
# "Y"); it deliberately leaves a mixed string like "YI" alone so the
# stricter downstream RULES pattern flags it as noise rather than
# guessing. That is the right call when the column's true width could
# plausibly hold more than one character, but this column can't (it's a
# fixed one-glyph cell in the source template) -- so here, once the yen-
# glyph substitution is applied, the first Y/N-like character found is
# taken as the value and anything else in the crop is dropped, rather
# than leaving the whole mixed token to be flagged as bad_format.
_FLAG_CHAR_RE = re.compile(r"[YN]")


def _clean_field(name: str, tokens: list[str]) -> str:
    if name in _FLAG_COLS:
        text = "".join(tokens).strip(_CODE_STRIP_CHARS)
        text = _YEN_RE.sub("Y", text).upper()
        m = _FLAG_CHAR_RE.search(text)
        return m.group(0) if m else text
    return _sibling_clean_field(name, tokens)


def _col_bounds(w: int, name: str) -> tuple[int, int]:
    for lo, hi, col in _COLUMNS:
        if col == name:
            return int(lo * w), int(hi * w)
    raise KeyError(name)


async def _ocr_column(img, name: str, y0: int, y1: int) -> list[tuple[float, str]]:
    """OCR one column's full-height strip and return (top, text) pairs in
    original-image page coordinates. Mirrors the sibling module's own
    helper of the same name, but reads this module's own _COLUMNS table
    via _col_bounds() above rather than the sibling's Letter-calibrated
    one."""
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


# Aspect-ratio gate -- see module docstring. Comfortably between the
# confirmed ~1.29 (Letter) and ~1.41 (A4) rotated-page ratios.
_MIN_A4_ASPECT = 1.35

# This A4 scan's rows are not perfectly horizontal -- confirmed directly
# by hand-checking a single real row's own word top-edges column by
# column: a column's OCR'd word-top drifts further from its own row's
# INSTALL_DATE word-top the further that column sits from INSTALL_DATE
# on the X axis (e.g. ATA, at the far left, reads ~29px "earlier" than
# its own row's INSTALL_DATE; REMAINING_HOUR, right of INSTALL_DATE,
# reads ~34px "later"), and the relationship is close to linear in each
# column's own X position (least-squares slope ~79px of top-drift per
# unit of page-width fraction, residuals within about +/-6px of that
# line across every column checked). The plain "sibling" INSTALL_DATE-
# anchor tolerance (see mm510_scanned.py) is calibrated for a page
# without this skew and is both too tight to catch the far columns on
# this one (e.g. ATA's own drift already exceeds it) and, if widened
# enough to catch them, wide enough to risk bleeding into a
# neighbouring row (confirmed directly: this file's own tightest
# observed row pitch is ~69px, barely more than twice the drift this
# page shows at its most skewed column) -- so each column's raw OCR top
# is corrected for its own predicted skew offset before the anchor
# tolerance check, rather than widening the tolerance itself.
_SKEW_SLOPE_PX_PER_FRAC = 79.0
_INSTALL_DATE_FRAC = (0.45440 + 0.51430) / 2

_COLUMN_FRAC = {name: (lo + hi) / 2 for lo, hi, name in _COLUMNS}


def _predicted_skew(name: str) -> float:
    return _SKEW_SLOPE_PX_PER_FRAC * (_COLUMN_FRAC[name] - _INSTALL_DATE_FRAC)


# Tolerance applied to the skew-corrected top, not the raw one. Set well
# under half this file's own tightest observed row pitch (~69px / 2 =
# ~34.5px) with headroom for the linear skew model's own residual error
# (confirmed directly, within about +/-6px per column) so a token is
# never pulled into a neighbouring row even at this file's tightest
# pitch, while still being generous enough to catch every column's own
# real value despite the skew.
_ANCHOR_TOLERANCE_PX_A4 = 16


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback (see
    sheet_types/ht.py). Requires the same paired header-phrase/metadata
    check as the sibling mm510_scanned.py's own ocr_detect(), plus a
    rotated-page aspect ratio confirming an A4-proportioned (not Letter)
    scan -- see module docstring for why the aspect gate is needed."""
    try:
        img = await _get_page_image(pdf_path, 0, dpi=300)
        w, h = img.size
        if w / h < _MIN_A4_ASPECT:
            return False
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
        # column-header row -- same offset the sibling module uses,
        # confirmed directly against this A4 sample too.
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
                skew = _predicted_skew(name)
                toks = [text for top, text in col_words[name]
                        if abs((top - skew) - atop) <= _ANCHOR_TOLERANCE_PX_A4]
                row[name] = _clean_field(name, toks)

            date_toks = [text for top, text in col_words["INSTALL_DATE"]
                         if abs(top - atop) <= _ANCHOR_TOLERANCE_PX_A4]
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
