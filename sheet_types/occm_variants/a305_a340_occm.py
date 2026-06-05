"""A305 (Virgin Atlantic) A340-600 OCCM — `Components >> OC/CM Components`.

Two airframes in the corpus (G-VFIT MSN 753, G-VWIN MSN 736, both A340-600).
Same family of PDF as the Swiss A340 — `Components >> OC/CM Components`
header — but a fuller 16-column layout with both LOCATION (physical mount
text) and CONFIG_ADDR (functional slot, the `1XM2`/`5PU1`-style codes).

Per-row layout::

    ATA  PN  SN  [DESC tokens]  GRN  INST_DATE  CONFIG_ADDR
        TSN  CSN  TSI  CSI  TSO  CSO  TSN_DAYS

A typical row::

    2429 740GA01Y02 1384 ECMU 0003449745 08/04/2012 1XM2 28436.41 3444 24101.09 2873 28436.41 3444 2736

LOCATION (e.g. `LWR FUSELAGE\\AVI COMPT\\ECMU 2`) appears on lines BEFORE
and AFTER the data row because of the underlying PDF's multi-column layout.
We assemble a best-effort LOCATION from neighbouring backslash-containing
lines.

For the A330 vs A340 position-comparison work, CONFIG_ADDR is the
functional slot identifier (analogous to FIN on Airbus OCCMs).
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "A305 A340 OCCM"
SIGNATURES = [
    "Components >> OC/CM Components",
    "AC-Model: A340-600",
]

CANONICAL_COLUMNS = [
    "ATA",                # 4-digit ATA subgroup e.g. `2429`, `2163`, `3441`
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
    "GRN",                # 10-digit good-received note number
    "INST_DATE",
    "POSITION",           # the Config Addr column (1XM2, 5PU1, 636HK …)
    "LOCATION",           # physical mounting text — reconstructed best-effort
    "TSN", "CSN",
    "TSI", "CSI",
    "TSO", "CSO",
    "TSN_DAYS",
]

_OVERRIDES = {
    # A305 uses the full 4-digit chapter+subchapter ATA code (e.g. `3441` =
    # chapter 34, subchapter 41). The base rule expects 2-digit ATA with
    # int_range 20-83, so we both widen the pattern AND nuke the int_range.
    "ATA":        {"pattern": r"^\d{2,6}$", "int_range": None},
    "GRN":        {"pattern": r"^\d{8,10}$"},
    "INST_DATE":  {"pattern": r"^\d{2}/\d{2}/\d{4}$"},
    "POSITION":   {"pattern": r"^[A-Z0-9][A-Z0-9./\-]{0,12}$", "uppercase": True},
    # LOCATION can contain backslash, comma, parens, dot, dash. Loose pattern.
    "LOCATION":   {"pattern": r"^[\w \\/,.\-()]{0,120}$", "uppercase": True,
                   "allow_empty": True},
    # Numeric time-matrix cells: decimal hours or integer cycles/days.
    "TSN":        {"pattern": r"^\d+(?:\.\d+)?$"},
    "CSN":        {"pattern": r"^\d+(?:\.\d+)?$"},
    "TSI":        {"pattern": r"^\d+(?:\.\d+)?$"},
    "CSI":        {"pattern": r"^\d+(?:\.\d+)?$"},
    "TSO":        {"pattern": r"^\d+(?:\.\d+)?$"},
    "CSO":        {"pattern": r"^\d+(?:\.\d+)?$"},
    "TSN_DAYS":   {"pattern": r"^\d+$"},
    "DESCRIPTION":{"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_NUM_RE = re.compile(r"^\d+(?:\.\d+)?$")
_INT_RE = re.compile(r"^\d+$")
_DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")
_GRN_RE = re.compile(r"^\d{8,10}$")
_ATA_RE = re.compile(r"^\d{2,6}$")
_POS_RE = re.compile(r"^[A-Z0-9][A-Z0-9./\-]{0,12}$")
# Location-fragment heuristic: contains a backslash (Virgin's path notation)
# OR is uppercase short words with no digits.
_LOC_FRAG_RE = re.compile(r"\\|^[A-Z][A-Z, \-/]{1,40}$")


def _is_loc_fragment(line: str) -> bool:
    s = line.strip()
    if not s or len(s) > 60:
        return False
    return bool(_LOC_FRAG_RE.search(s)) and not _DATE_RE.search(s)


def _parse_data_line(line: str, page_num: int) -> dict | None:
    toks = line.split()
    if len(toks) < 11:
        return None
    if not _ATA_RE.match(toks[0]):
        return None
    # Trailing 7 numerics: TSN CSN TSI CSI TSO CSO TSN_DAYS
    if not all(_NUM_RE.match(t) for t in toks[-7:-1]):
        return None
    if not _INT_RE.match(toks[-1]):
        return None
    # Token before the 7-block must be POSITION (config addr).
    pos = toks[-8]
    if not _POS_RE.match(pos):
        return None
    # And before THAT must be INST_DATE.
    if not _DATE_RE.match(toks[-9]):
        return None
    install_date = toks[-9]
    # And before THAT, GRN.
    if not _GRN_RE.match(toks[-10]):
        return None
    grn = toks[-10]
    # PN, SN sit at fixed positions 1 and 2; description fills 3..-10.
    pn = toks[1]
    sn = toks[2]
    description = " ".join(toks[3:-10]) if len(toks) > 13 else ""
    tsn, csn, tsi, csi, tso, cso, tsn_days = toks[-7:]
    return {
        "ATA": toks[0],
        "PART_NUMBER": pn,
        "SERIAL_NUMBER": sn,
        "DESCRIPTION": description,
        "GRN": grn,
        "INST_DATE": install_date,
        "POSITION": pos,
        "LOCATION": "",
        "TSN": tsn, "CSN": csn,
        "TSI": tsi, "CSI": csi,
        "TSO": tso, "CSO": cso,
        "TSN_DAYS": tsn_days,
        "_page": page_num,
    }


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            lines = text.splitlines()
            for i, raw in enumerate(lines):
                line = raw.strip()
                if not line:
                    continue
                rec = _parse_data_line(line, page_num)
                if rec is None:
                    continue
                # Best-effort LOCATION reconstruction from neighbouring
                # backslash-bearing fragments (line above + line below).
                loc_parts = []
                if i > 0 and _is_loc_fragment(lines[i - 1]):
                    loc_parts.append(lines[i - 1].strip())
                if i + 1 < len(lines) and _is_loc_fragment(lines[i + 1]):
                    loc_parts.append(lines[i + 1].strip())
                rec["LOCATION"] = " ".join(loc_parts).strip()
                records.append(rec)
    return records
