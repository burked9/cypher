"""AMOS "Aircraft-Ext-Equipment-List" report — scanned copy, no usable text
layer at all (confirmed directly: pdfplumber `extract_text()` returns 0
characters on every page of the sample file).

Same AMOS reporting family as `amos.py`/`amos_scanned.py` in this package
(the page footer prints "produced by AMOS www.swiss-as.com" on every page
of the sample), but a DIFFERENT export template from either of those two
siblings — this one's own title line reads "Aircraft-Ext-Equipment-List"
(not "Aircraft Equipment List Report"), and its column layout carries six
trailing numeric fields (own header labels: "TAHInst", "TACInst", "Tsl",
"Cst", "TSN", "CSN") rather than the siblings' own trailing TSN/CSN pair
alone, so neither sibling's `SIGNATURES`/`ocr_detect()` fires on it
(confirmed directly, both ways). No other module in this package's
`ht_variants`/`occm_variants`/`llp_variants` anchors on "TAHInst"/
"TACInst" or "Aircraft-Ext-Equipment-List" (checked directly via grep).

Header block (repeats near-identically at the top of every page)::

    <operator wordmark> Aircraft-Ext-Equipment-List   <time> | Page <n>/<n>
                                                        <operator legal name>
    Aircraft-Equipment-List of Aircraft <type> S/N <serial>
    Only rotables with requirements with subtrees, group by 2 char. on ATA-Chapter

The generation date sits in the page's own top-right corner (e.g.
"12.Jun.2014") but OCRs inconsistently page to page (confirmed directly —
sometimes cut off, sometimes misread) so it is treated as best-effort
metadata, not a strict field. The operator wordmark/legal-name line and the
"Aircraft <type> S/N <serial>" line are both genuine per-file identifying
data (not written into this module's source anywhere) and are parsed into
row metadata at runtime, same as this package's other per-file
header-metadata extraction elsewhere.

Main table, one plain (unruled, no drawn grid lines — confirmed directly
via a numpy vertical/horizontal divider-pixel scan on the sample, which
found no consistent line positions) positional header row::

    ATA | Partno | Serialno | Description | Con. | Pos. |
    Releaseno/Labelno | Inst-Date | TAHInst | TACInst | Tsl | Cst | TSN | CSN

Each equipment row is immediately followed by 1-3 HT-continuation lines
(a task name like "HYDROSTATIC TEST"/"LIFE LIMITER REPLACEMENT"/"BENCH
TEST"/"OVERHAUL" plus its own interval/due-date/remaining figures) — same
continuation-block shape `amos_scanned.py`'s own docstring describes for
its sibling template. Those aren't required for this project's downstream
use (position fingerprint of HT components per airframe family) and OCR
badly on the sample (small print, no ruled lines to anchor individual
sub-fields), so this module does not attempt to parse them — only the main
equipment row's own 14 columns are extracted.

Row anchoring: SERIAL_NUMBER (not INST_DATE) is used as the per-row Y
anchor. Confirmed directly necessary, not just a style choice: an
INST-DATE-anchored pass genuinely loses real rows on the sample two
different ways —

  * **Tesseract's own line-dedup quirk** (this package's usual concern —
    see e.g. `mm510_scanned.py`'s own docstring): two adjacent rows sharing
    the exact same INST-DATE string (e.g. two fire extinguishers both
    installed "01.Apr.2008") come back as a single OCR'd token spanning
    both rows' own Y positions, silently dropping one of the two real
    rows from a whole-column INST-DATE pass.
  * **A mid-token OCR split specific to this column**: a leading day digit
    is occasionally torn into its own token, separate from the following
    "<Mon>.<year>" token (e.g. "2.Nov.2010" -> "2." + "Nov.2010" as two
    distinct OCR word boxes) — confirmed directly on the sample — which
    fails a single-token anchor match outright even though the date is
    perfectly legible once both fragments are looked at together.

SERIAL_NUMBER was confirmed directly on the sample to avoid both failure
modes (every real row's own serial number is a distinct string, so there
is nothing for the OCR dedup quirk to collapse, and it never wraps across
two word boxes) while still being present on effectively every real data
row. A raw candidate is accepted as a row anchor when its own OCR text
(after stripping border/leader noise) is at least 3 characters and
contains at least one digit — confirmed directly this admits every real
serial number in the sample while rejecting stray short noise fragments.

Column X-boundaries below are fixed fractions of the rendered page's own
width, measured directly from a real per-word OCR pass restricted to
several individual data rows' own thin Y-bands (the column-header row's
own text was confirmed unreliable for this — a per-word OCR pass of the
header row's own Y-band merges several of its own short/adjacent header
labels into single glued tokens, unlike the data rows below it, which
space out cleanly enough to OCR each column's own leading edge
correctly). Column widths are NOT re-derived per page at runtime — the
sample's pages all render at the same size, so the fractions stay aligned
without a per-page recalibration pass, same technique as this package's
other fixed-fraction OCR variants (`mm510_scanned.py`,
`al_development_controlled_items_list_scanned.py`).

DESCRIPTION is genuinely truncated at a fixed print width by the source
report itself (confirmed directly: the same truncation, e.g. "EMERGENCY
LOCA" for what is presumably "EMERGENCY LOCATOR TRANSMITTER", is present
in a plain whole-page OCR pass too, not just this module's own narrower
column crop) — this module does not attempt to reconstruct the truncated
tail, per this project's "never guess a wrong split" convention.

ATA is blank on every row after a section's own first row in the source
(confirmed directly) and is forward-filled here from the most recent row
where it was present, same convention as this package's other per-section
HT variants (e.g. `mm510_scanned.py`).

Numeric columns (TAH_INST/TAC_INST/TSI/CSI/TSN/CSN) are reduced to only
their own matching digit-run substring rather than passed through raw, per
this project's "never guess a wrong split" convention — a dropped stray
OCR artifact (a border-bleed fragment, a misread bracket) is preferred
over a confidently-wrong value. A handful of real rows in the sample carry
the literal source value "UNKNOWN" in TSN/CSN instead of a number (OCR
reads it noisily, e.g. "NKNOWN"/"INKNOWN" — confirmed directly this is a
genuine source value, not scan noise, since it recurs consistently on
rows the surrounding fields mark as freshly installed with no prior
usage) — that literal is recognised and preserved (case-normalised) rather
than discarded as unparseable.

Sensitivity note: the sample file's own header carries a real operator
wordmark/legal name and a real aircraft type/serial — none of that is
written into this module's source/comments anywhere (only the generic
column-header/title/label phrases the template itself prints, which are
not document-specific, appear above). Those header fields ARE extracted
into row data at runtime (ordinary functional per-file header-metadata
capture, ordinary code, not a hardcoded value), same as this package's
other per-file header extraction elsewhere.
"""
from __future__ import annotations
import re

