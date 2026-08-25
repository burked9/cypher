"""Pyodide entry point.

Called from app.js with raw PDF bytes. Auto-detects sheet type (OCCM/HT/LLP)
*and* operator variant, then runs the right parser end-to-end. Returns a
JSON-serializable dict containing variant, columns, rows, summary stats,
and any warning.

`run()` is async: sheet_types/router.py's detect_sheet_type()/extract() are
both async now, since OCR-capable variants need to await
shared/ocr_bridge.py's render_page()/ocr_text()/ocr_words() primitives
(backed by pdf.js/Tesseract.js under Pyodide, since neither fitz nor
pytesseract can run there). Non-OCR variants are untouched, plain sync
functions underneath — router.py awaits either kind transparently.

`has_text_layer`, when app.js has already run its own fast pdf.js-based
check (see ocr_bridge.js's hasTextLayer()), lets this skip redoing that
check via pdfplumber — which is the one confirmed-slow operation on a
genuinely scanned PDF (2.5+ minutes observed on files as small as 89KB,
root cause not identified). Pass None (the default) to have this run its
own check, for callers that haven't already done it.

L4 (PaddleOCR) is intentionally not in the deploy — too heavy. The user
runs `research/colab_L4_paddleocr.ipynb` on demand for fringe cases.
"""
from __future__ import annotations
import os
import tempfile

import pdfplumber

from sheet_types import router


def _save_temp(pdf_bytes: bytes, original_name: str | None = None) -> str:
    """`original_name`, when given, is preserved in the saved path instead of
    a fully random name. shared.pairing.link_pair() falls back to a
    filename-derived aircraft_key when neither PDF's header carries a
    usable MSN/registration -- with the plain tempfile.mkstemp() name this
    always wrote before, that fallback was silently unreachable no matter
    what the user's upload was actually called."""
    if original_name:
        safe_name = os.path.basename(original_name) or "upload.pdf"
        tmpdir = tempfile.mkdtemp()
        path = os.path.join(tmpdir, safe_name)
        with open(path, "wb") as fh:
            fh.write(pdf_bytes)
        return path
    fd, path = tempfile.mkstemp(suffix=".pdf")
    with os.fdopen(fd, "wb") as fh:
        fh.write(pdf_bytes)
    return path


def _has_no_text_layer(pdf_path: str, n_pages: int = 3, threshold: int = 50) -> bool:
    """Backup check only. app.js already runs a fast pdf.js-based check
    (see hasTextLayer() in ocr_bridge.js) before ever calling into Pyodide,
    specifically because THIS check can itself take minutes under Pyodide
    on a genuinely scanned PDF (root cause not identified). This still
    exists for callers that reach main.run() without going through that
    JS pre-check, or if it ever fails open."""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            n_chars = sum(len(p.chars) for p in pdf.pages[:n_pages])
    except Exception:
        return False
    return n_chars < threshold


async def run(pdf_bytes: bytes, level: str = "auto", has_text_layer: bool | None = None):
    try:
        path = _save_temp(bytes(pdf_bytes))
    except Exception as e:
        return {"ok": False, "error": f"Could not buffer PDF: {e}"}

    try:
        sheet_type = await router.detect_sheet_type(path, has_text_layer=has_text_layer)
    except Exception as e:
        return {"ok": False, "error": f"Sheet-type detection failed: {e}"}

    if has_text_layer is None:
        has_text_layer = not _has_no_text_layer(path)

    if sheet_type == "Unknown" and not has_text_layer:
        return {
            "ok": True,
            "sheet_type": "Unknown",
            "variant": "Unknown",
            "columns": [],
            "rows": [],
            "warning": ("This PDF has no extractable text layer, which usually "
                        "means it's a scanned or image-only document, and "
                        "this build's in-browser OCR doesn't recognize it as "
                        "a supported variant. If you have local Python "
                        "access to this project, the local pipeline handles "
                        "more scanned formats than the browser does today."),
        }

    try:
        result = await router.extract(path)
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


# run_with_ocr() (a one-off Aeroflot-only entry point) is gone -- OCR is
# generic now (shared/ocr_bridge.py + deploy/assets/ocr_bridge.js), so
# every OCR-capable variant, Aeroflot included, goes through the same
# router.detect_sheet_type()/router.extract() path as every other variant.
# app.js calls run() for every PDF, text layer or not.


