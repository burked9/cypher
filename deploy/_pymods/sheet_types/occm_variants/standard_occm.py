"""Standard OCCM variant — the canonical multi-operator OCCM layout.

Empirically the most common OCCM format in our corpus (~50 files spanning
many operators: GOL, VNA, A-prefix airframes, and others). The format is
generic enough that several MIS vendors emit it — we name it for the
*format*, not the operator. If a per-operator override is ever needed, an
operator-specific variant can be added with stricter SIGNATURES and the
router will prefer it.

Format: 14 columns per row.
    ATA DESCRIPTION FIN PART_NUMBER SERIAL_NUMBER
    AC_FH_AT_INSTALL AC_CY_AT_INSTALL
    COMP_FH_AT_INSTALL COMP_CY_AT_INSTALL
    TSI_FH TSI_CY        (component time since installation)
    TSN_FH TSN_CY        (component time since new)
    INSTALLED_DATE

Some rows contain "REF TO HTLL STATUS" instead of FH/CY/date — those are
placeholder rows pointing at the HT/LLP list for that component. We capture
them with the trailing time fields empty and `_ref_htll: True`.

Strategy: tokenize each line, identify whether it's a normal row (anchored
on the trailing date) or a HTLL reference row (anchored on the literal
"REF TO HTLL STATUS" suffix). Walk backwards from the anchor to assign
ATA/DESC/FIN/PN/SN reliably.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "Standard OCCM"
SIGNATURES = [
    "OCCM STATUS",
    "AIRCRAFT REGISTRATION:",
]

CANONICAL_COLUMNS = [
    "ATA",
    "DESCRIPTION",
    "FIN",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "AC_FH_AT_INSTALL",
    "AC_CY_AT_INSTALL",
    "COMP_FH_AT_INSTALL",
    "COMP_CY_AT_INSTALL",
    "TSI_FH",
    "TSI_CY",
    "TSN_FH",
    "TSN_CY",
    "INSTALLED_DATE",
]

# Numeric-time fields share a common pattern (allow decimals)
_NUM_RULE = {"pattern": r"^\d+(?:\.\d+)?$"}
_INT_RULE = {"pattern": r"^\d+$"}

_OVERRIDES = {
    "AC_FH_AT_INSTALL":   _NUM_RULE,
    "AC_CY_AT_INSTALL":   _INT_RULE,
    "COMP_FH_AT_INSTALL": _NUM_RULE,
    "COMP_CY_AT_INSTALL": _INT_RULE,
    "TSI_FH": _NUM_RULE,
    "TSI_CY": _INT_RULE,
    "TSN_FH": _NUM_RULE,
    "TSN_CY": _INT_RULE,
    "INSTALLED_DATE": {"pattern": r"^\d{1,2}/[A-Za-z]{3}/\d{2}$"},
}
RULES = merged_rules(_OVERRIDES)

_DATE_RE = re.compile(r"^\d{1,2}/[A-Za-z]{3}/\d{2}$")
_NUM_RE = re.compile(r"^\d+(?:\.\d+)?$")
_REF_SUFFIX = "REF TO HTLL STATUS"


def _parse_line(line: str, page_num: int) -> dict | None:
    line = line.strip()
    if not line or not line[0].isdigit():
        return None
    tokens = line.split()
    if len(tokens) < 5:
        return None

    # ATA must be 2-digit and within plausible range. The first token gates
    # everything; this is also our cheap rejection of header / footer lines.
    if not re.match(r"^\d{2}$", tokens[0]):
        return None
    try:
        ata_int = int(tokens[0])
    except ValueError:
        return None
    if not (20 <= ata_int <= 83):
        return None

    # Branch 1 — placeholder row ending in "REF TO HTLL STATUS"
    if line.endswith(_REF_SUFFIX):
        # tokens[..., FIN, PN, SN, REF, TO, HTLL, STATUS]
        if len(tokens) < 5 + 4:
            return None
        ref_idx = len(tokens) - 4   # index of "REF"
        fin_pn_sn = tokens[ref_idx - 3:ref_idx]
        if len(fin_pn_sn) != 3:
            return None
        fin, pn, sn = fin_pn_sn
        desc_tokens = tokens[1:ref_idx - 3]
        if not desc_tokens:
            return None
        rec = {c: "" for c in CANONICAL_COLUMNS}
        rec["ATA"] = tokens[0]
        rec["DESCRIPTION"] = " ".join(desc_tokens)
        rec["FIN"] = fin
        rec["PART_NUMBER"] = pn
        rec["SERIAL_NUMBER"] = sn
        rec["_page"] = page_num
        rec["_ref_htll"] = True
        return rec

    # Branch 2 — full row, ends with date and 8 numeric tokens before that.
    if not _DATE_RE.match(tokens[-1]):
        return None
    if len(tokens) < 14:
        return None

    # Last 9 tokens: 8 numerics + date
    nums = tokens[-9:-1]
    for n in nums:
        if not _NUM_RE.match(n):
            return None
    date = tokens[-1]
    head = tokens[:-9]   # ATA + DESC... + FIN + PN + SN
    if len(head) < 5:
        return None
    fin = head[-3]
    pn = head[-2]
    sn = head[-1]
    desc = " ".join(head[1:-3])
    if not desc:
        return None

    rec = dict(zip(
        CANONICAL_COLUMNS,
        [tokens[0], desc, fin, pn, sn] + nums + [date],
    ))
    rec["_page"] = page_num
    return rec


def extract(pdf_path: str) -> list[dict]:
    from shared.cleanup import normalize_dashes
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = normalize_dashes(page.extract_text() or "")
            if len(text) < 100:
                continue
            for line in text.splitlines():
                rec = _parse_line(line, page_num)
                if rec is not None:
                    records.append(rec)
    return records
