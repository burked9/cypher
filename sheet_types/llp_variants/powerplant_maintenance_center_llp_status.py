"""Powerplant Maintenance Center "LIFE LIMITED PARTS STATUS" report --
single-page, real text layer (confirmed via direct pdfplumber inspection,
no OCR needed). Header carries an issuing facility line ("<operator> Date
of Issue : <date>"), a "POWERPLANT MAINTENANCE CENTER (FAA R/S No. ...,
EASA AMO ..., TDCA R/S No. ...)" facility block, the report title, then
engine model/serial, engine TSN/CSN, a repair order number, and a
customer/owner line -- all generic label:value pairs, not reproduced here
with any real value.

The body is organised into MODULE section headers of the shape::

    <MODULE NAME> Module <module code> TSN/CSN: <n>/<n> TSO/CSO: <n>/<n>

each followed by a run of numbered ITEM rows, one per life-limited part::

    <item#> <IIN> <description...> <P/N> <S/N> <TSN> <CSN> <P.CSN> <LIMIT> <REMAINING>

Confirmed by direct inspection of the sample file (41 numbered ITEM rows
across 5 module sections: LPC ROTOR, HPC ROTOR, HPT ROTOR, LPT ROTOR,
T/COUPLING). The MODULE NAME/code/TSN/CSN/TSO/CSO from each header is
forward-filled onto every row beneath it, mirroring how
egat_llp_on_log_list.py propagates its own MODULE_GROUP context.

Trailing numeric block noise: pdfplumber's text layer inserts a stray
space inside some of the five trailing numbers (thousands-formatted with
a comma), e.g. "8,680" comes back as "8 ,680" and "19,351" as "1 9,351" --
same value, just split across two whitespace-separated tokens. Footnote
asterisks ("*", "**", "***") also get glued onto the messier rows,
sometimes as their own token, sometimes touching a number. Handling:
strip every "*" first, then repeatedly merge any bare 1-3 digit orphan
token into the token immediately after it (concatenation, no separator)
until exactly five tokens remain -- this reconstructs the split number
regardless of exactly where the stray space landed (before or after the
comma). Verified against every one of the 41 real rows in the sample
file, including the messiest footnoted ones: it always resolves to
exactly five clean numeric tokens (TSN, CSN, P.CSN, LIFE_LIMIT,
REMAINING). No fallback catch-all field was needed.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.llp_variants._base import merged_rules

NAME = "Powerplant Maintenance Center LLP Status"

# "P.CSN" (this report's own column-header abbreviation for prorated CSN)
# and "POWERPLANT MAINTENANCE CENTER" (the issuing facility's own block
# heading) were both checked against every SIGNATURES list in
# sheet_types/{occm,ht,llp}.py and every existing {occm,ht,llp}_variants/*.py
# file -- no collisions found for either. The obvious "LIFE LIMITED PARTS
# STATUS" phrase alone was deliberately avoided: it's a plain substring of
# several other variants' own titles already in this list (e.g. "ENGINE
# LIFE LIMITED PARTS STATUS", "LANDING GEAR LIFE LIMITED PARTS STATUS"),
# so using it bare here would risk silently stealing their files.
SIGNATURES = [
    "POWERPLANT MAINTENANCE CENTER",
    "P.CSN",
]

CANONICAL_COLUMNS = [
    "ITEM_NO",
    "IIN",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "TSN",
    "CSN",
    "P_CSN",
    "LIFE_LIMIT",
    "REMAINING",
    "MODULE_NAME",
    "MODULE_CODE",
    "MODULE_TSN",
    "MODULE_CSN",
    "MODULE_TSO",
    "MODULE_CSO",
    # File-level metadata -- same on every row of a given file.
    "ENGINE_MODEL",
    "ENGINE_SERIAL_NUMBER",
    "ENGINE_TSN",
    "ENGINE_CSN",
    "REPAIR_ORDER_NO",
    "ISSUE_DATE",
]

_CYCLE_RULE = {"pattern": r"^[\d,]+$", "int_range": (0, 100000),
                "int_range_review": (0, 50000), "allow_empty": True}
_OVERRIDES = {
    "ITEM_NO":              {"pattern": r"^\d{1,3}$"},
    "IIN":                  {"pattern": r"^[A-Z]\d{3,4}$", "uppercase": True},
    "TSN":                  _CYCLE_RULE,
    "CSN":                  _CYCLE_RULE,
    "P_CSN":                _CYCLE_RULE,
    "LIFE_LIMIT":           _CYCLE_RULE,
    "REMAINING":            _CYCLE_RULE,
    "MODULE_TSN":           _CYCLE_RULE,
    "MODULE_CSN":           _CYCLE_RULE,
    "MODULE_TSO":           _CYCLE_RULE,
    "MODULE_CSO":           _CYCLE_RULE,
    "ENGINE_TSN":           _CYCLE_RULE,
    "ENGINE_CSN":           _CYCLE_RULE,
    "ENGINE_SERIAL_NUMBER": {"pattern": r"^[A-Z0-9]+$", "uppercase": True},
    "REPAIR_ORDER_NO":      {"pattern": r"^[A-Z0-9]+$", "uppercase": True, "allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_ROW_RE = re.compile(r"^(\d{1,3})\s+(\S+)\s+(.*)$")
_MODULE_RE = re.compile(
    r"^(.+?)\s+Module\s+(\S+)\s+TSN/CSN:\s*([\d,]+)\s*/\s*([\d,]+)\s+"
    r"TSO/CSO:\s*([\d,]+)\s*/\s*([\d,]+)\s*$"
)
_NUMERIC_TOK_RE = re.compile(r"^[0-9,*]+$")
_ORPHAN_RE = re.compile(r"^\d{1,3}$")

_ISSUE_DATE_RE = re.compile(r"Date of Issue\s*:\s*(.+)$", re.I | re.M)
_ENGINE_RE = re.compile(r"ENGINE MODEL\s*/\s*SERIAL NO\s*:\s*(\S+)\s*/\s*(\S+)", re.I)
_ENGINE_TSN_CSN_RE = re.compile(r"ENGINE TSN/CSN\s*:\s*([\d,]+)\s*/\s*([\d,]+)", re.I)
_REPAIR_ORDER_RE = re.compile(r"REPAIR ORDER NO\s*:\s*(\S+)", re.I)


def _merge_trailing(tokens: list[str]) -> list[str] | None:
    """Strip footnote asterisks, then merge stray-space-split thousands
    numbers by concatenating any bare 1-3 digit orphan token onto the
    token right after it, until exactly five tokens remain. Returns None
    if that can't be resolved (no fallback guess is made)."""
    toks = [t.replace("*", "") for t in tokens]
    toks = [t for t in toks if t]
    while len(toks) > 5:
        merged = False
        for i in range(len(toks) - 1):
            if _ORPHAN_RE.fullmatch(toks[i]):
                toks[i:i + 2] = [toks[i] + toks[i + 1]]
                merged = True
                break
        if not merged:
            return None
    if len(toks) != 5:
        return None
    return toks


