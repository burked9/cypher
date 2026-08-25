"""AerCap "OXYGEN GENERATOR STATUS" report -- single-component HT excerpt
(a known B767-3Q8ER file in the corpus, AerCap lessor letterhead).

Header (repeated per page)::

    AerCap Ireland Limited, 4450 Atlantic Avenue
    Westpark, Shannon, Co. Clare, Republic of Ireland
    A/C TYPE : B767-3Q8ER OXYGEN GENERATOR STATUS
    A/C REG.: <tail no.>
    A/C serial : <MSN> DATE : 10-May-19
    A/C TTSN : 75,757
    A/C TCSN : 12,180
    INTERVAL LAST DONE NEXT DUE REMAINED
    ATA MP ITEM PARTS DESCRPTION POSITION PART NUMBER SERIAL NUMBER TAG No. FH CY DAYS FH CY DATE FH CY DATE FH CY DAYS REMARKS

Row example::

    35 35-007-00 OXYGEN GENERATOR 10 AC 117003-13 8601960094 SO 32114757-1.000 4380 29-Mar-17 26-Mar-29 3608 WORTH TO GO

Narrower cousin of aercap_hard_time_component_status.py -- same lessor and
near-identical header block, but scoped to a single component family
(every row is ATA 35 / task 35-007-00, title says OXYGEN GENERATOR STATUS
not HARD TIME COMPONENT STATUS) and missing that report's ZONE column and
its double LAST-DONE timeline, so it parses cleanly with real field splits
rather than needing that module's coarse-grained fallback.

File quirk: the PDF is 6 pages, but only 3 pages of underlying content --
pages 1-3 are a noisy re-render (OCR text over/under the real glyphs) and
pages 4-6 repeat the identical 3 pages cleanly ("Page 1 of 3" through
"Page 3 of 3" appear on BOTH halves). Unlike aercap_hard_time_component_
status.py's source file, this noise is mild per-character (single-digit
misreads: POSITION "10" extracts as the word "to", SERIAL_NUMBER
"8601960094" extracts as "8601930094") rather than fully interleaved text
layers, so a misread row still LOOKS like a well-formed row -- the field
regexes below match it just as happily as the real one, silently doubling
every component with a corrupted twin (confirmed empirically: without
correction this parser pulls ~195 rows from a 3-page/~100-component
report). `_drop_duplicate_first_half` guards against this by comparing
per-page-half row counts rather than assuming a fixed page range (a
genuinely different file in this format might not duplicate at all), and
keeps only the higher-fidelity second half when the two halves' counts are
comparable.

DESCRIPTION is fixed at the two tokens right after the task code ("OXYGEN
GENERATOR" on every single row in this corpus -- this file is that
component's own report) rather than derived from a general boundary rule;
POSITION is whatever sits between DESCRIPTION and PART_NUMBER, which is
sometimes a bare index ("10"), sometimes index+batch code ("10 AC"), and
sometimes a multi-word phrase ("DOOR AFT L/H"). The token right after
SERIAL_NUMBER is a second identifier this report tracks per unit (TAG No.,
closed vocab SO/NO in this corpus) -- the report's own header names it, so
it gets its own column; everything past it (an unlabeled lot/cert code
folded in ahead of the ragged FH/CY/DATE columns, the same ragged-tail
tradeoff every sibling HT parser makes) is kept as one STATUS_TRAIL string.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.ht_variants._base import merged_rules

NAME = "AerCap Oxygen Generator Status"
SIGNATURES = [
    "OXYGEN GENERATOR STATUS",
]
CANONICAL_COLUMNS = [
    "ATA",
    "TASK_CODE",
    "DESCRIPTION",
    "POSITION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "TAG_NO",
    "STATUS_TRAIL",
]
_OVERRIDES = {
    "TASK_CODE": {"pattern": r"^\d{2}-?\d{3}-\d{2}$"},
    "POSITION": {"allow_empty": True, "uppercase": True},
    "TAG_NO": {"pattern": r"^(?:SO|NO)$", "allow_empty": True},
    "STATUS_TRAIL": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_ROW_RE = re.compile(r"^(\d{2})\s+(\d{2}-?\d{3}-\d{2})\s+(.+)$")
_PN_RE = re.compile(r"^\d{6}-\d{2}$")


def _parse_line(line: str, page_num: int) -> dict | None:
    m = _ROW_RE.match(line)
    if not m:
        return None
    ata, task_code, rest = m.groups()
    toks = rest.split()
    if len(toks) < 3:
        return None
    pn_idx = next((i for i, t in enumerate(toks) if _PN_RE.match(t)), None)
    if pn_idx is None or pn_idx < 2:
        return None
    description = " ".join(toks[:2])
    position = " ".join(toks[2:pn_idx])
    part_number = toks[pn_idx]
    after = toks[pn_idx + 1:]
    return {
        "ATA": ata,
        "TASK_CODE": task_code,
        "DESCRIPTION": description,
        "POSITION": position,
        "PART_NUMBER": part_number,
        "SERIAL_NUMBER": after[0] if after else "",
        "TAG_NO": after[1] if len(after) > 1 else "",
        "STATUS_TRAIL": " ".join(after[2:]),
        "_page": page_num,
    }


def _drop_duplicate_first_half(page_records: list[list[dict]]) -> list[list[dict]]:
    """This file's noisy-vs-clean duplication (see module docstring) is
    mild enough per-character -- single-digit OCR misreads, not the
    interleaved-text-layer corruption seen in aercap_hard_time_component_
    status.py's source file -- that a wrong digit still LEAVES the right
    SHAPE (e.g. SERIAL_NUMBER "8601930094" instead of "8601960094"), so the
    row regex alone does not reject the noisy half the way it does there.
    Detected by comparable per-half row *counts* (both halves describe the
    same physical components) rather than assumed from a fixed page range,
    since a genuinely different file in this format might not duplicate at
    all -- only the higher-fidelity second half is kept when duplication is
    detected."""
    n = len(page_records)
    if n < 2 or n % 2:
        return page_records
    half = n // 2
    first_count = sum(len(p) for p in page_records[:half])
    second_count = sum(len(p) for p in page_records[half:])
    if first_count == 0 or second_count == 0:
        return page_records
    if min(first_count, second_count) / max(first_count, second_count) < 0.6:
        return page_records
    return page_records[half:]


def extract(pdf_path: str) -> list[dict]:
    with pdfplumber.open(pdf_path) as pdf:
        page_records: list[list[dict]] = []
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            page_records.append([
                rec for raw in text.splitlines()
                if (rec := _parse_line(raw.strip(), page_num)) is not None
            ])
    return [r for page in _drop_duplicate_first_half(page_records) for r in page]
