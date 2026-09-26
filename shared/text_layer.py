"""Shared "is this text layer usable for SIGNATURES matching?" checks.

Three independent shapes of "unusable" have each been found on real corpus
files, in three different sheet-type modules, at different times: blank/
near-blank recovered text (the original case), a broken font/glyph-mapping
decode that comes back non-blank but not real words (`ht.py`'s ASCII-letter-
fraction check), a `(cid:<n>)` placeholder-dominated decode from a missing
ToUnicode table (`occm.py`'s check), and a scanned page-1 cover page sitting
in front of otherwise-real text (also `occm.py`). Consolidated here so a
caller that only had the weakest of these (a bare `len(head.strip())`
floor) can use the full set without duplicating any of them again.
"""
from __future__ import annotations
import re
import pdfplumber

_CID_GARBLE_RE = re.compile(r"\(cid:\d+\)", re.IGNORECASE)


def read_head_text(pdf_path: str, n_pages: int = 3) -> str:
    parts = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for p in pdf.pages[:n_pages]:
                parts.append(p.extract_text() or "")
    except Exception:
        pass
    return "\n".join(parts)


def read_page1_text(pdf_path: str) -> str:
    try:
        with pdfplumber.open(pdf_path) as pdf:
            if pdf.pages:
                return pdf.pages[0].extract_text() or ""
    except Exception:
        pass
    return ""


def is_cid_garbled(text: str) -> bool:
    """True when `text` is dominated by "(cid:<n>)" placeholder tokens --
    pdfplumber's own stand-in for a glyph it can't map through a broken
    ToUnicode table. Measured by character coverage, not token count, since
    token length varies (`(cid:9)` vs `(cid:123456)`)."""
    if not text:
        return False
    matches = _CID_GARBLE_RE.findall(text)
    covered = sum(len(m) for m in matches)
    return covered * 2 >= len(text)


def is_ascii_garbled(text: str) -> bool:
    """True when non-blank recovered text is mostly not recognisable
    letters -- a broken font/glyph-mapping decode (stray non-ASCII/
    accented characters) rather than real words."""
    stripped = text.strip()
    if len(stripped) < 50:
        return True
    non_space = [c for c in stripped if not c.isspace()]
    if not non_space:
        return True
    ascii_letters = sum(1 for c in non_space if c.isalpha() and ord(c) < 128)
    return (ascii_letters / len(non_space)) < 0.3


def text_layer_unusable(pdf_path: str, head: str | None = None) -> bool:
    """True when the text layer can't be trusted for SIGNATURES matching,
    across every shape of "unusable" confirmed on the real corpus so far."""
    if head is None:
        head = read_head_text(pdf_path)
    if len(head.strip()) < 50:
        return True
    if is_cid_garbled(head):
        return True
    if is_ascii_garbled(head):
        return True
    if len(read_page1_text(pdf_path).strip()) < 50:
        return True
    return False
