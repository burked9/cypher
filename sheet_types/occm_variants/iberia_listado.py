"""Iberia 'Listado OCCM' variant — bilingual Spanish/English OCCM.

Format header: `LISTADO DE EQUIPOS INSTALADOS EN UN AVIÓN O CONJUNTO` paired
with `LIST OF INSTALLED COMPONENTS (AC or NHA)`. Operator: Iberia (IBERIA,
L.A.E. OPERADORA).

Two sub-formats observed:

Short row (5 cols):
    `ATA LOCATION DESCRIPTION PART_NUMBER SERIAL_NUMBER`
    e.g. `21-61 10HH VALVE-BYPASS 758A0000-02 02593`

Long row (9 cols):
    `ATA LOCATION DESCRIPTION PART_NUMBER SERIAL_NUMBER
        MANUFACTURE_DATE  NHA_DATE  FH(HH:MM)  FC(INT)`
    e.g. `21-61 10HH VALVE-BYPASS 1312A0000-01 C-KMD21615301 18/01/2008
          02/01/2008 35506:13 16960`

ATA uses the `chapter-subchapter` form (`21-61`, `21-00`). The presence of
two trailing dates + `HH:MM` + integer determines whether it's the long
sub-format; otherwise the short layout applies.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "Iberia Listado OCCM"
SIGNATURES = [
    "LISTADO DE EQUIPOS INSTALADOS",
    "LIST OF INSTALLED COMPONENTS (AC or NHA)",
    "IBERIA, L.A.E. OPERADORA",
]

CANONICAL_COLUMNS = [
    "ATA",
    "LOCATION",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "MANUFACTURE_DATE",
    "NHA_DATE",
    "FH",
    "FC",
]

_OVERRIDES = {
    "ATA": {"pattern": r"^\d{2}-\d{2}$", "int_range": None},
    "LOCATION": {"pattern": r"^[A-Z0-9]{2,10}$", "uppercase": True},
    # These four columns are present only in the long-form Iberia Listado
    # sub-layout. In the short-form (5-column) layout they're genuinely
    # absent, so empty is not an extraction failure — keep the pattern check
    # for when they DO carry data.
    "MANUFACTURE_DATE": {"pattern": r"^\d{2}/\d{2}/\d{4}$", "allow_empty": True},
    "NHA_DATE":         {"pattern": r"^\d{2}/\d{2}/\d{4}$", "allow_empty": True},
    "FH": {"pattern": r"^\d+:\d{2}$|^\d+$",                  "allow_empty": True},
    "FC": {"pattern": r"^\d+$",                              "allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_ATA_RE  = re.compile(r"^\d{2}-\d{2}$")
_DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")
_FH_RE   = re.compile(r"^\d+:\d{2}$|^\d+$")
_INT_RE  = re.compile(r"^\d+$")


def _parse_line(line: str, page_num: int) -> dict | None:
    tokens = line.split()
    if len(tokens) < 5:
        return None
    if not _ATA_RE.match(tokens[0]):
        return None

    # Detect long sub-format: trailing pattern is <date> <date> <FH> <FC>
    is_long = (
        len(tokens) >= 9
        and _DATE_RE.match(tokens[-4])
        and _DATE_RE.match(tokens[-3])
        and _FH_RE.match(tokens[-2])
        and _INT_RE.match(tokens[-1])
    )

    if is_long:
        mfg_date  = tokens[-4]
        nha_date  = tokens[-3]
        fh        = tokens[-2]
        fc        = tokens[-1]
        head      = tokens[:-4]
    else:
        mfg_date = nha_date = fh = fc = ""
        head      = tokens

    # head: [ATA, LOCATION, DESCRIPTION..., PN, SN]
    if len(head) < 5:
        return None
    ata      = head[0]
    location = head[1]
    sn       = head[-1]
    pn       = head[-2]
    desc_tokens = head[2:-2]
    if not desc_tokens:
        return None
    description = " ".join(desc_tokens)

    return {
        "ATA": ata,
        "LOCATION": location,
        "DESCRIPTION": description,
        "PART_NUMBER": pn,
        "SERIAL_NUMBER": sn,
        "MANUFACTURE_DATE": mfg_date,
        "NHA_DATE": nha_date,
        "FH": fh,
        "FC": fc,
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
