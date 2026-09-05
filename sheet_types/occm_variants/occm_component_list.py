""""OCCM Component List" -- title reads "ON CONDITION CONDITION MONITORING
STATUS" (the doubled "CONDITION" is a genuine document-title typo/quirk,
not an extraction artefact) followed by "OCCM Component List". Has a real
text layer (confirmed directly via a pdfplumber pass over the whole real
sample file) -- this module is synchronous, pdfplumber-only, no OCR.

Header block (3 lines, first page and repeated verbatim on every page)::

    A/C TYPE: <type>  DATE: <date>
    A/C MSN: <msn>    AIRCRAFT HOURS: <n>
    A/C REG: <reg>    AIRCRAFT CYCLES: <n>

parsed once from the first page and stamped on every row, same convention
this project's other header-plus-body OCCM variants use.

Table layout -- a genuine two-band column-group header, confirmed directly
against word x-positions on the rendered page (NOT just the flattened
`extract_text()` line, which interleaves the two header sub-rows in an
order that doesn't match the data underneath them)::

    INSTALLATION DATA              COMPONENT DATA
    @ A/C   @ A/C   @ Part  @ Part
    NO ATA PART NUMBER DESCRIPTION Serial No POS DATE TSN CSN TSN CSN TSN CSN TSI CSI

A data row, tokens in column order::

    <no> <ata> <pn> <description...> <sn> <pos> <install_date>
    <ac_tsn_at_install> <ac_csn_at_install>
    <part_tsn_at_install> <part_csn_at_install>
    <tsn> <csn> <tsi> <csi>

Confirmed against real rows: the INSTALLATION DATA group's 4 numeric
sub-columns are the aircraft's and the component's own total time/cycles
*at the moment this part was installed* (both read 0 when the part has
been on since new/no prior life); COMPONENT DATA's TSN/CSN are the
aircraft's *current* total hours/cycles (matching the header's AIRCRAFT
HOURS/CYCLES on every row on a single-date report) and its TSI/CSI are the
component's own current time/cycles since that install date. The relation
CSI == (current CSN) - (@ A/C CSN at install) held on every checked row
(and correspondingly for hours), confirming the column identities above
rather than assuming them from header text alone.

Row extraction deliberately does NOT use whitespace/`.split()` tokenizing
(the pattern several sibling OCCM variants use) -- this format has a
confirmed real edge case that breaks that approach: some rows have blank
cells in the *middle* of the numeric run (e.g. the two @ Part @-install
columns and the current TSN/CSN pair genuinely blank/absent on a newly
installed part, while TSI/CSI further right are still populated), which
would silently shift every later positional index if tokens were sliced by
count. Instead each page is read with `extract_words()` (word-level boxes),
words are clustered into visual rows by `top` position, and each word is
assigned to its column purely by which column's x-range its center falls
in -- confirmed against the real header's own word positions and checked
row-by-row against the real sample file, including the sparse-row case
above. A blank cell simply contributes no word to its column and comes out
as "" -- never guessed, never shifted into a neighbour -- which is the same
"never guess a wrong split" principle this project's other variants apply
to ambiguous free text, just enforced geometrically here instead. No
STATUS_TRAIL catch-all column is needed as a result: every column is
resolved with confidence from position, not inferred from token count.

A row is accepted only when its ATA-column word is a bare 2-digit number;
this is what lets header lines, blank-page noise, and the page-number
footer ("<n> of <n>") on every page fall out for free without special-casing
them.

Known limitation, confirmed directly against the real sample file: one
page in the middle of an otherwise text-searchable, multi-page real
document had no extractable text layer at all for its body rows (0 chars
from `extract_text()`, despite the page's own ruled table grid still being
present as vector graphics) -- apparently a one-off text-embedding fault on
that single page, not a scanned/photographed page and not representative of
the file as a whole. Rows on such a page are simply not recovered by this
text-layer parser; an OCR fallback could recover them but is out of scope
here (this variant is documented, per the task that created it, as
text-layer-only).
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "OCCM Component List"
SIGNATURES = [
    "ON CONDITION CONDITION MONITORING STATUS",
    "OCCM Component List",
]

CANONICAL_COLUMNS = [
    "ATA",
    "PART_NUMBER",
    "DESCRIPTION",
    "SERIAL_NUMBER",
    "POSITION",
    "INSTALL_DATE",
    "AC_TSN_AT_INSTALL",
    "AC_CSN_AT_INSTALL",
    "PART_TSN_AT_INSTALL",
    "PART_CSN_AT_INSTALL",
    "TSN",
    "CSN",
    "TSI",
    "CSI",
    # Header metadata, parsed once per file and stamped on every row.
    "AIRCRAFT_TYPE",
    "REPORT_DATE",
    "AIRCRAFT_MSN",
    "AIRCRAFT_HOURS",
    "AIRCRAFT_REG",
    "AIRCRAFT_CYCLES",
]

# Time/cycle cells are plain integers, but a genuine sentinel "UNK" (seen on
# real rows for a just-installed part whose prior life is unknown/not
# tracked) and outright blank (see module docstring) are both legitimate
# values, not parse failures.
# A handful of real rows print INSTALL_DATE as "D-Mon-YYYY" (4-digit year,
# dash separator) instead of the format's usual "DD/Mon/YY" -- confirmed
# directly on the real sample file, a genuine formatting variance in the
# source data rather than a parse error, so both separators and either a
# 2- or 4-digit year are accepted.
_NUM_RULE = {"pattern": r"^(?:\d+|UNK)$", "allow_empty": True}
_DATE_RULE = {"pattern": r"^\d{1,2}[/-][A-Za-z]{3}[/-]\d{2,4}$", "allow_empty": True}

_OVERRIDES = {
    "DESCRIPTION": {"uppercase": True},
    # SNs on this format occasionally carry an embedded space (confirmed on
    # real rows, e.g. a manufacturer batch-code prefix separated from a
    # numeric suffix) -- the global default SN pattern forbids spaces, so
    # loosen it here rather than let every such row get flagged.
    "SERIAL_NUMBER": {
        "pattern": r"^[A-Z0-9](?:[A-Z0-9\-/ ]*[A-Z0-9])?$",
        "uppercase": True,
    },
    # POSITION is usually a real position code, but this format also prints
    # a literal "-" placeholder for structural/non-discrete parts (e.g.
    # airframe doors) -- allow both rather than flagging the placeholder.
    # A couple of real rows also carry a trailing space-separated
    # sub-letter (confirmed directly, e.g. a bay/zone code plus a lone
    # side-letter suffix) -- allowed too rather than flagged as bad_format.
    "POSITION": {
        "pattern": r"^(?:-|[A-Z0-9][A-Z0-9./\- ]{0,13})$",
        "uppercase": True,
        "allow_empty": True,
    },
    "INSTALL_DATE": _DATE_RULE,
    "AC_TSN_AT_INSTALL": _NUM_RULE,
    "AC_CSN_AT_INSTALL": _NUM_RULE,
    "PART_TSN_AT_INSTALL": _NUM_RULE,
    "PART_CSN_AT_INSTALL": _NUM_RULE,
    "TSN": _NUM_RULE,
    "CSN": _NUM_RULE,
    "TSI": _NUM_RULE,
    "CSI": _NUM_RULE,
    "AIRCRAFT_TYPE": {"allow_empty": True},
    "REPORT_DATE": {"allow_empty": True},
    "AIRCRAFT_MSN": {"allow_empty": True},
    "AIRCRAFT_HOURS": {"pattern": r"^\d+$", "allow_empty": True},
    "AIRCRAFT_REG": {"uppercase": True, "allow_empty": True},
    "AIRCRAFT_CYCLES": {"pattern": r"^\d+$", "allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Column boundaries as (x0_inclusive, x1_exclusive, CANONICAL_COLUMNS name),
# derived from the real header's own word x-positions (midpoints between
# adjacent column centers) and confirmed row-by-row against the real sample
# file, including the sparse/blank-cell rows described in the module
# docstring. "NO" (the report's own row counter) is parsed only to anchor
# nothing -- ATA is the real anchor -- and is not carried into the output.
_COLUMNS = [
    (-1e9, 52.4, "NO"),
    (52.4, 85.25, "ATA"),
    (85.25, 169.0, "PART_NUMBER"),
    (169.0, 290.35, "DESCRIPTION"),
    (290.35, 388.3, "SERIAL_NUMBER"),
    (388.3, 461.3, "POSITION"),
    (461.3, 517.3, "INSTALL_DATE"),
    (517.3, 552.0, "AC_TSN_AT_INSTALL"),
    (552.0, 580.8, "AC_CSN_AT_INSTALL"),
    (580.8, 610.8, "PART_TSN_AT_INSTALL"),
    (610.8, 640.6, "PART_CSN_AT_INSTALL"),
    (640.6, 670.2, "TSN"),
    (670.2, 702.5, "CSN"),
    (702.5, 737.1, "TSI"),
    (737.1, 1e9, "CSI"),
]
# Header/body split: the real header block (title + A/C metadata + the
# two-band column-group header) ends well above this -- confirmed directly
# against the real sample file's header word positions -- so restricting to
# words below it also incidentally drops the header's own repeated text on
# every page for free.
_BODY_TOP_MIN = 186.0
_ROW_CLUSTER_TOL = 3.5

_ATA_RE = re.compile(r"^\d{2}$")

_TYPE_RE = re.compile(r"A/C\s+TYPE:\s*(\S+)")
_DATE_RE = re.compile(r"\bDATE:\s*(\S+)")
_MSN_RE = re.compile(r"A/C\s+MSN:\s*(\S+)")
_HOURS_RE = re.compile(r"AIRCRAFT\s+HOURS:\s*(\S+)")
_REG_RE = re.compile(r"A/C\s+REG:\s*(\S+)")
_CYCLES_RE = re.compile(r"AIRCRAFT\s+CYCLES:\s*(\S+)")


def _col_for_x(x: float) -> str | None:
    for lo, hi, name in _COLUMNS:
        if lo <= x < hi:
            return name
    return None


def _parse_header_meta(first_page_text: str) -> dict:
    meta = {
        "AIRCRAFT_TYPE": "", "REPORT_DATE": "", "AIRCRAFT_MSN": "",
        "AIRCRAFT_HOURS": "", "AIRCRAFT_REG": "", "AIRCRAFT_CYCLES": "",
    }
    m = _TYPE_RE.search(first_page_text)
    if m:
        meta["AIRCRAFT_TYPE"] = m.group(1)
    m = _DATE_RE.search(first_page_text)
    if m:
        meta["REPORT_DATE"] = m.group(1)
    m = _MSN_RE.search(first_page_text)
    if m:
        meta["AIRCRAFT_MSN"] = m.group(1)
    m = _HOURS_RE.search(first_page_text)
    if m:
        meta["AIRCRAFT_HOURS"] = m.group(1)
    m = _REG_RE.search(first_page_text)
    if m:
        meta["AIRCRAFT_REG"] = m.group(1)
    m = _CYCLES_RE.search(first_page_text)
    if m:
        meta["AIRCRAFT_CYCLES"] = m.group(1)
    return meta


def _cluster_rows(words: list[dict]) -> list[list[dict]]:
    """Group words into visual table rows by `top` position. Words on the
    same printed row can differ by a fraction of a point due to font
    baseline/rendering, so a small tolerance is used rather than an exact
    match."""
    body = [w for w in words if w["top"] > _BODY_TOP_MIN]
    body.sort(key=lambda w: (w["top"], w["x0"]))
    rows: list[list[dict]] = []
    cur: list[dict] = []
    cur_top: float | None = None
    for w in body:
        if cur_top is None or abs(w["top"] - cur_top) <= _ROW_CLUSTER_TOL:
            cur.append(w)
            if cur_top is None:
                cur_top = w["top"]
        else:
            rows.append(cur)
            cur = [w]
            cur_top = w["top"]
    if cur:
        rows.append(cur)
    return rows


def _row_to_record(row_words: list[dict]) -> dict | None:
    cols: dict[str, list[str]] = {}
    for w in row_words:
        cx = (w["x0"] + w["x1"]) / 2
        name = _col_for_x(cx)
        if name is None:
            continue
        cols.setdefault(name, []).append(w["text"])
    ata_toks = cols.get("ATA")
    if not ata_toks or not _ATA_RE.match(ata_toks[0]):
        return None
    rec = {name: " ".join(cols.get(name, [])) for _, _, name in _COLUMNS if name != "NO"}
    return rec


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        if not pdf.pages:
            return records
        meta = _parse_header_meta(pdf.pages[0].extract_text() or "")
        for page_num, page in enumerate(pdf.pages, start=1):
            words = page.extract_words()
            if not words:
                continue
            for row_words in _cluster_rows(words):
                rec = _row_to_record(row_words)
                if rec is None:
                    continue
                rec.update(meta)
                rec["_page"] = page_num
                records.append(rec)
    return records
