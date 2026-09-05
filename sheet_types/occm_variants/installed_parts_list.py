"""Installed Parts List -- born-digital OCCM variant, real text layer,
confirmed via a direct pdfplumber pass over every page of one real sample
file (no OCR needed; extract() is synchronous).

Header block (repeats, with some noisy re-ordering/typos, at the top of
every page -- see below)::

    StatusASAT: <date>
    Technical Services Department
    <time>
    Technical Records UnitMSN: <msn>
    INSTALLED PARTS LIST
    Item: <aircraft type> UnitTSN: <n>
    Unit Name:
    UnitCSN: <n>
    <reg> serial: <msn>
    UnitDSN: <n>

Column header (repeats every page)::

    ItemNumber SerialNumber ItemDesc ATA Position InstalledDate Aircraft
    Aircraft TSN CSN

Confirmed real-file quirk: the header block re-renders slightly differently
(and with stray character glitches) on every page -- e.g. one page's
UnitMSN digit is misrendered as a different value than the rest of the
file, and the registration token grows a stray leading character on
another page. All confirmed-good header fields are therefore parsed once
from the FIRST page that yields a clean value for every field, then locked
in and stamped on every row for the rest of the file (matching this
project's header-parsing convention) -- later pages' header lines are never
consulted again once locked, so a one-off glitch on a later page can't
silently overwrite an already-good value.

Row shape -- confirmed exactly 8 whitespace/no-space-separated tokens on
every one of the 899 real data rows in the known sample (ITEM_DESC and
POSITION each render as a single pdfplumber "word" with no internal spaces
-- a font/kerning quirk of the source system, not a parsing artifact)::

    <pn> <sn> <desc> <ata> <position> <install_date> <ac_tsn> <ac_csn>

so rows are anchored purely by token count (exactly 8) plus a date-shaped
6th token, with no need for x-position column bucketing. ATA renders as a
two-part "<chapter>-<section>" token (e.g. "<ata>-<section>"), not a bare
chapter number -- validated against that shape rather than the generic
2-digit chapter pattern used elsewhere in this package (same convention as
occm_variants/iberia_listado.py and occm_variants/aircraft_rotables_report.py).

POSITION is a genuinely distinct field from ITEM_DESC -- not glued onto it
-- confirmed directly: ATA sits between them in the token stream on every
row, and POSITION's own values (e.g. "<desc-like text>_1", "_2", ...) are
plainly a separate, more specific sub-location label distinguishing
multiple installed instances of the same part, never a DESCRIPTION
fragment. No DESCRIPTION/POSITION split logic is therefore needed.

Confirmed rendering artifact: PART_NUMBER, SERIAL_NUMBER and POSITION
values frequently carry a single stray leading punctuation character with
no semantic meaning (e.g. a leading apostrophe on a PART_NUMBER, or a
leading "|"/"["/"]"/"}" on a POSITION value) -- confirmed by direct
inspection of the real sample: real values in these three columns always
otherwise start with an alphanumeric character, and the same handful of
stray lead characters recur across otherwise-unrelated rows/pages,
consistent with a font/table-border rendering glitch rather than real
data. A single leading run of non-alphanumeric characters is stripped from
these three fields before the shared cleanup pipeline runs (which then
also strips any remaining "|" and OCR_CHAR_MAP'd stray characters
per-field, e.g. a lone leading apostrophe).
"""
from __future__ import annotations
import re

import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "Installed Parts List"

SIGNATURES = [
    "INSTALLED PARTS LIST",
    "ItemNumber SerialNumber ItemDesc ATA Position",
]

CANONICAL_COLUMNS = [
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
    "ATA",
    "POSITION",
    "INSTALL_DATE",
    "AIRCRAFT_TSN",
    "AIRCRAFT_CSN",
    # Header metadata -- parsed once, stamped onto every row.
    "AS_OF_DATE",
    "MSN",
    "AIRCRAFT_TYPE",
    "AIRCRAFT_TSN_HEADER",
    "AIRCRAFT_CSN_HEADER",
    "AIRCRAFT_REG",
    "DSN",
]

