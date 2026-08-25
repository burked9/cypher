"""'OCCM LIST AS AT' variant — 12-column tabular OCCM with date+time stamps.

Format header: `ATA DESCRIPTION MPN MSN POSN INSTALL DATE TSN CSN TSO CSO TSSV CSSV`
First seen on a Caribbean-region operator's files and a related A305-prefixed
set (likely a shared MIS used across multiple Caribbean operators).

Per-row layout (single line, space-separated):
    ATA  DESCRIPTION...  MPN  MSN  POSN... INSTALL_DATE  TIME  TSN  CSN
    [TSO  CSO  [TSSV  CSSV]]

Distinctive features:
- Install date in `YYYY-MM-DD HH:MM:SS` form (two tokens).
- POSN is variable (1-3 tokens) — values like `LH SECONDARY`, `RH PRIMARY`,
  `LH ECS`, `2`, `*`, `A02`.
- Trailing numeric block is 2-6 values (TSN, CSN required; TSO/CSO/TSSV/CSSV
  optional).
- MPN is the first token after ATA that looks like a part number (contains
  digits and a hyphen).

Anchors: the ISO date pattern. MPN identified by `^\\d+(?:-[A-Z0-9]+)+$`.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "OCCM List As At"
SIGNATURES = [
    "OCCM LIST AS AT",
    "ATA DESCRIPTION MPN MSN POSN",
    "MPN MSN POSN INSTALL DATE",
]

CANONICAL_COLUMNS = [
    "ATA",
    "DESCRIPTION",
    "MPN",
    "MSN",
    "POSN",
    "INSTALL_DATE",
    "INSTALL_TIME",
    "TSN",
    "CSN",
    "TSO",
    "CSO",
    "TSSV",
    "CSSV",
]

_OVERRIDES = {
    # POSN occasionally absent; INSTALL_TIME often absent (only the date is
    # carried on many rows). Don't flag empty as failure.
    "POSN": {"pattern": r"^[A-Z0-9*\-/ ]{1,30}$", "uppercase": True, "allow_empty": True},
    "INSTALL_DATE": {"pattern": r"^\d{4}-\d{2}-\d{2}$"},
    "INSTALL_TIME": {"pattern": r"^\d{2}:\d{2}:\d{2}$", "allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_ATA_RE  = re.compile(r"^\d{2}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^\d{2}:\d{2}:\d{2}$")
# MPN looks like a part number: digits + at least one hyphen + alphanumeric tail
_MPN_RE  = re.compile(r"^\d+(?:-[A-Z0-9]+)+$")


def _parse_line(line: str, page_num: int) -> dict | None:
    tokens = line.split()
    if len(tokens) < 8:
        return None
    if not _ATA_RE.match(tokens[0]):
        return None
    ata_int = int(tokens[0])
    if not (20 <= ata_int <= 83):
        return None

    # Find the install date
    date_idx = None
    for i, t in enumerate(tokens):
        if _DATE_RE.match(t):
            date_idx = i
            break
    if date_idx is None or date_idx + 1 >= len(tokens):
        return None
    install_date = tokens[date_idx]
    install_time = tokens[date_idx + 1] if _TIME_RE.match(tokens[date_idx + 1]) else ""

    # Find MPN — first PN-shaped token after ATA (token[0])
    mpn_idx = None
    for i in range(1, date_idx):
        if _MPN_RE.match(tokens[i]):
            mpn_idx = i
            break
    if mpn_idx is None or mpn_idx + 1 >= date_idx:
        return None
    mpn = tokens[mpn_idx]
    msn = tokens[mpn_idx + 1]

    description = " ".join(tokens[1:mpn_idx])
    posn = " ".join(tokens[mpn_idx + 2:date_idx])
    if not description:
        return None

    # Numeric trailing block (TSN, CSN, [TSO, CSO, [TSSV, CSSV]])
    nums_start = date_idx + (2 if install_time else 1)
    nums = tokens[nums_start:]
    # Pad to 6 values
    while len(nums) < 6:
        nums.append("")
    tsn, csn, tso, cso, tssv, cssv = nums[:6]

    return {
        "ATA": tokens[0],
        "DESCRIPTION": description,
        "MPN": mpn,
        "MSN": msn,
        "POSN": posn,
        "INSTALL_DATE": install_date,
        "INSTALL_TIME": install_time,
        "TSN": tsn, "CSN": csn,
        "TSO": tso, "CSO": cso,
        "TSSV": tssv, "CSSV": cssv,
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
