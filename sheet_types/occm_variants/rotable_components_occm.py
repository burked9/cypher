"""ROTABLE COMPONENTS — FlyerTech-generated card-style OCCM inventory.

Parser strategy
---------------
Each component is a multi-line "card" block rather than a single table row.
A card begins with a ``Part No. :`` line and contains labelled fields spread
across 4-7 lines:

Simple form (known TSN/CSN)::

    Part No. : <PN>         TSN : <TSN>      Date : <DATE>
    Serial No. : <SN>       CSN : <CSN>      Hours : <HOURS>
    <ATA>
    Description : <DESC>                     Cycles : <CYCLES>
    GRN : <GRN>

Extended form (unknown TSN/CSN, with since-service-visit counters)::

    Part No. : <PN>         TSN : UKN        Date : <DATE>
    Serial No. : <SN>       TSSV : <TSSV>    Hours : <HOURS>
    <ATA>
    CSN : UKN
    Description : <DESC>                     Cycles : <CYCLES>
    CSSV : <CSSV>
    GRN : <GRN>

Description text may wrap onto the next line when long.

The page header repeats on every page (Registration, MSN, Model, ATA column
header) and a footer line carries the date + page number.
"""
from __future__ import annotations

import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "Rotable Components OCCM"
SIGNATURES = [
    "ROTABLE COMPONENTS",
    "Report Produced by FlyerTech",
    "Report produced by FlyerTech",
]

CANONICAL_COLUMNS = [
    "ATA",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
    "GRN",
    "INST_DATE",
    "TSN",
    "CSN",
    "TSSV",
    "CSSV",
    "AC_HOURS",
    "AC_CYCLES",
]