_NUM_RULE = {"pattern": r"^\d+(?::\d+)?$", "allow_empty": True}
_OVERRIDES = {
    # This report's ATA renders as "<chapter>-<section>", not a bare 2-digit
    # chapter -- same convention as iberia_listado.py / aircraft_rotables_report.py.
    "ATA": {"pattern": r"^\d{2}-\d{2}$", "int_range": None},
    "POSITION": {"pattern": r"^[A-Z0-9][A-Z0-9,.()\-_/]*$", "allow_empty": True},
    "INSTALL_DATE": {"pattern": r"^\d{2}-\d{2}-\d{4}$", "allow_empty": True},
    "AIRCRAFT_TSN": _NUM_RULE,
    "AIRCRAFT_CSN": _NUM_RULE,
    "AS_OF_DATE": {"pattern": r"^\d{2}-\d{2}-\d{4}$", "allow_empty": True},
    "MSN": {"pattern": r"^\d{3,6}$", "allow_empty": True},
    "AIRCRAFT_TYPE": {"pattern": r"^[A-Z0-9\-]{2,12}$", "allow_empty": True},
    "AIRCRAFT_TSN_HEADER": _NUM_RULE,
    "AIRCRAFT_CSN_HEADER": _NUM_RULE,
    "AIRCRAFT_REG": {"pattern": r"^[A-Z0-9\-]{3,10}$", "allow_empty": True},
    "DSN": {"pattern": r"^\d{1,6}$", "allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Row anchor: exactly 8 tokens, 6th one date-shaped (see module docstring).
_DATE_RE = re.compile(r"^\d{2}-\d{2}-\d{4}$")

# A single leading run of non-alphanumeric characters on PN/SN/POSITION is a
# confirmed rendering artifact (see module docstring) -- stripped up front,
# before the shared cleanup pipeline's own per-field OCR_CHAR_MAP/pipe-strip
# passes run.
_LEADING_ARTIFACT_RE = re.compile(r"^[^A-Za-z0-9]+")

# Header field patterns, searched independently (not order-dependent) since
# the header block's own word/line order is confirmed to shuffle across
# pages (see module docstring).
_HEADER_PATTERNS = {
    "AS_OF_DATE": re.compile(r"StatusASAT:\s*([\d/-]+)"),
    "MSN": re.compile(r"UnitMSN:\s*(\d+)"),
    "AIRCRAFT_TYPE": re.compile(r"Item:\s*([A-Za-z0-9\-]+)"),
    "AIRCRAFT_TSN_HEADER": re.compile(r"UnitTSN:\s*([\d:]+)"),
    "AIRCRAFT_CSN_HEADER": re.compile(r"UnitCSN:\s*(\d+)"),
    "AIRCRAFT_REG": re.compile(r"([A-Z0-9\-]+)\s+[Ss]erial:"),
    "DSN": re.compile(r"UnitDSN:\s*(\d+)"),
}
_HEADER_FIELDS = list(_HEADER_PATTERNS)


def _strip_leading_artifact(s: str) -> str:
    return _LEADING_ARTIFACT_RE.sub("", s)


def _parse_header(page_text: str) -> dict:
    meta: dict = {}
    for field, pat in _HEADER_PATTERNS.items():
        m = pat.search(page_text)
        if m:
            meta[field] = m.group(1)
    return meta


def _group_lines(words: list[dict]) -> list[list[dict]]:
    """Cluster words into physical lines by y-position (tolerant of
    sub-point 'top' jitter between words nominally on the same visual
    line)."""
    ws = sorted(words, key=lambda w: (w["top"], w["x0"]))
    lines: list[dict] = []
    for w in ws:
        if lines and abs(w["top"] - lines[-1]["top"]) <= 2.5:
            lines[-1]["words"].append(w)
            lines[-1]["top"] = (lines[-1]["top"] + w["top"]) / 2
        else:
            lines.append({"top": w["top"], "words": [w]})
    for line in lines:
        line["words"].sort(key=lambda w: w["x0"])
    return [line["words"] for line in lines]


def _parse_row(tokens: list[str]) -> dict | None:
    if len(tokens) != 8 or not _DATE_RE.match(tokens[5]):
        return None
    pn, sn, desc, ata, position, install_date, ac_tsn, ac_csn = tokens
    return {
        "PART_NUMBER": _strip_leading_artifact(pn),
        "SERIAL_NUMBER": _strip_leading_artifact(sn),
        "DESCRIPTION": desc,
        "ATA": ata,
        "POSITION": _strip_leading_artifact(position),
        "INSTALL_DATE": install_date,
        "AIRCRAFT_TSN": ac_tsn,
        "AIRCRAFT_CSN": ac_csn,
    }


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    header_meta: dict = {f: "" for f in _HEADER_FIELDS}
    header_locked = False
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            if not header_locked:
                text = page.extract_text() or ""
                page_meta = _parse_header(text)
                if all(page_meta.get(f) for f in _HEADER_FIELDS):
                    header_meta = page_meta
                    header_locked = True

            words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
            if not words:
                continue
            for line_words in _group_lines(words):
                tokens = [w["text"] for w in line_words]
                row = _parse_row(tokens)
                if row is None:
                    continue
                row.update(header_meta)
                row["_page"] = page_num
                records.append(row)
    return records
