"""OCCM Index -- born-digital, full text layer (confirmed via a direct
pdfplumber pass over the real sample file: `extract_text()` returns full
content on every page, no OCR needed). Synchronous `extract()`.

Header block (repeats verbatim at the top of every page)::

    MSN <msn> <aircraft_type>
    <reg>
    OCCM Index MFG Date: <date>
    Current FH: <n>
    Current FC: <n>
    Report Dated: <date>
    ATA DESCRIPTION PART NUMBER SERIAL NUMBER INSTALL DATE TSN CSN

Parsed once from the first page and stamped on every row, same convention
this project's other header-plus-body OCCM variants use.

Per-row layout, whitespace-tokenized::

    ATA  DESCRIPTION...  PART_NUMBER  SERIAL_NUMBER  INSTALL_DATE  TSN  CSN

A typical row (placeholders, not real values)::

    <ata> <description words> <pn> <sn> <date> <tsn> FH <csn> FC

DESCRIPTION is free-text of variable width (one or more tokens), so rows are
anchored on the trailing INSTALL_DATE token (`DD/Mon/YYYY`, 4-digit year --
confirmed on every row of the real sample file) rather than a fixed token
count; PART_NUMBER and SERIAL_NUMBER are then read as the two tokens
immediately preceding that date, and everything between ATA and them is
DESCRIPTION.

TSN/CSN are confirmed to appear in one of exactly two shapes on the real
sample file (every one of 945 data rows checked directly, zero exceptions):

  1. `<n> FH <n> FC` -- each figure glued to a literal unit suffix token
     ("FH" for TSN, "FC" for CSN). The unit is constant per column (TSN is
     always hours, CSN always cycles), never varies row to row, so it
     carries no extra information once the column is known -- stripped
     here, keeping the bare integer.
  2. The literal sentinel `UNK UNK` in place of both figures, for
     components with no recorded time value -- a real, valid value (not a
     parse failure), kept verbatim as the string "UNK".

A page footer ("Page <n> of <n>") and a lone registration-only line (the
reg re-printed with no other header text, confirmed once per page directly
beneath the MSN/type line) both repeat on every page and are dropped by
shape before row-anchor detection runs -- neither ever contains a 2-digit
leading ATA token, so there is no ambiguity with a real data row.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "OCCM Index"
SIGNATURES = [
    "OCCM Index",
    "ATA DESCRIPTION PART NUMBER SERIAL NUMBER INSTALL DATE TSN CSN",
]

CANONICAL_COLUMNS = [
    "ATA",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "INSTALL_DATE",
    "TSN",
    "CSN",
    # Header metadata -- same on every row of a given file.
    "MSN",
    "AIRCRAFT_TYPE",
    "AIRCRAFT_REG",
    "MFG_DATE",
    "CURRENT_FH",
    "CURRENT_FC",
    "REPORT_DATE",
]

# TSN/CSN: a plain integer (unit suffix already stripped during parsing --
# see module docstring) or the literal sentinel "UNK".
_NUM_OR_UNK = {"pattern": r"^(?:UNK|\d+)$", "allow_empty": True}

_OVERRIDES = {
    "INSTALL_DATE": {"pattern": r"^\d{2}/[A-Za-z]{3}/\d{4}$"},
    "TSN": _NUM_OR_UNK,
    "CSN": _NUM_OR_UNK,
    "MSN":            {"pattern": r"^[A-Z0-9]+$", "uppercase": True, "allow_empty": True},
    "AIRCRAFT_TYPE":  {"allow_empty": True},
    "AIRCRAFT_REG":   {"pattern": r"^[A-Z0-9\-]+$", "uppercase": True, "allow_empty": True},
    "MFG_DATE":       {"allow_empty": True},
    "CURRENT_FH":     {"pattern": r"^\d+$", "allow_empty": True},
    "CURRENT_FC":     {"pattern": r"^\d+$", "allow_empty": True},
    "REPORT_DATE":    {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_ATA_RE = re.compile(r"^\d{2}$")
_DATE_RE = re.compile(r"^\d{2}/[A-Za-z]{3}/\d{4}$")
_PAGE_FOOTER_RE = re.compile(r"^Page \d+ of \d+$")

_META_RE = re.compile(
    r"MSN\s+(\S+)\s+(\S+)\s*\n"
    r"(\S+)\s*\n"
    r"OCCM Index MFG Date:\s*(\S+)\s*\n"
    r"Current FH:\s*(\S+)\s*\n"
    r"Current FC:\s*(\S+)\s*\n"
    r"Report Dated:\s*(\S+)"
)


def _parse_meta(text: str) -> dict:
    m = _META_RE.search(text)
    if not m:
        return {}
    msn, actype, reg, mfg_date, fh, fc, report_date = m.groups()
    return {
        "MSN": msn,
        "AIRCRAFT_TYPE": actype,
        "AIRCRAFT_REG": reg,
        "MFG_DATE": mfg_date,
        "CURRENT_FH": fh,
        "CURRENT_FC": fc,
        "REPORT_DATE": report_date,
    }


def _parse_line(line: str, page_num: int) -> dict | None:
    line = line.strip()
    if not line or _PAGE_FOOTER_RE.match(line):
        return None
    toks = line.split()
    if len(toks) < 5:
        return None
    if not _ATA_RE.match(toks[0]):
        return None

    # Row anchor: trailing INSTALL_DATE token.
    date_idx = None
    for i in range(2, len(toks)):
        if _DATE_RE.match(toks[i]):
            date_idx = i
            break
    if date_idx is None:
        return None

    tail = toks[date_idx + 1:]
    if tail == ["UNK", "UNK"]:
        tsn, csn = "UNK", "UNK"
    elif len(tail) == 4 and tail[1] == "FH" and tail[3] == "FC":
        tsn, csn = tail[0], tail[2]
    else:
        return None

    # PART_NUMBER, SERIAL_NUMBER are the two tokens immediately before the
    # date; everything between ATA and them is DESCRIPTION (one or more
    # tokens -- confirmed variable width on the real sample file).
    head = toks[1:date_idx]
    if len(head) < 3:
        return None
    pn, sn = head[-2], head[-1]
    description = " ".join(head[:-2])
    if not description:
        return None

    return {
        "ATA": toks[0],
        "DESCRIPTION": description,
        "PART_NUMBER": pn,
        "SERIAL_NUMBER": sn,
        "INSTALL_DATE": toks[date_idx],
        "TSN": tsn,
        "CSN": csn,
        "_page": page_num,
    }


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    meta: dict[str, str] = {}
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if page_num == 1:
                meta = _parse_meta(text)
            for line in text.splitlines():
                rec = _parse_line(line, page_num)
                if rec is not None:
                    rec.update(meta)
                    records.append(rec)
    return records
