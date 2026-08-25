"""EL AL B767-3Q8ER records-package OCCM.

Distinctive cluster of PDFs covering one airframe split into per-ATA-chapter
bundles (ARL / non-ARL / ARL_STATUS / PREV OPERAT). Pages mix three layouts:

  * cover / table-of-contents pages (skipped)
  * the bulk "Parts Remaining Fitted at Build" tabular layout (the format we parse)
  * Aircraft Readiness Log pages with a different column set (skipped — different
    semantics; not position-data in the same sense)

Main row format (post-cleanup)::

    ATA DESCRIPTION...  PART_NUMBER  SERIAL_NUMBER  DESC2... INST-DATE TSN CSN

Example raw line (note OCR damage)::

    24 ELECTRICAL POWER B430-1 CL-97153 EAM CIRCUIT, BREAKER, 10.Mar.l998 7574018 12*178

The source PDFs have systematic OCR damage:
  * `l` rendered as digit `1` inside year tokens (`10.Mar.l998` ⇒ `10.Mar.1998`)
  * `*` and `'` rendered as comma in number tokens (`12*178` / `12'178` ⇒ `12,178`)
  * Occasional broken spacing inside long numeric values
We normalise these before row parsing — the damage is consistent enough that
character-class repair recovers the bulk of rows cleanly.

Anchor: the INST-DATE token in `DD.Mon.YYYY` form. PN is the leftmost token
to its left that contains a dash. SN is the token immediately after PN.
DESC2 absorbs anything between SN and the date.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "EL AL B767-3Q8ER Records Package"
SIGNATURES = [
    "4X-EAM",
    "Parts Remaining Fitted at Build",
    "Parts Remaining fitted at Build",
]

CANONICAL_COLUMNS = [
    "ATA",
    "ATA_DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
    "INST_DATE",
    "TSN",
    "CSN",
]

_OVERRIDES = {
    "ATA":          {"pattern": r"^\d{2}$"},
    "INST_DATE":    {"pattern": r"^\d{1,2}\.[A-Za-z]{3}\.\d{4}$"},
    "TSN":          {"pattern": r"^[\d,:]+$", "allow_empty": True},
    "CSN":          {"pattern": r"^[\d,]+$", "allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# OCR cleanup: only apply within token contexts (not blanket replacement).
# Repairs we've validated on the corpus:
#   l998 → 1998         (lowercase-L for digit-1, inside a 4-digit year)
#   12*178 → 12,178      (asterisk as thousands separator)
#   12'178 → 12,178      (apostrophe as thousands separator)
_RE_LDIGIT_YEAR = re.compile(r"\bl(\d{3})\b")
_RE_STAR_COMMA = re.compile(r"(\d)\*(\d)")
_RE_QUOTE_COMMA = re.compile(r"(\d)'(\d)")


def _clean_line(line: str) -> str:
    s = line
    s = _RE_LDIGIT_YEAR.sub(r"1\1", s)
    s = _RE_STAR_COMMA.sub(r"\1,\2", s)
    s = _RE_QUOTE_COMMA.sub(r"\1,\2", s)
    # Stray apostrophe + space inside numeric tokens like " ' 7 574018"
    s = re.sub(r"(?<=\s)'\s+(\d)", r"\1", s)
    return s


_DATE_RE = re.compile(r"^\d{1,2}\.[A-Za-z]{3}\.\d{4}$")
_ATA_RE = re.compile(r"^\d{2}$")
# A PN-shape token: alphanumeric containing at least one dash AND at least
# one digit. Catches `B430-1`, `113T2201-37G`, `285T0628-1076`, `5076D100-17`.
_PN_LIKELY = re.compile(r"^(?=[A-Z0-9-]*\d)(?=[A-Z0-9-]*-)[A-Z0-9-]{4,}$")
# Header / non-data lines we skip.
_HEADER_SKIP = re.compile(
    r"ATA\s+DESCRIPTION|Aircraft\s+Readiness|MSN\s+28132|Page\s+\d|Model\s+&|"
    r"Zone\s+Nomen|Customer|INTERNATIONAL|Parts\s+Remaining", re.I)


def _parse_line(line: str, page_num: int) -> dict | None:
    if _HEADER_SKIP.search(line):
        return None
    toks = line.split()
    if len(toks) < 6:
        return None
    if not _ATA_RE.match(toks[0]):
        return None
    ata_int = int(toks[0])
    if not (20 <= ata_int <= 83):
        return None
    # Find INST-DATE token; needed as a strong anchor.
    date_idx = None
    for i in range(2, len(toks)):
        if _DATE_RE.match(toks[i]):
            date_idx = i
            break
    if date_idx is None or date_idx < 4:
        return None
    # Locate the PN-shaped token to the left of the date. We scan FORWARD from
    # toks[1] and take the first PN-shape match — that's PN, and the next
    # token is SN. Tokens before PN are ATA_DESCRIPTION, after SN until date
    # are DESCRIPTION continuation.
    pn_idx = None
    for i in range(1, date_idx - 1):
        if _PN_LIKELY.match(toks[i]):
            pn_idx = i
            break
    if pn_idx is None or pn_idx >= date_idx - 1:
        return None
    pn = toks[pn_idx]
    sn = toks[pn_idx + 1]
    ata_desc = " ".join(toks[1:pn_idx])
    desc2 = " ".join(toks[pn_idx + 2:date_idx]) if pn_idx + 2 < date_idx else ""
    # Tail: TSN and CSN — best-effort split. OCR sometimes glues these into
    # one long token (`757401812178`). When we see a single tail token of
    # 11+ digits, split at position 7 (TSN is consistently 7 digits in this
    # corpus; CSN is 4-6 digits trailing).
    tail = toks[date_idx + 1:]
    tsn = ""; csn = ""
    if len(tail) == 1 and tail[0].isdigit() and len(tail[0]) >= 11:
        tsn = tail[0][:7]
        csn = tail[0][7:]
    elif tail:
        tsn = tail[0]
        if len(tail) >= 2:
            csn = tail[1]
    return {
        "ATA": toks[0],
        "ATA_DESCRIPTION": ata_desc,
        "PART_NUMBER": pn,
        "SERIAL_NUMBER": sn,
        "DESCRIPTION": desc2,
        "INST_DATE": toks[date_idx],
        "TSN": tsn,
        "CSN": csn,
        "_page": page_num,
    }


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if len(text) < 60:
                continue
            # Skip Aircraft Readiness Log pages — different layout, not OCCM.
            if "Aircraft Readiness Log" in text[:200]:
                continue
            for raw in text.splitlines():
                line = _clean_line(raw.strip())
                if not line:
                    continue
                rec = _parse_line(line, page_num)
                if rec is not None:
                    records.append(rec)
    return records
