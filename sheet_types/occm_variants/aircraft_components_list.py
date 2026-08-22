"""Aircraft Components List OCCM — Taiwan/China "B-" registration cluster.

Confirmed on B-2368 and B-2350 (both A320-232, real-corpus triage 2026-08-22).
Page 1 header::

    MODEL : A320-232 As of Date : 2018/02/28
    REG. NO. : B-2368 HOURS : 56,735:01
    SERIAL NO. : 0895 CYCLES : 34563.00
    AIRCRAFT COMPONENTS LIST
    ATA POSITION DESCRIPTION VENDOR P/N. SERIAL NO. INST_DATE TSN CSN

The header advertises 7 row columns, but across both confirmed files (2257
rows total) SERIAL NO./INST_DATE/TSN/CSN are never once populated — every
row has only ATA, POSITION, DESCRIPTION and a trailing PART_NUMBER. Hence
CANONICAL_COLUMNS below has 4 fields, not 7; the extra header columns are
a template artifact for this operator, not live data.

Row shape (space-separated, ATA anchors the line)::

    2100 11HL CONTROLLER PRESS 20791-12AC
    2126 10HQ AEVC-AVIONICS EQUIPMENT VENTILATION C8O72M9P23U2T5EVR07

ATA is a 4-digit chapter+subchapter code (chapter = first 2 digits, e.g.
`2100`/`2126`/`2143` are all chapter 21), unlike the plain 2-digit ATA used
by most other OCCM variants. DESCRIPTION is a variable number of words
(1 to 5+ observed); PART_NUMBER is always the last token.

A third file triaged into this same header cluster, "B-2366 OCCM Final
List.pdf", turned out NOT to share this row shape (its header instead reads
`ATA LOCATION NOMENCLATURE VENDOR PART NO SERIAL NUMBER DATE-INST. REMARK`,
2-digit ATA, extra REMARK column) -- and is unparseable regardless: pdfminer
raises `AttributeError: 'PSKeyword' object has no attribute 'decode'` on
~9 of its 40 pages (a broken embedded CID font, triggered by Chinese-
language REMARK values like "无资料"), and even the pages that don't raise
decode every character to the wrong glyph (verified byte-for-byte identical
garbage across independent fresh-session reads -- not cache poisoning from
the crashing pages). That's a pdfminer/pdfplumber limitation on that
specific file, not a parsing-logic gap, so it's deliberately left out of
this variant's scope. The per-page try/except below exists solely so a
future file sharing this cluster's header but hitting the same font bug on
a handful of pages loses only those pages, not the whole document.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "Aircraft Components List"
SIGNATURES = [
    "AIRCRAFT COMPONENTS LIST",
    "ATA POSITION DESCRIPTION VENDOR P/N. SERIAL NO. INST_DATE TSN CSN",
]

CANONICAL_COLUMNS = [
    "ATA",
    "POSITION",
    "DESCRIPTION",
    "PART_NUMBER",
]

_OVERRIDES = {
    # 4-digit chapter+subchapter code (e.g. `3441` = chapter 34, subchapter
    # 41), not the 2-digit chapter the global rule expects -- widen the
    # pattern AND drop int_range (20-83 would reject every real row here).
    "ATA": {"pattern": r"^\d{4}$", "int_range": None},
    # Alphanumeric slot code, optionally hyphenated ("52-81-01") or starred
    # ("200RH*" -- confirmed in B-2350, meaning unclear, kept as-is).
    "POSITION": {"pattern": r"^[A-Z0-9][A-Z0-9\-*]{0,14}$", "uppercase": True},
}
RULES = merged_rules(_OVERRIDES)

_ATA_RE = re.compile(r"^\d{4}$")


def _parse_row(tokens: list[str], page_num: int) -> dict | None:
    if len(tokens) < 4:
        return None
    if not _ATA_RE.match(tokens[0]):
        return None
    chapter = int(tokens[0][:2])
    if not (20 <= chapter <= 99):
        return None
    description = " ".join(tokens[2:-1])
    if not description:
        return None
    return {
        "ATA": tokens[0],
        "POSITION": tokens[1],
        "DESCRIPTION": description,
        "PART_NUMBER": tokens[-1],
        "_page": page_num,
    }


def extract(pdf_path: str) -> list[dict]:
    from shared.cleanup import normalize_dashes
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            try:
                text = normalize_dashes(page.extract_text() or "")
            except Exception:
                # See module docstring -- a broken embedded CID font on some
                # source files crashes pdfminer on specific pages. Skip just
                # that page rather than losing the whole document.
                continue
            if len(text) < 40:
                continue
            for line in text.splitlines():
                rec = _parse_row(line.split(), page_num)
                if rec is not None:
                    records.append(rec)
    return records
