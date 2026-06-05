"""Aeroflot variant — Avionic Inventory Listing (scanned, L3 OCR required).

Note: technically an Avionic Inventory Listing rather than a true OCCM. Kept
under occm_variants because the data is OCCM-adjacent and reuses the same
validation rules.

L3 import is lazy — `levels.L3_ocr` depends on pytesseract / PyMuPDF / Pillow
which aren't installed in the Pyodide deploy. Top-level import would crash
module loading even though the deploy never actually calls extract() for
this variant (router returns a friendly warning instead).
"""
from __future__ import annotations
from sheet_types.occm_variants._base import merged_rules

NAME = "Aeroflot"
SIGNATURES = [
    "AEROFLOT",
    "Inventory Listing of Avionic",
    "Avionic Installed Units",
]

CANONICAL_COLUMNS = [
    "ATA",
    "ZONE",
    "FIN",
    "DESCRIPTION",
    "VENDOR_CODE",
    "PART_NUMBER",
    "SERIAL_NUMBER",
]

RULES = merged_rules()  # global rules cover this schema as-is


def extract(pdf_path: str) -> list[dict]:
    # Lazy import — see module docstring for why.
    from levels.L3_ocr.extract import extract_records as _l3_extract
    return _l3_extract(pdf_path, columns=CANONICAL_COLUMNS)
