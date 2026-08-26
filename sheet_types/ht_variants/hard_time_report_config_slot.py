"""HARD TIME REPORT — CONFIG SLOT layout, from the same South American MIS
tool family that also produces `sheet_types/occm_variants/config_slot_occm.py`
(OCCM side) and `sheet_types/llp_variants/landing_gear_llp_report.py` (LLP
side, landing-gear-specific). This module is the general HT-side sibling:
every hard-time-tracked component on the airframe, not just landing gear.

Header, values genericized below but the shape is real::

    HARD TIME REPORT
    AIRCRAFT <tail> DATE OF MANUFACTURE <date> DATE ENTERED SERVICES <date>
    FLEET <type> TOTAL HOURS <n> TOTAL CYCLES <n>
    AIRCRAFT SERIAL N° <msn> Dt.MFL <date>
    AIRCRAFT OWNER <operator>
    LEVEL CONFIG SLOT PART NUMBER SERIAL NUMBER DESCRIPTION POSITION INSTALL DATE HOURS CYCLES
    1 21-51-00-00-001A XX00000-0 1234 SOME COMPONENT DESCRIPTION LH 01/01/2020 0,00 NO DATA
    INITIAL TIME COMPLETED ON
    TIME STD SERVICE DESCRIPTION INTERVAL INTERVAL TIME RUN REMAINING EXPIRE DATE DATE TASK
    Calendar MonthSOME-TASK-DESCRIPTION - 36 10,60 25,40 01/01/2023 01/01/2020 T00XXXXX
    Flying Hours SOME-TASK-DESCRIPTION - 12000 2899,23 9100,77 01/07/2023 01/01/2020 T00XXXXX

Each physical component is a repeating 4-line block:
  1. the column-header line ("LEVEL CONFIG SLOT PART NUMBER ...") — printed
     before *every* component, not once per page; skipped.
  2. the component data line — LEVEL, CONFIG_SLOT (a dash-segmented
     ATA-derived code, e.g. `21-51-00-00-001A`; some landing-gear-family
     rows append a side/gear suffix segment instead, e.g.
     `32-11-00-00-001-LH` or `32-21-00-00-002-NLG`), PART_NUMBER,
     SERIAL_NUMBER, DESCRIPTION, POSITION, INSTALL_DATE, HOURS, CYCLES.
  3. a second header line ("INITIAL TIME COMPLETED ON" / "TIME STD SERVICE
     DESCRIPTION INTERVAL ...") — skipped.
  4. one or more TASK sub-rows, each starting with a time-basis phrase
     ("Calendar Month", "Flying Hours", "Calendar Year", ... — glued
     directly onto the service description with no separating space in the
     source text) followed by the service description, interval, time run,
     remaining, expire date, completed-on date, and a task code. A single
     component commonly carries 2+ of these (one per time-basis it's
     tracked against).

Row grain: one row per component (matches this project's convention for
similarly-shaped trailing blocks — see `mm510.py`, `tap.py`,
`georgian_airways_ht_components_status.py`). The TASK sub-rows aren't
reliably splittable into fixed sub-columns from whitespace tokens alone
(the time-basis phrase is glued onto the following word with no space,
and the service-description vocabulary is open-ended), so they're kept
verbatim as one `STATUS_TRAIL` string per component, same call TAP HT and
Georgian Airways HT make for their own trailing columns.

Component-row anchor: a leading integer LEVEL, then a CONFIG_SLOT-shaped
token. PART_NUMBER is the token right after CONFIG_SLOT. SERIAL_NUMBER
starts at the next token; a source quirk in this format's PDF conversion
occasionally splits one serial number across 2-3 whitespace-separated
pure-digit tokens (e.g. a single serial rendered as `06 36 2489`) — those
get re-joined onto SERIAL_NUMBER by absorbing any further tokens that are
still pure digits, since a real DESCRIPTION always contains a token with a
letter. POSITION is the token immediately before INSTALL_DATE
(`DD/MM/YYYY`); everything between SERIAL_NUMBER and POSITION is
DESCRIPTION. HOURS/CYCLES follow the date and are each either a numeric
token or the two-token literal "NO DATA".
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.ht_variants._base import merged_rules

NAME = "Hard Time Report CONFIG SLOT"
SIGNATURES = [
    "HARD TIME REPORT",
    "LEVEL CONFIG SLOT PART NUMBER SERIAL NUMBER DESCRIPTION POSITION INSTALL DATE HOURS CYCLES",
]

CANONICAL_COLUMNS = [
    "LEVEL",
    "CONFIG_SLOT",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
    "POSITION",
    "INSTALL_DATE",
    "HOURS",
    "CYCLES",
    "STATUS_TRAIL",
]

_OVERRIDES = {
    "LEVEL":        {"pattern": r"^[1-9]\d?$"},
    "CONFIG_SLOT":  {"pattern": r"^\d{2}(?:-[A-Z0-9]{1,4}){2,5}$"},
    # This format occasionally renders one serial number as several
    # whitespace-separated pure-digit tokens (see module docstring) --
    # allow embedded spaces rather than flagging every such row.
    "SERIAL_NUMBER": {"pattern": r"^[A-Z0-9][A-Z0-9\-/ ]*[A-Z0-9]$"},
    "POSITION":     {"pattern": r"^[A-Z0-9/\-]{1,20}$", "uppercase": True,
                     "allow_empty": True},
    "INSTALL_DATE": {"pattern": r"^\d{2}/\d{2}/\d{4}$"},
    "HOURS":        {"pattern": r"^(NO DATA|[\d,]+)$"},
    "CYCLES":       {"pattern": r"^(NO DATA|[\d,]+)$"},
    "STATUS_TRAIL": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_LEVEL_RE = re.compile(r"^[1-9]\d?$")
_CONFIG_SLOT_RE = re.compile(r"^\d{2}(?:-[A-Z0-9]{1,4}){2,5}$")
_DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")
_PURE_DIGIT_RE = re.compile(r"^\d+$")
_FOOTER_RE = re.compile(r"^\d{2}/\d{2}/\d{4}\s+Page\s+\d+\s+of\s+\d+$", re.I)
_AIRCRAFT_HEADER_RE = re.compile(r"^AIRCRAFT\s+\S+\s+DATE OF MANUFACTURE\b")
_FLEET_HEADER_RE = re.compile(r"^FLEET\s+\S+\s+TOTAL HOURS\b")
_SKIP_PREFIXES = (
    "LEVEL CONFIG SLOT",
    "INITIAL TIME COMPLETED",
    "TIME STD SERVICE",
    "HARD TIME REPORT",
    "AIRCRAFT SERIAL",
    "AIRCRAFT OWNER",
)


def _is_skip_line(line: str) -> bool:
    if line.startswith(_SKIP_PREFIXES):
        return True
    if _FOOTER_RE.match(line):
        return True
    if _AIRCRAFT_HEADER_RE.match(line):
        return True
    if _FLEET_HEADER_RE.match(line):
        return True
    return False


def _parse_component_line(line: str) -> dict | None:
    toks = line.split()
    if len(toks) < 8:
        return None
    if not _LEVEL_RE.match(toks[0]):
        return None
    if not _CONFIG_SLOT_RE.match(toks[1]):
        return None
    part_number = toks[2]

    idx = 3
    if idx >= len(toks):
        return None
    sn_tokens = [toks[idx]]
    idx += 1
    while idx < len(toks) and _PURE_DIGIT_RE.match(toks[idx]):
        sn_tokens.append(toks[idx])
        idx += 1
    serial_number = " ".join(sn_tokens)

    date_idx = next((i for i in range(idx, len(toks)) if _DATE_RE.match(toks[i])), None)
    if date_idx is None or date_idx <= idx:
        return None
    position = toks[date_idx - 1]
    description = " ".join(toks[idx:date_idx - 1])

    tail = toks[date_idx + 1:]
    if not tail:
        return None
    if len(tail) >= 2 and tail[0] == "NO" and tail[1] == "DATA":
        hours = "NO DATA"
        tail = tail[2:]
    else:
        hours = tail[0]
        tail = tail[1:]
    if len(tail) >= 2 and tail[0] == "NO" and tail[1] == "DATA":
        cycles = "NO DATA"
        tail = tail[2:]
    elif tail:
        cycles = tail[0]
        tail = tail[1:]
    else:
        cycles = ""
    if tail:
        # Leftover tokens mean this wasn't actually a well-formed data
        # line (false positive on the LEVEL/CONFIG_SLOT anchor) -- reject
        # rather than silently truncate.
        return None

    return {
        "LEVEL": toks[0],
        "CONFIG_SLOT": toks[1],
        "PART_NUMBER": part_number,
        "SERIAL_NUMBER": serial_number,
        "DESCRIPTION": description,
        "POSITION": position,
        "INSTALL_DATE": toks[date_idx],
        "HOURS": hours,
        "CYCLES": cycles,
    }


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if len(text) < 80:
                continue
            current: dict | None = None
            status_lines: list[str] = []

            def _flush():
                if current is not None:
                    rec = dict(current)
                    rec["STATUS_TRAIL"] = " | ".join(status_lines)
                    rec["_page"] = page_num
                    records.append(rec)

            for raw in text.splitlines():
                line = raw.strip()
                if not line or _is_skip_line(line):
                    continue
                comp = _parse_component_line(line)
                if comp is not None:
                    _flush()
                    current = comp
                    status_lines = []
                    continue
                # Not a component line -- a TASK sub-row (or an unrecognized
                # continuation) belonging to the current component.
                if current is not None:
                    status_lines.append(line)
            _flush()
    return records
