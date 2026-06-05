"""SE-DOR-style B737 OCCM — `Component Inventory List` multi-line format.

5 files in this corpus covering 2 airframes (SE-DOR MSN 28305 + LN-RRC MSN
28300, both B737-600). Each logical row is split across THREE physical lines
because the source PDF has an IPC-style two-row table per record::

    IPC Ref  Description  Pos  Level  Part  Installed Date  NH Part
    21-21-51-06 CHECK VALVE-CONDITIONED AIR - LH  LH  2  123268-1-1  2008-02-12  B737-600
    Serial NH Serial
    7407  28305

Parsing strategy:
  1. Find a line whose first token matches the IPC-Ref pattern
     (``\\d{2}-\\d{2}(-\\d{1,3}){1,4}``). That's the "data line".
  2. The data line ends ``... LEVEL PART INSTALL_DATE NH_PART`` (anchored on
     the YYYY-MM-DD date second-to-last).
  3. The next non-empty line is the literal label ``Serial NH Serial`` (skip).
  4. The line after that carries two tokens: ``Part-SN  NH-SN``.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "SE-DOR B737 OCCM"
SIGNATURES = [
    "B737-600 Part: B737-600 Tail No:",
    # Title-page cover of the all-areas variant
    "Component Inventory List",
]

CANONICAL_COLUMNS = [
    "IPC_REF",
    "DESCRIPTION",
    "POS",
    "LEVEL",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "INSTALL_DATE",
    "NH_PART",
    "NH_SERIAL",
]

_OVERRIDES = {
    "IPC_REF":      {"pattern": r"^\d{2}-\d{2}(?:-\d{1,3}){0,4}$"},
    "POS":          {"pattern": r"^[A-Z0-9./\-]{1,8}$", "uppercase": True,
                     "allow_empty": True},
    "LEVEL":        {"pattern": r"^\d{1,2}$", "allow_empty": True},
    "INSTALL_DATE": {"pattern": r"^\d{4}-\d{2}-\d{2}$"},
    "NH_PART":      {"allow_empty": True},
    "NH_SERIAL":    {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_IPC_REF_RE = re.compile(r"^\d{2}-\d{2}(?:-\d{1,3}){0,4}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_LEVEL_RE = re.compile(r"^\d{1,2}$")
_POS_LIKE = re.compile(r"^[A-Z0-9./\-]{1,8}$")
_SERIAL_LABEL_RE = re.compile(r"^Serial\s+NH\s+Serial\s*$", re.I)
# Tokens that hint a description is wrapping over `Pos` (the source PDF
# sometimes ends descriptions in "- LH" / "- RH" alongside a separate POS
# token — we keep both).
_DESC_TAIL_HINTS = {"LH", "RH", "L/H", "R/H"}


def _parse_data_line(toks: list[str]) -> dict | None:
    """Parse a row's data tokens. Returns dict missing SERIAL_NUMBER/NH_SERIAL —
    those are filled by the caller from the following label-pair line."""
    if len(toks) < 5 or not _IPC_REF_RE.match(toks[0]):
        return None
    # Walk back from the end.
    nh_part = toks[-1]
    if not _DATE_RE.match(toks[-2]):
        return None
    install_date = toks[-2]
    pn = toks[-3]
    if not _LEVEL_RE.match(toks[-4]):
        return None
    level = toks[-4]
    # Optional POS at toks[-5] if it matches a short alphanumeric.
    pos = ""
    desc_end = -4   # exclusive: tokens before this are description
    if len(toks) >= 6 and _POS_LIKE.match(toks[-5]) and len(toks[-5]) <= 4:
        pos = toks[-5]
        desc_end = -5
    description = " ".join(toks[1:desc_end])
    return {
        "IPC_REF": toks[0],
        "DESCRIPTION": description,
        "POS": pos,
        "LEVEL": level,
        "PART_NUMBER": pn,
        "INSTALL_DATE": install_date,
        "NH_PART": nh_part,
        # SERIAL_NUMBER + NH_SERIAL added later
    }


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        # Collect all lines across all pages with their page numbers so we
        # can stitch the 3-line records that occasionally straddle pages.
        all_lines: list[tuple[int, str]] = []
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            for raw in text.splitlines():
                s = raw.strip()
                if s:
                    all_lines.append((page_num, s))

    pending: dict | None = None    # data line parsed, awaiting serial pair
    seen_label = False             # have we seen "Serial NH Serial" since the data line?
    for page_num, line in all_lines:
        toks = line.split()
        # 1) Try to parse as a new data line.
        rec = _parse_data_line(toks)
        if rec is not None:
            # If a previous record is still pending its serial pair, commit
            # it without serials so the row isn't lost.
            if pending is not None:
                pending.setdefault("SERIAL_NUMBER", "")
                pending.setdefault("NH_SERIAL", "")
                records.append(pending)
            rec["_page"] = page_num
            pending = rec
            seen_label = False
            continue
        # 2) Is this the literal "Serial NH Serial" label?
        if pending is not None and _SERIAL_LABEL_RE.match(line):
            seen_label = True
            continue
        # 3) After the label, the very next 2-token line carries the serial pair.
        if pending is not None and seen_label and len(toks) == 2:
            pending["SERIAL_NUMBER"] = toks[0]
            pending["NH_SERIAL"] = toks[1]
            pending["_page"] = page_num
            records.append(pending)
            pending = None
            seen_label = False
            continue
        # Anything else: continuation noise, ignore.

    # Don't lose a final un-paired record.
    if pending is not None:
        pending.setdefault("SERIAL_NUMBER", "")
        pending.setdefault("NH_SERIAL", "")
        records.append(pending)
    return records
