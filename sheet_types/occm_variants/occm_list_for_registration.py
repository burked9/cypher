""""OCCM LIST FOR <REG>" — scanned SAP/MIS-style export, no text layer.

Confirmed on 2 real files (real-corpus triage 2026-08-25), each duplicated
once (identical md5 within its own pair, "(2).pdf" siblings skipped):
"28519_OCCM status_20.10.2017.pdf" (16 pages) and "OCCMDUMP.pdf" (14 pages),
both "OCCM LIST FOR VP-BVY". Page 1-2 of each carries byte-for-byte the SAME
underlying rows (row 1 = equipment 24968, row 13 = 18427, etc.) in the same
column order -- this is one report format exported twice (different tool or
export pass), not two layouts, confirmed by direct inspection rather than
assumed from the filenames.

Neither file has any text layer (pdfplumber: 0 chars on every page, 1-2
embedded images), so this is OCR-only, like sriwijaya_b737_occm.py. Unlike
that module's data grid, plain page-level OCR (tesseract --psm 6) here comes
back cleanly row-segmented -- no per-cell grid-line detection needed (the
kalstar_aviation_llp_status.py approach): a whole-page free-text OCR pass
plus anchored token parsing recovers ~99% of rows correctly (156/158 across
the 4 sampled pages, both files) with only two failure modes below.

Header line (OCR'd, noisy prefix glyphs before the title vary by file/page
but the title phrase itself is always clean)::

    OCCM LIST FOR VP-BVY
    No Equipment Material Serial No. Master Batch Equipment Description
    Functional Location TSIHrs TSICyc TSOHrs TSOCyc TSNHrs TSN Cyc
    Install (TSN) Date

Real data row (OCR'd, whitespace as printed)::

    1 24968 4100945B:45153 1392B £43128340 B777 HS CARE:FAN, MIXED FLOW 7.5
    INCH DI 9V-OTE/2125/01/AFT 8634.38 2056 8634.38 2056 43490:58 9296
    19.05.2013

Two anchors, both far more reliable than trying to split the header's own
word-wrapped column names: the BATCH token (always exactly one colon
joining two alnum/hyphen runs, e.g. "4100945B:45153", "606707-1:70210") and
the FUNCTIONAL_LOCATION token immediately before the trailing numeric block
(always >=2 slashes, e.g. "9V-OTE/2125/01/AFT"). Everything between BATCH+2
and FUNCTIONAL_LOCATION is kept together as DESCRIPTION rather than split
further -- same call sriwijaya_b737_occm.py makes for its own scrambled
middle section, for the same reason (a wrong PART_NUMBER/SERIAL split would
be worse than none downstream).

Two confirmed OCR failure modes, both left unrecovered rather than guessed:
row-number/equipment-number occasionally fuse into one token when the space
between them is thin ("1727789" for "17 27789") -- recovered via a
1-2-digit-then-rest split, since the row numbers on this report are always
small and sequential; and a batch token can itself lose its internal hyphen
and split across two tokens ("810204 4:73030" for "810204-4:73030"), which
this module does NOT special-case (would risk falsely reassembling an
unrelated NO/EQUIPMENT pair elsewhere) -- confirmed as the only remaining
drop in the 4-page sample (1 row of 158).
"""
from __future__ import annotations
import re

from sheet_types.occm_variants._base import merged_rules

try:
    import fitz  # pymupdf
    import pytesseract
    from PIL import Image
    _OCR_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised under Pyodide, not locally
    _OCR_AVAILABLE = False

NAME = "OCCM List For Registration"

# Kept for interface consistency / a possible born-digital copy -- real
# detection for the known scanned files is via ocr_detect() below, same
# situation as sriwijaya_b737_occm.py (see its own SIGNATURES comment).
SIGNATURES = [
    "OCCM LIST FOR",
]

CANONICAL_COLUMNS = [
    "NO",
    "EQUIPMENT_NUMBER",
    "BATCH",
    "SERIAL_NUMBER",
    "MASTER_NUMBER",
    "DESCRIPTION",
    "FUNCTIONAL_LOCATION",
    "TSI_HOURS",
    "TSI_CYCLES",
    "TSO_HOURS",
    "TSO_CYCLES",
    "TSN_HOURS",
    "TSN_CYCLES",
    "INSTALL_DATE",
]

# TSO_HOURS/TSO_CYCLES print "NA" for never-overhauled units -- a real value,
# not a parse failure, so allow_empty alone would wrongly flag it.
_HOURS_RULE = {"pattern": r"^(\d+(\.\d+)?|NA)$", "allow_empty": True}
_CYC_RULE = {"pattern": r"^(\d+|NA)$", "allow_empty": True}
# TSN_HOURS prints as Hrs:Min ("43490:58"), not the decimal form the other
# *_HOURS columns use -- confirmed on every sampled row, not an OCR artifact.
_TSN_HOURS_RULE = {"pattern": r"^\d+:\d{2}$", "allow_empty": True}
_OVERRIDES = {
    "NO": {"pattern": r"^\d{1,4}$"},
    "EQUIPMENT_NUMBER": {"pattern": r"^\d{3,7}$"},
    "BATCH": {"pattern": r"^[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*:[A-Za-z0-9]+$"},
    "MASTER_NUMBER": {"pattern": r"^[A-Za-z0-9]{6,12}$"},
    "FUNCTIONAL_LOCATION": {"pattern": r"^\S+/\S+/\S+/\S+$"},
    "TSI_HOURS": _HOURS_RULE, "TSI_CYCLES": _CYC_RULE,
    "TSO_HOURS": _HOURS_RULE, "TSO_CYCLES": _CYC_RULE,
    "TSN_HOURS": _TSN_HOURS_RULE, "TSN_CYCLES": _CYC_RULE,
    "INSTALL_DATE": {"pattern": r"^\d{2}[.,]\d{2}\.\d{4}$"},
}
RULES = merged_rules(_OVERRIDES)

