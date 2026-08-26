"""TIME CONTROLLED ITEMS REPORT — per-aircraft hard-time export from a
"CAMP Systems"-style MIS (the phrase "CAMP SYSTEMS" appears verbatim in
this format's page footer, hence the attribution; this is inherent to the
document template rather than a specific customer identifier). Distinct
from this project's `time_controlled_items_status.py` and
`time_controlled_components_status.py` -- similarly named, but a genuinely
different vendor/format with its own header phrase and layout, not a
shared parser.

Header, values genericized below but the shape is real::

    Time Controlled Items Report
    737-7AX S/N <serial> (<code>) (<tail>): 17694:33 HRS, 26180 AFL as of 05-Feb-2018
    Owner: <operator> Operator: <operator2>
    Report Date: 12-FEB-2018
    TASK NO TASK DESCRIPTION UNIT INTERVAL TIME SINCE ADJ WARR EXP COMPLIANCE NEXT DUE MAX TIME
    PART/SERIAL (ENG/APU) A/C LIMIT REMAINING
    CHAPTER 23 COMMUNICATIONS
    23-110-00-01 EMERGENCY LOCATOR TRANSMITTER BATTERY
    452-0133 MOS 60 26-MAY-2014 30-JUN-2018 M 138 d
    359815-009 HRS/MSC 13174:26
    DISCARD REF: AFL 20687

The document is organized into `CHAPTER <NN> <name>` section headers, each
containing one or more component blocks. Confirmed by walking every page
of the sample files with zero unclassified lines inside the table body:
every component is a clean 4-line block --

  1. `<TASK_NO> <DESCRIPTION>` -- task code shaped like `NN-NNN-NN-NN` or
     `NN-NN-NN`, sometimes with a trailing `(N.N...)` sub-index and/or a
     further `-N` suffix glued directly onto the sub-index (e.g.
     `32-050-01 (1.0)-1`), followed by free-text description.
  2. `<PART_NUMBER or literal "PN"> MOS ...` -- MOS = months time-basis,
     followed by a ragged tail of interval/compliance-date/next-due-date/
     remaining-days tokens whose shape varies row to row (some rows carry
     an explicit interval count or a `TSR:n` prefix before the date, some
     have only one date, some have a trailing `M <n> d`).
  3. `<SERIAL_NUMBER or literal "SN-UNKNOWN"> HRS/MSC ...` -- followed by a
     similarly ragged tail of time-since figures (`A/R`, `TSN:n n`, a bare
     accumulated value, or nothing at all).
  4. a trailing line starting with `DISCARD REF:`, `LIFE LIMIT REF:`, or
     plain `REF:`, followed by an `AFL <n>` reference and sometimes
     further numeric fields (max-time/remaining).

The MAX TIME/REMAINING-column numerics that sometimes trail the REF line
are not consistently present or consistently shaped across rows (compare
`LIFE LIMIT REF: AFL 75000 TSN:0 0 75000 48820` against a plain
`REF: AFL 26180` with nothing further) -- not reliably splittable into
fixed sub-columns, so lines 2-4 in full (including the leading PART_NUMBER
/SERIAL_NUMBER tokens already lifted out below) are preserved verbatim,
pipe-joined, as one `STATUS_TRAIL` catch-all per component. Same call this
project's other ragged-trailing-block HT variants make for their own
trailing data (see `hard_time_report_config_slot.py` and
`air_france_ccinv_aircraft_inventory.py`).

ATA is not printed per row -- only on the `CHAPTER <NN> <name>` section
header above each group of components -- so it is forward-filled from the
most recently seen CHAPTER line as the document is walked in order, the
same section-header-carries-ATA convention this project's other
CHAPTER-organized/section-organized HT and OCCM variants use (see
`shared.cleanup.forward_fill_ata` for the row-level version of this same
idea, applied generically at the router layer for variants where ATA can
still end up missing on a row for some other reason).

Row grain: one row per component block (this format's own repeating
TASK_NO-anchored unit), matching this project's established convention
for similarly-shaped repeating blocks.

PART_NUMBER/SERIAL_NUMBER placeholders: this format prints the literal
token `PN` in the PART_NUMBER position when no part number is known, and
`SN-UNKNOWN` in the SERIAL_NUMBER position when no serial is known (seen
on life-limited structural items tracked by TSN alone, e.g. landing-gear
fittings). Both placeholders are normalized to an empty PART_NUMBER/
SERIAL_NUMBER value here rather than kept as literal text, so an analyst
filtering on "has a real part/serial" doesn't have to know this format's
own placeholder vocabulary.

Every page repeats the same title/aircraft-info/owner/report-date/column-
header lines and the same legend/copyright footer line (the footer always
contains the phrase "CAMP SYSTEMS"); these are skipped outright rather
than folded into whatever component happens to still be open at the top/
bottom of a page. Verified across every sampled page that no component
block itself ever straddles a page break -- each page both starts and
ends on a block boundary (either a fresh CHAPTER/TASK_NO line at the top,
or a complete REF line at the bottom) -- but the parser still walks the
whole document as one continuous line stream (state carried across pages)
rather than resetting per page, as a safety net in case a future sample
doesn't hold to that.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.ht_variants._base import merged_rules

NAME = "Time Controlled Items Report"
SIGNATURES = [
    "Time Controlled Items Report",
]

CANONICAL_COLUMNS = [
    "ATA",
    "TASK_NO",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "STATUS_TRAIL",
]

_OVERRIDES = {
    "TASK_NO":       {"pattern": r"^\d{2}-[A-Z0-9]{2,4}-\d{2}(?:-\d{1,2})?"
                                  r"(?:\s\([\d.]+\))?(?:-\d{1,2})?$"},
    "DESCRIPTION":   {"uppercase": True, "allow_empty": True},
    "PART_NUMBER":   {"pattern": r"^[A-Z0-9][A-Z0-9\-\./]*$", "uppercase": True,
                       "allow_empty": True},
    "SERIAL_NUMBER": {"pattern": r"^[A-Z0-9][A-Z0-9\-\./]*$", "uppercase": True,
                       "allow_empty": True},
    "STATUS_TRAIL":  {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_CHAPTER_RE = re.compile(r"^CHAPTER\s+(\d{1,3})\s+(.*)$")
_TASK_RE = re.compile(
    r"^(?P<task>\d{2}-[A-Z0-9]{2,4}-\d{2}(?:-\d{1,2})?"
    r"(?:\s\([\d.]+\))?(?:-\d{1,2})?)"
    r"\s+(?P<desc>\S.*)$"
)
_MOS_RE = re.compile(r"\bMOS\b")

# Page title/aircraft-info/owner/report-date/column-header lines repeat on
# every page. Matched by prefix (case-insensitive) rather than tied to
# whatever component happens to be open at the time, since a still-open
# component from the bottom of the previous page would otherwise absorb
# the next page's header junk into its STATUS_TRAIL.
_SKIP_PREFIXES = (
    "TIME CONTROLLED ITEMS REPORT",
    "OWNER:",
    "REPORT DATE:",
    "TASK NO TASK DESCRIPTION",
    "PART/SERIAL",
    "?-INSUFFICIENT INFORMATION",
)
# The aircraft-info line ("737-7AX S/N <serial> (<code>) (<tail>): ...
# HRS, ... AFL as of ...") -- matched structurally (a hyphenated model
# code, then "S/N", then a digit) since the model code itself varies.
_ACFT_LINE_RE = re.compile(r"^\S+-\S+\s+S/N\s+\d")


def _is_skip_line(line: str) -> bool:
    up = line.upper()
    if up.startswith(_SKIP_PREFIXES):
        return True
    # The legend/copyright footer line always carries this phrase
    # (inherent to the MIS template, see module docstring).
    if "CAMP SYSTEMS" in up:
        return True
    if _ACFT_LINE_RE.match(line):
        return True
    return False


def _extract_pn_sn(block_lines: list[str]) -> tuple[str, str]:
    """Pull PART_NUMBER off the MOS line and SERIAL_NUMBER off the
    HRS/MSC line (each is that line's leading token), normalizing the
    format's own "PN" / "SN-UNKNOWN" placeholders to empty strings."""
    part_number = ""
    serial_number = ""
    for line in block_lines:
        toks = line.split()
        if not toks:
            continue
        if part_number == "" and _MOS_RE.search(line):
            part_number = "" if toks[0].upper() == "PN" else toks[0]
        if serial_number == "" and "HRS/MSC" in line:
            serial_number = "" if toks[0].upper() == "SN-UNKNOWN" else toks[0]
    return part_number, serial_number


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    current_ata = ""
    current: dict | None = None
    block_lines: list[str] = []

    def _flush():
        if current is not None:
            rec = dict(current)
            rec["PART_NUMBER"], rec["SERIAL_NUMBER"] = _extract_pn_sn(block_lines)
            rec["STATUS_TRAIL"] = " | ".join(block_lines)
            records.append(rec)

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if len(text) < 50:
                continue
            for raw in text.splitlines():
                line = raw.strip()
                if not line or _is_skip_line(line):
                    continue

                m_chapter = _CHAPTER_RE.match(line)
                if m_chapter:
                    _flush()
                    current = None
                    block_lines = []
                    current_ata = m_chapter.group(1).zfill(2)
                    continue

                m_task = _TASK_RE.match(line)
                if m_task:
                    _flush()
                    block_lines = []
                    current = {
                        "ATA": current_ata,
                        "TASK_NO": m_task.group("task"),
                        "DESCRIPTION": m_task.group("desc"),
                        "PART_NUMBER": "",
                        "SERIAL_NUMBER": "",
                        "STATUS_TRAIL": "",
                        "_page": page_num,
                    }
                    continue

                if current is not None:
                    block_lines.append(line)
        _flush()
    return records
