"""Georgian Airways B737-76N — AIRCRAFT COMPONENT LOG.

Two of the Georgian Airways files in the corpus share this clean
single-line-per-row layout. The other three ("UNCHANGED OCCM since delivery"
and the two "STATUS OF REPLACED" variants) have column-shredded text that
needs L2 (word-coordinate) extraction — deferred.

Header structure::

    ATA DESCRIPTION PART POS SERIAL TSN CSN TSO CSO TLB PAGE
    HOURS CYCLES DATE

Row anchor: an installation date in `DD.MM.YYYY` form. Three tokens before
the date are SERIAL / TSN / CSN, except where TSN/CSN are absent (one-line
records without flight-hour history), in which case only SERIAL precedes.

PART = leftmost token containing both a dash AND a digit (this filters out
description fragments like `TRANSCEIVER-VHF` while accepting genuine PNs
like `7121-19971-01AC` and `B737-NG`). Everything between PART and SERIAL
is POSITION.
"""
from __future__ import annotations
import re

from sheet_types.occm_variants._base import merged_rules

NAME = "Georgian Airways B737"
SIGNATURES = [
    "GEORGIAN AIRWAYS",
    "AIRCRAFT COMPONENT LOG FOR A/C-REGISTRATION: 4L-TGM",
]

CANONICAL_COLUMNS = [
    "ATA",
    "DESCRIPTION",
    "PART_NUMBER",
    "POSITION",
    "SERIAL_NUMBER",
    "TSN",
    "CSN",
    "INST_DATE",
    "TSO",
    "CSO",
    "TLB",
    "PAGE_REF",
]

_OVERRIDES = {
    "ATA":       {"pattern": r"^\d{2}$"},
    "INST_DATE": {"pattern": r"^\d{1,2}\.\d{1,2}\.\d{4}$"},
    "TSN":       {"pattern": r"^\d+$", "allow_empty": True},
    "CSN":       {"pattern": r"^\d+$", "allow_empty": True},
    "TSO":       {"allow_empty": True},
    "CSO":       {"allow_empty": True},
    "TLB":       {"allow_empty": True},
    "PAGE_REF":  {"allow_empty": True},
    "POSITION":  {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_DATE_RE = re.compile(r"^\d{1,2}\.\d{1,2}\.\d{4}$")
_ATA_RE = re.compile(r"^\d{2}$")
# A PN-shape token: at least one dash AND at least one digit, alphanumeric.
_PN_RE = re.compile(r"^(?=[A-Z0-9/&\-]*\d)[A-Z0-9/&\-]*-[A-Z0-9/&\-]+$")
_NUM_RE = re.compile(r"^\d{3,6}$")
_HEADER_SKIP = re.compile(
    r"GEORGIAN\s+AIRWAYS|AIRCRAFT\s+COMPONENT|ATA\s+DESCRIPTION|"
    r"HOURS\s+CYCLES\s+DATE|ACN\s+AT|A/C\s+Total|Authorized|"
    r"^\d+\s+of\s+\d+$|^TGM\s*$", re.I)


def _parse_line(line: str, page_num: int) -> dict | None:
    if _HEADER_SKIP.search(line):
        return None
    toks = line.split()
    if len(toks) < 5:
        return None
    if not _ATA_RE.match(toks[0]):
        return None
    ata = int(toks[0])
    if not (20 <= ata <= 80):
        return None
    # Find date token.
    date_idx = None
    for i in range(2, len(toks)):
        if _DATE_RE.match(toks[i]):
            date_idx = i
            break
    if date_idx is None or date_idx < 3:
        return None
    # Pre-date: SERIAL, optionally TSN/CSN.
    if (date_idx >= 4
            and _NUM_RE.match(toks[date_idx - 1])
            and _NUM_RE.match(toks[date_idx - 2])):
        sn_idx = date_idx - 3
        tsn = toks[date_idx - 2]
        csn = toks[date_idx - 1]
    else:
        sn_idx = date_idx - 1
        tsn = ""
        csn = ""
    if sn_idx < 2:
        return None
    sn = toks[sn_idx]
    # PN: leftmost dash+digit token between desc start and sn.
    pn_idx = None
    for i in range(1, sn_idx):
        if _PN_RE.match(toks[i]):
            pn_idx = i
            break
    if pn_idx is None:
        return None
    pn = toks[pn_idx]
    desc = " ".join(toks[1:pn_idx])
    pos = " ".join(toks[pn_idx + 1:sn_idx]) if pn_idx + 1 < sn_idx else ""
    # Tail tokens after date — best-effort split into TSO/CSO/TLB/PAGE.
    tail = toks[date_idx + 1:]
    tso = cso = tlb = page_ref = ""
    # Detect the common 4-numeric pattern (TSO CSO TSO_again CSO_again PAGE)
    nums = [t for t in tail if t.isdigit()]
    if len(tail) >= 4 and all(t.isdigit() for t in tail[:4]):
        tso, cso = tail[0], tail[1]
        # tail[2], tail[3] often duplicate; tail[4] is page ref if present
        if len(tail) >= 5:
            page_ref = tail[4]
    elif len(tail) >= 2 and tail[0].isdigit() and tail[1].isdigit():
        tso, cso = tail[0], tail[1]
        if len(tail) >= 3:
            page_ref = tail[2]
    elif tail:
        # Single tail token or text — keep as page_ref / TLB.
        if tail[0].upper().startswith(("HIL", "TLB", "WO", "UNKNOWN", "C-CHECK")):
            tlb = " ".join(tail)
        else:
            page_ref = " ".join(tail)
    return {
        "ATA": toks[0],
        "DESCRIPTION": desc,
        "PART_NUMBER": pn,
        "POSITION": pos,
        "SERIAL_NUMBER": sn,
        "TSN": tsn,
        "CSN": csn,
        "INST_DATE": toks[date_idx],
        "TSO": tso,
        "CSO": cso,
        "TLB": tlb,
        "PAGE_REF": page_ref,
        "_page": page_num,
    }


def extract(pdf_path: str) -> list[dict]:
    import pdfplumber
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            for raw in text.splitlines():
                rec = _parse_line(raw.strip(), page_num)
                if rec is not None:
                    records.append(rec)
    return records
