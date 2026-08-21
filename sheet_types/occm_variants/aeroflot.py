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


def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback (see
    sheet_types/router.py and sheet_types/occm.py) — this variant's own
    SIGNATURES can never match through the normal pdfplumber text-extract
    path since the source PDF has no text layer at all.

    Anchors on the plain-text subject line ("Inventory Listing of Avionic
    Installed Units"), confirmed against research/test_pdfs/afl_test.pdf —
    not the AEROFLOT wordmark, which sits inside a stylized logo graphic.
    That's exactly the class of OCR risk (misread runs together, e.g.
    "PARTMG") that broke a similar check anchored on a wordmark elsewhere
    in this codebase; this phrase reads cleanly instead.
    """
    try:
        import fitz
        import pytesseract
        from PIL import Image
        doc = fitz.open(pdf_path)
        pix = doc[0].get_pixmap(dpi=300)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        w, h = img.size
        # Subject line sits at ~0.20-0.22 of page height on the known
        # sample; cropped generously (0.15-0.30) to tolerate layout drift.
        crop = img.crop((0, int(h * 0.15), w, int(h * 0.30)))
        text = pytesseract.image_to_string(crop, config="--psm 6").upper()
        return "INVENTORY LISTING" in text and "AVIONIC" in text
    except Exception:
        return False
