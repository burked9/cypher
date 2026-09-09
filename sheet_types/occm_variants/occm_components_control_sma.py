"""OCCM Components Control (S.M.A. MIS, form PASCOM1R) -- a distinct OCCM
export confirmed via a direct pdfplumber pass on the real sample: a real text
layer (`extract_words()` returns full content on every page), no OCR needed.

The known source file's header block repeats verbatim on every page::

    <date> <time>
    Page <n> of <n>
    S.M.A. (Sistema de Mantenimiento de Avion)
    PASCOM1R
    Co: <company_code>
    Register: <reg> TSN: <tsn> CSN: <csn>
    Date: <date>
    COMPONENTS CONTROL
    Install. Date Map Description Pos P/N S/N TSN CSN TSI CSI TSO CSO TSR CSR TLP
    <date> <map> <description> <pos> <pn> <sn> <tsn> <csn> <tsi> <csi> <tso> <cso> <tsr> <csr> <tlp>

This header block (company code / aircraft reg / A/C TSN+CSN as of the report
/ report date) is parsed once from the first page and stamped onto every row,
per this project's convention (COMPANY_CODE, AIRCRAFT_REG, HEADER_TSN,
HEADER_CSN, REPORT_DATE).

Column geometry (why word x-position bucketing, not token-count splitting):
DESCRIPTION is always multi-token, POS can combine a side code with a digit
in one token (e.g. "AFT1", "RH02"), and -- critically -- the eight
time/cycles columns (TSN/CSN/TSI/CSI/TSO/CSO/TSR/CSR) are frequently *not
all populated* on a given row: a component with no prior removal has only
TSN/CSN filled in (times "since new"), one with one prior removal adds
TSI/CSI ("since install") and TSR/CSR ("since repair"), and TSO/CSO ("since
overhaul") only appears when an overhaul basis applies -- so the populated
columns don't reliably start from a fixed column and run count-many. Naive
left-to-right `split()` would misassign every later field on any row that
skips a column. Instead every word on a physical line is bucketed by its x0
against fixed column boundaries, confirmed directly against `extract_words()`
across the full 87-page known source file (a consistent gap with no words
separates each pair of columns on every inspected page, including the first,
a middle, and the last page).

Verified directly against the real 87-page file (not just page 1):
- Column x-positions are identical on every page checked (first, several
  middle pages, and the last page) -- no per-page layout drift.
- The repeating header block's own "Register: ... TSN: ... CSN: ..." line
  falls inside the same x-range as the data grid and would otherwise be
  mis-bucketed as a bogus data row; it's excluded by content (its first
  bucketed token is always the literal "Register:", a value no genuine
  INSTALL_DATE cell ever takes).
- MAP is a 6-digit numeric code (zone/ATA-adjacent reference) on every one
  of the 2,340 real data rows found once the header line above is excluded.
- The four "identical repeated TSN/CSN/TSI/CSI/TSO/CSO/TSR/CSR values" seen
  in one rough single-page pass do NOT generalise: real rows across the
  full file show anywhere from one to four of the four time-basis pairs
  populated, independently, per row (confirmed directly by inspecting many
  pages, not coincidental to one page).
- TLP is a trailing "<code>/<NN>" reference token on every row seen; <code>
  is alphabetic on some rows (matching the pattern shape of an aircraft
  registration/tracking-basis code) and purely numeric on others (a
  tracking/log-page reference number) -- both shapes are accepted by one
  pattern rather than assuming either shape is the only one.
- INSTALL_DATE is almost always `DD-MM-YYYY`; a small number of rows (12 in
  the full 87-page file) instead carry the literal placeholder
  `Unk-Accept.` (installation date genuinely unknown / accepted as-is) --
  both shapes are accepted by the pattern rather than flagging every one of
  those rows.
- No signature block, approver name, or other person-identifying text was
  found anywhere in the known source file (checked directly, every page).

TSN/TSI/TSO/TSR are `<hours>:<minutes>` tokens (e.g. `<n>:<mm>`); CSN/CSI/
CSO/CSR are plain cycle-count integers. All eight are optional per-row (see
above), so their rules allow an empty cell rather than flagging every row
that only has some of the four bases populated.
"""
from __future__ import annotations
import re

import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "OCCM Components Control (S.M.A. PASCOM1R)"

SIGNATURES = [
    "PASCOM1R",
    "COMPONENTS CONTROL",
    "Install. Date Map Description Pos P/N S/N TSN CSN TSI CSI TSO CSO TSR CSR TLP",
]

CANONICAL_COLUMNS = [
    "INSTALL_DATE",
    "MAP",
    "DESCRIPTION",
    "POS",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "TSN",
    "CSN",
    "TSI",
    "CSI",
    "TSO",
    "CSO",
    "TSR",
    "CSR",
    "TLP",
    # Header metadata -- same on every row of a given file.
    "COMPANY_CODE",
    "AIRCRAFT_REG",
    "HEADER_TSN",
    "HEADER_CSN",
    "REPORT_DATE",
]

