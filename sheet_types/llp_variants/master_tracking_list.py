"""Master Tracking List — an engine LLP status sheet headed "Master Tracking
List <n>" (the trailing number is a tracking-list identifier, not a fleet or
tail reference).

Single-page layout, one row per part plus an engine-level summary row at the
top. Columns (per the footer legend on the sample file):

    AuRA Sub Structure Pos  Description  P/N  SIN  IT TC TSC CSC TSB CSB
    TSA CSA  Cycles Limit  Cycles Remain  ... Category

Row grammar::

    72-31-00-01-230A HPC FWD SHAFT SAC TI <pn> ABC1234R \
        17894 11953 17894 11953 17894 11953 17894 11953 20000 8047 LLP
    └── CODE ────────┘└─ DESCRIPTION ─┘  │└── PN ───┘└ SN ───┘\
        └──────────── 8 time/cycle fields ────────────┘└LIMIT┘└REMAIN┘└CAT┘

CODE is a 5-segment ATA-zone-position code (chapter-section-subsection-
sequence-suffix, e.g. "72-31-00-01-230A"). A literal "SAC TI" marker
(observed with inconsistent spacing/hyphenation -- "SAC TI", "SACTI",
"- SAC TI", "-SACTI") separates DESCRIPTION from PART_NUMBER/SERIAL_NUMBER
and anchors the split; DESCRIPTION is everything before it, stripped of a
trailing dash. The 8 trailing time/cycle fields split cleanly and are named
per the sheet's own footer legend (TT/TC/TSC/CSC/TSB/CSB/TSA/CSA = Total
Time, Total Cycles, Time/Cycles Since C, Since B, Since A checks), followed
by CYCLES_LIMIT and CYCLES_REMAIN (numeric, or "N/A"/"n/a" for components
with no cycle-based limit -- a legitimate value, not a parse failure) and a
trailing CATEGORY_CODE ("LLP", "VLP", "ENG", ...).

pdfplumber's extract_text() reconstructs each row as one clean line (the
per-word/x-position view is badly interleaved on this layout -- columns
wrap across different line counts per row -- but extract_text()'s own
reading order sidesteps that entirely). The one artifact worth handling is
a stray lone "-" line pdfplumber occasionally emits between rows (a
wrapped-off leading dash from the following row's "- SAC TI" marker); it
carries no data and is simply skipped since it never matches the row regex.

Occasionally the PN or SIN column absorbs a spurious internal space from
kerning (e.g. a stray space splitting an otherwise-contiguous P/N); the parser
rejoins every token between the description and the serial number with no
separator to undo this, then takes the final token as SERIAL_NUMBER.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.llp_variants._base import merged_rules

NAME = "Master Tracking List"
SIGNATURES = [
    "Master Tracking List",
]

CANONICAL_COLUMNS = [
    "CODE",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "TOTAL_TIME",
    "TOTAL_CYCLES",
    "TIME_SINCE_C",
    "CYCLES_SINCE_C",
    "TIME_SINCE_B",
    "CYCLES_SINCE_B",
    "TIME_SINCE_A",
    "CYCLES_SINCE_A",
    "CYCLES_LIMIT",
    "CYCLES_REMAIN",
    "CATEGORY_CODE",
]

_TIME_CYCLE_RULE = {"pattern": r"^[\d,]+$", "int_range": (0, 60000), "allow_empty": True}
_LIMIT_RULE = {"pattern": r"^(?:[\d,]+|N/A)$", "uppercase": True, "allow_empty": True}
_OVERRIDES = {
    "CODE": {"pattern": r"^\d{2}-\d{2}-\d{2}-\d{2}-[A-Z0-9]+$", "uppercase": True},
    "TOTAL_TIME": _TIME_CYCLE_RULE,
    "TOTAL_CYCLES": _TIME_CYCLE_RULE,
    "TIME_SINCE_C": _TIME_CYCLE_RULE,
    "CYCLES_SINCE_C": _TIME_CYCLE_RULE,
    "TIME_SINCE_B": _TIME_CYCLE_RULE,
    "CYCLES_SINCE_B": _TIME_CYCLE_RULE,
    "TIME_SINCE_A": _TIME_CYCLE_RULE,
    "CYCLES_SINCE_A": _TIME_CYCLE_RULE,
    "CYCLES_LIMIT": _LIMIT_RULE,
    "CYCLES_REMAIN": _LIMIT_RULE,
    "CATEGORY_CODE": {"pattern": r"^[A-Z]{2,4}$", "uppercase": True},
}
RULES = merged_rules(_OVERRIDES)

_CODE_RE = re.compile(r"^\d{2}-\d{2}-\d{2}-\d{2}-[A-Za-z0-9]+$")
_MARKER_RE = re.compile(r"\s*-?\s*SAC\s*TI\s*", re.I)
_NUM_OR_NA = r"(?:[\d,]+|[Nn]/[Aa])"
_TRAIL_RE = re.compile(
    r"^(?P<tt>[\d,]+)\s+(?P<tc>[\d,]+)\s+(?P<tsc>[\d,]+)\s+(?P<csc>[\d,]+)\s+"
    r"(?P<tsb>[\d,]+)\s+(?P<csb>[\d,]+)\s+(?P<tsa>[\d,]+)\s+(?P<csa>[\d,]+)\s+"
    r"(?P<limit>" + _NUM_OR_NA + r")\s+(?P<remain>" + _NUM_OR_NA + r")\s+"
    r"(?P<category>\S+)$"
)


def _parse_row(line: str) -> dict | None:
    s = line.strip()
    if not s:
        return None
    first_tok, _, rest = s.partition(" ")
    if not _CODE_RE.match(first_tok):
        return None
    rest = rest.strip()
    m = _MARKER_RE.search(rest)
    if not m:
        return None
    desc = rest[: m.start()].strip(" -")
    tail = rest[m.end():].strip()
    toks = tail.split()
    # Walk the split point between "PN/SN blob" and the fixed 11-token
    # trailing numeric block (8 time/cycle fields + limit + remain +
    # category) from the right, since the PN/SN blob's own token count
    # varies (kerning can split a PN across 1-2 extra tokens).
    trail_m = None
    cut = None
    for c in range(len(toks) - 11, -1, -1):
        candidate = " ".join(toks[c:])
        trail_m = _TRAIL_RE.match(candidate)
        if trail_m:
            cut = c
            break
    if trail_m is None or cut is None or cut < 1:
        return None
    pn_sin_toks = toks[:cut]
    sn = pn_sin_toks[-1]
    pn = "".join(pn_sin_toks[:-1]) if len(pn_sin_toks) > 1 else pn_sin_toks[0]

    rec = {c: "" for c in CANONICAL_COLUMNS}
    rec["CODE"] = first_tok
    rec["DESCRIPTION"] = desc
    rec["PART_NUMBER"] = pn
    rec["SERIAL_NUMBER"] = sn
    rec["TOTAL_TIME"] = trail_m.group("tt")
    rec["TOTAL_CYCLES"] = trail_m.group("tc")
    rec["TIME_SINCE_C"] = trail_m.group("tsc")
    rec["CYCLES_SINCE_C"] = trail_m.group("csc")
    rec["TIME_SINCE_B"] = trail_m.group("tsb")
    rec["CYCLES_SINCE_B"] = trail_m.group("csb")
    rec["TIME_SINCE_A"] = trail_m.group("tsa")
    rec["CYCLES_SINCE_A"] = trail_m.group("csa")
    rec["CYCLES_LIMIT"] = trail_m.group("limit")
    rec["CYCLES_REMAIN"] = trail_m.group("remain")
    rec["CATEGORY_CODE"] = trail_m.group("category")
    return rec


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            for raw in text.splitlines():
                rec = _parse_row(raw)
                if rec is None:
                    continue
                rec["_page"] = page_num
                records.append(rec)
    return records
