"""C.A.I. FIRST S.p.A. landing-gear LLP — "<Gear> Life Limited Parts Summary".

Source format: an Italian CAMO (C.A.I. FIRST S.p.A.) issues one summary per
landing gear (NLG / LH MLG / RH MLG), either as a single-gear sheet or, for a
"Certified Current Status" cert, all three gears as separate pages of one
PDF. Two very different text layers show up under this one visual template:
one file has a native/clean text layer, the other three are scans with an
OCR text layer that mangles letters badly (font-shape confusions: "I"->"|" or
"l", "life"->"erel", missing inter-word spaces) while digits mostly survive.

Clean-text data row (native PDF, one line per part):
    Nose Landing Gear 170-70404-403 00032 11956 11956 0 0 10-Jun-04 0 30000 4380 48000 18044 1593 36044
    <-desc-------------><-PN--------><SN--><CSN-><CSO-><mfg/ovh-><ics><ico><inst.date><ac.cyc><ovh lim cyc><ovh lim days><life lim cyc><ovh rem cyc><ovh rem days><life rem cyc>

Same row, OCR'd (I002 NLG LLP SEHEET.pdf):
    nlg shockstrut 170-70405403 00032 11962 11982 21may-04 0 0 10-jun-04 0 300004380 18038 1573

The 16 columns come straight off the PDF's own ruling-line grid (verified via
pdfplumber's lattice `extract_table()` on the clean file) under three grouped
header rows: Current Cycles{Since New, Since O/H}, Data @ Installation{Mfg/
Ovh Date, CSN, CSO, Date, A/C Cycles}, Limits{Overhaul Cycles/Days, Life
Cycles}, Remaining{Overhaul Cycles/Days, Life Cycles}. MFG_OVH_DATE is
genuinely blank on assembly-level rows (not "0" — the token disappears), and
the LIFE_LIMIT/LIFE_REMAIN pair is genuinely blank on parts with no hard
cycle life (shock struts, drag braces, locking stays).

OCR reliably drops the thin gaps between the two constant MRB-interval
columns ("30000"+"4380" -> "300004380") and between a date and the field
right after it ("22-apr-04"+"0" -> "22-apr-040"); both are undone before
tokenising. On the worst scans (STATUS/SEHEET) even the PN/SN separator can
vanish, fusing PART_NUMBER and SERIAL_NUMBER into one digit blob with no
recoverable split point -- SERIAL_NUMBER is left blank rather than guessed.

Row anchor, since column count varies with the two optional fields above:
walk in from the right collecting tokens that are bare integers or dates
(the numeric tail); walk the remainder in from the right collecting
digit-bearing tokens (PART_NUMBER, and SERIAL_NUMBER when it didn't fuse into
the numeric tail as its own token); whatever's left is DESCRIPTION.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.llp_variants._base import merged_rules

NAME = "CAI First Landing Gear LLP"
SIGNATURES = [
    # The producer's VAT number -- pure digits, so it is the one header
    # token that survives OCR intact on all three scanned samples ("Life
    # Limited Parts Summary" itself does not: "Limited" comes back as
    # "limilted"/"limlted" with the OCR engine's I/l confusion).
    "06331890969",
    "ERJ170-100LR",
]

CANONICAL_COLUMNS = [
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "CSN",
    "CSO",
    "MFG_OVH_DATE",
    "INSTALL_CSN",
    "INSTALL_CSO",
    "INSTALL_DATE",
    "INSTALL_AC_CYCLES",
    "OVERHAUL_LIMIT_CYCLES",
    "OVERHAUL_LIMIT_DAYS",
    "LIFE_LIMIT_CYCLES",
    "OVERHAUL_REMAIN_CYCLES",
    "OVERHAUL_REMAIN_DAYS",
    "LIFE_REMAIN_CYCLES",
    # Header metadata -- same on every row of a given page
    "GEAR",
    "ACFT_MODEL",
    "ACFT_REGISTRATION",
    "MSN",
    "AC_TSN",
    "AC_CSN",
    "MFG_DATE",
    "STATUS_DATE",
]

_CYCLE_RULE = {"pattern": r"^\d+$", "int_range": (0, 55000),
               "int_range_review": (0, 30000)}
_HOUR_RULE  = {"pattern": r"^\d+$", "int_range": (0, 80000)}
_DAY_RULE   = {"pattern": r"^\d+$", "int_range": (0, 10000)}
_DATE_RULE  = {"pattern": r"^\d{1,2}-[A-Za-z]{3}-\d{2,4}$"}

_OVERRIDES = {
    "CSN": _CYCLE_RULE, "CSO": _CYCLE_RULE,
    "INSTALL_CSN": _CYCLE_RULE, "INSTALL_CSO": _CYCLE_RULE,
    "INSTALL_AC_CYCLES": _CYCLE_RULE,
    "OVERHAUL_LIMIT_CYCLES": _CYCLE_RULE,
    "LIFE_LIMIT_CYCLES": _CYCLE_RULE,
    "OVERHAUL_REMAIN_CYCLES": _CYCLE_RULE,
    "LIFE_REMAIN_CYCLES": _CYCLE_RULE,
    "OVERHAUL_LIMIT_DAYS": _DAY_RULE,
    "OVERHAUL_REMAIN_DAYS": _DAY_RULE,
    "AC_TSN": _HOUR_RULE,
    "AC_CSN": _CYCLE_RULE,
    "MFG_OVH_DATE": _DATE_RULE, "INSTALL_DATE": _DATE_RULE,
    "MFG_DATE": _DATE_RULE, "STATUS_DATE": _DATE_RULE,
    "ACFT_REGISTRATION": {"pattern": r"^[A-Z]{1,2}-[A-Z]{3,4}$", "uppercase": True},
}
RULES = merged_rules(_OVERRIDES)

# Month letters allow 2-4 chars (not the usual 3) because the OCR'd files
# mangle month abbreviations ("nov" -> "ch") but keep the day-hyphen-year
# shape intact; the leading day/hyphen is also allowed to fuse ("21may-04").
_DATE_RE = re.compile(r"^\d{1,2}-?[A-Za-z]{2,4}-\d{2,4}$")
_NUM_RE = re.compile(r"^\d+$")
_FUSED_MRB_RE = re.compile(r"^30000(\d{4})$")
_FUSED_DATE_TAIL_RE = re.compile(r"^(\d{1,2}-?[A-Za-z]{2,4}-\d{2,4})(\d{1,2})$")

_TAIL_BASE_FIELDS = (
    "INSTALL_CSN", "INSTALL_CSO", "INSTALL_DATE", "INSTALL_AC_CYCLES",
    "OVERHAUL_LIMIT_CYCLES", "OVERHAUL_LIMIT_DAYS",
)


def _normalize_tokens(tokens: list[str]) -> list[str]:
    out = []
    for t in tokens:
        m = _FUSED_DATE_TAIL_RE.match(t)
        if m:
            out.append(m.group(1))
            out.append(m.group(2))
            continue
        m2 = _FUSED_MRB_RE.match(t)
        if m2:
            out.append("30000")
            out.append(m2.group(1))
            continue
        out.append(t)
    return out


def _is_tailish(tok: str) -> bool:
    return bool(_NUM_RE.match(tok) or _DATE_RE.match(tok))


def _looks_like_bare_sn(tok: str) -> bool:
    """S/Ns here are zero-padded (00032, 0059); current CSN/CSO never are --
    these are mature airframes always well into 4-5 digit cycle counts."""
    return tok.startswith("0") and tok != "0" and len(tok) >= 4


def _parse_row(line: str) -> dict | None:
    s = line.strip()
    if not s:
        return None
    tokens = _normalize_tokens(s.split())
    if len(tokens) < 5:
        return None

    i = len(tokens)
    while i > 0 and _is_tailish(tokens[i - 1]):
        i -= 1
    tail = tokens[i:]
    head = tokens[:i]
    if len(tail) < 2:
        return None

    j = len(head)
    while j > 0 and any(c.isdigit() for c in head[j - 1]):
        j -= 1
    desc_tokens = head[:j]
    pn_sn_tokens = head[j:]
    if not desc_tokens:
        return None

    if len(pn_sn_tokens) >= 2:
        part_number, serial_number = pn_sn_tokens[-2], pn_sn_tokens[-1]
    elif len(pn_sn_tokens) == 1:
        only = pn_sn_tokens[0]
        # A bare-digit S/N reads as just another tail number until we pull
        # it back out; CSN==CSO (never overhauled) is the fallback tell when
        # OCR has also scrubbed its leading zero.
        if len(tail) >= 3 and len(only) <= 16 and (
            _looks_like_bare_sn(tail[0]) or tail[1] == tail[2]
        ):
            part_number, serial_number = only, tail[0]
            tail = tail[1:]
        else:
            part_number, serial_number = only, ""
    else:
        # Worst scans drop every hyphen AND the PN/SN join, so the whole
        # PN+SN run lands as tail[0] as one long digit blob. A real CSN/CSO
        # is never anywhere near this long -- no false positive here.
        if tail and len(tail[0]) >= 15:
            part_number, serial_number = tail[0], ""
            tail = tail[1:]
        else:
            return None

    if len(tail) < 2:
        return None
    csn, cso, more = tail[0], tail[1], tail[2:]

    rec = {c: "" for c in CANONICAL_COLUMNS}
    rec["DESCRIPTION"] = " ".join(desc_tokens)
    rec["PART_NUMBER"] = part_number
    rec["SERIAL_NUMBER"] = serial_number
    rec["CSN"] = csn
    rec["CSO"] = cso

    if more and _DATE_RE.match(more[0]):
        rec["MFG_OVH_DATE"] = more.pop(0)
    for name in _TAIL_BASE_FIELDS:
        if not more:
            break
        rec[name] = more.pop(0)

    if len(more) == 4:
        (rec["LIFE_LIMIT_CYCLES"], rec["OVERHAUL_REMAIN_CYCLES"],
         rec["OVERHAUL_REMAIN_DAYS"], rec["LIFE_REMAIN_CYCLES"]) = more
    elif len(more) >= 2:
        # 2 is the documented shape (no life-limit pair); anything else here
        # is scan noise -- keep the trailing pair, since Remaining(Overhaul)
        # prints far more consistently across samples than Remaining(Life).
        rec["OVERHAUL_REMAIN_CYCLES"], rec["OVERHAUL_REMAIN_DAYS"] = more[-2:]

    return rec


_ACFT_MODEL_RE = re.compile(r"(?i)ERJ-?\d{3}-\d{3}[A-Z]{0,3}")
_REG_RE = re.compile(r"(?i)REGISTRATION:?\s*([A-Z]{1,2}-[A-Z]{3,4})")
_MSN_RE = re.compile(r"(?i)MSN:?\s*(\d{3,9})")
_TSN_RE = re.compile(r"(?i)TSN:?\s*(\d{2,7})")
_CSN_HDR_RE = re.compile(r"(?i)CSN:?\s*(\d{2,7})")
_MFGDATE_RE = re.compile(r"(?i)MFG\s*DATE:?\s*(\d{1,2}-?[A-Za-z]{2,4}-\d{2,4})")
_STATUSDATE_RE = re.compile(r"(?i)STATUS\s*DATE:?\s*(\d{1,2}-?[A-Za-z]{2,4}-\d{2,4})")
_GEAR_RH_RE = re.compile(r"(?i)RH\s*MLG")
_GEAR_LH_RE = re.compile(r"(?i)LH\s*MLG")
_GEAR_NLG_RE = re.compile(r"(?i)N\s*L\s*G")


def _find_gear(head: str) -> str:
    # Order matters: MLG pages also contain "NLG"-shaped noise nowhere, but
    # checking the two-letter-prefixed gears first keeps this unambiguous.
    if _GEAR_RH_RE.search(head):
        return "RH MLG"
    if _GEAR_LH_RE.search(head):
        return "LH MLG"
    if _GEAR_NLG_RE.search(head):
        return "NLG"
    return ""


def _parse_header_meta(head: str) -> dict:
    meta: dict[str, str] = {}
    m = _ACFT_MODEL_RE.search(head)
    if m:
        meta["ACFT_MODEL"] = m.group(0).upper()
    m = _REG_RE.search(head)
    if m:
        meta["ACFT_REGISTRATION"] = m.group(1).upper()
    m = _MSN_RE.search(head)
    if m:
        meta["MSN"] = m.group(1)
    m = _TSN_RE.search(head)
    if m:
        meta["AC_TSN"] = m.group(1)
    m = _CSN_HDR_RE.search(head)
    if m:
        meta["AC_CSN"] = m.group(1)
    m = _MFGDATE_RE.search(head)
    if m:
        meta["MFG_DATE"] = m.group(1)
    m = _STATUSDATE_RE.search(head)
    if m:
        meta["STATUS_DATE"] = m.group(1)
    return meta


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if len(text) < 50:
                continue
            head = text[:600]
            gear = _find_gear(head)
            meta = _parse_header_meta(head)
            for line in text.splitlines():
                rec = _parse_row(line)
                if rec is None:
                    continue
                rec["GEAR"] = gear
                for k, v in meta.items():
                    rec[k] = v
                rec["_page"] = page_num
                records.append(rec)
    return records
