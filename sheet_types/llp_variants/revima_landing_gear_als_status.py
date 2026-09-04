"""REVIMA landing-gear ALS component-status sheet.

Source format: a landing-gear overhaul shop's Airworthiness Limitations
Section (ALS) part-tracking table, produced on installation/removal of a
main (or nose) landing gear assembly. Header block (genericized below --
the real sample carries one specific tail/MSN/work-order, none of which
belong in this docstring):

    AIRBUS A330 - A340
    ALS Part 1 29-Jul-10 (R05) & Part 4 15-Dec-09 (R02)
    Hrs & Ldgs Hrs & Ldgs Hrs & Ldgs
    Performed On Performed On Performed On A330-200 WV02x
    A330-243 A330-243 A3XX-XXX
    MSN 334 MSN 340 MSN XXX
    Main Landing Gear A330 GROWTH A330 GROWTH A340 BASIC A330 GROWTH
    P/N S/N Designation A330-200 A330-200 A340-200 REMAINING
    Bare WV02x WV02x REQUIRED
    A330-200 WV02x
    LH MLG for <tail>, Msn <msn> From <date> <date> jj/mm/aaaa
    To <date> <date> jj/mm/aaaa
    Hrs Ldgs Hrs Ldgs Hrs Ldgs Hrs Ldgs
    DATE :
    <acft TSN> <acft CSN> 0 0 0 0 0 0
    10 1900 201272649 SER10328/99 Wheel axle 0 0 43611 10965 0 0 72489 19035
    ...
    REVIMA WO : <wo number> LH MLG

Each data row: a two-token zone/item CODE (space-separated numeric groups,
e.g. "10 1900", "215 8500" -- ATA-adjacent but not a strict 2-digit ATA),
PART_NUMBER (a 9-digit number on every row seen), an occasional footnote
marker token like "(1)" right after PART_NUMBER (dropped -- it refers to a
document footnote, not part data), SERIAL_NUMBER, then DESCRIPTION words,
followed by a trailing block of exactly 8 numeric/"NC" tokens: 3 parallel
Hrs/Ldgs pairs (one per tracking basis shown in the header -- e.g. "A330
GROWTH" x2 and "A340 BASIC" for an MLG shared across sub-models) plus a
final REMAINING-Hrs/REMAINING-Ldgs pair. "0 0" is a real value (not
missing); "NC" (seen only in the last two trailing slots, standing in for
a value that isn't tracked/controlled on that basis) is also a real
sentinel, not a parse failure.

Per this project's established convention for similarly dense trailing
blocks (see `sheet_types/ht_variants/hard_time_report_config_slot.py` and
`sheet_types/ht_variants/air_france_ccinv_aircraft_inventory.py`), the
8-value trailing block is kept as one verbatim STATUS_TRAIL string rather
than forced into 8 fixed sub-columns -- this is a singleton-cluster format
(one known real file) and doesn't warrant that investment.

A one-line header line just above the DATE line ("<TSN> <CSN> 0 0 0 0 0 0")
matches the same 8-trailing-numeric-token shape but carries no leading
CODE/PART_NUMBER/SERIAL_NUMBER/DESCRIPTION fields at all -- it's the
aircraft's own TSN/CSN as of the report date, not a component row, and is
excluded by requiring at least PART_NUMBER + SERIAL_NUMBER + one
DESCRIPTION word between the CODE and the trailing block.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.llp_variants._base import merged_rules

NAME = "REVIMA Landing Gear ALS Status"
SIGNATURES = [
    "ALS Part 1",
    "Hrs & Ldgs",
]

CANONICAL_COLUMNS = [
    "CODE",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
    "STATUS_TRAIL",
    "GEAR_POSITION",
    "AIRCRAFT_REG",
    "MSN",
    "AIRCRAFT_TYPE",
    "WORK_ORDER",
]

_OVERRIDES = {
    "CODE":           {"pattern": r"^\d{2,3} \d{1,4}$"},
    "PART_NUMBER":    {"pattern": r"^\d{6,10}$"},
    "STATUS_TRAIL":   {"allow_empty": True},
    "GEAR_POSITION":  {"pattern": r"^[A-Z0-9 ]{2,12}$", "uppercase": True,
                        "allow_empty": True},
    "AIRCRAFT_REG":   {"pattern": r"^[A-Z0-9\-]+$", "uppercase": True,
                        "allow_empty": True},
    "MSN":            {"pattern": r"^[A-Z0-9]+$", "uppercase": True,
                        "allow_empty": True},
    "AIRCRAFT_TYPE":  {"uppercase": True, "allow_empty": True},
    "WORK_ORDER":      {"pattern": r"^[A-Z0-9]+$", "uppercase": True,
                        "allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_TRAIL_TOKEN_RE = re.compile(r"^(?:NC|\d+)$")
_FOOTNOTE_RE = re.compile(r"^\(\d+\)$")
_GEAR_META_RE = re.compile(
    r"^(?P<pos>.+?)\s+for\s+(?P<reg>[^,]+),\s*Msn\s+(?P<msn>\S+)\s+From\b",
    re.I,
)
_WO_RE = re.compile(r"REVIMA WO\s*:\s*(\S+)", re.I)


def _parse_row(line: str) -> dict | None:
    toks = line.split()
    if len(toks) < 6:
        return None
    if not (toks[0].isdigit() and toks[1].isdigit()):
        return None

    trail: list[str] = []
    i = len(toks) - 1
    while i >= 0 and _TRAIL_TOKEN_RE.match(toks[i]):
        trail.insert(0, toks[i])
        i -= 1
    if len(trail) != 8:
        return None

    leftover = toks[2:i + 1]
    if len(leftover) < 3:
        # Not enough tokens for PART_NUMBER + SERIAL_NUMBER + >=1
        # DESCRIPTION word -- e.g. the aircraft TSN/CSN summary line, which
        # is all-numeric and gets fully absorbed by the trailing-block scan.
        return None

    part_number = leftover[0]
    rest = leftover[1:]
    if rest and _FOOTNOTE_RE.match(rest[0]):
        rest = rest[1:]
    if len(rest) < 2:
        return None
    serial_number = rest[0]
    description = " ".join(rest[1:])

    return {
        "CODE": f"{toks[0]} {toks[1]}",
        "PART_NUMBER": part_number,
        "SERIAL_NUMBER": serial_number,
        "DESCRIPTION": description,
        "STATUS_TRAIL": " ".join(trail),
    }


def _parse_page_meta(text: str) -> dict:
    meta: dict[str, str] = {}
    lines = text.splitlines()
    if lines:
        first = lines[0].strip()
        if first and not first[0].isdigit():
            meta["AIRCRAFT_TYPE"] = first
    for line in lines:
        m = _GEAR_META_RE.match(line.strip())
        if m:
            meta["GEAR_POSITION"] = m.group("pos").strip()
            meta["AIRCRAFT_REG"] = m.group("reg").strip()
            meta["MSN"] = m.group("msn").strip()
        m = _WO_RE.search(line)
        if m:
            meta["WORK_ORDER"] = m.group(1)
    return meta


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if len(text) < 50:
                continue
            meta = _parse_page_meta(text)
            for raw in text.splitlines():
                rec = _parse_row(raw.strip())
                if rec is None:
                    continue
                for col in CANONICAL_COLUMNS:
                    rec.setdefault(col, meta.get(col, ""))
                rec["_page"] = page_num
                records.append(rec)
    return records
