"""TAP Portugal HT — single-line `DDMmmYYYY` anchor layout.

TAP emits OCCM and HT reports from the same internal system with the
same header (`Serial Numbers Attached to Aircraft <REG>  PROG. MAN: TAP`)
and similar row layout. Two HT sub-formats appear in the corpus:

  * **Spaced FH** (MSN223 log HT status.pdf style) — post-date FH integer
    is followed by a separate `FH` units token:
        `... 21 316HL 05DEC2011 37523 FH HT OVH ...`

  * **Glued FH** (1399 / 1307 / A306_HT Inventory style) — units are
    glued onto the integer, no separating space:
        `... 21 15HQ 20NOV2019 32748FH 14350FH HT OVH ...`

The OCCM-side `tap_compact_occm` parser requires a pure-integer token
after the date, which breaks on the glued sub-format. This HT-side
parser accepts both forms by stripping a trailing `FH`/`CY` suffix
from the post-date integer before validating.

For sextant we only need the position fingerprint:
  PART_NUMBER, SERIAL_NUMBER, DESCRIPTION, ATA, POSITION (FIN), INSTALL_DATE.
The trailing task-history columns are preserved as-is in `TASK_TRAIL`.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "TAP HT (compact)"
SIGNATURES = [
    "PROG. MAN: TAP",
    "FLIGHT TIME:",
]
CANONICAL_COLUMNS = [
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
    "ATA",
    "POSITION",
    "INSTALL_DATE",
    "FH",
    "TASK_TRAIL",
]
_OVERRIDES = {
    "ATA":          {"pattern": r"^\d{2}$", "int_range": (20, 83)},
    "POSITION":     {"pattern": r"^[A-Z0-9/-]{2,12}$", "uppercase": True,
                     "allow_empty": True},
    "INSTALL_DATE": {"pattern": r"^\d{2}[A-Z]{3}\d{4}$"},
    "FH":           {"pattern": r"^\d+$", "allow_empty": True},
    "TASK_TRAIL":   {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_DATE_RE = re.compile(r"^\d{2}[A-Z]{3}\d{4}$")
# Tolerant FH integer: digits, optionally with glued FH/CY units.
_FH_RE = re.compile(r"^(\d+)(FH|CY|TSN|CSN)?$")
_HEADER_SKIP = re.compile(
    r"PROG\.?\s*MAN|FLIGHT TIME|MAINTENANCE|ENGINEERING|"
    r"^PN\s+SN\s+KEYWORD|^ATA\s*$|PAGE\s*-?\s*\d", re.I)


def _parse_line(line: str, page_num: int) -> dict | None:
    if _HEADER_SKIP.search(line):
        return None
    toks = line.split()
    if len(toks) < 6:
        return None
    # Find the compact date token (DDMmmYYYY).
    date_idx = None
    for i in range(3, len(toks)):
        if _DATE_RE.match(toks[i]):
            date_idx = i
            break
    if date_idx is None or date_idx < 4:
        return None
    # Two tokens immediately before the date are ATA + POSITION.
    ata = toks[date_idx - 2]
    position = toks[date_idx - 1]
    if not re.match(r"^\d{2}$", ata):
        return None
    ata_int = int(ata)
    if not (20 <= ata_int <= 83):
        return None
    # Post-date: FH integer (possibly glued with units), then variable tail.
    fh = ""
    trail_start = date_idx + 1
    if trail_start < len(toks):
        m = _FH_RE.match(toks[trail_start])
        if m:
            fh = m.group(1)
            trail_start += 1
    task_trail = " ".join(toks[trail_start:]) if trail_start < len(toks) else ""
    # Pre-ATA: PN, SN, then a multi-token DESCRIPTION.
    head = toks[:date_idx - 2]
    if len(head) < 3:
        return None
    pn = head[0]
    sn = head[1]
    description = " ".join(head[2:])
    return {
        "PART_NUMBER": pn,
        "SERIAL_NUMBER": sn,
        "DESCRIPTION": description,
        "ATA": ata,
        "POSITION": position,
        "INSTALL_DATE": toks[date_idx],
        "FH": fh,
        "TASK_TRAIL": task_trail,
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
                rec = _parse_line(raw.strip(), page_num)
                if rec is not None:
                    records.append(rec)
    return records
