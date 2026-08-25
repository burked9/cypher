"""Operator landing-gear leg "Life Limited Parts Summary" -- one file per
leg (NLG / MLG LH / MLG RH), footer signed with the issuing operator's name.

Header (P/N-S/N line's position prefix is bare "NLG" for the nose leg, "MLG
LH"/"MLG RH" for the main legs; case of "Life/life Limited Parts Summary"
varies by file)::

    NLG P/N 023589520-11 S/N 81854 Life Limited Parts Summary
    Aircraft Model A319-111 Aircraft TSN: 43.470,95
    MSN: 2548 Aircraft CSN: 30.435
    Leg Overhaul Date: 19-Apr-15 Status Date 17-Jun-20
    ...
    Insta/ Date: 14-May-15

"Insta/" above isn't a typo in this file -- pdfplumber's extraction of this
PDF's embedded font maps the "ll" ligature glyph in "Install" to "/", so it
always reads as "Insta/". The OCR fallback path (see below) reads the same
glyph correctly-ish as "Instal" (one L) instead. Matched permissively rather
than fixed on either spelling.

Row (single line, every row -- assemblies and sub-parts alike -- shares one
grammar, unlike ERJ190/aircraft_llp_status_report.py's header+child split)::

    BARREL 067583 B78-8095 20000 3650 9480 1886 1764 60000 36394 *

Anchor: the trailing block is always 5 plain integers (OVH cycle/day limit,
then OVH cycle/ageing/day remaining), optionally extended to 7 when the part
also carries its own hard life limit (LL cycle limit + remaining), optionally
followed by a bare "*"/"**" ALS-part footnote token. Matched at fixed length
(try 7, then 5), not an open-ended walk-back: several real serial numbers
here are themselves plain digits (e.g. SN "04231", "010046") and would
otherwise get swallowed into the trail. Whatever's left before that block is
DESCRIPTION/PART_NUMBER/SERIAL_NUMBER, PN and SN taken as the last two
tokens.

Known gap, confirmed on most source files: "REAR PINTLE PIN NUT"'s own PN
prints on the physical line *above* it instead of on its row (a source
layout quirk, not an OCR artifact -- reproduced identically in the
born-digital LH file). That PN is dropped; the row's parenthetical
"(SLN41193)" gets read as PART_NUMBER instead, since nothing distinguishes it
from a real PN by shape alone.

RH MLG's source file is a flat scan with no text layer at all (confirmed:
0 chars on every page via pdfplumber). Its pages 1-3 render each row over
faint Excel gridlines that OCR reads as stray "|" tokens plus, on a real
fraction of numeric cells, misread digits-as-letters (e.g. "3650" -> "aeso")
that no safe cleanup recovers -- those rows are silently skipped rather than
guessed at. Page 4 happens to scan cleanly and extracts fully. Pipe tokens
and bare punctuation-noise tokens (stray "." / "-" a gridline OCR's as its
own token) are stripped before row-matching; this is what fixes an otherwise
misaligned "REAR PINTLE PIN" row on that same page 4.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.llp_variants._base import merged_rules

try:
    import fitz  # pymupdf
    import pytesseract
    from PIL import Image
    _OCR_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised under Pyodide, not locally
    _OCR_AVAILABLE = False

NAME = "SKY Airlines LLP Summary"

# Both distinctive to this exact column grid, not just its column header text.
# NOT using "LIFE LIMITED PARTS SUMMARY" alone -- llp_variants/cfm_overhaul_llp.py's
# own signature ("LIFE LIMITED PARTS SUMMARY - OUTCOMING RATING") contains it as
# a substring, so it would also fire on that variant's real files.
SIGNATURES = [
    "OVH Limits OVH Remainings LL Limits LL Remainings",
    "Description PN SN Cycles Days Cycles Ageing Days Cycles Cycles",
]

CANONICAL_COLUMNS = [
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "OVH_CYCLES_LIMIT",
    "OVH_DAYS_LIMIT",
    "OVH_CYCLES_REMAINING",
    "OVH_AGEING_REMAINING",
    "OVH_DAYS_REMAINING",
    "LL_CYCLES_LIMIT",
    "LL_CYCLES_REMAINING",
    "LL_ALS_REF",
    # File metadata -- same on every row
    "POSITION",
    "ASSEMBLY_PART_NUMBER",
    "ASSEMBLY_SERIAL_NUMBER",
    "AIRCRAFT_MODEL",
    "MSN",
    "AIRCRAFT_TSN",
    "AIRCRAFT_CSN",
    "LEG_OVERHAUL_DATE",
    "STATUS_DATE",
    "INSTALL_DATE",
]

# 60000 LL cycle limits are the norm on this template (confirmed on real
# source files) and exceed the shared 55000 bound the same way ERJ190's
# landing-gear limits do -- a downstream review signal, not a mis-set
# threshold.
_CYCLE_RULE = {"pattern": r"^\d+$", "int_range": (0, 55000),
               "int_range_review": (0, 30000)}
_LL_CYCLE_RULE = {**_CYCLE_RULE, "allow_empty": True}
_DAY_RULE = {"pattern": r"^\d+$"}
_DATE_RULE = {"pattern": r"^\d{1,2}-[A-Za-z]{3}-\d{2}$"}
# European formatting throughout this header block: "." thousands, "," decimal.
_EU_NUM_RULE = {"pattern": r"^[\d.,]+$"}

_OVERRIDES = {
    "OVH_CYCLES_LIMIT":      _CYCLE_RULE,
    "OVH_CYCLES_REMAINING":  _CYCLE_RULE,
    "OVH_DAYS_LIMIT":        _DAY_RULE,
    "OVH_AGEING_REMAINING":  _DAY_RULE,
    "OVH_DAYS_REMAINING":    _DAY_RULE,
    "LL_CYCLES_LIMIT":       _LL_CYCLE_RULE,
    "LL_CYCLES_REMAINING":   _LL_CYCLE_RULE,
    "LL_ALS_REF":            {"pattern": r"^\*{1,2}$", "allow_empty": True},
    "MSN":                   {"pattern": r"^\d+$"},
    "AIRCRAFT_TSN":          _EU_NUM_RULE,
    "AIRCRAFT_CSN":          _EU_NUM_RULE,
    "LEG_OVERHAUL_DATE":     _DATE_RULE,
    "STATUS_DATE":           _DATE_RULE,
    "INSTALL_DATE":          _DATE_RULE,
}
RULES = merged_rules(_OVERRIDES)

_INT_RE = re.compile(r"^\d+$")
# A lone punctuation mark, standing in as its own token -- always a gridline
# or scan-noise artifact on this template, never real DESCRIPTION/PN/SN
# content (those are never bare punctuation).
_NOISE_TOK_RE = re.compile(r"^[.\-_;:,'\"]+$")

_POS_PN_SN_RE = re.compile(r"(NLG|MLG\s+(?:LH|RH))\s+P/N\s+(\S+)\s+S/N\s+(\S+)")
_AC_MODEL_TSN_RE = re.compile(r"Aircraft Model\s+(\S+)\s+Aircraft TSN:\s*([\d.,]+)", re.I)
_MSN_CSN_RE = re.compile(r"MSN:\s*(\S+)\s+Aircraft CSN:\s*([\d.,]+)", re.I)
_LEG_OVH_STATUS_RE = re.compile(r"Leg Overhaul Date:\s*(\S+)\s+Status Date\s+(\S+)", re.I)
# Matches "Insta/ Date:" (pdfplumber's ligature misread of "Install", see
# module docstring) and "Instal Date:" (OCR's own, different misread of the
# same word) alike.
_INSTALL_DATE_RE = re.compile(r"Insta\S*\s+Date\S*\s+(\S+)", re.I)


def _parse_meta(text: str) -> dict:
    meta: dict[str, str] = {}
    m = _POS_PN_SN_RE.search(text)
    if m:
        meta["POSITION"], meta["ASSEMBLY_PART_NUMBER"], meta["ASSEMBLY_SERIAL_NUMBER"] = m.groups()
    m = _AC_MODEL_TSN_RE.search(text)
    if m:
        meta["AIRCRAFT_MODEL"], meta["AIRCRAFT_TSN"] = m.groups()
    m = _MSN_CSN_RE.search(text)
    if m:
        meta["MSN"], meta["AIRCRAFT_CSN"] = m.groups()
    m = _LEG_OVH_STATUS_RE.search(text)
    if m:
        meta["LEG_OVERHAUL_DATE"], meta["STATUS_DATE"] = m.groups()
    m = _INSTALL_DATE_RE.search(text)
    if m:
        meta["INSTALL_DATE"] = m.group(1)
    return meta


def _parse_row(line: str) -> dict | None:
    toks = line.replace("|", " ").split()
    toks = [t for t in toks if not _NOISE_TOK_RE.match(t)]
    if len(toks) < 8:
        return None

    footnote = ""
    if toks[-1] in ("*", "**"):
        footnote = toks[-1]
        toks = toks[:-1]

    if len(toks) >= 10 and all(_INT_RE.match(t) for t in toks[-7:]):
        n = 7
    elif len(toks) >= 8 and all(_INT_RE.match(t) for t in toks[-5:]):
        n = 5
    else:
        return None

    nums = toks[-n:]
    rest = toks[:-n]
    if len(rest) < 3:
        return None
    pn, sn, desc = rest[-2], rest[-1], " ".join(rest[:-2])

    rec = {c: "" for c in CANONICAL_COLUMNS}
    rec["DESCRIPTION"] = desc
    rec["PART_NUMBER"] = pn
    rec["SERIAL_NUMBER"] = sn
    (rec["OVH_CYCLES_LIMIT"], rec["OVH_DAYS_LIMIT"], rec["OVH_CYCLES_REMAINING"],
     rec["OVH_AGEING_REMAINING"], rec["OVH_DAYS_REMAINING"]) = nums[:5]
    if n == 7:
        rec["LL_CYCLES_LIMIT"], rec["LL_CYCLES_REMAINING"] = nums[5:7]
    rec["LL_ALS_REF"] = footnote
    return rec


def ocr_detect(pdf_path: str) -> bool:
    """Cheap header-only OCR check for the router's blank-text-layer
    fallback -- RH MLG's source file has no text layer on any page.
    y=0-0.20 of page 1 comfortably holds the P/N-S/N-title line at 300dpi
    (confirmed directly); cropping tighter than that produced garbage OCR
    on the same line."""
    if not _OCR_AVAILABLE:
        return False
    try:
        doc = fitz.open(pdf_path)
        pix = doc[0].get_pixmap(dpi=300)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        crop = img.crop((0, 0, img.width, int(img.height * 0.20)))
        text = pytesseract.image_to_string(crop, config="--psm 6").upper()
        return "P/N" in text and "S/N" in text and "LIFE LIMITED PARTS SUMMARY" in text
    except Exception:
        return False


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    page_texts: list[tuple[int, str]] = []
    with pdfplumber.open(pdf_path) as pdf:
        doc = None
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if len(text.strip()) < 20 and _OCR_AVAILABLE:
                if doc is None:
                    doc = fitz.open(pdf_path)
                pix = doc[i].get_pixmap(dpi=400)
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                text = pytesseract.image_to_string(img, config="--psm 6")
            page_texts.append((i + 1, text))

    meta = _parse_meta("\n".join(t for _, t in page_texts))
    for page_num, text in page_texts:
        for line in text.splitlines():
            rec = _parse_row(line)
            if rec is None:
                continue
            for k, v in meta.items():
                rec[k] = v
            rec["_page"] = page_num
            records.append(rec)
    return records
