"""Shared helpers used by every OCCM variant module.

A variant module exposes:
    NAME: str                           # human-readable variant name
    SIGNATURES: list[str]               # case-insensitive substrings used for detection
    CANONICAL_COLUMNS: list[str]        # column order in extracted records
    RULES: dict                         # per-column validation rules (subset of COLUMN_RULES)
    extract(pdf_path) -> list[dict]     # returns raw records keyed by CANONICAL_COLUMNS
"""
from __future__ import annotations
from shared.aviation_rules import COLUMN_RULES as GLOBAL_RULES


def merged_rules(overrides: dict | None = None) -> dict:
    """Return a fresh dict combining global rules with per-variant overrides."""
    out = dict(GLOBAL_RULES)
    if overrides:
        for col, rule in overrides.items():
            base = dict(out.get(col, {}))
            base.update(rule)
            out[col] = base
    return out
