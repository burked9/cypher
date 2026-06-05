"""L1 — text-layer parsing.

Cheapest path: open the PDF with pdfplumber and use its built-in table
extraction. Filter to OCCM-like data rows (start with 2-digit ATA + 2-3-digit
ZONE) so we drop letterheads, page numbers, and signatures.

Returns the same record shape as L3 so the deploy layer can render either.
"""
from __future__ import annotations
import re
from typing import Iterator
from io import BytesIO

import pdfplumber

DEFAULT_COLUMNS = ["ATA", "ZONE", "FIN", "DESCRIPTION", "VENDOR_CODE", "PART_NUMBER", "SERIAL_NUMBER"]


def _is_data_row(cells: list[str]) -> bool:
    cells = [(c or "").strip() for c in cells]
    if len(cells) < 2:
        return False
    return bool(re.match(r"^\d{2}$", cells[0]) and re.match(r"^\d{2,3}$", cells[1]))


def extract_records(pdf_source, columns: list[str] = DEFAULT_COLUMNS) -> list[dict]:
    """`pdf_source` may be a path string or a bytes-like object (for Pyodide)."""
    src = BytesIO(pdf_source) if isinstance(pdf_source, (bytes, bytearray)) else pdf_source

    records: list[dict] = []
    with pdfplumber.open(src) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            for table in page.extract_tables() or []:
                for row in table:
                    if not _is_data_row(row):
                        continue
                    # Right-pad / truncate to expected column count
                    cells = [(c or "").strip() for c in row]
                    cells = (cells + [""] * len(columns))[:len(columns)]
                    rec = dict(zip(columns, cells))
                    rec["_page"] = page_num
                    records.append(rec)
    return records


def extract_tables(pdf_path: str, page_range: tuple[int, int] | None = None) -> Iterator[list[list[str]]]:
    yield [list(r.values()) for r in extract_records(pdf_path)]
