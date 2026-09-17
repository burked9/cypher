""""HT-COMPONENT" -- born-digital, full text layer (confirmed via a direct
pdfplumber `extract_text()`/`extract_words()` pass over the real sample
file: text is present, well-formed and correctly encoded on every page, no
OCR needed and no broken-font-encoding symptoms observed).

Header block (repeats verbatim at the top of every page)::

    <A/C REG> HT-COMPONENT A/C FH : <hours> FC : <cycles>
    (Date : <dd.mm.yyyy> Time : <hh:mm:ss>)
    (C OF A)
    Functional Location  Part number  Equipment text  Serial number
        Interval  Unit  Rem.life  End Date

Row grain: one row per tracked hard-time component position. Each data row
is a single physical text line, plain space-delimited (this MIS export is
*not* a fixed-coordinate table -- confirmed directly: the "Equipment text"
and "Serial number" fields' own x-positions drift row to row depending on
how long the preceding field's text is, e.g. a longer multi-word equipment
description pushes the serial-number token noticeably left of where it
sits on short-description rows. Only the first two fields (Functional
Location, Part number) and the trailing block starting at Interval keep a
genuinely fixed x-position throughout).

Because the columns aren't coordinate-fixed, rows are parsed by
whitespace-tokenizing the line and anchoring from **both ends**, which is
safe here because the last four fields have a fixed, unambiguous token
shape that appears nowhere else on a data line:

    tokens[0]    = FUNCTIONAL_LOCATION  (always one token, no internal space)
    tokens[1]    = PART_NUMBER          (always one token, no internal space)
    tokens[-1]   = END_DATE             (dd.mm.yyyy)
    tokens[-2]   = REM_LIFE             (signed integer)
    tokens[-3]   = UNIT                 (DAY | FH | FC)
    tokens[-4]   = INTERVAL             (letter-prefixed code, e.g. HBB2500)
    tokens[-5]   = SERIAL_NUMBER        (always one token, no internal space)
    tokens[2:-5] = EQUIPMENT_TEXT       (zero or more tokens, joined with a
                                          single space -- this is the only
                                          variable-width field, e.g. "VCP -
                                          HI 8" or "RESERVIOR ASSEMBLY
                                          900CU.IN")

This "last four fixed, first two fixed, middle is EQUIPMENT_TEXT" split was
checked directly against every one of this file's own rows (confirmed via
a full-corpus scan of `extract_text()` line tokens): the trailing
END_DATE/REM_LIFE/UNIT/INTERVAL quartet matches its own fixed pattern on
every genuine data row and on no header/title/footer line, so it is a
reliable anchor rather than a guess -- including on rows where the
equipment description is long enough that SERIAL_NUMBER's own x-position
visually drifts well left of the column header's nominal x (e.g. a serial
number carrying a bracketed prefix): tokens[-5] still lands on the correct
serial-number token in every such case because it's counted from the
fixed-shape tail, not from any x-coordinate.

Repeating page furniture skipped outright (never merged into a data row):
- the page title line ("<A/C REG> HT-COMPONENT A/C FH : ... FC : ...")
- the "(Date : ... Time : ...)" line
- the "(C OF A)" line
- the column-header line itself
- the final page's "Prepared by: <name>" signature line, which can carry a
  real individual's name -- this line has too few whitespace tokens (and
  its own trailing token never matches the END_DATE pattern) to satisfy
  the data-row shape above, so it is naturally skipped rather than
  requiring a dedicated regex; confirmed directly that no name from this
  line is captured into any output field.

Header metadata (aircraft registration, flight hours, flight cycles,
report date, report time) is parsed once from page 1's own title/date
lines and stamped on every row.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.ht_variants._base import merged_rules

NAME = "Functional Location HT Component"
SIGNATURES = [
    # Checked against every SIGNATURES list in occm.py/ht.py/llp.py and
    # every occm_variants/ht_variants/llp_variants module (including a
    # plain grep for "HT-COMPONENT"); no collision found.
    "HT-COMPONENT",
    # The full column-header line, verbatim -- a second, independent
    # anchor. Checked the same way; no collision found either as a whole
    # phrase or as a substring of any other variant's own signature in
    # either direction.
    "Functional Location Part number Equipment text Serial number Interval Unit Rem.life End Date",
]

CANONICAL_COLUMNS = [
    "FUNCTIONAL_LOCATION",
    "PART_NUMBER",
    "EQUIPMENT_TEXT",
    "SERIAL_NUMBER",
    "INTERVAL",
    "UNIT",
    "REM_LIFE",
    "END_DATE",
    # Header metadata -- same on every row of a given file.
    "AC_REG",
    "AC_FH",
    "AC_FC",
    "REPORT_DATE",
    "REPORT_TIME",
]

_END_DATE_RE = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")
_REM_LIFE_RE = re.compile(r"^-?\d+$")
_UNIT_RE = re.compile(r"^(DAY|FH|FC)$")
_INTERVAL_RE = re.compile(r"^[A-Z]{2,4}\d+$")

_TITLE_RE = re.compile(
    r"^(\S+)\s+HT-COMPONENT\s+A/C\s+FH\s*:\s*([\d.]+)\s+FC\s*:\s*(\d+)"
)
_DATE_TIME_RE = re.compile(r"\(Date\s*:\s*(\S+)\s+Time\s*:\s*([\d:]+)\)")
_HEADER_ROW_RE = re.compile(r"^Functional\s+Location\s+Part\s+number")

_NUM_RE = r"^-?\d+(?:\.\d+)?$"
_DATE_RE = r"^\d{2}\.\d{2}\.\d{4}$"

_OVERRIDES = {
    "FUNCTIONAL_LOCATION": {"allow_empty": True},
    "EQUIPMENT_TEXT":      {"allow_empty": True},
    "INTERVAL":            {"pattern": r"^[A-Z0-9]+$", "uppercase": True,
                             "allow_empty": True},
    "UNIT":                {"pattern": r"^(DAY|FH|FC)$", "uppercase": True,
                             "allow_empty": True},
    "REM_LIFE":            {"pattern": r"^-?\d+$", "allow_empty": True},
    "END_DATE":            {"pattern": _DATE_RE, "allow_empty": True},
    "AC_REG":              {"pattern": r"^[A-Z0-9\-]+$", "uppercase": True,
                             "allow_empty": True},
    "AC_FH":               {"pattern": _NUM_RE, "allow_empty": True},
    "AC_FC":               {"pattern": r"^\d+$", "allow_empty": True},
    "REPORT_DATE":         {"pattern": _DATE_RE, "allow_empty": True},
    "REPORT_TIME":         {"pattern": r"^\d{2}:\d{2}:\d{2}$", "allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)


def _row_from_tokens(tokens: list[str]) -> dict:
    return {
        "FUNCTIONAL_LOCATION": tokens[0],
        "PART_NUMBER": tokens[1],
        "EQUIPMENT_TEXT": " ".join(tokens[2:-5]),
        "SERIAL_NUMBER": tokens[-5],
        "INTERVAL": tokens[-4],
        "UNIT": tokens[-3],
        "REM_LIFE": tokens[-2],
        "END_DATE": tokens[-1],
    }


def _is_data_row(tokens: list[str]) -> bool:
    if len(tokens) < 7:
        return False
    return bool(
        _END_DATE_RE.match(tokens[-1])
        and _REM_LIFE_RE.match(tokens[-2])
        and _UNIT_RE.match(tokens[-3])
        and _INTERVAL_RE.match(tokens[-4])
    )


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    meta = {
        "AC_REG": "", "AC_FH": "", "AC_FC": "",
        "REPORT_DATE": "", "REPORT_TIME": "",
    }

    with pdfplumber.open(pdf_path) as pdf:
        if pdf.pages:
            head_text = pdf.pages[0].extract_text() or ""
            m = _TITLE_RE.search(head_text)
            if m:
                meta["AC_REG"], meta["AC_FH"], meta["AC_FC"] = m.groups()
            m2 = _DATE_TIME_RE.search(head_text)
            if m2:
                meta["REPORT_DATE"], meta["REPORT_TIME"] = m2.groups()

        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            for line in text.split("\n"):
                if _HEADER_ROW_RE.match(line):
                    continue
                tokens = line.split()
                if not _is_data_row(tokens):
                    # Not a recognisable data row (title line, date/time
                    # line, "(C OF A)" line, a page's "Prepared by:"
                    # signature footer, or other stray page furniture) --
                    # skip rather than force it into a row.
                    continue
                row = _row_from_tokens(tokens)
                row["_page"] = page_num
                row.update(meta)
                records.append(row)

    return records