_DATE_RULE = {"pattern": r"^(\d{2}-\d{2}-\d{4}|Unk-Accept\.)$"}
_TIME_RULE = {"pattern": r"^\d{1,6}:\d{1,2}$", "allow_empty": True}
_CYCLE_RULE = {"pattern": r"^\d{1,6}$", "allow_empty": True}
_OVERRIDES = {
    "INSTALL_DATE":  _DATE_RULE,
    "MAP":           {"pattern": r"^\d{6}$"},
    # POS values include plain side/index codes (e.g. "<n>", "LH", "RH")
    # as well as hyphenated/slashed sub-position codes (e.g. "<n>-<n>",
    # "LH-<letter>", "F/O") -- confirmed directly across the full 87-page
    # known source file.
    "POS":           {"pattern": r"^[A-Z0-9/\-]{1,10}$", "uppercase": True},
    "TSN":           _TIME_RULE,
    "CSN":           _CYCLE_RULE,
    "TSI":           _TIME_RULE,
    "CSI":           _CYCLE_RULE,
    "TSO":           _TIME_RULE,
    "CSO":           _CYCLE_RULE,
    "TSR":           _TIME_RULE,
    "CSR":           _CYCLE_RULE,
    "TLP":           {"pattern": r"^[A-Z0-9]+/\d{2}$", "uppercase": True},
    "COMPANY_CODE":  {"pattern": r"^[A-Z0-9]{2,6}$", "uppercase": True},
    "AIRCRAFT_REG":  {"pattern": r"^[A-Z0-9\-]{3,8}$", "uppercase": True},
    "HEADER_TSN":    {"pattern": r"^\d{1,6}:\d{1,2}$"},
    "HEADER_CSN":    {"pattern": r"^\d{1,6}$"},
    "REPORT_DATE":   {"pattern": r"^\d{2}/\d{2}/\d{4}$"},
}
RULES = merged_rules(_OVERRIDES)

# Column x-boundaries (PDF points), derived from real header + data-row word
# coordinates on the known source file -- consistent across every inspected
# page (first, several middle pages, and the last page). "Install." and
# "Date" are two header words for a single INSTALL_DATE data column.
# INSTALL_DATE | MAP | DESCRIPTION | POS | PART_NUMBER | SERIAL_NUMBER |
# TSN | CSN | TSI | CSI | TSO | CSO | TSR | CSR | TLP.
_BOUNDS = [0, 60, 85, 240, 265, 345, 490, 518, 548, 580, 618, 655, 688, 725, 762, 10**6]
_FIELDS = [
    "INSTALL_DATE", "MAP", "DESCRIPTION", "POS", "PART_NUMBER", "SERIAL_NUMBER",
    "TSN", "CSN", "TSI", "CSI", "TSO", "CSO", "TSR", "CSR", "TLP",
]

_CO_RE = re.compile(r"^Co:\s*(\S+)", re.MULTILINE)
_REG_RE = re.compile(r"^Register:\s*(\S+)\s+TSN:\s*(\S+)\s+CSN:\s*(\S+)", re.MULTILINE)
_DATE_RE = re.compile(r"^Date:\s*(\S+)", re.MULTILINE)


def _bucket(x0: float) -> str:
    for i in range(len(_BOUNDS) - 1):
        if _BOUNDS[i] <= x0 < _BOUNDS[i + 1]:
            return _FIELDS[i]
    return _FIELDS[-1]


def _parse_meta(text: str) -> dict:
    meta: dict[str, str] = {}
    m = _CO_RE.search(text)
    if m:
        meta["COMPANY_CODE"] = m.group(1)
    m = _REG_RE.search(text)
    if m:
        meta["AIRCRAFT_REG"] = m.group(1)
        meta["HEADER_TSN"] = m.group(2)
        meta["HEADER_CSN"] = m.group(3)
    m = _DATE_RE.search(text)
    if m:
        meta["REPORT_DATE"] = m.group(1)
    return meta


def _group_lines(words: list[dict]) -> list[dict]:
    """Cluster words into physical lines by y-position (tolerant of
    sub-point 'top' jitter between words nominally on the same visual
    line)."""
    ws = sorted(words, key=lambda w: (w["top"], w["x0"]))
    lines: list[dict] = []
    for w in ws:
        if lines and abs(w["top"] - lines[-1]["top"]) <= 2.5:
            lines[-1]["words"].append(w)
            lines[-1]["top"] = (lines[-1]["top"] + w["top"]) / 2
        else:
            lines.append({"top": w["top"], "words": [w]})
    for line in lines:
        line["words"].sort(key=lambda w: w["x0"])
    return lines


def _bucket_line(line: dict) -> dict:
    row = {f: "" for f in _FIELDS}
    for w in line["words"]:
        field = _bucket(w["x0"])
        row[field] = (row[field] + " " + w["text"]).strip()
    return row


def _extract_page(page) -> list[dict]:
    words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
    if not words:
        return []
    rows: list[dict] = []
    for line in _group_lines(words):
        row = _bucket_line(line)
        # The repeating column-header line ("Install. Date Map ...") buckets
        # its own literal "Description" label into the DESCRIPTION column --
        # skipped by content.
        if row["DESCRIPTION"] == "Description":
            continue
        # The repeating "Register: <reg> TSN: <n> CSN: <n>" header line falls
        # inside the same x-range as the data grid; its first bucketed token
        # is always the literal "Register:", a value no genuine INSTALL_DATE
        # cell ever takes -- skipped by content rather than a fixed
        # y-cutoff, so it's robust to the header block's height varying.
        if row["INSTALL_DATE"] == "Register:":
            continue
        # A genuine data row always carries both a MAP code and a
        # DESCRIPTION; no other repeating header/title line populates both.
        if not (row["MAP"] and row["DESCRIPTION"]):
            continue
        rows.append(row)
    return rows


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        meta = _parse_meta(pdf.pages[0].extract_text() or "") if pdf.pages else {}
        for page_num, page in enumerate(pdf.pages, start=1):
            for row in _extract_page(page):
                for k, v in meta.items():
                    row[k] = v
                row["_page"] = page_num
                records.append(row)
    return records
