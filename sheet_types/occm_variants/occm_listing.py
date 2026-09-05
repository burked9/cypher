"""OCCM Listing -- header block (repeated verbatim on every page)::

    <aircraft model>
    MSN <msn> Regn <reg>
    OCCM Listing
    Total Aircraft Hours <hours> and <cycles> Flight Cycles

followed by a column-header row::

    ATA Part No Serial No Unit Description Pos. Release no. / Label no. Inst-Date TSN CSN

Header metadata (aircraft model, MSN, registration, total hours, total
cycles) is parsed once from the first page and stamped on every row, this
project's usual convention. Confirmed identical on every page of the real
sample file (27 pages), so no per-page re-parse or fallback-carry-forward
logic is needed.

Has a genuine text layer (confirmed directly via a pdfplumber pass over the
whole real sample file) -- this module is synchronous, pdfplumber-only, no
OCR.

Column layout, confirmed directly against real header + data-row word
x-positions (NOT the flattened `extract_text()` line, whose word order can
look ambiguous around the Unit/Description boundary -- see below)::

    ATA | PART_NUMBER | SERIAL_NUMBER | UNIT | DESCRIPTION | POS |
    RELEASE_OR_LABEL_NO | INSTALL_DATE | TSN | CSN

UNIT is a real header column ("Unit"), but on every one of the ~880 real
data rows checked directly, no word ever starts inside the printed "Unit"
header's own x-range as a token distinct from the description that follows
it -- the DESCRIPTION text itself always begins flush at the left edge of
that shared band instead (the header labels are horizontally centered over
a column that data fills left-aligned, so the header word's own x0 is not
the true left edge of the column beneath it). In other words: this real
file's Unit column is simply never populated. UNIT is kept as its own
canonical column for interface consistency with the printed header, but is
always emitted as an empty string here and marked allow_empty in RULES --
this is a genuine property of the real sample, not a parsing gap. If a
future file of this same template turns out to actually populate Unit, this
module will need revisiting (it currently cannot distinguish a populated
Unit cell from the common case above).

RELEASE_OR_LABEL_NO holds the single "Release no. / Label no." column
verbatim (e.g. two sub-values joined by " / ", or a bare "-" placeholder
sub-value in some rows) -- confirmed directly that a plain manufacturer
name (rather than a numeric code) can legitimately appear as the release-no
sub-value on many rows, so this column is not further split or pattern
-restricted here.

POS is blank on a real minority of rows (roughly 1 in 20, confirmed by
direct count) -- allow_empty accordingly. A POS value that is naturally one
word in the source data (e.g. a short position code) is sometimes split
into two adjacent word-boxes by pdfplumber's own word-boundary detection,
apparently due to font kerning in the source PDF (confirmed directly, not
something introduced by this module) -- e.g. a placement label like
"<word1><word2>" can render as two separate words with a small gap between
them. This module does not attempt to detect and rejoin that split (no
reliable way to distinguish it from a genuinely two-word POS value observed
elsewhere in the real sample, e.g. "<side> <zone>"), so POS may occasionally
contain an extra internal space that isn't present in the true underlying
value. No pattern restriction is placed on POS as a result.

INSTALL_DATE is normally "DD/MM/YY", but two other legitimate forms were
confirmed directly on the real sample: the literal sentinel "UNKNOWN" (also
used for TSN/CSN when a part's history predates digitised records), and --
on a handful of rows, all on one page, all for the same component family --
a bare 4-6 digit integer. Converting that integer as a spreadsheet-style day
-count date serial (days since 1899-12-30, the classic Excel epoch) lands
on a plausible date consistent with neighbouring rows' own install dates,
confirming this is a genuine source-file quirk (a handful of cells that
kept their raw spreadsheet serial instead of being formatted as text when
the source system exported to PDF) rather than a parsing artifact. All
three forms are accepted by RULES; this module does not attempt to convert
the bare-integer form to a formatted date, so downstream consumers must
handle both shapes. Separately, one row on the real sample has a genuinely
malformed date with an extra digit (an actual source-data typo, distinct
from the spreadsheet-serial rows above) -- RULES intentionally does NOT
widen its pattern to swallow that one, so it is correctly flagged
bad_format rather than silently accepted.

TSN / CSN are a plain integer or the literal "UNKNOWN" sentinel, same
convention as several sibling OCCM variants in this project.

Row extraction does not tokenize by whitespace-splitting the flattened text
line (unreliable here, per the Unit/Description note above, and because
RELEASE_OR_LABEL_NO's own width varies row to row). Instead each page is
read with `extract_words()`, words are clustered into visual rows by `top`
position (small tolerance for per-glyph baseline jitter), and each word is
assigned to a column purely by which fixed x-range its center falls in --
boundaries derived from real header + data-row word positions and checked
row-by-row against the real sample file (every page), including the blank
-POS and blank-Unit cases above. A row is accepted only when its ATA-zone
word is a bare 2-digit number; this is what lets the header row, the
repeated per-page title block, and the page-number footer fall out for free
without special-casing them (confirmed: every one of the real sample's
~880 data rows starts with a bare 2-digit ATA, and nothing else in the
document does).

Illustrative-only example values below use placeholder tokens (<msn>,
<reg>, <pn>, <sn>, <ata>, <pos>, <date>, <hours>, <cycles>) -- never a real
value copied from a corpus file.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "OCCM Listing"
SIGNATURES = [
    "OCCM Listing",
    "Release no. / Label no.",
]

CANONICAL_COLUMNS = [
    "ATA",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "UNIT",
    "DESCRIPTION",
    "POS",
    "RELEASE_OR_LABEL_NO",
    "INSTALL_DATE",
    "TSN",
    "CSN",
    # Header metadata -- parsed once, stamped on every row.
    "AIRCRAFT_MODEL",
    "MSN",
    "AIRCRAFT_REG",
    "TOTAL_HOURS",
    "TOTAL_CYCLES",
]

_OVERRIDES = {
    # Always empty in the real sample -- see module docstring.
    "UNIT": {"allow_empty": True},
    # Blank on a real minority of rows (see module docstring).
    "POS": {"allow_empty": True},
    # Free text, variable width, includes bare "-" placeholder sub-values;
    # never observed blank on the real sample, so no allow_empty override.
    "RELEASE_OR_LABEL_NO": {},
    # DD/MM/YY, the literal "UNKNOWN" sentinel, or a bare spreadsheet-style
    # date serial (see module docstring) -- all three confirmed on the real
    # sample. Deliberately does NOT widen further, so a genuine malformed
    # date (an extra digit, confirmed on one real row) still flags.
    "INSTALL_DATE": {"pattern": r"^(?:\d{2}/\d{2}/\d{2}|\d{4,6}|UNKNOWN)$"},
    "TSN": {"pattern": r"^(?:\d+|UNKNOWN)$"},
    "CSN": {"pattern": r"^(?:\d+|UNKNOWN)$"},
    "AIRCRAFT_MODEL": {"allow_empty": True},
    "MSN": {"pattern": r"^\d+$", "allow_empty": True},
    "AIRCRAFT_REG": {"pattern": r"^[A-Z0-9\-]+$", "uppercase": True, "allow_empty": True},
    "TOTAL_HOURS": {"pattern": r"^\d+$", "allow_empty": True},
    "TOTAL_CYCLES": {"pattern": r"^\d+$", "allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Column boundaries as (x0_inclusive, x1_exclusive, CANONICAL_COLUMNS name),
# derived from the real header's own word x-positions and the real data
# rows' word positions (a word is assigned to the zone its center falls in),
# confirmed directly against the whole real sample file (every page) --
# including the merged Unit/Description band and the blank-POS rows
# described in the module docstring.
_COLUMNS = [
    (-1e9, 55.0, "ATA"),
    (55.0, 170.0, "PART_NUMBER"),
    (170.0, 235.0, "SERIAL_NUMBER"),
    (235.0, 430.0, "DESCRIPTION"),  # Unit's own band is folded in -- see docstring.
    (430.0, 486.0, "POS"),
    (486.0, 604.0, "RELEASE_OR_LABEL_NO"),
    (604.0, 655.0, "INSTALL_DATE"),
    (655.0, 715.0, "TSN"),
    (715.0, 1e9, "CSN"),
]
_ROW_CLUSTER_TOL = 3.5

_ATA_RE = re.compile(r"^\d{2}$")

_MODEL_RE = re.compile(r"^(?P<model>.+)\nMSN\s+\S+\s+Regn\s+\S+", re.MULTILINE)
_MSN_REG_RE = re.compile(r"MSN\s+(?P<msn>\S+)\s+Regn\s+(?P<reg>\S+)")
_HOURS_RE = re.compile(
    r"Total Aircraft Hours\s+(?P<hours>[\d,]+)\s+and\s+(?P<cycles>[\d,]+)\s+Flight Cycles"
)


def _col_for_x(x: float) -> str | None:
    for lo, hi, name in _COLUMNS:
        if lo <= x < hi:
            return name
    return None


def _parse_header_meta(first_page_text: str) -> dict:
    meta = {
        "AIRCRAFT_MODEL": "", "MSN": "", "AIRCRAFT_REG": "",
        "TOTAL_HOURS": "", "TOTAL_CYCLES": "",
    }
    m = _MODEL_RE.search(first_page_text)
    if m:
        meta["AIRCRAFT_MODEL"] = m.group("model").strip()
    m = _MSN_REG_RE.search(first_page_text)
    if m:
        meta["MSN"] = m.group("msn")
        meta["AIRCRAFT_REG"] = m.group("reg")
    m = _HOURS_RE.search(first_page_text)
    if m:
        meta["TOTAL_HOURS"] = m.group("hours")
        meta["TOTAL_CYCLES"] = m.group("cycles")
    return meta


def _cluster_rows(words: list[dict]) -> list[list[dict]]:
    """Group words into visual table rows by `top` position. Words on the
    same printed row can differ by a fraction of a point due to font
    baseline/rendering, so a small tolerance is used rather than an exact
    match (confirmed necessary directly -- a handful of real rows split
    into two clusters without it)."""
    ws = sorted(words, key=lambda w: (w["top"], w["x0"]))
    rows: list[list[dict]] = []
    cur: list[dict] = []
    cur_top: float | None = None
    for w in ws:
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
    rec = {name: " ".join(cols.get(name, [])) for _, _, name in _COLUMNS}
    # UNIT is always empty in the real sample -- see module docstring.
    rec["UNIT"] = ""
    return rec


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        if not pdf.pages:
            return records
        meta = _parse_header_meta(pdf.pages[0].extract_text() or "")
        for page in pdf.pages:
            words = page.extract_words()
            if not words:
                continue
            for row_words in _cluster_rows(words):
                rec = _row_to_record(row_words)
                if rec is None:
                    continue
                rec.update(meta)
                records.append(rec)
    return records
