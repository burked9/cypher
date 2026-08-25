"""Aircraft LLP Status Report — per-component "LLP Status Report" snapshot.

Source format: a fleet-management export headed by a single top-level
component (a landing gear leg OR a whole engine — same template either way,
only the component description differs), followed by a flat list of that
component's life-limited sub-parts. Confirmed on both a landing gear's MLG
RH/LH leg reports and that same aircraft's engine reports, which share this
exact header and row grammar, which is why they're one variant, not two,
despite covering different ATA systems.

Header block (repeated per page):
    LLP Status Report Page : 1 of 1
    Part Number Description Serial Number Install Date TSN CSN Position
    201540002-40 MAIN LANDING GEAR LEG MDL4766 08Jun2008 42074:50 14945 RH
    Aircraft Reg Model MSN Manufactured AC TSN AC CSN Last Flight
    <REG> A319-112 <MSN> 27Oct2008 25678:45 19050 21Dec2019
    Life Limit Life at Install Life Since New Life Remaining
    Component Part Serial Limit Hours Cycles Hours Cycles Hours Cycles Hours Cycles Due Date

Data row (one sub-part; optionally preceded by an all-caps/mixed-case module
line like "HPC ROTOR ASSEMBLY" or "Accessories / Other" with no numbers)::

    FORWARD PINTLE PIN 201173600 08MDG5492 Discard LLP - 60000 0:00 0 42074:50 14945 45055
    EAL

Anchor: the two "H:MM" tokens (hours-at-install, hours-since-new), each
immediately followed by its cycles counterpart. The life-limit-type phrase
("Overhaul" / "Discard LLP -" / "Cleaning") is the only Title-Case word in
the line — descriptions are all-caps, PN/SN are alphanumeric — so it marks
the DESC | PN | SN boundary without needing a fixed token-count.

"EAL" ("End of Approved Life") habitually wraps onto its own physical line
because the type column is narrow; when a description word wraps too it
rides along on the same line (e.g. "BOLT EAL" = DESCRIPTION continuation
"BOLT" + type-phrase continuation "EAL"). Any 0-H:MM-token line that isn't
one of those wraps is a new module heading.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.llp_variants._base import merged_rules

NAME = "Aircraft LLP Status Report"
SIGNATURES = [
    "LLP Status Report",
]

CANONICAL_COLUMNS = [
    "MODULE",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "LIFE_LIMIT_TYPE",
    "LIMIT",
    "HOURS_AT_INSTALL",
    "CYCLES_AT_INSTALL",
    "HOURS_SINCE_NEW",
    "CYCLES_SINCE_NEW",
    "REMAINING",
    "DUE_DATE",
    # Top-assembly + aircraft metadata -- same on every row of a given file
    "COMPONENT_DESCRIPTION",
    "COMPONENT_PART_NUMBER",
    "COMPONENT_SERIAL_NUMBER",
    "COMPONENT_INSTALL_DATE",
    "COMPONENT_TSN",
    "COMPONENT_CSN",
    "COMPONENT_POSITION",
    "AIRCRAFT_REG",
    "AIRCRAFT_MODEL",
    "MSN",
    "MANUFACTURED_DATE",
    "AC_TSN",
    "AC_CSN",
    "LAST_FLIGHT",
]

_HOUR_RULE = {"pattern": r"^\d+:\d{2}$"}
_CYCLE_RULE = {"pattern": r"^\d+$", "int_range": (0, 55000),
               "int_range_review": (0, 30000), "allow_empty": True}
_DATE_RULE = {"pattern": r"^\d{1,2}[A-Za-z]{3}\d{4}$", "allow_empty": True}
_OVERRIDES = {
    "LIMIT":              {"pattern": r"^\d+$", "allow_empty": True},
    "HOURS_AT_INSTALL":   _HOUR_RULE,
    "CYCLES_AT_INSTALL":  _CYCLE_RULE,
    "HOURS_SINCE_NEW":    _HOUR_RULE,
    "CYCLES_SINCE_NEW":   _CYCLE_RULE,
    "REMAINING":          _CYCLE_RULE,
    "DUE_DATE":           _DATE_RULE,
    "COMPONENT_INSTALL_DATE": {**_DATE_RULE, "allow_empty": False},
    "COMPONENT_TSN":      _HOUR_RULE,
    "COMPONENT_CSN":      _CYCLE_RULE,
    "AIRCRAFT_REG":       {"pattern": r"^[A-Z0-9\-]+$", "uppercase": True},
    "MANUFACTURED_DATE":  {**_DATE_RULE, "allow_empty": False},
    "AC_TSN":             _HOUR_RULE,
    "AC_CSN":             _CYCLE_RULE,
    "LAST_FLIGHT":        {**_DATE_RULE, "allow_empty": False},
}
RULES = merged_rules(_OVERRIDES)

_HMM_RE = re.compile(r"^\d+:\d{2}$")
_INT_RE = re.compile(r"^\d+$")
_DATE_RE = re.compile(r"^\d{1,2}[A-Za-z]{3}\d{4}$")
_TYPE_WORD_RE = re.compile(r"^[A-Z][a-z]+$")

_SKIP_FRAGMENTS = (
    "LLP Status Report",
    "Part Number Description Serial Number",
    "Aircraft Reg Model MSN",
    "Life Limit Life at Install",
    "Component Part Serial Limit",
    "Created by",
)


def _is_skip_line(line: str) -> bool:
    return any(frag in line for frag in _SKIP_FRAGMENTS)


def _parse_meta(text: str) -> dict:
    meta: dict[str, str] = {}
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == ("Part Number Description Serial Number Install "
                             "Date TSN CSN Position") and i + 1 < len(lines):
            toks = lines[i + 1].split()
            hmm = [j for j, t in enumerate(toks) if _HMM_RE.match(t)]
            if len(hmm) == 1 and "COMPONENT_PART_NUMBER" not in meta:
                h = hmm[0]
                if h >= 2 and h + 2 < len(toks):
                    meta["COMPONENT_PART_NUMBER"] = toks[0]
                    meta["COMPONENT_DESCRIPTION"] = " ".join(toks[1:h - 2])
                    meta["COMPONENT_SERIAL_NUMBER"] = toks[h - 2]
                    meta["COMPONENT_INSTALL_DATE"] = toks[h - 1]
                    meta["COMPONENT_TSN"] = toks[h]
                    meta["COMPONENT_CSN"] = toks[h + 1]
                    meta["COMPONENT_POSITION"] = " ".join(toks[h + 2:])
        if line.strip() == ("Aircraft Reg Model MSN Manufactured AC TSN AC "
                             "CSN Last Flight") and i + 1 < len(lines):
            toks = lines[i + 1].split()
            if len(toks) >= 7 and "AIRCRAFT_REG" not in meta:
                meta["AIRCRAFT_REG"] = toks[0]
                meta["AIRCRAFT_MODEL"] = toks[1]
                meta["MSN"] = toks[2]
                meta["MANUFACTURED_DATE"] = toks[3]
                meta["AC_TSN"] = toks[4]
                meta["AC_CSN"] = toks[5]
                meta["LAST_FLIGHT"] = toks[6]
    return meta


def _parse_row(line: str) -> dict | None:
    toks = line.split()
    hmm_idx = [i for i, t in enumerate(toks) if _HMM_RE.match(t)]
    if len(hmm_idx) != 2:
        return None
    i1, i2 = hmm_idx
    if i2 <= i1 + 1 or i1 + 1 >= len(toks) or i2 + 1 >= len(toks):
        return None
    cyc_install, cyc_new = toks[i1 + 1], toks[i2 + 1]
    if not (_INT_RE.match(cyc_install) and _INT_RE.match(cyc_new)):
        return None

    trail = toks[i2 + 2:]
    remaining = trail[0] if trail and _INT_RE.match(trail[0]) else ""
    due_date = trail[1] if len(trail) > 1 and _DATE_RE.match(trail[1]) else ""

    pre = toks[:i1]
    limit = ""
    if pre and _INT_RE.match(pre[-1]):
        limit = pre[-1]
        pre = pre[:-1]

    type_start = None
    for i in range(len(pre) - 1, -1, -1):
        if _TYPE_WORD_RE.match(pre[i]):
            type_start = i
            break
    if type_start is None or type_start < 2:
        return None

    desc = " ".join(pre[:type_start - 2])
    if not desc:
        return None

    rec = {c: "" for c in CANONICAL_COLUMNS}
    rec["DESCRIPTION"] = desc
    rec["PART_NUMBER"] = pre[type_start - 2]
    rec["SERIAL_NUMBER"] = pre[type_start - 1]
    rec["LIFE_LIMIT_TYPE"] = " ".join(pre[type_start:])
    rec["LIMIT"] = limit
    rec["HOURS_AT_INSTALL"] = toks[i1]
    rec["CYCLES_AT_INSTALL"] = cyc_install
    rec["HOURS_SINCE_NEW"] = toks[i2]
    rec["CYCLES_SINCE_NEW"] = cyc_new
    rec["REMAINING"] = remaining
    rec["DUE_DATE"] = due_date
    return rec


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        full_text = "\n".join((p.extract_text() or "") for p in pdf.pages)
        meta = _parse_meta(full_text)
        current_module = ""
        last_record: dict | None = None
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            for raw in text.splitlines():
                line = raw.strip()
                if not line or _is_skip_line(line):
                    continue
                rec = _parse_row(line)
                if rec is not None:
                    rec["MODULE"] = current_module
                    rec["_page"] = page_num
                    for k, v in meta.items():
                        rec[k] = v
                    records.append(rec)
                    last_record = rec
                    continue

                toks = line.split()
                # Restated top-assembly/aircraft metadata line (repeats on
                # every page) -- already captured once above, and it must be
                # excluded here or it gets mistaken for a module heading.
                if any(_HMM_RE.match(t) for t in toks):
                    continue
                if toks and toks[-1] == "EAL" and last_record is not None:
                    wrap = toks[:-1]
                    if wrap:
                        last_record["DESCRIPTION"] = (
                            last_record["DESCRIPTION"] + " " + " ".join(wrap)
                        ).strip()
                    last_record["LIFE_LIMIT_TYPE"] = (
                        last_record["LIFE_LIMIT_TYPE"] + " EAL"
                    ).strip()
                    continue
                current_module = line
                last_record = None
    return records
