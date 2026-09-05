"""OCCM PART STATUS report -- `MSN <msn> OCCM PART STATUS` header, real
(native) text layer, no OCR needed. Confirmed via a direct pdfplumber pass
across every page of one real sample file (an A340-family widebody, several
hundred rows across ~28 pages).

Header block (repeats verbatim at the top of every page)::

    A/C MSN: <msn>
    <reg>
    TOTAL A/C FH: <fh>
    MSN <msn> OCCM PART STATUS TOTAL A/C FC: <fc>
    DATE: <date DD-Mon-YY>

<reg> sits on its own line directly below the "A/C MSN:" line -- confirmed
directly on the real sample file -- and is captured positionally (the line
immediately after the MSN line) rather than via a fixed-format regex, since
the only reliable anchor for it is that position.

Column header (also repeats per page). A pdfplumber text dump renders it as
three separate lines because the underlying PDF wraps several two-line
column labels onto a shared physical line:

    INSTALLED INSTALLED TSN ACTUAL
    ATA PN SN PN DESCRIPTION CSN ACTUAL CYCLES
    POSITION DATE HOURS

Reconstructed by column x-position (confirmed via `extract_words()` on the
real file, not just the flattened `extract_text()` dump the initial rough
pass used, which is why that pass only surfaced one of these three lines),
the real 8 columns are::

    ATA | PN | SN | (PN) DESCRIPTION | INSTALLED POSITION |
    INSTALLED DATE | TSN ACTUAL HOURS | CSN ACTUAL CYCLES

i.e. ATA, the installed PN/SN, a free-text description (whose header
happens to read "PN DESCRIPTION" -- the description text associated with
the installed PN, not a second PN column), the installed position, the
installation date, and the current TSN (hours)/CSN (cycles) totals as of
the report's TOTAL A/C FH/FC.

Per-row layout, whitespace-tokenized (a typical clean row)::

    <ata> <pn> <sn> <description tokens...> <position> <inst_date> <tsn> <csn>

TSN/CSN are usually plain integers but two non-numeric placeholders show up
on real rows and are treated as valid (not flagged) rather than as parse
failures: `UNK` (component installed too recently/without history for the
report to compute a total) and `#VALUE!` (a spreadsheet-formula error that
was baked into the PDF export upstream, confirmed present on a handful of
real rows -- not something this module can recover a real number from, so
it's preserved verbatim like `UNK` rather than silently dropped).

Row anchor: ATA is a bare 2-digit token at the start of the line, and the
row's last three tokens are (POSITION, INST_DATE, TSN, CSN) shaped --
specifically the last two tokens each match `\\d+`/`UNK`/`#VALUE!` and the
third-from-last matches the `D-Mon-YY` date shape. Confirmed against every
line on every page of the real sample file: exactly the data rows match,
and every header/footer line (the 5-line header block above, the 3-line
column-header block, and the `Page N of M` footer) fails to match.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "OCCM Part Status"
# "OCCM PART STATUS" is a precise anchor unique to this format -- checked
# for collisions against every SIGNATURES list in sheet_types/
# {occm,ht,llp}.py and every existing variant file (none define it).
SIGNATURES = [
    "OCCM PART STATUS",
]

CANONICAL_COLUMNS = [
    "ATA",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
    "POSITION",
    "INST_DATE",
    "TSN",
    "CSN",
    # Header metadata -- parsed once per page, stamped onto every row of
    # that page.
    "MSN",
    "AIRCRAFT_REG",
    "TOTAL_FH",
    "TOTAL_FC",
    "REPORT_DATE",
]

_OVERRIDES = {
    # Seen shapes across the real file: plain digits ("0".."25"), a bare
    # leading dash ("-00"), and short alpha/alnum codes ("L00", "1PU2",
    # "E&E", "CENTER"). No fixed length or digit-only assumption holds.
    "POSITION":    {"pattern": r"^-?[A-Z0-9&]{1,10}$", "uppercase": True},
    "INST_DATE":   {"pattern": r"^\d{1,2}-[A-Za-z]{3}-\d{2}$"},
    # UNK / #VALUE! are real, valid placeholder values on this report (see
    # module docstring) -- not treated as bad_format.
    "TSN":         {"pattern": r"^(?:\d+|UNK|#VALUE!)$"},
    "CSN":         {"pattern": r"^(?:\d+|UNK|#VALUE!)$"},
    "DESCRIPTION": {"uppercase": True, "allow_empty": True},
    "MSN":          {"pattern": r"^\d{1,6}$", "allow_empty": True},
    "AIRCRAFT_REG": {"pattern": r"^[A-Z0-9]{1,3}-?[A-Z0-9]{2,6}$",
                      "uppercase": True, "allow_empty": True},
    "TOTAL_FH":     {"pattern": r"^\d+$", "allow_empty": True},
    "TOTAL_FC":     {"pattern": r"^\d+$", "allow_empty": True},
    "REPORT_DATE":  {"pattern": r"^\d{1,2}-[A-Za-z]{3}-\d{2}$",
                      "allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_ATA_RE = re.compile(r"^\d{2}$")
_DATE_RE = re.compile(r"^\d{1,2}-[A-Za-z]{3}-\d{2}$")
_NUM_RE = re.compile(r"^(?:UNK|#VALUE!|\d+)$")
_REG_RE = re.compile(r"^[A-Z0-9]{1,3}-?[A-Z0-9]{2,6}$")

_MSN_RE = re.compile(r"^A/C MSN:\s*(\S+)$")
_FH_RE = re.compile(r"^TOTAL A/C FH:\s*(\d+)$")
_FC_RE = re.compile(r"^MSN\s+(\S+)\s+OCCM PART STATUS TOTAL A/C FC:\s*(\d+)$")
_REPORT_DATE_RE = re.compile(r"^DATE:\s*(\d{1,2}-[A-Za-z]{3}-\d{2})$")


def _parse_header(lines: list[str]) -> dict:
    """Parse the 5-line header block that repeats at the top of every page.
    Returns whatever subset is found -- callers merge onto defaults so a
    header line that fails to match on some odd page never crashes
    extraction, it just leaves that field blank for that page."""
    meta: dict = {}
    for i, line in enumerate(lines):
        m = _MSN_RE.match(line)
        if m:
            meta["MSN"] = m.group(1)
            # <reg> sits on the line directly below "A/C MSN: <msn>" --
            # confirmed positionally on the real sample file, there is no
            # other reliable anchor for it (see module docstring).
            if i + 1 < len(lines) and _REG_RE.match(lines[i + 1]):
                meta["AIRCRAFT_REG"] = lines[i + 1]
            continue
        m = _FH_RE.match(line)
        if m:
            meta["TOTAL_FH"] = m.group(1)
            continue
        m = _FC_RE.match(line)
        if m:
            meta["TOTAL_FC"] = m.group(2)
            continue
        m = _REPORT_DATE_RE.match(line)
        if m:
            meta["REPORT_DATE"] = m.group(1)
            continue
    return meta


def _parse_data_line(line: str) -> dict | None:
    toks = line.split()
    # Minimum: ATA, PN, SN, >=1 description token, POSITION, INST_DATE,
    # TSN, CSN.
    if len(toks) < 8:
        return None
    if not _ATA_RE.match(toks[0]):
        return None
    if not (_NUM_RE.match(toks[-1]) and _NUM_RE.match(toks[-2])
            and _DATE_RE.match(toks[-3])):
        return None
    return {
        "ATA": toks[0],
        "PART_NUMBER": toks[1],
        "SERIAL_NUMBER": toks[2],
        "DESCRIPTION": " ".join(toks[3:-4]),
        "POSITION": toks[-4],
        "INST_DATE": toks[-3],
        "TSN": toks[-2],
        "CSN": toks[-1],
    }


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if not text.strip():
                continue
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            header_meta = {
                "MSN": "", "AIRCRAFT_REG": "", "TOTAL_FH": "",
                "TOTAL_FC": "", "REPORT_DATE": "",
            }
            header_meta.update(_parse_header(lines))
            for line in lines:
                row = _parse_data_line(line)
                if row is None:
                    continue
                rec: dict = {c: "" for c in CANONICAL_COLUMNS}
                rec.update(row)
                rec.update(header_meta)
                rec["_page"] = page_num
                records.append(rec)
    return records