from sheet_types.ht_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, ocr_words, page_count

NAME = "AMOS Aircraft-Ext-Equipment-List (Scanned)"

# Deliberately empty -- the known source files have no text layer at all
# (confirmed: 0 pdfplumber-extractable chars on every page), so this module
# is only ever reached via ocr_detect()'s blank-text fallback below, never
# the router's normal pdfplumber-text SIGNATURES match. Neither AMOS
# sibling in this package (`amos.py`'s born-digital "Aircraft Equipment
# List Report" SIGNATURES, `amos_scanned.py`'s own differently-shaped OCR
# fallback) fires on this template's own title/column layout (confirmed
# directly both ways) -- see module docstring.
SIGNATURES: list[str] = []

CANONICAL_COLUMNS = [
    "ATA",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
    "CON",
    "POS",
    "RELEASE_LABEL",
    "INST_DATE",
    "TAH_INST",
    "TAC_INST",
    "TSI",
    "CSI",
    "TSN",
    "CSN",
    # Header metadata -- parsed once per file (whichever page OCRs
    # cleanest first), stamped on every row.
    "OPERATOR",
    "AIRCRAFT_TYPE",
    "AIRCRAFT_SN",
    "REPORT_DATE",
]

_DATE_RE = r"^\d{1,2}[.\-][A-Za-z0][A-Za-z]{2}[.\-]\d{2,4}$"
_INT_OR_UNKNOWN_RE = r"^(?:\d+|UNKNOWN)$"

