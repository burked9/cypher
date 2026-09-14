"""OCCM (ATA Section Header, TSN/CSN) -- born-digital, full text layer,
word-position-aware parsing (confirmed via a direct pdfplumber pass over the
real sample file: `extract_words()` returns full content on every page, no
OCR needed). Synchronous `extract()`.

Header block (repeats verbatim at the top of every page)::

    OCCM
    Revision: <n>
    Aircraft Type: <type> Reference Date: <date>
    Registration: <reg> TSN: <hours:minutes>
    MSN: <msn> CSN: <n>
    Description Part Number Serial Number Position Installation Date TSN CSN Comment

Parsed once from the first page and stamped on every row, same convention
this project's other header-plus-body OCCM variants use. The header's own
"TSN"/"CSN" fields are aircraft-level totals-at-reference-date, a different
thing from the per-row TSN/CSN columns below (component time/cycles since
new) -- kept under distinct names (AIRCRAFT_TSN/AIRCRAFT_CSN) so the two
never collide.

ATA is NOT printed per component row -- only on its own "ATA <n> - <chapter
name>" section-heading row above each group (confirmed via `extract_words()`:
every word on such a line sits well left of any data column). These heading
rows are recognised and dropped rather than emitted as a component, with the
ATA number stamped onto every row that follows until the next heading --
same section-header-carries-ATA convention this project's other
section-organized OCCM/HT variants use (e.g. `ht_variants/
ca004_hard_time_monitoring_sheet.py`).

Row grain: one row per tracked component. Columns, left to right::

    DESCRIPTION | PART_NUMBER | SERIAL_NUMBER | POSITION | INSTALLATION_DATE |
    TSN | CSN | COMMENT

INSTALLATION_DATE can itself be the literal placeholder "UNK" rather than a
real date (confirmed directly: several real rows carry "UNK" in the date
slot with TSN/CSN also "UNK", or occasionally just the date alone), so the
row anchor is "a token that is either a `DD-Mon-YY(YY)` date or the literal
`UNK`" rather than requiring a real date. COMMENT is free text and optional
(certificate/document references, e.g. "DR <n> CERT: <id>"); most rows have
none.

PART_NUMBER and SERIAL_NUMBER are always exactly one token each (confirmed:
no real PN/SN value in the source data contains an internal space) while
POSITION and DESCRIPTION are free-width multi-token spans -- so rows are
parsed by *sequence*, not by fixed x-coordinate bucketing, for the
DESCRIPTION/PN/SN/POSITION boundary: PART_NUMBER is the first token past the
description column's own x-position band (x0 >= ~235pt, confirmed: every
real DESCRIPTION word's own x0 tops out at ~220pt and every real PART_NUMBER
value's own x0 starts at ~251pt, a clean gap in between), SERIAL_NUMBER is
unconditionally the very next token, and POSITION is whatever tokens remain
up to the DATE-or-UNK anchor (this sidesteps a genuinely ambiguous, narrow
overlap band between this template's own SERIAL_NUMBER and POSITION columns
that a fixed x-coordinate boundary could not reliably separate -- confirmed
directly against the real sample file).

One extraction quirk confirmed directly on the real sample file: the literal
word "UNKNOWN" occasionally splits into two separate word-tokens ("UNKNOW"
+ "N") by pdfplumber's own word-boundary heuristic -- not a real typo in the
source data (contrast `occm_variants/standard_occm.py`'s own "UNKNOW"
*spelling* sentinel, a different, genuine source-data quirk). Adjacent
"UNKNOW"+"N" token pairs are merged back into one "UNKNOWN" token before any
column parsing, so it lands cleanly in whichever single column it belongs to
rather than spilling the trailing "N" into the next column.

Known limitation, confirmed directly on the real sample file: its own final
page renders as a single full-page raster image (0 extractable words/chars
via `extract_words()`/`.chars`, one embedded image spanning the whole page)
rather than born-digital text like every other page in the file -- likely a
wet-ink-signature page re-inserted as a scan after the rest of the report was
generated. `extract()` is synchronous and does not OCR individual blank
pages within an otherwise-text-layer file (the router's own OCR-fallback
loop only triggers when the *whole* document, or page 1 specifically, is
blank -- not the case here, since detection matches cleanly on page 1's own
text). Rows on such a page are silently not extracted; if this turns out to
be common across this template's own real corpus rather than a one-off, a
per-page OCR fallback (using `shared/ocr_bridge`, not raw `fitz`/
`pytesseract`) would be the fix.

Data-row geometry -- word x-position bucketing (same technique as
`occm_control_sheet.py`) is still used for the trailing TSN/CSN/COMMENT
columns (a fixed, safely-separated x-position band each) and for attaching
line-wrap overflow fragments back onto their own anchor row: this template's
own SERIAL_NUMBER value can spill across up to three physical lines exactly
like `occm_control_sheet.py`'s own known source file (a leading fragment
printed just above the row's own anchor line, the row itself with that
token's continuation, and/or a trailing fragment printed just below) --
confirmed directly. Handled the same way: each non-anchor physical line is
attached to whichever anchor row (previous or next) it sits vertically
closer to, its own words re-bucketed by x-position into the row's fields,
prepending if leading (its own anchor row comes after it) or appending if
trailing (before) -- a fixed, deterministic rule rather than a per-case
guess, per this project's "never guess a wrong split" convention.
"""
from __future__ import annotations
import re

