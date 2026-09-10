"""OCCM Inventory (Spanish SAP-style header) -- real text layer, single-line
rows keyed on a compound "Ubicac.técnica" (technical location) code.

Confirmed on a real corpus file (multi-page, genuine pdfplumber text layer
throughout -- no OCR needed). The column-header row reads (Spanish SAP
labels)::

    Ubicac.técnica  Denominación  Material  Número de serie  Válido de

...i.e. Technical Location / Designation / Material / Serial Number /
Valid-From (date). It repeats once at the top of the document, not per
page.

Each data row is a single line, e.g. (genericized)::

    <reg> -ATA<cc>-<ss>-<pp>-<seq> <DESCRIPTION> <pn>:<code> <sn> <dd/mm/yyyy>

Ubicac.técnica is itself a compound string: the aircraft registration
(constant across every row in the file -- a cross-reference back to the
document header, not per-row data, so it's dropped rather than carried on
every record, matching this package's other compound-code variants e.g.
`fl_compound_code_occm.py` / `occm_list_func_loc_scanned.py`) immediately
followed by a hyphenated ATA-adjacent code of the shape
``-ATA<chapter>-<sub>-<sub>-<seq>`` (segment count after the chapter varies
row to row -- confirmed directly across the real sample file, e.g. some
rows stop after a single two-part suffix like ``-ATA22-66`` with no further
segments). Only the 2-digit ATA chapter is pulled into its own ATA column
(cross-format consistency / ATA-based tooling); everything from the chapter
onward is kept verbatim as POSITION_CODE, since the sub-chapter/sequence
segments don't follow one single fixed-width shape -- re-splitting further
risks a wrong split more than it helps.

Material is also a compound string, shaped ``<part_number>:<code>``. The
colon is a clean, consistent separator (confirmed directly across every row
of the real sample file -- it appears exactly once per Material cell, with
non-empty text on both sides, no exceptions found), so it is split into
PART_NUMBER and MATERIAL_CODE. The trailing code is a short alphanumeric
token always observed starting with a leading letter (e.g. a material-master
/ valuation-class style reference distinct from the part number itself);
its exact business meaning in the source system is not confirmed from the
document alone, so it is kept as an opaque verbatim column rather than
interpreted further.

Número de serie (serial number) is genuinely blank on a meaningful minority
of rows in the real sample file (roughly a third -- confirmed directly,
these are contiguous runs of rows sharing one ATA chapter, consistent with
non-serialized consumable-type parts) -- the row parser treats it as
optional rather than requiring exactly 6 tokens per row.

Válido de (valid-from date, ``dd/mm/yyyy``) is kept under its own
VALID_FROM column name rather than a generic INSTALL_DATE: the header's own
label is "valid from", not "installed", and nothing else in the document
confirms these are install dates specifically -- naming it INSTALL_DATE
would be an unconfirmed assumption about what the date actually represents.

No TSN/CSN or position columns are present anywhere in this format.

Row anchor: every row starts with a registration token immediately followed
by a hyphen-ATA-digit code (``<reg> -ATA<cc>...``) and ends with a
``dd/mm/yyyy`` date. Whatever sits between the Ubicac.técnica token and the
Material token (itself identified by its own ``<pn>:<code>`` shape, which is
otherwise unambiguous in this format -- no other field contains a colon) is
DESCRIPTION.

Unicode dash variants (seen throughout the real sample file's Ubicac.técnica
and Material cells, e.g. U+2010 in place of ASCII '-') are normalized to
ASCII '-' before the row-anchor regex runs, per this package's usual
`normalize_dashes` convention -- required here because the row-anchor
pattern itself matches on a literal ASCII hyphen.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules
from shared.cleanup import normalize_dashes

NAME = "OCCM Inventory (SAP-ES)"
SIGNATURES = [
    "Ubicac.técnica Denominación Material Número de serie Válido de",
]

CANONICAL_COLUMNS = [
    "ATA",
    "POSITION_CODE",
    "DESCRIPTION",
    "PART_NUMBER",
    "MATERIAL_CODE",
    "SERIAL_NUMBER",
    "VALID_FROM",
]

_OVERRIDES = {
    "POSITION_CODE": {"pattern": r"^ATA\d{2}(?:-[A-Z0-9]+)*$", "uppercase": True},
    "MATERIAL_CODE": {"pattern": r"^[A-Z0-9]+$", "uppercase": True},
    "SERIAL_NUMBER": {"allow_empty": True},
    "VALID_FROM": {"pattern": r"^\d{2}/\d{2}/\d{4}$"},
}
RULES = merged_rules(_OVERRIDES)

# Row anchor: "<reg> -ATA<cc>[-<sub>...]". Dashes already normalized to ASCII.
_ROW_RE = re.compile(
    r"^(?P<reg>[A-Z0-9]{3,8})\s+"
    r"-(?P<code>ATA\d{2}(?:-[A-Z0-9]+)*)\s+"
    r"(?P<desc>.+?)\s+"
    r"(?P<pn>[A-Z0-9./,\-]+):(?P<matcode>[A-Z0-9]+)\s+"
    r"(?:(?P<sn>\S+)\s+)?"
    r"(?P<date>\d{2}/\d{2}/\d{4})$"
)


def _parse_line(line: str, page_num: int) -> dict | None:
    m = _ROW_RE.match(line.strip())
    if not m:
        return None
    code = m.group("code")
    ata_m = re.match(r"^ATA(\d{2})", code)
    ata = ata_m.group(1) if ata_m else ""
    return {
        "ATA": ata,
        "POSITION_CODE": code,
        "DESCRIPTION": m.group("desc"),
        "PART_NUMBER": m.group("pn"),
        "MATERIAL_CODE": m.group("matcode"),
        "SERIAL_NUMBER": m.group("sn") or "",
        "VALID_FROM": m.group("date"),
        "_page": page_num,
    }


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if not text:
                continue
            text = normalize_dashes(text)
            for raw in text.splitlines():
                line = raw.strip()
                if not line or line.startswith("Ubicac"):
                    continue
                rec = _parse_line(line, page_num)
                if rec is not None:
                    records.append(rec)
    return records
