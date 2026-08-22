"""e.MES Airframe LLP Status — "Life Limited Part Status" / Airframe, one file
per landing-gear position (NOSE / RMLG seen so far; LMLG presumed same
template). Footer reads "From e.MES" (the source MIS). Confirmed on 3 real
files: MSN30625 and MSN33019 NOSE, and MSN30625 RMLG (the only one of the
three that runs to 2 content pages, header block reprinted at the top of
each).

Each page's header block carries aircraft + assembly identity:
    A/C Type B737NG A/C # HL8028 MSN 30625 AC TSN 59165.53 AC CSN 47322 Date 2020-03-15
    NOSE LANDING GEAR ASSY
followed by a HARD TIME line for the gear assembly itself as a unit (TSO/CSO/
TSN/CSN + "HardTime Limit"/"HT Remaining"). That block belongs to the HT sheet
type, not LLP, and is deliberately not extracted here -- only the
"Life Limited Parts (<date>)" table beneath it is in scope.

Row format (single line, space-separated), one row per LLP piece-part:
    L/I#  DESCRIPTION...  DETAIL_P/N  [ASSY_P/N]  S/N  TSO CSO DSO TSN CSN  LIMIT_CSN LIMIT_CSO LIMIT_DSO  REMAIN_CSN REMAIN_CSO REMAIN_DSO
e.g. (MSN30625 NOSE LLP, L/I 2):
    2 Trunnion Pin - Left 162A0301-2 162A0301-1 E0217 3987.53 4761 702 61092.53 52725 75000 18000 3650 22,275 13,239 2,948
Confirmed column meaning by arithmetic, not guessed: LIMIT_x - x == REMAIN_x
holds for CSN/CSO/DSO on every data row across all 3 files.

Anchors:
    - S/N is always the very last token -- even on the one row (MSN33019
      NOSE, L/I 2-02) where S/N is itself all-digits ("1476"), so it can't be
      told apart from the numeric fields by shape, only by position.
    - The trailing numeric block is taken as a fixed-size slice (last 11
      tokens, or last 10, checked to be all-numeric) rather than "walk back
      while numeric" -- precisely because of that all-digit S/N. A walk-back
      would swallow it as a 12th numeric field (confirmed: it does, on that
      exact row).
    - Some rows print only 10 trailing numbers, not 11 -- confirmed on 3 rows
      across 2 files (MSN33019 NOSE L/I 1-04 & 1-10, MSN30625 RMLG L/I 35),
      always the same missing field: TSN. CSN follows DSO directly in that
      case. Verified against the LIMIT-CURRENT=REMAINING identity above, not
      assumed.
    - 1 or 2 part-number tokens sit between the description and S/N (ASSY P/N
      is omitted when the part has no separate parent-assembly P/N to cite).
      Detected by shape (alnum-hyphen-alnum), scanned back from S/N.

L/I# also prefixes non-data section headers ("1 NLG Installation Assy" /
"2-00 Drag Strut Installation" / "1 Installation -RH") that group the rows
beneath them but carry no P/N, S/N or numbers of their own. These update
SUB_ASSEMBLY for subsequent rows rather than becoming rows themselves --
confirmed necessary on MSN33019 NOSE, the only one of the 3 files with more
than one such section (NLG Installation Assy, then Drag Strut Installation).

Known finding, not a bug: MSN30625 NOSE L/I 23 prints its detail P/N with the
hyphen replaced by a space -- "162A2301 2" instead of "162A2301-2" -- so that
one row's DETAIL_PART_NUMBER/description split lands one token off (confirmed
by comparing against sibling L/I 22, an identical part correctly formed).
Not special-cased: a fix targeted at one observed row would be guessing at
the source PDF's intent, not parsing what's printed.

Aircraft/assembly metadata (AC_TYPE, AC_REG, MSN, AC_TSN, AC_CSN, STATUS_DATE,
ASSEMBLY) is parsed once per file from the header block and stamped on every
row, matching every other variant here.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.llp_variants._base import merged_rules

NAME = "e.MES Airframe LLP Status"
SIGNATURES = [
    "Life Limited Part Status",
    "From e.MES",
]

CANONICAL_COLUMNS = [
    "LI",
    "SUB_ASSEMBLY",
    "DESCRIPTION",
    "DETAIL_PART_NUMBER",
    "ASSY_PART_NUMBER",
    "SERIAL_NUMBER",
    "TSO",
    "CSO",
    "DSO",
    "TSN",
    "CSN",
    "LIMIT_CSN",
    "LIMIT_CSO",
    "LIMIT_DSO",
    "REMAIN_CSN",
    "REMAIN_CSO",
    "REMAIN_DSO",
    # File-level metadata -- same on every row
    "AC_TYPE",
    "AC_REG",
    "MSN",
    "AC_TSN",
    "AC_CSN",
    "STATUS_DATE",
    "ASSEMBLY",
]

# LIMIT_CSN of 75000 is real (confirmed above) and exceeds the 55000 cycle
# ceiling other LLP variants in this project use -- their range doesn't fit
# this airframe's numbers.
_CYCLE_RULE = {"pattern": r"^[\d,]+$", "int_range": (0, 100000),
               "int_range_review": (0, 60000)}
# No int_range here: TSO/TSN/AC_TSN carry a real decimal (".53") on every
# row, and shared/cleanup.py's _parse_thousands_int rejects decimals outright
# ("these fields should be whole cycles") -- adding int_range would flag
# every correctly-parsed hour value as not_a_number. Pattern still validates
# shape.
_HOUR_RULE = {"pattern": r"^[\d,]+(?:\.\d+)?$"}
_PN_RULE = {"pattern": r"^[A-Z0-9][A-Z0-9\-]*$", "uppercase": True}

_OVERRIDES = {
    "LI": {"pattern": r"^\d+(-\d+)?$"},
    "DETAIL_PART_NUMBER": _PN_RULE,
    "ASSY_PART_NUMBER": {"pattern": r"^[A-Z0-9][A-Z0-9\-]*$", "uppercase": True,
                          "allow_empty": True},
    "TSO": _HOUR_RULE,
    "TSN": {"pattern": r"^[\d,]+(?:\.\d+)?$",
            "allow_empty": True},  # blank on 3 confirmed rows -- see docstring
    "CSO": _CYCLE_RULE,
    "DSO": _CYCLE_RULE,
    "CSN": _CYCLE_RULE,
    "LIMIT_CSN": _CYCLE_RULE,
    "LIMIT_CSO": _CYCLE_RULE,
    "LIMIT_DSO": _CYCLE_RULE,
    "REMAIN_CSN": _CYCLE_RULE,
    "REMAIN_CSO": _CYCLE_RULE,
    "REMAIN_DSO": _CYCLE_RULE,
    "AC_TYPE": {"pattern": r"^[A-Z0-9]+$", "uppercase": True},
    "AC_REG": {"pattern": r"^[A-Z0-9]+$", "uppercase": True},
    "MSN": {"pattern": r"^\d+$"},
    "AC_TSN": _HOUR_RULE,
    "AC_CSN": _CYCLE_RULE,
    "STATUS_DATE": {"pattern": r"^\d{4}-\d{2}-\d{2}$"},
}
RULES = merged_rules(_OVERRIDES)

_LI_RE = re.compile(r"^\d+(?:-\d+)?$")
_NUM_RE = re.compile(r"^[\d,]+(?:\.\d+)?$")
# Requires an internal hyphen (alnum-alnum) so it can't match a lone "2"
# split off a broken PN -- see the L/I 23 known finding in the docstring.
_PN_TOKEN_RE = re.compile(r"^[A-Za-z0-9]+-[A-Za-z0-9]+$")

_META_RE = re.compile(
    r"A/C Type\s+(?P<ac_type>\S+)\s+A/C #\s+(?P<ac_reg>\S+)\s+MSN\s+(?P<msn>\S+)\s+"
    r"AC TSN\s+(?P<ac_tsn>[\d.]+)\s+AC CSN\s+(?P<ac_csn>\d+)\s+Date\s+(?P<date>\d{4}-\d{2}-\d{2})"
)


def _parse_meta(text: str) -> dict:
    meta: dict[str, str] = {}
    m = _META_RE.search(text)
    if m:
        meta["AC_TYPE"] = m.group("ac_type")
        meta["AC_REG"] = m.group("ac_reg")
        meta["MSN"] = m.group("msn")
        meta["AC_TSN"] = m.group("ac_tsn")
        meta["AC_CSN"] = m.group("ac_csn")
        meta["STATUS_DATE"] = m.group("date")
    lines = text.splitlines()
    for i, line in enumerate(lines):
        # The assembly label ("NOSE LANDING GEAR ASSY" / "MAIN LANDING GEAR
        # ASSY-RH") is a standalone line right after the A/C-identity line --
        # there's no other anchor for it on the page.
        if line.startswith("A/C Type") and i + 1 < len(lines):
            meta["ASSEMBLY"] = lines[i + 1].strip()
            break
    return meta


def _numeric_block(tokens: list[str], size: int) -> list[str] | None:
    if len(tokens) < size:
        return None
    block = tokens[-size:]
    return block if all(_NUM_RE.match(t) for t in block) else None


def _split_pns(pn_tokens: list[str]) -> tuple[str, str, list[str]]:
    """Peel up to 2 PN-shaped tokens off the end; whatever's left is the
    description. Returns (detail_pn, assy_pn, remaining_desc_tokens)."""
    found: list[str] = []
    while pn_tokens and len(found) < 2 and _PN_TOKEN_RE.match(pn_tokens[-1]):
        found.insert(0, pn_tokens.pop())
    if len(found) == 2:
        return found[0], found[1], pn_tokens
    if len(found) == 1:
        return found[0], "", pn_tokens
    return "", "", pn_tokens


def _parse_row(line: str) -> dict | None:
    tokens = line.split()
    if not tokens or not _LI_RE.match(tokens[0]):
        return None
    rest = tokens[1:]

    block = _numeric_block(rest, 11)
    if block is not None:
        head = rest[:-11]
        tso, cso, dso, tsn, csn, lcsn, lcso, ldso, rcsn, rcso, rdso = block
    else:
        block = _numeric_block(rest, 10)
        if block is None:
            return None
        head = rest[:-10]
        tso, cso, dso, csn, lcsn, lcso, ldso, rcsn, rcso, rdso = block
        tsn = ""

    if len(head) < 2:
        return None
    sn = head[-1]
    detail_pn, assy_pn, desc_tokens = _split_pns(head[:-1])
    desc = " ".join(desc_tokens)
    if not desc:
        return None

    rec = {c: "" for c in CANONICAL_COLUMNS}
    rec["LI"] = tokens[0]
    rec["DESCRIPTION"] = desc
    rec["DETAIL_PART_NUMBER"] = detail_pn
    rec["ASSY_PART_NUMBER"] = assy_pn
    rec["SERIAL_NUMBER"] = sn
    rec["TSO"], rec["CSO"], rec["DSO"], rec["TSN"], rec["CSN"] = tso, cso, dso, tsn, csn
    rec["LIMIT_CSN"], rec["LIMIT_CSO"], rec["LIMIT_DSO"] = lcsn, lcso, ldso
    rec["REMAIN_CSN"], rec["REMAIN_CSO"], rec["REMAIN_DSO"] = rcsn, rcso, rdso
    return rec


def _section_header(line: str) -> str | None:
    tokens = line.split()
    if not tokens or not _LI_RE.match(tokens[0]):
        return None
    rest = tokens[1:]
    # Real data rows need >= 1 desc word + 1 PN + S/N + 10 numbers (13+
    # tokens) -- nothing this short can be a genuine row, only a header.
    if len(rest) < 2:
        return None
    if _numeric_block(rest, 10) or _numeric_block(rest, 11):
        return None
    return " ".join(rest)


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        full_text = "\n".join((p.extract_text() or "") for p in pdf.pages)
        meta = _parse_meta(full_text)
        sub_assembly = ""
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            for line in text.splitlines():
                rec = _parse_row(line)
                if rec is not None:
                    rec.update(meta)
                    rec["SUB_ASSEMBLY"] = sub_assembly
                    rec["_page"] = page_num
                    records.append(rec)
                    continue
                header = _section_header(line)
                if header is not None:
                    sub_assembly = header
    return records
