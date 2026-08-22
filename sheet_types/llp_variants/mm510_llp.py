"""MM_510 / MM_531 LLP-side rows — same MIS export family as
sheet_types/ht_variants/mm510.py's "HARD TIME/LLP COMPONENTS" report. The
header text is identical regardless of whether a given export's rows are
HT-relevant or LLP-relevant (this tool prints one combined table either
way) — which bucket a file lands in depends on what was queried
(Doc.Type=LLP, ATA/Comp.Type=NN, or nothing i.e. everything), never on a
distinguishing phrase in the header. This module handles the LLP side.

Two sub-layouts confirmed by direct inspection of the 7-file corpus cluster
this variant targets:

  * **MM_510 flat layout** (A307_EC-LNH, TC-ETN, OBL, OBM): one row per
    component under a single Tail-Number header. Position is an optional
    1-2 word token right after ATA — frequently blank, in which case PN
    sits directly after ATA::

        57 LH WING F57550028000 EEP106348 RETRACTION JACK FITTING LG-LLP 15-11-2019 126000 21000 56078:49 9953

    OBL / OBM ("<tail> HT-LLP.pdf") have no text layer at all — confirmed
    with both pdfplumber and PyMuPDF (0 chars, 0 char-objects, on every one
    of 5 pages in each file), so this isn't a pdfplumber-specific gap. This
    module OCRs those pages and feeds the reconstructed text through the
    same line parser used for the born-digital files.

  * **MM_531 parent/child layout** (E307 LH/RH MLG, NLG): rows sit under a
    per-page "LAND-GEAR : <parent PN> / <serial> <desc> Position : <pos>"
    header — stamped onto every row from that page rather than parsed
    per-row, since the row's own position slot is unreliable here (usually
    absorbed into DESCRIPTION instead, see below). Each row also carries
    its own TSN/CSN immediately before the install date::

        32 114256308 A0963 RETRACTION ACTUATOR MLG RH 54323:11 9332 07-09-2013 LG-LLP 50000 40668

Row anchor strategy mirrors mm510.py: locate the first PN-shaped token,
treat the next token as S/N, then scan forward for an install-date token.
Two adaptations the real data required over a straight port: PN search
starts at token[1] rather than token[2], because this format's position
column is blank often enough that assuming a fixed offset drops rows; and a
trailing (TSN, CSN) pair — a colon-hour token immediately followed by a
plain-int token, right before the date — is pulled off the end of the
description rather than left in it.

Trailing interval/remaining figures are bucketed by count, same convention
cfm_overhaul_llp.py uses: 4 numerics = LIMIT_HOURS, LIMIT_CYCLES,
REMAIN_HOURS, REMAIN_CYCLES; 2 = LIMIT_CYCLES, REMAIN_CYCLES (checked
against CSN arithmetic — printed limit minus CSN equals printed remaining
on every 2-number MM_531 row); 1 = LIMIT_CYCLES only. LIMIT values print as
plain integers even when they're hour limits (fixed program constants);
REMAIN values print colon (h:mm) form when derived from a colon TSN and
plain form otherwise, so REMAIN_HOURS alone has to accept both shapes.

Out of scope, same as mm510.py documents for its own harder rows: a second
task line for the same component with nothing to ATA-anchor on (OBL prints
these as bare "OVERHAUL <date> ... " continuation lines with no leading
ATA/PN/SN), and a description that wraps onto a second physical line. Both
are dropped/truncated rather than reassembled.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.llp_variants._base import merged_rules
from shared.cleanup import normalize_dashes

try:
    import fitz  # pymupdf
    import pytesseract
    from PIL import Image
    _OCR_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised under Pyodide, not locally
    _OCR_AVAILABLE = False

NAME = "MM_510 LLP Components"
SIGNATURES = [
    "HARD TIME/LLP COMPONENTS",
    "PARENT/CHILD HT/LLP COMPONENTS",
    "MM_510",
    "MM_531",
]
CANONICAL_COLUMNS = [
    "ATA",
    "POSITION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
    "TSN",
    "CSN",
    "INST_DATE",
    "TASK",
    "LIMIT_HOURS",
    "LIMIT_CYCLES",
    "REMAIN_HOURS",
    "REMAIN_CYCLES",
]

_HOUR_RULE = {"pattern": r"^[\d,]+$", "int_range": (0, 150000), "allow_empty": True}
_CYCLE_RULE = {"pattern": r"^[\d,]+$", "int_range": (0, 55000),
               "int_range_review": (0, 30000), "allow_empty": True}
_OVERRIDES = {
    "POSITION":      {"allow_empty": True},
    "PART_NUMBER":   {"allow_empty": True},
    "SERIAL_NUMBER": {"allow_empty": True},
    "TSN":           {"pattern": r"^\d+:\d{2}$", "allow_empty": True},
    "CSN":           _CYCLE_RULE,
    "TASK":          {"allow_empty": True},
    "LIMIT_HOURS":   _HOUR_RULE,
    "LIMIT_CYCLES":  _CYCLE_RULE,
    # Unlike LIMIT_HOURS (always a plain-int program constant), REMAIN_HOURS
    # inherits colon (h:mm) form whenever it was derived from a colon TSN --
    # MM_531 rows print it that way, MM_510 rows print it plain. Has to
    # accept both; int_range is skipped here since clean_cell's thousands
    # parser can't read the colon form and would flag every MM_531 row.
    "REMAIN_HOURS":  {"pattern": r"^[\d,]+(?::\d{2})?$", "allow_empty": True},
    "REMAIN_CYCLES": _CYCLE_RULE,
}
RULES = merged_rules(_OVERRIDES)

# Trailing digits/dashes after the 2-digit chapter are a sub-code (e.g. OCR's
# "21-0000", or the genuine "2153-03") -- chapter is always just the lead pair.
_ATA_RE = re.compile(r"^(\d{2})[\d\-]*$")
_DATE_RE = re.compile(r"^\d{2}-\d{2}-\d{4}$")
_PN_RE = re.compile(r"^(?=[A-Z0-9/\-]*\d)[A-Z0-9/\-]+-[A-Z0-9/\-]+$")
_TSN_RE = re.compile(r"^\d+:\d{2}$")
_CSN_RE = re.compile(r"^\d+$")
_NUM_RE = re.compile(r"^[\d,]+(?::\d{1,2})?$")
_TASK_RE = re.compile(r"^[A-Za-z][A-Za-z0-9\-]*$")
_HEADER_SKIP = re.compile(
    r"HARD TIME|PARENT/CHILD|MM_5\d\d|Tail Number|Component\s+Serial|"
    r"Part\s+Serial|LAND-GEAR|ATA\s+Pos|^\s*Page\s*:|Last\s+Done|"
    r"Last\s+Flight\s+Date", re.I)
_POSITION_META_RE = re.compile(r"Position\s*:\s*(\S.*)$", re.M)


def _page_position(text: str) -> str:
    m = _POSITION_META_RE.search(text)
    return m.group(1).strip() if m else ""


def _parse_line(line: str, page_num: int, page_position: str) -> dict | None:
    if _HEADER_SKIP.search(line):
        return None
    toks = line.split()
    if len(toks) < 4:
        return None
    ata_m = _ATA_RE.match(toks[0])
    if not ata_m:
        return None
    ata = int(ata_m.group(1))
    if not (20 <= ata <= 83):
        return None

    date_idx = None
    for i in range(1, len(toks)):
        if _DATE_RE.match(toks[i]):
            date_idx = i
            break
    if date_idx is None or date_idx < 3:
        return None

    # Search from token[1], not token[2] like mm510.py -- this format's
    # position slot is blank often enough (PN landing right after ATA) that
    # assuming a fixed throwaway token there silently drops those rows.
    pn_idx = None
    for i in range(1, date_idx - 1):
        if _PN_RE.match(toks[i]):
            pn_idx = i
            break
    if pn_idx is None:
        for i in range(1, date_idx - 1):
            if len(toks[i]) >= 5 and any(c.isdigit() for c in toks[i]):
                pn_idx = i
                break
    if pn_idx is None or pn_idx + 1 >= date_idx:
        return None

    position = toks[1] if pn_idx > 1 else ""
    pn = toks[pn_idx].rstrip("-")
    sn = toks[pn_idx + 1].rstrip("-")

    desc_toks = toks[pn_idx + 2:date_idx]
    tsn = csn = ""
    if len(desc_toks) >= 2 and _TSN_RE.match(desc_toks[-2]) and _CSN_RE.match(desc_toks[-1]):
        tsn, csn = desc_toks[-2], desc_toks[-1]
        desc_toks = desc_toks[:-2]
    description = " ".join(desc_toks)

    tail = toks[date_idx + 1:]
    task = ""
    if tail and _TASK_RE.match(tail[0]):
        task = tail[0]
        tail = tail[1:]
    nums = [t for t in tail if _NUM_RE.match(t)]

    rec = {c: "" for c in CANONICAL_COLUMNS}
    rec["ATA"] = toks[0][:2]
    # LAND-GEAR-section metadata wins when present (MM_531) -- far more
    # reliable than this row's own slot, which the fixed-offset search above
    # only recovers when a throwaway token actually preceded PN.
    rec["POSITION"] = page_position or position
    rec["PART_NUMBER"] = pn
    rec["SERIAL_NUMBER"] = sn
    rec["DESCRIPTION"] = description
    rec["TSN"] = tsn
    rec["CSN"] = csn
    rec["INST_DATE"] = toks[date_idx]
    rec["TASK"] = task
    if len(nums) >= 4:
        rec["LIMIT_HOURS"], rec["LIMIT_CYCLES"], rec["REMAIN_HOURS"], rec["REMAIN_CYCLES"] = nums[:4]
    elif len(nums) == 2:
        rec["LIMIT_CYCLES"], rec["REMAIN_CYCLES"] = nums
    elif len(nums) == 1:
        rec["LIMIT_CYCLES"] = nums[0]
    rec["_page"] = page_num
    return rec


def ocr_detect(pdf_path: str) -> bool:
    """Cheap header-only OCR check for the router's blank-text-layer
    fallback. OBL/OBM-style exports have no text layer at all (confirmed
    with pdfplumber AND PyMuPDF, not a pdfplumber gap), so text-signature
    matching never fires for them without this."""
    if not _OCR_AVAILABLE:
        return False
    try:
        doc = fitz.open(pdf_path)
        pix = doc[0].get_pixmap(dpi=300)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        crop = img.crop((0, 0, img.width, int(img.height * 0.10)))
        text = pytesseract.image_to_string(crop, config="--psm 6").upper()
        return "MM_5" in text and "LLP COMPONENTS" in text
    except Exception:
        return False


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        doc = None
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if len(text.strip()) < 20 and _OCR_AVAILABLE:
                if doc is None:
                    doc = fitz.open(pdf_path)
                pix = doc[page_num - 1].get_pixmap(dpi=300)
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                text = pytesseract.image_to_string(img, config="--psm 6")
            text = normalize_dashes(text)
            page_position = _page_position(text)
            for raw in text.splitlines():
                rec = _parse_line(raw.strip(), page_num, page_position)
                if rec is not None:
                    records.append(rec)
    return records
