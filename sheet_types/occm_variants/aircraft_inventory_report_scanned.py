"""Aircraft Inventory Report (MM_504) — scanned, no text layer, OCR required.

Confirmed on a handful of real files from the same operator's fleet
(real-corpus triage), covering a few different airframes and a couple of
duplicate exports of the same aircraft on different dates. Every page of
every file is a single flat scanned image with no text layer at all
(confirmed via pdfplumber: 0 chars, 1 embedded image, page 1 of each), so
this module renders each page and OCRs it directly via pytesseract, same
approach as `sriwijaya_b737_occm.py`.

This is the SAME underlying form as the born-digital
`aircraft_inventory_report.py` sibling (identical header text, identical
11-column layout: ATA PART_NUMBER SERIAL_NUMBER DESCRIPTION POSITION
INSTALL_DATE COMMENT COUNTER FH FC DAYS) — just a scanned copy that
sibling's plain-pdfplumber extraction never sees (page-1 text is empty, so
its SIGNATURES never get compared against anything). Row-parsing heuristic
here deliberately mirrors that sibling's (anchor on the install date, walk
backward: POSITION -> DESCRIPTION -> SERIAL_NUMBER -> PART_NUMBER -> ATA at
the head) rather than inventing a different convention, including its same
known limitation on rows where no real POSITION is printed (the last
pre-date token gets misread as POSITION rather than folded back into
DESCRIPTION) and on wrapped continuation lines (a bare description
continuation like "COOLING" or a repeated COMMENT/COUNTER/FH/FC/DAYS
history row with no leading ATA/PN/SN) -- neither carries a date, so
`_parse_line` naturally skips them rather than misattributing them to the
wrong component row.

OCR quality on this form is good relative to `sriwijaya_b737_occm.py`'s
(clean vector-drawn table, not a noisy fax-quality grid), but the header
band still costs more image height to resolve than that sibling's does:
0.12 was confirmed too tight on one of the known files (crops the header
before the operator name resolves even though "AIRCRAFT INVENTORY REPORT"
above it already has); 0.15 recovered both anchors on all known files.
"""
from __future__ import annotations
import re

from sheet_types.occm_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, page_count

NAME = "Aircraft Inventory Report (MM_504, Scanned)"

# Deliberately NOT "MM_504" / "AIRCRAFT INVENTORY REPORT" -- those already
# belong to the born-digital `aircraft_inventory_report.py` sibling, and
# this variant's SIGNATURES can never fire through the router's normal
# pdfplumber text-signature match anyway (every known source file has no
# text layer at all -- see module docstring). Real detection happens via
# ocr_detect() below, independent of VARIANTS list order. Kept scoped to
# this operator so a born-digital MM_504 copy from a DIFFERENT operator
# still routes to the generic sibling rather than here, and so that if
# this module is ever registered ahead of that sibling in occm.py's
# VARIANTS list it can't shadow it on a lucky plain-text substring match.
SIGNATURES = [
    "ATLASGLOBAL",
]

CANONICAL_COLUMNS = [
    "ATA",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
    "POSITION",
    "INSTALL_DATE",
    "COMMENT",
    "COUNTER",
    "FH",
    "FC",
    "DAYS",
]

_OVERRIDES = {
    # Same rationale as the born-digital sibling: ATA here is mixed --
    # plain 2-digit chapters, chapter+subchapter runs (e.g. "2300"), and
    # true alphanumeric PNs OCR occasionally leaves in this slot.
    "ATA":          {"pattern": r"^[A-Z0-9]{2,12}$", "int_range": None, "uppercase": True},
    "POSITION":     {"pattern": r"^[A-Z0-9#:>\-/]+$", "uppercase": True, "allow_empty": True},
    "INSTALL_DATE": {"pattern": r"^(?:\d{2}-[A-Z]{3}-\d{2}|\d{2}-\d{2}-\d{4})$"},
}
RULES = merged_rules(_OVERRIDES)

_DATE_RE = re.compile(r"^(?:\d{2}-[A-Za-z]{3}-\d{2}|\d{2}-\d{2}-\d{4})$")
_ATA_LIKE_RE = re.compile(r"^[A-Z0-9]{2,12}$")
# A lone leftover border/placeholder glyph where a real POSITION would be
# printed (confirmed on a real file -- an em-dash stands in for "no
# position" the same way a blank cell would in the born-digital original).
_PLACEHOLDER_RE = re.compile(r"^[-_—–]+$")


def _parse_line(line: str, page_num: int) -> dict | None:
    tokens = line.split()
    if len(tokens) < 6:
        return None
    if not _ATA_LIKE_RE.match(tokens[0].upper()):
        return None

    date_idx = None
    for i, t in enumerate(tokens):
        if _DATE_RE.match(t):
            date_idx = i
            break
    if date_idx is None or date_idx < 4:
        return None

    install_date = tokens[date_idx]

    head = tokens[:date_idx]
    if len(head) < 5:
        return None
    ata = head[0]
    pn = head[1]
    sn = head[2]
    position = "" if _PLACEHOLDER_RE.match(head[-1]) else head[-1]
    desc_tokens = head[3:-1]
    if not desc_tokens:
        return None
    description = " ".join(desc_tokens)

    after = tokens[date_idx + 1:]
    comment = ""
    idx = 0
    if after and not re.match(r"^[\d:.]", after[0]):
        comment_tokens = []
        while idx < len(after) and not re.match(r"^[\d:.]", after[idx]):
            comment_tokens.append(after[idx])
            idx += 1
        comment = " ".join(comment_tokens)
    rest = after[idx:]
    nums = [t for t in rest if re.match(r"^[\d:.]+$", t)][:4]
    while len(nums) < 4:
        nums.append("")
    counter, fh, fc, days = nums

    return {
        "ATA": ata,
        "PART_NUMBER": pn,
        "SERIAL_NUMBER": sn,
        "DESCRIPTION": description,
        "POSITION": position,
        "INSTALL_DATE": install_date,
        "COMMENT": comment,
        "COUNTER": counter,
        "FH": fh,
        "FC": fc,
        "DAYS": days,
        "_page": page_num,
    }


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback (see
    sheet_types/occm.py) -- this variant's SIGNATURES can never match
    through the normal pdfplumber text-extract path since every known
    source file has no text layer at all.

    Anchors on the form title (shared with the born-digital sibling) AND
    "ATLASGLOBAL" (this operator specifically), so a scanned MM_504 export
    from a different operator falls through rather than being claimed here.
    """
    try:
        img = await render_page(pdf_path, 0, dpi=300)
        w, h = img.size
        crop = img.crop((0, 0, w, int(h * 0.15)))
        text = (await ocr_text(crop, psm=6)).upper()
        return "AIRCRAFT INVENTORY REPORT" in text and "ATLASGLOBAL" in text
    except Exception:
        return False


async def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    n_pages = await page_count(pdf_path)
    for page_index in range(n_pages):
        img = await render_page(pdf_path, page_index, dpi=300)
        text = await ocr_text(img, psm=6)
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            rec = _parse_line(line, page_index + 1)
            if rec is not None:
                records.append(rec)
    return records
