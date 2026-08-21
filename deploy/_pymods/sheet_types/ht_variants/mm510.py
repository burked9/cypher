"""MM_510 — HARD TIME/LLP COMPONENTS report (Sun Express / Atlas Global / IKAR /
Red Wings / various TC- and VP- operators).

Header signature::

    MM_510 - HARD TIME/LLP COMPONENTS Date: <DD-MM-YYYY HH:MM>
    Tail Number : <REG> (<OPERATOR>)  Time Since New : <FH>  Cycle Since New : <FC>

Two row sub-formats observed across the 18-file cluster:

  * **Inline-task layout** (MSN 963 / TC-ETN style): the install date and task
    name are emitted on the same line, with the task name glued to the date::

        21 LH 754C0000-01 81212-50402 MAIN HEAT EXCHANGER 28-02-2014CLEANING 215200-...

  * **Wrap-task layout** (A306 VP-BOZ / VP-BWW style): the row wraps over 2-3
    lines and the task name lives on a continuation line. We currently parse
    only the first line of these — the position fingerprint is on it.

Anchor: a `DD-MM-YYYY` install date (sometimes followed by a glued letter
sequence — the task name). We split that token apart for parsing.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "MM_510 HARD TIME LLP Components"
SIGNATURES = [
    "HARD TIME/LLP COMPONENTS",
    "MM_510",
]
CANONICAL_COLUMNS = [
    "ATA",
    "POSITION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
    "INST_DATE",
    "TASK",
    "TASK_NUMBER",
    "INTERVAL",
    "REMAINING",
]
_OVERRIDES = {
    "ATA":         {"pattern": r"^\d{2}(?:00)?$"},
    # MM_510 reports use two date forms — `DD-MM-YYYY` (Atlas Global / Red Wings)
    # and `DD-MMM-YY` (Sun Express). Accept both.
    "INST_DATE":   {"pattern": r"^(\d{2}-\d{2}-\d{4}|\d{2}-[A-Z]{3}-\d{2})$",
                    "allow_empty": True},
    "PART_NUMBER": {"allow_empty": True},
    "SERIAL_NUMBER": {"allow_empty": True},
    "TASK":        {"allow_empty": True},
    "TASK_NUMBER": {"allow_empty": True},
    "INTERVAL":    {"allow_empty": True},
    "REMAINING":   {"allow_empty": True},
    "POSITION":    {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_DATE_RE = re.compile(r"\b(\d{2}-\d{2}-\d{4}|\d{2}-[A-Z]{3}-\d{2})\b")
# A "fused" date+task token like `28-02-2014CLEANING`, `04-03-2020`, or
# `04-OCT-13` (Sun Express style). We pull the date out and treat any
# trailing alpha (with no separating space) as the start of the task name.
_DATE_GLUED_RE = re.compile(
    r"\b(\d{2}-\d{2}-\d{4}|\d{2}-[A-Z]{3}-\d{2})([A-Z][A-Z]*)?\b")
_ATA_RE = re.compile(r"^\d{2}(?:00)?$")
# PN-shape token: dash+digit+alphanumeric — same rule we use elsewhere.
_PN_RE = re.compile(r"^(?=[A-Z0-9/\-]*\d)[A-Z0-9/\-]+-[A-Z0-9/\-]+$")
_HEADER_SKIP = re.compile(
    r"HARD TIME|MM_510|Tail Number|Doc\.?Type|Part\s+Serial|Component\s+Serial|"
    r"ATA\s+Pos|^\s*Page\s*:|Last\s+Done\s+Due|Form\s+MCM|Issue\s+\d", re.I)


def _parse_line(line: str, page_num: int) -> dict | None:
    if _HEADER_SKIP.search(line):
        return None
    toks = line.split()
    if len(toks) < 5:
        return None
    if not _ATA_RE.match(toks[0]):
        return None
    ata = int(toks[0][:2])
    if not (20 <= ata <= 80):
        return None
    # Find a date or date-glued-task token.
    date_idx = None
    date_str = ""
    task_inline = ""
    for i in range(2, len(toks)):
        m = _DATE_GLUED_RE.match(toks[i])
        if m:
            date_idx = i
            date_str = m.group(1)
            task_inline = (m.group(2) or "").strip(" -/")
            break
    if date_idx is None or date_idx < 4:
        return None
    # POS = toks[1]; PN = leftmost PN-shape between POS and SN; SN = next token.
    pn_idx = None
    for i in range(2, date_idx - 1):
        if _PN_RE.match(toks[i]):
            pn_idx = i
            break
    if pn_idx is None:
        # Some rows have a non-dashed PN like `20499004` (numeric only).
        # Treat the first token-after-POS that has 5+ alphanumerics as PN.
        for i in range(2, date_idx - 1):
            if len(toks[i]) >= 5 and any(c.isdigit() for c in toks[i]):
                pn_idx = i
                break
    if pn_idx is None or pn_idx + 1 >= date_idx:
        return None
    pos = toks[1]
    # PDF text extraction occasionally splits long PN/SN tokens across a
    # line wrap, leaving a trailing `-` on the visible token. Strip it so
    # the value passes the global PN/SN regex.
    pn = toks[pn_idx].rstrip("-")
    sn = toks[pn_idx + 1].rstrip("-")
    description = " ".join(toks[pn_idx + 2:date_idx]) if pn_idx + 2 < date_idx else ""
    # Post-date: task-number ref, then interval/remaining values.
    tail = toks[date_idx + 1:]
    task_number = ""
    interval = ""
    remaining = ""
    if tail:
        # First post-date token is usually a task reference like 215200-04-1.
        if "-" in tail[0]:
            task_number = tail[0]
            tail = tail[1:]
        # The remaining tokens carry interval / hour values — capture loosely
        # as space-joined string. Caller can parse further if needed.
        if tail:
            # Try to keep the 1st (interval) and last (remaining) numerics.
            nums = [t for t in tail if re.match(r"^\d", t)]
            if len(nums) >= 1: interval = nums[0]
            if len(nums) >= 2: remaining = nums[-1]
    return {
        "ATA": toks[0][:2],
        "POSITION": pos,
        "PART_NUMBER": pn,
        "SERIAL_NUMBER": sn,
        "DESCRIPTION": description,
        "INST_DATE": date_str,
        "TASK": task_inline,
        "TASK_NUMBER": task_number,
        "INTERVAL": interval,
        "REMAINING": remaining,
        "_page": page_num,
    }


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            for raw in text.splitlines():
                rec = _parse_line(raw.strip(), page_num)
                if rec is not None:
                    records.append(rec)
    return records
