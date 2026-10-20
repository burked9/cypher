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
from shared.ocr_bridge import maybe_await
from shared.text_layer import read_head_text, text_layer_unusable, extract_aircraft_type, extract_aircraft_family
from shared.variant_detection import detect_sheet_type_from_text
from shared.text_layer import is_cid_garbled, is_ascii_garbled


SHEET_TYPES = {
    "OCCM": occm,
    "HT":   ht,
    "LLP":  llp,
}
# Detection order matters — most specific first.
DETECTION_ORDER = ["LLP", "HT", "OCCM"]


async def detect_sheet_type(pdf_path: str, has_text_layer: bool | None = None) -> str:
    """Return 'OCCM' / 'HT' / 'LLP' / 'Unknown' based on first-pages text.

    `has_text_layer=False` skips the pdfplumber-based head-text read
    entirely — a caller that already knows the answer (deploy/main.py,
    via app.js's own fast pdf.js-based check) shouldn't pay that cost
    redundantly just to re-derive "no text layer" a second time before
    falling through to the exact same OCR loop below anyway."""
    head = "" if has_text_layer is False else read_head_text(pdf_path).upper()
    if head.strip():
        st = detect_sheet_type_from_text(head, SHEET_TYPES, DETECTION_ORDER)
        if st != "Unknown":
            return st

        for st in DETECTION_ORDER:
            mod = SHEET_TYPES[st]
            for variant in getattr(mod, "VARIANTS", []):
                data_check = getattr(variant, "data_detect", None)
                if data_check and data_check(head):
                    return st

        if has_text_layer is False or not text_layer_unusable(pdf_path, head=head):
            return "Unknown"
    # No usable text layer — ask any OCR-capable variant, across every
    # sheet type, to confirm its own template via a cheap header OCR pass.
    for st in DETECTION_ORDER:
        mod = SHEET_TYPES[st]
        for variant in getattr(mod, "VARIANTS", []):
            ocr_check = getattr(variant, "ocr_detect", None)
            if ocr_check and await maybe_await(ocr_check(pdf_path)):
                return st
    return "Unknown"


async def extract(pdf_path: str, has_text_layer: bool | None = None) -> dict:
    """Detect sheet type + variant, run the right parser, return validated rows.

    Return shape:
        {
          "ok": True/False,
          "sheet_type": "OCCM" | "HT" | "LLP" | "Unknown",
          "variant":    "<variant name>",
          "columns":    [...],
          "records":    [{...}, ...],   # cleaned + validated
          "aircraft_type":   "<raw type string from header>",
          "aircraft_family": "<normalised family, e.g. A320, B737>",
        }
    """
    head = "" if has_text_layer is False else read_head_text(pdf_path)
    sheet_type = await detect_sheet_type(pdf_path, has_text_layer=has_text_layer)
    aircraft_type = extract_aircraft_type(head)
    aircraft_family = extract_aircraft_family(head)
    if sheet_type == "Unknown":
        diag = diagnose_unknown(pdf_path, head, has_text_layer=has_text_layer)
        return {"ok": False, "sheet_type": "Unknown", "variant": "Unknown",
                "columns": [], "records": [],
                "aircraft_type": aircraft_type, "aircraft_family": aircraft_family,
                "diagnosis": diag,
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
        "aircraft_type": aircraft_type,
        "aircraft_family": aircraft_family,
    }


def diagnose_unknown(pdf_path: str, head: str, *,
                     has_text_layer: bool | None = None) -> dict:
    """Build a structured diagnosis explaining why detection returned Unknown.

    Returns a dict with:
        reason:     short machine-readable tag
        stage:      which detection stage failed
        detail:     human-readable explanation
        suggestion: what the user should try next
        text_chars: approximate character count from the text layer
    """
    head_stripped = head.strip()
    text_chars = len(head_stripped)

    if text_chars < 50:
        if has_text_layer is False or text_chars == 0:
            return {
                "reason": "no_text_layer",
                "stage": "text_extraction",
                "detail": ("This PDF has no extractable text layer — it is "
                           "likely a scanned or image-only document."),
                "suggestion": ("The in-browser tool needs a text layer to "
                               "identify the format. If you have local Python "
                               "access, the local pipeline handles some scanned "
                               "formats via OCR."),
                "text_chars": text_chars,
            }
        return {
            "reason": "near_blank_text",
            "stage": "text_extraction",
            "detail": (f"Only {text_chars} characters of text were extracted "
                       "from the first three pages — too little for format "
                       "detection."),
            "suggestion": ("This usually means a scanned document with minimal "
                           "embedded text. The local Python pipeline may handle "
                           "it via OCR."),
            "text_chars": text_chars,
        }

    head_upper = head.upper()

    if is_cid_garbled(head):
        return {
            "reason": "garbled_cid",
            "stage": "text_extraction",
            "detail": ("The PDF's text layer is dominated by (cid:N) placeholder "
                       "tokens — the font's character mapping is broken."),
            "suggestion": ("The text is present but unreadable due to a missing "
                           "font encoding table. The local pipeline may recover "
                           "this via OCR."),
            "text_chars": text_chars,
        }

    if is_ascii_garbled(head):
        return {
            "reason": "garbled_encoding",
            "stage": "text_extraction",
            "detail": ("The PDF's text layer is mostly non-ASCII or accented "
                       "characters — likely a broken font/glyph decode."),
            "suggestion": ("The text is present but garbled. The local pipeline "
                           "may recover this via OCR."),
            "text_chars": text_chars,
        }

    near_misses = _find_near_miss_signatures(head_upper)

    return {
        "reason": "no_signature_match",
        "stage": "signature_matching",
        "detail": (f"Text layer is readable ({text_chars} chars) but no "
                   "known format signature was found in the first three pages."),
        "suggestion": ("This document uses an unfamiliar MIS/airline format. "
                       "Please share it so we can add support."),
        "text_chars": text_chars,
        "near_misses": near_misses,
    }


def _find_near_miss_signatures(head_upper: str, max_results: int = 3) -> list[dict]:
    """Find signatures that partially match the head text.

    Checks every top-level and variant-level signature. A "near miss" is a
    signature where at least 60% of its words appear in the head text.
    """
    results: list[dict] = []
    seen: set[str] = set()

    def _check(sig: str, sheet_type: str, source: str):
        sig_upper = sig.upper()
        if sig_upper in seen:
            return
        seen.add(sig_upper)
        sig_words = sig_upper.split()
        if len(sig_words) < 2:
            return
        matched = sum(1 for w in sig_words if w in head_upper)
        ratio = matched / len(sig_words)
        if ratio >= 0.6 and ratio < 1.0:
            results.append({
                "signature": sig,
                "sheet_type": sheet_type,
                "source": source,
                "match_ratio": round(ratio, 2),
            })

    for st in DETECTION_ORDER:
        mod = SHEET_TYPES[st]
        for sig in mod.SIGNATURES:
            _check(sig, st, "top_level")
        for variant in getattr(mod, "VARIANTS", []):
            for sig in variant.SIGNATURES:
                _check(sig, st, getattr(variant, "NAME", "unknown"))

    results.sort(key=lambda r: r["match_ratio"], reverse=True)
    return results[:max_results]
