"""Swiss International Airlines A340 landing-gear LLP — "LDG LLP COMPLIANCE
STATUS" format. Sibling of occm_variants/swiss_a340_occm.py (same known
airframes, same source system, same character-level corruption habits), but
a distinct per-gear-assembly document: one file per MLG RH / MLG LH / CTR
Gear, each listing that assembly's LLP components.

Row format (single line, space-separated, one LIFE LIMIT requirement per
line — a component with both an hours and a cycles limit prints two rows):

    114256308 A872 (RETRACTION S019GM 11148089/9031545 lOJul.2008 70732:56 8662 LIFE LIMIT 50000 FC 8662 41338

    PART_NUMBER SERIAL_NUMBER DESCRIPTION... POS RELEASE_LABEL INST_DATE TSN CSN
    "LIFE"/"UFE" LIMIT INTERVAL UNIT TSR TOGO

Anchors (both survive the corruption below intact, unlike everything between
them): the literal token "LIMIT", and a POS token shaped like "5019GM" /
"S019GM" (always *something*+"GM", 3-6 leading alnum chars). CSN and TSN are
always the two unsplit tokens immediately left of "LIFE"/"UFE"; INTERVAL/
UNIT/TSR are the first three tokens right of "LIMIT", with TOGO soaking up
whatever's left (plain int, "HH:MM", or a "10y, 86d" duration split across
1-2 tokens depending on the row).

The source PDFs interleave characters from overlapping text runs on free-text
cells — same defect noted in swiss_a340_occm.py's docstring (0/Q, 1/l/5/S
digit-letter swaps) but worse here: whole words sometimes come out
character-shuffled (e.g. "OUTER CYLINDER (MAIN FITTING)" renders as
"O (MU ATE INR FC ITY TLI IN ND GE )R"). DESCRIPTION and RELEASE_LABEL are
captured best-effort and left for review rather than reverse-engineered;
PART_NUMBER/SERIAL_NUMBER/POS/TSN/CSN survive intact often enough to anchor
on. A DESCRIPTION cell that doesn't fit its row's line wraps onto the line
before and/or after (pdfplumber linearises it there); short non-row lines
adjacent to a row are folded into DESCRIPTION on that basis, which
occasionally pulls in a neighbouring row's RELEASE_LABEL wrap instead — left
as noise rather than guessed at.

Per-file header metadata (aircraft reg, status date, A/C total FH/FC, and
the gear assembly's own P/N/S/N/TSN/CSN) is parsed once from page 1 and
stamped on every row, mirroring ENGINE_* in vietnam_airlines.py.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.llp_variants._base import merged_rules

NAME = "Swiss A340 LDG LLP"
SIGNATURES = [
    "LDG LLP COMPLIANCE STATUS",
    "A/C total flighthours:",
]

CANONICAL_COLUMNS = [
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
    "POS",
    "RELEASE_LABEL",
    "INST_DATE",
    "TSN",
    "CSN",
    "INTERVAL",
    "UNIT",
    "TSR",
    "TOGO",
    # File-level metadata -- same on every row
    "AC_REGISTRATION",
    "STATUS_DATE",
    "AC_TOTAL_FH",
    "AC_TOTAL_FC",
    "GEAR_POSITION",
    "GEAR_PART_NUMBER",
    "GEAR_SERIAL_NUMBER",
    "GEAR_TSN",
    "GEAR_CSN",
]

_HOUR_RULE = {"pattern": r"^\d+$", "int_range": (0, 120000)}
_CYCLE_RULE = {"pattern": r"^\d+$", "int_range": (0, 55000),
               "int_range_review": (0, 30000)}
# Table TSN/TSR print "HHHHH:MM" (76181:56) alongside plain decimals
# elsewhere in the same document -- no int_range, since TSR mixes hours,
# cycles and days depending on the row's own UNIT column.
_ROW_TIME_RULE = {"pattern": r"^\d+(?:[:.]\d{1,2})?$"}

_OVERRIDES = {
    "POS": {"pattern": r"^[A-Z0-9]{3,6}GM(?:-[A-Z]{2,4})?$", "uppercase": True},
    "TSN": _ROW_TIME_RULE,
    "CSN": {"pattern": r"^\d+$"},
    "TSR": _ROW_TIME_RULE,
    "INTERVAL": {"pattern": r"^\d+$"},
    "UNIT": {"pattern": r"^[A-Za-z0-9]{2,5}$", "uppercase": True},
    "AC_REGISTRATION": {"pattern": r"^[A-Z]{1,2}-[A-Z0-9]{2,5}$", "uppercase": True},
    "AC_TOTAL_FH": _HOUR_RULE,
    "AC_TOTAL_FC": _CYCLE_RULE,
    "GEAR_PART_NUMBER": {"pattern": r"^[A-Z0-9\-/]+$", "uppercase": True},
    "GEAR_SERIAL_NUMBER": {"pattern": r"^[A-Z0-9\-/]+$", "uppercase": True},
    "GEAR_TSN": _HOUR_RULE,
    "GEAR_CSN": _CYCLE_RULE,
}
RULES = merged_rules(_OVERRIDES)

_META_COLUMNS = [
    "AC_REGISTRATION", "STATUS_DATE", "AC_TOTAL_FH", "AC_TOTAL_FC",
    "GEAR_POSITION", "GEAR_PART_NUMBER", "GEAR_SERIAL_NUMBER",
    "GEAR_TSN", "GEAR_CSN",
]

_POS_RE = re.compile(r"^[A-Z0-9]{3,6}GM(?:-[A-Z]{2,4})?$", re.IGNORECASE)
_MONTH_RE = re.compile(r"jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec", re.IGNORECASE)

_GEAR_HEADER_RE = re.compile(
    r"(MLG RH|MLG LH|CTR Gear)\s+P/N\s+(\S+)\s+S/N\s+(\S+)"
    r"\s+TSN\s+([\d ]+?)\s+CSN\s+([\d ]+)",
    re.IGNORECASE,
)
_DATE_RE = re.compile(r"[A-Z][a-z]+ \d{1,2},\s*\d{4}")
_REG_RE = re.compile(r"\bHB-[A-Z]{3}\b")
_FH_RE = re.compile(r"A/C total flighthours:\s*([\d ]+)", re.IGNORECASE)
_FC_RE = re.compile(r"A/C total flightcycles:\s*([\d ]+)", re.IGNORECASE)

_HEADER_MARKERS = (
    "SWISS", "GEAR LLP", "GEAR UP", "PART NO", "SERIAL NO", "TSN:",
    "TECHNICAL DATA", "PARTNO", "THIS IS A TRUE STATEMENT", "APPROVED BY",
    "PAGE ", "LDG LLP COMPLIANCE", "A/C TOTAL", "TYPE CERTIFICATE",
    "ACKNOWLEDGED BY", "HEAD OF ENGINEERING", "PROJECT MANAGER",
    "TECHNICAL DATE",
)


def _find_pos_idx(tokens: list[str], end: int) -> int | None:
    for i in range(2, end):
        if _POS_RE.match(tokens[i]):
            return i
    return None


def _parse_row_line(line: str) -> dict | None:
    tokens = line.split()
    if len(tokens) < 10:
        return None
    limit_idx = next((i for i, t in enumerate(tokens) if t.upper() == "LIMIT"), None)
    if limit_idx is None or limit_idx < 6:
        return None
    pos_idx = _find_pos_idx(tokens, limit_idx)
    if pos_idx is None:
        return None

    mid = tokens[pos_idx + 1:limit_idx - 1]
    if len(mid) < 2:
        return None
    tsn, csn = mid[-2], mid[-1]
    date_blob = mid[:-2]
    m_idx = next((i for i, t in enumerate(date_blob) if _MONTH_RE.search(t)), None)
    if m_idx is not None:
        release_label = " ".join(date_blob[:m_idx])
        inst_date = " ".join(date_blob[m_idx:])
    else:
        release_label, inst_date = " ".join(date_blob), ""

    tail = tokens[limit_idx + 1:]
    if len(tail) < 3:
        return None

    return {
        "PART_NUMBER": tokens[0],
        "SERIAL_NUMBER": tokens[1],
        "_desc_in_row": " ".join(tokens[2:pos_idx]),
        "POS": tokens[pos_idx],
        "RELEASE_LABEL": release_label,
        "INST_DATE": inst_date,
        "TSN": tsn,
        "CSN": csn,
        "INTERVAL": tail[0],
        "UNIT": tail[1],
        "TSR": tail[2],
        "TOGO": " ".join(tail[3:]),
    }


def _is_wrap_fragment(line: str) -> bool:
    if not line or len(line) > 30:
        return False
    u = line.upper()
    if any(marker in u for marker in _HEADER_MARKERS):
        return False
    return _parse_row_line(line) is None


def _parse_file_meta(page1_text: str) -> dict:
    flat = " ".join(page1_text.split())
    meta = {c: "" for c in _META_COLUMNS}
    m = _DATE_RE.search(flat)
    if m:
        meta["STATUS_DATE"] = m.group(0)
    m = _REG_RE.search(flat)
    if m:
        meta["AC_REGISTRATION"] = m.group(0)
    m = _FH_RE.search(flat)
    if m:
        meta["AC_TOTAL_FH"] = m.group(1).replace(" ", "")
    m = _FC_RE.search(flat)
    if m:
        meta["AC_TOTAL_FC"] = m.group(1).replace(" ", "")
    m = _GEAR_HEADER_RE.search(flat)
    if m:
        meta["GEAR_POSITION"] = m.group(1)
        meta["GEAR_PART_NUMBER"] = m.group(2)
        meta["GEAR_SERIAL_NUMBER"] = m.group(3)
        meta["GEAR_TSN"] = m.group(4).replace(" ", "")
        meta["GEAR_CSN"] = m.group(5).replace(" ", "")
    return meta


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    meta: dict = {}
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if page_num == 1:
                meta = _parse_file_meta(text)
            if len(text) < 50:
                continue
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            consumed: set[int] = set()
            for i, line in enumerate(lines):
                if i in consumed:
                    continue
                parsed = _parse_row_line(line)
                if parsed is None:
                    continue

                desc_parts = []
                if i - 1 >= 0 and (i - 1) not in consumed and _is_wrap_fragment(lines[i - 1]):
                    desc_parts.append(lines[i - 1])
                    consumed.add(i - 1)
                if parsed["_desc_in_row"]:
                    desc_parts.append(parsed["_desc_in_row"])
                if i + 1 < len(lines) and _is_wrap_fragment(lines[i + 1]):
                    desc_parts.append(lines[i + 1])
                    consumed.add(i + 1)

                rec = {c: "" for c in CANONICAL_COLUMNS}
                rec.update(meta)
                rec["PART_NUMBER"] = parsed["PART_NUMBER"]
                rec["SERIAL_NUMBER"] = parsed["SERIAL_NUMBER"]
                rec["DESCRIPTION"] = " ".join(p.rstrip("_").strip() for p in desc_parts if p.strip())
                rec["POS"] = parsed["POS"]
                rec["RELEASE_LABEL"] = parsed["RELEASE_LABEL"]
                rec["INST_DATE"] = parsed["INST_DATE"]
                rec["TSN"] = parsed["TSN"]
                rec["CSN"] = parsed["CSN"]
                rec["INTERVAL"] = parsed["INTERVAL"]
                rec["UNIT"] = parsed["UNIT"]
                rec["TSR"] = parsed["TSR"]
                rec["TOGO"] = parsed["TOGO"]
                rec["_page"] = page_num
                records.append(rec)
    return records
