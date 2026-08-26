"""Aircraft Inspection Report (grouped-by-equipment HT export) — scanned,
OCR required.

Confirmed on a small cluster of real files in the corpus: a single-page
scanned "Aircraft Inspection Report" per ATA chapter, **no text layer at
all** (pdfplumber: 0 chars, 1 embedded image, on every known file), so
this module renders the page and OCRs it directly via
`shared/ocr_bridge.py` — like several other scanned HT/OCCM siblings in
this project it cannot run purely on pdfplumber text and must never be
imported unconditionally from the router.

Despite the per-item filenames some source files carry (named after a
single serial number), every known file is a genuine multi-row table —
one "equipment group" per distinct part definition, followed by one row
per physical unit/position that has carried that part over time. Header,
every known file (values genericized below, layout/shape real)::

    Aerospatiale Matra Aircraft Inspection Report   Aircraft Chapter <n>
    <manufacturer> Equipment | ATA: <chapter> | MSN : <msn> Date : <date>
    Functional        Description   Code | Vendor   Part Number  CMS  B  Serial Number
    Item Number                                                          E| Remarks

Each data row is one of two shapes, both anchored on a leading 2-4 digit
Functional Location code:

  * **Group-header row** — carries the full equipment definition:
    ``<zone> <fin> <description...> <vendor-code F0nnn> <vendor...>
    <part-number> <cms-code> <serial-number>``. Example (genericized)::

        212 10AB WIDGET ASSEMBLY 12V/5V-15 F0123 EXAMPLE VENDOR CO 456
        7800900100 1234

  * **Continuation row** — a further unit/position under the SAME
    equipment definition, only ``<zone> <fin> ... <serial-number>``
    (description/vendor/part-number/cms-code are blank on the scan
    itself and carried forward from the most recent group-header row)::

        212 16AB 1235

A group is detected purely by the presence of the vendor-code token
(``F0`` + 2-4 digits, tolerant of the O/0 OCR confusion) — NOT by any
change in the Functional Location, since a brand new equipment
definition can reuse a Functional Location a previous group already used
higher up the page. That vendor-code token also anchors the
DESCRIPTION/VENDOR split: everything between FIN and the code token is
DESCRIPTION, everything between the code token and the trailing
PART_NUMBER/CMS_CODE/SERIAL_NUMBER triple is VENDOR. OCR regularly glues
the vendor-code onto the last description word with no space (e.g. a
truncated "...LIGH" + "T0280" for "...LIGHT" + "F0280") — the leading
non-code fragment of that glued token is recovered and appended back
onto DESCRIPTION rather than silently lost or misread as part of the
code.

PART_NUMBER/CMS_CODE/SERIAL_NUMBER are the last three whitespace tokens
on a group-header row (CMS_CODE is a long purely-numeric internal
reference code distinct from PART_NUMBER, always positioned directly
before SERIAL_NUMBER on this form). A trailing "E"/Remarks column exists
on the printed form but is empty on every known real row, so REMARKS is
kept as an always-empty column for schema completeness rather than
guessed at.
"""
from __future__ import annotations
import re

from sheet_types.ht_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, page_count

NAME = "Aircraft Inspection Report (Scanned)"

# Deliberately empty. Every known source file has no text layer at all
# (confirmed via pdfplumber: 0 extractable chars on every page of every
# file), so this SIGNATURES list can never actually fire through the
# router's plain pdfplumber text-signature path (see
# sheet_types/ht.py detect_variant). Detection happens structurally via
# ocr_detect() below instead, same pattern as amos_scanned.py and
# aircraft_rotables_ht_scanned.py in this package.
SIGNATURES: list[str] = []

CANONICAL_COLUMNS = [
    "ATA",
    "ZONE",
    "FIN",
    "DESCRIPTION",
    "VENDOR_CODE",
    "VENDOR",
    "PART_NUMBER",
    "CMS_CODE",
    "SERIAL_NUMBER",
    "REMARKS",
]

