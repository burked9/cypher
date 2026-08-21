"""Vietnam Airlines variant — LLP (Life Limited Parts) sheet.

Source format: "LIFE LIMITED PART LIST" (form ID `VNA-MNT-F65-01a`). One file
per engine; the document header carries the engine S/N and current TSN/CSN/TSI/CSI.

Row format (single line, space-separated):
    NO  DESCRIPTION...  PART_NUMBER  SERIAL_NUMBER  TSN  CSN  LIMIT  REMAINING  REMARK

Anchors:
    - NO is a leading integer (1, 2, 3, …)
    - The four numeric fields (TSN, CSN, LIMIT, REMAINING) sit immediately
      before the trailing REMARK token
    - REMARK is typically a single word: "Original" / "New" / "Replaced"

Engine metadata (V-prefixed serial, current totals) is parsed once per file
into `engine_meta` and added to every row as `ENGINE_SN`, `ENGINE_TSN`,
`ENGINE_CSN`, `ENGINE_TSI`, `ENGINE_CSI`, `LOWEST_LLP_REMAINING`.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.llp_variants._base import merged_rules

NAME = "Vietnam Airlines"
SIGNATURES = [
    "LIFE LIMITED PART LIST",
    "VNA-MNT-F65",
]

CANONICAL_COLUMNS = [
    "NO",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "TSN",
    "CSN",
    "LIMIT",
    "REMAINING",
    "REMARK",
    # Engine metadata — same value on every row of a given file
    "ENGINE_SN",
    "ENGINE_TSN",
    "ENGINE_CSN",
    "ENGINE_TSI",
    "ENGINE_CSI",
    "LOWEST_LLP_REMAINING",
]

_NUM_RULE = {"pattern": r"^\d+(?:\.\d+)?$"}
_HOUR_RULE  = {"pattern": r"^\d+(?:\.\d+)?$", "int_range": (0, 80000)}
_CYCLE_RULE = {"pattern": r"^\d+(?:\.\d+)?$", "int_range": (0, 55000),
               "int_range_review": (0, 30000)}

_OVERRIDES = {
    "NO":       {"pattern": r"^\d+$"},
    "TSN":      _HOUR_RULE,
    "CSN":      _CYCLE_RULE,
    "LIMIT":    _CYCLE_RULE,     # LLP cycle limit
    "REMAINING": _CYCLE_RULE,    # cycles remaining
    "ENGINE_SN":  {"pattern": r"^[A-Z0-9]+$", "uppercase": True},
    "ENGINE_TSN": _HOUR_RULE,
    "ENGINE_CSN": _CYCLE_RULE,
    "ENGINE_TSI": _HOUR_RULE,
    "ENGINE_CSI": _CYCLE_RULE,
    "LOWEST_LLP_REMAINING": _CYCLE_RULE,
}
RULES = merged_rules(_OVERRIDES)


_NUM_RE = re.compile(r"^\d+(?:\.\d+)?$")
_ENGINE_LINE_RE = re.compile(
    r"^(?P<sn>[A-Z]\d+)\s+(?P<tsn>\d+(?:\.\d+)?)\s+(?P<csn>\d+(?:\.\d+)?)"
    r"\s+(?P<tsi>\d+(?:\.\d+)?)\s+(?P<csi>\d+(?:\.\d+)?)\s+(?P<lowest>\d+(?:\.\d+)?)"
)


def _parse_engine_meta(text: str) -> dict:
    """Find the engine-info line (V12639 29623.6 17605 ...). Returns empty
    dict if not found — the row parser will simply not populate metadata."""
    for line in text.splitlines():
        m = _ENGINE_LINE_RE.match(line.strip())
        if m:
            return {
                "ENGINE_SN":  m.group("sn"),
                "ENGINE_TSN": m.group("tsn"),
                "ENGINE_CSN": m.group("csn"),
                "ENGINE_TSI": m.group("tsi"),
                "ENGINE_CSI": m.group("csi"),
                "LOWEST_LLP_REMAINING": m.group("lowest"),
            }
    return {}


def _parse_row_line(line: str, page_num: int, meta: dict) -> dict | None:
    line = line.strip()
    if not line:
        return None
    tokens = line.split()
    if len(tokens) < 9:
        return None
    if not tokens[0].isdigit():
        return None

    no = tokens[0]
    remark = tokens[-1]

    # Last 4 tokens before remark must all be numeric
    nums = tokens[-5:-1]
    for n in nums:
        if not _NUM_RE.match(n):
            return None
    tsn, csn, limit, remaining = nums

    head = tokens[1:-5]
    if len(head) < 3:
        return None
    sn = head[-1]
    pn = head[-2]
    desc_tokens = head[:-2]
    if not desc_tokens:
        return None
    desc = " ".join(desc_tokens)

    rec = {c: "" for c in CANONICAL_COLUMNS}
    rec["NO"] = no
    rec["DESCRIPTION"] = desc
    rec["PART_NUMBER"] = pn
    rec["SERIAL_NUMBER"] = sn
    rec["TSN"] = tsn
    rec["CSN"] = csn
    rec["LIMIT"] = limit
    rec["REMAINING"] = remaining
    rec["REMARK"] = remark
    for k, v in meta.items():
        rec[k] = v
    rec["_page"] = page_num
    return rec


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        full_text = "\n".join((p.extract_text() or "") for p in pdf.pages)
        meta = _parse_engine_meta(full_text)
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if len(text) < 100:
                continue
            for line in text.splitlines():
                rec = _parse_row_line(line, page_num, meta)
                if rec is not None:
                    records.append(rec)
    return records
