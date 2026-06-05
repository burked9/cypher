"""Remaining Potentials variant — "Remaining potentials report" format.

Likely produced by 2MORO's AMASIS MIS (the "remaining potentials" phrase is
strongly associated with it), but we name the variant after the format header
rather than the vendor since we haven't confirmed attribution. If a future
document carries an explicit `AMASIS` or `2MORO` string, we can update the
signature and confidently rename.

Uses a six-line-per-record layout very different from AMOS or OASES.

Per-record layout (6 lines):

    Line 1 — Kardex + Position/AMM-Description
        "345101A VHF NAV-433 L/H"

    Line 2 — Installation date + PN + SN + Full equipment description
        "23/10/2008 PN : 822-0393-001 SN :26GH0 RECEIVER-VHF NAV-433"

    Line 3 — AMM / FIN status (often just "O/C" = "On Condition")
        "O/C"

    Line 4 — FH (Flight-Hours) time matrix: 13–16 tokens of values / "O/C"
    Line 5 — CY (Cycles) time matrix
    Line 6 — Days time matrix

The time-matrix rows hold 4 maintenance categories
(Inspection / Inspection 2 / Overhaul / Life Limit) each with up to 4
sub-columns (BI / SI / Remain / Deadline). Many cells are "O/C" because
the component is on-condition monitoring only. We capture the entire row
verbatim as a single field — `FH_RAW`, `CY_RAW`, `DAYS_RAW` — so the
analyst can post-process without losing data. A future refinement could
split these into the full 48-column matrix once the variation across files
is characterised; the raw fields are the safe v1 substrate.

Header lines (5 or 6 lines at the top of every page) are skipped by
requiring records to start with a token that looks like a kardex
(alphanumeric, typically `\\d{4,7}[A-Z]?`).
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "Remaining Potentials"
SIGNATURES = [
    "Remaining potentials report",
    "Aircraft Remaining Potentials",
    "BI SI Remain Deadline",
    "Effectivity :",   # always paired with the Remaining-Potentials header
]

CANONICAL_COLUMNS = [
    "KARDEX",
    "POSITION_DESC",
    "INSTAL_DATE",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "FULL_DESCRIPTION",
    "AMM_FIN",
    # Time matrix preserved as raw strings — future refinement can parse the
    # 16-sub-column layout once it's confirmed stable across operators.
    "FH_RAW",
    "CY_RAW",
    "DAYS_RAW",
]

_OVERRIDES = {
    "KARDEX": {"pattern": r"^[A-Z0-9]{3,10}$", "uppercase": True},
    "INSTAL_DATE": {"pattern": r"^\d{1,2}/\d{1,2}/\d{4}$"},
    # FH_RAW / CY_RAW / DAYS_RAW are free-form preserved-data fields
}
RULES = merged_rules(_OVERRIDES)

# Patterns
_KARDEX_RE = re.compile(r"^[A-Z0-9]{3,10}\b")   # e.g. 345101A, 783203C
_DATE_RE   = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}\b")
_LINE2_RE  = re.compile(
    r"^(?P<date>\d{1,2}/\d{1,2}/\d{4})\s+"
    r"PN\s*:\s*(?P<pn>\S+)\s+"
    r"SN\s*:\s*(?P<sn>\S+)"
    r"(?:\s+(?P<desc>.+))?$"
)


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if len(text) < 100:
                continue
            lines = [l.strip() for l in text.splitlines() if l.strip()]

            i = 0
            while i < len(lines):
                line = lines[i]

                # Try line-2 first (most distinctive); when found, walk back
                # one line for the kardex and forward 4 lines for AMM/FH/CY/Days.
                m2 = _LINE2_RE.match(line)
                if m2:
                    # Need a previous line that looks like a kardex header
                    if i >= 1 and _KARDEX_RE.match(lines[i - 1]):
                        kardex_line = lines[i - 1].split(maxsplit=1)
                        kardex = kardex_line[0]
                        pos_desc = kardex_line[1] if len(kardex_line) > 1 else ""

                        # Read forward
                        amm_fin = lines[i + 1] if i + 1 < len(lines) else ""
                        fh_raw  = lines[i + 2] if i + 2 < len(lines) else ""
                        cy_raw  = lines[i + 3] if i + 3 < len(lines) else ""
                        days_raw = lines[i + 4] if i + 4 < len(lines) else ""

                        # Strip the leading "FH"/"CY"/"Days" keyword from the raw lines
                        if fh_raw.startswith("FH "):    fh_raw = fh_raw[3:]
                        if cy_raw.startswith("CY "):    cy_raw = cy_raw[3:]
                        if days_raw.startswith("Days "): days_raw = days_raw[5:]

                        rec = {c: "" for c in CANONICAL_COLUMNS}
                        rec["KARDEX"] = kardex
                        rec["POSITION_DESC"] = pos_desc
                        rec["INSTAL_DATE"] = m2.group("date")
                        rec["PART_NUMBER"] = m2.group("pn")
                        rec["SERIAL_NUMBER"] = m2.group("sn")
                        rec["FULL_DESCRIPTION"] = m2.group("desc") or ""
                        rec["AMM_FIN"] = amm_fin
                        rec["FH_RAW"] = fh_raw
                        rec["CY_RAW"] = cy_raw
                        rec["DAYS_RAW"] = days_raw
                        rec["_page"] = page_num
                        records.append(rec)
                        # Skip past this record
                        i += 5
                        continue
                i += 1
    return records
