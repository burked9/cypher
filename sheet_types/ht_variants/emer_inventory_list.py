""""EMER INVENTORY <MSN> rev<NN>" -- born-digital, full text layer,
multi-section emergency-equipment hard-time inventory (confirmed directly
against the real sample file with pdfplumber: every page has a populated
text layer and `extract_tables()` returns one clean ruled/aligned table
per page -- no OCR needed, and no handwritten content anywhere).

This is a single multi-page report made of eight distinct sub-sections,
each with its own column layout, one section per page (except the
passenger-life-vest section, which spans several consecutive pages). Every
page repeats the same two-line header -- the report title line
("EMER INVENTORY <MSN> rev<NN>") then the section title line -- and ends
with a "<dd/mm/yyyy> // Page <n>" footer line (the footer date is absent
on the file's own final page).

Section titles seen (second line of each page's text, with the
"// <suffix>" part, where present, being a passenger-count or category
annotation rather than a routing key)::

    PBE LIST
    CARTRIDGES INVENTORY
    PORTABLE O2 BOTTLES INVENTORY
    PORTABLE EXTINGUISHERS INVENTORY
    LAV EXTINGUISHERS INVENTORY
    PASSENGERS LIFE VEST INVENTORY // <n> PAX
    ATTENDANT AND CREW LIFE VEST
    supplementary life vest // adult + infants

Row grain: one row per tracked component/position, except on the
CARTRIDGES INVENTORY section (see below). Columns are unified across all
eight section layouts into one canonical column set; a column that has no
counterpart in a given section's own table is left blank on that
section's rows rather than guessed -- this is a structural absence (the
source table has no such column at all on that page), not missing data.

CARTRIDGES INVENTORY layout is a genuine two-sub-component-per-row table
(confirmed directly via `extract_tables()`, not a guess): the header row
reads `FIN | PN | SN | FIN | PN | SN | MFG date | EASA CERT` -- i.e. a
"Main Assy" FIN/PN/SN triplet followed by a "Cartridge" FIN/PN/SN triplet,
with MFG date and EASA CERT trailing. Several rows populate only one of
the two triplets (the other left blank by the source table), and the
MFG date / EASA CERT pair is only ever populated alongside the Cartridge
triplet, never the Main Assy one -- confirmed directly: rows with a blank
Cartridge triplet also have a blank MFG date / EASA CERT, and rows with
only a Cartridge triplet (blank Main Assy) still have MFG date / EASA CERT
populated. This is the source table's own convention (the cartridge is
the life-limited consumable; the main assembly housing isn't), not a
guessed split. This parser therefore emits up to two records per
CARTRIDGES INVENTORY row -- one per populated triplet -- tagged via
COMPONENT_GROUP ("Main Assy" / "Cartridge"), with MANUFACTURING_DATE and
BATCH_OR_CERT populated only on the Cartridge record, matching the source
table's own layout rather than force-sharing them across both.

Header metadata (AC_MSN, REPORT_DATE) is parsed once per page from that
page's own title/footer lines and stamped on every row extracted from
that page.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.ht_variants._base import merged_rules
from shared.cleanup import normalize_dashes

NAME = "Emergency Equipment Inventory List"

SIGNATURES = [
    # Checked against every SIGNATURES list in occm.py/ht.py/llp.py and
    # every occm_variants/ht_variants/llp_variants module's own SIGNATURES
    # list (plus a plain grep for "EMER INVENTORY", "PBE LIST",
    # "CARTRIDGES INVENTORY", "PORTABLE O2 BOTTLES", "PORTABLE
    # EXTINGUISHERS INVENTORY", "LAV EXTINGUISHERS INVENTORY", "PASSENGERS
    # LIFE VEST", "ATTENDANT AND CREW LIFE VEST" and "supplementary life
    # vest" across all of them); no collision found.
    "EMER INVENTORY MSN",
]

CANONICAL_COLUMNS = [
    "REPORT_SECTION",
    "COMPONENT_GROUP",
    "LINE",
    "POSITION",
    "LOCATION",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "FIN",
    "MANUFACTURING_DATE",
    "VALIDITY_DATE",
    "INSPECTED_DATE",
    "REINSPECTED_DATE",
    "BATCH_OR_CERT",
    # Header metadata -- same on every row of a given page.
    "AC_MSN",
    "REPORT_DATE",
]

# Mixed-format date column covering every date shape seen directly in the
# sample file across its eight sections: "Jun-26" / "MAY 2022" (word +
# separator + 2-4 digit year), "15/01/2019" / "28-08-2023" (D/M/Y with
# either separator), "02/2019" (M/Y), a bare "2018" (year only), and
# "1-Jun-10" (day + word-month + year, all dash-separated -- the passenger
# life vest and supplementary sections' own format).
_DATE_RE = (
    r"^(?:"
    r"\d{4}"
    r"|\d{1,2}[/-]\d{4}"
    r"|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"
    r"|\d{1,2}-[A-Za-zÀ-ÿ]{3,9}-\d{2,4}"
    r"|[A-Za-zÀ-ÿ]{3,9}[\s.-]\d{2,4}"
    r")$"
)
_REPORT_DATE_RE = r"^\d{2}/\d{2}/\d{4}$"

_OVERRIDES = {
    "REPORT_SECTION":     {"allow_empty": True},
    "COMPONENT_GROUP":    {"allow_empty": True},
    "LINE":               {"pattern": r"^\d+$", "allow_empty": True},
    "POSITION":           {"allow_empty": True},
    "LOCATION":           {"allow_empty": True},
    # DESCRIPTION only exists on the O2-bottle and portable-extinguisher
    # sections (a repeated equipment-name cell, e.g. "PORT O2 BOTTLE") --
    # every other section's own table has no such column at all.
    "DESCRIPTION":        {"allow_empty": True},
    "PART_NUMBER":        {"allow_empty": True},
    "SERIAL_NUMBER":      {"allow_empty": True},
    "FIN":                {"allow_empty": True},
    "MANUFACTURING_DATE": {"pattern": _DATE_RE, "allow_empty": True},
    "VALIDITY_DATE":      {"pattern": _DATE_RE, "allow_empty": True},
    "INSPECTED_DATE":     {"pattern": _DATE_RE, "allow_empty": True},
    "REINSPECTED_DATE":   {"pattern": _DATE_RE, "allow_empty": True},
    "BATCH_OR_CERT":      {"allow_empty": True},
    "AC_MSN":             {"pattern": r"^\d+$", "allow_empty": True},
    "REPORT_DATE":        {"pattern": _REPORT_DATE_RE, "allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_MSN_RE = re.compile(r"MSN0*(\d+)", re.IGNORECASE)
_FOOTER_DATE_RE = re.compile(r"^(\d{2}/\d{2}/\d{4})\s*//")

_SECTION_TITLES = [
    "PBE LIST",
    "CARTRIDGES INVENTORY",
    "PORTABLE O2 BOTTLES INVENTORY",
    "PORTABLE EXTINGUISHERS INVENTORY",
    "LAV EXTINGUISHERS INVENTORY",
    "PASSENGERS LIFE VEST INVENTORY",
    "ATTENDANT AND CREW LIFE VEST",
    "SUPPLEMENTARY LIFE VEST",
]


def _clean_cell(value) -> str:
    if not value:
        return ""
    text = " ".join(str(value).split())
    return normalize_dashes(text)


def _row_blank(cells: list[str]) -> bool:
    return not any(cells)


def _parse_page_meta(lines: list[str]) -> tuple[str, dict]:
    """Returns (section_key, meta). section_key is "" if this page's own
    title line doesn't match one of the known section titles -- callers
    skip such pages rather than guessing a section."""
    meta = {"AC_MSN": "", "REPORT_DATE": ""}
    if not lines:
        return "", meta
    m = _MSN_RE.search(lines[0])
    if m:
        meta["AC_MSN"] = m.group(1)
    if len(lines) > 1:
        title = lines[1].split("//", 1)[0].strip().upper()
    else:
        title = ""
    section_key = title if title in _SECTION_TITLES else ""
    if lines:
        m = _FOOTER_DATE_RE.match(lines[-1].strip())
        if m:
            meta["REPORT_DATE"] = m.group(1)
    return section_key, meta


def _base_row(section_key: str, meta: dict) -> dict:
    return {
        "REPORT_SECTION": section_key,
        "COMPONENT_GROUP": "",
        "LINE": "",
        "POSITION": "",
        "LOCATION": "",
        "DESCRIPTION": "",
        "PART_NUMBER": "",
        "SERIAL_NUMBER": "",
        "FIN": "",
        "MANUFACTURING_DATE": "",
        "VALIDITY_DATE": "",
        "INSPECTED_DATE": "",
        "REINSPECTED_DATE": "",
        "BATCH_OR_CERT": "",
        "AC_MSN": meta.get("AC_MSN", ""),
        "REPORT_DATE": meta.get("REPORT_DATE", ""),
    }


def _extract_pbe(cells: list[str], section_key: str, meta: dict) -> list[dict]:
    row = _base_row(section_key, meta)
    row["PART_NUMBER"] = cells[0] if len(cells) > 0 else ""
    row["SERIAL_NUMBER"] = cells[1] if len(cells) > 1 else ""
    row["POSITION"] = cells[2] if len(cells) > 2 else ""
    row["VALIDITY_DATE"] = cells[3] if len(cells) > 3 else ""
    return [row]


def _extract_cartridges(cells: list[str], section_key: str, meta: dict) -> list[dict]:
    out = []
    main_fin = cells[0] if len(cells) > 0 else ""
    main_pn = cells[1] if len(cells) > 1 else ""
    main_sn = cells[2] if len(cells) > 2 else ""
    cart_fin = cells[3] if len(cells) > 3 else ""
    cart_pn = cells[4] if len(cells) > 4 else ""
    cart_sn = cells[5] if len(cells) > 5 else ""
    mfg_date = cells[6] if len(cells) > 6 else ""
    easa_cert = cells[7] if len(cells) > 7 else ""

    if main_fin or main_pn or main_sn:
        row = _base_row(section_key, meta)
        row["COMPONENT_GROUP"] = "Main Assy"
        row["FIN"] = main_fin
        row["PART_NUMBER"] = main_pn
        row["SERIAL_NUMBER"] = main_sn
        out.append(row)

    if cart_fin or cart_pn or cart_sn or mfg_date or easa_cert:
        row = _base_row(section_key, meta)
        row["COMPONENT_GROUP"] = "Cartridge"
        row["FIN"] = cart_fin
        row["PART_NUMBER"] = cart_pn
        row["SERIAL_NUMBER"] = cart_sn
        row["MANUFACTURING_DATE"] = mfg_date
        row["BATCH_OR_CERT"] = easa_cert
        out.append(row)

    return out


def _extract_o2_bottles(cells: list[str], section_key: str, meta: dict) -> list[dict]:
    # Columns (confirmed directly via extract_tables(), not the merged
    # single-cell header text): DESCRIPTION | P/N | S/N | POS | MFD |
    # VALIDITY -- a leading equipment-name cell (e.g. "PORT O2 BOTTLE"),
    # not part of the P/N.
    row = _base_row(section_key, meta)
    row["DESCRIPTION"] = cells[0] if len(cells) > 0 else ""
    row["PART_NUMBER"] = cells[1] if len(cells) > 1 else ""
    row["SERIAL_NUMBER"] = cells[2] if len(cells) > 2 else ""
    row["POSITION"] = cells[3] if len(cells) > 3 else ""
    row["MANUFACTURING_DATE"] = cells[4] if len(cells) > 4 else ""
    row["VALIDITY_DATE"] = cells[5] if len(cells) > 5 else ""
    return [row]


def _extract_extinguishers(cells: list[str], section_key: str, meta: dict) -> list[dict]:
    # Columns (confirmed directly via extract_tables()): DESCRIPTION | P/N
    # | S/N | LOCATION | POSITION | MFD -- same leading equipment-name
    # cell pattern as the O2-bottle section.
    row = _base_row(section_key, meta)
    row["DESCRIPTION"] = cells[0] if len(cells) > 0 else ""
    row["PART_NUMBER"] = cells[1] if len(cells) > 1 else ""
    row["SERIAL_NUMBER"] = cells[2] if len(cells) > 2 else ""
    row["LOCATION"] = cells[3] if len(cells) > 3 else ""
    row["POSITION"] = cells[4] if len(cells) > 4 else ""
    row["MANUFACTURING_DATE"] = cells[5] if len(cells) > 5 else ""
    return [row]


def _extract_lav_extinguishers(cells: list[str], section_key: str, meta: dict) -> list[dict]:
    row = _base_row(section_key, meta)
    row["POSITION"] = cells[0] if len(cells) > 0 else ""
    row["PART_NUMBER"] = cells[1] if len(cells) > 1 else ""
    row["SERIAL_NUMBER"] = cells[2] if len(cells) > 2 else ""
    row["MANUFACTURING_DATE"] = cells[3] if len(cells) > 3 else ""
    row["BATCH_OR_CERT"] = cells[4] if len(cells) > 4 else ""
    return [row]


def _extract_passenger_vests(cells: list[str], section_key: str, meta: dict) -> list[dict]:
    row = _base_row(section_key, meta)
    row["LINE"] = cells[0] if len(cells) > 0 else ""
    row["POSITION"] = cells[1] if len(cells) > 1 else ""
    row["PART_NUMBER"] = cells[2] if len(cells) > 2 else ""
    row["SERIAL_NUMBER"] = cells[3] if len(cells) > 3 else ""
    row["MANUFACTURING_DATE"] = cells[4] if len(cells) > 4 else ""
    row["INSPECTED_DATE"] = cells[5] if len(cells) > 5 else ""
    row["REINSPECTED_DATE"] = cells[6] if len(cells) > 6 else ""
    row["BATCH_OR_CERT"] = cells[7] if len(cells) > 7 else ""
    return [row]


def _extract_crew_vests(cells: list[str], section_key: str, meta: dict) -> list[dict]:
    row = _base_row(section_key, meta)
    row["POSITION"] = cells[0] if len(cells) > 0 else ""
    row["PART_NUMBER"] = cells[1] if len(cells) > 1 else ""
    row["SERIAL_NUMBER"] = cells[2] if len(cells) > 2 else ""
    row["MANUFACTURING_DATE"] = cells[3] if len(cells) > 3 else ""
    row["INSPECTED_DATE"] = cells[4] if len(cells) > 4 else ""
    row["REINSPECTED_DATE"] = cells[5] if len(cells) > 5 else ""
    row["BATCH_OR_CERT"] = cells[6] if len(cells) > 6 else ""
    return [row]


def _extract_supplementary_vests(cells: list[str], section_key: str, meta: dict) -> list[dict]:
    row = _base_row(section_key, meta)
    row["PART_NUMBER"] = cells[0] if len(cells) > 0 else ""
    row["SERIAL_NUMBER"] = cells[1] if len(cells) > 1 else ""
    row["MANUFACTURING_DATE"] = cells[2] if len(cells) > 2 else ""
    row["INSPECTED_DATE"] = cells[3] if len(cells) > 3 else ""
    row["REINSPECTED_DATE"] = cells[4] if len(cells) > 4 else ""
    row["BATCH_OR_CERT"] = cells[5] if len(cells) > 5 else ""
    return [row]


# Each section's own row-extraction function, keyed by section title.
_SECTION_HANDLERS = {
    "PBE LIST": _extract_pbe,
    "CARTRIDGES INVENTORY": _extract_cartridges,
    "PORTABLE O2 BOTTLES INVENTORY": _extract_o2_bottles,
    "PORTABLE EXTINGUISHERS INVENTORY": _extract_extinguishers,
    "LAV EXTINGUISHERS INVENTORY": _extract_lav_extinguishers,
    "PASSENGERS LIFE VEST INVENTORY": _extract_passenger_vests,
    "ATTENDANT AND CREW LIFE VEST": _extract_crew_vests,
    "SUPPLEMENTARY LIFE VEST": _extract_supplementary_vests,
}

# Each section's own non-data header row(s), as the row's non-blank cells
# joined with single spaces and upper-cased -- confirmed directly against
# `extract_tables()` output for every page in the sample file. Matched by
# whole-row joined text rather than by first-cell value alone because two
# of the eight sections' header rows don't split into per-column cells the
# way their data rows do: PORTABLE O2 BOTTLES INVENTORY's header lands in
# `extract_tables()` as a single merged cell holding the whole header
# string ("P/N S/N POS MFD VALIDITY"), and PORTABLE EXTINGUISHERS
# INVENTORY's header row has a blank leading cell (its first real header
# label, "P/N", sits in cells[1], not cells[0]) -- a first-cell-only check
# would either miss these rows entirely (leaking the header text in as a
# bogus data record) or require a different, error-prone special case per
# section. CARTRIDGES INVENTORY carries two such header rows on every
# page: a "Main Assy"/"Cartridge" group-label row above the real
# "FIN"/"PN"/"SN" column-header row.
_SECTION_HEADER_TEXT = {
    "PBE LIST": {"P/N S/N POS VALIDITY"},
    "CARTRIDGES INVENTORY": {
        "MAIN ASSY CARTRIDGE",
        "FIN PN SN FIN PN SN MFG DATE EASA CERT",
    },
    "PORTABLE O2 BOTTLES INVENTORY": {"P/N S/N POS MFD VALIDITY"},
    "PORTABLE EXTINGUISHERS INVENTORY": {"P/N S/N LOCATION POSITION MFD"},
    "LAV EXTINGUISHERS INVENTORY": {"LAVATORY PN SN MANUF DATE EASA"},
    "PASSENGERS LIFE VEST INVENTORY": {
        "LINE POSITION GILETS P/N S/N MANUFACTURING DATE INSPECTED DATE "
        "REINSPECTED DATE BATCH",
    },
    "ATTENDANT AND CREW LIFE VEST": {
        "LIFE VEST POSITION P/N S/N MANUFACTURING DATE INSPECTED DATE "
        "REINSPECTED DATE BATCH",
    },
    "SUPPLEMENTARY LIFE VEST": {
        "P/N S/N MANUFACTURING DATE INSPECTED DATE REINSPECTED DATE BATCH",
    },
}


def _joined_text(cells: list[str]) -> str:
    return " ".join(c for c in cells if c).upper()


def _extract_page_rows(page) -> list[dict]:
    text = page.extract_text() or ""
    lines = text.splitlines()
    section_key, meta = _parse_page_meta(lines)
    if section_key not in _SECTION_HANDLERS:
        return []
    handler = _SECTION_HANDLERS[section_key]
    header_texts = _SECTION_HEADER_TEXT[section_key]

    rows_out: list[dict] = []
    for table in page.extract_tables():
        for raw in table:
            cells = [_clean_cell(c) for c in raw]
            if _row_blank(cells):
                continue
            if _joined_text(cells) in header_texts:
                # Non-data header/group-label row -- skip.
                continue
            rows_out.extend(handler(cells, section_key, meta))
    return rows_out


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            records.extend(_extract_page_rows(page))
    return records
