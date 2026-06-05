"""Pyodide entry point.

Called from app.js with raw PDF bytes. Auto-detects sheet type (OCCM/HT/LLP)
*and* operator variant, then runs the right parser end-to-end. Returns a
JSON-serializable dict containing variant, columns, rows, summary stats,
and any warning.

Aeroflot OCCM (the only L3 variant) returns a friendly warning because
Tesseract.js isn't wired in to the deploy yet.

L4 (PaddleOCR) is intentionally not in the deploy — too heavy. The user
runs `research/colab_L4_paddleocr.ipynb` on demand for fringe cases.
"""
from __future__ import annotations
import os
import tempfile

from sheet_types import router


def _save_temp(pdf_bytes: bytes) -> str:
    fd, path = tempfile.mkstemp(suffix=".pdf")
    with os.fdopen(fd, "wb") as fh:
        fh.write(pdf_bytes)
    return path


def run(pdf_bytes: bytes, level: str = "auto"):
    try:
        path = _save_temp(bytes(pdf_bytes))
    except Exception as e:
        return {"ok": False, "error": f"Could not buffer PDF: {e}"}

    try:
        sheet_type = router.detect_sheet_type(path)
    except Exception as e:
        return {"ok": False, "error": f"Sheet-type detection failed: {e}"}

    # Aeroflot OCCM needs L3 OCR — not available in this build of the deploy.
    # We probe the OCCM router specifically because Aeroflot sets the OCCM
    # sheet type even for empty text layers.
    if sheet_type == "OCCM":
        from sheet_types import occm
        if occm.detect_variant(path) == "Aeroflot":
            return {
                "ok": True,
                "sheet_type": "OCCM",
                "variant": "Aeroflot",
                "columns": [],
                "rows": [],
                "warning": ("This PDF is the Aeroflot variant (Avionic Inventory "
                            "Listing) with no text layer. It requires L3 OCR, which "
                            "runs in the browser via Tesseract.js — not yet wired "
                            "into this build. Use the local Python pipeline for now."),
            }

    try:
        result = router.extract(path)
    except Exception as e:
        return {"ok": False, "error": f"Extraction failed: {e}", "sheet_type": sheet_type}

    if not result.get("ok"):
        return {"ok": False,
                "error": result.get("error", "Unknown error"),
                "sheet_type": sheet_type}

    rows_in = result["records"]
    if not rows_in:
        return {
            "ok": True,
            "sheet_type": result["sheet_type"],
            "variant": result["variant"],
            "columns": result["columns"],
            "rows": [],
            "warning": ("No rows extracted. The document may be an unfamiliar "
                        f"layout within {result['sheet_type']} — please share "
                        "for tuning."),
        }

    columns = list(result["columns"]) + ["_issues", "_page"]
    rows = [{c: ("" if r.get(c) is None else str(r.get(c, ""))) for c in columns}
            for r in rows_in]

    n = len(rows)
    flagged = sum(1 for r in rows if r.get("_issues"))
    imputed = sum(1 for r in rows if "_imputed:ATA" in r.get("_issues", ""))

    return {
        "ok": True,
        "sheet_type": result["sheet_type"],
        "variant": result["variant"],
        "columns": columns,
        "rows": rows,
        "summary": {
            "total": n,
            "clean": n - flagged,
            "flagged": flagged,
            "imputed_ata": imputed,
        },
    }
