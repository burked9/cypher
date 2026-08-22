"""Serialized Unit List - Hard Limits — a generic per-serialized-unit
hard-time tracker. Confirmed run against both a landing-gear assembly (ATA
32, PN 161T0000-191 SN T7468) and an APU (ATA 49, PN 49-60001-1, three
files/SNs G93/G91/G85) with byte-identical header and row grammar — it's a
report any serialized rotable can be queried through, not APU-specific.

Header (repeated per page):
    2020-11-25 16:30 PM
    Serialized Unit List - Hard Limits REQUESTOR:AC018195
    PAGE 1 of 5
    FLEET TYPE: B767-375ER A/C:685 A/C TOTAL HOURS: 130189:41 A/C TOTAL CYCLES: 25311
    PN: 161T0000-191 SN: T7468 PN TOTAL HOURS: 103342:19 PN TOTAL CYCLES: 18216

Each part occupies a literal "HCD" sentinel line followed by 3 data lines —
Hours / Cycles / Days limits tracked in parallel for the same part:

    HCD
    32- 10 MLG INNER CYLINDER ONLY 81205 DISCARD H Y 0 H 162842:46 H 0:00H 162842:46H 0 H
    015T1433-4 0696 50000 C 27681 C 22319 C 27681 C 47630 C
    0 D 2038 D 0 D 2038 D

Line 2 (H): ATA "32- 10" (chapter-dash-section, rejoined "32-10"), then
DESCRIPTION, POS ("ONLY"), MFR_PN (a short NHA/reference code — "81205",
"99193", "P9037" seen), CONTROL ("DISCARD"), then two one-char flags H/S
and E/C, then 5 hour-metrics suffixed "H". Line 3 (C) carries the real
PART_NUMBER/SERIAL_NUMBER of the removed unit plus the same 5 metrics in
cycles ("C"). Line 4 (D) carries only 4 metrics in calendar days ("D") — no
DUE_AT_DAYS; a countdown in days has no "due at X aircraft-cycles" analogue.

The 5 metrics are (positionally) LIMIT, SINCE, REMAIN, TOTAL, DUE_AT. This
is confirmed arithmetically on the one dimension populated in every sample
row (cycles): REMAIN_CYCLES == LIMIT_CYCLES - SINCE_CYCLES, and
DUE_AT_CYCLES == AC_TOTAL_CYCLES + REMAIN_CYCLES, both exactly or within
rounding. Rows with no limit on a given dimension print 0 (or "0:00" for
hours) straight through LIMIT/REMAIN/DUE_AT rather than a negative — every
sample row is cycle-limited only, so LIMIT_HRS/LIMIT_DAYS are 0 throughout.
TOTAL is a higher-precision echo of SINCE — plain integer everywhere except
this one slot, where APU files carry a fractional cycle count ("9803.86").

pdfplumber sometimes glues a value straight onto its unit letter with no
space ("0:00H", "162842:46H") and sometimes doesn't ("162842:46 H", "0 H"
in the same row) depending on how that particular string kerns — the
metrics regex matches the unit letter as a bare suffix so both forms parse
the same way.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.llp_variants._base import merged_rules

NAME = "Serialized Unit Hard Limits"
SIGNATURES = [
    "Serialized Unit List - Hard Limits",
    "PN TOTAL CYCLES",
]

CANONICAL_COLUMNS = [
    "ATA",
    "DESCRIPTION",
    "POS",
    "MFR_PN",
    "CONTROL",
    "HS_FLAG",
    "EC_FLAG",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "LIMIT_HRS", "SINCE_HRS", "REMAIN_HRS", "TOTAL_HRS", "DUE_AT_HRS",
    "LIMIT_CYCLES", "SINCE_CYCLES", "REMAIN_CYCLES", "TOTAL_CYCLES", "DUE_AT_CYCLES",
    "LIMIT_DAYS", "SINCE_DAYS", "REMAIN_DAYS", "TOTAL_DAYS",
    # Report header metadata -- same on every row of a given file
    "FLEET_TYPE", "AC_TAIL", "AC_TOTAL_HOURS", "AC_TOTAL_CYCLES",
    "REPORT_PN", "REPORT_SN", "REPORT_PN_TOTAL_HOURS", "REPORT_PN_TOTAL_CYCLES",
    "STATUS_DATE", "REQUESTOR",
]

# Hour fields print as "H:MM" (e.g. "162842:46"), not a thousands-grouped
# int, so int_range (which parses comma/dot/apostrophe thousands only) can't
# apply here -- shape-check only.
_HRS_RULE = {"pattern": r"^\d+(:\d{2})?$"}
_CYCLE_RULE = {"pattern": r"^[\d,]+$", "int_range": (0, 55000),
               "int_range_review": (0, 30000)}
# TOTAL_CYCLES (row) / REPORT_PN_TOTAL_CYCLES (header) are the one slot that
# carries a fractional cycle count on APU files ("9803.86") -- everywhere
# else cycles are whole, so this gets its own pattern rather than loosening
# _CYCLE_RULE for every column.
_FRAC_CYCLE_RULE = {"pattern": r"^\d+(\.\d{1,2})?$"}
_DAY_RULE = {"pattern": r"^\d+$", "int_range": (0, 20000)}
_PN_LIKE = {"pattern": r"^[A-Z0-9](?:[A-Z0-9\-]*[A-Z0-9])?$", "uppercase": True}

_OVERRIDES = {
    # int_range explicitly cancelled -- GLOBAL_RULES["ATA"] carries a bare
    # 2-digit int_range (20, 83) that merged_rules() would otherwise leave
    # in place alongside our combined "32-10" pattern, and _parse_thousands_int
    # can't parse the dash, so every row would flag ATA:not_a_number.
    "ATA":     {"pattern": r"^\d{2}-\d{2}$", "int_range": None},
    "MFR_PN":  {"pattern": r"^[A-Z0-9]+$", "uppercase": True},
    "CONTROL": {"pattern": r"^[A-Z]+$", "uppercase": True},
    "HS_FLAG": {"pattern": r"^[HS]$", "uppercase": True},
    "EC_FLAG": {"pattern": r"^[A-Z]$", "uppercase": True},
    "LIMIT_HRS": _HRS_RULE, "SINCE_HRS": _HRS_RULE,
    "REMAIN_HRS": _HRS_RULE, "TOTAL_HRS": _HRS_RULE, "DUE_AT_HRS": _HRS_RULE,
    "LIMIT_CYCLES": _CYCLE_RULE, "SINCE_CYCLES": _CYCLE_RULE,
    "REMAIN_CYCLES": _CYCLE_RULE, "DUE_AT_CYCLES": _CYCLE_RULE,
    "TOTAL_CYCLES": _FRAC_CYCLE_RULE,
    "LIMIT_DAYS": _DAY_RULE, "SINCE_DAYS": _DAY_RULE,
    "REMAIN_DAYS": _DAY_RULE, "TOTAL_DAYS": _DAY_RULE,
    "FLEET_TYPE": {"pattern": r"^[A-Z0-9\-]+$", "uppercase": True},
    "AC_TAIL":    {"pattern": r"^[A-Z0-9]+$", "uppercase": True},
    "AC_TOTAL_HOURS":  _HRS_RULE,
    "AC_TOTAL_CYCLES": _CYCLE_RULE,
    "REPORT_PN": _PN_LIKE,
    "REPORT_SN": {"pattern": r"^[A-Z0-9\-]+$", "uppercase": True},
    "REPORT_PN_TOTAL_HOURS":  _HRS_RULE,
    "REPORT_PN_TOTAL_CYCLES": _FRAC_CYCLE_RULE,
    "STATUS_DATE": {"pattern": r"^\d{4}-\d{2}-\d{2}$"},
    "REQUESTOR":   {"pattern": r"^[A-Z0-9]+$", "uppercase": True},
}
RULES = merged_rules(_OVERRIDES)


_ATA_PREFIX_RE = re.compile(r"^(\d{2})-\s*(\d{2})\s+(.+)$")
# desc is non-greedy so it grows only as far as needed for pos/mfr_pn/control
# to fall immediately before a bare H/S flag token -- avoids hardcoding the
# literal "ONLY" / "DISCARD" values, which aren't guaranteed to be the only
# ones a live system ever prints.
_H_ROW_RE = re.compile(
    r"^(?P<desc>.+?)\s+(?P<pos>\S+)\s+(?P<mfr_pn>\S+)\s+(?P<control>\S+)\s+"
    r"(?P<hs>[HS])\s+(?P<ec>\S+)\s+(?P<tail>.+)$"
)
_CSN_ROW_RE = re.compile(r"^(?P<pn>\S+)\s+(?P<sn>\S+)\s+(?P<tail>.+)$")

_HEADER_RE = re.compile(
    r"FLEET TYPE:\s*(?P<fleet>\S+)\s+A/C:(?P<tail>\S+)\s+"
    r"A/C TOTAL HOURS:\s*(?P<ac_hrs>\S+)\s+A/C TOTAL CYCLES:\s*(?P<ac_cyc>\S+)"
)
_PN_HEADER_RE = re.compile(
    r"PN:\s*(?P<pn>\S+)\s+SN:\s*(?P<sn>\S+)\s+"
    r"PN TOTAL HOURS:\s*(?P<pn_hrs>\S+)\s+PN TOTAL CYCLES:\s*(?P<pn_cyc>\S+)"
)
_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\s")
_REQUESTOR_RE = re.compile(r"REQUESTOR:(\S+)")


def _metrics(tail: str, unit: str) -> list[str]:
    """Pull every '<value><unit>' token out of a metrics tail, tolerating
    both glued ("0:00H") and spaced ("162842:46 H") forms."""
    return re.findall(rf"([0-9][0-9:.,']*)\s*{unit}\b", tail)


def _parse_meta(text: str) -> dict:
    meta: dict[str, str] = {}
    for line in text.splitlines():
        m = _HEADER_RE.search(line)
        if m and "FLEET_TYPE" not in meta:
            meta["FLEET_TYPE"] = m.group("fleet")
            meta["AC_TAIL"] = m.group("tail")
            meta["AC_TOTAL_HOURS"] = m.group("ac_hrs")
            meta["AC_TOTAL_CYCLES"] = m.group("ac_cyc")
        m = _PN_HEADER_RE.search(line)
        if m and "REPORT_PN" not in meta:
            meta["REPORT_PN"] = m.group("pn")
            meta["REPORT_SN"] = m.group("sn")
            meta["REPORT_PN_TOTAL_HOURS"] = m.group("pn_hrs")
            meta["REPORT_PN_TOTAL_CYCLES"] = m.group("pn_cyc")
        m = _DATE_RE.match(line)
        if m and "STATUS_DATE" not in meta:
            meta["STATUS_DATE"] = m.group(1)
        m = _REQUESTOR_RE.search(line)
        if m and "REQUESTOR" not in meta:
            meta["REQUESTOR"] = m.group(1)
    return meta


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    all_lines: list[tuple[int, str]] = []
    with pdfplumber.open(pdf_path) as pdf:
        full_text = "\n".join((p.extract_text() or "") for p in pdf.pages)
        meta = _parse_meta(full_text)
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            for raw in text.splitlines():
                s = raw.strip()
                if s:
                    all_lines.append((page_num, s))

    i, n = 0, len(all_lines)
    while i < n:
        _, line = all_lines[i]
        if line != "HCD" or i + 3 >= n:
            i += 1
            continue
        h_page, h_line = all_lines[i + 1]
        _, c_line = all_lines[i + 2]
        _, d_line = all_lines[i + 3]

        ata_m = _ATA_PREFIX_RE.match(h_line)
        row_m = _H_ROW_RE.match(ata_m.group(3)) if ata_m else None
        csn_m = _CSN_ROW_RE.match(c_line)
        if not (ata_m and row_m and csn_m):
            i += 1
            continue

        rec = {c: "" for c in CANONICAL_COLUMNS}
        rec["ATA"] = f"{ata_m.group(1)}-{ata_m.group(2)}"
        rec["DESCRIPTION"] = row_m.group("desc")
        rec["POS"] = row_m.group("pos")
        rec["MFR_PN"] = row_m.group("mfr_pn")
        rec["CONTROL"] = row_m.group("control")
        rec["HS_FLAG"] = row_m.group("hs")
        rec["EC_FLAG"] = row_m.group("ec")
        rec["PART_NUMBER"] = csn_m.group("pn")
        rec["SERIAL_NUMBER"] = csn_m.group("sn")
        for k, v in zip(("LIMIT_HRS", "SINCE_HRS", "REMAIN_HRS", "TOTAL_HRS", "DUE_AT_HRS"),
                        _metrics(row_m.group("tail"), "H")):
            rec[k] = v
        for k, v in zip(("LIMIT_CYCLES", "SINCE_CYCLES", "REMAIN_CYCLES", "TOTAL_CYCLES", "DUE_AT_CYCLES"),
                        _metrics(csn_m.group("tail"), "C")):
            rec[k] = v
        for k, v in zip(("LIMIT_DAYS", "SINCE_DAYS", "REMAIN_DAYS", "TOTAL_DAYS"),
                        _metrics(d_line, "D")):
            rec[k] = v
        for k, v in meta.items():
            rec[k] = v
        rec["_page"] = h_page
        records.append(rec)
        i += 4

    return records
