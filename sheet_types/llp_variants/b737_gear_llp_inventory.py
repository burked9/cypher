"""Boeing 737 gear LLP inventory -- "<POSITION> LANDING GEAR AND LIFE LIMIT
PART STATUS[ AS REMOVED]", form TP-023 (NLG) / TP-024 (MLG). Confirmed on
PK-CMH (B737-86Q, installed-gear sub-layout) and PK-CMN (B737-86J,
as-removed sub-layout); the header block, row grammar and part-number shape
are identical, only the trailing numeric-column count differs.

One row per part, all figures already computed rather than derived from a
separate requirement line (contrast amos.py / landing_gear_llp_report.py,
which pair a component row with 1+ time-basis requirement rows)::

    9 Pin (Braking Torque) 162A2301-2 01579T788 75.000 18.000 10 13.742 0
    25.069 11.327 6.673 49.931 1.094

    ITEM DESCRIPTION PART_NUMBER SERIAL_NUMBER LIFE_LIMIT_CYCLES
    OVERHAUL_LIMIT_CYCLES LIMIT_YEARS CSN_INSTALL CSO_INSTALL CSN_CURRENT
    CSO_CURRENT REMAIN_TO_OVERHAUL_CYCLES REMAIN_TO_LIFE_CYCLES
    REMAIN_TO_OVERHAUL_DAYS

Anchor: ITEM is a leading integer (0 on one file's first row); PART_NUMBER
always matches Boeing's `\\d{3}[A-Z]\\d{3,4}-\\d{1,2}` shape and never
collides with a DESCRIPTION word, so it's found by pattern rather than by
fixed offset -- DESCRIPTION runs from ITEM to PART_NUMBER and is free to
contain commas/hyphens ("PIN - TRUNNION, DRAG STRUT, LEFT").

Trailing-column count is a genuine per-file split, not noise: PK-CMH's two
files (Form TP-023, TP-024 "current status") print 10 columns ending in
REMAIN_TO_OVERHAUL_DAYS; PK-CMN's two (Form. TP-024 "AS REMOVED") print only
9 -- a removed gear has no calendar-day-to-next-overhaul figure to show.
Bucketed by count per row (not assumed from the file header) since that's
the only signal available at parse time.

A second, unlabelled part table ("AIRFRAME LIFE LIMIT PARTS") follows the
gear's own table on 3 of the 4 known files, restarting ITEM at 1 -- tagged
via SECTION rather than merged into the gear table's numbering, since
collapsing the two would make two genuinely different item 1s
indistinguishable.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.llp_variants._base import merged_rules

NAME = "B737 Gear LLP Inventory"
SIGNATURES = [
    "MAINTENANCEPLANNING AND CONTROL",
    "LIFE LIMIT PART STATUS",
]

CANONICAL_COLUMNS = [
    "ITEM",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "LIFE_LIMIT_CYCLES",
    "OVERHAUL_LIMIT_CYCLES",
    "LIMIT_YEARS",
    "CSN_INSTALL",
    "CSO_INSTALL",
    "CSN_CURRENT",
    "CSO_CURRENT",
    "REMAIN_TO_OVERHAUL_CYCLES",
    "REMAIN_TO_LIFE_CYCLES",
    "REMAIN_TO_OVERHAUL_DAYS",
    "SECTION",
    # File-level metadata -- same on every row.
    "AIRCRAFT_TYPE",
    "AIRCRAFT_SN",
    "AIRCRAFT_REG",
    "GEAR_POSITION",
    "AS_REMOVED",
    "GEAR_ASSY_PN",
    "GEAR_ASSY_SN",
    "AC_TSN",
    "AC_CSN",
    "FORM_NUMBER",
]

_CYCLE_RULE = {"pattern": r"^[\d.,]+$", "int_range": (0, 90000),
               "int_range_review": (0, 55000), "allow_empty": True}
_OVERRIDES = {
    "ITEM":                      {"pattern": r"^\d+$"},
    "LIFE_LIMIT_CYCLES":         {"pattern": r"^(UNLIMITED|[\d.,]+)$"},
    "OVERHAUL_LIMIT_CYCLES":     _CYCLE_RULE,
    "LIMIT_YEARS":               {"pattern": r"^\d{1,3}$"},
    "CSN_INSTALL":               _CYCLE_RULE,
    "CSO_INSTALL":               _CYCLE_RULE,
    "CSN_CURRENT":               _CYCLE_RULE,
    "CSO_CURRENT":               _CYCLE_RULE,
    "REMAIN_TO_OVERHAUL_CYCLES": _CYCLE_RULE,
    "REMAIN_TO_LIFE_CYCLES":     {"pattern": r"^(N/A|[\d.,]+)$", "allow_empty": True},
    "REMAIN_TO_OVERHAUL_DAYS":   {"pattern": r"^(NA|[\d.,]+)$", "allow_empty": True},
    "AIRCRAFT_REG":              {"pattern": r"^[A-Z0-9\-]+$", "uppercase": True},
    "AIRCRAFT_TYPE":             {"pattern": r"^[A-Z0-9\-]+$", "uppercase": True},
}
RULES = merged_rules(_OVERRIDES)

_PN_RE = re.compile(r"^\d{3}[A-Z]\d{3,4}-\d{1,2}$")
_TRAIL_KEYS_10 = ["LIFE_LIMIT_CYCLES", "OVERHAUL_LIMIT_CYCLES", "LIMIT_YEARS",
                  "CSN_INSTALL", "CSO_INSTALL", "CSN_CURRENT", "CSO_CURRENT",
                  "REMAIN_TO_OVERHAUL_CYCLES", "REMAIN_TO_LIFE_CYCLES",
                  "REMAIN_TO_OVERHAUL_DAYS"]
_TRAIL_KEYS_9 = _TRAIL_KEYS_10[:-1]

_TITLE_RE = re.compile(r"^(.+?) AND LIFE LIMIT PART STATUS( AS REMOVED)?\s*$", re.M)
_TYPE_RE = re.compile(r"AIRCRAFT TYPE\s*:\s*(\S+)")
_AC_SN_RE = re.compile(r"AIRCRAFT S/N\s*:\s*(\S+)")
_REG_RE = re.compile(r"AIRCRAFT REG\.?\s*:\s*(\S+)")
_ASSY_PN_RE = re.compile(r"(?:INSTALLATION|ASSY)\s+P/N\s*:\s*(\S+)")
_ASSY_SN_RE = re.compile(r"(?:INSTALLATION|ASSY)\s+S/N\s*:\s*(\S+)")
_AC_TSN_RE = re.compile(r"A/C TSN\s*:\s*(\S+)")
_AC_CSN_RE = re.compile(r"A/C CSN\s*:\s*(\S+)")
_FORM_RE = re.compile(r"Form\.?\s+(TP-\d+)")
_AIRFRAME_SECTION = "AIRFRAME LIFE LIMIT PARTS"


def _parse_meta(text: str) -> dict:
    meta: dict[str, str] = {}
    m = _TITLE_RE.search(text)
    if m:
        meta["GEAR_POSITION"] = m.group(1).strip()
        meta["AS_REMOVED"] = "TRUE" if m.group(2) else "FALSE"
    for pat, key in ((_TYPE_RE, "AIRCRAFT_TYPE"), (_AC_SN_RE, "AIRCRAFT_SN"),
                     (_REG_RE, "AIRCRAFT_REG"), (_ASSY_PN_RE, "GEAR_ASSY_PN"),
                     (_ASSY_SN_RE, "GEAR_ASSY_SN"), (_FORM_RE, "FORM_NUMBER")):
        m = pat.search(text)
        if m:
            meta[key] = m.group(1).strip()
    # Each label appears twice (install-time, then current) -- findall + last
    # rather than first-match-wins, since current is the more useful figure
    # and there's no other way to tell the two occurrences apart by regex.
    tsn_all = _AC_TSN_RE.findall(text)
    if tsn_all:
        meta["AC_TSN"] = tsn_all[-1]
    csn_all = _AC_CSN_RE.findall(text)
    if csn_all:
        meta["AC_CSN"] = csn_all[-1]
    return meta


def _parse_row(line: str, section: str) -> dict | None:
    toks = line.split()
    if len(toks) < 6 or not toks[0].isdigit():
        return None
    pn_idx = next((i for i in range(1, len(toks)) if _PN_RE.match(toks[i])), None)
    if pn_idx is None or pn_idx + 1 >= len(toks):
        return None
    trail = toks[pn_idx + 2:]
    if len(trail) == 10:
        keys = _TRAIL_KEYS_10
    elif len(trail) == 9:
        keys = _TRAIL_KEYS_9
    else:
        return None

    rec = {c: "" for c in CANONICAL_COLUMNS}
    rec["ITEM"] = toks[0]
    rec["DESCRIPTION"] = " ".join(toks[1:pn_idx])
    rec["PART_NUMBER"] = toks[pn_idx]
    rec["SERIAL_NUMBER"] = toks[pn_idx + 1]
    for k, v in zip(keys, trail):
        rec[k] = v
    rec["SECTION"] = section
    return rec


def extract(pdf_path: str) -> list[dict]:
    with pdfplumber.open(pdf_path) as pdf:
        full_text = "\n".join((p.extract_text() or "") for p in pdf.pages)
        meta = _parse_meta(full_text)

        records: list[dict] = []
        section = ""
        for page in pdf.pages:
            text = page.extract_text() or ""
            for raw in text.splitlines():
                line = raw.strip()
                if line == _AIRFRAME_SECTION:
                    section = line
                    continue
                rec = _parse_row(line, section)
                if rec is None:
                    continue
                for k, v in meta.items():
                    rec[k] = v
                records.append(rec)
    return records