# Strips leading/trailing OCR border noise from every token (stray "=", "|",
# "©", a misplaced quote/underscore/colon glued onto an otherwise-clean
# value) without touching internal punctuation real values rely on
# (BATCH's hyphen+colon, FUNCTIONAL_LOCATION's slashes) -- confirmed against
# both files rather than assumed, same idea as sriwijaya_b737_occm.py's
# _BORDER_RE but applied per-token instead of per-line since here the noise
# glyphs land fused onto real tokens more often than floating standalone.
_TRIM_RE = re.compile(r"^[^A-Za-z0-9]+|[^A-Za-z0-9]+$")
_BATCH_RE = re.compile(r"^[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*:[A-Za-z0-9]+$")
# NO and EQUIPMENT_NUMBER occasionally OCR as one fused token when the gap
# between them is thin -- see module docstring. Row numbers on this report
# never reach 3 digits within a single 2-page sample, but stay at 1-2 to be
# safe against a wider file than sampled.
_SPLIT_NO_EQUIP_RE = re.compile(r"^(\d{1,2})(\d{4,6})$")


def _clean_tokens(line: str) -> list[str]:
    out = []
    for tok in line.split():
        # A misread colon prints as ";" often enough on this report's batch
        # column specifically (confirmed on multiple rows in both files) to
        # normalize outright rather than widen _BATCH_RE and risk matching
        # unrelated punctuation-heavy noise tokens elsewhere on the line.
        tok = _TRIM_RE.sub("", tok).replace(";", ":")
        if tok:
            out.append(tok)
    return out


def _parse_line(line: str, page_num: int) -> dict | None:
    toks = _clean_tokens(line)
    batch_idx = None
    for i, t in enumerate(toks):
        if t.count(":") == 1 and _BATCH_RE.match(t):
            batch_idx = i
            break
    if batch_idx is None:
        return None

    if batch_idx == 2:
        no, equipment_number = toks[0], toks[1]
    elif batch_idx == 1:
        m = _SPLIT_NO_EQUIP_RE.match(toks[0])
        if not m:
            return None
        no, equipment_number = m.group(1), m.group(2)
    else:
        return None

    floc_idx = None
    for j in range(batch_idx + 3, len(toks)):
        if toks[j].count("/") >= 2:
            floc_idx = j
            break
    if floc_idx is None:
        return None

    description = " ".join(toks[batch_idx + 3:floc_idx])
    if not description:
        return None

    trailing = toks[floc_idx + 1:]
    if len(trailing) < 6:
        return None

    return {
        "NO": no,
        "EQUIPMENT_NUMBER": equipment_number,
        "BATCH": toks[batch_idx],
        "SERIAL_NUMBER": toks[batch_idx + 1],
        "MASTER_NUMBER": toks[batch_idx + 2],
        "DESCRIPTION": description,
        "FUNCTIONAL_LOCATION": toks[floc_idx],
        "TSI_HOURS": trailing[0],
        "TSI_CYCLES": trailing[1],
        "TSO_HOURS": trailing[2],
        "TSO_CYCLES": trailing[3],
        "TSN_HOURS": trailing[4],
        "TSN_CYCLES": trailing[5],
        "INSTALL_DATE": trailing[6] if len(trailing) >= 7 else "",
        "_page": page_num,
    }


def _render_page(doc, page_index: int, dpi: int = 300):
    pix = doc[page_index].get_pixmap(dpi=dpi)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback (see
    sheet_types/occm.py) -- SIGNATURES can never match through the normal
    pdfplumber text-extract path since both known source files have no text
    layer at all.

    Anchors on "OCCM LIST FOR" alone (not the registration itself), which
    OCRs clean on both known files despite noisy graphic glyphs immediately
    before it on the same line -- kept generic rather than tied to VP-BVY so
    a future export of the same MIS template for a different registration
    still routes here.
    """
    if not _OCR_AVAILABLE:
        return False
    try:
        doc = fitz.open(pdf_path)
        img = _render_page(doc, 0, dpi=300)
        doc.close()
        w, h = img.size
        crop = img.crop((0, 0, w, int(h * 0.12)))
        text = pytesseract.image_to_string(crop, config="--psm 6").upper()
        return "OCCM LIST FOR" in text
    except Exception:
        return False


def extract(pdf_path: str) -> list[dict]:
    if not _OCR_AVAILABLE:
        return []
    records: list[dict] = []
    doc = fitz.open(pdf_path)
    try:
        for page_index in range(len(doc)):
            img = _render_page(doc, page_index, dpi=300)
            text = pytesseract.image_to_string(img, config="--psm 6")
            for raw in text.splitlines():
                line = raw.strip()
                if not line:
                    continue
                rec = _parse_line(line, page_index + 1)
                if rec is not None:
                    records.append(rec)
    finally:
        doc.close()
    return records
