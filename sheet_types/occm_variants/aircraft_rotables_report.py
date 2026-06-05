"""Aircraft Rotables Report variant — one row per line, 9 columns.

Layout (all on one line, space-separated):
    ATA  POSITION  DESCRIPTION...  PART_NUMBER  SERIAL_NUMBER
    [MANUFACTURED_DATE]  INSTALLED_DATE  TSN  CSN

Distinctive features:
- ATA uses the extended `chapter-subchapter` format like `21-00`, `21-26`.
- Dates use the dotted `DD.Mmm.YYYY` form (e.g. `01.Feb.2013`).
- MANUFACTURED date is *sometimes missing* — only INSTALLED is required.

Anchoring strategy: tokens at the end are unambiguous (TSN and CSN are bare
integers, then 1-2 dotted dates). Walk backwards from the last integer pair
to identify dates → SN → PN → DESCRIPTION (multi-token) → POSITION → ATA.

Header line (`ATA POSITION DESCRIPTION P/N S/N MANUFACTURED INSTALLED TSN CSN`)
is rejected because ATA doesn't match the chapter-subchapter pattern.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "Aircraft Rotables Report"
SIGNATURES = [
    "Aircraft Rotables Report",
    # Distinctive column-header sequence — caught even when the title is
    # rebranded by an operator
    "POSITION DESCRIPTION P/N S/N MANUFACTURED INSTALLED",
]

CANONICAL_COLUMNS = [
    "ATA",
    "POSITION",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "MANUFACTURED",
    "INSTALLED",
    "TSN",
    "CSN",
]

_OVERRIDES = {
    # ATA in this variant is `chapter-subchapter` (e.g. "21-00"), not 2-digit.
    "ATA":     {"pattern": r"^\d{2}-\d{2}$", "int_range": None},
    "POSITION": {"pattern": r"^[A-Z0-9]{2,10}$", "uppercase": True},
    "MANUFACTURED": {"pattern": r"^\d{1,2}\.[A-Za-z]{3}\.\d{4}$"},
    "INSTALLED":    {"pattern": r"^\d{1,2}\.[A-Za-z]{3}\.\d{4}$"},
    "TSN": {"pattern": r"^\d+$"},
    "CSN": {"pattern": r"^\d+$"},
}
RULES = merged_rules(_OVERRIDES)

_ATA_RE  = re.compile(r"^\d{2}-\d{2}$")
_DATE_RE = re.compile(r"^\d{1,2}\.[A-Za-z]{3}\.\d{4}$")
_INT_RE  = re.compile(r"^\d+$")


def _parse_line(line: str, page_num: int) -> dict | None:
    tokens = line.split()
    if len(tokens) < 7:
        return None
    if not _ATA_RE.match(tokens[0]):
        return None
    # Trailing tokens: <TSN_int> <CSN_int>
    if not (_INT_RE.match(tokens[-1]) and _INT_RE.match(tokens[-2])):
        return None
    tsn = tokens[-2]
    csn = tokens[-1]

    # Before TSN/CSN: 1 or 2 dotted dates
    head = tokens[:-2]
    manufactured = ""
    installed = ""
    if _DATE_RE.match(head[-1]) and len(head) >= 2 and _DATE_RE.match(head[-2]):
        manufactured = head[-2]
        installed = head[-1]
        head = head[:-2]
    elif _DATE_RE.match(head[-1]):
        installed = head[-1]
        head = head[:-1]
    else:
        return None

    if len(head) < 4:   # need ATA, POSITION, at least one DESC token, PN, SN
        return None

    ata = head[0]
    position = head[1]
    sn = head[-1]
    pn = head[-2]
    desc_tokens = head[2:-2]
    if not desc_tokens:
        return None
    description = " ".join(desc_tokens)

    return {
        "ATA": ata,
        "POSITION": position,
        "DESCRIPTION": description,
        "PART_NUMBER": pn,
        "SERIAL_NUMBER": sn,
        "MANUFACTURED": manufactured,
        "INSTALLED": installed,
        "TSN": tsn,
        "CSN": csn,
        "_page": page_num,
    }


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if len(text) < 100:
                continue
            for raw in text.splitlines():
                line = raw.strip()
                if not line:
                    continue
                rec = _parse_line(line, page_num)
                if rec is not None:
                    records.append(rec)
    return records
