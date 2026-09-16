"""OCCM Status Listing (ATA/Zone/FIN, born-digital, word-position-aware) --
confirmed via a direct pdfplumber pass over the real sample file:
`extract_words()` returns full content on every page, no OCR needed.
Synchronous `extract()`.

Header block (repeats verbatim at the top of every page, wrapped across
three lines followed by a two-line-wrapped column-header row)::

    <Aircraft Type> TSN : <hours> FH
    MSN - <msn> CSN : <cycles>
    EFFECTIVITY NO: <n> STATUS AS OF <date>
    OCCM STATUS LISTING
    Zone FIN Description Part Number Serial Number Date of Installation TSN CSN

Parsed once from the first page and stamped on every row, same convention
this project's other header-plus-body OCCM variants use.

Row grain: one row per tracked component. Columns as printed, left to
right -- but the printed column-header line only names six of the eight
values actually present on each data row::

    <Item> <ATA> [Zone] [FIN] Description... Part Number Serial Number
    Date of Installation TSN CSN

ITEM (a sequential, zero-padded 4-digit row counter, occasionally suffixed
with a trailing letter for a sub-item or a "+<n>" for an inserted row, or
printed as "IA-<nn>" on a few pages for items added outside the main
numbering) and ATA (the 2-digit ATA chapter) both print at fixed x0
positions on every row (confirmed directly: x0 106500/1000pt-stable
across the whole real sample) but are NOT named in the column-header line
above -- the header line's own leftmost label ("Zone") actually applies to
the THIRD value on the row, not the first two. This is a genuine header/
data mismatch in the source report, not an extraction bug -- confirmed
directly by cross-checking the ATA values against known ATA chapter
numbers (e.g. 21 = air conditioning, 27 = flight controls, 32 = landing
gear) and the "Zone" values against known airframe zone-numbering ranges.

ZONE and FIN are each independently and legitimately blank on plenty of
real rows (confirmed directly: ZONE blank on ~4.4% of rows, FIN blank on
~5.5%) -- so the two can't be told apart by column position alone when
only one of the pair is printed. Told apart instead by content: ZONE is
always purely numeric when present (confirmed: every real ZONE value
matches `^\\d+$`), while FIN always carries at least one letter -- so the
leading token in the Zone/FIN span (if any) is ZONE only when it is
purely numeric; everything after that (or the whole span, if the leading
token isn't purely numeric) is FIN. FIN itself is occasionally two
space-separated tokens on this template (confirmed: a bay/sub-slot
compound code on a handful of real rows) -- joined as one FIN value
rather than split further.

DESCRIPTION, PART_NUMBER, SERIAL_NUMBER and the trailing TSN/CSN pair each
print at their own fixed x0 band (confirmed directly across the whole real
sample, clean gaps between every band, no data-row line wrapping anywhere
in the sample -- unlike this package's other OCCM word-geometry variants,
every row here is exactly one physical line), so the split is done purely
by each word's x0 falling in its band rather than by token count -- this
naturally absorbs the variable-width ZONE/FIN span above without needing
per-row token-count branching for the columns after it.

INSTALLATION_DATE is `D-Mon-YYYY`-shaped on the overwhelming majority of
rows, but a handful of real rows on the same template print it with plain
spaces instead of hyphens and/or a full month name with a trailing comma
(e.g. "27 AUG 1015", "27 July, 2015") -- confirmed directly; one of these
even carries an implausible year ("1015"), which is left as-is and flagged
by validation rather than silently "corrected" to a guessed value, per
this project's "never guess a wrong split" convention. All date tokens in
the field's own x0 band are joined into one INSTALLATION_DATE string
regardless of internal separator, so both shapes land in the same column.

TSN/CSN are plain integers, or the placeholder "UNK"/"UKN" seen throughout
the real sample where a figure isn't tracked for that component (both
spellings confirmed directly -- "UKN" is a genuine, distinct sentinel on
this template, not a typo of "UNK", so both are accepted rather than
normalized into each other).

Known limitation, confirmed directly on the real sample file: it has no
narrative/signature page anywhere in it (every physical line on every page
is either the repeating header block, a data row, or a page-footer "N of
NN" marker) -- there is nothing to guard against on that front for this
particular template.
"""
from __future__ import annotations
import re

