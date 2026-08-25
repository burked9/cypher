"""Thai landing-gear LLP status -- "<n> THAI LANDING GEAR LIFE LIMITED PARTS
STATUS" (confirmed on a real source file). Despite its filename following
the same "<MSN>_E307_LLP_Inventory_<position>_<date>" convention as the
Boeing-737 TP-023/TP-024 files this cluster also contains, the header, row
grammar and even the airline are unrelated -- b737_gear_llp_inventory.py's
own docstring notes exactly this kind of filename-vs-content mismatch for a
different pair of files, and it recurs here.

No text layer (confirmed with pdfplumber: 0 chars on every page) but reads
cleanly via plain OCR at the OCR helper's usual 300dpi/psm 6 -- unlike
kalstar_aviation_llp_status.py's scan, cell gaps survive intact at that
setting on every row checked, so there was no need to chase a higher DPI
here.

One row per part::

    UPPER SHORTENING LINK S/A 201428359 HSM/MDM/0677/98 55088 24875 75000
    50000 19912 25125

    DESCRIPTION PART_NUMBER SERIAL_NUMBER TSN CSN LIFE_LIMIT_HOURS
    LIFE_LIMIT_CYCLES REMAIN_HOURS REMAIN_CYCLES

PART_NUMBER anchors the row: always 6+ plain digits with an optional
`-NNN` suffix, which SERIAL_NUMBER and DESCRIPTION never are -- including
DESCRIPTION, which rules out the more obvious "first token with a digit"
anchor (several descriptions carry a short parenthetical code that does
contain one, e.g. "PIN-LOWER TORQUE LINK(TL3)", "PIN-SM7(UPPER LINK)").
That trade-off does cost the two rows whose PART_NUMBER is itself a
hardware-standard callout instead of a house part number ("NAS6606D10",
"MS21250H06016") -- confirmed dropped on the one file that has them, and
left that way rather than widening the anchor back into the parenthetical
false positives it was narrowed to avoid.

Trailing fields are read left-to-right, not bucketed by position from the
right, because a small number of on-condition parts replace all 4 life-limit/
remaining figures with a free-text remark after TSN/CSN instead of printing
them ("PIVOT LINK BRACKET BOLT NAS6606D10 UNK 26109 11923 MUST BE REPLACED
BY A NEW ONE EVERY TIME...") -- captured whole into REMARKS rather than
forced into 4 numeric columns it doesn't have.
"""
from __future__ import annotations
import re

import fitz
import pytesseract
from PIL import Image

from sheet_types.llp_variants._base import merged_rules

NAME = "Thai Landing Gear LLP Status"
SIGNATURES = [
    "LANDING GEAR LIFE LIMITED PARTS STATUS",
    "REPORT TIME :",
]

CANONICAL_COLUMNS = [
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "TSN",
    "CSN",
    "LIFE_LIMIT_HOURS",
    "LIFE_LIMIT_CYCLES",
    "REMAIN_HOURS",
    "REMAIN_CYCLES",
    "REMARKS",
    # File-level metadata -- same on every row.
    "TOP_DESCRIPTION",
    "TOP_PART_NUMBER",
    "TOP_SERIAL_NUMBER",
    "OVERHAULED_DATE",
    "AIRCRAFT_REG",
    "MSN",
    "AC_FH",
    "AC_FC",
    "IN_AIRCRAFT_DATE",
    "GEAR_TSN",
    "GEAR_TSO",
    "GEAR_CSN",
    "GEAR_CSO",
    "REPORT_DATE",
    "REPORT_TIME",
]

_HOUR_CYCLE_RULE = {"pattern": r"^(N/?A|NIA|[\d,]+)$", "allow_empty": True}
_OVERRIDES = {
    "TSN": {"pattern": r"^[\d.,]+$"},
    "CSN": {"pattern": r"^[\d,]+$"},
    "LIFE_LIMIT_HOURS": _HOUR_CYCLE_RULE,
    "LIFE_LIMIT_CYCLES": _HOUR_CYCLE_RULE,
    "REMAIN_HOURS": _HOUR_CYCLE_RULE,
    "REMAIN_CYCLES": _HOUR_CYCLE_RULE,
    "REMARKS": {"allow_empty": True},
    "AIRCRAFT_REG": {"pattern": r"^[A-Z0-9\-]+$", "uppercase": True},
    "MSN": {"pattern": r"^\d+$"},
}
RULES = merged_rules(_OVERRIDES)

# Header/label lines carry a genuine PART_NUMBER-shaped token (the top
# assembly's own PN) and would otherwise pass the row anchor below.
_HEADER_FRAGMENTS = ("OVERHAULED DATE", "AIRCRAFT :", "REPORT DATE", "REPORT TIME")

_PN_RE = re.compile(r"^\d{6,}(?:-\d+)?$")
# The column rule glyph between DESCRIPTION and PART_NUMBER OCRs as a bare
# "|" glued to the next token with no space often enough (confirmed on
# LEG-STRUT&DRESSING, both TORQUE LINK ASSY rows and PIN-LOWER TORQUE
# LINK(TL3) on this file's own page 1) that anchoring _PN_RE directly
# against the raw token silently drops the row -- worse, on a row whose
# only *other* 6+-digit token happens to be a life-limit figure sharing the
# same width (TL1's "126000"), the anchor latches onto that instead and
# emits a garbled row sliced from the wrong offset. Stripping a leading
# non-digit run before testing recovers the real PN in both cases.
_LEADING_JUNK_RE = re.compile(r"^\D+")
_TAIL_RE = re.compile(r"^(?:[\d,]+|N/?A|NIA)$", re.I)
_TAIL_KEYS = ["TSN", "CSN", "LIFE_LIMIT_HOURS", "LIFE_LIMIT_CYCLES", "REMAIN_HOURS", "REMAIN_CYCLES"]

