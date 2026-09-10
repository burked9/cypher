"""Component "Localization" list -- a per-aircraft OCCM export headed by
(labels shown genericized; the real header carries heavy character-
substitution corruption described below)::

    <manufacturer, corrupted>
    <page> of <total>
    Airplane Model: <type>
    Airplane Serial Number: <msn>
    Customer: <customer>
    Registration: <reg>
    Date/Time: <date> <time>

    Localization
    <PN>  <SN>  <description...>  <position>

repeated per page, with section rows breaking up the P/N-column band, e.g.
(values genericized)::

    21<section name, glued to the ATA number with no space>

followed by rows for that ATA chapter until the next section row.

Confirmed on a single real file so far (singleton cluster) -- born-digital,
full text layer (`extract_words()` returns real content on every page, no
OCR needed). The text layer is real but carries SEVERE, systematic
character-substitution corruption, the same "real but noisy text layer"
pattern already documented elsewhere in this project (see e.g.
`occm_component_status_report.py`, `occm_components_status.py`). Confirmed
corruption examples seen directly in the sample (never "corrected", just
described here so the pattern is recognisable, and deliberately NOT
reproducing the actual corrupted strings verbatim -- only their shape):
a single letter is sometimes rendered as a completely different letter or a
short cluster of letters depending on which embedded font subset drew that
particular run of text (so the SAME letter renders correctly in one column
of a row and wrong in another column of the very same row); this is
consistent with several distinct, independently-corrupted embedded font
subsets being used for different parts of the layout, not a single global
substitution table. Part numbers, serial numbers and ATA-chapter digit
pairs are digits-only or digit-led and were NOT observed to be affected by
this corruption (digits render correctly throughout); free-text
description/position/header-label words are the ones affected.

Row grain: one row per component. Columns, left to right: PART_NUMBER,
SERIAL_NUMBER, DESCRIPTION (may be more than one whitespace-split token,
occasionally wraps with an embedded stray space inside what should be one
word), LOCATION (the report's own "Localization"/position column -- kept
as a single catch-all field per this project's "never guess a wrong split"
convention, since it sometimes carries more than one token with no
reliable internal delimiter). PART_NUMBER is occasionally missing on an
isolated, otherwise-empty row (confirmed directly: a handful of rows carry
only a lone numeric token with no recoverable SERIAL_NUMBER, DESCRIPTION or
LOCATION at all) -- these are not recovered as data rows at all (no
description or location content to anchor them), matching this project's
"missing data over guessed data" convention; a small unrecovered-row count
is therefore expected and acceptable here, not a bug to engineer away.

Column geometry -- word x-position bucketing, not token counting (same
technique as `occm_component_status_report.py`): every word on the page
(`extract_words()`) is assigned to a canonical column purely by its own x0
position, using boundaries derived directly from measuring real data-row
word positions across the sample (a histogram of every word's own x0 across
the whole document shows four clearly-separated bands with wide gaps
between them, confirmed directly). This makes row parsing immune to the
occasional embedded-space/word-wrap issue described above: a value split
into two or three word-fragments still lands in the right bucket and is
simply joined with a single space, verbatim, no matter how many fragments
it was split into.

Row clustering: words are grouped into row-clusters by chain-merging
consecutive (sorted, de-duplicated) `top` values within a small tolerance,
same technique as `occm_component_status_report.py`. Measured directly
against the sample: a single logical row's own words scatter by no more
than about 1-2pt of `top`, while consecutive real rows are reliably spaced
roughly 12-13pt apart -- well clear of the chosen tolerance.

Row validity, in order: (a) reject anything above the page's repeating
header block (measured directly: every page's own repeating title/
aircraft-summary block sits above a fixed top, every real data or section
row sits below it, with one narrow overlap band near that boundary --
checked directly against the whole document: the only real content found
inside that narrow band is a single genuine data row, so the boundary was
set to admit it rather than the more conservative value, without admitting
any of the several stray single-glyph artefacts also found in that same
band, none of which carry enough content on their own to pass the checks
below anyway); (b) a row whose only populated bucket is PART_NUMBER, and
whose leading digit-pair is immediately followed by a letter (not another
digit), is an ATA-chapter section row, not a component row -- its leading
two digits update the running ATA chapter carried onto subsequent rows,
and the row itself is not emitted as a record (this specific shape --
digit-pair directly followed by a letter, no space -- was checked directly
against every such row in the sample and reliably distinguishes real
section rows from the rare orphan lone-PN-token row described above, whose
own digits are not followed by a letter at all); (c) an ordinary row needs
some DESCRIPTION-or-LOCATION content and some PART_NUMBER-or-SERIAL_NUMBER
content to be emitted, same shape of check as
`occm_component_status_report.py`.

No digit-level "correction" (0/O, 1/l/I, etc.) or letter-level correction
is attempted anywhere in this module on any column, per this project's
"never guess a wrong split, wrong data is worse than missing data"
convention -- the raw extracted text (words found in that column's
x-range, joined with a single space, exactly as pdfplumber returns them)
is kept as-is. The shared global ATA/PART_NUMBER/SERIAL_NUMBER rules
already carry an OCR char-map that runs during validation/cleanup (see
`shared/aviation_rules.py`), so digit/letter confusion is handled centrally
rather than guessed at per-variant.

Header metadata (AIRCRAFT_TYPE, MSN, CUSTOMER, REGISTRATION, AS_OF_DATE) is
parsed once from the first page's own aircraft-summary block -- confirmed
to sit at a consistent position on every page, directly above the
repeating "Localization" column-header word -- and stamped onto every row,
same convention this project's other header-plus-body OCCM variants use
(e.g. `occm_component_status_report.py`). Each label/value pair is split by
its own x0 (label words sit well to the left of value words on the same
line, with a wide, consistently-empty gap between them, confirmed directly
against the sample), then matched to a field by a lowercase keyword found
in the label text (e.g. "model", "serial", "customer", "regist", "date"),
not by hardcoding the exact corrupted label spelling -- the keyword
approach was chosen because the labels themselves render with the same
column-dependent corruption described above and their exact spelling was
NOT reliably constant across the pages checked, while the keyword
substring was.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "Component Localization List"
SIGNATURES = [
    # The report's own repeating column-header word and two of its
    # aircraft-summary field labels. Checked directly (grep across every
    # SIGNATURES list in sheet_types/{occm,ht,llp}.py and every existing
    # occm_variants/ht_variants/llp_variants file): none of these three
    # phrases appear anywhere else in this package, and none is a substring
    # of (nor contains) any other variant's own SIGNATURES entries.
    "AIRPLANE MODEL:",
    "AIRPLANE SERIAL NUMBER:",
    "LOCALIZATION",
]

CANONICAL_COLUMNS = [
    "ATA",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
    "LOCATION",
    # Header metadata -- parsed once, stamped onto every row.
    "AIRCRAFT_TYPE",
    "MSN",
    "CUSTOMER",
    "REGISTRATION",
    "AS_OF_DATE",
]

_OVERRIDES = {
    "LOCATION": {"allow_empty": True},
    "AIRCRAFT_TYPE": {"allow_empty": True},
    "MSN": {"pattern": r"^[A-Za-z0-9]{2,10}$", "allow_empty": True},
    "CUSTOMER": {"allow_empty": True},
    "REGISTRATION": {"allow_empty": True},
    "AS_OF_DATE": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# --- Row clustering ----------------------------------------------------------
# Chain-merge tolerance for grouping words into visual row-clusters by their
# `top` coordinate -- see module docstring "Row clustering".
_TOP_TOLERANCE = 2.5

# The repeating title/aircraft-summary/column-header block sits above this
# `top` on every page of the sample; every real data or section row sits
# below it. Measured directly: the block's own words go up to top ~209 on
# a couple of pages, real content starts as low as top ~206.5 on one page
# (the only real data row found in that narrow overlap band) -- see module
# docstring "Row validity" for what was checked in that band.
_HEADER_BLOCK_MAX_TOP = 206.0

# --- Column geometry: x0 boundaries -----------------------------------------
# Each (name, upper) pair is that column's own upper x0 boundary (a word
# qualifies for that column when its x0 is less than this value, having
# already failed every earlier column's boundary). LOCATION is the implicit
# catch-all for anything at/after the last (DESCRIPTION) boundary. Derived
# directly from a histogram of every word's own x0 across the whole sample
# (see module docstring "Column geometry") -- four clearly-separated bands
# with wide gaps between them.
_BOUNDS = [
    ("PART_NUMBER", 250.0),
    ("SERIAL_NUMBER", 345.0),
    ("DESCRIPTION", 680.0),
]

# ATA-chapter section row: leading two digits immediately followed by a
# letter (no space) -- see module docstring "Row validity" (b).
_SECTION_ROW_RE = re.compile(r"^(\d{2})[A-Za-z]")

_LABEL_VALUE_SPLIT_X0 = 350.0


def _bucket(x0: float) -> str:
    for name, upper in _BOUNDS:
        if x0 < upper:
            return name
    return "LOCATION"


def _cluster_rows(words: list[dict]) -> list[list[dict]]:
    """Group words into visual line-clusters by their `top` coordinate,
    chain-merging consecutive tops within `_TOP_TOLERANCE` -- see module
    docstring "Row clustering"."""
    if not words:
        return []
    tops = sorted(set(round(w["top"], 1) for w in words))
    clusters: list[list[float]] = []
    cur = [tops[0]]
    for t in tops[1:]:
        if t - cur[-1] <= _TOP_TOLERANCE:
            cur.append(t)
        else:
            clusters.append(cur)
            cur = [t]
    clusters.append(cur)

    row_groups = []
    for cl in clusters:
        lo, hi = min(cl) - 0.5, max(cl) + 0.5
        row_words = [w for w in words if lo <= w["top"] <= hi]
        if row_words:
            row_groups.append(row_words)
    return row_groups


def _bucket_row(tokens: list[dict]) -> tuple[dict, float]:
    tokens = sorted(tokens, key=lambda w: w["x0"])
    top = min(w["top"] for w in tokens)
    buckets: dict[str, list[str]] = {}
    for w in tokens:
        buckets.setdefault(_bucket(w["x0"]), []).append(w["text"])
    row_cols = ("PART_NUMBER", "SERIAL_NUMBER", "DESCRIPTION", "LOCATION")
    rec = {c: " ".join(buckets.get(c, [])) for c in row_cols}
    return rec, top


def _is_section_row(rec: dict) -> str | None:
    """Return the two-digit ATA chapter if `rec` is a section-title row
    (see module docstring "Row validity" (b)), else None."""
    if rec["SERIAL_NUMBER"] or rec["DESCRIPTION"] or rec["LOCATION"]:
        return None
    m = _SECTION_ROW_RE.match(rec["PART_NUMBER"])
    return m.group(1) if m else None


def _is_data_row(rec: dict) -> bool:
    if not rec["DESCRIPTION"] and not rec["LOCATION"]:
        return False
    if not rec["PART_NUMBER"] and not rec["SERIAL_NUMBER"]:
        return False
    return True


_LABEL_KEYWORDS = {
    "model": "AIRCRAFT_TYPE",
    "serial": "MSN",
    "customer": "CUSTOMER",
    "regist": "REGISTRATION",
    "date": "AS_OF_DATE",
}


def _parse_header(words: list[dict]) -> dict:
    """Parse the first page's aircraft-summary block (AIRCRAFT_TYPE, MSN,
    CUSTOMER, REGISTRATION, AS_OF_DATE) -- see module docstring "Header
    metadata". Each cluster below the header block's own max top is split
    into label words (x0 < `_LABEL_VALUE_SPLIT_X0`) and value words (x0 >=
    that), then matched to a field by keyword found in the label text."""
    meta: dict = {}
    for cl in _cluster_rows(words):
        top = min(w["top"] for w in cl)
        if top >= _HEADER_BLOCK_MAX_TOP:
            continue
        label_words = sorted(
            (w for w in cl if w["x0"] < _LABEL_VALUE_SPLIT_X0), key=lambda w: w["x0"]
        )
        value_words = sorted(
            (w for w in cl if w["x0"] >= _LABEL_VALUE_SPLIT_X0), key=lambda w: w["x0"]
        )
        if not label_words or not value_words:
            continue
        label = " ".join(w["text"] for w in label_words).lower()
        value = " ".join(w["text"] for w in value_words)
        for kw, field in _LABEL_KEYWORDS.items():
            if kw in label and field not in meta:
                meta[field] = value
                break
    return meta


_HEADER_META_KEYS = ("AIRCRAFT_TYPE", "MSN", "CUSTOMER", "REGISTRATION", "AS_OF_DATE")


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    header_meta: dict = {}
    current_ata = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            words = page.extract_words()
            if not words:
                continue
            if page_num == 1:
                header_meta = _parse_header(words)
            for cl in _cluster_rows(words):
                rec, top = _bucket_row(cl)
                if top < _HEADER_BLOCK_MAX_TOP:
                    continue
                section_ata = _is_section_row(rec)
                if section_ata is not None:
                    current_ata = section_ata
                    continue
                if not _is_data_row(rec):
                    continue
                rec["ATA"] = current_ata
                for key in _HEADER_META_KEYS:
                    rec[key] = header_meta.get(key, "")
                rec["_page"] = page_num
                records.append(rec)
    return records