import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "OCCM Status Listing (ATA/Zone/FIN)"
SIGNATURES = [
    "Zone FIN Description Part Number Serial Number",
    "OCCM STATUS LISTING",
]

CANONICAL_COLUMNS = [
    "ITEM",
    "ATA",
    "ZONE",
    "FIN",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "INSTALLATION_DATE",
    "TSN",
    "CSN",
    # Header metadata -- same on every row of a given file.
    "AIRCRAFT_TYPE",
    "AIRCRAFT_TSN",
    "MSN",
    "AIRCRAFT_CSN",
    "EFFECTIVITY_NO",
    "REFERENCE_DATE",
]

_NUM_OR_UNK = r"^(?:UNK|UKN|\d+)$"
_DATE_PATTERN = r"^\d{1,2}[\-\s][A-Za-z]{3,9},?[\-\s]\d{4}$"
_OVERRIDES = {
    "ITEM": {"pattern": r"^(?:\d{4}[A-Z]?(?:\+\d+)?|IA-\d{2,3})$"},
    "ZONE": {"allow_empty": True},
    "FIN": {"allow_empty": True},
    "INSTALLATION_DATE": {"pattern": _DATE_PATTERN},
    "TSN": {"pattern": _NUM_OR_UNK, "allow_empty": True},
    "CSN": {"pattern": _NUM_OR_UNK, "allow_empty": True},
    "AIRCRAFT_TYPE": {"allow_empty": True},
    "AIRCRAFT_TSN": {"pattern": _NUM_OR_UNK, "allow_empty": True},
    "MSN": {"pattern": r"^[A-Z0-9]+$", "uppercase": True, "allow_empty": True},
    "AIRCRAFT_CSN": {"pattern": r"^[A-Z0-9]+$", "uppercase": True, "allow_empty": True},
    "EFFECTIVITY_NO": {"allow_empty": True},
    "REFERENCE_DATE": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# --- Row anchor -------------------------------------------------------------
_ITEM_RE = re.compile(r"^(?:\d{4}[A-Z]?(?:\+\d+)?|IA-\d{2,3})$")
_ATA_RE = re.compile(r"^\d{2}$")
_DIGIT_RE = re.compile(r"^\d+$")

_HEADER_PREFIXES = (
    "TSN", "MSN -", "MSN-", "EFFECTIVITY", "OCCM STATUS LISTING",
    "Date of", "Zone FIN", "Installation",
)
_FOOTER_RE = re.compile(r"^\d+\s+of\s+\d+$")

# Fixed x0 bands, confirmed directly against the real sample file (see
# module docstring). Each band is [lo, hi).
_ATA_X_MIN, _ATA_X_MAX = 85.0, 100.0
_MID_X_MAX = 182.0          # Zone/FIN span ends just before Description
_DESC_X_MAX = 347.0         # Description ends just before Part Number
_PN_X_MAX = 450.0           # Part Number ends just before Serial Number
_SN_X_MAX = 533.0           # Serial Number ends just before the date column
_DATE_X_MAX = 600.0         # Date ends just before TSN
_TSN_X_MAX = 625.0          # TSN ends just before CSN

_META_RE_1 = re.compile(r"^(?P<type>\S+)\s+TSN\s*:\s*(?P<tsn>\S+)\s+FH", re.MULTILINE)
_META_RE_2 = re.compile(r"MSN\s*-\s*(?P<msn>\S+)\s+CSN\s*:\s*(?P<csn>\S+)")
_META_RE_3 = re.compile(
    r"EFFECTIVITY\s+NO:\s*(?P<eff>\S+)\s+STATUS\s+AS\s+OF\s+(?P<date>\S+)"
)


def _parse_meta(text: str) -> dict:
    meta: dict[str, str] = {}
    m = _META_RE_1.search(text)
    if m:
        meta["AIRCRAFT_TYPE"] = m.group("type")
        meta["AIRCRAFT_TSN"] = m.group("tsn")
    m = _META_RE_2.search(text)
    if m:
        meta["MSN"] = m.group("msn")
        meta["AIRCRAFT_CSN"] = m.group("csn")
    m = _META_RE_3.search(text)
    if m:
        meta["EFFECTIVITY_NO"] = m.group("eff")
        meta["REFERENCE_DATE"] = m.group("date")
    return meta


def _group_lines(words: list[dict]) -> list[dict]:
    """Cluster words into physical lines by y-position, tolerant of
    sub-point 'top' jitter between words nominally on the same line."""
    ws = sorted(words, key=lambda w: (w["top"], w["x0"]))
    lines: list[dict] = []
    for w in ws:
        if lines and abs(w["top"] - lines[-1]["top"]) <= 3.0:
            lines[-1]["words"].append(w)
            lines[-1]["top"] = (lines[-1]["top"] + w["top"]) / 2
        else:
            lines.append({"top": w["top"], "words": [w]})
    return lines


def _parse_row(words: list[dict]) -> dict | None:
    ws = sorted(words, key=lambda w: w["x0"])
    if not ws or not _ITEM_RE.match(ws[0]["text"]):
        return None
    if len(ws) < 2 or not _ATA_RE.match(ws[1]["text"]):
        return None
    item = ws[0]["text"]
    ata = ws[1]["text"]

    mid = [w["text"] for w in ws if _ATA_X_MAX <= w["x0"] < _MID_X_MAX]
    if mid and _DIGIT_RE.match(mid[0]):
        zone = mid[0]
        fin = " ".join(mid[1:])
    else:
        zone = ""
        fin = " ".join(mid)

    description = " ".join(w["text"] for w in ws if _MID_X_MAX <= w["x0"] < _DESC_X_MAX)
    part_number = " ".join(w["text"] for w in ws if _DESC_X_MAX <= w["x0"] < _PN_X_MAX)
    serial_number = " ".join(w["text"] for w in ws if _PN_X_MAX <= w["x0"] < _SN_X_MAX)
    installation_date = " ".join(w["text"] for w in ws if _SN_X_MAX <= w["x0"] < _DATE_X_MAX)
    tsn = " ".join(w["text"] for w in ws if _DATE_X_MAX <= w["x0"] < _TSN_X_MAX)
    csn = " ".join(w["text"] for w in ws if w["x0"] >= _TSN_X_MAX)

    if not description or not part_number:
        return None

    return {
        "ITEM": item,
        "ATA": ata,
        "ZONE": zone,
        "FIN": fin,
        "DESCRIPTION": description,
        "PART_NUMBER": part_number,
        "SERIAL_NUMBER": serial_number,
        "INSTALLATION_DATE": installation_date,
        "TSN": tsn,
        "CSN": csn,
    }


def _extract_page(page) -> list[dict]:
    words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
    if not words:
        return []
    lines = _group_lines(words)
    rows = []
    for line in lines:
        ws = sorted(line["words"], key=lambda w: w["x0"])
        text = " ".join(w["text"] for w in ws).strip()
        if not text:
            continue
        if any(text.startswith(p) for p in _HEADER_PREFIXES):
            continue
        if _FOOTER_RE.match(text):
            continue
        row = _parse_row(ws)
        if row is not None:
            rows.append(row)
    return rows


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    meta: dict[str, str] = {}
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            if page_num == 1:
                meta = _parse_meta(page.extract_text() or "")
            for row in _extract_page(page):
                row.update(meta)
                row["_page"] = page_num
                records.append(row)
    return records
