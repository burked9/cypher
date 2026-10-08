"""CCA A340 HT — `HT COMPONETS STATUS` format.

Companion to `occm_variants/cca_a340_occm.py` (same operator, same
distinctive ``COMPONETS`` misspelling). Small file (5 pages on the known
sample), tabular layout with these columns::

    MPD No. DESCRIPTION MFG DATE OH/REPAIR DATE LOC P/N S/N
    NEXT DUE FH NEXT DUE FC NEXT DUE DATE LIFE TIME CAL/H TASK
    DATE OF INSTL CURRENT FH CURRENT FC REMAINING FH REMAINING FC

Dates appear in ``YYYY.MM.DD`` format. ``LIFE TIME`` may contain compound
values like ``50000FH/12YEARS``.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.ht_variants._base import merged_rules

NAME = "CCA A340 HT"
SIGNATURES = [
    "HT COMPONETS STATUS",
]
AIRCRAFT_FILTER = re.compile(r"A340", re.I)

CANONICAL_COLUMNS = [
    "MPD_NO",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "POSITION",
    "INSTALL_DATE",
    "NEXT_DUE_DATE",
    "LIFE_LIMIT",
    "REMAINING_FH",
    "REMAINING_FC",
]

_OVERRIDES = {
    "MPD_NO":        {"pattern": r"^[A-Z]?\d[\d\-]+$", "allow_empty": False},
    "POSITION":      {"pattern": r"^[A-Z0-9 ./\-]{1,12}$", "uppercase": True,
                      "allow_empty": True},
    "INSTALL_DATE":  {"pattern": r"^\d{4}\.\d{1,2}\.\d{1,2}$",
                      "allow_empty": True},
    "NEXT_DUE_DATE": {"pattern": r"^\d{4}\.\d{1,2}\.\d{1,2}$",
                      "allow_empty": True},
    "LIFE_LIMIT":    {"allow_empty": True},
    "REMAINING_FH":  {"allow_empty": True},
    "REMAINING_FC":  {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_MPD_RE = re.compile(r"^[A-Z]?\d[\d\-]{4,}$")
_DATE_RE = re.compile(r"^\d{4}\.\d{1,2}\.\d{1,2}$")
_NUM_RE = re.compile(r"^[\d.,#]+$|^#VALUE!$")
_HEADER_SKIP = re.compile(
    r"^MPD\b|^A/C Type|^Prepared by|^As of|^A340|^MSN|^Page\b|^HT COMP",
    re.I)


def _parse_table_row(cells: list[str], page_num: int) -> dict | None:
    if len(cells) < 6:
        return None
    mpd = (cells[0] or "").strip()
    if not _MPD_RE.match(mpd):
        return None
    desc = (cells[1] or "").strip()
    pn = (cells[5] or "").strip() if len(cells) > 5 else ""
    sn = (cells[6] or "").strip() if len(cells) > 6 else ""
    loc = (cells[4] or "").strip() if len(cells) > 4 else ""
    next_due_date = (cells[9] or "").strip() if len(cells) > 9 else ""
    life_limit = (cells[10] or "").strip() if len(cells) > 10 else ""
    install_date = (cells[13] or "").strip() if len(cells) > 13 else ""
    remaining_fh = (cells[16] or "").strip() if len(cells) > 16 else ""
    remaining_fc = (cells[17] or "").strip() if len(cells) > 17 else ""
    if not desc and not pn:
        return None
    return {
        "MPD_NO": mpd,
        "DESCRIPTION": desc,
        "PART_NUMBER": pn,
        "SERIAL_NUMBER": sn,
        "POSITION": loc,
        "INSTALL_DATE": install_date,
        "NEXT_DUE_DATE": next_due_date,
        "LIFE_LIMIT": life_limit,
        "REMAINING_FH": remaining_fh,
        "REMAINING_FC": remaining_fc,
        "_page": page_num,
    }


def _parse_text_line(line: str, page_num: int) -> dict | None:
    toks = line.split()
    if len(toks) < 5:
        return None
    if not _MPD_RE.match(toks[0]):
        return None
    mpd = toks[0]
    desc_parts = []
    i = 1
    while i < len(toks) and not _DATE_RE.match(toks[i]) and not _NUM_RE.match(toks[i]):
        desc_parts.append(toks[i])
        i += 1
    if not desc_parts:
        return None
    desc = " ".join(desc_parts)
    rest = toks[i:]
    pn = ""
    sn = ""
    loc = ""
    for j, t in enumerate(rest):
        if re.match(r"^\d{3,}[A-Z]?[A-Z0-9\-]*$", t) and not pn:
            if j + 1 < len(rest) and re.match(r"^[A-Z0-9\-]{4,}$", rest[j + 1]):
                pn = rest[j]
                sn = rest[j + 1]
                break
    return {
        "MPD_NO": mpd,
        "DESCRIPTION": desc,
        "PART_NUMBER": pn,
        "SERIAL_NUMBER": sn,
        "POSITION": loc,
        "INSTALL_DATE": "",
        "NEXT_DUE_DATE": "",
        "LIFE_LIMIT": "",
        "REMAINING_FH": "",
        "REMAINING_FC": "",
        "_page": page_num,
    }


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            tables = page.extract_tables()
            if tables:
                for table in tables:
                    for row in table:
                        if not row:
                            continue
                        rec = _parse_table_row(row, page_num)
                        if rec is not None:
                            records.append(rec)
            else:
                text = page.extract_text() or ""
                for raw in text.splitlines():
                    line = raw.strip()
                    if not line or _HEADER_SKIP.search(line):
                        continue
                    rec = _parse_text_line(line, page_num)
                    if rec is not None:
                        records.append(rec)
    return records
