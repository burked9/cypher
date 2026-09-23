"""COMPONENTS NO CONTROLLED IN STATUS -- born-digital, full text layer,
coordinate-bucketed columns (confirmed directly via an `extract_words()`
pass over the real sample file). This is a short prose-letter format, not
a ruled table: a single page opens with a dateline and salutation, then
the fixed subject line "Components no controlled in status", a one-line
intro paragraph, a column header row, a small number of data rows, and a
signature block (a person's name and job title -- never extracted as
data; see below).

Column header (one line, wrapping onto a second line for two of the
labels)::

    Item  Description  PN  SN  Inst  Requirement  Dim  Last  Next
                              Date               Done  Due

Row grain: this template tracks each component item against one or more
separate limit bases (a "Days" basis with two dates, and/or an "Hours"
basis with two plain numbers) -- confirmed in the sample, where two of
three items are tracked under both bases and the third only under
"Days". One output row is emitted per (item, limit basis) pair, so an
item tracked under both bases yields two rows sharing the same
ITEM/DESCRIPTION/PART_NUMBER/SERIAL_NUMBER.

Physical layout per item (confirmed directly against the real sample):
a first physical line carries ITEM, DESCRIPTION, PART_NUMBER,
SERIAL_NUMBER, plus the first fragment of INSTALLED_DATE/REQUIREMENT/
LAST_DONE/NEXT_DUE and the first LIMIT_UNIT ("Days"); a second physical
line (no ITEM/LIMIT_UNIT token) completes those same four fragments
(each date's year, or the task-card number); an optional third physical
line carries only a second LIMIT_UNIT ("Hours") plus its own
LAST_DONE/NEXT_DUE values, which are plain numbers needing no
continuation line of their own. Column assignment is fixed x0-threshold
bucketing (confirmed directly: every field sits at a consistent,
non-overlapping x0 band on every row in the sample).

New-item and new-limit-basis detection: a line starting a new item
carries an ITEM token (a bare integer landing in the ITEM x-band); a
line starting an additional limit basis for the *same* item carries a
LIMIT_UNIT token ("Days"/"Hours") but no ITEM token, and inherits the
open item's DESCRIPTION/PART_NUMBER/SERIAL_NUMBER; any other line is
treated as a continuation of the currently open row and is only ever
merged into INSTALLED_DATE/REQUIREMENT/LAST_DONE/NEXT_DUE -- never into
ITEM/DESCRIPTION/PART_NUMBER/SERIAL_NUMBER -- and only when it actually
carries a token in one of those four bands, so a line with no relevant
content is skipped outright rather than blindly merged. A continuation
fragment that completes a hyphen-terminated date fragment (e.g.
"30-Jan-" + "2018") is joined with no inserted space; every other
continuation is space-joined.

This last rule is what keeps the signature block at the foot of the
page (the accomplishing engineer's name and job title) out of the
extracted data without any dedicated footer-skipping logic: both of its
lines fall entirely inside the ITEM/DESCRIPTION x-bands, so neither line
ever carries a token in the four continuation-eligible bands and both
are silently skipped (confirmed directly against the real sample).

No per-page aircraft metadata (registration/MSN/etc.) appears anywhere
in this template's own text -- confirmed directly, every field above is
per-row.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.ht_variants._base import merged_rules
from shared.cleanup import normalize_dashes

NAME = "Components No Controlled in Status (Letter)"
SIGNATURES = [
    # Checked against every SIGNATURES list in occm.py/ht.py/llp.py and
    # every occm_variants/ht_variants/llp_variants module's own SIGNATURES
    # list; no collision found. Not a substring of, and does not contain
    # as a substring, any other variant's own signature phrase.
    "Components no controlled in status",
]

CANONICAL_COLUMNS = [
    "ITEM",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "INSTALLED_DATE",
    "REQUIREMENT",
    "LIMIT_UNIT",
    "LAST_DONE",
    "NEXT_DUE",
]

_DATE_RE = r"^\d{1,2}-[A-Za-z]{3}-\d{4}$"

_OVERRIDES = {
    "ITEM":            {"pattern": r"^\d+$"},
    "DESCRIPTION":     {"allow_empty": True},
    "PART_NUMBER":     {"allow_empty": True},
    "SERIAL_NUMBER":   {"allow_empty": True},
    "INSTALLED_DATE":  {"pattern": _DATE_RE, "allow_empty": True},
    "REQUIREMENT":     {"allow_empty": True},
    "LIMIT_UNIT":      {"pattern": r"^(DAYS|HOURS)$", "uppercase": True},
    # LAST_DONE/NEXT_DUE hold a date on Days-basis rows but a plain
    # aircraft-time reading on Hours-basis rows -- deliberately no
    # pattern so neither basis is flagged against the other (same
    # reasoning as LAST_INTERVAL in hard_time_status_ata_reference.py).
    "LAST_DONE":       {"allow_empty": True},
    "NEXT_DUE":        {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Fixed x0 (PDF points) column boundaries, derived directly from the real
# sample file's own word coordinates (see module docstring). Assignment is
# "which band does this word's x0 fall in" -- no nearest-neighbour needed,
# because none of these bands ever overlap on the sample file.
# Thresholds are midpoints between each column's own measured x0 and the
# next column's measured x0 (not the next column's x0 itself), so a word
# sitting exactly on a column's anchor x0 is never pushed into the band
# to its left by float rounding.
_ITEM_X = 106.0
_DESC_X = 175.0
_PN_X = 213.0
_SN_X = 277.0
_INSTALLED_X = 333.0
_REQUIREMENT_X = 386.0
_LIMIT_X = 433.0
_LAST_X = 467.0

_FIELD_ORDER = [
    ("ITEM", _ITEM_X),
    ("DESCRIPTION", _DESC_X),
    ("PART_NUMBER", _PN_X),
    ("SERIAL_NUMBER", _SN_X),
    ("INSTALLED_DATE", _INSTALLED_X),
    ("REQUIREMENT", _REQUIREMENT_X),
    ("LIMIT_UNIT", _LIMIT_X),
    ("LAST_DONE", _LAST_X),
    ("NEXT_DUE", float("inf")),
]

# Fields a continuation line (no ITEM, no LIMIT_UNIT) is ever allowed to
# merge into -- never ITEM/DESCRIPTION/PART_NUMBER/SERIAL_NUMBER/
# LIMIT_UNIT, so stray boilerplate (e.g. the signature block) can never
# pollute row identity even if it happened to land in one of these bands.
_CONTINUATION_FIELDS = {"INSTALLED_DATE", "REQUIREMENT", "LAST_DONE", "NEXT_DUE"}

_ITEM_RE = re.compile(r"^\d+$")
_LIMIT_UNIT_RE = re.compile(r"^(Days|Hours)$", re.IGNORECASE)
_HEADER_META_RE = re.compile(
    r"^(Item|Description|PN|SN|Inst|Requirement|Dim|Last|Next|Date|Done|Due)$",
    re.IGNORECASE,
)
# Static boilerplate lines that appear once per page and are never data:
# dateline, salutation, the subject line itself, and the intro paragraph.
_BOILERPLATE_RE = re.compile(
    r"^(To\s+whom\s+it\s+may\s+concern|Subject\s*:|This\s+statement\s+is\s+to\s+confirm)",
    re.IGNORECASE,
)


def _field_for_x0(x0: float) -> str:
    for name, upper in _FIELD_ORDER:
        if x0 < upper:
            return name
    return "NEXT_DUE"


def _group_lines(words: list[dict]) -> list[dict]:
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
    return lines


def _bucket_line(words: list[dict]) -> dict[str, list[str]]:
    buckets: dict[str, list[str]] = {}
    for w in words:
        field = _field_for_x0(w["x0"])
        buckets.setdefault(field, []).append(w["text"])
    return buckets


def _merge_fragment(existing: str, val: str) -> str:
    if existing and existing.endswith("-"):
        return existing + val
    return (existing + " " + val).strip() if existing else val


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
            if not words:
                continue
            for w in words:
                w["text"] = normalize_dashes(w["text"])
            lines = _group_lines(words)

            current_identity: dict | None = None  # ITEM/DESCRIPTION/PN/SN
            current_row: dict | None = None

            for line in lines:
                line_words = line["words"]
                line_text = " ".join(w["text"] for w in line_words)

                # Column header row (two physical lines) and static
                # boilerplate (dateline/salutation/subject/intro) are
                # never data and never continuations of a data row.
                if _BOILERPLATE_RE.match(line_text.strip()):
                    continue
                if all(_HEADER_META_RE.match(tok) for tok in line_text.split()):
                    continue

                buckets = _bucket_line(line_words)
                item_tokens = buckets.get("ITEM", [])
                has_new_item = len(item_tokens) == 1 and _ITEM_RE.match(item_tokens[0])
                limit_tokens = [
                    t for t in buckets.get("LIMIT_UNIT", []) if _LIMIT_UNIT_RE.match(t)
                ]
                has_limit_unit = len(limit_tokens) == 1

                if has_new_item:
                    current_identity = {
                        "ITEM": item_tokens[0],
                        "DESCRIPTION": " ".join(buckets.get("DESCRIPTION", [])),
                        "PART_NUMBER": " ".join(buckets.get("PART_NUMBER", [])),
                        "SERIAL_NUMBER": " ".join(buckets.get("SERIAL_NUMBER", [])),
                    }
                    row = {col: "" for col in CANONICAL_COLUMNS}
                    row.update(current_identity)
                    row["LIMIT_UNIT"] = limit_tokens[0] if has_limit_unit else ""
                    row["INSTALLED_DATE"] = " ".join(buckets.get("INSTALLED_DATE", []))
                    row["REQUIREMENT"] = " ".join(buckets.get("REQUIREMENT", []))
                    row["LAST_DONE"] = " ".join(buckets.get("LAST_DONE", []))
                    row["NEXT_DUE"] = " ".join(buckets.get("NEXT_DUE", []))
                    row["_page"] = page_num
                    records.append(row)
                    current_row = row
                elif has_limit_unit and current_identity is not None:
                    # Additional limit basis for the same open item.
                    row = {col: "" for col in CANONICAL_COLUMNS}
                    row.update(current_identity)
                    row["LIMIT_UNIT"] = limit_tokens[0]
                    row["LAST_DONE"] = " ".join(buckets.get("LAST_DONE", []))
                    row["NEXT_DUE"] = " ".join(buckets.get("NEXT_DUE", []))
                    row["_page"] = page_num
                    records.append(row)
                    current_row = row
                elif current_row is not None:
                    relevant = {
                        f: buckets[f] for f in _CONTINUATION_FIELDS if buckets.get(f)
                    }
                    if not relevant:
                        # Nothing in a continuation-eligible band (e.g. the
                        # signature block) -- never merged, always skipped.
                        continue
                    for field, toks in relevant.items():
                        for tok in toks:
                            current_row[field] = _merge_fragment(current_row[field], tok)
                # else: stray line before any item has been seen -- skip.

    return records
