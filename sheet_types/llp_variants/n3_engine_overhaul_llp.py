"""N3 Engine Overhaul Services (Lufthansa Technik / Rolls-Royce joint venture)
— "Module Life Limited Parts Summary" for the RB211 Trent 556-61.

Local-only, like Part M Engine Disk Sheet elsewhere in this project: every
known source file is a single flat scanned image with **no text layer**
(confirmed on all 9 known files: 0 chars via pdfplumber, 1 embedded image
per page), so this module renders page 1 and OCRs it directly via
`pytesseract` — it cannot run under Pyodide and must never be imported
unconditionally from the router. See the try/except around this import in
`sheet_types/llp.py`.

Header carries ENGINE TYPE ("RB211 Trent 556-61"), ENGINE NO. (the file's
own ESN, e.g. 71058), ENGINE TSN/CSN, and a DATE. The body is grouped into
fixed module sections ("M 01 L.P. COMPRESSOR FAN", "M 02 I.P. COMPRESSOR",
"M 03 INTERMEDIATE", "M 04 H.P. SYSTEM", "M 05 I.P. TURBINE", "M 08 L.P.
TURBINE" on every known file), each followed by one row per component:

    LPC Shaft  FW10599  PBAN694A  49732  5936  10000  4064  723120  01-170
    └desc────┘ └─PN───┘ └──SN───┘ └TSN─┘ └CSN┘ └LIM──┘ └REM┘ └── ATA ref ──┘

The trailing ATA reference pair (chapter + task/item code) only survives
OCR on the newer-looking scans; the older-looking ones (e.g. 71058, 71053,
71060) end after REMAIN. Both are accepted — see the 4-vs-6 trailing-count
branch in `_parse_row`.

TSN/CSN of 0 (a part fitted new) OCRs unreliably as a bare letter — "O",
"o", "Oo" — because the digit sits alone in its cell with nothing to anchor
Tesseract's digit-vs-letter guess. Confirmed against every 0-value cell in
all 9 known files: none contain any letter other than O/o, so treating any
all-O/o/0 token as "0" is safe here specifically (would NOT be safe as a
general PN/SN rule, which is why it's applied only to the TSN/CSN slots,
not via the shared OCR_CHAR_MAP).

Not attempted: deriving a missing CSN from LIMIT-REMAIN when a row's
trailing run comes back short. It would work arithmetically, but nothing
confirms *which* number went missing versus merely misread, so a derived
figure would look identical to a printed one while being a guess — the
row is dropped instead (matches part_m_engine_disk_sheet.py's stance on
not re-deriving REMAINING_R3).
"""
from __future__ import annotations
import re

from PIL import Image

from sheet_types.llp_variants._base import merged_rules

try:
    import fitz  # pymupdf
    import pytesseract
    _OCR_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised under Pyodide, not locally
    _OCR_AVAILABLE = False

NAME = "N3 Engine Overhaul LLP"

# Never actually fires through the router's normal text-signature match --
# every known source file has no text layer at all (see module docstring).
# Kept for interface consistency and in case a born-digital copy turns up.
# Real detection happens via ocr_detect() below.
SIGNATURES = [
    "MODULE LIFE LIMITED PARTS",
    "N3 ENGINE OVERHAUL SERVICES",
]

CANONICAL_COLUMNS = [
    "MODULE",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "TSN",
    "CSN",
    "LIMIT_CYCLES",
    "REMAIN_CYCLES",
    "ATA_CHAPTER",
    # Engine metadata -- same on every row
    "ENGINE_MODEL",
    "ESN",
    "ENGINE_TSN",
    "ENGINE_CSN",
    "STATUS_DATE",
]

_HOUR_RULE = {"pattern": r"^[\d,]+$", "int_range": (0, 80000), "allow_empty": True}
_CYCLE_RULE = {"pattern": r"^[\d,]+$", "int_range": (0, 55000),
               "int_range_review": (0, 30000), "allow_empty": True}
_OVERRIDES = {
    "TSN":           _HOUR_RULE,
    "CSN":           _CYCLE_RULE,
    "LIMIT_CYCLES":  _CYCLE_RULE,
    "REMAIN_CYCLES": _CYCLE_RULE,
    "ESN":           {"pattern": r"^\d{4,6}$"},
    "ENGINE_TSN":    _HOUR_RULE,
    "ENGINE_CSN":    _CYCLE_RULE,
    "STATUS_DATE":   {"pattern": r"^\d{1,2}-[A-Za-z]{3}-\d{4}$"},
}
RULES = merged_rules(_OVERRIDES)

# Table gridlines OCR as stray |[]=~ between/around numeric cells -- collapse
# whole runs to one space rather than dropping them, so two genuinely
# adjacent tokens never get fused into one.
_NOISE_RE = re.compile(r"[|\[\]=~]+")
_ZERO_RE = re.compile(r"^[Oo0]+$")
_NUM_LIKE_RE = re.compile(r"^(\d+|\d{1,3}-\d{1,3}|[Oo0]+)$")
_CODE_RE = re.compile(r"^[A-Z0-9]{4,}$")
_MODULE_RE = re.compile(r"^M\s?(\d{2})\b")

