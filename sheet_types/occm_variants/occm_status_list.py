"""OCCM Status List variant — `OCCM COMPONENTS STATUS LIST` format.

First seen in China Eastern documents but the signature catches the same
layout used by other carriers (e.g. Air Serbia). Named for the format
header rather than the operator. Supports mixed text-layer + scanned pages
within one document — pdfplumber is used for the text layer, with an OCR
fallback (pymupdf + pytesseract) when a page has too little selectable text.

Row format (8 columns, single line, space-separated):
    ATA  DESCRIPTION...  FIN  PART_NUMBER  SERIAL_NUMBER  DATE(YYYY-M-D)  FH  FC

DESCRIPTION can contain spaces. The trailing three tokens (DATE, FH, FC) are
strong anchors — DATE has a fixed shape and FH/FC are bare integers, so the
column boundaries are unambiguous.

Some rows have trailing "EASA" / "FAA" / "ORIGI" markers after FC — captured
into a `_trailer` field.

OCR fallback only runs locally (requires Tesseract). Browser deployments
silently skip it for now until Tesseract.js is wired in.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "OCCM Status List"
SIGNATURES = [
    "OCCM COMPONENTS STATUS LIST",
    "COMPONENTS STATUS LIST",
]

CANONICAL_COLUMNS = [
    "ATA",
    "DESCRIPTION",
    "FIN",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DATE",
    "FH",
    "FC",
]

_OVERRIDES = {
    "DATE": {"pattern": r"^\d{4}-\d{1,2}-\d{1,2}$"},
    "FH":   {"pattern": r"^\d+$"},
    "FC":   {"pattern": r"^\d+$"},
}
RULES = merged_rules(_OVERRIDES)

# Line-level row regex. Anchored on:
#   - 2-digit ATA at start
#   - DATE in YYYY-M-D form near the end
#   - FH, FC as integers after DATE
# DESCRIPTION is lazy; FIN is the alphanumeric token immediately before PN.
_ROW_RE = re.compile(
    r"^(?P<ATA>\d{2})\s+"
    r"(?P<DESCRIPTION>.+?)\s+"
    r"(?P<FIN>[A-Za-z0-9]+)\s+"
    r"(?P<PART_NUMBER>\S+)\s+"
    r"(?P<SERIAL_NUMBER>\S+)\s+"
    r"(?P<DATE>\d{4}-\d{1,2}-\d{1,2})\s+"
    r"(?P<FH>\d+)\s+"
    r"(?P<FC>\d+)"
    r"(?:\s+(?P<_trailer>.+))?$"
)


def _clean_ocr_text(text: str) -> str:
    """Strip table-border characters Tesseract introduces when OCRing bordered
    tables. Replaces `[`, `]`, `|`, `_` with spaces and collapses runs."""
    for ch in "[]|_":
        text = text.replace(ch, " ")
    # Collapse multiple spaces but preserve newlines (rows are line-anchored)
    text = re.sub(r"[ \t]+", " ", text)
    return text


def _parse_text_lines(text: str, page_num: int, source: str = "text") -> list[dict]:
    """Apply the row regex line-by-line; return matched records.

    `source='ocr'` triggers OCR-text pre-cleaning (strip table borders) before
    matching, since Tesseract often reads `|`, `[`, `]`, `_` as content."""
    if source == "ocr":
        text = _clean_ocr_text(text)
    records: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or not line[0].isdigit():
            continue
        m = _ROW_RE.match(line)
        if not m:
            continue
        ata = int(m.group("ATA"))
        if not (20 <= ata <= 83):
            continue
        rec = {col: m.group(col) for col in CANONICAL_COLUMNS}
        rec["_page"] = page_num
        trailer = m.group("_trailer")
        if trailer:
            rec["_trailer"] = trailer
        records.append(rec)
    return records


def _merge_split_ata(line: str) -> str:
    """Tesseract often splits the leading "23" ATA chapter into "2 3" on
    bordered tables (the two digits sit in separate cells). If the first
    two tokens are single digits that together form a valid chapter, merge."""
    parts = line.split()
    if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
        candidate = parts[0] + parts[1]
        if len(candidate) == 2 and 20 <= int(candidate) <= 83:
            return candidate + " " + " ".join(parts[2:])
    return line


def _ocr_page_text(pdf_path: str, page_index: int) -> str:
    """Render and OCR a single page. Returns reassembled-line text or ''.

    Strategy:
      - Render at 300 DPI.
      - Use Tesseract PSM 12 (sparse text with OSD), which is much better at
        bordered tables than PSM 6.
      - Get word-level bounding boxes via image_to_data.
      - Cluster words into rows by Y coordinate (adaptive threshold).
      - Within each row, sort by X and space-join.
      - Merge split ATA digits.

    Local-only — requires pymupdf + pytesseract. Returns '' silently in
    browser/Pyodide contexts where these libraries aren't installed."""
    try:
        import fitz  # pymupdf
        import pytesseract
        from PIL import Image
        import pandas as pd
    except Exception:
        return ""

    try:
        doc = fitz.open(pdf_path)
        page = doc[page_index]
        pix = page.get_pixmap(dpi=300)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        df = pytesseract.image_to_data(
            img, output_type=pytesseract.Output.DATAFRAME, config="--psm 12"
        )
        df = df.dropna(subset=["text"])
        df = df[df["text"].astype(str).str.strip() != ""]
        df = df[df["conf"].astype(float) > 30].copy()
        if df.empty:
            return ""

        df = df.sort_values(["top", "left"]).reset_index(drop=True)
        median_h = df["height"].median() if len(df) else 20
        df["row_id"] = (df["top"].diff().fillna(0).abs() > median_h * 0.7).cumsum()

        lines = []
        for _rid, g in df.groupby("row_id"):
            g = g.sort_values("left")
            line = " ".join(g["text"].astype(str).tolist())
            line = _merge_split_ata(line)
            lines.append(line)
        return "\n".join(lines)
    except Exception:
        return ""


def extract(pdf_path: str, ocr_fallback: bool = True) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            page_records = _parse_text_lines(text, page_num)

            # If we got 0 rows from a page that has no usable text layer,
            # try OCR. This covers mixed PDFs (China Eastern's letterhead is
            # text-layered but later pages are scanned).
            if not page_records and ocr_fallback and len(text) < 200:
                ocr_text = _ocr_page_text(pdf_path, page_num - 1)
                if ocr_text:
                    page_records = _parse_text_lines(ocr_text, page_num, source="ocr")
                    if page_records:
                        for r in page_records:
                            r["_source"] = "ocr"

            records.extend(page_records)
    return records
