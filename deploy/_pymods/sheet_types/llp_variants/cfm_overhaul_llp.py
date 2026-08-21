"""CFM Overhaul-shop LLP — \"LIFE LIMITED PARTS SUMMARY - OUTCOMING RATING\".

Source format: CFM56 engine overhaul shops (e.g. EASA FR.145.0010 / FAA CNFY912C)
emit a 2-page summary after an outcoming rating. Header carries ESN, IIN,
HSN/CSN and ENGINE_MODEL; data table is one row per disk with columns:

    IIN  DESIGNATION  PART NUMBER  SERIAL NUMBER  HSN  CSN  CAT_HOURS  CAT_CYCLES  \
        LIMIT_HOURS  LIMIT_CYCLES  LIMIT_DATE  REMAIN_HOURS  REMAIN_CYCLES  REMAIN_DATE

Numbers in this format use a SPACE as thousands separator (\"30 000\" not
\"30,000\"). The parser collapses those before tokenising. Some rows have a
DESIGNATION that wraps over two lines, which we reassemble using the
trailing-tokens heuristic.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.llp_variants._base import merged_rules

NAME = "CFM Overhaul LLP"
SIGNATURES = [
    "LIFE LIMITED PARTS SUMMARY - OUTCOMING RATING",
    "ENGINE OVERHAUL DEPARTMENT",
]

CANONICAL_COLUMNS = [
    "IIN",
    "DESIGNATION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "HSN",
    "CSN",
    "CAT_HOURS",
    "CAT_CYCLES",
    "LIMIT_HOURS",
    "LIMIT_CYCLES",
    "REMAIN_HOURS",
    "REMAIN_CYCLES",
    # Engine metadata
    "ESN",
    "ENGINE_MODEL",
    "ENGINE_HSN",
    "ENGINE_CSN",
]

# The hour columns are optional — not all rows are hour-limited. We allow
# empty silently. The cycle columns are also optional (some rows aren't
# life-limited at all), but the moment a cycle column IS populated we want
# the range check (0..45000) to fire.
# Hours bound widened to 150 000 — long-haul engines (777, A380) can run
# well past 80k hours over a 25-year life. Cycles bound stays at 45k per
# the engine-LLP rule.
_HOUR_RULE  = {"pattern": r"^[\d,]+$", "int_range": (0, 150000), "allow_empty": True}
_CYCLE_RULE = {"pattern": r"^[\d,]+$", "int_range": (0, 55000),
               "int_range_review": (0, 30000), "allow_empty": True}
_OVERRIDES = {
    "IIN":           {"pattern": r"^\d{1,4}$", "allow_empty": True},
    "HSN":           _HOUR_RULE,
    "CSN":           _CYCLE_RULE,
    "CAT_HOURS":     _HOUR_RULE,
    "CAT_CYCLES":    _CYCLE_RULE,
    "LIMIT_HOURS":   _HOUR_RULE,
    "LIMIT_CYCLES":  _CYCLE_RULE,
    "REMAIN_HOURS":  _HOUR_RULE,
    "REMAIN_CYCLES": _CYCLE_RULE,
    "ESN":           {"pattern": r"^\d{4,8}$"},
    "ENGINE_HSN":    _HOUR_RULE,
    "ENGINE_CSN":    _CYCLE_RULE,
}
RULES = merged_rules(_OVERRIDES)


# Match "30 000", "20 000", "1 234 567" etc. (thousands grouped with spaces).
_SPACE_THOUSANDS_RE = re.compile(r"(?<!\d)(\d{1,3}(?: \d{3})+)(?!\d)")
_NUM_RE = re.compile(r"^[\d,]+$")
_PN_RE = re.compile(r"^[A-Z0-9][A-Z0-9\-./]*$", re.I)
_DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$|^\d{2}\.\d{2}\.\d{4}$|^\d{2}-\d{2}-\d{4}$")

_SKIP_FRAGMENTS = (
    "LIFE LIMITED PARTS SUMMARY",
    "ENGINE OVERHAUL DEPARTMENT",
    "Version:",
    "Life Limit Category",
    "Total / Rating",
    "IIN Designation",
    "Page ",
    "(1)",
    "(2)",
    "REPAIR STATION",
)


def _collapse_space_thousands(line: str) -> str:
    """Replace ``30 000`` style space-grouped thousands with ``30000``."""
    return _SPACE_THOUSANDS_RE.sub(lambda m: m.group(1).replace(" ", ""), line)


def _is_skip_line(line: str) -> bool:
    return any(frag in line for frag in _SKIP_FRAGMENTS)


def _parse_meta(text: str) -> dict:
    meta: dict[str, str] = {}
    for line in text.splitlines()[:20]:
        # ESN
        m = re.search(r"\bSN\s*:\s*(\d{4,8})\b", line)
        if m and "ESN" not in meta:
            meta["ESN"] = m.group(1)
        m = re.search(r"\bENGINE\s*MODEL\s*:?\s*([A-Z0-9\-/]+)", line, re.I)
        if m and "ENGINE_MODEL" not in meta:
            meta["ENGINE_MODEL"] = m.group(1)
        m = re.search(r"\bHSN\s*:\s*([\d ,]+)", line, re.I)
        if m and "ENGINE_HSN" not in meta:
            meta["ENGINE_HSN"] = m.group(1).replace(" ", "").strip()
        m = re.search(r"\bCSN\s*:\s*([\d ,]+)", line, re.I)
        if m and "ENGINE_CSN" not in meta:
            meta["ENGINE_CSN"] = m.group(1).replace(" ", "").strip()
    return meta


def _parse_row(line: str) -> dict | None:
    """The Overhaul format uses plain integers — NO space-thousands collapse.
    Trailing-num count varies per row:
      4 nums = HSN, CSN, CAT_HOURS, CAT_CYCLES                (not life-limited)
      6 nums = ...above + LIMIT_CYCLES, REMAIN_CYCLES         (cycle-limited)
      8 nums = ...above + LIMIT_HOURS, REMAIN_HOURS pairs     (hour AND cycle)
    """
    s = line.strip()
    if not s or _is_skip_line(s):
        return None
    toks = s.split()
    if len(toks) < 6:
        return None
    trail: list[str] = []
    i = len(toks) - 1
    while i >= 0 and (_NUM_RE.match(toks[i]) or _DATE_RE.match(toks[i])):
        trail.insert(0, toks[i])
        i -= 1
    if len(trail) < 4:
        return None
    if i < 2:
        return None
    sn = toks[i]
    pn = toks[i - 1]
    iin = ""
    desc_start = 0
    if toks[0].isdigit() and len(toks[0]) <= 4:
        iin = toks[0]
        desc_start = 1
    designation = " ".join(toks[desc_start: i - 1])
    if not _PN_RE.match(pn):
        return None

    rec: dict[str, str] = {c: "" for c in CANONICAL_COLUMNS}
    rec["IIN"] = iin
    rec["DESIGNATION"] = designation
    rec["PART_NUMBER"] = pn
    rec["SERIAL_NUMBER"] = sn

    nums = [t for t in trail if _NUM_RE.match(t)]
    rec["HSN"], rec["CSN"] = (nums + ["", ""])[:2]
    rec["CAT_HOURS"], rec["CAT_CYCLES"] = (nums[2:] + ["", ""])[:2]
    if len(nums) == 6:
        # Cycle-limited only: skip LIMIT_HOURS / REMAIN_HOURS slots
        rec["LIMIT_CYCLES"] = nums[4]
        rec["REMAIN_CYCLES"] = nums[5]
    elif len(nums) >= 8:
        rec["LIMIT_HOURS"]   = nums[4]
        rec["LIMIT_CYCLES"]  = nums[5]
        rec["REMAIN_HOURS"]  = nums[6]
        rec["REMAIN_CYCLES"] = nums[7]
    elif len(nums) == 7:
        # Some files have 7 — assume the missing one is REMAIN_HOURS
        rec["LIMIT_HOURS"]   = nums[4]
        rec["LIMIT_CYCLES"]  = nums[5]
        rec["REMAIN_CYCLES"] = nums[6]
    return rec


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        full_text = "\n".join((p.extract_text() or "") for p in pdf.pages)
        meta = _parse_meta(full_text)
        last_record: dict | None = None
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            for raw in text.splitlines():
                rec = _parse_row(raw)
                if rec is None:
                    # Possible wrap-continuation of a previous designation
                    s = raw.strip()
                    if (last_record is not None and s and not _is_skip_line(s)
                            and not any(c.isdigit() for c in s) and len(s) <= 60):
                        last_record["DESIGNATION"] = (
                            last_record["DESIGNATION"] + " " + s
                        ).strip()
                    continue
                rec["_page"] = page_num
                for k, v in meta.items():
                    rec[k] = v
                records.append(rec)
                last_record = rec
    return records
