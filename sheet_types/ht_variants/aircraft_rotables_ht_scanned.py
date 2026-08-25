"""Aircraft Rotables Report (Iberia MIS) — HT side, scanned, OCR required.

Same underlying template as the born-digital `aircraft_rotables_ht.py`
sibling and as `sheet_types/occm_variants/aircraft_rotables_report_scanned.py`.
"""
from __future__ import annotations
import re

from sheet_types.ht_variants._base import merged_rules

NAME = "Aircraft Rotables HT (Scanned)"

# Deliberately empty. The header phrase "Aircraft Rotables Report" is
# IDENTICAL on the OCCM-side scanned form
# (occm_variants/aircraft_rotables_report_scanned.py) and is not a safe
# discriminator between the two -- this side's table has two extra
# trailing columns (REQUIREMENT/INTERVAL/TOGO/EXPECTED) plus MPD task
# text, that side's stops at TSN/CSN. Detection happens structurally via
# ocr_detect() below instead.
SIGNATURES = []

CANONICAL_COLUMNS = [
    "ATA",
    "POSITION",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "MANUFACTURED",
    "INSTALL_DATE",
    "TSN",
    "CSN",
    "REQUIREMENT",
    "INTERVAL",
    "TO_GO",
    "EXPECTED",
]

_OVERRIDES = {
    "ATA": {"allow_empty": True},
    "POSITION": {"allow_empty": True},
    "PART_NUMBER": {"allow_empty": True},
    "SERIAL_NUMBER": {"allow_empty": True},
    "MANUFACTURED": {"allow_empty": True},
    "INSTALL_DATE": {"allow_empty": True},
    "TSN": {"allow_empty": True},
    "CSN": {"allow_empty": True},
    "REQUIREMENT": {"allow_empty": True},
    "INTERVAL": {"allow_empty": True},
    "TO_GO": {"allow_empty": True},
    "EXPECTED": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_BOUNDS = [0, 180, 355, 1045, 1445, 1775, 2045, 2230, 2350, 2480, 2870, 3060, 3220, 10**6]

_BORDER_RE = re.compile(r"[|\[\]<>=~()`*\"'«»‘’“”–—]+")
_SEP_RUN_RE = re.compile(r"_{2,}|\.{3,}|-{3,}")
_EDGE_STRIP = " _-|[]=~.\"'"


def _clean_bucket(text: str) -> str:
    s = _SEP_RUN_RE.sub(" ", _BORDER_RE.sub(" ", text))
    return " ".join(s.split()).strip(_EDGE_STRIP)


def _bucket_words(words: list[tuple[float, float, str]]) -> list[str]:
    buckets: list[list[str]] = [[] for _ in range(len(_BOUNDS) - 1)]
    for left, width, text in words:
        center = left + width / 2
        for i in range(len(_BOUNDS) - 1):
            if _BOUNDS[i] <= center < _BOUNDS[i + 1]:
                buckets[i].append(text)
                break
    return [_clean_bucket(" ".join(b)) for b in buckets]


def _group_lines(df):
    groups = {}
    for _, row in df.iterrows():
        text = str(row["text"]).strip()
        if not text:
            continue
        key = (row["block_num"], row["par_num"], row["line_num"])
        g = groups.setdefault(key, {"top": [], "words": []})
        g["top"].append(row["top"])
        g["words"].append((row["left"], row["width"], text))
    ordered = sorted(groups.values(), key=lambda g: sum(g["top"]) / len(g["top"]))
    return [g["words"] for g in ordered]


def _parse_page(img, page_num: int) -> list[dict]:
    import pytesseract

    df = pytesseract.image_to_data(img, config="--psm 6",
                                    output_type=pytesseract.Output.DATAFRAME)
    df = df.dropna(subset=["text"])
    lines = _group_lines(df)
    # First two text-lines on every known page are the title and the
    # column-header row -- skipped positionally, not by matching text.
    records = []
    for words in lines[2:]:
        cols = _bucket_words(words)
        (ata, position, description, part_number, serial_number,
         manufactured, install_date, tsn, csn,
         requirement, interval, to_go, expected) = cols
        if not description:
            continue
        if not (part_number or serial_number):
            continue
        if not requirement:
            continue
        records.append({
            "ATA": ata,
            "POSITION": position,
            "DESCRIPTION": description,
            "PART_NUMBER": part_number,
            "SERIAL_NUMBER": serial_number,
            "MANUFACTURED": manufactured,
            "INSTALL_DATE": install_date,
            "TSN": tsn,
            "CSN": csn,
            "REQUIREMENT": requirement,
            "INTERVAL": interval,
            "TO_GO": to_go,
            "EXPECTED": expected,
            "_page": page_num,
        })
    return records


def _render_page(doc, page_index: int, dpi: int = 300):
    import fitz  # pymupdf
    from PIL import Image

    pix = doc[page_index].get_pixmap(dpi=dpi)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def _page1_max_right(pdf_path: str):
    """Return (has_title, max_right_edge_px) for page 1, where the title
    (always the topmost text-line) is excluded from the max-right
    computation -- the title itself runs wide ("... Aircraft: <tail no.>")
    and would otherwise swamp the table-width signal this is used for."""
    import fitz  # pymupdf
    import pytesseract

    doc = fitz.open(pdf_path)
    try:
        img = _render_page(doc, 0, dpi=300)
    finally:
        doc.close()
    df = pytesseract.image_to_data(img, config="--psm 6",
                                    output_type=pytesseract.Output.DATAFRAME)
    df = df.dropna(subset=["text"])
    lines = _group_lines(df)
    if not lines:
        return False, 0
    title_text = " ".join(w[2] for w in lines[0]).upper()
    has_title = "AIRCRAFT" in title_text and "ROTABLES" in title_text
    rest = lines[1:]
    if not rest:
        return has_title, 0
    max_right = max(left + width for words in rest for left, width, _ in words)
    return has_title, max_right


# Confirmed on the known files in the corpus (HT-side and OCCM-side, see
# occm_variants/aircraft_rotables_report_scanned.py): HT-side max right
# edge never drops below ~3451px @ 300 DPI; OCCM-side tops out at ~2434px.
_MAX_RIGHT_THRESHOLD = 2900


def ocr_detect(pdf_path: str) -> bool:
    try:
        result = _page1_max_right(pdf_path)
    except Exception:
        return False
    if result is None:
        return False
    has_title, max_right = result
    return has_title and max_right >= _MAX_RIGHT_THRESHOLD


def extract(pdf_path: str) -> list[dict]:
    try:
        import fitz  # pymupdf
    except ImportError:  # pragma: no cover - exercised under Pyodide, not locally
        return []
    records: list[dict] = []
    doc = fitz.open(pdf_path)
    try:
        for page_index in range(len(doc)):
            img = _render_page(doc, page_index, dpi=300)
            records.extend(_parse_page(img, page_index + 1))
    finally:
        doc.close()
    return records
