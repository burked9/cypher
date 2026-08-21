"""Cathay-style OCCM variant — 13-column tabular OCCM with 6-metric time matrix.

First seen on Cathay Pacific (CX) A330 documents (B-HLD, B-HLC, B-HLB).
Named for the dominant operator pattern; rename if other carriers using the
same format show up.

Format header:
    ATA Description Equip ID Part Number Serial Number Location
        TSN TSO TSR CSN CSO CSR Install Date

Per-row layout (one line, space-separated):
    ATA DESCRIPTION... EQUIP_ID PART_NUMBER SERIAL_NUMBER [LOCATION]
    TSN_H:M TSO_H:M TSR_H:M CSN_INT CSO_INT CSR_INT INSTALL_DATE

The 6-metric block is unambiguous: 3 HH:MM-style tokens (TSN/TSO/TSR) then
3 integer tokens (CSN/CSO/CSR), then a `DD/MM/YYYY` date. We anchor on the
trailing 7 tokens (6 metrics + date) and walk back.

LOCATION is optional — sometimes present (`LH`, `RH`, `1`, `2`, `AFT`, `FWD`)
and sometimes absent. Heuristic: when the second-to-last head token has a
hyphen (= part number shape), the last head token is SERIAL_NUMBER, not
LOCATION. Otherwise the last head token is treated as LOCATION.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "Cathay OCCM"
SIGNATURES = [
    "ATA Description Equip ID Part Number Serial Number Location TSN TSO TSR",
    "TSN TSO TSR CSN CSO CSR Install Date",
]

CANONICAL_COLUMNS = [
    "ATA",
    "DESCRIPTION",
    "EQUIP_ID",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "LOCATION",
    "TSN", "TSO", "TSR",
    "CSN", "CSO", "CSR",
    "INSTALL_DATE",
]

_OVERRIDES = {
    "EQUIP_ID": {"pattern": r"^[A-Z0-9]{2,10}$", "uppercase": True},
    # LOCATION is optional in the Cathay format (sometimes present, sometimes
    # absent — see module docstring). Don't flag empty as failure.
    "LOCATION": {"pattern": r"^[A-Z0-9]{1,5}$", "uppercase": True, "allow_empty": True},
    # Two date forms seen in this format: `DD/MM/YYYY` and `D-Mon-YYYY`.
    # B-HLC is 100% the hyphen-month-name form; B-HLB mixes both.
    "INSTALL_DATE": {"pattern": r"^(\d{1,2}/\d{2}/\d{4}|\d{1,2}-[A-Za-z]{3}-\d{2,4})$"},
    "TSN": {"pattern": r"^\d+:\d{2}$"},
    "TSO": {"pattern": r"^\d+:\d{2}$"},
    "TSR": {"pattern": r"^\d+:\d{2}$"},
    "CSN": {"pattern": r"^\d+$"},
    "CSO": {"pattern": r"^\d+$"},
    "CSR": {"pattern": r"^\d+$"},
}
RULES = merged_rules(_OVERRIDES)

_ATA_RE = re.compile(r"^\d{2}$")
_HH_MM_RE = re.compile(r"^\d+:\d{2}$")
_INT_RE = re.compile(r"^\d+$")
_DATE_RE = re.compile(r"^(?:\d{1,2}/\d{2}/\d{4}|\d{1,2}-[A-Za-z]{3}-\d{2,4})$")


def _looks_like_pn(token: str) -> bool:
    """PNs typically contain a hyphen; SNs typically don't."""
    return "-" in token


def _looks_like_location(token: str) -> bool:
    return 1 <= len(token) <= 5 and bool(re.match(r"^[A-Z0-9]+$", token))


def _parse_line(line: str, page_num: int) -> dict | None:
    tokens = line.split()
    if len(tokens) < 11:
        return None
    if not _ATA_RE.match(tokens[0]):
        return None
    ata_int = int(tokens[0])
    if not (20 <= ata_int <= 83):
        return None

    # Trailing 7: 3×HH:MM, 3×int, 1×date
    if not _DATE_RE.match(tokens[-1]):
        return None
    if not all(_INT_RE.match(t) for t in tokens[-4:-1]):
        return None
    if not all(_HH_MM_RE.match(t) for t in tokens[-7:-4]):
        return None

    tsn, tso, tsr = tokens[-7:-4]
    csn, cso, csr = tokens[-4:-1]
    install_date = tokens[-1]

    head = tokens[:-7]
    if len(head) < 5:
        return None

    # Determine whether the last head token is LOCATION or SN.
    last = head[-1]
    penult = head[-2]
    if _looks_like_location(last) and not _looks_like_pn(penult) and len(penult) >= 3:
        location = last
        sn = penult
        pn = head[-3]
        equip_id = head[-4]
        desc_end = -4
    else:
        location = ""
        sn = last
        pn = penult
        equip_id = head[-3]
        desc_end = -3

    desc_tokens = head[1:desc_end]
    if not desc_tokens:
        return None
    description = " ".join(desc_tokens)

    return {
        "ATA": tokens[0],
        "DESCRIPTION": description,
        "EQUIP_ID": equip_id,
        "PART_NUMBER": pn,
        "SERIAL_NUMBER": sn,
        "LOCATION": location,
        "TSN": tsn, "TSO": tso, "TSR": tsr,
        "CSN": csn, "CSO": cso, "CSR": csr,
        "INSTALL_DATE": install_date,
        "_page": page_num,
    }


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if len(text) < 100:
                continue
            for raw in text.splitlines():
                line = raw.strip()
                if not line:
                    continue
                rec = _parse_line(line, page_num)
                if rec is not None:
                    records.append(rec)
    return records
