"""On Condition and Condition Monitoring OCCM — Indonesian operator B737-800 format.

Header is highly specific and appears identically across all files in this
cluster::

    ON CONDITION AND CONDITION MONITORING AIRCRAFT COMPONENTS STATUS
    AIRCRAFT TYPE/MODEL : B737-800
    ...
    ATA  QTY  INDEX  TYPE  DESCRIPTION  PART NUMBER  SERIAL NUMBER  POSITION
    DATE  TSN  CSN  HOURS  CYCLES  DAYS

Some files drop QTY+INDEX (seen on at least one known airframe in the
corpus) — the parser handles both shapes via per-row token-count detection.

Per-row anchor::

    ATA [QTY INDEX] TYPE  DESCRIPTION...  PN  SN  POSITION...  INSTALL_DATE  TSN  CSN  HOURS  CYCLES  DAYS

INSTALL_DATE is `D-Mon-YY` or `DD-Mon-YYYY` or `D/Mon/YYYY`. The 5-numeric
trailing block uses European decimal `,` as thousands separator
(`54.866` = 54866 hours). POSITION can be one or two tokens (`LH`, `RH`,
`Primary`, `LH Primary`, `1`, `21`, `-`).

Distinct from the existing `On Condition Components Report` variant — that
one is a different operator with a different layout.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "On Condition Monitoring OCCM"
SIGNATURES = [
    "ON CONDITION AND CONDITION MONITORING AIRCRAFT COMPONENTS STATUS",
]

CANONICAL_COLUMNS = [
    "ATA",
    "QTY",
    "INDEX",
    "TYPE",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "POSITION",
    "INSTALL_DATE",
    "TSN",
    "CSN",
    "HOURS",
    "CYCLES",
    "DAYS",
]

# Numeric values use European decimal `.` as thousands separator (54.866).
# Cycle range checks aren't appropriate here since these are dotted European
# integers — we leave them as raw strings.
_NUM_RULE = {"pattern": r"^[\d.,]+$", "allow_empty": True}
_OVERRIDES = {
    "ATA":          {"pattern": r"^\d{2}$"},
    "QTY":          {"pattern": r"^\d{1,3}$", "allow_empty": True},
    "INDEX":        {"pattern": r"^\d{1,3}$", "allow_empty": True},
    "TYPE":         {"pattern": r"^[A-Z]{2,4}$", "allow_empty": True},
    "POSITION":     {"pattern": r"^[A-Z0-9 .\-/]{1,30}$", "uppercase": True,
                     "allow_empty": True},
    "INSTALL_DATE": {"pattern": r"^(\d{1,2}[-/][A-Za-z]{3}[-/]\d{2,4})$"},
    "TSN": _NUM_RULE, "CSN": _NUM_RULE, "HOURS": _NUM_RULE,
    "CYCLES": _NUM_RULE, "DAYS": _NUM_RULE,
}
RULES = merged_rules(_OVERRIDES)

_DATE_RE = re.compile(r"^\d{1,2}[-/][A-Za-z]{3}[-/]\d{2,4}$")
_NUM_RE = re.compile(r"^[\d.,]+$")
_PN_LIKELY = re.compile(r"^[A-Z0-9][A-Z0-9.\-/]{2,}$")
_TYPE_RE = re.compile(r"^(CM|OC|HT|CD|LL)$")


def _is_position_token(tok: str) -> bool:
    """POSITION tokens are short, alphanumeric, often a single letter (`LH`,
    `RH`, `1`, `2`, `21`, `Primary`, `-`).

    Pure digits ≥3 chars are rejected — they're almost always serial numbers
    being mistaken for positions (`2570`, `1757`).
    """
    s = tok.strip()
    if not s or s == "-":
        return True
    if len(s) > 12:
        return False
    # Pure-digit tokens: only short (≤2) are real positions; longer = SN.
    if s.isdigit():
        return len(s) <= 2
    return bool(re.match(r"^[A-Z0-9./\-]+$", s, re.I))


def _parse_line(line: str, page_num: int) -> dict | None:
    toks = line.split()
    if len(toks) < 9:
        return None
    # ATA must be first
    if not (toks[0].isdigit() and 20 <= int(toks[0]) <= 83):
        return None
    # find INSTALL_DATE
    date_idx = next((i for i, t in enumerate(toks) if _DATE_RE.match(t)), None)
    if date_idx is None or date_idx < 4:
        return None
    # 5 numeric tokens must follow date (TSN, CSN, HOURS, CYCLES, DAYS)
    tail = toks[date_idx + 1:]
    if len(tail) < 2:
        return None
    # Pad up to 5
    while len(tail) < 5:
        tail.append("")
    tsn, csn, hours, cycles, days = tail[0], tail[1], tail[2], tail[3], tail[4]

    # Walk back from date_idx-1 collecting POSITION tokens (up to 3)
    pos_tokens = []
    i = date_idx - 1
    while i > 3 and _is_position_token(toks[i]) and len(pos_tokens) < 3:
        # Stop if we hit something that's clearly an SN (long alphanum)
        if len(toks[i]) >= 6 and any(c.isdigit() for c in toks[i]):
            break
        pos_tokens.insert(0, toks[i])
        i -= 1
    position = " ".join(pos_tokens)

    # toks[i] = SN, toks[i-1] = PN, toks[i-2..] = leading area
    if i < 3:
        return None
    sn = toks[i]
    pn = toks[i - 1]
    head = toks[:i - 1]   # everything before PN

    # Parse leading area: ATA [QTY INDEX] TYPE DESCRIPTION...
    ata = head[0]
    qty = index = type_v = ""
    desc_start = 1
    # If head[1] is a digit (QTY) AND head[2] is a digit (INDEX) AND head[3] is TYPE
    if (len(head) >= 4 and head[1].isdigit() and head[2].isdigit()
            and _TYPE_RE.match(head[3])):
        qty = head[1]
        index = head[2]
        type_v = head[3]
        desc_start = 4
    elif len(head) >= 2 and _TYPE_RE.match(head[1]):
        type_v = head[1]
        desc_start = 2
    description = " ".join(head[desc_start:])
    if not description:
        return None
    return {
        "ATA": ata,
        "QTY": qty,
        "INDEX": index,
        "TYPE": type_v,
        "DESCRIPTION": description,
        "PART_NUMBER": pn,
        "SERIAL_NUMBER": sn,
        "POSITION": position,
        "INSTALL_DATE": toks[date_idx],
        "TSN": tsn,
        "CSN": csn,
        "HOURS": hours,
        "CYCLES": cycles,
        "DAYS": days,
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
                line = raw.strip()
                if not line:
                    continue
                rec = _parse_line(line, page_num)
                if rec is not None:
                    records.append(rec)
    return records
