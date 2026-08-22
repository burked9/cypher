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

Two sibling sub-formats confirmed via real-corpus triage (2026-08-22),
found because production silently returned zero rows on both:

  - An extra leading row-number column ("NO. ATA FIN..." instead of
    "ATA FIN..."). Detected once per file from the header text itself
    (see `_HAS_ROW_NUMBER_COL`) rather than guessed per-row, since row
    numbers and real ATA chapters can collide (both are small 2-digit
    integers).
  - A structurally simpler 8-column layout with no AC/COMP FH-CY
    breakdown at all — see `_parse_simple_row`. Only one confirmed
    example so far; a second one turning up with a different shape is
    a good signal to split this into its own variant module instead.
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

# Both slash- and dash-separated dates confirmed in the corpus, both with
# a 2-digit year ("31/Aug/19" and "20-May-05") -- kept distinct from
# _SIMPLE_DATE_RE below by year length, since that one's 4-digit-year
# dash format would otherwise be ambiguous with this one.
_DATE_RE = re.compile(r"^\d{1,2}[/-][A-Za-z]{3}[/-]\d{2}$")
_NUM_RE = re.compile(r"^\d+(?:\.\d+)?$")
_REF_SUFFIX = "REF TO HTLL STATUS"

# A sibling sub-format (confirmed on one file, "A349 OCCM 31.pdf") has an
# extra leading row-number column pdfplumber's text extraction preserves
# as its own token -- the column header literally reads "NO. ATA FIN..."
# instead of "ATA FIN...". Detected once from the file's own header text
# rather than guessed per-row: row numbers and real ATA chapters are both
# small 2-digit integers (rows commonly run past 20), so a row like
# "25 21 ..." is genuinely ambiguous token-by-token -- trying the
# unshifted interpretation first would silently accept it with FIN/PN/SN
# all off by one instead of falling through to the correct shifted read.
_HAS_ROW_NUMBER_COL = "NO. ATA"


def _parse_line(line: str, page_num: int, has_row_number: bool = False) -> dict | None:
    line = line.strip()
    if not line or not line[0].isdigit():
        return None
    tokens = line.split()
    if has_row_number and len(tokens) > 1 and tokens[0].isdigit():
        tokens = tokens[1:]
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


# A structurally different, simpler sibling format -- confirmed on one file
# so far ("CC-AFY OCCM STATUS REV 0.pdf"). No AC/COMP FH-CY breakdown at
# all: ATA FIN DESCRIPTION... PART_NUMBER SERIAL_NUMBER INSTALLED_DATE
# ACTUAL_TSN ACTUAL_CSN -- 8 columns, not 14. Dates are D-Mon-YYYY with
# dashes and a 4-digit year (the main branch expects D/Mon/YY with
# slashes). Numbers use a comma decimal separator ("49490,50"). TSN/CSN
# carry an unrecorded-value sentinel spelled three different ways in the
# source data itself: "UNKNOWN", the typo "UNKNOW", and "TBC". Only one
# confirmed example so far -- if more turn up with a different shape,
# this is a good candidate to split into its own variant module instead
# of a third branch here.
_SIMPLE_DATE_RE = re.compile(r"^\d{1,2}-[A-Za-z]{3}-\d{4}$")
_SIMPLE_SENTINEL_RE = re.compile(r"^([\d.,]+|UNKNOWN|UNKNOW|TBC)$", re.I)


def _parse_simple_row(tokens: list[str], page_num: int) -> dict | None:
    if len(tokens) < 8:
        return None
    if not re.match(r"^\d{2}$", tokens[0]):
        return None
    try:
        ata_int = int(tokens[0])
    except ValueError:
        return None
    if not (20 <= ata_int <= 83):
        return None
    if not (_SIMPLE_SENTINEL_RE.match(tokens[-1]) and _SIMPLE_SENTINEL_RE.match(tokens[-2])):
        return None
    if not _SIMPLE_DATE_RE.match(tokens[-3]):
        return None
    pn, sn = tokens[-5], tokens[-4]
    desc = " ".join(tokens[2:-5])
    if not desc:
        return None

    rec = {c: "" for c in CANONICAL_COLUMNS}
    rec["ATA"] = tokens[0]
    rec["FIN"] = tokens[1]
    rec["DESCRIPTION"] = desc
    rec["PART_NUMBER"] = pn
    rec["SERIAL_NUMBER"] = sn
    rec["INSTALLED_DATE"] = tokens[-3]
    rec["TSN_FH"] = tokens[-2]
    rec["TSN_CY"] = tokens[-1]
    rec["_page"] = page_num
    return rec


# A third sibling format -- confirmed on one file ("A305_OCCM
# Inventory_20210308.pdf"): ATA PN SN DESCRIPTION POS DATE, no TSN/CSN or
# FH/CY breakdown at all. POS is folded into DESCRIPTION rather than
# split out: real examples ("GALLEY G", "P8-CAPT", "P8-F/O", "0", "FO")
# have no consistent shape to anchor on, and guessing at a split from one
# file's worth of examples risks being confidently wrong rather than
# usefully approximate. An analyst can still read the combined text; a
# wrong split could silently misattribute a real field.
def _parse_ata_pn_sn_date_row(tokens: list[str], page_num: int) -> dict | None:
    if len(tokens) < 5:
        return None
    if not re.match(r"^\d{2}$", tokens[0]):
        return None
    try:
        ata_int = int(tokens[0])
    except ValueError:
        return None
    if not (20 <= ata_int <= 83):
        return None
    if not _DATE_RE.match(tokens[-1]):
        return None
    desc = " ".join(tokens[3:-1])
    if not desc:
        return None
    rec = {c: "" for c in CANONICAL_COLUMNS}
    rec["ATA"] = tokens[0]
    rec["PART_NUMBER"] = tokens[1]
    rec["SERIAL_NUMBER"] = tokens[2]
    rec["DESCRIPTION"] = desc
    rec["INSTALLED_DATE"] = tokens[-1]
    rec["_page"] = page_num
    return rec


def extract(pdf_path: str) -> list[dict]:
    from shared.cleanup import normalize_dashes
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        # extract_text() once per page, cached -- the row-number-column
        # detection needs the whole document's text, and re-calling
        # extract_text() a second time per page would double the cost of
        # extraction for no benefit.
        page_texts = [normalize_dashes(p.extract_text() or "") for p in pdf.pages]
        has_row_number = any(_HAS_ROW_NUMBER_COL in t for t in page_texts)
        for page_num, text in enumerate(page_texts, start=1):
            if len(text) < 100:
                continue
            for line in text.splitlines():
                rec = _parse_line(line, page_num, has_row_number=has_row_number)
                if rec is None:
                    toks = line.strip().split()
                    rec = _parse_simple_row(toks, page_num) or _parse_ata_pn_sn_date_row(toks, page_num)
                if rec is not None:
                    records.append(rec)
    return records