_OVERRIDES = {
    "PART_NUMBER": {"allow_empty": True},
    "SERIAL_NUMBER": {"allow_empty": True},
    "DESCRIPTION": {"allow_empty": True, "uppercase": True},
    "CON": {"pattern": r"^[A-Z]{1,4}$", "allow_empty": True, "uppercase": True},
    "POS": {"allow_empty": True, "uppercase": True},
    "RELEASE_LABEL": {"allow_empty": True},
    "INST_DATE": {"pattern": _DATE_RE, "allow_empty": True},
    "TAH_INST": {"pattern": _INT_OR_UNKNOWN_RE, "allow_empty": True},
    "TAC_INST": {"pattern": _INT_OR_UNKNOWN_RE, "allow_empty": True},
    "TSI": {"pattern": _INT_OR_UNKNOWN_RE, "allow_empty": True},
    "CSI": {"pattern": _INT_OR_UNKNOWN_RE, "allow_empty": True},
    "TSN": {"pattern": _INT_OR_UNKNOWN_RE, "allow_empty": True},
    "CSN": {"pattern": _INT_OR_UNKNOWN_RE, "allow_empty": True},
    # Header metadata -- a single OCR misread here shouldn't flag every row
    # of the file, same reasoning this package's other header-plus-body OCR
    # variants use.
    "OPERATOR": {"allow_empty": True},
    "AIRCRAFT_TYPE": {"allow_empty": True},
    "AIRCRAFT_SN": {"allow_empty": True},
    "REPORT_DATE": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_DPI = 300

# Column X-boundaries, as a fraction of the rendered page's own width -- see
# module docstring for how these were derived (a fixed-fraction layout, not
# a per-page divider-line scan -- this template has no ruled grid lines).
_COLUMNS = [
    (0.00000, 0.08200, "ATA"),
    (0.08200, 0.17800, "PART_NUMBER"),
    (0.17800, 0.28300, "SERIAL_NUMBER"),
    (0.28300, 0.39300, "DESCRIPTION"),
    (0.39300, 0.41500, "CON"),
    (0.41500, 0.44000, "POS"),
    (0.44000, 0.54800, "RELEASE_LABEL"),
    (0.54800, 0.60800, "INST_DATE"),
    (0.60800, 0.67700, "TAH_INST"),
    (0.67700, 0.74700, "TAC_INST"),
    (0.74700, 0.79400, "TSI"),
    (0.79400, 0.84400, "CSI"),
    (0.84400, 0.89500, "TSN"),
    (0.89500, 1.00000, "CSN"),
]
_COLUMN_NAMES = [name for _, _, name in _COLUMNS]

_TEXT_JOIN_COLS = {"DESCRIPTION", "POS"}
_CODE_COLS = {"PART_NUMBER", "SERIAL_NUMBER", "ATA", "CON", "RELEASE_LABEL"}
_DATE_COLS = {"INST_DATE"}
_NUM_COLS = {"TAH_INST", "TAC_INST", "TSI", "CSI", "TSN", "CSN"}

_STRIP_CHARS = " _|\"'`‘’“”()[]{}<>=~.,;:"
_DATE_TOKEN_RE = re.compile(r"\d{1,2}\s*[.\-]?\s*[A-Za-z0][A-Za-z]{2}\s*[.\-]\s*\d{2,4}")
_INT_TOKEN_RE = re.compile(r"\d+")
_UNKNOWN_RE = re.compile(r"^[IN]{0,2}[UN]?KNOWN$", re.IGNORECASE)

# Row-anchor shape check (SERIAL_NUMBER column) -- see module docstring for
# why this column, not INST_DATE, is the primary per-row Y anchor here.
_SN_MIN_LEN = 3


def _has_digit(s: str) -> bool:
    return any(c.isdigit() for c in s)


def _col_bounds(w: int, name: str) -> tuple[int, int]:
    for lo, hi, col in _COLUMNS:
        if col == name:
            return int(lo * w), int(hi * w)
    raise KeyError(name)


async def _ocr_column(img, name: str, y0: int, y1: int) -> list[tuple[float, str]]:
    """OCR one column's full-height strip and return (top, text) pairs in
    original-image page coordinates."""
    x0, x1 = _col_bounds(img.width, name)
    if y1 <= y0:
        return []
    crop = img.crop((x0, y0, x1, y1))
    words = await ocr_words(crop, psm=6, min_conf=-1)
    out = []
    for wd in words:
        text = str(wd.get("text", "")).strip()
        if not text:
            continue
        out.append((y0 + wd["top"], text))
    return out


def _clean_field(name: str, tokens: list[str]) -> str:
    if name in _NUM_COLS:
        found: list[str] = []
        joined = " ".join(tokens)
        for t in tokens:
            if _UNKNOWN_RE.match(t.strip(_STRIP_CHARS).upper()):
                return "UNKNOWN"
        found.extend(_INT_TOKEN_RE.findall(joined))
        found = list(dict.fromkeys(found))
        return max(found, key=len) if found else ""
    if name in _DATE_COLS:
        joined = " ".join(tokens)
        m = _DATE_TOKEN_RE.search(joined)
        if not m:
            return ""
        # Normalise stray internal whitespace introduced by a mid-token OCR
        # split (see module docstring) back into the plain dotted form.
        return re.sub(r"\s+", "", m.group(0))
    sep = " " if name in _TEXT_JOIN_COLS else ""
    text = sep.join(t.strip() for t in tokens)
    text = " ".join(text.split())
    if name in _CODE_COLS:
        text = text.strip(_STRIP_CHARS)
    return text


_HEADER_FIELDS = ["OPERATOR", "AIRCRAFT_TYPE", "AIRCRAFT_SN", "REPORT_DATE"]

# Un-obscured title fragment -- checked directly (grep) against every
# SIGNATURES list and every ocr_detect()/SIGNATURES anchor string in
# occm_variants/ht_variants/llp_variants: unique to this module.
_TITLE_RE = re.compile(r"Aircraft\s*-?\s*(?:Ext\s*-?\s*)?Equipment\s*-?\s*List", re.IGNORECASE)
_AIRCRAFT_RE = re.compile(
    r"Aircraft\s+([A-Za-z0-9]{2,10})\s*S\s*/\s*N\s*([A-Za-z0-9]{2,12})",
    re.IGNORECASE,
)
# Generic "<name> GmbH"-style operator legal-name line -- "GmbH" is a
# generic German business-entity suffix (like "Ltd"/"Inc"), not specific to
# any one operator, so this regex itself carries nothing corpus-specific.
_OPERATOR_RE = re.compile(r"([A-Za-z][A-Za-z0-9 .&-]{1,40}\bGmbH\b)")
_REPORT_DATE_RE = re.compile(r"(\d{1,2}\.[A-Za-z]{3}\.\d{4})")

# This template's own distinctive trailing-column header fragment --
# checked directly (grep) against every SIGNATURES list and every
# ocr_detect()/SIGNATURES anchor string in occm_variants/ht_variants/
# llp_variants: unique to this module (see module docstring).
_HEADER_COL_RE = re.compile(r"TAH\s*Inst.{0,20}TAC\s*Inst", re.IGNORECASE)


async def _parse_header(img) -> dict:
    meta = {k: "" for k in _HEADER_FIELDS}
    w, h = img.size
    crop = img.crop((0, 0, w, int(h * 0.22)))
    text = await ocr_text(crop, psm=6)

    m = _AIRCRAFT_RE.search(text)
    if m:
        meta["AIRCRAFT_TYPE"] = m.group(1).strip()
        meta["AIRCRAFT_SN"] = m.group(2).strip()
    m = _OPERATOR_RE.search(text)
    if m:
        meta["OPERATOR"] = " ".join(m.group(1).split())
    m = _REPORT_DATE_RE.search(text)
    if m:
        meta["REPORT_DATE"] = m.group(1).strip()
    return meta


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback (see
    sheet_types/ht.py) -- this variant's SIGNATURES is deliberately empty
    (see module docstring).

    Requires BOTH the "Aircraft(-Ext)-Equipment-List" title fragment AND
    the table's own "TAHInst ... TACInst" column-header fragment -- the
    paired check matters since the title fragment alone risks collision
    with this package's other AMOS siblings' own broader "Equipment List"
    phrasing; the TAHInst/TACInst combination specifically is what the
    module-docstring grep check confirmed is unique to this template."""
    try:
        img = await render_page(pdf_path, 0, dpi=_DPI)
        w, h = img.size
        crop = img.crop((0, 0, w, int(h * 0.22)))
        text = await ocr_text(crop, psm=6)
        if not _TITLE_RE.search(text):
            return False
        header_crop = img.crop((0, int(h * 0.20), w, int(h * 0.27)))
        header_text = (await ocr_text(header_crop, psm=6)).upper()
        normed = " ".join(header_text.split())
        return bool(_HEADER_COL_RE.search(normed))
    except Exception:
        return False


async def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    header_meta = {k: "" for k in _HEADER_FIELDS}
    n_pages = await page_count(pdf_path)

    # Data rows start just below the column-header row -- confirmed
    # directly at ~0.249 of page height at 300 DPI on the sample (the
    # header row's own text band ends there on every page checked).
    y0_frac = 0.249

    cur_ata = ""

    for page_index in range(n_pages):
        img = await render_page(pdf_path, page_index, dpi=_DPI)
        w, h = img.size
        y0 = int(h * y0_frac)
        y1 = h

        if not all(header_meta.values()):
            page_meta = await _parse_header(img)
            for k, v in page_meta.items():
                if v and not header_meta[k]:
                    header_meta[k] = v

        col_words: dict[str, list[tuple[float, str]]] = {}
        for name in _COLUMN_NAMES:
            col_words[name] = await _ocr_column(img, name, y0, y1)

        # SERIAL_NUMBER, not INST_DATE, is the primary row anchor -- see
        # module docstring for the two distinct ways an INST_DATE-anchored
        # pass was confirmed to lose real rows on the sample.
        raw_anchors = sorted(
            top for top, text in col_words["SERIAL_NUMBER"]
            if len(text.strip(_STRIP_CHARS)) >= _SN_MIN_LEN and _has_digit(text)
        )
        anchors: list[float] = []
        for a in raw_anchors:
            if anchors and a - anchors[-1] <= 30:
                continue
            anchors.append(a)

        for atop in anchors:
            row: dict[str, str] = {}
            for name in _COLUMN_NAMES:
                toks = [text for top, text in col_words[name]
                        if abs(top - atop) <= 30]
                row[name] = _clean_field(name, toks)

            if row["ATA"]:
                cur_ata = row["ATA"]
            else:
                row["ATA"] = cur_ata

            row["_page"] = page_index + 1
            row.update(header_meta)
            records.append(row)

    return records