import pdfplumber

from sheet_types.occm_variants._base import merged_rules
from shared.cleanup import normalize_dashes

NAME = "OCCM (ATA Section Header, TSN/CSN)"
SIGNATURES = [
    "Description Part Number Serial Number Position Installation Date TSN CSN Comment",
]

CANONICAL_COLUMNS = [
    "ATA",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "POSITION",
    "INSTALLATION_DATE",
    "TSN",
    "CSN",
    "COMMENT",
    # Header metadata -- same on every row of a given file.
    "REVISION",
    "AIRCRAFT_TYPE",
    "REFERENCE_DATE",
    "AIRCRAFT_REG",
    "AIRCRAFT_TSN",
    "MSN",
    "AIRCRAFT_CSN",
]

# TSN/CSN: plain integers, HH:MM-style cumulative hours, or the literal
# placeholder "UNK"/"UNKNOWN" seen throughout the real sample where a figure
# isn't tracked for that component.
_NUM_OR_UNK = r"^(?:UNK|UNKNOWN|\d+(?::\d{2})?)$"
_OVERRIDES = {
    "POSITION": {"allow_empty": True},
    "INSTALLATION_DATE": {"pattern": r"^(?:\d{1,2}-[A-Za-z]{3}-\d{2,4}|UNK)$"},
    "TSN": {"pattern": _NUM_OR_UNK, "allow_empty": True},
    "CSN": {"pattern": _NUM_OR_UNK, "allow_empty": True},
    "COMMENT": {"allow_empty": True},
    "REVISION": {"allow_empty": True},
    "AIRCRAFT_TYPE": {"allow_empty": True},
    "REFERENCE_DATE": {"allow_empty": True},
    "AIRCRAFT_REG": {"pattern": r"^[A-Z0-9\-]+$", "uppercase": True, "allow_empty": True},
    "AIRCRAFT_TSN": {"pattern": _NUM_OR_UNK, "allow_empty": True},
    "MSN": {"pattern": r"^[A-Z0-9]+$", "uppercase": True, "allow_empty": True},
    "AIRCRAFT_CSN": {"pattern": _NUM_OR_UNK, "allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# --- Row anchor -------------------------------------------------------------
# A `DD-Mon-YY` or `DD-Mon-YYYY` date, or the literal unknown-value sentinel.
_DATE_OR_UNK_RE = re.compile(r"^(?:\d{1,2}-[A-Za-z]{3}-\d{2,4}|UNK)$")

# DESCRIPTION words never land past ~220pt; PART_NUMBER never starts before
# ~251pt -- confirmed directly against the real sample file's full word
# geometry (see module docstring).
_PN_X_MIN = 235.0

# SERIAL_NUMBER never starts past ~399pt and POSITION never starts before
# ~406pt (confirmed directly, a clean gap) -- but SERIAL_NUMBER can be
# legitimately blank on a row whose own value is entirely a line-wrap
# overflow fragment (see module docstring's SN-wrap note), in which case the
# very next token after PART_NUMBER is actually POSITION, not an empty SN.
# Gated on this boundary rather than assumed present, so that case doesn't
# silently steal POSITION's own leading token as SERIAL_NUMBER.
_SN_X_MAX = 404.0

_HEADER_PREFIXES = (
    "OCCM", "Revision:", "Aircraft Type:", "Registration:", "MSN:",
    "Description Part Number",
)
_FOOTER_PREFIXES = ("Part M Aviation", "Original Page", "Approval Number")
_SECTION_HEADER_RE = re.compile(r"^ATA\s+(\d{1,3})\s*-")

_META_RE_REVISION = re.compile(r"Revision:\s*(\S+)")
_META_RE_1 = re.compile(r"Aircraft Type:\s*(\S+)\s+Reference Date:\s*(\S+)")
_META_RE_2 = re.compile(r"Registration:\s*(\S+)\s+TSN:\s*(\S+)")
_META_RE_3 = re.compile(r"MSN:\s*(\S+)\s+CSN:\s*(\S+)")

# Approximate x-position bands, used only for (a) the trailing TSN/CSN/COMMENT
# split on an anchor row and (b) re-bucketing line-wrap overflow fragments.
# The DESCRIPTION/PART_NUMBER/SERIAL_NUMBER/POSITION split on an anchor row
# itself is sequence-based, not bucket-based (see module docstring).
_FRAG_FIELDS = [
    "DESCRIPTION", "PART_NUMBER", "SERIAL_NUMBER", "POSITION",
    "INSTALLATION_DATE", "TSN", "CSN", "COMMENT",
]
_FRAG_BOUNDS = [0, 235, 330, 404, 483, 539, 605, 660, 10 ** 6]


def _parse_meta(text: str) -> dict:
    meta: dict[str, str] = {}
    m = _META_RE_REVISION.search(text)
    if m:
        meta["REVISION"] = m.group(1)
    m = _META_RE_1.search(text)
    if m:
        meta["AIRCRAFT_TYPE"] = m.group(1)
        meta["REFERENCE_DATE"] = m.group(2)
    m = _META_RE_2.search(text)
    if m:
        meta["AIRCRAFT_REG"] = m.group(1)
        meta["AIRCRAFT_TSN"] = m.group(2)
    m = _META_RE_3.search(text)
    if m:
        meta["MSN"] = m.group(1)
        meta["AIRCRAFT_CSN"] = m.group(2)
    return meta


def _bucket(x0: float) -> str:
    for i in range(len(_FRAG_BOUNDS) - 1):
        if _FRAG_BOUNDS[i] <= x0 < _FRAG_BOUNDS[i + 1]:
            return _FRAG_FIELDS[i]
    return _FRAG_FIELDS[-1]


def _merge_unknown_split(words: list[dict]) -> list[dict]:
    """Merge an adjacent "UNKNOW" + "N" token pair (a pdfplumber word-boundary
    artifact, not real source data -- see module docstring) back into a
    single "UNKNOWN" token, so it lands in one column rather than two."""
    out: list[dict] = []
    i = 0
    while i < len(words):
        w = words[i]
        if (
            w["text"] == "UNKNOW"
            and i + 1 < len(words)
            and words[i + 1]["text"] == "N"
            and words[i + 1]["x0"] - w["x0"] < 45
        ):
            merged = dict(w)
            merged["text"] = "UNKNOWN"
            out.append(merged)
            i += 2
        else:
            out.append(w)
            i += 1
    return out


def _group_lines(words: list[dict]) -> list[dict]:
    """Cluster words into physical lines by y-position, tolerant of
    sub-point 'top' jitter between words nominally on the same line."""
    ws = sorted(words, key=lambda w: (w["top"], w["x0"]))
    lines: list[dict] = []
    for w in ws:
        if lines and abs(w["top"] - lines[-1]["top"]) <= 2.5:
            lines[-1]["words"].append(w)
            lines[-1]["top"] = (lines[-1]["top"] + w["top"]) / 2
        else:
            lines.append({"top": w["top"], "words": [w]})
    return lines


def _date_or_unk_index(words: list[dict]) -> int | None:
    for i, w in enumerate(words):
        if i >= 2 and _DATE_OR_UNK_RE.match(w["text"]):
            return i
    return None


def _parse_anchor_row(words: list[dict]) -> dict | None:
    date_idx = _date_or_unk_index(words)
    if date_idx is None:
        return None
    pn_idx = None
    for i in range(date_idx):
        if words[i]["x0"] >= _PN_X_MIN:
            pn_idx = i
            break
    if pn_idx is None:
        return None
    desc = " ".join(w["text"] for w in words[:pn_idx])
    if not desc:
        return None
    sn_idx = pn_idx + 1
    if sn_idx < date_idx and words[sn_idx]["x0"] < _SN_X_MAX:
        serial_number = words[sn_idx]["text"]
        position = " ".join(w["text"] for w in words[sn_idx + 1:date_idx])
    else:
        serial_number = ""
        position = " ".join(w["text"] for w in words[pn_idx + 1:date_idx])
    row = {f: "" for f in _FRAG_FIELDS}
    row["DESCRIPTION"] = desc
    row["PART_NUMBER"] = words[pn_idx]["text"]
    row["SERIAL_NUMBER"] = serial_number
    row["POSITION"] = position
    row["INSTALLATION_DATE"] = words[date_idx]["text"]
    if date_idx + 1 < len(words):
        row["TSN"] = words[date_idx + 1]["text"]
    if date_idx + 2 < len(words):
        row["CSN"] = words[date_idx + 2]["text"]
    if date_idx + 3 < len(words):
        row["COMMENT"] = " ".join(w["text"] for w in words[date_idx + 3:])
    return row


def _bucket_words(words: list[dict]) -> dict:
    row = {f: "" for f in _FRAG_FIELDS}
    for w in sorted(words, key=lambda w: w["x0"]):
        f = _bucket(w["x0"])
        row[f] = (row[f] + " " + w["text"]).strip()
    return row


def _extract_page(page, current_ata: str) -> tuple[list[dict], str]:
    words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
    if not words:
        return [], current_ata
    for w in words:
        w["text"] = normalize_dashes(w["text"])
    lines = _group_lines(words)

    real_lines = []
    for line in lines:
        text = " ".join(w["text"] for w in sorted(line["words"], key=lambda w: w["x0"]))
        stripped = text.strip()
        if not stripped:
            continue
        if any(stripped.startswith(p) for p in _HEADER_PREFIXES):
            continue
        if any(stripped.startswith(p) for p in _FOOTER_PREFIXES):
            continue
        sec = _SECTION_HEADER_RE.match(stripped)
        if sec:
            current_ata = sec.group(1).zfill(2)
            continue
        real_lines.append({**line, "words": _merge_unknown_split(sorted(line["words"], key=lambda w: w["x0"]))})

    anchors = []
    row_by_anchor: dict[int, dict] = {}
    for i, line in enumerate(real_lines):
        row = _parse_anchor_row(line["words"])
        if row is not None:
            row["ATA"] = current_ata
            anchors.append(i)
            row_by_anchor[i] = row
    anchor_set = set(anchors)

    for i, line in enumerate(real_lines):
        if i in anchor_set:
            continue
        prev_a = max((a for a in anchors if a < i), default=None)
        next_a = min((a for a in anchors if a > i), default=None)
        if prev_a is None and next_a is None:
            continue  # no anchor row on this page to attach an orphan fragment to
        if prev_a is None:
            target_idx = next_a
        elif next_a is None:
            target_idx = prev_a
        else:
            gap_prev = real_lines[i]["top"] - real_lines[prev_a]["top"]
            gap_next = real_lines[next_a]["top"] - real_lines[i]["top"]
            target_idx = prev_a if gap_prev <= gap_next else next_a
        is_leading = target_idx == next_a
        target_row = row_by_anchor[target_idx]
        frag = _bucket_words(line["words"])
        for f, val in frag.items():
            if not val:
                continue
            if not target_row[f]:
                target_row[f] = val
            elif is_leading:
                target_row[f] = f"{val} {target_row[f]}".strip()
            else:
                target_row[f] = f"{target_row[f]} {val}".strip()

    rows = [row_by_anchor[i] for i in anchors]
    return rows, current_ata


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    meta: dict[str, str] = {}
    current_ata = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            if page_num == 1:
                meta = _parse_meta(normalize_dashes(page.extract_text() or ""))
            rows, current_ata = _extract_page(page, current_ata)
            for row in rows:
                row.update(meta)
                row["_page"] = page_num
                records.append(row)
    return records
