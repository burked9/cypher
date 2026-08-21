"""On Condition / Condition Components Report variant.

A clean 6-column tabular OCCM format seen across multiple Boeing-737 airframes
(LN-RPZ, LN-RCU and others — Norwegian Air Shuttle fleet).

Row format (one line, space-separated):
    ATA  DESCRIPTION...  PART_NUMBER  SERIAL_NUMBER  POSITION  INSTALLATION_DATE

POSITION is a short token (e.g. `LH`, `RH`, `APU`, `ONLY`). The date uses the
short `D-MMM-YY` form (1- or 2-digit day, 3-letter month, 2-digit year).

Some long descriptions wrap onto a second line as a single trailing letter
(e.g. `CONTROLLER-LOW LIMIT (35F` followed by `A` on the next line ⇒
`CONTROLLER-LOW LIMIT (35FA`). We merge those continuations into the previous
record's DESCRIPTION.

Anchor: the trailing date pattern.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "On Condition Components Report"
SIGNATURES = [
    "On Condition / Condition Components",
    "ATA Description Part Number Serial Number Position",
]

CANONICAL_COLUMNS = [
    "ATA",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "POSITION",
    "INSTALLATION_DATE",
]

_OVERRIDES = {
    "POSITION":          {"pattern": r"^[A-Z0-9]{1,8}$", "uppercase": True},
    "INSTALLATION_DATE": {"pattern": r"^\d{1,2}-[A-Za-z]{3}-\d{2}$"},
}
RULES = merged_rules(_OVERRIDES)

_DATE_RE = re.compile(r"^\d{1,2}-[A-Za-z]{3}-\d{2}$")
_ATA_RE  = re.compile(r"^\d{2}$")


def _parse_line(line: str, page_num: int) -> dict | None:
    tokens = line.split()
    if len(tokens) < 6:
        return None
    if not _ATA_RE.match(tokens[0]):
        return None
    if not _DATE_RE.match(tokens[-1]):
        return None
    ata_int = int(tokens[0])
    if not (20 <= ata_int <= 83):
        return None

    install_date = tokens[-1]
    position = tokens[-2]
    sn = tokens[-3]
    pn = tokens[-4]
    desc_tokens = tokens[1:-4]
    if not desc_tokens:
        return None

    return {
        "ATA": tokens[0],
        "DESCRIPTION": " ".join(desc_tokens),
        "PART_NUMBER": pn,
        "SERIAL_NUMBER": sn,
        "POSITION": position,
        "INSTALLATION_DATE": install_date,
        "_page": page_num,
    }


def _is_wrap_continuation(line: str) -> bool:
    """Single-letter or very short alpha-only continuation lines like
    `A`, `N`, `B`, `RE` appearing after a wrapped description token."""
    s = line.strip()
    return 1 <= len(s) <= 4 and s.isalpha()


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if len(text) < 100:
                continue
            last_rec: dict | None = None
            for raw in text.splitlines():
                line = raw.strip()
                if not line:
                    last_rec = None
                    continue
                rec = _parse_line(line, page_num)
                if rec is not None:
                    records.append(rec)
                    last_rec = rec
                    continue
                if last_rec is not None and _is_wrap_continuation(line):
                    last_rec["DESCRIPTION"] = last_rec["DESCRIPTION"] + line
                    continue
                last_rec = None
    return records
