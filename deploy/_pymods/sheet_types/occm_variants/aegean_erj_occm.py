"""Aegean Air ERJ170 OCCM — doubled-char header + reversed-watermark interleaving.

Two files in the corpus (HZ-AEE, HZ-AEA). Distinctive header::

    Aircraft-Equipment-List
    HZ-AEE (HZ-AEE EMBRAER-170) S/N: 17000121
    CCooddee -- PP//NN -- IInntteerrvvaall DDeessccrriippttiioonn SSeerriiaallnnuummbbeerr AATTAA--CChhaapptteerr AA//CC--PPoossiittiioonnTTrree
    AEE ( 1135 rotables ) HZ-AEE EMBRAER-170

The column-header line is rendered with every character DOUBLED (PDF font/encoding
quirk). Data rows are NOT doubled, but a reversed-and-rotated watermark
("Regeneration of IEAS is not allowed without prior approval by .IEAS") is
interleaved as short fragments — ``.IEAS``, ``IEAS``, ``yb``, ``lavorppa``,
``roirp``, ``tuohtiw``, ``dewolla``, ``ton``, ``si``, ``noitarnegeR``, ``fo``.
These appear either as standalone lines (drop) or as leading tokens on data
lines (strip).

Data row shape::

    [- ] PN  DESCRIPTION...  SN  ATA-CHAPTER  POSITION

  * PN is the first real token, almost always contains hyphens (`170-28980-902`,
    `1001700-2`).
  * DESCRIPTION is multi-token free text (may contain commas).
  * SN is a long alphanumeric token, almost always numeric in this format.
  * ATA-CHAPTER renders as `00-00` for every row (Aegean's data has ATA
    unassigned — we keep the literal value, the position is what matters).
  * POSITION is a 3-digit position code (`001`, `002`, `000`).

Detection must run BEFORE AMOS — these files match the AMOS column-header
signature first.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "Aegean ERJ OCCM"
SIGNATURES = [
    "EMBRAER-170",   # appears only in these two files in the corpus
]

CANONICAL_COLUMNS = [
    "PART_NUMBER",
    "DESCRIPTION",
    "SERIAL_NUMBER",
    "ATA_CHAPTER",
    "POSITION",
]

_OVERRIDES = {
    "ATA_CHAPTER": {"pattern": r"^\d{2}-\d{2}$"},
    "POSITION":    {"pattern": r"^\d{3}$"},
}
RULES = merged_rules(_OVERRIDES)

# Reversed-rotated watermark fragments that appear as standalone lines or
# leading-prefix tokens on data lines.
_WATERMARK_TOKENS = frozenset({
    ".IEAS", "IEAS",
    "yb", "lavorppa", "roirp", "tuohtiw",
    "dewolla", "ton", "si", "noitarnegeR", "fo",
})

_ATA_CHAP_RE = re.compile(r"^\d{2}-\d{2}$")
_POSITION_RE = re.compile(r"^\d{3}$")
_DOUBLED_HEADER_RE = re.compile(r"CCooddee|SSeerriiaallnnuummbbeerr")
_HEADER_PN_HINT_RE = re.compile(r"^[A-Z0-9][A-Z0-9\-]*-[A-Z0-9\-]+$|^\d+-\d+$")


def _strip_watermark_tokens(toks: list[str]) -> list[str]:
    """Drop watermark tokens from the start of the token list. The watermark
    only ever prefixes a data row — never appears between PN and POSITION."""
    out = list(toks)
    while out and out[0] in _WATERMARK_TOKENS:
        out.pop(0)
    # Also drop a leading literal hyphen (continuation marker rendering noise).
    if out and out[0] == "-":
        out.pop(0)
    return out


def _is_watermark_only(line: str) -> bool:
    toks = line.strip().split()
    return bool(toks) and all(t in _WATERMARK_TOKENS for t in toks)


def _parse_line(line: str, page_num: int) -> dict | None:
    if _DOUBLED_HEADER_RE.search(line):
        return None  # column-header line (doubled chars)
    if _is_watermark_only(line):
        return None
    toks = _strip_watermark_tokens(line.split())
    if len(toks) < 5:
        return None
    # Anchor from the right: POSITION, ATA-CHAPTER, then SN.
    if not _POSITION_RE.match(toks[-1]):
        return None
    if not _ATA_CHAP_RE.match(toks[-2]):
        return None
    position = toks[-1]
    ata_chapter = toks[-2]
    sn = toks[-3]
    pn = toks[0]
    if not _HEADER_PN_HINT_RE.match(pn):
        return None
    description = " ".join(toks[1:-3])
    if not description:
        return None
    return {
        "PART_NUMBER": pn,
        "DESCRIPTION": description,
        "SERIAL_NUMBER": sn,
        "ATA_CHAPTER": ata_chapter,
        "POSITION": position,
        "_page": page_num,
    }


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if len(text) < 80:
                continue
            for raw in text.splitlines():
                rec = _parse_line(raw, page_num)
                if rec is not None:
                    records.append(rec)
    return records
