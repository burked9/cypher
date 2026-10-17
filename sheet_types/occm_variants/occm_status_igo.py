"""OCCM Status variant — 10-column layout with POSITION and TSI/CSI.

Header line (confirmed in real-corpus triage, after dash normalisation):

    ATA PART NO. SERIAL NO. DESCRIPTION POSITION INST-DATE TSN CSN TSI CSI

Per-row layout, whitespace-tokenized::

    ATA  PN  SN  DESCRIPTION...  POSITION  INST-DATE  TSN  CSN  TSI  CSI

A typical row::

    21 1209-100 13982 PRESSURE SWITCH 19HQ 21-Dec-10 36295 17161 36295 17161

Dates appear as D-Mon-YY (after normalisation of the source's Unicode
en-dashes to ASCII hyphens). POSITION is always a single token.

The source PDFs use Unicode en-dashes (U+2010 / U+2011 / U+2012 / U+2013)
throughout — in dates, part numbers, and column headers. The extractor
normalises them via ``shared.cleanup.normalize_dashes`` before parsing,
the same approach used by ``standard_occm.py``.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "OCCM Status (IGO)"
SIGNATURES = [
    # The full column-header line as it appears in the PDF's own text layer
    # (U+2010 HYPHEN in INST‐DATE). The variant detection runs on raw
    # pdfplumber text (pre-normalisation), so the signature must carry the
    # original Unicode dash. Checked (grep across sheet_types/{occm,ht,llp}.py
    # and every existing occm_variants file): no other module's SIGNATURES
    # entry contains this phrase or is contained by it.
    "ATA PART NO. SERIAL NO. DESCRIPTION POSITION INST‐DATE TSN CSN TSI CSI",
]

CANONICAL_COLUMNS = [
    "ATA",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
    "POSITION",
    "INSTALL_DATE",
    "TSN",
    "CSN",
    "TSI",
    "CSI",
]

_NUM_RULE = {"pattern": r"^\d+(?:\.\d+)?$"}
_INT_RULE = {"pattern": r"^\d+$"}

_OVERRIDES = {
    "POSITION": {"pattern": r"^[A-Z0-9][A-Z0-9./\-]{0,15}$", "uppercase": True},
    "INSTALL_DATE": {"pattern": r"^\d{1,2}-[A-Za-z]{3}-\d{2}$"},
    "TSN": _INT_RULE,
    "CSN": _INT_RULE,
    "TSI": _INT_RULE,
    "CSI": _INT_RULE,
}
RULES = merged_rules(_OVERRIDES)

_ATA_RE = re.compile(r"^\d{2}$")
_DATE_RE = re.compile(r"^\d{1,2}-[A-Za-z]{3}-\d{2}$")
_NUM_RE = re.compile(r"^\d+$")


def _parse_line(line: str, page_num: int) -> dict | None:
    line = line.strip()
    if not line or not line[0].isdigit():
        return None
    toks = line.split()
    if len(toks) < 8:
        return None
    if not _ATA_RE.match(toks[0]):
        return None
    try:
        ata_int = int(toks[0])
    except ValueError:
        return None
    if not (20 <= ata_int <= 83):
        return None

    # Trailing layout: POSITION INST-DATE TSN CSN TSI CSI
    # The last 4 tokens must be integers (TSN CSN TSI CSI).
    for t in toks[-4:]:
        if not _NUM_RE.match(t):
            return None
    # The 5th-from-last must be a date.
    if not _DATE_RE.match(toks[-5]):
        return None
    # The 6th-from-last is POSITION.
    # ATA(1) + PN(1) + SN(1) + DESC(>=1) + POS(1) + DATE(1) + 4 nums = 10 min
    if len(toks) < 10:
        return None

    tsn, csn, tsi, csi = toks[-4:]
    install_date = toks[-5]
    position = toks[-6]
    pn = toks[1]
    sn = toks[2]
    description = " ".join(toks[3:-6])
    if not description:
        return None

    return {
        "ATA": toks[0],
        "PART_NUMBER": pn,
        "SERIAL_NUMBER": sn,
        "DESCRIPTION": description,
        "POSITION": position,
        "INSTALL_DATE": install_date,
        "TSN": tsn,
        "CSN": csn,
        "TSI": tsi,
        "CSI": csi,
        "_page": page_num,
    }


def extract(pdf_path: str) -> list[dict]:
    from shared.cleanup import normalize_dashes
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = normalize_dashes(page.extract_text() or "")
            for raw_line in text.splitlines():
                rec = _parse_line(raw_line, page_num)
                if rec is not None:
                    records.append(rec)
    return records
