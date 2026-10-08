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


_TYPE_STOP = (
    r"(?:\s+(?:Reference|A/C\s+T[TC]|MSN|Registration|TSN|CSN|"
    r"Serial\s+N|Date|Reg\b)|\s{2,}|\s*$)"
)
_AIRCRAFT_TYPE_PATTERNS = [
    re.compile(r"Aircraft\s+Type:\s*(.+?)" + _TYPE_STOP, re.I | re.M),
    re.compile(r"A/C\s+Type\s*:\s*(.+?)" + _TYPE_STOP, re.I | re.M),
    re.compile(r"Type/Series\s*:\s*(.+?)" + _TYPE_STOP, re.I | re.M),
    re.compile(r"Aircraft\s+Model\s*:\s*(.+?)" + _TYPE_STOP, re.I | re.M),
    re.compile(r"AIRPLANE\s+MODEL\s*:\s*(.+?)" + _TYPE_STOP, re.I | re.M),
]
_FAMILY_RE = re.compile(
    r"(A3[012345]\d|A2[28]0|B7[0-9]{2}|EMB[\s-]?\d{3}|ERJ[\s-]?\d{3}|"
    r"CRJ[\s-]?\d{3}|ATR[\s-]?\d{2}|MD[\s-]?\d{2}|DC[\s-]?\d+|"
    r"737|747|757|767|777|787)",
    re.I,
)


def extract_aircraft_type(head: str) -> str:
    """Best-effort aircraft type from PDF header text.  Returns '' if none found."""
    for pat in _AIRCRAFT_TYPE_PATTERNS:
        m = pat.search(head)
        if m:
            return m.group(1).strip()
    return ""


def extract_aircraft_family(head: str) -> str:
    """Normalised airframe family (e.g. 'A320', 'B737') from header text."""
    raw = extract_aircraft_type(head)
    if raw:
        m = _FAMILY_RE.search(raw)
        if m:
            fam = m.group(1).upper().replace(" ", "").replace("-", "")
            if fam.isdigit():
                fam = "B" + fam
            return fam
    m = _FAMILY_RE.search(head)
    if m:
        fam = m.group(1).upper().replace(" ", "").replace("-", "")
        if fam.isdigit():
            fam = "B" + fam
        return fam
    return ""


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
