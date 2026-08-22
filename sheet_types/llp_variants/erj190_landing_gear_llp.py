"""ERJ 190 landing-gear LLP — "LIFE LIMITS PARTS STATUS LIST" (one file per
gear position: RH MLG / LH MLG / NLG). Header carries A/C REG, MSN, current
LDG TSN/TSO/CSN/CSO + A/C TT/TC, DOM and the next-overhaul date.

Row format (single line, space-separated) — one row per assembly AND one row
per its numbered sub-component, both shapes carrying the same trailing 8
fields:

    MLG STRUT STAY 190-70200-402 00256 15,708 15,708 56,000 40,292 25,000 9,292 12 1.7
    1 MLG MAIN FITTING 2822-0111 L1068 15,708 15,708 56,000 40,292 25,000 9,292 12 1.7

Anchors:
    - Trailing 8 fields are always CSN, CSO, CYCLE_LIMIT, CYCLE_REMAINING,
      OVH_LIMIT, OVH_REMAINING, YEAR_LIMIT, YEARS_REMAINING (REMAINING =
      LIMIT - CSN holds on every row checked). Taken by fixed position, not
      an open-ended numeric walk-back: several serial numbers are themselves
      plain digits (e.g. "00256", "1028") and would otherwise get swallowed
      into the trail.
    - A leading integer token is ITEM_NO, renumbered from 1 under each
      assembly. Its absence marks an assembly-header row -- itself a real
      serialized part, not just a section label, so it gets its own record
      too (unlike a pure separator row).

Assembly headers forward-fill onto their numbered children as ASSEMBLY, then
reset at the next assembly header.

MSN isn't always printed -- absent on one of the 4 known source files (a
different tail, same template) -- so it's read as optional, not required.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.llp_variants._base import merged_rules

NAME = "ERJ190 Landing Gear LLP"
SIGNATURES = [
    "LIFE LIMITS PARTS STATUS LIST",
    "SERIAL NUMBER CSN CSO LIFE LIMIT",
]

CANONICAL_COLUMNS = [
    "ITEM_NO",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "CSN",
    "CSO",
    "CYCLE_LIMIT",
    "CYCLE_REMAINING",
    "OVH_LIMIT",
    "OVH_REMAINING",
    "YEAR_LIMIT",
    "YEARS_REMAINING",
    "ASSEMBLY",
    # File metadata — same on every row
    "POSITION",
    "AIRCRAFT_MODEL",
    "MSN",
    "AC_REG",
    "REPORT_DATE",
    "LDG_TSN",
    "LDG_TSO",
    "AC_TT",
    "LDG_CSN",
    "LDG_CSO",
    "AC_TC",
    "DOM",
    "NEXT_OVH",
]

# Cycle bound mirrors the engine-LLP convention used across the other LLP
# variants (0..55000, review band 0..30000). Landing-gear limits here run
# past it (STEERING CYLINDER at 82,400) -- same class of part amos.py
# already notes tripping this bound on purpose; it's a downstream review
# signal, not a mis-set threshold.
_CYCLE_RULE = {"pattern": r"^[\d,]+$", "int_range": (0, 55000),
               "int_range_review": (0, 30000)}
_YEAR_LIMIT_RULE = {"pattern": r"^\d+$"}
_YEARS_REMAIN_RULE = {"pattern": r"^\d+(?:\.\d+)?$"}
# LDG TSN/TSO and A/C TT print as HHHHH:MM, not a plain integer -- no
# int_range here, since the shared thousands-parser can't read the colon
# and would flag every row "not_a_number".
_TIME_HHMM_RULE = {"pattern": r"^\d+:\d{2}$"}
_PLAIN_INT_RULE = {"pattern": r"^\d+$"}
_DATE_RULE = {"pattern": r"^\d{1,2}-[A-Za-z]{3}-\d{2}$"}

_OVERRIDES = {
    "ITEM_NO":         {"pattern": r"^\d+$", "allow_empty": True},
    "CSN":             _CYCLE_RULE,
    "CSO":             _CYCLE_RULE,
    "CYCLE_LIMIT":     _CYCLE_RULE,
    "CYCLE_REMAINING": _CYCLE_RULE,
    "OVH_LIMIT":       _CYCLE_RULE,
    "OVH_REMAINING":   _CYCLE_RULE,
    "YEAR_LIMIT":      _YEAR_LIMIT_RULE,
    "YEARS_REMAINING": _YEARS_REMAIN_RULE,
    "AC_REG":          {"pattern": r"^[A-Z0-9\-]+$", "uppercase": True},
    "REPORT_DATE":     _DATE_RULE,
    "LDG_TSN":         _TIME_HHMM_RULE,
    "LDG_TSO":         _TIME_HHMM_RULE,
    "AC_TT":           _TIME_HHMM_RULE,
    "LDG_CSN":         _PLAIN_INT_RULE,
    "LDG_CSO":         _PLAIN_INT_RULE,
    "AC_TC":           _PLAIN_INT_RULE,
    "DOM":             _DATE_RULE,
    "NEXT_OVH":        _DATE_RULE,
}
RULES = merged_rules(_OVERRIDES)

_NUM_RE = re.compile(r"^[\d,]+(?:\.\d+)?$")

_TITLE_RE = re.compile(
    r"^(RIGHT MAIN LANDING GEAR|LEFT MAIN LANDING GEAR|NOSE LANDING GEAR)\s+(\S.*)$"
)
_META_PATTERNS = [
    ("MSN",          r"MSN-\s*(\S+)"),
    ("AC_REG",       r"A/C REG:\s*(\S+)"),
    ("REPORT_DATE",  r"DATE:\s*(\S+)"),
    ("LDG_TSN",      r"LDG TSN:\s*(\S+)"),
    ("LDG_TSO",      r"LDG TSO:\s*(\S+)"),
    ("AC_TT",        r"A/C TT:\s*(\S+)"),
    ("LDG_CSN",      r"LDG CSN:\s*(\S+)"),
    ("LDG_CSO",      r"LDG CSO:\s*(\S+)"),
    ("AC_TC",        r"A/C TC:\s*(\S+)"),
    ("DOM",          r"\bDOM\s+(\S+)"),
    ("NEXT_OVH",     r"NEXT OVH\s+(\S+)"),
]


def _parse_meta(text: str) -> dict:
    meta: dict[str, str] = {}
    for line in text.splitlines()[:3]:
        m = _TITLE_RE.match(line.strip())
        if m:
            meta["POSITION"], meta["AIRCRAFT_MODEL"] = m.group(1), m.group(2)
            break
    for key, pattern in _META_PATTERNS:
        m = re.search(pattern, text)
        if m:
            meta[key] = m.group(1)
    return meta


def _parse_row(line: str) -> dict | None:
    toks = line.split()
    if len(toks) < 11:
        return None
    trail = toks[-8:]
    if not all(_NUM_RE.match(t) for t in trail):
        return None
    sn = toks[-9]
    pn = toks[-10]
    head = toks[:-10]
    if not head:
        return None
    if head[0].isdigit() and len(head) > 1:
        item_no, desc = head[0], " ".join(head[1:])
    else:
        item_no, desc = "", " ".join(head)

    rec = {c: "" for c in CANONICAL_COLUMNS}
    rec["ITEM_NO"] = item_no
    rec["DESCRIPTION"] = desc
    rec["PART_NUMBER"] = pn
    rec["SERIAL_NUMBER"] = sn
    (rec["CSN"], rec["CSO"], rec["CYCLE_LIMIT"], rec["CYCLE_REMAINING"],
     rec["OVH_LIMIT"], rec["OVH_REMAINING"], rec["YEAR_LIMIT"],
     rec["YEARS_REMAINING"]) = trail
    return rec


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        full_text = "\n".join((p.extract_text() or "") for p in pdf.pages)
        meta = _parse_meta(full_text)
        current_assembly = ""
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if len(text) < 100:
                continue
            for line in text.splitlines():
                rec = _parse_row(line)
                if rec is None:
                    continue
                if rec["ITEM_NO"]:
                    rec["ASSEMBLY"] = current_assembly
                else:
                    current_assembly = rec["DESCRIPTION"]
                for k, v in meta.items():
                    rec[k] = v
                rec["_page"] = page_num
                records.append(rec)
    return records