# ATA/FIN/VENDOR_CODE/PART_NUMBER/SERIAL_NUMBER already have sensible
# global rules in shared/aviation_rules.py (VENDOR_CODE's `^[A-Z0-9]{4,5}$`
# fits this form's "F0nnn" code exactly; FIN's `^[A-Z0-9]{2,8}$` fits the
# alphanumeric item-number suffix). ZONE mirrors the same-shaped column in
# occm_variants/aeroflot.py -- a 2-3 digit Functional Location code, not
# an ATA chapter itself. VENDOR/CMS_CODE/REMARKS are new to this form and
# kept generously permissive: OCR quality on the glued vendor-code/
# description boundary is inherently best-effort (see module docstring),
# so flagging via RULES is preferred over the extractor guessing/dropping.
_OVERRIDES = {
    "ATA": {"allow_empty": True},
    "ZONE": {"pattern": r"^\d{2,4}$", "allow_empty": True},
    "FIN": {"allow_empty": True},
    "DESCRIPTION": {"allow_empty": True},
    "VENDOR_CODE": {"allow_empty": True},
    "VENDOR": {"allow_empty": True},
    "PART_NUMBER": {"allow_empty": True},
    "CMS_CODE": {"pattern": r"^\d{6,12}$", "allow_empty": True},
    "SERIAL_NUMBER": {"allow_empty": True},
    "REMARKS": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Border/leader glyphs a ruled table's gridlines OCR as their own stray
# characters -- never real data. Left deliberately narrow (unlike some
# siblings' _BORDER_RE) since this form's real tokens use '.', '!', '-'
# and '/' as genuine punctuation (e.g. "115V/5V-15", "G.M!", "292-25").
_BORDER_CHARS = "|[]<>=~()`*\"'«»‘’“”–—"
_ZONE_RE = re.compile(r"^\d{2,4}$")
# The vendor code is always "F" + "O"/"0" + 2-4 digits (confirmed on every
# known file: F0123-style codes only) -- tolerant of the O/0 OCR mix-up on
# the 2nd character, which happens on roughly half of the real occurrences.
_CODE_RE = re.compile(r"(?i)F[O0]\d{2,4}")
_ATA_HEADER_RE = re.compile(r"(?i)ATA\s*:?\s*(\d{2})")


def _strip_border(tok: str) -> str:
    return tok.strip(_BORDER_CHARS)


def _find_code(tokens: list[str]) -> tuple[int, str, str] | None:
    """Locate the vendor-code anchor from index 2 onward (past ZONE/FIN),
    returning (token index, leading fragment to re-attach to DESCRIPTION,
    normalized code). None if this line carries no vendor code at all,
    which is how a continuation row (see module docstring) is told apart
    from a group-header row."""
    for i in range(2, len(tokens)):
        m = _CODE_RE.search(tokens[i])
        if m:
            prefix = _strip_border(tokens[i][:m.start()])
            code = m.group().upper().replace("O", "0")
            return i, prefix, code
    return None


def _parse_line(raw_tokens: list[str], cur_group: dict | None, ata: str,
                 page_num: int) -> tuple[dict, dict | None] | None:
    # Some source files visually highlight one particular row's serial
    # number with a pair of standalone pipe characters (e.g. "... 24 |" or
    # "... | 24 |") that OCR emits as their own tokens -- these carry no
    # data and, left in, silently shift the trailing PART_NUMBER/CMS_CODE/
    # SERIAL_NUMBER triple by a position. Drop any token that is nothing
    # but border/leader glyphs before doing any positional logic (a token
    # with a real border-glued prefix/suffix, e.g. "|AIR", is untouched
    # here -- only ever stripped downstream once its real content is
    # used).
    tokens = [t for t in raw_tokens if _strip_border(t) != ""]
    if len(tokens) < 3 or not _ZONE_RE.match(tokens[0]):
        return None
    zone, fin = tokens[0], tokens[1]

    hit = _find_code(tokens)
    if hit is not None:
        idx, desc_extra, code = hit
        if len(tokens) - idx - 1 < 3:
            # Not enough trailing tokens for PART_NUMBER/CMS_CODE/
            # SERIAL_NUMBER -- a malformed/partially-OCR'd row, skip
            # rather than guess at a shifted split.
            return None
        desc_tokens = [t for t in tokens[2:idx]]
        if desc_extra:
            desc_tokens.append(desc_extra)
        description = " ".join(desc_tokens)
        vendor_tokens = [_strip_border(t) for t in tokens[idx + 1:-3]]
        vendor = " ".join(t for t in vendor_tokens if t)
        part_number = _strip_border(tokens[-3])
        cms_code = _strip_border(tokens[-2])
        serial_number = _strip_border(tokens[-1])
        cur_group = {
            "DESCRIPTION": description,
            "VENDOR_CODE": code,
            "VENDOR": vendor,
            "PART_NUMBER": part_number,
            "CMS_CODE": cms_code,
        }
    else:
        if cur_group is None:
            # A continuation row can't appear before its group's
            # header row on a well-formed page -- an orphan here means
            # the group-header row itself failed to OCR/parse, so
            # there's nothing to attach it to.
            return None
        serial_number = _strip_border(tokens[-1])
        if not serial_number:
            return None

    record = {
        "ATA": ata,
        "ZONE": zone,
        "FIN": fin,
        "DESCRIPTION": cur_group["DESCRIPTION"],
        "VENDOR_CODE": cur_group["VENDOR_CODE"],
        "VENDOR": cur_group["VENDOR"],
        "PART_NUMBER": cur_group["PART_NUMBER"],
        "CMS_CODE": cur_group["CMS_CODE"],
        "SERIAL_NUMBER": serial_number,
        "REMARKS": "",
        "_page": page_num,
    }
    return record, cur_group


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback (see
    sheet_types/ht.py) -- this variant's SIGNATURES is deliberately empty
    (see module docstring) since every known source file has no text
    layer at all.

    Anchors on the report title plus the "Functional"/"Description"
    column-header words, which OCR cleanly even though the data grid
    below them doesn't -- the title phrase alone ("Aircraft Inspection
    Report") isn't checked against any other sheet_types/*.py SIGNATURES
    list in this project, but the header words add specificity in case a
    differently-shaped report ever shares that title.
    """
    try:
        img = await render_page(pdf_path, 0, dpi=300)
        w, h = img.size
        crop = img.crop((0, 0, w, int(h * 0.3)))
        text = (await ocr_text(crop, psm=6)).upper()
        return ("INSPECTION REPORT" in text and "FUNCTIONAL" in text
                and "DESCRIPTION" in text)
    except Exception:
        return False


async def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    n_pages = await page_count(pdf_path)
    cur_ata = ""
    for page_index in range(n_pages):
        img = await render_page(pdf_path, page_index, dpi=300)
        text = await ocr_text(img, psm=6)
        m = _ATA_HEADER_RE.search(text)
        if m:
            cur_ata = m.group(1)
        cur_group: dict | None = None
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            tokens = line.split()
            result = _parse_line(tokens, cur_group, cur_ata, page_index + 1)
            if result is not None:
                rec, cur_group = result
                records.append(rec)
    return records