def _parse_meta(text: str) -> dict:
    meta: dict[str, str] = {}
    m = _ISSUE_DATE_RE.search(text)
    if m:
        meta["ISSUE_DATE"] = m.group(1).strip()
    m = _ENGINE_RE.search(text)
    if m:
        meta["ENGINE_MODEL"] = m.group(1).strip()
        meta["ENGINE_SERIAL_NUMBER"] = m.group(2).strip()
    m = _ENGINE_TSN_CSN_RE.search(text)
    if m:
        meta["ENGINE_TSN"] = m.group(1)
        meta["ENGINE_CSN"] = m.group(2)
    m = _REPAIR_ORDER_RE.search(text)
    if m:
        meta["REPAIR_ORDER_NO"] = m.group(1).strip()
    return meta


def _parse_row(line: str) -> dict | None:
    m = _ROW_RE.match(line.strip())
    if not m:
        return None
    item_no, iin, rest = m.groups()
    parts = rest.split()
    # Trailing numeric block is a suffix of tokens made only of digits,
    # commas and asterisks; PART_NUMBER/SERIAL_NUMBER (and every
    # description token) always contain a letter, so scanning backward
    # from the end never mistakes them for part of the numeric block.
    j = len(parts)
    while j > 0 and _NUMERIC_TOK_RE.match(parts[j - 1]):
        j -= 1
    if j < 2:
        return None
    sn = parts[j - 1]
    pn = parts[j - 2]
    desc = " ".join(parts[:j - 2])
    trail = _merge_trailing(parts[j:])
    if trail is None:
        return None

    rec = {c: "" for c in CANONICAL_COLUMNS}
    rec["ITEM_NO"] = item_no
    rec["IIN"] = iin
    rec["DESCRIPTION"] = desc
    rec["PART_NUMBER"] = pn
    rec["SERIAL_NUMBER"] = sn
    rec["TSN"], rec["CSN"], rec["P_CSN"], rec["LIFE_LIMIT"], rec["REMAINING"] = trail
    return rec


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        full_text = "\n".join((p.extract_text() or "") for p in pdf.pages)
        meta = _parse_meta(full_text)
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            module_name = module_code = ""
            module_tsn = module_csn = module_tso = module_cso = ""
            for raw in text.splitlines():
                line = raw.strip()
                m = _MODULE_RE.match(line)
                if m:
                    module_name = m.group(1).strip()
                    module_code = m.group(2)
                    module_tsn, module_csn = m.group(3), m.group(4)
                    module_tso, module_cso = m.group(5), m.group(6)
                    continue
                rec = _parse_row(line)
                if rec is None:
                    continue
                rec["MODULE_NAME"] = module_name
                rec["MODULE_CODE"] = module_code
                rec["MODULE_TSN"] = module_tsn
                rec["MODULE_CSN"] = module_csn
                rec["MODULE_TSO"] = module_tso
                rec["MODULE_CSO"] = module_cso
                for k, v in meta.items():
                    rec[k] = v
                rec["_page"] = page_num
                records.append(rec)
    return records
