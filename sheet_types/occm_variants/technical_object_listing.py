"""Technical Object Listing variant — SAP/EAM-style OCCM export.

Detected on a single-operator document set. Multi-line records: each
component spans 6-9 lines with a time matrix block covering Install /
Inspect / Repair / Overhaul / Total.

Per-record layout:
    Line 1:    <KARDEX> <DESCRIPTION...> <PN> <SN> <FUNCTIONAL_LOCATION>
    Line 2:    `Since Install` <Hours> <Cycles> <ServDays> <Days> <EventDate>
    Line 3:    `Since Inspect` <Hours> <Cycles> <ServDays> <Days>
    Line 4:    `Since Repair`  <Hours> <Cycles> <ServDays> <Days>
    Line 5:    `Since Overhaul`<Hours> <Cycles> <ServDays> <Days>
    Line 6:    `TOTAL`         <Hours> <Cycles> <ServDays> <Days>
    Line 7+:   `Allowable Time` / `Life Limit` / `Inspection Period`
               (often empty or sparse; these terminate the record group)

We capture the key identity fields and the time matrix rows as raw strings
(install_raw / inspect_raw / repair_raw / overhaul_raw / total_raw) so the
analyst can post-process without lossy parsing. A future refinement can
split the 4-5 numeric columns per row into typed fields once we have more
sample diversity.

Kardex anchor: a leading 8-digit number on a line that also contains a
plausible part number and a `OJB/…` (or similar) functional-location token.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "Technical Object Listing"
SIGNATURES = [
    "Equipment Description of Technical Object",
    "Functional Location",
    "Since Install",
    "Since Inspect",
]

CANONICAL_COLUMNS = [
    "KARDEX",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "FUNCTIONAL_LOCATION",
    "INSTALL_RAW",
    "INSPECT_RAW",
    "REPAIR_RAW",
    "OVERHAUL_RAW",
    "TOTAL_RAW",
    "INSTALL_DATE",
]

_OVERRIDES = {
    "KARDEX": {"pattern": r"^\d{8}$"},
    "INSTALL_DATE": {"pattern": r"^\d{1,2}/\d{1,2}/\d{4}$"},
    # Raw fields are free-form preserved-data strings
}
RULES = merged_rules(_OVERRIDES)

_KARDEX_RE = re.compile(r"^\d{8}\b")
_HEADER_RE = re.compile(
    r"^(?P<kardex>\d{8})\s+(?P<desc>.+?)\s+(?P<pn>\S+)\s+(?P<sn>\S+)\s+(?P<loc>\S+)$"
)
_INSTALL_DATE_RE = re.compile(r"\d{1,2}/\d{1,2}/\d{4}")


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
                m = _HEADER_RE.match(lines[i])
                if not m:
                    i += 1
                    continue

                rec = {c: "" for c in CANONICAL_COLUMNS}
                rec["KARDEX"] = m.group("kardex")
                rec["DESCRIPTION"] = m.group("desc")
                rec["PART_NUMBER"] = m.group("pn")
                rec["SERIAL_NUMBER"] = m.group("sn")
                rec["FUNCTIONAL_LOCATION"] = m.group("loc")
                rec["_page"] = page_num

                # Walk forward, attaching time-matrix lines until we hit a
                # terminator or the next kardex.
                j = i + 1
                while j < len(lines):
                    nxt = lines[j]
                    if _KARDEX_RE.match(nxt):
                        break
                    low = nxt.lower()
                    if low.startswith("since install"):
                        rec["INSTALL_RAW"] = nxt[len("Since Install"):].strip()
                        # Pull the install date out — it lives on this line
                        date_m = _INSTALL_DATE_RE.search(nxt)
                        if date_m:
                            rec["INSTALL_DATE"] = date_m.group(0)
                    elif low.startswith("since inspect"):
                        rec["INSPECT_RAW"] = nxt[len("Since Inspect"):].strip()
                    elif low.startswith("since repair"):
                        rec["REPAIR_RAW"] = nxt[len("Since Repair"):].strip()
                    elif low.startswith("since overhaul"):
                        rec["OVERHAUL_RAW"] = nxt[len("Since Overhaul"):].strip()
                    elif low.startswith("total"):
                        rec["TOTAL_RAW"] = nxt[len("TOTAL"):].strip()
                    elif low.startswith(("allowable time", "life limit",
                                         "inspection period")):
                        # Terminator group — end of this record's matrix
                        j += 1
                        break
                    j += 1
                records.append(rec)
                i = j
    return records
