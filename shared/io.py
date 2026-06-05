"""Output writers — xlsx and csv. Used by both the notebook and the deployed app."""
from __future__ import annotations


def to_xlsx_bytes(records: list[dict]) -> bytes:
    raise NotImplementedError


def to_csv_bytes(records: list[dict]) -> bytes:
    raise NotImplementedError
