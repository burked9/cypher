"""Gear LLP Status List — "Assemblies >> Gear LLPs >> <ID>" breadcrumb header.

Source format: a per-assembly (landing gear leg) LLP status export. The
header block (repeated on every page) carries the assembly's own PN/SN and
the aircraft it's fitted to:

    Assemblies >> Gear LLPs >> B73
    Part No.: 10-113104-002 Install Date: 25-01-2016 Status at: 08/01/2018
    Serial No.: B73 TSN: 54645:48 CSN: 6023
    A/C Pos: G-VWIN #CTMLG
    Description Serial No. Part No. FH Interval FH Used FH Remaining FC Interval FC Used FC Remaining

Row format (single line, space-separated) when the description is short
enough to fit next to everything else:

    BRAKE ROD B04-315 50-1116005-00 20600.00 6023 14577

FC-only rows (3 trailing numbers) are the common case — most gear LLPs are
cycle-limited, not hour-limited. Hour-limited parts print 6 trailing numbers
(FH interval/used/remaining THEN FC interval/used/remaining):

    TUBE-HOLDING 14B0049X00003 55-1105370-00 105650:00 6386:04 99263:56 17410.00 863 16547

FH values use HH:MM colon notation; FC values are plain integers, sometimes
suffixed ".00" for no discernible reason (inconsistent even within one
file) — stripped at parse time so the cycle columns stay comparable ints.

The real wrinkle: whenever DESCRIPTION is too long to sit on the row's own
baseline, pdfplumber's line-grouping splits it across the line ABOVE and the
line BELOW the SN/PN/numbers line (the wrapped text is taller than the
single-line SN/PN/number cells, so the two description fragments land on
their own lines, with the data line sandwiched between them):

    PIN-RETRACTION
    0065 G53323625200 16600 6179 10421
    ACTUATOR CLG

is one logical row: DESCRIPTION="PIN-RETRACTION ACTUATOR CLG", SN="0065",
PN="G53323625200". We anchor on the trailing numeric run (3 or 6 tokens); if
the line it's found on has no leading description tokens of its own, the
previous non-data line is borrowed as the description prefix and the
following non-data line (if any) as its suffix.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.llp_variants._base import merged_rules

NAME = "Gear LLP Status List"
SIGNATURES = [
    "Assemblies >> Gear LLPs",
    "FH Interval FH Used FH Remaining",
]

CANONICAL_COLUMNS = [
    "DESCRIPTION",
    "SERIAL_NUMBER",
    "PART_NUMBER",
    "FH_INTERVAL",
    "FH_USED",
    "FH_REMAINING",
    "FC_INTERVAL",
    "FC_USED",
    "FC_REMAINING",
    # Assembly (gear leg) + aircraft metadata — same on every row of a file
    "ASSEMBLY_PART_NUMBER",
    "ASSEMBLY_SERIAL_NUMBER",
    "INSTALL_DATE",
    "STATUS_DATE",
    "ASSEMBLY_TSN",
    "ASSEMBLY_CSN",
    "AC_REGISTRATION",
    "AC_POSITION",
]

_FH_RULE = {"pattern": r"^\d+:\d{2}$", "allow_empty": True}
_FC_RULE = {"pattern": r"^\d+$", "int_range": (0, 55000),
            "int_range_review": (0, 30000), "allow_empty": True}
_OVERRIDES = {
    "FH_INTERVAL":  _FH_RULE,
    "FH_USED":      _FH_RULE,
    "FH_REMAINING": _FH_RULE,
    "FC_INTERVAL":  _FC_RULE,
    "FC_USED":      _FC_RULE,
    "FC_REMAINING": _FC_RULE,
    "ASSEMBLY_PART_NUMBER":   {"pattern": r"^[A-Z0-9\-./]+$", "uppercase": True},
    "ASSEMBLY_SERIAL_NUMBER": {"pattern": r"^[A-Z0-9\-]+$", "uppercase": True},
    "INSTALL_DATE": {"pattern": r"^\d{2}[-/]\d{2}[-/]\d{4}$"},
    "STATUS_DATE":  {"pattern": r"^\d{2}[-/]\d{2}[-/]\d{4}$"},
    # TSN mixes HH:MM ("54645:48") and decimal-hours ("52095.43") across
    # files -- no int_range, the shared thousands parser understands neither.
    "ASSEMBLY_TSN": {"pattern": r"^\d+[:.]\d+$"},
    "ASSEMBLY_CSN": {"pattern": r"^\d+$", "int_range": (0, 55000),
                      "int_range_review": (0, 30000)},
    "AC_REGISTRATION": {"pattern": r"^[A-Z0-9\-]+$", "uppercase": True},
    "AC_POSITION":     {"pattern": r"^[A-Z0-9/]+$", "uppercase": True},
}
RULES = merged_rules(_OVERRIDES)

# Numeric trailing tokens: plain ints, HH:MM colon time, or dot-decimal.
_NUM_TOKEN_RE = re.compile(r"^\d[\d:.,]*$")
_PN_RE = re.compile(r"^[A-Z0-9][A-Z0-9\-./]*$", re.I)
_PAGE_FOOTER_RE = re.compile(r"^Page \d+ of \d+$")

_SKIP_FRAGMENTS = (
    "Assemblies >>",
    "Part No.:",
    "Serial No.:",
    "A/C Pos:",
    "Description Serial No. Part No.",
)

_HEADER_RE = re.compile(
    r"Part No\.:\s*(?P<pn>\S+)\s+Install Date:\s*(?P<install>\S+)"
    r"\s+Status at:\s*(?P<status>\S+)"
)
_SN_LINE_RE = re.compile(
    r"Serial No\.:\s*(?P<sn>\S+)\s+TSN:\s*(?P<tsn>\S+)\s+CSN:\s*(?P<csn>\S+)"
)
_ACPOS_RE = re.compile(r"A/C Pos:\s*(?P<reg>[A-Z0-9\-]+)\s*#(?P<pos>\S+)")


def _is_num(tok: str) -> bool:
    return bool(_NUM_TOKEN_RE.match(tok))


def _is_skip_line(line: str) -> bool:
    if _PAGE_FOOTER_RE.match(line):
        return True
    return any(frag in line for frag in _SKIP_FRAGMENTS)


def _strip_dot_zero(tok: str) -> str:
    return tok[:-3] if tok.endswith(".00") else tok


def _parse_meta(text: str) -> dict:
    meta: dict[str, str] = {}
    m = _HEADER_RE.search(text)
    if m:
        meta["ASSEMBLY_PART_NUMBER"] = m.group("pn")
        meta["INSTALL_DATE"] = m.group("install")
        meta["STATUS_DATE"] = m.group("status")
    m = _SN_LINE_RE.search(text)
    if m:
        meta["ASSEMBLY_SERIAL_NUMBER"] = m.group("sn")
        meta["ASSEMBLY_TSN"] = m.group("tsn")
        meta["ASSEMBLY_CSN"] = m.group("csn")
    m = _ACPOS_RE.search(text)
    if m:
        meta["AC_REGISTRATION"] = m.group("reg")
        meta["AC_POSITION"] = m.group("pos")
    return meta


def _split_trail(raw_trail: list[str]) -> tuple[list[str] | None, list[str]]:
    """Only 3 (FC only) or 6 (FH+FC) trailing numeric cells are ever printed,
    but a handful of PNs are bare digit strings (e.g. "201442651") that look
    numeric too and get swept into the greedy walk. Peel off anything beyond
    the nearest valid group size and hand it back to `head`."""
    n = len(raw_trail)
    if n >= 6:
        return raw_trail[-6:], raw_trail[:-6]
    if n >= 3:
        return raw_trail[-3:], raw_trail[:-3]
    return None, raw_trail


def _parse_line(line: str) -> dict | None:
    toks = line.split()
    if not toks:
        return None
    i = len(toks)
    raw_trail: list[str] = []
    while i > 0 and _is_num(toks[i - 1]):
        raw_trail.insert(0, toks[i - 1])
        i -= 1
    trail, extra = _split_trail(raw_trail)
    if trail is None:
        return None
    head = toks[:i] + extra
    if not head:
        return None
    if len(head) == 1:
        # SN itself got line-wrapped away from its own row (rare) -- PN
        # survives, SN doesn't; nothing downstream requires SN to be set.
        sn, pn, desc = "", head[0], ""
    else:
        sn, pn, desc = head[-2], head[-1], " ".join(head[:-2])
    if not _PN_RE.match(pn) or (sn and not _PN_RE.match(sn)):
        return None
    return {"desc": desc, "sn": sn, "pn": pn, "trail": trail}


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        full_text = "\n".join((p.extract_text() or "") for p in pdf.pages)
        meta = _parse_meta(full_text)
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if len(text) < 50:
                continue
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            lines = [ln for ln in lines if not _is_skip_line(ln)]

            pending_pre: str | None = None
            i = 0
            while i < len(lines):
                parsed = _parse_line(lines[i])
                if parsed is None:
                    pending_pre = lines[i]
                    i += 1
                    continue

                desc_parts = []
                if parsed["desc"]:
                    desc_parts.append(parsed["desc"])
                elif pending_pre is not None:
                    desc_parts.append(pending_pre)
                pending_pre = None

                if (not parsed["desc"] and i + 1 < len(lines)
                        and _parse_line(lines[i + 1]) is None):
                    desc_parts.append(lines[i + 1])
                    i += 1

                rec = {c: "" for c in CANONICAL_COLUMNS}
                rec["DESCRIPTION"] = " ".join(desc_parts).strip()
                rec["SERIAL_NUMBER"] = parsed["sn"]
                rec["PART_NUMBER"] = parsed["pn"]
                trail = parsed["trail"]
                if len(trail) == 6:
                    (rec["FH_INTERVAL"], rec["FH_USED"], rec["FH_REMAINING"],
                     rec["FC_INTERVAL"], rec["FC_USED"], rec["FC_REMAINING"]) = trail
                else:
                    rec["FC_INTERVAL"], rec["FC_USED"], rec["FC_REMAINING"] = trail
                for k in ("FC_INTERVAL", "FC_USED", "FC_REMAINING"):
                    rec[k] = _strip_dot_zero(rec[k])
                for k, v in meta.items():
                    rec[k] = v
                rec["_page"] = page_num
                records.append(rec)
                i += 1
    return records
