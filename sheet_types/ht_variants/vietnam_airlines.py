"""Vietnam Airlines variant — HT (Hard Time) sheet.

Source format: "PLAN OF AIRCRAFT COMPONENT REPLACEMENT". Listed components
have hard-time deadlines (must be replaced / overhauled / inspected by the
listed date).

Row format (single line, space-separated):
    DESCRIPTION...  PN  SN  AIRCRAFT  DEADLINE  ESTIMATE  REASON...  REMARK

Anchors:
    - AIRCRAFT is a single short token like "A350" / "A351" / "A321"
    - DEADLINE and ESTIMATE are dates in DD-MMM-YY form (1-2 digit day)
    - REMARK is the last token (typically "H/T" or similar)

Walking the tokens: find the AIRCRAFT token; the two tokens after it must be
dates; everything between the two dates and the last token is the REASON
(can be multiple words like "Discard (LL)").
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.ht_variants._base import merged_rules

NAME = "Vietnam Airlines"
SIGNATURES = [
    "PLAN OF AIRCRAFT COMPONENT REPLACEMENT",
]

CANONICAL_COLUMNS = [
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "AIRCRAFT",
    "DEADLINE",
    "ESTIMATE",
    "REASON",
    "REMARK",
]

_OVERRIDES = {
    "AIRCRAFT": {"pattern": r"^A\d{3}$", "uppercase": True},
    "DEADLINE": {"pattern": r"^\d{1,2}-[A-Za-z]{3}-\d{2}$"},
    "ESTIMATE": {"pattern": r"^\d{1,2}-[A-Za-z]{3}-\d{2}$"},
    # REASON and REMARK are free-form; let pattern stay open
}
RULES = merged_rules(_OVERRIDES)

_AIRCRAFT_RE = re.compile(r"^A\d{3}$")
_DATE_RE = re.compile(r"^\d{1,2}-[A-Za-z]{3}-\d{2}$")


def _parse_line(line: str, page_num: int) -> dict | None:
    line = line.strip()
    if not line:
        return None
    tokens = line.split()
    if len(tokens) < 7:
        return None

    # Find AIRCRAFT token
    ac_idx = None
    for i, t in enumerate(tokens):
        if _AIRCRAFT_RE.match(t):
            ac_idx = i
            break
    if ac_idx is None:
        return None
    if ac_idx < 3:                         # need at least DESC + PN + SN before
        return None
    if ac_idx + 3 >= len(tokens):          # need at least 2 dates + reason + remark after
        return None

    deadline = tokens[ac_idx + 1]
    estimate = tokens[ac_idx + 2]
    if not _DATE_RE.match(deadline) or not _DATE_RE.match(estimate):
        return None

    aircraft = tokens[ac_idx]
    sn = tokens[ac_idx - 1]
    pn = tokens[ac_idx - 2]
    desc_tokens = tokens[:ac_idx - 2]
    desc = " ".join(desc_tokens)
    if not desc:
        return None

    remark = tokens[-1]
    reason_tokens = tokens[ac_idx + 3:-1]
    if not reason_tokens:
        # Some rows have only the remark after the dates; reason inferred to remark
        reason = ""
    else:
        reason = " ".join(reason_tokens)

    rec = {
        "DESCRIPTION":  desc,
        "PART_NUMBER":  pn,
        "SERIAL_NUMBER": sn,
        "AIRCRAFT":     aircraft,
        "DEADLINE":     deadline,
        "ESTIMATE":     estimate,
        "REASON":       reason,
        "REMARK":       remark,
        "_page":        page_num,
    }
    return rec


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if len(text) < 100:
                continue
            for line in text.splitlines():
                rec = _parse_line(line, page_num)
                if rec is not None:
                    records.append(rec)
    return records
