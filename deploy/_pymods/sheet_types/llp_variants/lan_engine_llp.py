"""LAN-Airlines engine LLP — "ENGINE LLPs STATUS REPORT - SUMMARY".

Source format (LAN-family operators, CF6/CFM engine LLPs). Header carries
engine model, ESN, current TSN/CSN/TSO/CSO and status date. The data table is
one line per disk:

    DESCRIPTION                   PART_NUMBER  SERIAL_NUMBER  HRS    CYC    HRS    CYC   HRS    CYC
    FAN ROTOR DISK STAGE 1        1856M89P01   TMT6B027       20000  32698  5931   14069
    FAN ROTOR STAGES 2-5 SPOOL    1782M80P01   VOLJ1774       20000  32698  5931   14069
    ...

Anchor: the trailing 4–6 numeric tokens after S/N. We walk back from the end
of the line, collect the longest run of integer tokens, and then S/N is the
token immediately preceding them, PN is the token before that, and everything
to the left is the description.

Engine metadata (ENGINE_MODEL, ESN, TSN, CSN, TSO, CSO, STATUS_DATE) is parsed
once per file from the header block and stamped on every row.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.llp_variants._base import merged_rules

NAME = "LAN Engine LLP"
SIGNATURES = [
    "ENGINE LLPs STATUS REPORT",
    "DISK LIMIT TOTAL REMAIN",
]

CANONICAL_COLUMNS = [
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "LIMIT_HRS",
    "LIMIT_CYCLES",
    "TOTAL_HRS",
    "TOTAL_CYCLES",
    "REMAIN_HRS",
    "REMAIN_CYCLES",
    # Engine metadata — same on every row
    "ENGINE_MODEL",
    "ESN",
    "ENGINE_TSN",
    "ENGINE_CSN",
    "ENGINE_TSO",
    "ENGINE_CSO",
    "STATUS_DATE",
]

_HOUR_RULE  = {"pattern": r"^[\d.,']+$", "int_range": (0, 80000)}
_CYCLE_RULE = {"pattern": r"^[\d.,']+$", "int_range": (0, 55000),
               "int_range_review": (0, 30000)}
_OVERRIDES = {
    "LIMIT_HRS":    _HOUR_RULE,
    "LIMIT_CYCLES": _CYCLE_RULE,
    "TOTAL_HRS":    _HOUR_RULE,
    "TOTAL_CYCLES": _CYCLE_RULE,
    "REMAIN_HRS":   _HOUR_RULE,
    "REMAIN_CYCLES": _CYCLE_RULE,
    "ENGINE_TSN":   _HOUR_RULE,
    "ENGINE_CSN":   _CYCLE_RULE,
    "ENGINE_TSO":   _HOUR_RULE,
    "ENGINE_CSO":   _CYCLE_RULE,
    "STATUS_DATE":  {"pattern": r"^\d{2}[-/]\d{2}[-/]\d{4}$"},
}
RULES = merged_rules(_OVERRIDES)

# Numbers used here are integers, sometimes with `.` or `,` as thousands sep
_NUM_TOKEN_RE = re.compile(r"^[\d][\d.,']*$")
_DATE_RE = re.compile(r"^\d{2}[-/]\d{2}[-/]\d{4}$")
# Part-number-ish token: must contain at least one letter or hyphen
_PN_RE = re.compile(r"^[A-Z0-9][A-Z0-9\-./]*$")


def _is_num(tok: str) -> bool:
    return bool(_NUM_TOKEN_RE.match(tok))


def _parse_engine_meta(text: str) -> dict:
    """Pull engine model / ESN / TSN / CSN / TSO / CSO / status-date from header."""
    meta: dict[str, str] = {}
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    # Header block typical layout (per the sample):
    #   ENGINE MODEL ESN                            (label)
    #   CF6-80C2B6F  707124                         (values)
    #   TSN CSN STATUS DATE                         (label)
    #   32.698 5.931 01-02-2019                     (values)
    #   TSO CSO                                     (label)
    #   2.899 439                                   (values)
    # We look for the label lines and read the next non-empty line as values.
    for i, ln in enumerate(lines):
        u = ln.upper()
        if u.startswith("ENGINE MODEL") and i + 1 < len(lines):
            toks = lines[i - 1].split() if i > 0 else []
            # In the sample the values line is the one BEFORE the labels line.
            # Try the line directly above (between operator/tail and labels).
            if not toks:
                continue
            if len(toks) >= 2:
                meta["ENGINE_MODEL"] = toks[0]
                meta["ESN"] = toks[-1]
        if u.startswith("TSN CSN STATUS") and i > 0:
            toks = lines[i - 1].split()
            if len(toks) >= 3:
                meta["ENGINE_TSN"] = toks[0]
                meta["ENGINE_CSN"] = toks[1]
                if _DATE_RE.match(toks[-1]):
                    meta["STATUS_DATE"] = toks[-1]
        if u.startswith("TSO CSO") and i > 0:
            toks = lines[i - 1].split()
            if len(toks) >= 2:
                meta["ENGINE_TSO"] = toks[0]
                meta["ENGINE_CSO"] = toks[1]
    return meta


def _parse_row(line: str) -> dict | None:
    """Parse one disk row. Returns dict or None."""
    s = line.strip()
    if not s:
        return None
    toks = s.split()
    # Need at least description-token + PN + SN + 4 trailing numbers
    if len(toks) < 7:
        return None

    # Walk back from the end collecting numeric tokens.
    trail = []
    i = len(toks) - 1
    while i >= 0 and _is_num(toks[i]):
        trail.insert(0, toks[i])
        i -= 1
    # We expect exactly 6 numeric trailing tokens (LIMIT_HRS, LIMIT_CYC,
    # TOTAL_HRS, TOTAL_CYC, REMAIN_HRS, REMAIN_CYC). Some files only print
    # 4 (LIMIT_CYC, TOTAL_CYC, REMAIN_CYC + a 4th) — accept 4 or 6.
    if len(trail) not in (4, 6):
        return None
    # i now points at S/N
    if i < 2:
        return None
    sn = toks[i]
    pn = toks[i - 1]
    desc = " ".join(toks[: i - 1])
    if not desc:
        return None
    if not _PN_RE.match(pn) or not _PN_RE.match(sn):
        return None

    rec: dict[str, str] = {c: "" for c in CANONICAL_COLUMNS}
    rec["DESCRIPTION"] = desc
    rec["PART_NUMBER"] = pn
    rec["SERIAL_NUMBER"] = sn
    if len(trail) == 6:
        (rec["LIMIT_HRS"], rec["LIMIT_CYCLES"],
         rec["TOTAL_HRS"], rec["TOTAL_CYCLES"],
         rec["REMAIN_HRS"], rec["REMAIN_CYCLES"]) = trail
    else:  # 4 trailing — sample shows HRS/CYC/CYC/CYC variants
        rec["LIMIT_HRS"] = trail[0]
        rec["TOTAL_CYCLES"] = trail[1]
        rec["REMAIN_HRS"] = trail[2]
        rec["REMAIN_CYCLES"] = trail[3]
    return rec


# Lines that look like the column-header — skip
_HEADER_FRAGMENTS = (
    "DISK LIMIT TOTAL REMAIN",
    "DESCRIPTION PART NUMBER SERIAL NUMBER",
    "HRS CYCLES HRS CYCLES",
    "ENGINE LLPs",
    "OPERATOR TAIL ID",
    "ENGINE MODEL ESN",
    "TSN CSN STATUS",
    "TSO CSO",
)


def _is_header_line(line: str) -> bool:
    u = line.upper()
    return any(frag.upper() in u for frag in _HEADER_FRAGMENTS)


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        full_text = "\n".join((p.extract_text() or "") for p in pdf.pages)
        meta = _parse_engine_meta(full_text)
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if len(text) < 50:
                continue
            for raw in text.splitlines():
                line = raw.strip()
                if not line or _is_header_line(line):
                    continue
                rec = _parse_row(line)
                if rec is None:
                    continue
                for k, v in meta.items():
                    rec[k] = v
                rec["_page"] = page_num
                records.append(rec)
    return records