# ---------------------------------------------------------------------------
# OCCM+HT combined mode (Phase 3) — pair two PDFs in-browser and emit
# a slot-joined view alongside the long-form per-sheet rows.
# ---------------------------------------------------------------------------

async def _extract_one(pdf_bytes: bytes, expected_sheet: str, filename: str | None = None,
                        has_text_layer: bool | None = None) -> dict:
    """Extract one PDF for the combined flow. The user has already told us
    which sheet this is via the drop-zone choice, so we go directly through
    the relevant sheet-type router (occm / ht) — the top-level router's
    coarse signatures don't always recognize HT-style headers."""
    path = _save_temp(bytes(pdf_bytes), filename)
    try:
        from sheet_types import occm, ht
        mod = occm if expected_sheet == "OCCM" else ht
        variant = await mod.detect_variant(path)
    except Exception as e:
        return {"ok": False, "error": f"Variant detection failed: {e}",
                "path": path}
    if variant in ("Unknown", "Timeout"):
        if has_text_layer is None:
            has_text_layer = not _has_no_text_layer(path)
        if not has_text_layer:
            return {"ok": False, "path": path,
                    "error": ("This PDF has no extractable text layer (looks "
                              "scanned or image-only), and this build's "
                              "in-browser OCR doesn't recognize it as a "
                              f"known {expected_sheet} variant.")}
        return {"ok": False, "path": path,
                "error": (f"This PDF doesn't match any known {expected_sheet} "
                          f"variant. If you put the files in the wrong drop "
                          f"zones, switch them.")}
    try:
        raw = await mod.extract(path, variant_name=variant)
        cleaned = mod.normalize_and_validate(raw["records"], variant_name=variant)
    except Exception as e:
        return {"ok": False, "error": f"Extraction failed: {e}", "path": path}
    result = {
        "ok": True, "sheet_type": expected_sheet, "variant": variant,
        "columns": raw["columns"], "records": cleaned,
    }
    if not result.get("ok"):
        return {"ok": False, "error": result.get("error", "Unknown error"),
                "path": path}
    rows_in = result.get("records") or []
    columns = list(result["columns"]) + ["_issues", "_page"]
    rows = [{c: ("" if r.get(c) is None else str(r.get(c, "")))
             for c in columns} for r in rows_in]
    return {
        "ok": True,
        "path": path,
        "sheet_type": result["sheet_type"],
        "variant": result["variant"],
        "columns": columns,
        "rows": rows,
    }


def _build_combined_slots(occm_rows: list[dict], ht_rows: list[dict],
                           aircraft_key: str, family: str) -> list[dict]:
    """Build the slot-joined wide view in pure Python — same shape as the
    `cross_sheet_slot` SQL view.

    Picks the latest row per (position, sheet) using the OCCM/HT row's
    presence in the list (the caller has already routed each side, so
    rows are in source order; we just dedupe to the last seen).
    """
    def _key(r):
        # Position column may carry different names across variants; use
        # the first non-empty among POSITION / POS / FIN / LOCATION / POSN.
        for col in ("POSITION", "POS", "FIN", "LOCATION", "POSN"):
            v = (r.get(col) or "").strip()
            if v:
                return v
        return ""
    latest_occm: dict[str, dict] = {}
    for r in occm_rows:
        pos = _key(r)
        if pos:
            latest_occm[pos] = r       # last write wins → newest snapshot
    latest_ht: dict[str, dict] = {}
    for r in ht_rows:
        pos = _key(r)
        if pos:
            latest_ht[pos] = r
    all_positions = sorted(set(latest_occm) | set(latest_ht),
                           key=lambda p: (str(latest_occm.get(p, latest_ht.get(p, {})).get("ATA", "") or ""), p))
    out = []
    for pos in all_positions:
        o = latest_occm.get(pos, {})
        h = latest_ht.get(pos,   {})
        coverage = ("both" if o and h else "occm_only" if o else "ht_only")
        out.append({
            "aircraft_key": aircraft_key,
            "family": family,
            "ata": (o.get("ATA") or h.get("ATA") or ""),
            "position": pos,
            "slot_coverage": coverage,
            "occm_part_number":   o.get("PART_NUMBER", ""),
            "occm_serial_number": o.get("SERIAL_NUMBER", ""),
            "occm_description":   o.get("DESCRIPTION", ""),
            "ht_part_number":     h.get("PART_NUMBER", ""),
            "ht_serial_number":   h.get("SERIAL_NUMBER", ""),
            "ht_description":     h.get("DESCRIPTION", ""),
        })
    return out


