"""CONFIG SLOT OCCM variant — South American operator format.

Seen across LV-IQW (Argentina), CC-CZU / CC-CZT (Chile), PR-MAP (Brazil), and
MSN_3214 documents. Uses a 5-segment ATA-like `CONFIG SLOT`, an internal
`I______`-prefixed barcode column, and European decimal formatting
(`88.943,55` = 88943.55 in plain English).

Format header:
    CONFIG SLOT PART NUMBER SERIAL NUMBER POSITION ID BARCODE EQUIPMENT DESCRIPTION
        ORIGINAL DATE INSTALL  TIME SINCE NEW  TIME SINCE OVERHAUL
        CYCLE SINCE NEW  CYCLE SINCE OVERHAUL

Per-row layout (one line, space-separated):
    CONFIG_SLOT  PN  SN  POSITION  ID_BARCODE  EQUIPMENT_DESCRIPTION...
        INSTALL_DATE  TIME_SN  TIME_SO  CYCLE_SN  CYCLE_SO

The ID_BARCODE token has a very distinctive shape (`I` + 6-8 alphanumeric)
and reliably anchors the split between the structured fields and the
multi-token description.

Numeric values preserve their European format as raw strings — analysts can
convert downstream if needed. Splitting them into typed floats here would
either drop the original notation or require ambiguous heuristics.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "CONFIG SLOT OCCM"
SIGNATURES = [
    "CONFIG SLOT PART NUMBER SERIAL NUMBER POSITION ID BARCODE",
    "TIME SINCE NEW TIME SINCE OVERHAUL CYCLE SINCE NEW CYCLE SINCE OVERHAUL",
    "CONFIG SLOT",
]

CANONICAL_COLUMNS = [
    "CONFIG_SLOT",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "POSITION",
    "ID_BARCODE",
    "EQUIPMENT_DESCRIPTION",
    "INSTALL_DATE",
    "TIME_SINCE_NEW",
    "TIME_SINCE_OVERHAUL",
    "CYCLE_SINCE_NEW",
    "CYCLE_SINCE_OVERHAUL",
]

_OVERRIDES = {
    "CONFIG_SLOT": {"pattern": r"^\d+(?:-\d+){2,5}$"},
    "ID_BARCODE":  {"pattern": r"^I[0-9A-Z]{6,8}$", "uppercase": True},
    "INSTALL_DATE": {"pattern": r"^\d{2}[/-]\d{2}[/-]\d{4}$"},
    # Euro-numeric values kept as raw strings — no pattern enforced
    "TIME_SINCE_NEW": {},
    "TIME_SINCE_OVERHAUL": {},
    "CYCLE_SINCE_NEW": {},
    "CYCLE_SINCE_OVERHAUL": {},
}
RULES = merged_rules(_OVERRIDES)

_CONFIG_RE  = re.compile(r"^\d+(?:-\d+){2,5}$")
_BARCODE_RE = re.compile(r"^I[0-9A-Z]{6,8}$")
_DATE_RE    = re.compile(r"^\d{2}[/-]\d{2}[/-]\d{4}$")
# Euro-numeric: digits with optional thousand separators (.) and decimal (,)
_EU_NUMERIC_RE = re.compile(r"^\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?$|^\d+$")


def _parse_line(line: str, page_num: int) -> dict | None:
    tokens = line.split()
    if len(tokens) < 9:
        return None
    if not _CONFIG_RE.match(tokens[0]):
        return None

    # Find install date
    date_idx = None
    for i, t in enumerate(tokens):
        if _DATE_RE.match(t):
            date_idx = i
            break
    if date_idx is None or date_idx + 4 >= len(tokens):
        return None

    # 4 numeric tokens after date
    nums = tokens[date_idx + 1:date_idx + 5]
    if not all(_EU_NUMERIC_RE.match(t) for t in nums):
        return None
    tsn, tso, csn, cso = nums

    # Find ID_BARCODE before date
    bc_idx = None
    for i in range(date_idx - 1, 0, -1):
        if _BARCODE_RE.match(tokens[i]):
            bc_idx = i
            break
    if bc_idx is None or bc_idx < 4:
        # Need at least: CONFIG_SLOT, PN, SN, POSITION before ID_BARCODE
        return None

    # Before barcode: 4 tokens — CONFIG_SLOT, PN, SN, POSITION
    if bc_idx < 4:
        return None
    config_slot = tokens[0]
    pn          = tokens[1]
    sn          = tokens[2]
    position    = tokens[3] if bc_idx == 4 else " ".join(tokens[3:bc_idx])
    id_barcode  = tokens[bc_idx]

    # Between barcode and date: EQUIPMENT_DESCRIPTION (multi-token)
    desc_tokens = tokens[bc_idx + 1:date_idx]
    if not desc_tokens:
        return None
    description = " ".join(desc_tokens)

    return {
        "CONFIG_SLOT": config_slot,
        "PART_NUMBER": pn,
        "SERIAL_NUMBER": sn,
        "POSITION": position,
        "ID_BARCODE": id_barcode,
        "EQUIPMENT_DESCRIPTION": description,
        "INSTALL_DATE": tokens[date_idx],
        "TIME_SINCE_NEW": tsn,
        "TIME_SINCE_OVERHAUL": tso,
        "CYCLE_SINCE_NEW": csn,
        "CYCLE_SINCE_OVERHAUL": cso,
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
