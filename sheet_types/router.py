"""Top-level sheet-type dispatcher.

Cypher handles three document classes today:
    OCCM — On Condition / Condition Monitored (component status lists)
    HT   — Hard Time (planned replacement schedules)
    LLP  — Life Limited Parts (engine LLP lists)

Each class has its own router under `sheet_types/<class>.py` and one or more
variants under `sheet_types/<class>_variants/`. This top-level dispatcher
detects the class first, then delegates to the class-specific router which
detects the variant.

Detection has two phases:

  1. **Top-level SIGNATURES** — fast, one curated list per sheet type.
     Most files resolve here.

  2. **Variant-level SIGNATURES fallback** — when phase 1 fails, every
     variant's own SIGNATURES are checked across all types. This catches
     phrases deliberately excluded from the top-level lists because the
     same MIS tool emits them for multiple sheet types (MM_510 for HT+LLP,
     STARS/Trax for HT+OCCM, OASES Lifed Component Report for HT+LLP).
     When only one type's variants match, that type wins unambiguously.
     When multiple types match, DETECTION_ORDER breaks the tie.

Detection priority: HT and LLP signatures are checked before OCCM, because
the OCCM signature list is broader and could otherwise match HT/LLP files
that happen to contain words like "AIRCRAFT REGISTRATION:".
"""
from __future__ import annotations

from sheet_types import occm, ht, llp
from shared.cleanup import clean_record
from shared.ocr_bridge import maybe_await
from shared.text_layer import read_head_text, text_layer_unusable


SHEET_TYPES = {
    "OCCM": occm,
    "HT":   ht,
    "LLP":  llp,
}
# Detection order matters — most specific first.
DETECTION_ORDER = ["LLP", "HT", "OCCM"]


async def detect_sheet_type(pdf_path: str, has_text_layer: bool | None = None) -> str:
    """Return 'OCCM' / 'HT' / 'LLP' / 'Unknown' based on first-pages text.

    `has_text_layer=False` skips the pdfplumber-based head-text read below
    entirely — that read is the confirmed-slow operation on a genuinely
    scanned PDF under Pyodide (minutes, root cause unidentified), and a
    caller that already knows the answer (deploy/main.py, via app.js's own
    fast pdf.js-based check) shouldn't pay that cost redundantly just to
    re-derive "no text layer" a second time before falling through to the
    exact same OCR loop below anyway."""
    head = "" if has_text_layer is False else read_head_text(pdf_path).upper()
    if head.strip():
        for st in DETECTION_ORDER:
            mod = SHEET_TYPES[st]
            for sig in mod.SIGNATURES:
                if sig.upper() in head:
                    return st
        # Variant-level SIGNATURES fallback: some MIS tools (MM_510,
        # STARS/Trax, OASES) produce headers that match variant SIGNATURES
        # across multiple sheet types — those phrases are deliberately
        # excluded from the top-level lists to avoid false positives there.
        # Before giving up, check every variant's own SIGNATURES.
        matched_types = set()
        for st in DETECTION_ORDER:
            mod = SHEET_TYPES[st]
            for variant in getattr(mod, "VARIANTS", []):
                for sig in variant.SIGNATURES:
                    if sig.upper() in head:
                        matched_types.add(st)
                        break
        if matched_types:
            for st in DETECTION_ORDER:
                if st in matched_types:
                    return st

        if has_text_layer is False or not text_layer_unusable(pdf_path, head=head):
            return "Unknown"
    # No text layer at all -- ask any OCR-capable variant, across every
    # sheet type, to confirm its own template via a cheap header OCR pass.
    # This used to default blind to "OCCM" (only Aeroflot fit that when it
    # was written), which meant a blank-text PDF got labeled OCCM before
    # variant detection even ran -- exactly what mislabeled a scanned LLP
    # engine sheet as "OCCM . Aeroflot" in practice. No sheet type is a safe
    # default for "no text at all"; each variant must self-confirm.
    for st in DETECTION_ORDER:
        mod = SHEET_TYPES[st]
        for variant in getattr(mod, "VARIANTS", []):
            ocr_check = getattr(variant, "ocr_detect", None)
            if ocr_check and await maybe_await(ocr_check(pdf_path)):
                return st
    return "Unknown"


async def extract(pdf_path: str) -> dict:
    """Detect sheet type + variant, run the right parser, return validated rows.

    Return shape:
        {
          "ok": True/False,
          "sheet_type": "OCCM" | "HT" | "LLP" | "Unknown",
          "variant":    "<variant name>",
          "columns":    [...],
          "records":    [{...}, ...],   # cleaned + validated
        }
    """
    sheet_type = await detect_sheet_type(pdf_path)
    if sheet_type == "Unknown":
        return {"ok": False, "sheet_type": "Unknown", "variant": "Unknown",
                "columns": [], "records": [],
                "error": "Sheet type not recognized — extend signatures in sheet_types/"}

    mod = SHEET_TYPES[sheet_type]
    variant = await mod.detect_variant(pdf_path)
    raw = await mod.extract(pdf_path, variant_name=variant)
    cleaned = mod.normalize_and_validate(raw["records"], variant_name=variant)
    return {
        "ok": True,
        "sheet_type": sheet_type,
        "variant": raw["variant"],
        "columns": raw["columns"],
        "records": cleaned,
    }