_OVERRIDES = {
    "ATA": {"pattern": r"^\d{2}(?:-\d{2}){0,2}$", "int_range": None},
    "GRN": {"allow_empty": True},
    "INST_DATE": {"pattern": r"^\d{2}-[A-Za-z]{3}-\d{2}$"},
    # Time values may be hours:minutes (e.g. "48,039:40"), plain integers,
    # or "UKN".
    "TSN": {"allow_empty": True},
    "CSN": {"allow_empty": True},
    "TSSV": {"allow_empty": True},
    "CSSV": {"allow_empty": True},
    "AC_HOURS": {"allow_empty": True},
    "AC_CYCLES": {"allow_empty": True},
    "DESCRIPTION": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# --- regexes ----------------------------------------------------------------

_PART_NO_RE = re.compile(
    r"^Part\s+No\.\s*:\s*(?P<pn>\S+)"
    r"\s+TSN\s*:\s*(?P<tsn>\S+(?:\s*\S+)?)"
    r"\s+Date\s*:\s*(?P<date>\S+)",
    re.IGNORECASE,
)

_SERIAL_CSN_RE = re.compile(
    r"^Serial\s+No\.\s*:\s*(?P<sn>\S+)"
    r"\s+CSN\s*:\s*(?P<csn>\S+(?:,\S+)?)"
    r"\s+Hours\s*:\s*(?P<hours>\S+)",
    re.IGNORECASE,
)

_SERIAL_TSSV_RE = re.compile(
    r"^Serial\s+No\.\s*:\s*(?P<sn>\S+)"
    r"\s+TSSV\s*:\s*(?P<tssv>\S+(?:,\S+)?)"
    r"\s+Hours\s*:\s*(?P<hours>\S+)",
    re.IGNORECASE,
)

_ATA_LINE_RE = re.compile(r"^\d{2}(?:-\d{2}){0,2}$")

_CSN_LINE_RE = re.compile(r"^CSN\s*:\s*(?P<csn>\S+)", re.IGNORECASE)

_DESC_LINE_RE = re.compile(
    r"^Description\s*:\s*(?P<desc>.+?)(?:\s+Cycles\s*:\s*(?P<cycles>\S+(?:,\S+)?))?$",
    re.IGNORECASE,
)

_CSSV_LINE_RE = re.compile(r"^CSSV\s*:\s*(?P<cssv>\S+)", re.IGNORECASE)

_GRN_LINE_RE = re.compile(r"^GRN\s*:\s*(?P<grn>.*)", re.IGNORECASE)

# Header / footer lines to skip
_HEADER_RE = re.compile(
    r"^(Registration\s*:|MSN\s*:|Model\s*:|ATA\s+Details|ROTABLE\s+COMPONENTS)",
    re.IGNORECASE,
)
_FOOTER_RE = re.compile(
    r"\bPage\s+\d+\s*$",
    re.IGNORECASE,
)


def _is_header_or_footer(line: str) -> bool:
    return bool(_HEADER_RE.match(line)) or bool(_FOOTER_RE.search(line))


def _emit(card: dict, page_num: int, records: list[dict]) -> None:
    """Validate and append a finished card to records."""
    if not card.get("PART_NUMBER") or not card.get("SERIAL_NUMBER"):
        return
    card.setdefault("ATA", "")
    card.setdefault("DESCRIPTION", "")
    card.setdefault("GRN", "")
    card.setdefault("INST_DATE", "")
    card.setdefault("TSN", "")
    card.setdefault("CSN", "")
    card.setdefault("TSSV", "")
    card.setdefault("CSSV", "")
    card.setdefault("AC_HOURS", "")
    card.setdefault("AC_CYCLES", "")
    card["_page"] = page_num
    records.append(card)


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []

    # Gather all lines across pages
    all_lines: list[tuple[int, str]] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            for raw in text.splitlines():
                s = raw.strip()
                if s:
                    all_lines.append((page_num, s))

    card: dict = {}
    card_page = 1
    current_ata = ""
    expecting_desc_wrap = False

    for page_num, line in all_lines:
        if _is_header_or_footer(line):
            continue

        # --- Part No. line (start of new card) ---
        m = _PART_NO_RE.match(line)
        if m:
            # Emit previous card
            if card:
                _emit(card, card_page, records)
            card = {
                "PART_NUMBER": m.group("pn"),
                "TSN": m.group("tsn"),
                "INST_DATE": m.group("date"),
            }
            card_page = page_num
            expecting_desc_wrap = False
            continue

        if not card:
            # Not inside a card yet — could be an ATA line between cards
            if _ATA_LINE_RE.match(line):
                current_ata = line
            continue

        # --- Serial No. line (CSN variant) ---
        m = _SERIAL_CSN_RE.match(line)
        if m:
            card["SERIAL_NUMBER"] = m.group("sn")
            card["CSN"] = m.group("csn")
            card["AC_HOURS"] = m.group("hours")
            expecting_desc_wrap = False
            continue

        # --- Serial No. line (TSSV variant) ---
        m = _SERIAL_TSSV_RE.match(line)
        if m:
            card["SERIAL_NUMBER"] = m.group("sn")
            card["TSSV"] = m.group("tssv")
            card["AC_HOURS"] = m.group("hours")
            expecting_desc_wrap = False
            continue

        # --- Bare ATA chapter number ---
        if _ATA_LINE_RE.match(line):
            current_ata = line
            card["ATA"] = current_ata
            expecting_desc_wrap = False
            continue

        # --- Standalone CSN line (appears in TSSV variant) ---
        m = _CSN_LINE_RE.match(line)
        if m and "CSN" not in card:
            card["CSN"] = m.group("csn")
            expecting_desc_wrap = False
            continue

        # --- Description line ---
        m = _DESC_LINE_RE.match(line)
        if m:
            card["DESCRIPTION"] = m.group("desc").strip()
            if m.group("cycles"):
                card["AC_CYCLES"] = m.group("cycles")
            expecting_desc_wrap = True
            continue

        # --- CSSV line ---
        m = _CSSV_LINE_RE.match(line)
        if m:
            card["CSSV"] = m.group("cssv")
            expecting_desc_wrap = False
            continue

        # --- GRN line ---
        m = _GRN_LINE_RE.match(line)
        if m:
            card["GRN"] = m.group("grn").strip()
            expecting_desc_wrap = False
            continue

        # --- Description wrap continuation ---
        if expecting_desc_wrap and card.get("DESCRIPTION"):
            # Description wraps onto next line when long (e.g. "COMPUTER (FMGC)")
            # Must not accidentally consume ATA numbers or labelled lines
            if not any(
                pat.match(line)
                for pat in (_PART_NO_RE, _SERIAL_CSN_RE, _SERIAL_TSSV_RE,
                            _ATA_LINE_RE, _CSN_LINE_RE, _DESC_LINE_RE,
                            _CSSV_LINE_RE, _GRN_LINE_RE)
            ):
                card["DESCRIPTION"] = card["DESCRIPTION"] + " " + line.strip()
                expecting_desc_wrap = False
                continue

        expecting_desc_wrap = False

    # Emit final card
    if card:
        _emit(card, card_page, records)

    return records
