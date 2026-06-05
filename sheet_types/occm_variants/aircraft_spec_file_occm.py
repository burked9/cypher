"""Aircraft Specification File / OCCM List — AMOS-family export, distinct layout.

Header::

    AIRCRAFT SPECIFICATION FILE
    Airbus A330-223 EI-GFF MSN 0469 OCCM List
    ...
    ATA  ATA-Description  Part No  Serial No  Description  Pos.  Inst-Date  TSN  CSN

Row shapes:
  * Section-start row carries the ATA chapter + ATA description, then the
    component:  ``21 AIR CONDITIONING GEN 11469-00 492647 HEATER UNIT - FAN 431HC 06.04.2016 72415:33 9648``
  * Continuation rows omit ATA/ATA-Description and begin at the part number:
    ``120D2 1058 INDICATR 215HG 09.04.2002 79298:39 10463``

ATA forward-fills from the most recent section-start row.

Anchored on the right: every data row ends ``… POS INST_DATE TSN CSN`` where
INST_DATE is ``DD.MM.YYYY``, TSN is ``HHHHH:MM[:SS]`` and CSN is an integer.
Left of POS: optional ATA + ATA-Description, then PN, SN, free-text Description.

Distinct from the main AMOS variant (no RELEASE_LABEL column, `DD.MM.YYYY`
dates rather than `DD.Mon.YYYY`), so it gets its own module and must be
checked *before* AMOS in the router.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.llp_variants._base import merged_rules  # shared rule merger

NAME = "Aircraft Spec File OCCM"
SIGNATURES = [
    "AIRCRAFT SPECIFICATION FILE",
]

CANONICAL_COLUMNS = [
    "ATA",
    "ATA_DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
    "POS",
    "INST_DATE",
    "TSN",
    "CSN",
]

# Cycles capped per the engine/airframe rule used elsewhere (0..55000 hard,
# review band over 30000). TSN here is an hours:min string, left unranged.
_CYCLE_RULE = {"pattern": r"^\d+$", "int_range": (0, 55000),
               "int_range_review": (0, 30000)}
_OVERRIDES = {
    "ATA":       {"pattern": r"^\d{2}$"},
    "INST_DATE": {"pattern": r"^\d{2}\.\d{2}\.\d{4}$"},
    "TSN":       {"pattern": r"^\d+:\d{2}(?::\d{2})?$"},
    "CSN":       _CYCLE_RULE,
    "POS":       {"pattern": r"^[A-Z0-9]{2,8}$", "uppercase": True},
}
RULES = merged_rules(_OVERRIDES)

_DATE_RE = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")
_TSN_RE = re.compile(r"^\d+:\d{2}(?::\d{2})?$")
_INT_RE = re.compile(r"^\d+$")
_ATA_RE = re.compile(r"^\d{1,2}$")
_HAS_DIGIT = re.compile(r"\d")


def _parse_left(left: list[str]) -> tuple[str, str, str, str, str]:
    """Return (ata, ata_desc, pn, sn, description) from the tokens left of POS."""
    ata = ata_desc = ""
    i = 0
    # Optional leading ATA chapter (1-2 digits)
    if left and _ATA_RE.match(left[0]):
        ata = left[0]
        i = 1
        # ATA description = run of pure-alpha tokens before the first PN-ish token
        desc_toks = []
        while i < len(left) and not _HAS_DIGIT.search(left[i]):
            desc_toks.append(left[i])
            i += 1
        ata_desc = " ".join(desc_toks)
    if i >= len(left):
        return ata, ata_desc, "", "", ""
    pn = left[i]
    sn = left[i + 1] if i + 1 < len(left) else ""
    description = " ".join(left[i + 2:]) if i + 2 < len(left) else ""
    return ata, ata_desc, pn, sn, description


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    current_ata = ""
    current_ata_desc = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            for raw in text.splitlines():
                toks = raw.split()
                if len(toks) < 5:
                    continue
                # locate the INST_DATE token
                date_idx = next((k for k, t in enumerate(toks) if _DATE_RE.match(t)), None)
                if date_idx is None or date_idx < 1:
                    continue
                # need POS before date and TSN+CSN after
                if date_idx + 2 >= len(toks):
                    continue
                tsn = toks[date_idx + 1]
                csn = toks[date_idx + 2]
                if not _TSN_RE.match(tsn) or not _INT_RE.match(csn):
                    continue
                pos = toks[date_idx - 1]
                left = toks[: date_idx - 1]
                ata, ata_desc, pn, sn, desc = _parse_left(left)
                if not pn:
                    continue
                if ata:
                    current_ata = ata
                    current_ata_desc = ata_desc
                records.append({
                    "ATA": ata or current_ata,
                    "ATA_DESCRIPTION": ata_desc or current_ata_desc,
                    "PART_NUMBER": pn,
                    "SERIAL_NUMBER": sn,
                    "DESCRIPTION": desc,
                    "POS": pos,
                    "INST_DATE": toks[date_idx],
                    "TSN": tsn,
                    "CSN": csn,
                    "_page": page_num,
                })
    return records
