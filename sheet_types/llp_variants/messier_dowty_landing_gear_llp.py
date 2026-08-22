"""Messier-Dowty landing-gear LLP status — "<POSITION> LANDING GEAR STATUS".

Source format: per-gear (LH MLG / RH MLG / NLG) life-limited-parts status for
Messier-Dowty gear assemblies (seen on an Airbus A318). A single PDF can carry
more than one gear's table as separate pages, each page repeating its own
full header block (MSN, gear assy P/N & S/N, install date, current-status
date, current A/C TSN/CSN) — unlike the single-header-per-file engine LLP
variants, metadata here is parsed fresh per page and stamped only onto that
page's own rows.

Row format (single line, space-separated, numbers space-grouped in
thousands):

    1 SLN41193 REAR PINTLE PIN NUT MS51770-12372 60 000 20 000 10 9 211 \
10 477 9 211 10 477 0 29-Feb-08 9 523 2 007 49 523 28-Feb-18

    NO PART_NUMBER DESCRIPTION... SERIAL_NUMBER LIFE_LIMIT OVH_LIMIT YEARS \
TSN CSN TSO CSO CYCLES_AT_OVH OVH_DATE REMAIN_OVH_CYC REMAIN_OVH_DAYS \
REMAIN_LIFE_CYC NEXT_DUE_DATE

Anchor: after collapsing space-grouped thousands, the trailing 13 tokens are
always numeric / "N/A" / date-shaped, matching the header's own 13
sub-column labels ("CYCLES CYCLES YR TSN CSN TSO CSO CYCLES DATE CYCLES DAYS
CYCLES DATE"). SERIAL_NUMBER always carries a letter, so it never gets
swept into that trailing run. Rows that aren't life-limited (only
overhaul-limited) show "N/A" for LIFE_LIMIT_CYCLES / REMAIN_TO_LIFE_CYCLES.

A handful of rows per file (2 on the LH page, 1 each on the RH/NLG pages
seen so far) render with every character doubled ("1188 220011554400330000
MMAAIINN FFIITTTTIINNGG...") — a bold-emphasis line the source PDF draws
twice at a near-zero offset. Its trailing tokens no longer match the
numeric/date shape at all, so it fails the anchor and is silently skipped
rather than stored garbled.

Note: a same-fleet file named with the unrelated "<MSN>_E307_LLP_Inventory_
MLG <side>_<date>" convention (header "AIRCRAFT TYPE : B737-86Q...", form
"TP-024") is NOT this format despite the superficially similar filename —
it's a Boeing 737 gear-and-airframe LLP sheet with a completely different
row layout and belongs to a separate variant.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.llp_variants._base import merged_rules

NAME = "Messier-Dowty Landing Gear LLP"
SIGNATURES = [
    "LANDING GEAR STATUS",
    "MESSIER - DOWTY",
]

CANONICAL_COLUMNS = [
    "NO",
    "PART_NUMBER",
    "DESCRIPTION",
    "SERIAL_NUMBER",
    "LIFE_LIMIT_CYCLES",
    "OVH_LIMIT_CYCLES",
    "LIMIT_YEARS",
    "TSN",
    "CSN",
    "TSO",
    "CSO",
    "CYCLES_AT_LAST_OVH",
    "LAST_OVH_DATE",
    "REMAIN_TO_OVH_CYCLES",
    "REMAIN_TO_OVH_DAYS",
    "REMAIN_TO_LIFE_CYCLES",
    "NEXT_DUE_DATE",
    # Gear/aircraft metadata -- same on every row of a given page/section,
    # re-parsed per page since one PDF can hold more than one gear's table.
    "MSN",
    "AIRCRAFT_REG",
    "AIRCRAFT_TYPE",
    "GEAR_POSITION",
    "GEAR_ASSY_PN",
    "GEAR_ASSY_SN",
    "DATE_INSTALLED",
    "CURRENT_STATUS_DATE",
    "AC_TSN",
    "AC_CSN",
]

_HOUR_RULE = {"pattern": r"^[\d,]+$", "int_range": (0, 80000)}
# Landing-gear cycle limits run to 60k, above the 55k engine-LLP ceiling --
# same intentional trip amos.py already notes for landing-gear rows; it's a
# downstream review signal, not a threshold to widen away.
_CYCLE_RULE = {"pattern": r"^[\d,]+$", "int_range": (0, 55000),
               "int_range_review": (0, 30000)}
_DAYS_RULE = {"pattern": r"^[\d,]+$", "int_range": (0, 20000)}
_DATE_RULE = {"pattern": r"^\d{1,2}-[A-Za-z]{3}-\d{2}$"}
_OVERRIDES = {
    "NO":                    {"pattern": r"^\d+$"},
    "LIFE_LIMIT_CYCLES":     _CYCLE_RULE,
    "OVH_LIMIT_CYCLES":      _CYCLE_RULE,
    "LIMIT_YEARS":           {"pattern": r"^\d{1,3}$"},
    "TSN":                   _HOUR_RULE,
    "CSN":                   _CYCLE_RULE,
    "TSO":                   _HOUR_RULE,
    "CSO":                   _CYCLE_RULE,
    "CYCLES_AT_LAST_OVH":    _CYCLE_RULE,
    "LAST_OVH_DATE":         _DATE_RULE,
    "REMAIN_TO_OVH_CYCLES":  _CYCLE_RULE,
    "REMAIN_TO_OVH_DAYS":    _DAYS_RULE,
    "REMAIN_TO_LIFE_CYCLES": _CYCLE_RULE,
    "NEXT_DUE_DATE":         _DATE_RULE,
    "AIRCRAFT_REG":          {"pattern": r"^[A-Z0-9\-]+$", "uppercase": True},
    "AIRCRAFT_TYPE":         {"pattern": r"^[A-Z0-9\-]+$", "uppercase": True},
    "GEAR_POSITION":         {"uppercase": True},
    "DATE_INSTALLED":        _DATE_RULE,
    "CURRENT_STATUS_DATE":   _DATE_RULE,
    "AC_TSN":                _HOUR_RULE,
    "AC_CSN":                _CYCLE_RULE,
}
RULES = merged_rules(_OVERRIDES)

# Trailing shape: space-collapsed integer, "N/A", or a "29-Feb-08" date.
_TRAIL_RE = re.compile(r"^(?:[\d,]+|N/A|\d{1,2}-[A-Za-z]{3}-\d{2,4})$", re.I)
_SPACE_THOUSANDS_RE = re.compile(r"(?<!\S)(\d{1,3}(?: \d{3})+)(?!\S)")

_MSN_RE = re.compile(r"\bM\s*S\s*N\s*:\s*(\S+)", re.I)
_REG_RE = re.compile(r"AIRCRAFT REG\.?\s*:\s*(\S+)", re.I)
_TYPE_RE = re.compile(r"AIRCRAFT TYPE\s*:\s*(\S+)", re.I)
_POSITION_RE = re.compile(r"^MSN\s+\S+\s+\S+\s+(.+?)\s+STATUS\s*$", re.I)
# Deliberately unanchored to "MLG"/"NLG" -- the NLG page's own header still
# prints the label as "MLG ASSY P/N" (a copy-pasted template artifact).
_ASSY_PN_RE = re.compile(r"\bASSY P/N\s*:\s*(\S+)", re.I)
_ASSY_SN_RE = re.compile(r"\bASSY S/N\s*:\s*(\S+)", re.I)
_INSTALLED_RE = re.compile(r"DATE INSTALLED\s*:\s*(\S+)", re.I)
_STATUS_DATE_RE = re.compile(r"CURRENT STATUS\s*:\s*(\S+)", re.I)
_AC_TSN_RE = re.compile(r"A/C TSN\s*:\s*([\d ]+)", re.I)
_AC_CSN_RE = re.compile(r"A/C CSN\s*:\s*([\d ]+)", re.I)


def _collapse_space_thousands(line: str) -> str:
    return _SPACE_THOUSANDS_RE.sub(lambda m: m.group(1).replace(" ", ""), line)


def _parse_page_meta(text: str) -> dict:
    meta: dict[str, str] = {}
    for line in text.splitlines()[:12]:
        m = _POSITION_RE.match(line.strip())
        if m:
            meta["GEAR_POSITION"] = m.group(1).strip()
        m = _MSN_RE.search(line)
        if m:
            meta.setdefault("MSN", m.group(1))
        m = _REG_RE.search(line)
        if m:
            meta.setdefault("AIRCRAFT_REG", m.group(1))
        m = _TYPE_RE.search(line)
        if m:
            meta.setdefault("AIRCRAFT_TYPE", m.group(1))
        m = _ASSY_PN_RE.search(line)
        if m:
            meta.setdefault("GEAR_ASSY_PN", m.group(1))
        m = _ASSY_SN_RE.search(line)
        if m:
            meta.setdefault("GEAR_ASSY_SN", m.group(1))
        m = _INSTALLED_RE.search(line)
        if m:
            meta.setdefault("DATE_INSTALLED", m.group(1))
        m = _STATUS_DATE_RE.search(line)
        if m:
            meta.setdefault("CURRENT_STATUS_DATE", m.group(1))
        # Each of these labels appears twice (install-time, then current) --
        # plain overwrite so the later, current-status line wins.
        m = _AC_TSN_RE.search(line)
        if m:
            meta["AC_TSN"] = m.group(1).replace(" ", "").strip()
        m = _AC_CSN_RE.search(line)
        if m:
            meta["AC_CSN"] = m.group(1).replace(" ", "").strip()
    return meta


def _parse_row(line: str) -> dict | None:
    s = _collapse_space_thousands(line.strip())
    toks = s.split()
    if len(toks) < 6 or not toks[0].isdigit():
        return None

    trail: list[str] = []
    i = len(toks) - 1
    while i >= 0 and _TRAIL_RE.match(toks[i]):
        trail.insert(0, toks[i])
        i -= 1
    if len(trail) != 13:
        return None
    if i < 3:  # need NO, PART_NUMBER, >=1 DESCRIPTION word, SERIAL_NUMBER
        return None

    rec: dict[str, str] = {c: "" for c in CANONICAL_COLUMNS}
    rec["NO"] = toks[0]
    rec["PART_NUMBER"] = toks[1]
    rec["SERIAL_NUMBER"] = toks[i]
    rec["DESCRIPTION"] = " ".join(toks[2:i])

    keys = ["LIFE_LIMIT_CYCLES", "OVH_LIMIT_CYCLES", "LIMIT_YEARS", "TSN", "CSN",
            "TSO", "CSO", "CYCLES_AT_LAST_OVH", "LAST_OVH_DATE",
            "REMAIN_TO_OVH_CYCLES", "REMAIN_TO_OVH_DAYS",
            "REMAIN_TO_LIFE_CYCLES", "NEXT_DUE_DATE"]
    for k, v in zip(keys, trail):
        rec[k] = v
    return rec


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if len(text) < 50:
                continue
            meta = _parse_page_meta(text)
            for raw in text.splitlines():
                rec = _parse_row(raw)
                if rec is None:
                    continue
                for k, v in meta.items():
                    rec[k] = v
                rec["_page"] = page_num
                records.append(rec)
    return records
