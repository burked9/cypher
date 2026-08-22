"""VN-registered "HT-LL STATUS" / "HT&LLP STATUS" hard-time report.

Header (page 1 only for the STATUS sub-format; repeated per page for the
REMAINING-LIFE sub-format)::

    AIRCRAFT REGISTRATION: VN-A344
    HT-LL STATUS AIRCRAFT SERIAL NUMBER 2255
    CURRENT AIRCRAFT FH: 37524.7 AIRCRAFT MODEL & TYPE: 1 ACT
    CURRENT AIRCRAFT CY: 24511 REPORT DATE: 10/07/19
    NO. ATA DESCRIPTION FIN PART NUMBER SERIAL NUMBER ...

Two sibling sub-formats share this header style and the same leading
`NO. ATA DESCRIPTION FIN PART NUMBER SERIAL NUMBER` columns, but diverge
completely in what follows -- confirmed by inspecting actual page text and
word x-positions (a generic ATA-anchored line check quietly mis-shifted or
dropped most rows of both, since neither has a plain "ATA-starts-the-line"
shape once the row number is accounted for).

STATUS sub-format ("HT-LL STATUS" -- A344/A348/A349 in the corpus). Fixed
8 numeric-or-"UNK" fields then a date, e.g.::

    1 21 VALVE-SAFETY 6HL 9024-15704-03 0932254 28011.4 18382 17539.25 8989 9513.3 6129 27052.55 15118 13-Apr-16

    NO ATA DESC FIN PN SN AC_FH_AT_INSTALL AC_CY_AT_INSTALL COMP_FH_AT_INSTALL
    COMP_CY_AT_INSTALL TSI_FH TSI_CY TSN_FH TSN_CY INSTALLED_DATE

"UNK" (component time-at-install unknown) and the sentinel "999995"
(component time-since-new uncapped) both appear in place of real numbers.
Parsed by tokenizing the line and anchoring on the trailing date + 8
numeric/UNK fields, then walking backwards -- same strategy as
occm_variants/standard_occm.py, adapted for the UNK sentinel.

REMAINING-LIFE sub-format ("HT&LLP STATUS" -- A345 in the corpus). This is
the genuine hard-time data the STATUS sub-format lacks: up to 4 independent
(LIMIT, REMAINING) pairs -- one each for FH / CY / DY (days) / CAL -- of
which a given row populates only the limit types that actually apply to
that component. E.g.::

    2 21 VALVE-SAFETY 7HL 9024-15704-03 1532061 34966.47 23222 50000 47492 6390 5938 6390 4918 2-Jul-2018

has FH, DY and CAL pairs (6 numbers) but no CY pair; a life-of-aircraft
bracket elsewhere has only a CAL pair and no AC_FH/AC_CY at all (2 numbers).
Column *count* alone can't say which pair is missing -- the row has to be
read by x-position against the header's own column layout::

    FH   CY   FH     RE_FH   CY     RE_CY   DY     RE_DY   CAL    RE_CAL
    x314 x360 x402   x442    x487   x524    x566   x608    x653   x695

(x-positions in points, read once via pdfplumber `extract_words`; stable
across pages because this is a fixed computer-generated template). Columns
are left-aligned so a long value only grows its x1, never shifts its x0 --
safe to bucket on x0 alone. Dates here carry a 4-digit year, unlike the
STATUS sub-format's 2-digit year.

Both sub-formats occasionally glue the FIN column onto the last word of
DESCRIPTION with no space when the description overflows its column width
("TRANSMITTER-PR4HT" vs the same part unglued elsewhere as "TRANSMITTER-PRESS
4HT") -- this is in the source PDF's own text stream, not a pdfplumber
artifact (confirmed at the word level), so it can't be split back apart
reliably. We keep the glued form as FIN rather than guess, same call
standard_occm.py makes for its own unsplittable column.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.ht_variants._base import merged_rules

NAME = "HT-LL Status"
SIGNATURES = [
    "HT-LL STATUS",
    "HT&LLP STATUS",
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
    "LIMIT_FH",
    "REMAINING_FH",
    "LIMIT_CY",
    "REMAINING_CY",
    "LIMIT_DY",
    "REMAINING_DY",
    "LIMIT_CAL",
    "REMAINING_CAL",
    "INSTALLED_DATE",
]

_FH_RULE = {"pattern": r"^\d+(?:\.\d+)?$|^UNK$", "allow_empty": True}
_CY_RULE = {"pattern": r"^\d+$|^UNK$", "allow_empty": True}
_REMAINING_LIFE_RULE = {"pattern": r"^\d+(?:\.\d+)?$", "allow_empty": True}

_OVERRIDES = {
    "FIN": {"allow_empty": True},
    "AC_FH_AT_INSTALL": {"pattern": r"^\d+(?:\.\d+)?$", "allow_empty": True},
    "AC_CY_AT_INSTALL": {"pattern": r"^\d+$", "allow_empty": True},
    "COMP_FH_AT_INSTALL": _FH_RULE,
    "TSI_FH": _FH_RULE,
    "TSN_FH": _FH_RULE,
    "COMP_CY_AT_INSTALL": _CY_RULE,
    "TSI_CY": _CY_RULE,
    "TSN_CY": _CY_RULE,
    "LIMIT_FH": _REMAINING_LIFE_RULE,
    "REMAINING_FH": _REMAINING_LIFE_RULE,
    "LIMIT_CY": _REMAINING_LIFE_RULE,
    "REMAINING_CY": _REMAINING_LIFE_RULE,
    "LIMIT_DY": _REMAINING_LIFE_RULE,
    "REMAINING_DY": _REMAINING_LIFE_RULE,
    "LIMIT_CAL": _REMAINING_LIFE_RULE,
    "REMAINING_CAL": _REMAINING_LIFE_RULE,
    "INSTALLED_DATE": {"pattern": r"^\d{1,2}-[A-Za-z]{3}-\d{2,4}$"},
}
RULES = merged_rules(_OVERRIDES)

_ATA_RE = re.compile(r"^\d{2}$")
_DATE_RE = re.compile(r"^\d{1,2}-[A-Za-z]{3}-\d{2,4}$")
_NUM_OR_UNK_RE = re.compile(r"^(?:\d+(?:\.\d+)?|UNK)$")


def _valid_ata(tok: str) -> bool:
    return bool(_ATA_RE.match(tok)) and 20 <= int(tok) <= 83


def _split_desc_fin_pn_sn(head: list[str]) -> tuple[str, str, str, str] | None:
    if len(head) < 3:
        return None
    pn, sn = head[-2], head[-1]
    remaining = head[:-2]
    last = remaining[-1]
    # A real FIN always mixes letters and digits (6HL, 1000EM1, and the
    # glued "RH2506"). A bare digit here is a position suffix on the
    # description itself (e.g. "AXLE SLEEVE 1"), not a FIN -- checking
    # for a digit alone would wrongly steal that word out of DESCRIPTION.
    if (len(remaining) >= 2
            and any(c.isdigit() for c in last) and any(c.isalpha() for c in last)):
        fin, desc = last, " ".join(remaining[:-1])
    else:
        fin, desc = "", " ".join(remaining)
    if not desc:
        return None
    return desc, fin, pn, sn


def _new_record(ata: str, desc: str, fin: str, pn: str, sn: str, date: str, page_num: int) -> dict:
    rec = {c: "" for c in CANONICAL_COLUMNS}
    rec["ATA"] = ata
    rec["DESCRIPTION"] = desc
    rec["FIN"] = fin
    rec["PART_NUMBER"] = pn
    rec["SERIAL_NUMBER"] = sn
    rec["INSTALLED_DATE"] = date
    rec["_page"] = page_num
    return rec


def _parse_status_row(line: str, page_num: int) -> dict | None:
    tokens = line.strip().split()
    if not tokens or not tokens[0].isdigit():
        return None
    tokens = tokens[1:]                      # drop the leading row number
    if len(tokens) < 13 or not _valid_ata(tokens[0]) or not _DATE_RE.match(tokens[-1]):
        return None
    nums = tokens[-9:-1]
    if len(nums) != 8 or not all(_NUM_OR_UNK_RE.match(n) for n in nums):
        return None
    split = _split_desc_fin_pn_sn(tokens[1:-9])
    if split is None:
        return None
    desc, fin, pn, sn = split
    rec = _new_record(tokens[0], desc, fin, pn, sn, tokens[-1], page_num)
    rec["AC_FH_AT_INSTALL"], rec["AC_CY_AT_INSTALL"] = nums[0], nums[1]
    rec["COMP_FH_AT_INSTALL"], rec["COMP_CY_AT_INSTALL"] = nums[2], nums[3]
    rec["TSI_FH"], rec["TSI_CY"] = nums[4], nums[5]
    rec["TSN_FH"], rec["TSN_CY"] = nums[6], nums[7]
    return rec


# Column x0s for the 10 possible numeric slots on a REMAINING-LIFE row,
# read once off the header's own word positions (see module docstring).
# Boundaries sit at the midpoints between slots -- gaps are >=25pt so
# there's no realistic ambiguity.
_METRIC_SLOTS = [
    (300, 345, "AC_FH_AT_INSTALL"),
    (345, 385, "AC_CY_AT_INSTALL"),
    (385, 426, "LIMIT_FH"),
    (426, 469, "REMAINING_FH"),
    (469, 510, "LIMIT_CY"),
    (510, 550, "REMAINING_CY"),
    (550, 592, "LIMIT_DY"),
    (592, 636, "REMAINING_DY"),
    (636, 680, "LIMIT_CAL"),
    (680, 725, "REMAINING_CAL"),
]
# SERIAL NUMBER's header ends ~x1=298; the first metric column starts
# ~x0=314. Columns are left-aligned, so a wide SN only grows x1 -- x0 stays
# put, which is what makes a flat 300pt cutoff safe regardless of SN length.
_METRIC_X0_START = 300


def _slot_for_x0(x0: float) -> str | None:
    for lo, hi, name in _METRIC_SLOTS:
        if lo <= x0 < hi:
            return name
    return None


def _iter_word_lines(page):
    lines: dict[float, list[dict]] = {}
    for w in page.extract_words():
        lines.setdefault(round(w["top"], 1), []).append(w)
    for top in sorted(lines):
        yield sorted(lines[top], key=lambda w: w["x0"])


def _parse_remaining_row(ws: list[dict], page_num: int) -> dict | None:
    toks = [w["text"] for w in ws]
    if not toks or not toks[0].isdigit():
        return None
    if len(toks) < 2 or not _valid_ata(toks[1]) or not _DATE_RE.match(toks[-1]):
        return None
    head_ws = [w for w in ws[2:] if w["x0"] < _METRIC_X0_START]
    split = _split_desc_fin_pn_sn([w["text"] for w in head_ws])
    if split is None:
        return None
    desc, fin, pn, sn = split
    rec = _new_record(toks[1], desc, fin, pn, sn, toks[-1], page_num)
    for w in ws[2 + len(head_ws):-1]:
        slot = _slot_for_x0(w["x0"])
        if slot:
            rec[slot] = w["text"]
    return rec


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        if not pdf.pages:
            return records
        remaining_life = "HT&LLP STATUS" in (pdf.pages[0].extract_text() or "")
        for page_num, page in enumerate(pdf.pages, start=1):
            if remaining_life:
                for ws in _iter_word_lines(page):
                    rec = _parse_remaining_row(ws, page_num)
                    if rec is not None:
                        records.append(rec)
            else:
                text = page.extract_text() or ""
                if len(text) < 100:
                    continue
                for line in text.splitlines():
                    rec = _parse_status_row(line, page_num)
                    if rec is not None:
                        records.append(rec)
    return records
