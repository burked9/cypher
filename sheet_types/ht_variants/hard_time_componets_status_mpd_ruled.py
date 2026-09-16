""""HT COMPONETS STATUS" -- born-digital, real ruled table, extracted via
pdfplumber's `extract_tables()` rather than coordinate-word-bucketing
(confirmed directly: `page.extract_tables()` returns exactly one clean
table per page with a stable 17-column shape, so pdfplumber's own
cell-boundary detection is used directly instead of re-deriving column
edges from word x-positions or splitting `extract_text()` lines -- the
latter comes back badly interleaved on this file for any cell whose value
wraps across more than one physical line, e.g. a wrapped MFG/OVERHAUL date
pair renders character-by-character-interleaved in `extract_text()`'s own
output while `extract_tables()`'s own cell for that same value reads
cleanly as a plain two-line string, so `extract_tables()` is the only
reliable path here -- confirmed directly against the sample file).

Title line reads "HT COMPONETS STATUS" (the distinctive misspelling
"COMPONETS" for "COMPONENTS" carried through verbatim from the source
document, not a transcription slip here). This is a Hard-Time counterpart
of the existing `occm_variants/cca_a340_occm.py` module's own
"OCCM COMPONETS STATUS" format -- same misspelling, same apparent
reporting family -- but the two are structurally unrelated: the OCCM
sibling has no ruled table at all and is parsed by walking whitespace-
split text lines against a fixed LOCATION token lexicon, while this
file's own table is a real bordered/ruled grid pulled cleanly via
`extract_tables()`. Also checked directly against every other
"Hard Time Component(s)..."-titled HT variant in this package (their own
column layouts and header shapes) -- none match this file's own 17-column
MPD No./DESCRIPTION/MFG DATE/OH-REPAIR DATE/LOC/P-N/S-N/NEXT DUE (FH, FC,
DATE)/LIFE TIME CAL-H/TASK/DATE OF INSTL/CURRENT (FH, FC)/REMAINING
(FH, FC) grid, nor does any of them share this file's own single-line
"A/C Type:<type> MSN:<msn> FH:<fh> FC:<fc> As of date:<date>" header
format.

Header block (repeats verbatim at the top of every page)::

    <A/C TYPE><MSN...> HT COMPONETS STATUS Prepared by: <name>
    A/C Type:<type> MSN:<msn> FH:<fh> FC:<fc> As of date:<date>
    MPD No. DESCRIPTION MFG DATE OH/REPAIR DATE LOC P/N S/N ...

followed by the main ruled data table, one header row, 17 columns::

    MPD No. | DESCRIPTION | MFG DATE | OH/REPAIR DATE | LOC | P/N | S/N |
    NEXT DUE FH | NEXT DUE FC | NEXT DUE DATE | LIFE TIME CAL/H | TASK |
    DATE OF INSTL | CURRENT FH | CURRENT FC | REMAINING FH | REMAINING FC

Row grain: one row per tracked hard-time component/position. Columns,
left to right (matching the ruled table's own cell grid exactly)::

    MPD_NO | DESCRIPTION | MFG_DATE | OH_REPAIR_DATE | LOC | PART_NUMBER |
    SERIAL_NUMBER | NEXT_DUE_FH | NEXT_DUE_FC | NEXT_DUE_DATE | LIFE_LIMIT |
    TASK | DATE_OF_INSTL | CURRENT_FH | CURRENT_FC | REMAINING_FH |
    REMAINING_FC

DATE_OF_INSTL occasionally reads the literal sentinel "OROGINAL" (a
misspelling of "ORIGINAL" carried through verbatim from the source
document, confirmed directly on multiple rows) instead of a date, meaning
the part has been fitted since new/never replaced -- carried through as
its own valid value rather than treated as a parse error.

CURRENT_FH/CURRENT_FC repeat the same report-level flight-hour/cycle
totals on every row of a file (confirmed directly: identical across every
row of the sample file) -- this is the source table's own convention, not
something this parser derives or duplicates.

REMAINING_FH/REMAINING_FC frequently carry the literal Excel error tokens
"#VALUE!"/"#REF!" (the source workbook's own broken formula results,
exported verbatim into the PDF) alongside genuine parenthesised negative
figures (e.g. "(12033)") and plain positive integers -- all three forms
are carried through as-is per this project's convention of never
force-correcting a genuine source-table artifact.

A handful of cells (mostly SERIAL_NUMBER and LIFE_TIME/interval cells)
wrap across two physical lines inside their own ruled cell; the wrapped
text is joined with a single space rather than left with an embedded
newline or guessed apart into separate fields -- this is expected to
surface as a validation flag on the affected field (its pattern
disallows internal spaces) rather than being silently "fixed", per this
project's "never guess a wrong split" convention.

Each page's title line carries "Prepared by: <name>" -- confirmed
directly to be a real person's name in the sample file. It is never
captured into any output field: the parser only reads cells from the
table returned by `page.extract_tables()`, and this line sits entirely
outside that table's own bounding box (it's part of the page's free text
above the table start), so it is structurally excluded rather than
filtered after the fact. Header metadata actually captured (aircraft
type, aircraft MSN, current FH/FC totals, "As of date") comes from the
second header line only, which never carries a person's name.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.ht_variants._base import merged_rules
from shared.cleanup import normalize_dashes

NAME = "Hard Time Componets Status (ATA Ruled)"
SIGNATURES = [
    # Checked against every SIGNATURES list in occm.py/ht.py/llp.py and
    # every existing occm_variants/ht_variants/llp_variants module's own
    # SIGNATURES list (plus a plain grep for "COMPONETS" and "MPD No."
    # across all of them); no collision found. The nearest look-alike is
    # occm_variants/cca_a340_occm.py's own "OCCM COMPONETS STATUS" (that
    # phrase starts with "OCCM", this one with "HT" -- neither is a
    # substring of the other).
    "HT COMPONETS STATUS",
    "MPD No. DESCRIPTION",
]

CANONICAL_COLUMNS = [
    "MPD_NO",
    "DESCRIPTION",
    "MFG_DATE",
    "OH_REPAIR_DATE",
    "LOC",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "NEXT_DUE_FH",
    "NEXT_DUE_FC",
    "NEXT_DUE_DATE",
    "LIFE_LIMIT",
    "TASK",
    "DATE_OF_INSTL",
    "CURRENT_FH",
    "CURRENT_FC",
    "REMAINING_FH",
    "REMAINING_FC",
    # Header metadata -- same on every row of a given page.
    "AC_TYPE",
    "AC_MSN",
    "REPORT_FH",
    "REPORT_FC",
    "REPORT_DATE",
]

_DOTTED_DATE = r"\d{4}\.\d{1,2}(?:\.\d{1,2})?"
_NUM_RE = r"^[\d,]+$"
_REMAINING_RE = r"^(?:\(?-?[\d,]+\)?|#VALUE!|#REF!)$"

_OVERRIDES = {
    "MPD_NO":          {"pattern": r"^[A-Z0-9/\-]+$", "uppercase": True},
    "MFG_DATE":        {"pattern": r"^" + _DOTTED_DATE + r"$", "allow_empty": True},
    "OH_REPAIR_DATE":  {"pattern": r"^(?:[A-Z]{1,2}[/ ])?" + _DOTTED_DATE + r"$|^NEW$",
                         "uppercase": True, "allow_empty": True},
    "LOC":             {"allow_empty": True},
    "NEXT_DUE_FH":     {"pattern": _NUM_RE, "allow_empty": True},
    "NEXT_DUE_FC":     {"pattern": _NUM_RE, "allow_empty": True},
    "NEXT_DUE_DATE":   {"pattern": r"^" + _DOTTED_DATE + r"$", "allow_empty": True},
    "LIFE_LIMIT":      {"allow_empty": True},
    "TASK":            {"pattern": r"^[A-Z]{2,4}(?:/[A-Z]{2,4})*$", "uppercase": True,
                         "allow_empty": True},
    "DATE_OF_INSTL":   {"pattern": r"^(?:" + _DOTTED_DATE + r"|OROGINAL)$",
                         "uppercase": True, "allow_empty": True},
    "CURRENT_FH":      {"pattern": _NUM_RE, "allow_empty": True},
    "CURRENT_FC":      {"pattern": _NUM_RE, "allow_empty": True},
    "REMAINING_FH":    {"pattern": _REMAINING_RE, "allow_empty": True},
    "REMAINING_FC":    {"pattern": _REMAINING_RE, "allow_empty": True},
    "AC_TYPE":         {"pattern": r"^[A-Z0-9\-]+$", "uppercase": True, "allow_empty": True},
    "AC_MSN":          {"pattern": r"^\d+$", "allow_empty": True},
    "REPORT_FH":       {"pattern": _NUM_RE, "allow_empty": True},
    "REPORT_FC":       {"pattern": _NUM_RE, "allow_empty": True},
    "REPORT_DATE":     {"pattern": r"^\d{1,2}-[A-Za-z]{3}-\d{2,4}$", "allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_HEADER_FIRST_CELL = "MPD No."
_NUM_COLUMNS = 17

_HEADER_LINE_RE = re.compile(
    r"A/C Type:(?P<type>\S+)\s+MSN:(?P<msn>\S+)\s+FH:(?P<fh>\S+)\s+FC:(?P<fc>\S+)"
    r"\s+As of date:(?P<date>\S+)",
    re.IGNORECASE,
)


def _clean_cell(value: str | None) -> str:
    if not value:
        return ""
    # Multi-line cell content (wrapped text within one ruled cell) is
    # joined with a single space rather than left with an embedded
    # newline.
    text = " ".join(value.split())
    return normalize_dashes(text)


def _parse_page_meta(page) -> dict:
    text = page.extract_text() or ""
    meta = {"AC_TYPE": "", "AC_MSN": "", "REPORT_FH": "", "REPORT_FC": "", "REPORT_DATE": ""}
    m = _HEADER_LINE_RE.search(text)
    if m:
        meta["AC_TYPE"] = m.group("type")
        meta["AC_MSN"] = m.group("msn")
        meta["REPORT_FH"] = m.group("fh")
        meta["REPORT_FC"] = m.group("fc")
        meta["REPORT_DATE"] = m.group("date")
    return meta


def _extract_page_rows(page) -> list[dict]:
    meta = _parse_page_meta(page)
    rows_out: list[dict] = []

    for table in page.extract_tables():
        for raw in table:
            cells = [_clean_cell(c) for c in raw]
            if not any(cells):
                continue
            if cells[0] == _HEADER_FIRST_CELL:
                # Column header row.
                continue
            if len(cells) < _NUM_COLUMNS:
                continue
            if not cells[0]:
                # Not a recognisable data row (e.g. stray/blank trailer
                # row) -- skip rather than force it into a row.
                continue

            row = {
                "MPD_NO": cells[0],
                "DESCRIPTION": cells[1],
                "MFG_DATE": cells[2],
                "OH_REPAIR_DATE": cells[3],
                "LOC": cells[4],
                "PART_NUMBER": cells[5],
                "SERIAL_NUMBER": cells[6],
                "NEXT_DUE_FH": cells[7],
                "NEXT_DUE_FC": cells[8],
                "NEXT_DUE_DATE": cells[9],
                "LIFE_LIMIT": cells[10],
                "TASK": cells[11],
                "DATE_OF_INSTL": cells[12],
                "CURRENT_FH": cells[13],
                "CURRENT_FC": cells[14],
                "REMAINING_FH": cells[15],
                "REMAINING_FC": cells[16],
            }
            row.update(meta)
            rows_out.append(row)

    return rows_out


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            for row in _extract_page_rows(page):
                row["_page"] = page_num
                records.append(row)
    return records
