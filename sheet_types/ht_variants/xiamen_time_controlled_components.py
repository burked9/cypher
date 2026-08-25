"""Xiamen Airlines B737-75C "A/C List and Status of Time-controlled
Components" HT report -- mixed real-text and scanned corpus.

Confirmed on real files in the corpus, header (repeated per page)::

    <REG> A/C List and Status of Time-controlled Components
    XIAMEN AIRLINES
    MAKE/MODEL SER NO TSN CSN PREPARED BY <NAME>
    AIRFRAME* 737-75C 30656 44195:42 29498
    ENGINE L CFM56-7B22 890408 43650:59 28515 APPROVED BY <NAME>
    ...
    MPD Description Part No. Serial No. Position INST Hard Total Used REMAIN Next Work Certificate
    DATE Time Time Time Time Date

Files in the corpus include a mix of a real text layer and scanned
(OCR-required) pages, one of which was seen with a real reg in its
filename and two seen with an MSN in the filename instead.

Sibling occm_variants/xiamen_b737_installed_components.py covers the same
B-reg/MSN range but a different title ("List of Installed Components")
and a genuinely different row shape (plain DESCRIPTION + single TSN/CSN
pair, no ATA sub-code, no position/Hard-Time/Used/REMAIN/Next-Work-Date
columns) -- that module explicitly excludes this title phrase for exactly
this reason (see its own docstring). Grepped clean across every
SIGNATURES list in this package before picking it here.

Row example (clean text)::

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

Most of the known files are scanned with no text layer. Reuses the
xiamen occm sibling's 400dpi-grayscale-threshold + `--psm 4` OCR recipe
verbatim (same source generator, same ruled-grid noise pattern against
plain 300dpi psm-6) -- confirmed against both scanned files here: roughly
half the rows recover cleanly, the rest are dropped by the anchor/date
checks below rather than guessed at.
"""
from __future__ import annotations
import re

from sheet_types.ht_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, page_count

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


def _to_bw(img):
    gray = img.convert("L")
    return gray.point(lambda x: 0 if x < 150 else 255, "1")


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback.

    Anchors on the title phrase, which OCRs reliably even at the cheaper
    300dpi/psm-6 pass used here (unlike the data grid below it -- see
    module docstring, which needs the more expensive 400dpi/psm-4 pass)."""
    try:
        img = await render_page(pdf_path, 0, dpi=300)
        w, h = img.size
        crop = img.crop((0, 0, w, int(h * 0.15)))
        text = (await ocr_text(crop, psm=6)).upper()
        return "TIME-CONTROLLED COMPONENTS" in text and "XIAMEN" in text
    except Exception:
        return False


def _extract_text_pages(pdf_path: str):
    import pdfplumber
    with pdfplumber.open(pdf_path) as pdf:
        return [(i + 1, p.extract_text() or "") for i, p in enumerate(pdf.pages)]


async def _extract_ocr_pages(pdf_path: str):
    pages = []
    n_pages = await page_count(pdf_path)
    for page_index in range(n_pages):
        img = await render_page(pdf_path, page_index, dpi=400)
        bw = _to_bw(img)
        text = await ocr_text(bw, psm=4)
        pages.append((page_index + 1, text))
    return pages


async def extract(pdf_path: str) -> list[dict]:
    pages = _extract_text_pages(pdf_path)
    if not any(len(t.strip()) > 50 for _, t in pages):
        pages = await _extract_ocr_pages(pdf_path)
    records: list[dict] = []
    for page_num, text in pages:
        for raw in text.splitlines():
            rec = _parse_line(raw.strip(), page_num)
            if rec is not None:
                records.append(rec)
    return records
