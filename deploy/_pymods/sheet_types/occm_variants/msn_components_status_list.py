"""MSN Components Status List — N-prefix Item / `D-Mon-YYYY` format.

Distinct from `occm_status_list` (which uses `YYYY-M-D` dates and a different
column set). Header is::

    MSN 1541 OC&CM COMPONENTS STATUS LIST Flight Hour: 39991
    Item MSN ATA Zone FIN Description Date of Install Part Number Serial number TSN CSN TSR CSR Status Cert.

Per-row layout (single line)::

    Item(N#####) MSN ATA Zone FIN  Description...  INSTALL_DATE  PN  SN  TSN  CSN  [TSR]  [CSR]  [Status]  [Cert]

Example::

    N00001 1541 21 197 11HC VALVE-PRESSURE REDUCI 17-Jul-2001 B17CA1042 797 39991.00 28485 Orig.

Trailing fields are optional — TSR/CSR appear when the part has been
through a repair/overhaul cycle; Status (`Orig.`, `INSP`, `MOD`, `REP`,
`NEW`) and Cert (`FAA`, `EASA`, `JAA`) likewise.

Must be registered ahead of `occm_status_list` since the substring
`COMPONENTS STATUS LIST` matches both.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "MSN Components Status List"
SIGNATURES = [
    "OC&CM COMPONENTS STATUS LIST",
    "Item MSN ATA Zone FIN Description",
]

CANONICAL_COLUMNS = [
    "ITEM",
    "MSN",
    "ATA",
    "ZONE",
    "FIN",
    "DESCRIPTION",
    "INSTALL_DATE",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "TSN",
    "CSN",
    "TSR",
    "CSR",
    "STATUS",
    "CERT",
]

_OVERRIDES = {
    "ITEM":         {"pattern": r"^N\d{4,6}$"},
    "MSN":          {"pattern": r"^\d{3,6}$"},
    "ATA":          {"pattern": r"^\d{2}$"},
    "ZONE":         {"pattern": r"^\d{1,4}$", "allow_empty": True},
    "FIN":          {"pattern": r"^[A-Z0-9]{2,10}$", "uppercase": True,
                     "allow_empty": True},
    "INSTALL_DATE": {"pattern": r"^\d{1,2}-[A-Za-z]{3}-\d{2,4}$"},
    "TSN": {"pattern": r"^[\d.]+$", "allow_empty": True},
    "CSN": {"pattern": r"^\d+$",    "allow_empty": True},
    "TSR": {"pattern": r"^[\d.]+$", "allow_empty": True},
    "CSR": {"pattern": r"^\d+$",    "allow_empty": True},
    "STATUS": {"pattern": r"^[A-Z][A-Z.a-z]*$", "allow_empty": True},
    "CERT":   {"pattern": r"^[A-Z/]+$", "uppercase": True, "allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_DATE_RE = re.compile(r"^\d{1,2}-[A-Za-z]{3}-\d{2,4}$")
_ITEM_RE = re.compile(r"^N\d{4,6}$")
_INT_RE = re.compile(r"^\d+$")
_FLOAT_RE = re.compile(r"^[\d.]+$")
_CERT_VALUES = {"FAA", "EASA", "JAA", "CAAC", "CAD", "DGAC"}


def _parse_line(line: str, page_num: int) -> dict | None:
    toks = line.split()
    if len(toks) < 9:
        return None
    if not _ITEM_RE.match(toks[0]):
        return None
    # Find INSTALL_DATE token (D-Mon-YYYY anywhere mid-row).
    date_idx = next((i for i, t in enumerate(toks) if _DATE_RE.match(t)), None)
    if date_idx is None or date_idx < 5:
        return None
    if len(toks) - date_idx - 1 < 2:
        return None
    # Fixed left: ITEM, MSN, ATA, ZONE, FIN, then DESCRIPTION (variable).
    item, msn, ata, zone, fin = toks[:5]
    description = " ".join(toks[5:date_idx])
    # Tail after date: PN, SN, TSN, CSN, [TSR], [CSR], [STATUS], [CERT]
    tail = toks[date_idx + 1:]
    if len(tail) < 2:
        return None
    pn = tail[0]; sn = tail[1]
    rest = tail[2:]
    # Walk through rest collecting numeric blocks first, then optional Status/Cert.
    nums = []
    i = 0
    while i < len(rest) and (_FLOAT_RE.match(rest[i]) or _INT_RE.match(rest[i])):
        nums.append(rest[i]); i += 1
    # Status/cert are the remaining trailing tokens.
    extras = rest[i:]
    cert = ""
    status = ""
    # Cert is the LAST token if it matches a known cert authority.
    if extras and extras[-1].upper().replace(".","") in _CERT_VALUES:
        cert = extras[-1].upper()
        extras = extras[:-1]
    if extras:
        status = " ".join(extras)
    # Pad nums to 4 (TSN, CSN, TSR, CSR)
    while len(nums) < 4:
        nums.append("")
    return {
        "ITEM": item, "MSN": msn, "ATA": ata, "ZONE": zone, "FIN": fin,
        "DESCRIPTION": description,
        "INSTALL_DATE": toks[date_idx],
        "PART_NUMBER": pn, "SERIAL_NUMBER": sn,
        "TSN": nums[0], "CSN": nums[1], "TSR": nums[2], "CSR": nums[3],
        "STATUS": status, "CERT": cert,
        "_page": page_num,
    }


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if len(text) < 50:
                continue
            for raw in text.splitlines():
                line = raw.strip()
                if not line:
                    continue
                rec = _parse_line(line, page_num)
                if rec is not None:
                    records.append(rec)
    return records
