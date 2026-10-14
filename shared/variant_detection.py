"""Shared variant-detection helpers used by all three sheet-type routers
(occm.py, ht.py, llp.py), the top-level router, and the triage tool.
"""
from __future__ import annotations

from shared.text_layer import extract_aircraft_family


def aircraft_filter_ok(variant, head: str) -> bool:
    """Check variant's optional AIRCRAFT_FILTER against extracted family."""
    filt = getattr(variant, "AIRCRAFT_FILTER", None)
    if filt is None:
        return True
    family = extract_aircraft_family(head)
    if not family:
        return True
    return bool(filt.search(family))


def match_variant_by_signatures(variants, head: str):
    """Two-pass signature match: normal then space-collapsed.

    Returns the first matching variant module, or None.
    ``head`` must already be uppercased.
    """
    for v in variants:
        for sig in v.SIGNATURES:
            if sig.upper() in head:
                if aircraft_filter_ok(v, head):
                    return v
                break

    head_nospace = "".join(head.split())
    for v in variants:
        for sig in v.SIGNATURES:
            sig_ns = "".join(sig.upper().split())
            if len(sig_ns) >= 8 and sig_ns in head_nospace:
                if aircraft_filter_ok(v, head):
                    return v
                break

    return None


def detect_sheet_type_from_text(head: str, sheet_types: dict,
                                detection_order: list[str]) -> str:
    """Determine sheet type from header text using three tiers:

    1. Top-level module SIGNATURES (exact, then space-collapsed)
    2. Variant-level SIGNATURES fallback across all types

    ``sheet_types`` maps type names to modules with SIGNATURES and VARIANTS.
    ``detection_order`` controls priority when multiple types match.
    ``head`` must already be uppercased.

    Returns the matched type name, or "Unknown".
    """
    for st in detection_order:
        mod = sheet_types[st]
        for sig in mod.SIGNATURES:
            if sig.upper() in head:
                return st

    head_nospace = "".join(head.split())
    for st in detection_order:
        mod = sheet_types[st]
        for sig in mod.SIGNATURES:
            sig_ns = "".join(sig.upper().split())
            if len(sig_ns) >= 8 and sig_ns in head_nospace:
                return st

    matched_types: set[str] = set()
    for st in detection_order:
        mod = sheet_types[st]
        for variant in getattr(mod, "VARIANTS", []):
            for sig in variant.SIGNATURES:
                if sig.upper() in head:
                    matched_types.add(st)
                    break
            if st in matched_types:
                break
    if not matched_types:
        for st in detection_order:
            mod = sheet_types[st]
            for variant in getattr(mod, "VARIANTS", []):
                for sig in variant.SIGNATURES:
                    sig_ns = "".join(sig.upper().split())
                    if len(sig_ns) >= 8 and sig_ns in head_nospace:
                        matched_types.add(st)
                        break
                if st in matched_types:
                    break
    if matched_types:
        for st in detection_order:
            if st in matched_types:
                return st

    return "Unknown"
