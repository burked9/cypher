"""OCCM Report (Time Matrix) -- a distinct "OCCM Report"-titled export from
`occm_report.py`, confirmed via a direct pdfplumber pass on the real sample:
a real text layer (`extract_text()`/`extract_words()` return full content on
every page), no OCR needed.

`occm_report.py`'s known source file is a 6-column grid (ATA / INSTALL DATE
/ POSITION / PN / SN / DESCRIPTION) with no "OCCM" text anywhere in its
header. This variant's known source file is genuinely different: it has a
distinct header block giving report date and aircraft totals, and a
10-column data grid that additionally carries per-component time/cycles
"at install" and "since install, as of today" figures -- fields
`occm_report.py` does not have at all::

    OCCM Report Date : <date>
    A/C hours : <n>
    <reg> A/C cycles : <n>
    ATA Part # Serial # Position Description Installation Date T@I C@I TSI@Today CSI@Today
    <ata> <pn> <sn> <position> <description> <date> <n> <n> <n> <n>
    <ata> <pn> <sn> <position> <description> <date> <n> <n> <n> <n>

This header block (report date / aircraft hours / registration + aircraft
cycles) repeats verbatim on every page of the known source file and is
parsed once from the first page and stamped onto every row.

Column geometry (why word x-position bucketing, not token-count splitting):
PART_NUMBER, POSITION and DESCRIPTION can each be more than one
whitespace-separated token (e.g. a Position of "<n> HB" or a Description of
two words), and PART_NUMBER occasionally splits into two words purely from
inter-glyph spacing in the source PDF (e.g. "<pn>-0" / "1" rendering as two
separate words for what is really one part number) -- naive left-to-right
`split()` would misassign every column after the first such field. Instead
every word on a physical line is bucketed by its x0 against fixed column
boundaries, confirmed directly against `extract_words()` on the known
source file (a wide gap with no words in it separates each pair of
columns, consistent across every inspected page). No line-wrap/overflow
case was found on the known source file -- every data row's ten fields
land on one physical line -- so unlike `occm_report.py`'s sibling variant,
no multi-line row-merging logic is needed here.

The data columns run to 4-figure comma-thousands values (e.g. hours/cycles
figures), which is why the four time/cycles columns use `int_range` rather
than a plain-digit `pattern` -- this project's shared cleanup pipeline
already parses comma-thousands integers for range-checked columns, but a
`^\\d+$`-style pattern would reject every comma-formatted value outright.

The known source file's Installation Date values are mostly clean
`D-Mon-YY` tokens, but at least one row's month abbreviation is corrupted
in the extracted text (a font/encoding quirk in the source PDF itself, not
an artifact of this parser) -- that row is expected to soft-fail the
INSTALLATION_DATE pattern check and surface via `_issues`, which is the
intended behaviour (validation here is soft: flag, never drop or silently
"fix" a value we can't be sure of).
"""
from __future__ import annotations
import re

import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "OCCM Report (Time Matrix)"

SIGNATURES = [
    "OCCM Report Date :",
    "Serial # Position Description Installation Date",
]

CANONICAL_COLUMNS = [
    "ATA",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "POSITION",
    "DESCRIPTION",
    "INSTALLATION_DATE",
    "T_AT_INSTALL",
    "C_AT_INSTALL",
    "TSI_TODAY",
    "CSI_TODAY",
    # Header metadata -- same on every row of a given file.
    "AIRCRAFT_REG",
    "REPORT_DATE",
    "AC_HOURS",
    "AC_CYCLES",
]

_DATE_RULE = {"pattern": r"^\d{1,2}-[A-Za-z]{3}-\d{2}$"}
_HOURS_RULE = {"int_range": (0, 200000)}
_CYCLES_RULE = {"int_range": (0, 55000), "int_range_review": (0, 30000)}
_OVERRIDES = {
    # ATA here is "<chapter>-<subchapter>" (e.g. "21-00"), not the global
    # bare 2-digit chapter -- same convention as iberia_listado.py's ATA
    # override. int_range must be cleared too, or the inherited (20, 83)
    # bound from the global rule would run range-checking against a value
    # that isn't a clean integer at all and wrongly flag every row.
    "ATA":                {"pattern": r"^\d{2}-\d{2}$", "int_range": None},
    "POSITION":            {"allow_empty": True},
    "INSTALLATION_DATE":   _DATE_RULE,
    "T_AT_INSTALL":        _HOURS_RULE,
    "C_AT_INSTALL":        _CYCLES_RULE,
    "TSI_TODAY":           _HOURS_RULE,
    "CSI_TODAY":           _CYCLES_RULE,
    "AIRCRAFT_REG":        {"pattern": r"^[A-Z0-9\-]+$", "uppercase": True},
    "REPORT_DATE":         _DATE_RULE,
    "AC_HOURS":            _HOURS_RULE,
    "AC_CYCLES":           _CYCLES_RULE,
}
RULES = merged_rules(_OVERRIDES)

# Column x-boundaries (PDF points), derived from real header + data-row word
# coordinates on the known source file -- consistent across every inspected
# page (a wide gap with no words in it separates each pair of columns).
# ATA | PART_NUMBER | SERIAL_NUMBER | POSITION | DESCRIPTION |
# INSTALLATION_DATE | T_AT_INSTALL | C_AT_INSTALL | TSI_TODAY | CSI_TODAY.
_BOUNDS = [0, 80, 155, 210, 250, 350, 410, 445, 480, 515, 10**6]
_FIELDS = [
    "ATA", "PART_NUMBER", "SERIAL_NUMBER", "POSITION", "DESCRIPTION",
    "INSTALLATION_DATE", "T_AT_INSTALL", "C_AT_INSTALL", "TSI_TODAY", "CSI_TODAY",
]

_REPORT_DATE_RE = re.compile(r"OCCM Report Date\s*:\s*(\S+)")
_AC_HOURS_RE = re.compile(r"A/C hours\s*:\s*([\d,]+)")
_REG_CYCLES_RE = re.compile(r"^(\S+)\s+A/C cycles\s*:\s*([\d,]+)", re.MULTILINE)


def _bucket(x0: float) -> str:
    for i in range(len(_BOUNDS) - 1):
        if _BOUNDS[i] <= x0 < _BOUNDS[i + 1]:
            return _FIELDS[i]
    return _FIELDS[-1]


def _parse_meta(text: str) -> dict:
    meta: dict[str, str] = {}
    m = _REPORT_DATE_RE.search(text)
    if m:
        meta["REPORT_DATE"] = m.group(1)
    m = _AC_HOURS_RE.search(text)
    if m:
        meta["AC_HOURS"] = m.group(1)
    m = _REG_CYCLES_RE.search(text)
    if m:
        meta["AIRCRAFT_REG"] = m.group(1)
        meta["AC_CYCLES"] = m.group(2)
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
        # The repeating column-header line ("ATA Part # Serial # ...")
        # buckets its own literal "ATA" label into the ATA column -- the
        # one value a genuine data row (always "<chapter>-<subchapter>")
        # can never take. Skipped by content rather than by a fixed
        # y-position so it's robust to the header block's height varying.
        if row["ATA"] == "ATA":
            continue
        # A genuine data row always carries both an ATA chapter and an
        # Installation Date; the report-header lines (title/date/hours/
        # reg+cycles block) never populate both, so this doubles as the
        # anchor that excludes them without needing a fixed y-cutoff.
        if not (row["ATA"] and row["INSTALLATION_DATE"]):
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
