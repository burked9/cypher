"""Xiamen Airlines B737-75C "A/C List and Status of Time-controlled
Components" HT report -- mixed real-text and scanned corpus.

Confirmed on 3 real files (KEEL_aviation_records corpus, 2026-08-25),
header (repeated per page)::

    B-5038 A/C List and Status of Time-controlled Components
    XIAMEN AIRLINES
    MAKE/MODEL SER NO TSN CSN PREPARED BY FANG XIAOQIU
    AIRFRAME* 737-75C 30656 44195:42 29498
    ENGINE L CFM56-7B22 890408 43650:59 28515 APPROVED BY LIN XIANGQUN
    ...
    MPD Description Part No. Serial No. Position INST Hard Total Used REMAIN Next Work Certificate
    DATE Time Time Time Time Date

    "B-5038 HT Component Status.pdf"    -- real text layer
    "MSN 30512 HT.pdf"                  -- scanned, OCR required
    "MSN 29042 HT list.pdf"             -- scanned, OCR required

Sibling occm_variants/xiamen_b737_installed_components.py covers the same
B-reg/MSN range but a different title ("List of Installed Components")
and a genuinely different row shape (plain DESCRIPTION + single TSN/CSN
pair, no ATA sub-code, no position/Hard-Time/Used/REMAIN/Next-Work-Date
columns) -- that module explicitly excludes this title phrase for exactly
this reason (see its own docstring). Grepped clean across every
SIGNATURES list in this package before picking it here.

Row example (clean text, B-5038 p1)::

    1 21-100-00 EXCHANGER HEAT 182820-3 12956 R 2017-06-04 2000FC 17473 792 1208 CAAC

Anchor: leading row INDEX, then a task code shaped `NN-NNN-NN` (ATA is the
leading 2 digits). DESCRIPTION/PART_NUMBER/SERIAL_NUMBER/POSITION/INST_DATE/
Hard-Time-interval/TOTAL/USED/REMAIN/[NEXT_WORK_DATE]/CERTIFICATE are not
split -- same call aercap_hard_time_component_status.py makes for its own
report: POSITION is present on some rows and absent on others, PART_NUMBER
shapes range from "182820-3" to "1151324-1M412" to "251A4510-9", and
several rows carry a multi-ATA-code prefix that wraps onto its own
continuation line with no INDEX ("26-260-00/26-275-00" alone) -- that
continuation line has no whitespace-separated leading INDEX token so it
never matches the anchor below and is silently dropped, the same
ragged-trailing-columns tradeoff every HT sibling parser makes.

Two of the three known files are scanned with no text layer. Reuses the
xiamen occm sibling's 400dpi-grayscale-threshold + `--psm 4` OCR recipe
verbatim (same source generator, same ruled-grid noise pattern against
plain 300dpi psm-6) -- confirmed against both scanned files here: roughly
half the rows recover cleanly, the rest are dropped by the anchor/date
checks below rather than guessed at.
"""
from __future__ import annotations
import re

from sheet_types.ht_variants._base import merged_rules

try:
    import fitz  # pymupdf
    import pytesseract
    from PIL import Image
    _OCR_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised under Pyodide, not locally
    _OCR_AVAILABLE = False

NAME = "Xiamen A/C List and Status of Time-controlled Components"
SIGNATURES = [
    "A/C List and Status of Time-controlled Components",
    "Time-controlled Components",
]
CANONICAL_COLUMNS = [
    "INDEX",
    "ATA",
    "TASK_CODE",
    "STATUS_TRAIL",
]
_OVERRIDES = {
    "INDEX": {"pattern": r"^\d{1,3}$"},
    "TASK_CODE": {"pattern": r"^\d{2}-\d{1,3}-\d{2}.*$"},
    "STATUS_TRAIL": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_BORDER_RE = re.compile(r"[|\[\]]+")
# INDEX and TASK_CODE print space-separated even under OCR noise; the rest
# of the row (description through certificate) is kept whole.
_ROW_RE = re.compile(r"^(\d{1,3})\s+(\d{2}-\d{1,3}-\d{2}[\dA-Za-z,/\-]*)\s+(.*)$")


def _parse_line(line: str, page_num: int) -> dict | None:
    s = _BORDER_RE.sub(" ", line).strip()
    m = _ROW_RE.match(s)
    if not m:
        return None
    index, task_code, trail = m.groups()
    ata = task_code[:2]
    if not (20 <= int(ata) <= 83):
        return None
    trail = trail.strip()
    if not trail:
        return None
    return {
        "INDEX": index,
        "ATA": ata,
        "TASK_CODE": task_code,
        "STATUS_TRAIL": trail,
        "_page": page_num,
    }


def _render_bw(doc, page_index: int, dpi: int = 400):
    pix = doc[page_index].get_pixmap(dpi=dpi)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    gray = img.convert("L")
    return gray.point(lambda x: 0 if x < 150 else 255, "1")


def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback.

    Anchors on the title phrase, which OCRs reliably even at the cheaper
    300dpi/psm-6 pass used here (unlike the data grid below it -- see
    module docstring, which needs the more expensive 400dpi/psm-4 pass)."""
    if not _OCR_AVAILABLE:
        return False
    try:
        doc = fitz.open(pdf_path)
        pix = doc[0].get_pixmap(dpi=300)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        doc.close()
        w, h = img.size
        crop = img.crop((0, 0, w, int(h * 0.15)))
        text = pytesseract.image_to_string(crop, config="--psm 6").upper()
        return "TIME-CONTROLLED COMPONENTS" in text and "XIAMEN" in text
    except Exception:
        return False


def _extract_text_pages(pdf_path: str):
    import pdfplumber
    with pdfplumber.open(pdf_path) as pdf:
        return [(i + 1, p.extract_text() or "") for i, p in enumerate(pdf.pages)]


def _extract_ocr_pages(pdf_path: str):
    if not _OCR_AVAILABLE:
        return []
    pages = []
    doc = fitz.open(pdf_path)
    try:
        for page_index in range(len(doc)):
            bw = _render_bw(doc, page_index)
            text = pytesseract.image_to_string(bw, config="--psm 4")
            pages.append((page_index + 1, text))
    finally:
        doc.close()
    return pages


def extract(pdf_path: str) -> list[dict]:
    pages = _extract_text_pages(pdf_path)
    if not any(len(t.strip()) > 50 for _, t in pages):
        pages = _extract_ocr_pages(pdf_path)
    records: list[dict] = []
    for page_num, text in pages:
        for raw in text.splitlines():
            rec = _parse_line(raw.strip(), page_num)
            if rec is not None:
                records.append(rec)
    return records
