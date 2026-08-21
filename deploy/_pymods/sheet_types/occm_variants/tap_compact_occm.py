"""TAP-style compact OCCM variant.

Format header begins `CS-TTQ PROG. MAN: TAP` (TAP Portugal's program-manager
export). Used for CS-TTQ MSN 629 across multiple page-range chunks.

Per-row layout (one line, space-separated):
    PART_NUMBER SERIAL_NUMBER DESCRIPTION... ATA POSITION INSTALL_DATE
        FH_INT  FH  CM

Where `INSTALL_DATE` is the compact `DDMmmYYYY` form (`22JUN2016`), and the
trailing `FH CM` is a constant units marker that always follows the FH
integer. We anchor on the date.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "TAP Compact OCCM"
SIGNATURES = [
    "PROG. MAN: TAP",
    "FLIGHT TIME:",   # paired with PROG MAN line in headers
]

CANONICAL_COLUMNS = [
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
    "ATA",
    "POSITION",
    "INSTALL_DATE",
    "FH",
]

_OVERRIDES = {
    "ATA": {"pattern": r"^\d{2}$", "int_range": (20, 83)},
    "POSITION": {"pattern": r"^[A-Z0-9]{2,10}$", "uppercase": True},
    "INSTALL_DATE": {"pattern": r"^\d{2}[A-Z]{3}\d{4}$"},
    "FH": {"pattern": r"^\d+$"},
}
RULES = merged_rules(_OVERRIDES)

_DATE_RE = re.compile(r"^\d{2}[A-Z]{3}\d{4}$")
_INT_RE  = re.compile(r"^\d+$")


def _parse_line(line: str, page_num: int) -> dict | None:
    tokens = line.split()
    if len(tokens) < 8:
        return None
    # Find the compact date token
    date_idx = None
    for i, t in enumerate(tokens):
        if _DATE_RE.match(t):
            date_idx = i
            break
    if date_idx is None or date_idx < 4 or date_idx + 3 != len(tokens) - 1 + 1:
        # Need at least PN, SN, DESC, ATA, POSITION before date,
        # plus FH + "FH" + "CM" after. The trailing FH/CM constants take 2 tokens.
        pass
    if date_idx is None or date_idx < 4 or date_idx + 1 >= len(tokens):
        return None
    if not _INT_RE.match(tokens[date_idx + 1]):
        return None

    fh = tokens[date_idx + 1]
    install_date = tokens[date_idx]
    position = tokens[date_idx - 1]
    ata = tokens[date_idx - 2]
    # ATA must be 2-digit
    if not re.match(r"^\d{2}$", ata):
        return None
    ata_int = int(ata)
    if not (20 <= ata_int <= 83):
        return None

    # Before ATA: PN, SN, DESC...
    head = tokens[:date_idx - 2]
    if len(head) < 3:
        return None
    pn = head[0]
    sn = head[1]
    description = " ".join(head[2:])
    if not description:
        return None

    return {
        "PART_NUMBER": pn,
        "SERIAL_NUMBER": sn,
        "DESCRIPTION": description,
        "ATA": ata,
        "POSITION": position,
        "INSTALL_DATE": install_date,
        "FH": fh,
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
