"""SAS Drawing Item LLP -- per-leg "Life Limited Parts" gear status sheet.

One file per gear leg (NLG / LH MLG / RH MLG), each a single flat table keyed
to a Boeing/MDC drawing item number rather than a part-family code. Header
block (repeated wrapping varies by file -- pdfplumber's column grouping
splits the two-line "*Drawing Item No. ... Cycles Remaining" header
differently depending on how many words happen to share a text row):

    Life Limited Parts
    RH Main Landing Gear Current Position: LN-XXX
    As of: 01-Jun-18
    When Airframe CSN: 44,438
    Cycle Cycles
    *Drawing Item No. PN S/N Description Position CSN Remarks
    Limit Remaining

Row grammar -- Item, PN, S/N, Description, Position, CSN, Cycle Limit,
Cycles Remaining, Remarks:

    2.0 162A1100-5 T9661Y0329 NOSE LANDING GEAR - 43,731 N/A -
    Part of 2.1 (1) 162A1411-1 AV0056 PIN, STEERING COLLAR ATT - NLG - LH LH 13,819 75,000 61,181

Anchor on PN (regex, not token count): Item is free-form ("2.0", "3.1.2.1",
"Part of 2 (1)", "6.5 (1)*") and can't be split from PN by counting tokens,
but PN's own shape (digits-letter-digits, e.g. "162A1100-5" or the
suffix-less "161A1185") never occurs in an Item token, so PN is just "the
first token after position 0 matching that shape"; everything left of it is
Item, and S/N is the token immediately after it.

The rest of the row (after S/N) is peeled from the right, remarks first:
trailing tokens that aren't drawn from the Position/CSN/limit vocabulary
("Shimmy Dampers fitted") are remarks, not data. What's left is then read as
up to 4 trailing tokens -- Position, CSN, Cycle Limit, Cycles Remaining, in
that order -- capped at 4 so a mid-description dash ("STEERING COLLAR ATT -
NLG -") is never mistaken for a column. Side-specific parts genuinely repeat
their own Position in the Description text too ("... NLG - LH LH 13,819"),
so the duplicate is real data, not a parse error: the second occurrence is
the actual Position column, the first stays part of the description. Some
rows drop trailing columns rather than padding them -- the two on-condition
bearing assemblies print Position+CSN+Limit but no Cycles Remaining, and the
two "TORSION LINK APEX" pins (Shimmy Dampers fitted, no hard limit) print
only Position+CSN -- so the tail is read short rather than assumed fixed-width.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.llp_variants._base import merged_rules

NAME = "SAS Drawing Item LLP"
SIGNATURES = [
    "When Airframe CSN:",
    "Drawing Item",
]

CANONICAL_COLUMNS = [
    "DRAWING_ITEM_NO",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
    "POSITION",
    "CSN",
    "CYCLE_LIMIT",
    "CYCLES_REMAINING",
    "REMARKS",
    # File-level metadata -- same on every row of a given gear-leg file
    "GEAR_ASSEMBLY",
    "AC_REGISTRATION",
    "STATUS_DATE",
    "AIRFRAME_CSN",
]

_VALUE_RULE = {"pattern": r"^(?:[\d,]+|N/A|NA|OCCM|-)$", "allow_empty": True}
_OVERRIDES = {
    "DRAWING_ITEM_NO": {"pattern": r"^[A-Za-z0-9.() ]+\*{0,2}$"},
    "POSITION": {"pattern": r"^(?:-|LH|RH|UP|LW|FW|RA|LA|LF|NA|N/A)$",
                 "uppercase": True},
    "CSN": _VALUE_RULE,
    "CYCLE_LIMIT": _VALUE_RULE,
    "CYCLES_REMAINING": _VALUE_RULE,
    "AC_REGISTRATION": {"pattern": r"^[A-Z0-9\-]+$", "uppercase": True},
    "STATUS_DATE": {"pattern": r"^\d{2}-[A-Za-z]{3}-\d{2}$"},
    "AIRFRAME_CSN": {"pattern": r"^[\d,]+$"},
}
RULES = merged_rules(_OVERRIDES)

_ROW_START_RE = re.compile(r"^(?:Part|\d+(?:\.\d+)*\*{0,2})$")
_PN_RE = re.compile(r"^\d+[A-Z]\d+(?:-\d+)?$", re.I)
_POS_CODES = {"-", "LH", "RH", "UP", "LW", "FW", "RA", "LA", "LF", "NA", "N/A"}
_VALUE_RE = re.compile(r"^(?:\d[\d,]*|N/A|NA|OCCM|-)$")

_GEAR_RE = re.compile(r"^(.+?)\s+Current Position:\s*(\S+)")
_ASOF_RE = re.compile(r"^As of:\s*(\S+)")
_AIRFRAME_CSN_RE = re.compile(r"^When Airframe CSN:\s*([\d,]+)")


def _is_tail_tok(tok: str) -> bool:
    return tok in _POS_CODES or bool(_VALUE_RE.match(tok))


def _parse_meta(text: str) -> dict:
    meta: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        m = _GEAR_RE.match(line)
        if m:
            meta["GEAR_ASSEMBLY"] = m.group(1)
            meta["AC_REGISTRATION"] = m.group(2)
            continue
        m = _ASOF_RE.match(line)
        if m:
            meta["STATUS_DATE"] = m.group(1)
            continue
        m = _AIRFRAME_CSN_RE.match(line)
        if m:
            meta["AIRFRAME_CSN"] = m.group(1)
    return meta


def _parse_row(line: str) -> dict | None:
    toks = line.split()
    if not toks or not _ROW_START_RE.match(toks[0]):
        return None
    pn_idx = next((i for i in range(1, len(toks)) if _PN_RE.match(toks[i])), None)
    if pn_idx is None or pn_idx + 1 >= len(toks):
        return None

    rest = toks[pn_idx + 2:]
    if not rest:
        return None

    end = len(rest)
    while end > 0 and not _is_tail_tok(rest[end - 1]):
        end -= 1
    remarks = " ".join(rest[end:])
    rest = rest[:end]

    tail: list[str] = []
    i = len(rest)
    while i > 0 and len(tail) < 4 and _is_tail_tok(rest[i - 1]):
        tail.insert(0, rest[i - 1])
        i -= 1

    rec = {c: "" for c in CANONICAL_COLUMNS}
    rec["DRAWING_ITEM_NO"] = " ".join(toks[:pn_idx])
    rec["PART_NUMBER"] = toks[pn_idx]
    rec["SERIAL_NUMBER"] = toks[pn_idx + 1]
    rec["DESCRIPTION"] = " ".join(rest[:i])
    rec["REMARKS"] = remarks
    for col, val in zip(("POSITION", "CSN", "CYCLE_LIMIT", "CYCLES_REMAINING"), tail):
        rec[col] = val
    return rec


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        full_text = "\n".join((p.extract_text() or "") for p in pdf.pages)
        meta = _parse_meta(full_text)
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            for raw in text.splitlines():
                line = raw.strip()
                if not line:
                    continue
                rec = _parse_row(line)
                if rec is None:
                    continue
                rec["_page"] = page_num
                for k, v in meta.items():
                    rec[k] = v
                records.append(rec)
    return records