_ENGINE_LINE_RE = re.compile(
    r"(RB211\s*Trent\s*[\w-]+)\s+(\d{4,6})\s+(\d[\d,]*)\s+(\d[\d,]*)", re.I)
_DATE_RE = re.compile(r"DATE:?\s*(\d{1,2}-[A-Za-z]{3}-\d{4})", re.I)

_SKIP_FRAGMENTS = (
    "LIFE LIMITED PARTS",
    "ENGINE OVERHAUL SERVICES",
    "JOINT VENTURE",
    "ENGINE TYPE",
    "ENGINE NO",
    "DECLARED LIFE",
    "RESIDUAL LIFE",
    "ATA CHAPTER",
    "DESCRIPTION",
    "PART NO",
    "SERIAL NO",
    "*NOTE",
    "APPROVAL STAMP",
    "PLEASE NOTE",
    "IS ONLY VALID",
    "PRINT NAME",
    "PAGE 1 OF",
    "DATE:",
)


def _render_page0(pdf_path: str, dpi: int = 300):
    doc = fitz.open(pdf_path)
    page = doc[0]
    pix = page.get_pixmap(dpi=dpi)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def _is_skip_line(upper_line: str) -> bool:
    return any(frag in upper_line for frag in _SKIP_FRAGMENTS)


def _clean_numeric(tok: str) -> str:
    return "0" if _ZERO_RE.match(tok) else tok


def _parse_meta(text: str) -> dict:
    meta: dict[str, str] = {}
    m = _ENGINE_LINE_RE.search(text)
    if m:
        meta["ENGINE_MODEL"] = re.sub(r"\s+", " ", m.group(1)).strip()
        meta["ESN"] = m.group(2)
        meta["ENGINE_TSN"] = m.group(3).replace(",", "")
        meta["ENGINE_CSN"] = m.group(4).replace(",", "")
    m = _DATE_RE.search(text)
    if m:
        meta["STATUS_DATE"] = m.group(1)
    return meta


def _parse_row(line: str) -> dict | None:
    s = _NOISE_RE.sub(" ", line.strip())
    if not s:
        return None
    u = s.upper()
    mod = _MODULE_RE.match(s)
    if mod:
        return {"_module": f"M{mod.group(1)}"}
    if _is_skip_line(u):
        return None
    toks = s.split()
    if len(toks) < 5:
        return None

    trail: list[str] = []
    i = len(toks) - 1
    while i >= 0 and _NUM_LIKE_RE.match(toks[i]):
        trail.insert(0, toks[i])
        i -= 1
    # 4 = TSN,CSN,LIMIT,REMAIN. 6 = ...+ the ATA chapter/item pair (see
    # module docstring on why that pair only survives on some scans). Any
    # other count means a cell got merged or dropped by OCR -- drop the row
    # rather than guess which field is missing.
    if len(trail) not in (4, 6):
        return None
    if i < 2:
        return None
    sn, pn = toks[i], toks[i - 1]
    if not _CODE_RE.match(sn) or not _CODE_RE.match(pn):
        return None
    desc = " ".join(toks[: i - 1])
    if not desc:
        return None

    rec: dict[str, str] = {c: "" for c in CANONICAL_COLUMNS}
    rec["DESCRIPTION"] = desc
    rec["PART_NUMBER"] = pn
    rec["SERIAL_NUMBER"] = sn
    rec["TSN"] = _clean_numeric(trail[0])
    rec["CSN"] = _clean_numeric(trail[1])
    rec["LIMIT_CYCLES"] = trail[2]
    rec["REMAIN_CYCLES"] = trail[3]
    if len(trail) == 6:
        rec["ATA_CHAPTER"] = f"{trail[4]} {trail[5]}"
    return rec


def ocr_detect(pdf_path: str) -> bool:
    """Cheap header-only OCR check the router falls back to when a PDF has no
    usable text layer. "RB211" + "TRENT" is the anchor, not the "Module Life
    Limited Parts Summary" title -- confirmed against all 9 known files that
    the title band OCRs inconsistently (drops "Summary" or the whole line on
    3 of the 9), while the RB211/Trent engine-type line reads clean on all 9."""
    if not _OCR_AVAILABLE:
        return False
    try:
        img = _render_page0(pdf_path, dpi=300)
        w, h = img.size
        crop = img.crop((0, 0, w, int(h * 0.25)))
        text = pytesseract.image_to_string(crop, config="--psm 6").upper()
        return "RB211" in text and "TRENT" in text
    except Exception:
        return False


def extract(pdf_path: str) -> list[dict]:
    if not _OCR_AVAILABLE:
        return []
    img = _render_page0(pdf_path, dpi=300)
    text = pytesseract.image_to_string(img, config="--psm 6")
    meta = _parse_meta(text)

    records: list[dict] = []
    module = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        rec = _parse_row(line)
        if rec is None:
            continue
        if "_module" in rec:
            module = rec["_module"]
            continue
        rec["MODULE"] = module
        for k, v in meta.items():
            rec[k] = v
        rec["_page"] = 1
        records.append(rec)
    return records
