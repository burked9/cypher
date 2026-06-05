"""L2 — layout-aware extraction.

Uses pdfplumber's word-level positions (or pymupdf blocks) to reconstruct tables
when ruled lines are missing or columns are detected by whitespace.
"""
from __future__ import annotations

from typing import Iterator


def extract_tables(pdf_path: str, page_range: tuple[int, int] | None = None) -> Iterator[list[list[str]]]:
    raise NotImplementedError("L2 — implement after L1 baseline is working")
