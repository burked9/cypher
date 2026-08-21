"""Avianca / AVA OCCM — letter-spaced header, two row sub-shapes.

Distinctive header (always present):

    A I C R A F T: N591EL
    S E R I A L #: 2333
    M O D E L: A318-111

Two row shapes share this same header:

  1) ITEM format (the majority — 16 files in this corpus). Per-row layout::

       ITEM ATA POSITION DESCRIPTION...  PN  SN  INST_DATE  TSN  CSN

     Example:  ``2 21 30HH VALVE-BYPASS 1312B0000-01 1312B00LI001148 14-Jan-12 16277,42 18147``
     POSITION can be ``0`` (no slot recorded), ``10HH`` (FIN-like) or
     ``1002TW1`` (longer alphanumeric). TSN/CSN may be the literal sentinel
     ``UNKNOWN``. Dates are ``D-Mon-YY``.

  2) ATA-prefix format (the minority — 1 file: MSN 1612). Per-row layout::

       ATA<chapter> PN SN DESCRIPTION... INST_DATE

     Example:  ``ATA21 1303A0000-04 S1303-02382 FCV-FLOW CONTROL VALVE 05.02.2012``
     No POSITION, no TSN/CSN columns. Date is ``DD.MM.YYYY``.

Per-line dispatch decides which shape to apply. Must be registered ahead of
Standard OCCM (these files currently match its "OCCM STATUS" signature).
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "Avianca OCCM"
SIGNATURES = [
    "A I C R A F T:",   # the letter-spaced header is the cluster marker
    "A I R C R A F T:",
]

CANONICAL_COLUMNS = [
    "ITEM",
    "ATA",
    "POSITION",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "INST_DATE",
    "TSN",
    "CSN",
]

# TSN/CSN may carry the literal "UNKNOWN" sentinel where component time
# is unrecorded. Accept it as valid rather than flagging bad_format.
_OVERRIDES = {
    "ITEM":          {"pattern": r"^\d{1,5}$", "allow_empty": True},
    "ATA":           {"pattern": r"^\d{2}$"},
    "POSITION":      {"pattern": r"^[A-Z0-9./\- ]{1,15}$", "uppercase": True,
                      "allow_empty": True},
    "INST_DATE":     {"pattern": r"^(\d{1,2}-[A-Za-z]{3}-\d{2,4}|\d{2}\.\d{2}\.\d{4})$"},
    "TSN":           {"pattern": r"^([\d.,]+|UNKNOWN)$", "allow_empty": True},
    "CSN":           {"pattern": r"^(\d+|UNKNOWN)$", "allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_ITEM_DATE_RE = re.compile(r"^\d{1,2}-[A-Za-z]{3}-\d{2,4}$")
_PREFIX_DATE_RE = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")
_ATA_PREFIX_RE = re.compile(r"^ATA(\d{2})$", re.I)
_TSN_RE = re.compile(r"^([\d.,]+|UNKNOWN)$")
_CSN_RE = re.compile(r"^(\d+|UNKNOWN)$")


def _parse_item_row(toks: list[str], page_num: int) -> dict | None:
    """ITEM format: ITEM ATA POSITION DESCRIPTION... PN SN DATE TSN CSN."""
    if len(toks) < 8:
        return None
    if not (toks[0].isdigit() and toks[1].isdigit()):
        return None
    # find INST_DATE
    date_idx = next((i for i, t in enumerate(toks) if _ITEM_DATE_RE.match(t)), None)
    if date_idx is None or date_idx < 5:
        return None
    if len(toks) - date_idx - 1 < 2:
        return None
    tsn = toks[date_idx + 1]
    csn = toks[date_idx + 2]
    if not _TSN_RE.match(tsn) or not _CSN_RE.match(csn):
        return None
    sn = toks[date_idx - 1]
    pn = toks[date_idx - 2]
    item = toks[0]
    ata = toks[1]
    position = toks[2]
    description = " ".join(toks[3:date_idx - 2])
    return {
        "ITEM": item,
        "ATA": ata,
        "POSITION": position if position != "0" else "",
        "DESCRIPTION": description,
        "PART_NUMBER": pn,
        "SERIAL_NUMBER": sn,
        "INST_DATE": toks[date_idx],
        "TSN": tsn,
        "CSN": csn,
        "_page": page_num,
    }


def _parse_atapre_row(toks: list[str], page_num: int) -> dict | None:
    """ATA<chapter> PN SN DESCRIPTION... INST_DATE — no POSITION, no TSN/CSN."""
    if len(toks) < 5:
        return None
    m = _ATA_PREFIX_RE.match(toks[0])
    if not m:
        return None
    if not _PREFIX_DATE_RE.match(toks[-1]):
        return None
    ata = m.group(1)
    pn = toks[1]
    sn = toks[2]
    description = " ".join(toks[3:-1])
    return {
        "ITEM": "",
        "ATA": ata,
        "POSITION": "",
        "DESCRIPTION": description,
        "PART_NUMBER": pn,
        "SERIAL_NUMBER": sn,
        "INST_DATE": toks[-1],
        "TSN": "",
        "CSN": "",
        "_page": page_num,
    }


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if len(text) < 80:
                continue
            for raw in text.splitlines():
                line = raw.strip()
                if not line:
                    continue
                toks = line.split()
                if not toks:
                    continue
                # Try both shapes; first match wins.
                rec = _parse_item_row(toks, page_num) or _parse_atapre_row(toks, page_num)
                if rec is not None:
                    records.append(rec)
    return records
