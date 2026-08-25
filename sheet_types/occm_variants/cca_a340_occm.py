"""China Cargo Airlines (CCA) A340 OCCM — `OCCM COMPONETS STATUS` format.

Single-airframe sample so far (A340-313, a few hundred pages, thousands of
rows). Distinctive header is misspelled `COMPONETS` and the row layout is::

    ITEM ATA DESCRIPTION P/N S/N [LOCATION...] INSTALL_DATE [NOTES] [CERTS]

INSTALL_DATE comes in two forms: dotted `YYYY.MM.DD` or compact `YYYYMMDD`.
The sentinel `ORIGINAL` is also valid as either LOCATION or INSTALL_DATE
("factory original" — used when the part has been in-place since delivery).

LOCATION is a short positional token from a fixed lexicon (`CARGO`, `E/E`,
`FRONT`, `AFTER`, `L`, `R`, `LH`, `RH`, etc.) that can run 0-2 tokens. NOTES
and CERTS are concatenated tail content (we capture them but don't try to
split — Certs like `EASA/CAAC` aren't position-relevant).

Multiple `21`'s in a row of digits don't anchor cleanly, so we identify the
INSTALL_DATE positionally and walk back into the LOCATION lexicon.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "CCA A340 OCCM"
SIGNATURES = [
    "OCCM COMPONETS STATUS",       # the distinctive misspelling
    "ITEM ATA DESCRIPTION P/N S/N LOCATION",
]

CANONICAL_COLUMNS = [
    "ITEM",
    "ATA",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "LOCATION",
    "INSTALL_DATE",
    "NOTES",
]

_OVERRIDES = {
    "ITEM":         {"pattern": r"^\d{1,5}$"},
    "ATA":          {"pattern": r"^\d{2}$"},
    "LOCATION":     {"pattern": r"^[A-Z0-9 ./\-]{1,30}$", "uppercase": True,
                     "allow_empty": True},
    # Either dotted, compact 8-digit, or the literal sentinel ORIGINAL.
    "INSTALL_DATE": {"pattern": r"^(?:\d{4}\.\d{2}\.\d{2}|\d{8}|ORIGINAL)$"},
    "NOTES":        {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Tokens that may legitimately appear as a LOCATION value (the source PDF
# uses a small fixed vocabulary). Includes "ORIGINAL" because some rows
# write LOCATION="ORIGINAL" as a stand-in for "no slot recorded — was
# original install". Multi-token combinations like `FRONT CARGO` walk back
# one token at a time.
_LOCATION_LEXICON = {
    "CARGO", "FRONT", "AFTER", "AFT", "FORWARD", "FWD", "REAR",
    "LEFT", "RIGHT", "L", "R", "LH", "RH",
    "UPR", "UPPER", "LWR", "LOWER",
    "CTR", "CENTER", "CENTRE", "MIDDLE",
    "E/E", "EE", "CABIN", "COCKPIT", "GALLEY", "LAVATORY",
    "ZONE", "ROOM", "BAY", "STN",
    "ORIGINAL",
}

_DATE_RE = re.compile(r"^(?:\d{4}\.\d{2}\.\d{2}|\d{8}|ORIGINAL)$")
_ITEM_RE = re.compile(r"^\d{1,5}$")
_ATA_RE = re.compile(r"^\d{2}$")


def _is_location_word(tok: str) -> bool:
    return tok.upper() in _LOCATION_LEXICON


def _find_date_idx(toks: list[str], start: int = 3) -> int | None:
    # Skip leading "ORIGINAL"s — they're valid date sentinels but only the
    # LATER ORIGINAL is the INSTALL_DATE; an earlier ORIGINAL can be LOCATION.
    last = None
    for i in range(start, len(toks)):
        if _DATE_RE.match(toks[i]):
            last = i
    # We want the rightmost date-shaped token (INSTALL_DATE is followed by
    # only NOTES/CERTS, which are alphanumeric but not date-shaped).
    return last


def _parse_line(line: str, page_num: int) -> dict | None:
    toks = line.split()
    if len(toks) < 5:
        return None
    if not (_ITEM_RE.match(toks[0]) and _ATA_RE.match(toks[1])):
        return None
    ata_int = int(toks[1])
    if not (20 <= ata_int <= 83):
        return None
    date_idx = _find_date_idx(toks)
    if date_idx is None or date_idx < 4:
        return None
    # Walk back from date_idx-1 into LOCATION lexicon (up to 2 tokens).
    loc_tokens: list[str] = []
    i = date_idx - 1
    while i > 2 and _is_location_word(toks[i]) and len(loc_tokens) < 3:
        loc_tokens.insert(0, toks[i])
        i -= 1
    location = " ".join(loc_tokens)
    # toks[i] is now SN; toks[i-1] is PN.
    if i < 3:
        return None
    sn = toks[i]
    pn = toks[i - 1]
    if i - 1 < 2:
        return None
    description = " ".join(toks[2:i - 1])
    if not description:
        return None
    notes = " ".join(toks[date_idx + 1:])
    return {
        "ITEM": toks[0],
        "ATA": toks[1],
        "DESCRIPTION": description,
        "PART_NUMBER": pn,
        "SERIAL_NUMBER": sn,
        "LOCATION": location,
        "INSTALL_DATE": toks[date_idx],
        "NOTES": notes,
        "_page": page_num,
    }


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if len(text) < 60:
                continue
            for raw in text.splitlines():
                line = raw.strip()
                if not line:
                    continue
                rec = _parse_line(line, page_num)
                if rec is not None:
                    records.append(rec)
    return records
