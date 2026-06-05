"""L4 — alternative OCR (PaddleOCR / EasyOCR), reserved for fringe cases.

L3 (Tesseract) handles most scanned PDFs. When it fails — typically on
bordered tables, dense Asian-carrier scans, or low-resolution rescans — L4
swaps in a heavier OCR engine (PaddleOCR's PP-Structure table model is the
preferred choice; EasyOCR is the fallback).

Status & deployment
-------------------
- Designed to **NOT** run in the Pyodide deploy. PaddleOCR pulls in PaddlePaddle
  / PyTorch and ~500 MB of model weights — far too heavy for a static GitHub
  Pages site. Instead, the deployed page links to a Colab notebook
  (`research/colab_L4_paddleocr.ipynb`) where users run L4 on demand.
- This module provides a **stub** so the variant parsers can call L4
  uniformly. When called locally without paddleocr installed, it returns
  an empty list and an instructional note. When paddleocr IS installed,
  the implementation should land here.

Trigger conditions (when to escalate to L4)
-------------------------------------------
A page is a candidate for L4 when L3 has run and:
- produced fewer rows than expected (heuristic: less than half the median
  text-layer page's row count for the same document), or
- produced rows whose date / FH / FC fields fail the row regex anchors, or
- has been explicitly forced by the analyst.

Per-row provenance
------------------
Rows produced by L4 carry `_source: "L4_paddle"` (or `_source: "L4_easyocr"`)
so the analyst can filter them in the report.
"""
from __future__ import annotations
from typing import Iterator


HOWTO_NOTE = (
    "L4 (alternative OCR) is not installed locally. To use it on fringe-quality "
    "scans, run the Colab notebook at research/colab_L4_paddleocr.ipynb. "
    "PaddleOCR's PP-Structure model is well-suited to bordered-table OCCM scans "
    "where Tesseract struggles."
)


def extract_records(pdf_path: str, *, page_indices: list[int] | None = None) -> list[dict]:
    """Stub. Returns empty when paddleocr isn't installed; otherwise should
    run PaddleOCR PP-Structure on the requested pages."""
    try:
        import paddleocr  # noqa: F401
    except ImportError:
        return []

    # If paddleocr is installed locally, the implementation belongs here.
    # Kept as a stub so we don't take an environment dependency by default.
    raise NotImplementedError(
        "L4 PaddleOCR runner not yet implemented locally. Use the Colab notebook "
        "for now and import the resulting CSV via your normal merge workflow."
    )


def extract_tables(pdf_path: str, page_range: tuple[int, int] | None = None) -> Iterator[list[list[str]]]:
    yield [list(r.values()) for r in extract_records(pdf_path)]
