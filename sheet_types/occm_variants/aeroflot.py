"""Aeroflot variant — Avionic Inventory Listing (scanned, L3 OCR required).

Note: technically an Avionic Inventory Listing rather than a true OCCM. Kept
under occm_variants because the data is OCCM-adjacent and reuses the same
validation rules.

extract()/ocr_detect() are async and go through shared/ocr_bridge.py's
render_page()/ocr_text()/ocr_words() primitives rather than fitz/pytesseract
directly — this is what makes the variant work identically locally and
under Pyodide (see levels/L3_ocr/extract.py's extract_records_async(),
which does the actual OCR + column-projection). This was the FIRST variant
ever to work in the deployed browser app, via a one-off hard-coded path in
deploy/assets/ocr_bridge.js/deploy/main.py — that special case is gone now
that the underlying primitives are generic; this variant goes through the
same sheet_types/occm.py dispatch as every other OCR variant.
"""
from __future__ import annotations
from sheet_types.occm_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text

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


async def extract(pdf_path: str) -> list[dict]:
    from levels.L3_ocr.extract import extract_records_async
    return await extract_records_async(pdf_path, columns=CANONICAL_COLUMNS)


async def ocr_detect(pdf_path: str) -> bool:
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
        img = await render_page(pdf_path, 0, dpi=300)
        w, h = img.size
        # Subject line sits at ~0.20-0.22 of page height on the known
        # sample; cropped generously (0.15-0.30) to tolerate layout drift.
        crop = img.crop((0, int(h * 0.15), w, int(h * 0.30)))
        text = (await ocr_text(crop, psm=6)).upper()
        return "INVENTORY LISTING" in text and "AVIONIC" in text
    except Exception:
        return False