_TOP_RE = re.compile(
    r"DESCRIPTION\s*:\s*(.+?)\s+PN\s*:\s*(\S+)\s+SN\s*:\s*(\S+)\s+OVERHAULED DATE\s*:\s*(\S+)", re.I)
_AIRCRAFT_RE = re.compile(r"AIRCRAFT\s*:\s*(\S+)\s*\(MSN:\s*(\d+)\)", re.I)
_ACFH_RE = re.compile(r"A[IJ/]C\s+FH\s*:\s*(\S+)", re.I)
_ACFC_RE = re.compile(r"A[IJ/]C\s+FC\s*:\s*(\S+)", re.I)
_IN_AIRCRAFT_RE = re.compile(r"IN AIRCRAFT DATE\s*:\s*(\S+)", re.I)
_TSN_RE = re.compile(r"^TSN\s*:\s*(\S+)", re.M)
_TSO_RE = re.compile(r"\bTSO\s*:\s*(\S+)")
_REPORT_DATE_RE = re.compile(r"REPORT DATE\s*:\s*(\S+)", re.I)
_GEAR_CSN_RE = re.compile(r"^CSN\s*:\s*(\S+)", re.M)
_GEAR_CSO_RE = re.compile(r"\bCSO\s*:\s*(\S+)")
_REPORT_TIME_RE = re.compile(r"REPORT TIME\s*:\s*(\S+)", re.I)


def _parse_meta(text: str) -> dict:
    meta: dict[str, str] = {}
    m = _TOP_RE.search(text)
    if m:
        meta["TOP_DESCRIPTION"] = m.group(1).strip()
        meta["TOP_PART_NUMBER"] = m.group(2)
        meta["TOP_SERIAL_NUMBER"] = m.group(3)
        meta["OVERHAULED_DATE"] = m.group(4)
    m = _AIRCRAFT_RE.search(text)
    if m:
        meta["AIRCRAFT_REG"] = m.group(1)
        meta["MSN"] = m.group(2)
    for pat, key in (
        (_ACFH_RE, "AC_FH"), (_ACFC_RE, "AC_FC"), (_IN_AIRCRAFT_RE, "IN_AIRCRAFT_DATE"),
        (_TSN_RE, "GEAR_TSN"), (_TSO_RE, "GEAR_TSO"), (_REPORT_DATE_RE, "REPORT_DATE"),
        (_GEAR_CSN_RE, "GEAR_CSN"), (_GEAR_CSO_RE, "GEAR_CSO"), (_REPORT_TIME_RE, "REPORT_TIME"),
    ):
        m = pat.search(text)
        if m:
            meta[key] = m.group(1).strip()
    return meta


def _is_header_line(line: str) -> bool:
    up = line.upper()
    return any(frag in up for frag in _HEADER_FRAGMENTS)


def _parse_row(line: str) -> dict | None:
    toks = line.split()
    pn_idx = pn_clean = None
    for i, t in enumerate(toks):
        candidate = _LEADING_JUNK_RE.sub("", t)
        if _PN_RE.match(candidate):
            pn_idx, pn_clean = i, candidate
            break
    if pn_idx is None or pn_idx < 1 or pn_idx + 1 >= len(toks):
        return None

    rec = {c: "" for c in CANONICAL_COLUMNS}
    rec["DESCRIPTION"] = " ".join(toks[:pn_idx])
    rec["PART_NUMBER"] = pn_clean
    rec["SERIAL_NUMBER"] = toks[pn_idx + 1]

    rest = toks[pn_idx + 2:]
    i = 0
    while i < len(rest) and i < len(_TAIL_KEYS) and _TAIL_RE.match(rest[i]):
        rec[_TAIL_KEYS[i]] = rest[i]
        i += 1
    rec["REMARKS"] = " ".join(rest[i:])
    return rec


def _ocr_all_pages(pdf_path: str, dpi: int = 300) -> list[str]:
    doc = fitz.open(pdf_path)
    try:
        texts = []
        for page in doc:
            pix = page.get_pixmap(dpi=dpi)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            texts.append(pytesseract.image_to_string(img, config="--psm 6"))
        return texts
    finally:
        doc.close()


def ocr_detect(pdf_path: str) -> bool:
    try:
        doc = fitz.open(pdf_path)
        pix = doc[0].get_pixmap(dpi=300)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        text = pytesseract.image_to_string(img, config="--psm 6").upper()
        return "LANDING GEAR LIFE LIMITED PARTS STATUS" in text
    except Exception:
        return False


def extract(pdf_path: str) -> list[dict]:
    pages = _ocr_all_pages(pdf_path)
    meta = _parse_meta("\n".join(pages))

    records: list[dict] = []
    for page_num, text in enumerate(pages, start=1):
        for raw in text.splitlines():
            line = raw.strip()
            if not line or _is_header_line(line):
                continue
            rec = _parse_row(line)
            if rec is None:
                continue
            for k, v in meta.items():
                rec[k] = v
            rec["_page"] = page_num
            records.append(rec)
    return records
