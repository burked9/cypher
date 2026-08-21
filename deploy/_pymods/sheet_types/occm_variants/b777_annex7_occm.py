"""B777 Annex 7 / 'Annex 6' — master parts template, NOT operational OCCM.

Five-file cluster (B777-300ER lease-package master parts lists, split by
area: Airframe / Engine / APU / Landing Gear / Airframe-msn34571). The
header literally says ``ANNEX 6:`` even though filenames say ``Annex 7`` —
that's a document-author typo and is our most distinctive signature.

Row layout has only three logical fields::

    Ref  Part-No (Material)  Equipment Description

Example::

    1 4100945B B777 HS PBH: FAN - MIXED FLOW 7.5" DIA

Critically these files carry **no Serial Number, no Functional Location,
no Position, no ATA chapter, no Install Date.** They're a master parts
inventory ("the parts a B777-300ER comes with from the seller"), useful as
a template for synthetic-OCCM generation in the forked dummy-positions
session, not as positions data.

Each row will land in the positions table with empty position/serial/ATA;
callers should filter by `variant='B777 Annex 7 OCCM'` to grab template
data, or by `position <> ''` to exclude template rows from positions queries.

The Ref number sequences within each area file but isn't a position — it's
just a row counter, often repeats the same PN over consecutive Refs (e.g.
`2-1693 GOODRICH CPBL BRAKE AY MLG` appears 7 times because a B777 has 7
main-gear brakes).

Distinct from `b777_annex8_occm.py` — Annex 8 carries Functional Location
per row and IS operational OCCM (parsed elsewhere as positions data).
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "B777 Annex 7 OCCM"
SIGNATURES = [
    "ANNEX 6:",                  # the document-author typo, very specific
    "B777-300ER Airframe OCCM",
    "B777-300ER ENGINE OCCM",
    "B777-300ER APU OCCM",
    "B777-300ER LANDING GEAR OCCM",
]

CANONICAL_COLUMNS = [
    "REF",
    "PART_NUMBER",
    "DESCRIPTION",
    "AREA",   # derived from filename: Airframe / Engine / APU / LG
]

_OVERRIDES = {
    "REF":         {"pattern": r"^\d{1,5}$"},
    "AREA":        {"pattern": r"^[A-Z][A-Z0-9 _-]{1,30}$", "uppercase": True,
                    "allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_REF_RE = re.compile(r"^\d{1,5}$")
# A part number in this format is essentially "anything alphanumeric with at
# least one digit and at least 4 chars" — e.g. `4100945B`, `2-1693`, `161W1000-81`,
# `UA541461-14`. Used to confirm the second token is plausibly a PN.
_PN_LIKELY = re.compile(r"^[A-Z0-9][A-Z0-9./\-]{2,}$")


def _derive_area(filename: str) -> str:
    """Pull the sub-area (Airframe / Engine / APU / LG) from the filename."""
    s = filename.lower()
    if "airframe" in s:
        return "AIRFRAME"
    if "engine" in s:
        return "ENGINE"
    if "apu" in s:
        return "APU"
    if "landing gear" in s or "_lg_" in s or " lg " in s.lower() or "lg occm" in s:
        return "LG"
    return ""


def _parse_line(line: str, page_num: int, area: str) -> dict | None:
    toks = line.split()
    if len(toks) < 3:
        return None
    if not _REF_RE.match(toks[0]):
        return None
    pn = toks[1]
    if not _PN_LIKELY.match(pn):
        return None
    description = " ".join(toks[2:]).strip()
    if not description:
        return None
    return {
        "REF": toks[0],
        "PART_NUMBER": pn,
        "DESCRIPTION": description,
        "AREA": area,
        "_page": page_num,
    }


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    area = _derive_area(pdf_path)
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if len(text) < 30:
                continue
            for raw in text.splitlines():
                line = raw.strip()
                if not line:
                    continue
                rec = _parse_line(line, page_num, area)
                if rec is not None:
                    records.append(rec)
    return records
