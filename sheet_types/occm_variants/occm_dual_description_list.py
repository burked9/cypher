"""OCCM Dual-Description List -- born-digital, full text layer, coordinate-
bucketed columns (same technique as `occm_summary_list.py` / `occm_report.py`
/ `ht_variants/time_controlled_components_status.py`).

Confirmed on one real file in the corpus (clean text layer via pdfplumber
`extract_words()` on every page, no OCR needed)::

    Date: <date> Flight Hours: <n> OCCM
    Aircraft: msn <msn> Cycles: <n>
    ATA DESCRIPTION PART NO. SERIAL NO. DESCRIPTION2 POS. INST-DATE
    <ata> <ata-chapter heading> <pn> <sn> <description> <pos> <inst-date>
    <pn> <sn> <description> <pos> <inst-date>
    <pn> <sn> <description> <pos> <inst-date>

The column header line has TWO "DESCRIPTION" columns at different
x-positions, the same two-heading shape as `occm_summary_list.py` -- the
first ("DESCRIPTION") is an ATA-CHAPTER-level heading (e.g. "AIR
CONDITIONING") that only prints on the FIRST data row of a new ATA chapter;
the second ("DESCRIPTION2") is the real per-component description (e.g.
"SWITCH, SELECTOR"). Confirmed directly against the real sample file: only
31 of 2288 data rows carry an ATA number + chapter heading at all (one per
chapter run); every other row in that chapter starts straight from PART NO.,
with blank ATA and blank heading. This differs from `occm_summary_list.py`
in one important way that changes the row-anchor logic: on that module's
known source file, EVERY data row repeats the ATA number as its first
token, so "first word is a bare 1-2 digit number" is a safe universal
row anchor. On THIS format's known source file, only the chapter-heading
row itself starts with an ATA number -- continuation rows within the same
chapter start directly at the PART NO. column with no leading digit token
in the ATA column's x-range at all. Anchoring on "first word is ATA-shaped"
here would silently drop every continuation row (the vast majority of the
table). Instead, a row is accepted when it has a word in the PART NO.
column's x-range AND its last INST-DATE-column word matches the
"<D>.<Mon>.<YYYY>" date shape -- confirmed true for all 2288 data rows and
false for every header/footer line on all 72 pages of the known source file
(see `_is_data_row`).

INST-DATE uses a dot-separated "<D>.<Mon>.<YYYY>" shape (e.g. a 1-2 digit
day, 3-letter month, 4-digit year, each separated by a literal "."), unlike
`occm_summary_list.py`'s dash-separated "<D>-<Mon>-<YY>" shape -- confirmed
directly against every INST-DATE value on the known source file, no
exceptions found.

No trailing TSN/CSN-style columns exist on this format -- confirmed both
from the column-header line (which has none) and by checking every data
row's rightmost word position across all 72 pages of the known source
file: nothing follows the INST-DATE value on any row.

DESCRIPTION2 (the real per-component description) is frequently multi-word
and can run wide enough to abut the POS. column's own x-position on the
known source file (confirmed: the widest observed description word starts
well below where POS. values start, with a comfortable gap between them --
see `_BOUNDS`), so the DESCRIPTION/POSITION boundary is placed close to the
POS. column's own start rather than at the naive header-midpoint, to avoid
misbucketing a long wrapped description word as a position code.

Each page repeats a small fixed header/footer block (a title line with
Date/Flight-Hours, an Aircraft/Cycles line, the column-header line, and a
page-footer line with the aircraft identifier and "Page X of Y") -- all
four are rejected by `_is_data_row` for free, no special-casing needed,
since none of them carries a PART NO.-column word paired with a
dot-separated date in the INST-DATE column.

Header metadata (REPORT_DATE, FLIGHT_HOURS, MSN, CYCLES) is parsed once
from the first page and stamped on every row, same convention this
project's other header-plus-body OCCM variants use. ATA_HEADING is left
per-row (not forward-filled) since it is a chapter-level label, not a
per-component fact that's missing -- the generic ATA forward-fill in
`sheet_types/occm.py`'s `normalize_and_validate` still fills the plain ATA
column across each chapter's continuation rows.
"""
from __future__ import annotations
import re

import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "OCCM Dual-Description List"

SIGNATURES = [
    "ATA DESCRIPTION PART NO. SERIAL NO. DESCRIPTION2 POS. INST-DATE",
]

CANONICAL_COLUMNS = [
    "ATA",
    "ATA_HEADING",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
    "POSITION",
    "INST_DATE",
    # Header metadata, parsed once per file and stamped on every row.
    "REPORT_DATE",
    "FLIGHT_HOURS",
    "MSN",
    "CYCLES",
]

