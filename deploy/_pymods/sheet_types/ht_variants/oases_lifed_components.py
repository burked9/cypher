"""OASES "Lifed Component Report" — HT side.

Output of the OASES MIS (`OASES Option : TR42`). Sample header::

    Lifed Component Report          Report Date : 16Nov2016 15:19 Page : 1 of 24
    Aircraft Reg Model MSN Manufacture Date Airframe TSN Airframe CSN
    UR-WRO A321-211 0781 03Mar1998 62956 21982 07Oct2016

Two header sub-formats appear:

  * **TR42 / table-formatted** (UR-WRO style) — model on its own row,
    column header on a separate line.
  * **OK-TSV inline** (`Aircraft Reg: OK-TSV MSN 30664 ...`) — header
    info collapsed onto one or two lines, MSN inline with the reg label.

Both share the same per-record body layout::

    PN  SN  <ATA-block>/<POSITION>/<level>.<sublevel>  DESC  ...trail...
    <LEVEL_VARIATION>  <continuation>  Days (Calendar)  <numerics>
    <continuation>     Fleet Hours    <numerics>
                       Landings       <numerics>

Anchor: the slashed identifier `\d{8}/<POS>/\d+\.\d+` that appears on the
first physical line of every record. Everything before that anchor on the
same line is PN [SN]; everything after it up to a date token is the
description. The 3 continuation lines (Days/Hours/Landings) are skipped
for the position-fingerprint extraction sextant needs.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "OASES Lifed Component Report"
SIGNATURES = [
    "Lifed Component Report",
]
CANONICAL_COLUMNS = [
    "ATA",
    "POSITION",
    "ZONE_LEVEL",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
    "TASK_TYPE",
    "LAST_DONE",
    "NEXT_DUE",
]
_OVERRIDES = {
    "ATA":         {"pattern": r"^\d{2}$", "int_range": (20, 83)},
    "POSITION":    {"pattern": r"^[A-Z0-9/_\.-]{1,30}$", "allow_empty": True,
                    "uppercase": True},
    "ZONE_LEVEL":  {"allow_empty": True},
    "TASK_TYPE":   {"allow_empty": True},
    "LAST_DONE":   {"pattern": r"^\d{1,2}[A-Z][a-z]{2}\d{4}$", "allow_empty": True},
    "NEXT_DUE":    {"pattern": r"^\d{1,2}[A-Z][a-z]{2}\d{4}$", "allow_empty": True},
    # SN often lives on a continuation line below the anchor (UR-WRO,
    # YR-BMF, 9H-XFW sub-formats). The anchor-line PN + ATA + POSITION
    # is enough for sextant's position fingerprint — leave SN blank
    # rather than guessing the wrong token.
    "SERIAL_NUMBER": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Anchor: the slashed identifier `<8-digit ATA-task>/<POS-token>/<level.sublevel>`
# that appears on every record's first physical line. The 8-digit block
# starts with the ATA chapter.
_ANCHOR = re.compile(r"^(\d{8})/([A-Z0-9_./-]+)/(\d+\.\d+)$")
# Date in `DDMmmYYYY` form (`23Nov2012`).
_DATE_RE = re.compile(r"^\d{1,2}[A-Z][a-z]{2}\d{4}$")
_HEADER_SKIP = re.compile(
    r"Lifed Component Report|Aircraft Reg|Chapter \d|Part\s+Serial|"
    r"Life\s+Remaining|Level\s*\(Variation\)|^Page\s|OASES Option|"
    r"Days\s*\(Calendar\)|Fleet\s+Hours|^Landings\b|Manufacture Date|"
    r"Threshold|Card\s+Schedule|Last\s+Limit\s*/\s*Interval|Section\s*/\s*Last", re.I)


def _parse_record_line(line: str, page_num: int) -> dict | None:
    """Try to parse the *anchor* line of a record into a row dict."""
    if _HEADER_SKIP.search(line):
        return None
    toks = line.split()
    if len(toks) < 4:
        return None
    # Find the anchor token
    anchor_idx = None
    ata = position = zone_level = ""
    for i, t in enumerate(toks):
        m = _ANCHOR.match(t)
        if m:
            anchor_idx = i
            ata_full, pos, level = m.groups()
            ata = ata_full[:2]
            position = pos
            zone_level = level
            break
    if anchor_idx is None or anchor_idx == 0:
        return None
    ata_int = int(ata)
    if not (20 <= ata_int <= 83):
        return None
    # Pre-anchor: PN, optionally SN
    head = toks[:anchor_idx]
    pn = head[0]
    sn = head[1] if len(head) >= 2 else ""
    # Post-anchor up to first date is task description; first date is LAST_DONE
    tail = toks[anchor_idx + 1:]
    last_done = next_due = ""
    desc_tokens: list[str] = []
    task_type = ""
    # Common task-type keywords (single-token marker before the date)
    TASK_KEYWORDS = {"Discard", "Restore", "Overhaul", "Restoration",
                     "Inspection", "Functional", "Replace", "Test"}
    i = 0
    while i < len(tail):
        t = tail[i]
        if _DATE_RE.match(t):
            last_done = t
            # next date in tail = next_due (if any)
            for j in range(i + 1, len(tail)):
                if _DATE_RE.match(tail[j]):
                    next_due = tail[j]
                    break
            break
        if t in TASK_KEYWORDS and not task_type:
            task_type = t
        else:
            desc_tokens.append(t)
        i += 1
    description = " ".join(desc_tokens)
    if not (pn and (ata and position)):
        return None
    return {
        "ATA": ata,
        "POSITION": position,
        "ZONE_LEVEL": zone_level,
        "PART_NUMBER": pn,
        "SERIAL_NUMBER": sn,
        "DESCRIPTION": description,
        "TASK_TYPE": task_type,
        "LAST_DONE": last_done,
        "NEXT_DUE": next_due,
        "_page": page_num,
    }


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if len(text) < 80:
                continue
            for raw in text.splitlines():
                rec = _parse_record_line(raw.strip(), page_num)
                if rec is not None:
                    records.append(rec)
    return records
