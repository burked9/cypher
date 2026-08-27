"""OCCM Summary List -- born-digital, full text layer, coordinate-bucketed
columns (same technique as `occm_report.py` / `ht_variants/
time_controlled_components_status.py`).

Confirmed on one real file in the corpus (clean text layer via pdfplumber
`extract_text()`/`extract_words()` on every page, no wrapped lines
anywhere)::

    OCCM SUMMARY LIST MSN <n> <tail>
    DATE AS OF: <D-Mon-YY>
    FLIGHT HRS: <n>
    FLIGHT CYCLE: <n>
    ATA Description Partno Serialno Description Pos. Inst-Date TSN CSN
    21 AIR CONDITIONING 1209-100 20609 PRESSURE SWITCH 17HQ 30-Mar-10 24852 14777
    21 1209-100 2936 PRESSURE SWITCH 30HQ 17-Sep-98 49385 29711
    21 1263A0000-03 334 MACHINE CYCLE ONLY 28-Dec-00 92738 56573

The column header line has TWO "Description" columns at different
x-positions -- the first is an ATA-CHAPTER-level heading (e.g. "AIR
CONDITIONING") that only prints on the FIRST data row of a new ATA
chapter (confirmed: on the known source file, 27 of 955 data rows carry
one, one per chapter run -- every other row in that chapter goes straight
from ATA to Partno); the second is the real per-component description
(e.g. "PRESSURE SWITCH"). A row-shape heuristic based on token count or
"looks like a short all-caps phrase with no digits" is fragile (some
chapter headings are short, some real descriptions are also short
all-caps phrases with no digits, e.g. "FCV"). Column x-position is
reliable instead: on every inspected page, the chapter-heading text (when
present) and the Partno value that follows it share the *same* x-range as
each other's column would if empty -- i.e. the two possible contents of
that slot (heading text vs. nothing) never collide with Partno's own
column, which starts at a fixed x-position regardless of whether a
heading preceded it on that row. Bucketing every word by x-position into
9 fixed columns (mirroring the two header "Description" columns plus
Pos./Inst-Date/TSN/CSN) resolves both shapes with the same code path, no
row-shape branching needed.

TSN/CSN are frequently the literal string ``UNKNOWN`` instead of a
number (confirmed real data, not a parse failure -- roughly a quarter of
rows on the known source file). POSITION is empty on rows describing
life-limited/consumable items with no installed position (e.g. "MACHINE
CYCLE ONLY" rows, Pos. blank). ATA_HEADING is empty on every row except
the first of each chapter -- left per-row (not forward-filled) since it
is a chapter-level label, not a per-component fact that's missing.

No page footer, watermark, or other confounding text was found on the
known source file's pages -- every physical line either matches the
column-header line, the small fixed page-top block (title/date/hours/
cycles), or is an ATA-anchored data row.
"""
from __future__ import annotations
import re

import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "OCCM Summary List"

SIGNATURES = [
    "OCCM SUMMARY LIST",
]

CANONICAL_COLUMNS = [
    "ATA",
    "ATA_HEADING",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
    "POSITION",
    "INST_DATE",
    "TSN",
    "CSN",
]

# TSN/CSN may carry the literal "UNKNOWN" sentinel where component time is
# unrecorded (confirmed real data on the known source file). Accept it as
# valid rather than flagging bad_format.
_OVERRIDES = {
    "ATA_HEADING":   {"allow_empty": True, "uppercase": True},
    "POSITION":      {"pattern": r"^[A-Z0-9./\- ]{1,20}$", "uppercase": True,
                       "allow_empty": True},
    "INST_DATE":     {"pattern": r"^\d{1,2}-[A-Za-z]{3}-\d{2,4}$"},
    "TSN":           {"pattern": r"^(?:[\d.,]+|UNKNOWN)$", "allow_empty": True},
    "CSN":           {"pattern": r"^(?:\d+|UNKNOWN)$", "allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Column x-boundaries (PDF points), derived from real header + data-row word
# coordinates on the known source file -- consistent across every inspected
# page. Order matches the header line's own column order:
# ATA | Description(heading) | Partno | Serialno | Description(real) |
# Pos. | Inst-Date | TSN | CSN.
_BOUNDS = [0, 90, 225, 300, 375, 554, 592, 643, 690, 10**6]
_FIELDS = [
    "ATA", "ATA_HEADING", "PART_NUMBER", "SERIAL_NUMBER", "DESCRIPTION",
    "POSITION", "INST_DATE", "TSN", "CSN",
]

_ATA_RE = re.compile(r"^\d{1,2}$")


def _bucket(x0: float) -> str:
    for i in range(len(_BOUNDS) - 1):
        if _BOUNDS[i] <= x0 < _BOUNDS[i + 1]:
            return _FIELDS[i]
    return _FIELDS[-1]


def _group_lines(words: list[dict]) -> list[dict]:
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
    return lines


def _bucket_line(line: dict) -> dict:
    row = {f: "" for f in _FIELDS}
    for w in line["words"]:
        field = _bucket(w["x0"])
        row[field] = (row[field] + " " + w["text"]).strip()
    return row


def _is_data_row(line: dict) -> bool:
    """A real data row's first word is an ATA-shaped token (1-2 digits)
    landing in the ATA column's x-range. Confirmed on the known source
    file: every non-data line (title, DATE AS OF/FLIGHT HRS/FLIGHT CYCLE
    block, column-header line) fails this test, and every data row
    passes it -- no wrapped lines were found, so no anchor/overflow
    handling is needed here (unlike `occm_report.py`)."""
    if not line["words"]:
        return False
    first = line["words"][0]
    return bool(_ATA_RE.match(first["text"])) and _bucket(first["x0"]) == "ATA"


def _extract_page(page) -> list[dict]:
    words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
    if not words:
        return []
    rows: list[dict] = []
    for line in _group_lines(words):
        if _is_data_row(line):
            rows.append(_bucket_line(line))
    return rows


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            for row in _extract_page(page):
                row["_page"] = page_num
                records.append(row)
    return records
