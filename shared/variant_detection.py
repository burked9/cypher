"""Shared variant-detection helpers used by all three sheet-type routers
(occm.py, ht.py, llp.py) and the triage tool.
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
