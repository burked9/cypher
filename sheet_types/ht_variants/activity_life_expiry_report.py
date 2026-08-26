"""ACTIVITY LIFE EXPIRY REPORT — OASES-based HT/LLP export. Two header
sub-layouts confirmed for the same underlying report, handled by one
shared parser (the per-component block grammar is identical; only the
column-header wording and a run-date locale string differ):

Sub-layout A (English column headers, dates only)::

    Activity Life Expiry Report Page : 1 of 77
    Aircraft Reg Last Flight Date Airframe Hours Airframe Landings Since Check Hours Since Check Landings
    <tail> <date> <hours> <landings> <hours> <landings>
    ATA/Pos/Zone/Desc Part/Serial Activity Description Card/DRN Class Life Last Compl. Limit/Interval Remaining Next Due Overdue
    21310500/316/2.71 7012-18088-03 213100-05-1 FCT HT Date 09Sep2015 07Sep2021
    VALVE SAFETY 10115854 CMR - PRESSURE CONTROL AND Fleet Days (Calendar) 1967 2190 775
    MONITORING Hours 17274:01 24000:00 17681:59 77399:25
    Landings 3132

Sub-layout B (operator-branded header, a mixed-locale run-date string, and
a slightly different mid-line composition -- the token between PART_NUMBER
and the task-type abbreviation is free-text "Requirement/Remarks", not a
Card/DRN code as in sub-layout A)::

    <operator-branded prefix> Activity Life Expiry Report Run Date : <locale timestamp> Page : 1 of 16
    (Oases Option : TF30)
    Aircraft = <tail> Last Flight Date = 19Aug2015 Airframe Hours = 31448:29 Airframe Landings = 17269 Since Check Hours = 31448:29 Since Check Landings = 17269
    ATA/Pos/Zone/Description Part/Serial Requirement/Remarks DRN Class Life Last Compl. Frequency Next Due Remaining Overdue
    21265300 / OUT / 1.27 VFT300B00 VENT SKIN AIR OUTLET VALVE OVH HT Date 02Aug2013 31Jul2023
    SKIN AIR OULET VALVE 03303 REMOVE FOR OVERHAUL Fleet Days (Calendar) 0 3650 2897
    Hours 0:00 18000:00 45891:14 14442:45
    Landings 0

Row grain: one row per component-task block. Each block is a repeating
run of 3-5 physical text lines:

  1. Anchor/code line -- ATA/POS/ZONE (slash-separated; the POS segment
     itself occasionally contains a literal "/", e.g. "L/H", so it can't
     be split on a fixed slash count), PART_NUMBER, then a free-text
     middle span (a Card/DRN code in sub-layout A, or the start of the
     Requirement/Remarks text in sub-layout B -- semantically different
     between the two sub-layouts, so kept as raw text rather than forced
     into one typed column), the task-type abbreviation (2-6 chars,
     e.g. FCT/RST/OVH/DSF/CLN/OH1 -- consistent in meaning across both
     sub-layouts and reliably anchors the line), an optional life-class
     token ("HT" or "LL" -- occasionally absent even on an otherwise
     normal row), the literal "Date", then 0-3 date tokens (last
     completed / next due, sometimes with a duplicated third date token
     observed in a handful of rows).
  2. Description/remarks continuation line(s) (1-2 lines) ending in the
     metric-basis label ("Fleet Days (Calendar)", "Part Days (Calendar)",
     "Serial Days (Calendar)", "Fleet Days (Fitted)", ...) plus 0-4
     numeric values for that basis.
  3. An "Hours" line with 0-4 numeric values.
  4. A "Landings" line with 0-1 numeric values (occasionally "?" where
     the source report has no data).

The Limit/Interval/Remaining/Next-Due/Overdue numeric breakdown is
column-ragged in both sub-layouts (confirmed: different metric-basis rows
carry different counts of trailing numbers, and the column that a given
number lands in isn't determinable from whitespace position alone without
per-page x/y coordinate work that this format's real-world value doesn't
justify). Per this project's established convention for this kind of
ragged trailing block (see `hard_time_report_config_slot.py`,
`time_controlled_components_status.py`), it's kept verbatim as one
`STATUS_TRAIL` catch-all string rather than force-split into fixed
sub-columns. STATUS_TRAIL also carries the anchor line's own free-text
middle span (Card/DRN or Requirement/Remarks -- see above), since that
field's meaning isn't consistent across the two sub-layouts.

Row anchor: a line matching the ATA/POS/ZONE + PART_NUMBER + ... + "Date"
shape below. Confirmed to match every genuine component line and zero
false positives across every page of all sample files used to build this
parser.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.ht_variants._base import merged_rules

NAME = "Activity Life Expiry Report"
SIGNATURES = [
    "Activity Life Expiry Report",
]

CANONICAL_COLUMNS = [
    "ATA_POS_ZONE",
    "PART_NUMBER",
    "TASK_TYPE",
    "LIFE_CLASS",
    "LAST_COMPL_DATE",
    "NEXT_DUE_DATE",
    "STATUS_TRAIL",
]

_OVERRIDES = {
    "ATA_POS_ZONE": {"pattern": r"^\d{6,8}\s*/\s*\S.*\S\s*/\s*[\d.]+$",
                      "uppercase": True},
    # This format's part numbers occasionally contain a forward slash
    # (e.g. "DK120/90"), unlike the global PART_NUMBER rule's plain
    # hyphen-only pattern.
    "PART_NUMBER": {"pattern": r"^[A-Z0-9](?:[A-Z0-9\-/]*[A-Z0-9])?$"},
    "TASK_TYPE": {"pattern": r"^[A-Z0-9]{2,6}$", "uppercase": True},
    "LIFE_CLASS": {"pattern": r"^(HT|LL)?$", "allow_empty": True},
    "LAST_COMPL_DATE": {"pattern": r"^\d{1,2}[A-Za-z]{3}\d{4}$", "allow_empty": True},
    "NEXT_DUE_DATE": {"pattern": r"^\d{1,2}[A-Za-z]{3}\d{4}$", "allow_empty": True},
    "STATUS_TRAIL": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_ANCHOR_RE = re.compile(
    r"^(?P<ata>\d{6,8})\s*/\s*(?P<pos>.+?)\s*/\s*(?P<zone>\d+\.\d+)\s+"
    r"(?P<part>\S+)\s+(?P<middle>.*?)\s+(?P<ttype>[A-Z0-9]{2,6})\s+"
    r"(?:(?P<lifecls>HT|LL)\s+)?Date"
    r"(?:\s+(?P<last>\d{1,2}[A-Za-z]{3}\d{4}))?"
    r"(?:\s+(?P<next>\d{1,2}[A-Za-z]{3}\d{4}))?"
    r"(?:\s+\d{1,2}[A-Za-z]{3}\d{4})?"  # occasional duplicated 3rd date token
    r"\s*$"
)
# Cheap pre-filter before the full anchor regex (which is somewhat costly
# to run per line): a real anchor line always starts with ATA digits then
# a slash.
_CANDIDATE_RE = re.compile(r"^\d{6,8}\s*/")

_SKIP_SUBSTRINGS = (
    "Activity Life Expiry Report",
    "Aircraft Reg",
    "Aircraft =",
    "ATA/Pos/Zone",
    "(Oases Option",
    "Created by",
    "Continued >>",
)


def _is_skip_line(line: str) -> bool:
    return any(s in line for s in _SKIP_SUBSTRINGS)


def _parse_anchor(line: str) -> dict | None:
    m = _ANCHOR_RE.match(line)
    if not m:
        return None
    return {
        "ATA_POS_ZONE": f"{m.group('ata')}/{m.group('pos')}/{m.group('zone')}",
        "PART_NUMBER": m.group("part"),
        "TASK_TYPE": m.group("ttype"),
        "LIFE_CLASS": m.group("lifecls") or "",
        "LAST_COMPL_DATE": m.group("last") or "",
        "NEXT_DUE_DATE": m.group("next") or "",
        "_middle": m.group("middle").strip(),
    }


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if not text.strip():
                continue

            current: dict | None = None
            trail: list[str] = []

            def _flush():
                if current is not None:
                    rec = {k: v for k, v in current.items() if k != "_middle"}
                    middle = current.get("_middle", "")
                    parts = ([middle] if middle else []) + trail
                    rec["STATUS_TRAIL"] = " | ".join(parts)
                    rec["_page"] = page_num
                    records.append(rec)

            for raw in text.splitlines():
                line = raw.strip()
                if not line or _is_skip_line(line):
                    continue
                if _CANDIDATE_RE.match(line):
                    anchor = _parse_anchor(line)
                    if anchor is not None:
                        _flush()
                        current = anchor
                        trail = []
                        continue
                if current is not None:
                    trail.append(line)
            _flush()
    return records
