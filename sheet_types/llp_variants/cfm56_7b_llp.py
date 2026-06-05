"""CFM56-7B LLP status report — \"CFM56-7B LIFE LIMITED PARTS Date DD.MM.YYYY\".

Source format: per-engine LLP snapshot showing actual cycles, cycle life
limits and remaining cycles broken out by rating pair (7B18-7B24 vs
7B26-7B27). Header lines carry ENGINE_MODEL (e.g. CFM56-7B22), ESN, current
Engine TSN and CSN.

Row format::

    BOOSTER SPOOL  211  340-000-825-0  BB571267  22 086  22 086  0  30 000  30 000  7 914  7 914
    └ name ──────┘└IIN┘└── PN ──────┘└── SN ───┘└ actual cycles ──┘└ limit ─┘└ remain ┘

Numbers use SPACE as thousands separator (\"30 000\"). The parser collapses
those before tokenising. The trailing \"no limit\" / \"N/A\" markers for
non-life-limited rows (e.g. LPT TURBINE CASE) are preserved verbatim.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.llp_variants._base import merged_rules

NAME = "CFM56-7B LLP"
SIGNATURES = [
    "CFM56-7B LIFE LIMITED PARTS",
]

CANONICAL_COLUMNS = [
    "PART_NAME",
    "IIN",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "TOTAL_CYCLES",
    "ACTUAL_RATING_LOW",   # 7B18-7B24 actual
    "ACTUAL_RATING_HIGH",  # 7B26-7B27 actual
    "LIMIT_LOW",
    "LIMIT_HIGH",
    "REMAIN_LOW",
    "REMAIN_HIGH",
    # Engine metadata
    "ESN",
    "ENGINE_MODEL",
    "ENGINE_TSN",
    "ENGINE_CSN",
    "STATUS_DATE",
]

_CYCLE_RULE = {"pattern": r"^[\d,]+$", "int_range": (0, 55000),
               "int_range_review": (0, 30000), "allow_empty": True}
_HOUR_RULE  = {"pattern": r"^[\d,]+$", "int_range": (0, 80000), "allow_empty": True}
_OVERRIDES = {
    "IIN":               {"pattern": r"^\d{1,4}$"},
    "TOTAL_CYCLES":      _CYCLE_RULE,
    "ACTUAL_RATING_LOW": _CYCLE_RULE,
    "ACTUAL_RATING_HIGH": _CYCLE_RULE,
    "LIMIT_LOW":         _CYCLE_RULE,
    "LIMIT_HIGH":        _CYCLE_RULE,
    "REMAIN_LOW":        _CYCLE_RULE,
    "REMAIN_HIGH":       _CYCLE_RULE,
    "ESN":               {"pattern": r"^\d{4,8}$"},
    "ENGINE_TSN":        _HOUR_RULE,
    "ENGINE_CSN":        _CYCLE_RULE,
    "STATUS_DATE":       {"pattern": r"^\d{2}\.\d{2}\.\d{4}$"},
}
RULES = merged_rules(_OVERRIDES)


# `(?!\S)` requires whitespace (or end-of-string) after the match. Without it
# the regex would happily collapse `"211 340"` (IIN followed by start of a
# dash-prefixed PN like `340-000-825-0`) into `"211340"` and the row would
# fail to parse.
_SPACE_THOUSANDS_RE = re.compile(r"(?<!\S)(\d{1,3}(?: \d{3})+)(?!\S)")
_NUM_OR_NA_RE = re.compile(r"^([\d,]+|N/A|no limit)$", re.I)
_NUM_RE = re.compile(r"^[\d,]+$")
_PN_RE = re.compile(r"^[A-Z0-9][A-Z0-9\-./]*$", re.I)

_SKIP_FRAGMENTS = (
    "CFM56-7B LIFE LIMITED PARTS",
    "Engine TSN",
    "ACTUAL CYCLES",
    "PART NAME",
    "Limit for engine",
    "This information is based",
    "* Calculation",
    "For rotating LLP",
    "Refer to sections",
)


def _collapse_space_thousands(line: str) -> str:
    return _SPACE_THOUSANDS_RE.sub(lambda m: m.group(1).replace(" ", ""), line)


def _collapse_no_limit(line: str) -> str:
    """Treat 'no limit' and 'N/A' as single tokens so the trailing walk picks them up."""
    return line.replace("no limit", "no_limit")


def _is_skip_line(line: str) -> bool:
    return any(frag in line for frag in _SKIP_FRAGMENTS)


def _parse_meta(text: str) -> dict:
    meta: dict[str, str] = {}
    for line in text.splitlines()[:8]:
        m = re.search(r"\bCFM56-7B\w*\b", line)
        if m and "ENGINE_MODEL" not in meta:
            meta["ENGINE_MODEL"] = m.group(0)
        m = re.search(r"\bESN\s+(\d{4,8})\b", line)
        if m:
            meta["ESN"] = m.group(1)
        m = re.search(r"Engine\s+TSN:\s*([\d ]+)", line)
        if m:
            meta["ENGINE_TSN"] = m.group(1).replace(" ", "").strip()
        m = re.search(r"Engine\s+CSN:\s*([\d ]+)", line)
        if m:
            meta["ENGINE_CSN"] = m.group(1).replace(" ", "").strip()
        m = re.search(r"Date\s+(\d{2}\.\d{2}\.\d{4})", line)
        if m:
            meta["STATUS_DATE"] = m.group(1)
    return meta


def _parse_row(line: str) -> dict | None:
    s = line.strip()
    if not s or _is_skip_line(s):
        return None
    s = _collapse_no_limit(_collapse_space_thousands(s))
    toks = s.split()
    if len(toks) < 6:
        return None
    # Trailing numerics or no_limit/N/A markers
    trail: list[str] = []
    i = len(toks) - 1
    while i >= 0 and (_NUM_RE.match(toks[i])
                      or toks[i] in ("no_limit",)
                      or toks[i].upper() == "N/A"):
        trail.insert(0, toks[i])
        i -= 1
    if len(trail) < 4:
        return None
    if i < 2:
        return None
    sn = toks[i]
    pn = toks[i - 1]
    iin = toks[i - 2]
    if not iin.isdigit() or not _PN_RE.match(pn):
        return None
    part_name = " ".join(toks[: i - 2])

    rec: dict[str, str] = {c: "" for c in CANONICAL_COLUMNS}
    rec["PART_NAME"] = part_name
    rec["IIN"] = iin
    rec["PART_NUMBER"] = pn
    rec["SERIAL_NUMBER"] = sn

    keys = ["TOTAL_CYCLES", "ACTUAL_RATING_LOW", "ACTUAL_RATING_HIGH",
            "LIMIT_LOW", "LIMIT_HIGH", "REMAIN_LOW", "REMAIN_HIGH"]
    # First numeric is TOTAL_CYCLES; the rest follow. Trail can be 6 or 7 long.
    for k, v in zip(keys, trail):
        rec[k] = v.replace("no_limit", "no limit")
    return rec


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        full_text = "\n".join((p.extract_text() or "") for p in pdf.pages)
        meta = _parse_meta(full_text)
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            for raw in text.splitlines():
                rec = _parse_row(raw)
                if rec is None:
                    continue
                rec["_page"] = page_num
                for k, v in meta.items():
                    rec[k] = v
                records.append(rec)
    return records
