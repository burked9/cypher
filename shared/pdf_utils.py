"""Shared PDF helpers — page iteration, text-layer detection, page-range handling."""
from __future__ import annotations


def has_text_layer(pdf_path: str) -> bool:
    raise NotImplementedError


def page_count(pdf_path: str) -> int:
    raise NotImplementedError
