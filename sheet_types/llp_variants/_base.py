"""Shared helpers for LLP variants — mirrors occm_variants/_base.py."""
from __future__ import annotations
from shared.aviation_rules import COLUMN_RULES as GLOBAL_RULES


def merged_rules(overrides: dict | None = None) -> dict:
    out = dict(GLOBAL_RULES)
    if overrides:
        for col, rule in overrides.items():
            base = dict(out.get(col, {}))
            base.update(rule)
            out[col] = base
    return out
