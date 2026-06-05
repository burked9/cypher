"""Aircraft Inventory Report (MM_504) variant.

Format produced by an MRO maintenance system used by multiple operators
(Atlasjet, Atlasglobal, Red Wings, and others). The internal form code is
`MM_504` and an `MCM-RW-1.3-5` form ID often appears in the header.

Layout (one row per line, space-separated):
    ATA  PART_NUMBER  SERIAL_NUMBER  DESCRIPTION...  POSITION  INSTALL_DATE
    [COMMENT  COUNTER  FH  FC  DAYS]

The trailing block (COMMENT, COUNTER, FH, FC, DAYS) is optional — many
historical rows have only the install date with no usage data.

Two date formats observed across operators:
    `DD-MMM-YY`   e.g. `15-OCT-15`
    `DD-MM-YYYY`  e.g. `27-04-2018`

The Red Wings sub-format (two date columns + continuation rows) is not
handled by this variant yet — those rows will simply not match the regex
and be skipped. A future refinement can add a second variant for it once
the format is understood.

Anchor: the install date (matches either pattern). Walk back from the date
to identify POSITION (last token before date) → DESCRIPTION (lazy span) →
SN → PN → ATA at the start.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "Aircraft Inventory Report (MM_504)"
SIGNATURES = [
    "MM_504",
    "AIRCRAFT INVENTORY REPORT",
    "MCM-RW-1.3-5",
]

CANONICAL_COLUMNS = [
    "ATA",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
    "POSITION",
    "INSTALL_DATE",
    "COMMENT",
    "COUNTER",
    "FH",
    "FC",
    "DAYS",
]

_OVERRIDES = {
    # ATA in this variant is mixed — sometimes 2-digit chapter, sometimes
    # 4-digit chapter+subchapter, sometimes alphanumeric (e.g. `2100M96P05`).
    "ATA":     {"pattern": r"^[A-Z0-9]{2,12}$", "int_range": None, "uppercase": True},
    "POSITION": {"pattern": r"^[A-Z0-9#:>\-/]+$", "uppercase": True},
    "INSTALL_DATE": {"pattern": r"^(?:\d{2}-[A-Z]{3}-\d{2}|\d{2}-\d{2}-\d{4})$"},
    # Numeric fields are optional and can be HH:MM-format hours
}
RULES = merged_rules(_OVERRIDES)

# Either DD-MMM-YY or DD-MM-YYYY
_DATE_RE = re.compile(r"^(?:\d{2}-[A-Za-z]{3}-\d{2}|\d{2}-\d{2}-\d{4})$")
_ATA_LIKE_RE = re.compile(r"^[A-Z0-9]{2,12}$")


def _parse_line(line: str, page_num: int) -> dict | None:
    tokens = line.split()
    if len(tokens) < 6:
        return None
    if not _ATA_LIKE_RE.match(tokens[0].upper()):
        return None

    # Find the install date — the first token matching either date shape
    date_idx = None
    for i, t in enumerate(tokens):
        if _DATE_RE.match(t):
            date_idx = i
            break
    if date_idx is None or date_idx < 4:  # need ATA + PN + SN + at least 1 description + POS
        return None

    install_date = tokens[date_idx]

    # Before date: ATA / PN / SN / DESCRIPTION... / POSITION
    head = tokens[:date_idx]
    if len(head) < 5:
        return None
    ata = head[0]
    pn = head[1]
    sn = head[2]
    position = head[-1]
    desc_tokens = head[3:-1]
    if not desc_tokens:
        return None
    description = " ".join(desc_tokens)

    # After date: optional COMMENT then up to 4 numeric values
    after = tokens[date_idx + 1:]
    comment = ""
    counter = fh = fc = days = ""
    # If the first token after the date isn't numeric/colon, treat it as COMMENT
    idx = 0
    if after and not re.match(r"^[\d:.]", after[0]):
        # COMMENT can be a single word like "Overhaul", "New", "Inspection",
        # "Installation". Multi-word comments are rare; if needed, take all
        # leading non-numeric tokens.
        comment_tokens = []
        while idx < len(after) and not re.match(r"^[\d:.]", after[idx]):
            comment_tokens.append(after[idx])
            idx += 1
        comment = " ".join(comment_tokens)
    rest = after[idx:]
    # The remaining tokens are COUNTER / FH / FC / DAYS in some order — the
    # exact column count varies. We just record the first 4 numeric-ish tokens
    # left-to-right.
    nums = [t for t in rest if re.match(r"^[\d:.]+$", t)][:4]
    while len(nums) < 4:
        nums.append("")
    counter, fh, fc, days = nums

    return {
        "ATA": ata,
        "PART_NUMBER": pn,
        "SERIAL_NUMBER": sn,
        "DESCRIPTION": description,
        "POSITION": position,
        "INSTALL_DATE": install_date,
        "COMMENT": comment,
        "COUNTER": counter,
        "FH": fh,
        "FC": fc,
        "DAYS": days,
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
