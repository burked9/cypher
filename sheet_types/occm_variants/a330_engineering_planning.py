"""A330 Engineering & Planning OCCM — French A330 operator format.

Single airframe seen so far, but distinct layout that needs its own parser.
Header looks like::

    OCCM STATUS
    A/C REG <REG> ENGINEERING & PLANNING
    A/C MSN <MSN>
    A/C TYPE A330-200
    ...
    ATA ZONE FIN DESCRIPTION PART NUMBER SERIAL NUMBER ... TSN CSN
    21 162 282HN FAN,EXTRACTION VD3810 9054008 3-Jan-13 40691 6013 6772 3724 32233,55 7347

Per-row layout (13 fixed-position tokens):

    [0] ATA          (2-digit chapter)
    [1] ZONE         (3-digit airframe zone)
    [2] FIN          (functional item number, e.g. 282HN)
    [3..date-2] DESCRIPTION (variable width; one or more tokens)
    [date-2] PART_NUMBER
    [date-1] SERIAL_NUMBER
    [date]   INSTALL_DATE (D-Mon-YY, possibly with Unicode hyphens)
    [date+1] AC_FH_AT_INSTALL    (current airframe FH at install)
    [date+2] AC_FC_AT_INSTALL
    [date+3] COMP_FH_AT_INSTALL  (component time at install)
    [date+4] COMP_FC_AT_INSTALL
    [date+5] COMP_TSN            (European decimal: 32233,55)
    [date+6] COMP_CSN

The PDF uses Unicode hyphens (U+2010) throughout — we normalise to ASCII at
read time using shared.cleanup.normalize_dashes so the row-anchor regex on
the date can match.

Must be registered ahead of Standard OCCM in the router: this file currently
hits Standard OCCM's "OCCM STATUS" signature first.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules
from shared.cleanup import normalize_dashes

NAME = "A330 Engineering Planning OCCM"
SIGNATURES = [
    "ENGINEERING & PLANNING",
]

CANONICAL_COLUMNS = [
    "ATA",
    "ZONE",
    "FIN",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "INSTALL_DATE",
    "AC_FH_AT_INSTALL",
    "AC_FC_AT_INSTALL",
    "COMP_FH_AT_INSTALL",
    "COMP_FC_AT_INSTALL",
    "COMP_TSN",
    "COMP_CSN",
]

_OVERRIDES = {
    "ATA":          {"pattern": r"^\d{2}$"},
    "ZONE":         {"pattern": r"^\d{2,4}$"},
    "FIN":          {"pattern": r"^[A-Z0-9]{3,8}$", "uppercase": True},
    "INSTALL_DATE": {"pattern": r"^\d{1,2}-[A-Za-z]{3}-\d{2,4}$"},
    # The source PDF writes literal "UNK" when the operator has no value
    # (e.g. component-time unknown on legacy installs). Accept it as a
    # sentinel rather than flagging.
    "AC_FH_AT_INSTALL":   {"pattern": r"^([\d,]+|UNK)$"},
    "AC_FC_AT_INSTALL":   {"pattern": r"^(\d+|UNK)$"},
    "COMP_FH_AT_INSTALL": {"pattern": r"^([\d,]+|UNK)$"},
    "COMP_FC_AT_INSTALL": {"pattern": r"^(\d+|UNK)$"},
    "COMP_TSN":           {"pattern": r"^([\d,]+|UNK)$"},
    "COMP_CSN":           {"pattern": r"^(\d+|UNK)$"},
}
RULES = merged_rules(_OVERRIDES)

_ATA_RE = re.compile(r"^\d{2}$")
_DATE_RE = re.compile(r"^\d{1,2}-[A-Za-z]{3}-\d{2,4}$")


def _parse_line(line: str, page_num: int) -> dict | None:
    toks = line.split()
    if len(toks) < 10:
        return None
    if not _ATA_RE.match(toks[0]):
        return None
    ata = int(toks[0])
    if not (20 <= ata <= 83):
        return None
    # Locate the INSTALL_DATE token. Must be at index >= 5 (needs at least
    # ATA, ZONE, FIN, DESCRIPTION, PN, SN before it) and leave >= 6 tokens
    # after for the trailing time matrix.
    date_idx = None
    for i in range(5, len(toks) - 5):
        if _DATE_RE.match(toks[i]):
            date_idx = i
            break
    if date_idx is None:
        return None
    if len(toks) - date_idx - 1 < 6:
        return None
    desc = " ".join(toks[3:date_idx - 2])
    return {
        "ATA":                toks[0],
        "ZONE":               toks[1],
        "FIN":                toks[2],
        "DESCRIPTION":        desc,
        "PART_NUMBER":        toks[date_idx - 2],
        "SERIAL_NUMBER":      toks[date_idx - 1],
        "INSTALL_DATE":       toks[date_idx],
        "AC_FH_AT_INSTALL":   toks[date_idx + 1],
        "AC_FC_AT_INSTALL":   toks[date_idx + 2],
        "COMP_FH_AT_INSTALL": toks[date_idx + 3],
        "COMP_FC_AT_INSTALL": toks[date_idx + 4],
        "COMP_TSN":           toks[date_idx + 5],
        "COMP_CSN":           toks[date_idx + 6],
        "_page":              page_num,
    }


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = normalize_dashes(page.extract_text() or "")
            if len(text) < 50:
                continue
            for line in text.splitlines():
                rec = _parse_line(line, page_num)
                if rec is not None:
                    records.append(rec)
    return records