async def run_combined(occm_bytes: bytes, ht_bytes: bytes,
                       manual_aircraft_key: str = "",
                       occm_filename: str = "", ht_filename: str = "",
                       occm_has_text_layer: bool | None = None,
                       ht_has_text_layer: bool | None = None):
    """In-browser combined OCCM+HT extraction.

    Saves both PDFs, extracts each via the existing routers, pairs them
    via `shared.pairing.link_pair`, and returns the long-form rows from
    each sheet plus the slot-joined combined view.
    """
    occm = await _extract_one(occm_bytes, "OCCM", occm_filename or None, occm_has_text_layer)
    ht   = await _extract_one(ht_bytes,   "HT",   ht_filename or None, ht_has_text_layer)
    if not occm["ok"]:
        return {"ok": False, "stage": "occm", **occm}
    if not ht["ok"]:
        return {"ok": False, "stage": "ht", **ht}

    try:
        from shared.pairing import link_pair
        pair = link_pair(occm["path"], ht["path"],
                         manual_override=manual_aircraft_key or None)
    except Exception as e:
        return {"ok": False, "stage": "pair",
                "error": f"Pairing failed: {e}",
                "occm": {"variant": occm["variant"], "rows_n": len(occm["rows"])},
                "ht":   {"variant": ht["variant"],   "rows_n": len(ht["rows"])}}

    pair_summary = {
        "status": pair.status,
        "confidence": pair.confidence,
        "aircraft_key": pair.aircraft_key,
        "occm_filename": pair.occm.filename if pair.occm else "",
        "occm_msn": pair.occm.msn if pair.occm else "",
        "occm_registration": pair.occm.registration if pair.occm else "",
        "ht_filename": pair.ht.filename if pair.ht else "",
        "ht_msn": pair.ht.msn if pair.ht else "",
        "ht_registration": pair.ht.registration if pair.ht else "",
        "warnings": list(pair.warnings),
        "is_safe_auto_pair": pair.is_safe_auto_pair,
        "is_hard_mismatch": pair.is_hard_mismatch,
    }

    if pair.is_hard_mismatch and not manual_aircraft_key:
        # Stop before combining — but DO return per-sheet rows so the
        # UI can still show what was extracted for each side.
        return {
            "ok": True, "combined_ok": False, "pair": pair_summary,
            "occm": {"variant": occm["variant"], "columns": occm["columns"],
                     "rows": occm["rows"]},
            "ht":   {"variant": ht["variant"],   "columns": ht["columns"],
                     "rows": ht["rows"]},
        }

    family = (pair.occm.family if pair.occm and pair.occm.family
              else pair.ht.family if pair.ht and pair.ht.family
              else "")
    combined = _build_combined_slots(occm["rows"], ht["rows"],
                                     pair.aircraft_key, family)
    coverage_counts = {
        "both":      sum(1 for r in combined if r["slot_coverage"] == "both"),
        "occm_only": sum(1 for r in combined if r["slot_coverage"] == "occm_only"),
        "ht_only":   sum(1 for r in combined if r["slot_coverage"] == "ht_only"),
    }
    return {
        "ok": True,
        "combined_ok": True,
        "pair": pair_summary,
        "occm": {"variant": occm["variant"], "columns": occm["columns"],
                 "rows": occm["rows"]},
        "ht":   {"variant": ht["variant"],   "columns": ht["columns"],
                 "rows": ht["rows"]},
        "combined": {
            "columns": ["aircraft_key", "family", "ata", "position",
                        "slot_coverage", "occm_part_number",
                        "occm_serial_number", "occm_description",
                        "ht_part_number", "ht_serial_number",
                        "ht_description"],
            "rows": combined,
            "coverage": coverage_counts,
        },
    }
