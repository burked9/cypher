"""B777 Annex 8 OCCM — single-airframe Boeing 777 records-package inventory.

Single airframe seen (9V-SQJ, MSN 30875 — Singapore Airlines). Header is::

    Annex 8
    489 9V-SQJ List dd 28 Mar 18
    No  Part No  Equipment  Description  Functional Location

Each row is one line with four logical fields. The Functional Location is the
unambiguous right-anchor — always the form ``<REG>/<ATA-subgroup>/<seq>/<pos>``
e.g. ``9V-SQJ/2125/01/AFT``. ATA chapter and POSITION can both be derived from
it (the 4-digit subgroup's first two digits are the ATA chapter).

Example row::

    1 4100945B B777 HS PBH: FAN - MIXED FLOW 7.5" DIA 9V-SQJ/2125/01/AFT

Parsed as:
    ITEM=1, PART_NUMBER=4100945B,
    DESCRIPTION='B777 HS PBH: FAN - MIXED FLOW 7.5" DIA',
    FUNCTIONAL_LOCATION=9V-SQJ/2125/01/AFT, ATA=21, POSITION=AFT

Registered ahead of generic variants since the signature is highly specific
and won't collide.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "B777 Annex 8 OCCM"
SIGNATURES = [
    "Equipment Description Functional Location",
]

CANONICAL_COLUMNS = [
    "ITEM",
    "PART_NUMBER",
    "DESCRIPTION",
    "ATA",
    "POSITION",
    "FUNCTIONAL_LOCATION",
]

_OVERRIDES = {
    "ITEM":                {"pattern": r"^\d{1,5}$"},
    "ATA":                 {"pattern": r"^\d{2}$"},
    "POSITION":            {"pattern": r"^[A-Z0-9]{1,12}$", "uppercase": True,
                            "allow_empty": True},
    "FUNCTIONAL_LOCATION": {"pattern": r"^[A-Z0-9\-]+/\d{4}/\d{2}/[A-Z0-9]+$",
                            "uppercase": True},
}
RULES = merged_rules(_OVERRIDES)

# Functional Location: <REG>/<4-digit ATA group>/<2-digit seq>/<position token>
_FUNC_LOC_RE = re.compile(r"^[A-Z0-9\-]+/(\d{4})/\d{2}/([A-Z0-9]+)$")
_ITEM_RE = re.compile(r"^\d{1,5}$")


def _parse_line(line: str, page_num: int) -> dict | None:
    toks = line.split()
    if len(toks) < 4:
        return None
    # Must end with a functional-location token
    fl_match = _FUNC_LOC_RE.match(toks[-1].upper())
    if not fl_match:
        return None
    # Must start with an item number
    if not _ITEM_RE.match(toks[0]):
        return None
    item = toks[0]
    pn = toks[1]
    description = " ".join(toks[2:-1])
    if not description:
        return None
    func_loc = toks[-1].upper()
    # ATA chapter = first two digits of the 4-digit ATA subgroup
    ata_subgroup = fl_match.group(1)        # e.g. "2125"
    ata = ata_subgroup[:2]                  # "21"
    position = fl_match.group(2)            # "AFT", "L", "R", etc.
    return {
        "ITEM": item,
        "PART_NUMBER": pn,
        "DESCRIPTION": description,
        "ATA": ata,
        "POSITION": position,
        "FUNCTIONAL_LOCATION": func_loc,
        "_page": page_num,
    }


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if len(text) < 30:
                continue
            for raw in text.splitlines():
                line = raw.strip()
                if not line:
                    continue
                rec = _parse_line(line, page_num)
                if rec is not None:
                    records.append(rec)
    return records