# INST-DATE uses a dot-separated "<D>.<Mon>.<YYYY>" shape on this format,
# unlike occm_summary_list.py's dash-separated equivalent -- confirmed
# directly against every value on the known source file.
_DATE_RE = re.compile(r"^\d{1,2}\.[A-Za-z]{3}\.\d{4}$")

_OVERRIDES = {
    "ATA_HEADING":   {"allow_empty": True, "uppercase": True},
    "POSITION":      {"pattern": r"^[A-Z0-9./\- ]{1,20}$", "uppercase": True,
                       "allow_empty": True},
    "INST_DATE":     {"pattern": _DATE_RE.pattern},
    "REPORT_DATE":   {"allow_empty": True},
    "FLIGHT_HOURS":  {"pattern": r"^\d+$", "allow_empty": True},
    "MSN":           {"allow_empty": True},
    "CYCLES":        {"pattern": r"^\d+$", "allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Column x-boundaries (PDF points), derived from real header + data-row word
# coordinates on the known source file -- consistent across every inspected
# page. Order matches the header line's own column order: ATA |
# DESCRIPTION(heading) | PART NO. | SERIAL NO. | DESCRIPTION2 | POS. |
# INST-DATE. The DESCRIPTION/POSITION boundary is placed close to POS.'s own
# start (not the naive midpoint) since DESCRIPTION2 text can run wide -- see
# module docstring.
_BOUNDS = [0, 90, 235, 330, 430, 625, 680, 10**6]
_FIELDS = [
    "ATA", "ATA_HEADING", "PART_NUMBER", "SERIAL_NUMBER", "DESCRIPTION",
    "POSITION", "INST_DATE",
]

_REPORT_DATE_RE = re.compile(r"\bDate:\s*(\S+)")
_FLIGHT_HOURS_RE = re.compile(r"\bFlight Hours:\s*(\S+)")
_MSN_RE = re.compile(r"\bAircraft:\s*msn\s+(\S+)", re.IGNORECASE)
_CYCLES_RE = re.compile(r"\bCycles:\s*(\S+)")


def _bucket(x0: float) -> str:
    for i in range(len(_BOUNDS) - 1):
        if _BOUNDS[i] <= x0 < _BOUNDS[i + 1]:
            return _FIELDS[i]
    return _FIELDS[-1]


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


def _is_data_row(line: dict) -> bool:
    """A real data row has a word in the PART NO. column's x-range AND its
    last INST-DATE-column word matches the dot-separated date shape.
    Confirmed on the known source file: every non-data line (title,
    Date/Flight Hours block, Aircraft/Cycles block, column-header line,
    page-footer "<msn> Page X of Y" line) fails this test on all 72
    pages, and every one of the 2288 data rows passes it. Unlike
    `occm_summary_list.py`, "first word is ATA-shaped" is NOT used here --
    that test only matches the ~1%-of-rows chapter-heading lines on this
    format (see module docstring) and would drop every continuation row."""
    has_pn = False
    inst_words: list[str] = []
    for w in line["words"]:
        field = _bucket(w["x0"])
        if field == "PART_NUMBER":
            has_pn = True
        elif field == "INST_DATE":
            inst_words.append(w["text"])
    return has_pn and bool(inst_words) and bool(_DATE_RE.match(inst_words[-1]))


def _parse_header_meta(first_page_text: str) -> dict:
    meta = {"REPORT_DATE": "", "FLIGHT_HOURS": "", "MSN": "", "CYCLES": ""}
    m = _REPORT_DATE_RE.search(first_page_text)
    if m:
        meta["REPORT_DATE"] = m.group(1)
    m = _FLIGHT_HOURS_RE.search(first_page_text)
    if m:
        meta["FLIGHT_HOURS"] = m.group(1)
    m = _MSN_RE.search(first_page_text)
    if m:
        meta["MSN"] = m.group(1)
    m = _CYCLES_RE.search(first_page_text)
    if m:
        meta["CYCLES"] = m.group(1)
    return meta


def _extract_page(page) -> list[dict]:
    words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
    if not words:
        return []
    rows: list[dict] = []
    for line in _group_lines(words):
        if _is_data_row(line):
            rows.append(_bucket_line(line))
    return rows


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        if not pdf.pages:
            return records
        meta = _parse_header_meta(pdf.pages[0].extract_text() or "")
        for page_num, page in enumerate(pdf.pages, start=1):
            for row in _extract_page(page):
                row.update(meta)
                row["_page"] = page_num
                records.append(row)
    return records
