"""Landing Gear LLP Report — "LANDING GEAR LIFE LIMIT PARTS REPORT" (task-code
tracked, database-generated). Confirmed on CC-CZU (B767) and PR-MAP (A320);
header field layout and number formatting (`.` vs `,` decimals, 1 vs 2
trailing task-code columns) differ slightly between the two but the row
grammar is identical.

Each physical part is a component header row followed by 1-3 requirement
rows (one per applicable time-basis/task, e.g. a calendar-day overhaul, a
cycle-based overhaul, AND a cycle-based discard on the same part)::

    LEVEL CONFIG SLOT PART NUMBER SERIAL NUMBER DESCRIPTION POSITION INSTALL DATE HOURS CYCLES
    1 32-11-01-01-001-LH 161T0000-807 T11759 LH MAIN LANDING GEAR INSTALLAT MLG-LH 02/04/2018 81340.55 17023
    INITIAL TIME COMPLETED
    TIME STD SERVICE DESCRIPTION LIFE LIMIT TIME RUN EXPIRE DATE TASK
    INTERVAL REMAINING ON DATE
    Cycles LH_MAIN_LANDING_GEAR_INSTALLAT-OVERHAUL - 12500 445 12055 10/12/2039 21/02/2018 T00DFFDR
    Cycles LH_MAIN_LANDING_GEAR_INSTALLAT-DISCARD - 50000 7947 42053 26/10/2091 07/11/2007 T000E8W7

Unlike AMOS's one-sub-row-per-component "LIFE LIMIT" line, this format can
carry several independent requirement rows per part, so each requirement is
emitted as its own record (component fields copied onto every one) rather
than folded into a single row per part -- collapsing them would mean
silently dropping whichever requirement lost the merge.

Component-row anchor: a leading integer LEVEL, then a run of fixed-position
identity fields, then a `DD/MM/YYYY` INSTALL DATE. PR-MAP's schema inserts a
COMP_TSN/COMP_CSN pair between POSITION and INSTALL DATE that CC-CZU's
doesn't; detected by checking whether the two tokens immediately before the
date are numeric. Cells the source prints as "NO DATA" are collapsed to a
single token before splitting so they can't be mistaken for two columns.

Requirement-row anchor works from the right, not the left, because
SERVICE_DESCRIPTION's own shape varies too much to anchor on (space-separated
in some rows, underscore-joined in others -- e.g. "RH M.L.G. LEG &
DRESSINGS-(FIN : MLG-RH)..." vs "RH_MAIN_LANDING_GEAR_COMPLETE-OVERHAUL").
After the line starts with a known time-basis ("Cycles" / "Calendar Day"),
the reliable part is the tail: 2 dates (expire/completed-on) then 1-2 task
codes (DISCARD rows only ever carry one -- there's no "next" task once a
part is discarded), and immediately before the dates, 3 numbers
(limit/time-run/remaining). Whatever sits between those numbers and
SERVICE_DESCRIPTION is LIFE_LIMIT_INTERVAL -- printed as a literal "-" on
434 of 435 known rows, but real files do carry a populated value there at
least once (confirmed on CC-CZU p.20, "...ASSY-OVERHAUL 16000 16000 445
15555..."), so it's captured as data rather than assumed to always be "-".
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.llp_variants._base import merged_rules

NAME = "Landing Gear LLP Report"
SIGNATURES = [
    "LANDING GEAR LIFE LIMIT PARTS REPORT",
]

CANONICAL_COLUMNS = [
    "LEVEL",
    "CONFIG_SLOT",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
    "POSITION",
    "COMP_TSN",
    "COMP_CSN",
    "INSTALL_DATE",
    "COMP_HOURS",
    "COMP_CYCLES",
    "TIME_BASIS",
    "REQUIREMENT",
    "SERVICE_DESCRIPTION",
    "LIFE_LIMIT_INTERVAL",
    "LIMIT",
    "TIME_RUN",
    "REMAINING",
    "EXPIRE_DATE",
    "COMPLETED_ON_DATE",
    "TASK_CODE",
    "NEXT_TASK_CODE",
    # File-level aircraft metadata -- same on every row
    "AIRCRAFT_REG",
    "FLEET_MODEL",
    "MSN",
    "TOTAL_HOURS",
    "TOTAL_CYCLES",
]

_CYCLE_RULE = {"pattern": r"^\d+$", "int_range": (0, 55000),
               "int_range_review": (0, 30000)}
_DATE_RULE = {"pattern": r"^\d{2}/\d{2}/\d{4}$"}
_COMP_NUM_RULE = {"pattern": r"^(NO DATA|[\d.,]+)$"}
_OVERRIDES = {
    "LEVEL":        {"pattern": r"^\d+$"},
    "CONFIG_SLOT":  {"pattern": r"^[A-Z0-9\-]+$", "uppercase": True},
    "POSITION":     {"pattern": r"^[A-Z0-9\-]+$", "uppercase": True},
    "COMP_TSN":     _COMP_NUM_RULE,
    "COMP_CSN":     _COMP_NUM_RULE,
    "COMP_HOURS":   _COMP_NUM_RULE,
    "COMP_CYCLES":  _COMP_NUM_RULE,
    "INSTALL_DATE": _DATE_RULE,
    "EXPIRE_DATE":  _DATE_RULE,
    "COMPLETED_ON_DATE": _DATE_RULE,
    "LIFE_LIMIT_INTERVAL": {"pattern": r"^(-|[\d.,]+)$"},
    "LIMIT":        _CYCLE_RULE,
    "TIME_RUN":     _CYCLE_RULE,
    "REMAINING":    _CYCLE_RULE,
    "TASK_CODE":      {"pattern": r"^T[A-Z0-9]+$", "uppercase": True, "allow_empty": True},
    "NEXT_TASK_CODE": {"pattern": r"^T[A-Z0-9]+$", "uppercase": True, "allow_empty": True},
    "AIRCRAFT_REG": {"pattern": r"^[A-Z0-9\-]+$", "uppercase": True},
}
RULES = merged_rules(_OVERRIDES)

_LEVEL_RE = re.compile(r"^\d+$")
_DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")
_NUM_RE = re.compile(r"^[\d.,]+$")
_TIME_BASES = ("Calendar Day", "Cycles")
_REQUIREMENT_RE = re.compile(r"(OVERHAUL|DISCARD)")

_AIRCRAFT_RE = re.compile(r"^AIRCRAFT\s+(\S+)\s+DATE OF MANUFACTURE")
_FLEET_RE = re.compile(r"^(?:FLEET|ASSEMBLY)\s+(\S+)")
_MSN_RE = re.compile(r"\bMSN\s+(\d+)")
_SERIAL_NO_RE = re.compile(r"AIRCRAFT SERIAL N[ºo°]\s+(\d+)")
_TOTAL_HOURS_RE = re.compile(r"TOTAL (?:HOURS|FH)\s+([\d,]+)")
_TOTAL_CYCLES_RE = re.compile(r"TOTAL (?:CYCLES|FC)\s+([\d,]+)")

_HEADER_FRAGMENTS = (
    "LANDING GEAR LIFE LIMIT PARTS REPORT",
    "LEVEL CONFIG SLOT",
    "INITIAL",
    "COMPLETED",
    "TIME STD SERVICE",
    "INTERVAL REMAINING",
    "INTERVAL ON DATE",
    "AIRCRAFT OWNER",
    "AIRCRAFT SERIAL",
    "Página",
    " Page ",
)


def _is_skip_line(line: str) -> bool:
    return any(frag in line for frag in _HEADER_FRAGMENTS)


def _parse_meta(text: str) -> dict:
    meta: dict[str, str] = {}
    for line in text.splitlines()[:6]:
        m = _AIRCRAFT_RE.search(line)
        if m:
            meta.setdefault("AIRCRAFT_REG", m.group(1))
        m = _FLEET_RE.search(line)
        if m:
            meta.setdefault("FLEET_MODEL", m.group(1))
        m = _MSN_RE.search(line) or _SERIAL_NO_RE.search(line)
        if m:
            meta.setdefault("MSN", m.group(1))
        m = _TOTAL_HOURS_RE.search(line)
        if m:
            meta.setdefault("TOTAL_HOURS", m.group(1))
        m = _TOTAL_CYCLES_RE.search(line)
        if m:
            meta.setdefault("TOTAL_CYCLES", m.group(1))
    return meta


def _parse_component_row(line: str) -> dict | None:
    toks = line.replace("NO DATA", "NO_DATA").split()
    if len(toks) < 9 or not _LEVEL_RE.match(toks[0]):
        return None
    date_idx = next((i for i in range(4, len(toks)) if _DATE_RE.match(toks[i])), None)
    if date_idx is None or date_idx + 2 >= len(toks):
        return None

    comp_tsn = comp_csn = ""
    pos_idx = date_idx - 1
    if (date_idx - 2 > 3 and _NUM_RE.match(toks[date_idx - 1])
            and _NUM_RE.match(toks[date_idx - 2])):
        comp_tsn, comp_csn = toks[date_idx - 2], toks[date_idx - 1]
        pos_idx = date_idx - 3
    if pos_idx <= 3:
        return None

    rec = {c: "" for c in CANONICAL_COLUMNS}
    rec["LEVEL"] = toks[0]
    rec["CONFIG_SLOT"] = toks[1]
    rec["PART_NUMBER"] = toks[2]
    rec["SERIAL_NUMBER"] = toks[3]
    rec["DESCRIPTION"] = " ".join(toks[4:pos_idx])
    rec["POSITION"] = toks[pos_idx]
    rec["COMP_TSN"] = comp_tsn
    rec["COMP_CSN"] = comp_csn
    rec["INSTALL_DATE"] = toks[date_idx]
    rec["COMP_HOURS"] = toks[date_idx + 1].replace("NO_DATA", "NO DATA")
    rec["COMP_CYCLES"] = toks[date_idx + 2].replace("NO_DATA", "NO DATA")
    return rec


def _parse_requirement_row(line: str) -> dict | None:
    basis = next((b for b in _TIME_BASES if line.startswith(b + " ")), None)
    if basis is None:
        return None
    toks = line[len(basis):].split()

    date_idx = next((i for i in range(len(toks) - 1)
                      if _DATE_RE.match(toks[i]) and _DATE_RE.match(toks[i + 1])), None)
    if date_idx is None:
        return None
    expire_date, on_date = toks[date_idx], toks[date_idx + 1]
    tasks = toks[date_idx + 2:]

    pre = toks[:date_idx]
    if len(pre) < 4 or not all(_NUM_RE.match(t) for t in pre[-3:]):
        return None
    limit, time_run, remaining = pre[-3:]

    pre = pre[:-3]
    life_limit_interval = ""
    if pre and (pre[-1] == "-" or _NUM_RE.match(pre[-1])):
        life_limit_interval = pre[-1]
        pre = pre[:-1]
    service_desc = " ".join(pre)
    if not service_desc:
        return None
    m = _REQUIREMENT_RE.search(service_desc)

    # Partial dict, not a full CANONICAL_COLUMNS template -- this gets merged
    # onto the parent component record with dict.update(), and a full
    # template here would clobber every component field back to "".
    return {
        "TIME_BASIS": basis,
        "SERVICE_DESCRIPTION": service_desc,
        "REQUIREMENT": m.group(1) if m else "",
        "LIFE_LIMIT_INTERVAL": life_limit_interval,
        "LIMIT": limit,
        "TIME_RUN": time_run,
        "REMAINING": remaining,
        "EXPIRE_DATE": expire_date,
        "COMPLETED_ON_DATE": on_date,
        "TASK_CODE": tasks[0] if tasks else "",
        "NEXT_TASK_CODE": tasks[1] if len(tasks) > 1 else "",
    }


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        full_text = "\n".join((p.extract_text() or "") for p in pdf.pages)
        meta = _parse_meta(full_text)
        current: dict | None = None
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            for raw in text.splitlines():
                line = raw.strip()
                if not line or _is_skip_line(line):
                    continue
                comp = _parse_component_row(line)
                if comp is not None:
                    current = comp
                    continue
                req = _parse_requirement_row(line)
                if req is not None and current is not None:
                    rec = dict(current)
                    rec.update(req)
                    rec["_page"] = page_num
                    for k, v in meta.items():
                        rec[k] = v
                    records.append(rec)
    return records
