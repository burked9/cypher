"""Aircraft Rotables Report — HT side.

Same `Aircraft Rotables Report` template the OCCM-side parser handles
(`aircraft_rotables_report.py`) but with an HT-flavoured column tail:

    ATA POSITION DESCRIPTION P/N S/N MANUFACTURED INSTALLED TSN CSN
        REQUIREMENT INTERVAL TO GO EXPECTED

The OCCM variant returned 0 rows on these because the post-install
columns differ. This parser anchors on the `DD.MMM.YYYY` install date
(the one followed by two integers — TSN, CSN) and slices around it.

5 files in the corpus, all single-line per record, all clean text-layer
PDFs (no doubled-char OCR). MANUFACTURED date is optional.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "Aircraft Rotables HT"
SIGNATURES = [
    "Aircraft Rotables Report",
]
CANONICAL_COLUMNS = [
    "ATA",
    "POSITION",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "MANUFACTURED",
    "INSTALL_DATE",
    "TSN",
    "CSN",
    "REQUIREMENT",
    "INTERVAL",
    "TO_GO",
    "EXPECTED",
]
_OVERRIDES = {
    "ATA":          {"pattern": r"^\d{2}$", "int_range": (20, 83)},
    "POSITION":     {"pattern": r"^[A-Z0-9/_-]{1,12}$", "uppercase": True,
                     "allow_empty": True},
    "MANUFACTURED": {"pattern": r"^\d{2}\.[A-Za-z]{3}\.\d{4}$", "allow_empty": True},
    "INSTALL_DATE": {"pattern": r"^\d{2}\.[A-Za-z]{3}\.\d{4}$", "allow_empty": True},
    "EXPECTED":     {"pattern": r"^\d{2}\.[A-Za-z]{3}\.\d{4}$", "allow_empty": True},
    "TSN":          {"pattern": r"^\d+$", "allow_empty": True},
    "CSN":          {"pattern": r"^\d+$", "allow_empty": True},
    "REQUIREMENT":  {"allow_empty": True},
    "INTERVAL":     {"allow_empty": True},
    "TO_GO":        {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_DATE_RE = re.compile(r"^\d{2}\.[A-Za-z]{3}\.\d{4}$")
_ATA_RE = re.compile(r"^\d{2}-\d{2}$")
_HEADER_SKIP = re.compile(
    r"Aircraft Rotables Report|^Aircraft:|^ATA\s+POSITION", re.I)


def _parse_line(line: str, page_num: int) -> dict | None:
    if _HEADER_SKIP.search(line):
        return None
    toks = line.split()
    if len(toks) < 8:
        return None
    if not _ATA_RE.match(toks[0]):
        return None
    ata_int = int(toks[0].split("-")[0])
    if not (20 <= ata_int <= 83):
        return None
    # Find INSTALL date: first DD.MMM.YYYY followed by two integers.
    install_pos = None
    for i, t in enumerate(toks):
        if (_DATE_RE.match(t)
                and i + 2 < len(toks)
                and toks[i + 1].isdigit() and toks[i + 2].isdigit()):
            install_pos = i
            break
    if install_pos is None or install_pos < 4:
        return None
    # Optional MFG date immediately before INSTALL.
    has_mfg = install_pos >= 1 and _DATE_RE.match(toks[install_pos - 1])
    mfg = toks[install_pos - 1] if has_mfg else ""
    sn_idx = install_pos - 2 if has_mfg else install_pos - 1
    pn_idx = sn_idx - 1
    if pn_idx < 2:
        return None
    sn = toks[sn_idx]
    pn = toks[pn_idx]
    position = toks[1]
    description = " ".join(toks[2:pn_idx]) if pn_idx > 2 else ""
    tsn = toks[install_pos + 1]
    csn = toks[install_pos + 2]
    # Tail: REQUIREMENT  INTERVAL_VAL UNIT  TO_GO_VAL UNIT  EXPECTED_DATE
    tail = toks[install_pos + 3:]
    requirement = interval = to_go = expected = ""
    # REQUIREMENT ends at the first numeric token followed by `H` or `D`.
    req_end = None
    for i in range(len(tail) - 1):
        if re.match(r"^[0-9]+$", tail[i]) and tail[i + 1] in ("H", "D"):
            req_end = i
            break
    if req_end is not None:
        requirement = " ".join(tail[:req_end])
        rest = tail[req_end:]
        if len(rest) >= 2:
            interval = f"{rest[0]} {rest[1]}"
        if len(rest) >= 4:
            to_go = f"{rest[2]} {rest[3]}"
        # Last token (date-shaped) is EXPECTED.
        for t in reversed(rest):
            if _DATE_RE.match(t):
                expected = t
                break
    else:
        requirement = " ".join(tail)
    return {
        "ATA": toks[0].split("-")[0],
        "POSITION": position,
        "DESCRIPTION": description,
        "PART_NUMBER": pn,
        "SERIAL_NUMBER": sn,
        "MANUFACTURED": mfg,
        "INSTALL_DATE": toks[install_pos],
        "TSN": tsn,
        "CSN": csn,
        "REQUIREMENT": requirement,
        "INTERVAL": interval,
        "TO_GO": to_go,
        "EXPECTED": expected,
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
                rec = _parse_line(raw.strip(), page_num)
                if rec is not None:
                    records.append(rec)
    return records
