"""OCR-extraction wrapper.

For an image-only PDF whose page-1 OCR matched a known variant signature,
this module:

  1. Renders every page at 300 DPI via pymupdf.
  2. OCRs each page with tesseract (PSM 6 — uniform block of text).
  3. Substitutes the OCR'd text for pdfplumber's `page.extract_text()` via
     a monkey-patch on `pdfplumber.open`.
  4. Calls the matched variant module's normal `extract(pdf_path)` — so the
     variant's full state machine (ATA forward-fill, multi-line wrap, etc.)
     runs on the OCR text as if it had come from the text layer.

Local-only — Tesseract isn't available under Pyodide. The browser build
silently degrades to text-layer parsing only.

Expected quality: OCR introduces character noise (l↔1, O↔0, broken dashes).
Many row-anchor regexes will reject noisy lines. We accept partial recovery
and rely on the variants' soft-validation `_issues` column to flag the
damage — never silent loss.
"""
from __future__ import annotations
import contextlib
import re
from pathlib import Path

import pymupdf
import pytesseract
from PIL import Image
import pdfplumber


# Characters Tesseract regularly reads from table borders into "content".
# Stripping these before parsing is the difference between zero rows and
# hundreds of recoverable rows on scanned-table OCCMs.
_BORDER_CHARS = re.compile(r"[\|\[\]<>~`*“”\"]+")
# Whitespace runs (including tabs / non-breaking spaces) collapse to single space.
_WS_RE = re.compile(r"[ \t ]+")
# Strings of underscores / dots / dashes used as separators (>=2 in a row)
# collapse to a single space — they're never meaningful data.
_SEP_RUN_RE = re.compile(r"[_]{2,}|\.{3,}|-{4,}")


def _clean_ocr_text(text: str) -> str:
    """Pre-clean a page of Tesseract output before feeding to variant parsers.

    Strips table-border characters, collapses whitespace, normalises
    separator runs. Preserves newlines because variants iterate rows
    line-by-line.
    """
    out_lines: list[str] = []
    for ln in text.splitlines():
        s = _BORDER_CHARS.sub(" ", ln)
        s = _SEP_RUN_RE.sub(" ", s)
        s = _WS_RE.sub(" ", s).strip()
        if s:
            out_lines.append(s)
    return "\n".join(out_lines)


def _ocr_all_pages(pdf_path: str, dpi: int = 300, clean: bool = True) -> list[str]:
    """Render every page and OCR it. Returns one text string per page.
    If `clean=True`, applies table-border / whitespace cleanup so variant
    parsers can match row anchors against OCR text."""
    texts: list[str] = []
    doc = pymupdf.open(pdf_path)
    try:
        for page in doc:
            pix = page.get_pixmap(dpi=dpi)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            raw = pytesseract.image_to_string(img, config="--psm 6")
            texts.append(_clean_ocr_text(raw) if clean else raw)
    finally:
        doc.close()
    return texts


class _FakePage:
    def __init__(self, text: str):
        self._text = text

    def extract_text(self) -> str:
        return self._text


class _FakeDoc:
    """Pretends to be a pdfplumber PDF — exposes the `pages` attribute and
    works as a context manager."""

    def __init__(self, page_texts: list[str]):
        self.pages = [_FakePage(t) for t in page_texts]

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


@contextlib.contextmanager
def _patch_pdfplumber(page_texts: list[str]):
    """Monkey-patch pdfplumber.open so the variant's extract() sees OCR text
    instead of opening the actual (image-only) PDF."""
    fake = _FakeDoc(page_texts)
    orig = pdfplumber.open

    def fake_open(_pdf_path, *args, **kwargs):
        return fake

    pdfplumber.open = fake_open
    try:
        yield
    finally:
        pdfplumber.open = orig


def extract_via_ocr(pdf_path: str, variant_module, dpi: int = 300) -> list[dict]:
    """Render + OCR every page, then run `variant_module.extract(pdf_path)`
    against the OCR'd text. The variant doesn't know it's being fed OCR.

    Returns the same shape as the variant's native extract().
    """
    page_texts = _ocr_all_pages(pdf_path, dpi=dpi)
    with _patch_pdfplumber(page_texts):
        return variant_module.extract(pdf_path)
