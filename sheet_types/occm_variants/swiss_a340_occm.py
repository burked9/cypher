"""Swiss International Airlines A340 OCCM — \"OCCM COMPLIANCE STATUS\" format.

Two airframes in the corpus (HB-JMO MSN 179, H3-JMN MSN 175 — both
A340-313X). The PDF column layout linearises poorly via pdfplumber: the
Description column flows to the LEFT of the data, so each description's
words appear on the lines BEFORE and AFTER the data row, like this::

    SENSOR-
    21 773A0000-01 3819 656HK 11476423/9109228 29.04.1997 UNKNOWN UNKNOWN
    TEMPERATURE

We can't reliably reconstruct multi-line descriptions from linear text, so
we focus on POSITION (the key field for the A330 vs A340 comparison work)
and capture description on a best-effort basis from neighbouring short
alpha-only lines.

Data row anchor: trailing ``TSN CSN`` pair (both either ``HHHH:MM``/integer
or the literal ``UNKNOWN``), preceded by ``INST_DATE`` (``DD.MM.YYYY`` on
0179 or ``DD/Mon/YYYY`` on 0175), then a ``RELEASE_LABEL`` with a slash,
then a ``POS`` token (``313HL``, ``5319HL``, ``641HK``), then ``SN``, then
``PN`` (always dash-containing), with ATA as the first token of the row.

0175 has heavy OCR damage (`Q` for `0`, `l` for `1`, dashes dropped to
spaces) — we capture what's parseable and let the rest stay flagged.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "Swiss A340 OCCM"
SIGNATURES = [
    "OCCM COMPLIANCE STATUS",
    "SWISS INTERNATIONAL AIRLINES",
]

CANONICAL_COLUMNS = [
    "ATA",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
    "POSITION",
    "RELEASE_LABEL",
    "INST_DATE",
    "TSN",
    "CSN",
]

_OVERRIDES = {
    "ATA":          {"pattern": r"^\d{2}$"},
    "POSITION":     {"pattern": r"^[0-9]+[A-Z][A-Z0-9]*$", "uppercase": True},
    # Two date forms across the two airframes; both accepted.
    "INST_DATE":    {"pattern": r"^(?:\d{1,2}\.\d{1,2}\.\d{4}|\d{1,2}/[A-Za-z]{3}/\d{4})$"},
    # TSN / CSN can be HHHHH:MM, plain integer, or the sentinel UNKNOWN.
    "TSN":          {"pattern": r"^(?:\d+:\d{2}|\d+|UNKNOWN)$"},
    "CSN":          {"pattern": r"^(?:\d+|UNKNOWN)$"},
    "DESCRIPTION":  {"allow_empty": True},
    "RELEASE_LABEL": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_ATA_RE = re.compile(r"^\d{2}$")
_DATE_RE = re.compile(
    r"^(?:\d{1,2}\.\d{1,2}\.\d{4}|\d{1,2}/[A-Za-z]{3}/\d{4})$")
_TSN_RE = re.compile(r"^(?:\d+:\d{2}|\d+|UNKNOWN)$")
_CSN_RE = re.compile(r"^(?:\d+|UNKNOWN)$")
_POS_RE = re.compile(r"^[0-9]+[A-Z][A-Z0-9]*$")
_PN_RE = re.compile(r"^[A-Z0-9]+(?:[-/][A-Z0-9]+)+$")
# Short alpha-only continuation fragment ("SENSOR-", "TEMPERATURE", "RELIEF")
_DESC_FRAG_RE = re.compile(r"^[A-Z][A-Z, \-/]{2,30}$")


def _parse_data_line(line: str, page_num: int) -> dict | None:
    toks = line.split()
    if len(toks) < 7:
        return None
    if not _ATA_RE.match(toks[0]):
        return None
    ata_int = int(toks[0])
    if not (20 <= ata_int <= 83):
        return None
    # Anchor: last two tokens = TSN, CSN
    if not (_TSN_RE.match(toks[-2]) and _CSN_RE.match(toks[-1])):
        return None
    # Token before TSN must be INST_DATE
    if not _DATE_RE.match(toks[-3]):
        return None
    tsn = toks[-2]
    csn = toks[-1]
    install_date = toks[-3]
    # Walk back from date for RELEASE_LABEL (with slash). The label can be
    # written as one token (`11476423/9109228`), three tokens with the slash
    # standalone, or two tokens with the slash at edge — capture them all.
    # Simpler: take tokens[-?:-3] up to the POS marker.
    # First find POS — walk back from date-3 looking for first POS-shaped
    # token. Tokens in between are RELEASE_LABEL.
    pos_idx = None
    for j in range(len(toks) - 4, 2, -1):
        if _POS_RE.match(toks[j]):
            pos_idx = j
            break
    if pos_idx is None:
        return None
    position = toks[pos_idx]
    release_label = " ".join(toks[pos_idx + 1:-3])
    # PN and SN sit at FIXED positions immediately after ATA (toks[1] and
    # toks[2]). Description fills the variable-length span between SN and POS.
    # Anchoring back from POS got this wrong because the description goes
    # between them, not the PN/SN.
    if pos_idx < 3:
        return None
    pn = toks[1]
    sn = toks[2]
    description = " ".join(toks[3:pos_idx]) if pos_idx > 3 else ""
    return {
        "ATA": toks[0],
        "PART_NUMBER": pn,
        "SERIAL_NUMBER": sn,
        "DESCRIPTION": description,
        "POSITION": position,
        "RELEASE_LABEL": release_label,
        "INST_DATE": install_date,
        "TSN": tsn,
        "CSN": csn,
        "_page": page_num,
    }


def _is_desc_fragment(line: str) -> bool:
    s = line.strip()
    if not s or len(s) > 32:
        return False
    return bool(_DESC_FRAG_RE.match(s)) and not any(c.isdigit() for c in s)


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            lines = text.splitlines()
            # First pass: identify data rows + their indices
            for i, raw in enumerate(lines):
                line = raw.strip()
                if not line:
                    continue
                rec = _parse_data_line(line, page_num)
                if rec is None:
                    continue
                # Best-effort description reconstruction: combine line above
                # and line below if they're short alpha-only fragments.
                desc_parts = []
                if i > 0 and _is_desc_fragment(lines[i - 1]):
                    desc_parts.append(lines[i - 1].strip())
                if rec["DESCRIPTION"]:
                    desc_parts.append(rec["DESCRIPTION"])
                if i + 1 < len(lines) and _is_desc_fragment(lines[i + 1]):
                    desc_parts.append(lines[i + 1].strip())
                rec["DESCRIPTION"] = " ".join(desc_parts).strip()
                records.append(rec)
    return records
