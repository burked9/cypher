"""OCCM COMPONENTS STATUS report -- a per-component status list headed by::

    <code> OCCM COMPONENTS STATUS Type Reg: MSN <date>
    <facility code> Airbus <type prefix> -
    <type suffix> <reg> <msn> TTSN <hours>
    TCSN <cycles>
    Installation Installation
    ATA Description P/N S/N Position Date TTSN TCSN TSI CSI Document

followed by one row per component. Confirmed on a single real file so far
(singleton cluster) -- born-digital, full text layer, coordinate-bucketed
columns (no OCR needed; extract() is synchronous). The text layer is real
but carries systematic character-substitution noise consistent with an OCR
pass somewhere upstream of this particular PDF's own creation -- the same
"real but noisy text layer" pattern already documented elsewhere in this
project (see e.g. llp_variants/engine_items_control_llp_status.py). Examples
of the noise seen directly in the sample (never "corrected", just described
here so the pattern is recognisable): "lnstallation" for "Installation",
"Unknourn"/"Unknovun" for "Unknown", a digit run with a stray internal
space (e.g. a part number rendered like "<prefix>- <n> <suffix>" where the
clean value is presumably a single unbroken string), a position code with
a letter substituted for a digit (e.g. a leading "1" misread as a similar
glyph), and an ATA chapter digit occasionally misread as a punctuation
character.

Two page layouts (confirmed by direct pdfplumber word-position inspection):
the FIRST and LAST page of the sample each carry a letterhead graphic that
shifts every column ~27pt right of where the same columns sit on every
other (plain) page. Column x-positions are therefore never hard-coded as a
single global table -- see "Column geometry" below.

Row grain: one row per component. Columns, left to right: ATA, DESCRIPTION
(may wrap onto one or more lines ABOVE the row's own line -- confirmed
directly: a component with a long name renders its description across up
to 3 physical lines, with ATA/PN/SN/... only appearing on the LAST of
those lines), PART_NUMBER, SERIAL_NUMBER, POSITION, INSTALL_DATE, then four
per-component life fields (TTSN/TCSN/TSI/CSI -- "installation" hours/
cycles context per the (corrupted) "Installation Installation" sub-header
over the Date column), and finally an optional DOCUMENT reference.

Column geometry -- why proportional interpolation, not fixed x anchors:
The two page layouts described above use DIFFERENT absolute x-coordinates
for every column (confirmed directly: e.g. the ATA column sits at x0=~83
on the letterhead layout and x0=~56 on the plain layout -- a ~27pt shift
that is NOT constant across columns further right, ruling out a single
per-page offset correction). For the ATA-through-INSTALL_DATE span,
column boundaries are instead computed PER ROW as a fraction of the
distance between that row's own ATA token and its own INSTALL_DATE token
(both reliably identifiable per row -- ATA is always the row's leftmost
token, INSTALL_DATE is found via a dedicated date regex). These fractions
were measured once on the letterhead layout's real data and confirmed to
predict the plain layout's real column positions to within ~1pt without
any per-layout tuning -- i.e. the column proportions are a property of the
underlying document template, not of either individual page layout.

The TTSN/TCSN/TSI/CSI/DOCUMENT span (right of INSTALL_DATE) does NOT
follow the same proportional relationship (confirmed directly: interpolating
the same way for this span mispredicts real column positions by ~20pt on
the plain layout), so this span instead uses a small per-layout absolute
x-boundary table, selected per row from which layout's INSTALL_DATE anchor
that row's own date token is closer to (the two layouts' date-column x0
differ by ~15pt, an unambiguous discriminator).

A further confirmed rendering quirk in this span: narrow single/double
digit values in the TSI/CSI columns render right-aligned (further right
than the column's own left-aligned wide values, e.g. a lone "1" or "0"),
landing close to -- but empirically always slightly LEFT of -- where a
genuine DOCUMENT-column token starts. This was measured directly across
several real rows on both layouts (a consistent ~4-8pt gap between the
rightmost plausible CSI position and the leftmost plausible DOCUMENT
position), and the per-layout boundary is set in that gap.

DESCRIPTION continuation and DOCUMENT wrapping -- an intentionally
conservative, evidence-based rule (not a guess):
Both DESCRIPTION (when it wraps to extra lines above the row) and DOCUMENT
(a certificate/release reference like "<code> <year>-<n>", which wraps its
own prefix onto the line ABOVE the row when present) are rendered as
"orphan" text lines with no ATA token of their own, sitting between two
real data rows. Directly comparing several such orphan lines against their
neighbouring rows (including one real case where an orphan line carries
BOTH a description word AND a document-prefix fragment side by side, e.g.
a hyphenated description continuation immediately followed by a "<code>
<year>-" style fragment on the same physical line) confirmed that these
orphan fragments always belong to the FOLLOWING data row, never the
preceding one -- consistent with a table renderer emitting a row's
overflow content just above the row itself. Each orphan line is therefore
split by x-position into a description-zone part (prepended to the
following row's DESCRIPTION, but only tokens containing a letter --
digit-only fragments in that zone are not real description text) and a
document-zone part (prepended to the following row's DOCUMENT).

A rarer, genuinely ambiguous shape: an orphan line consisting of a single
short digit-only token sitting almost exactly on the CSI/DOCUMENT boundary
(neither clearly a stray CSI value nor clearly a document-prefix digit,
and not merged into either neighbouring row's own line by the row
clustering below). Per this project's "never guess a wrong split"
convention, this is NOT forced into either CSI or DOCUMENT -- it is
appended, verbatim, to the FOLLOWING row's STATUS_TRAIL instead (the same
"following row" direction as every other confirmed orphan-fragment case
above, for consistency, though confidence here is lower than for the
description/document split, which is why it is kept out of the named
columns entirely).

PART_NUMBER / SERIAL_NUMBER: several real rows show a stray internal space
inside what looks like it should be one unbroken value. No digit-level or
space-level "correction" is attempted anywhere in this module, per this
project's "never guess a wrong split, wrong data is worse than missing
data" convention (see e.g. llp_variants/engine_items_control_llp_status.py)
-- the raw extracted text (tokens found in that column's x-range, joined
with a single space, exactly as pdfplumber returns them) is kept as-is.
The shared global PART_NUMBER/SERIAL_NUMBER rules already flag embedded
spaces (`no_spaces` -> bad_format), so this corruption surfaces honestly
downstream rather than being silently "fixed" into a possibly-wrong value.

Row validity: a real data row is identified by the presence of an
INSTALL_DATE-shaped token within its row cluster -- this was confirmed to
be a more reliable anchor than the ATA token itself, since the date token
is never glued to neighbouring text without at least a recognisable date
prefix, whereas ATA is occasionally rendered as a single punctuation-like
glyph with no digit at all. A rare confirmed sub-case: the INSTALL_DATE
token itself is sometimes glued directly onto the following TTSN value
with no space at all (e.g. a clean date immediately followed by a status
word with no gap) -- handled by splitting any token that starts with a
recognisable date shape into the date part and a remainder, before column
bucketing runs.

Header metadata (AIRCRAFT_TYPE, AIRCRAFT_REG, MSN, REPORT_TTSN, REPORT_TCSN,
REPORT_DATE) is parsed once from the header block (which repeats, with
varying amounts of the same character-substitution noise, on every page)
and stamped onto every row. REPORT_TTSN/REPORT_TCSN are the aircraft's own
total time/cycles as of the report date (distinct from each row's own
per-component TTSN/TCSN, which describe that component's life since its
own installation).
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "OCCM Components Status"
SIGNATURES = [
    "ATA Description P/N S/N Position Date TTSN TCSN TSI CSI Document",
]

CANONICAL_COLUMNS = [
    "ATA",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "POSITION",
    "INSTALL_DATE",
    "TTSN",
    "TCSN",
    "TSI",
    "CSI",
    "DOCUMENT",
    # Raw, unparsed fragments that couldn't be confidently attributed to a
    # named column -- see module docstring ("DESCRIPTION continuation and
    # DOCUMENT wrapping").
    "STATUS_TRAIL",
    # Header metadata -- parsed once, stamped onto every row.
    "AIRCRAFT_TYPE",
    "AIRCRAFT_REG",
    "MSN",
    "REPORT_TTSN",
    "REPORT_TCSN",
    "REPORT_DATE",
]

_TIME_RULE = {"pattern": r"^(?:\d+(?::\d{1,2})?|Unknow\w*)$", "allow_empty": True}
_OVERRIDES = {
    "POSITION": {
        "pattern": r"^[A-Za-z0-9]{1,10}$",
        "allow_empty": True,
    },
    "INSTALL_DATE": {
        "pattern": r"^\d{2}-[A-Za-z0-9]{3}-[A-Za-z0-9]{4}$",
        "allow_empty": True,
    },
    "TTSN": _TIME_RULE,
    "TCSN": _TIME_RULE,
    "TSI": _TIME_RULE,
    "CSI": _TIME_RULE,
    "DOCUMENT": {"allow_empty": True},
    "STATUS_TRAIL": {"allow_empty": True},
    "AIRCRAFT_TYPE": {"allow_empty": True},
    "AIRCRAFT_REG": {"allow_empty": True},
    "MSN": {"pattern": r"^\d{3,6}$", "allow_empty": True},
    "REPORT_TTSN": {"allow_empty": True},
    "REPORT_TCSN": {"allow_empty": True},
    "REPORT_DATE": {
        "pattern": r"^\d{2}-[A-Za-z0-9]{3}-\d{4}$",
        "allow_empty": True,
    },
}
RULES = merged_rules(_OVERRIDES)

# --- Row / date detection --------------------------------------------------
# Day is confirmed clean (always 2 digits) in every real date token seen;
# month and year each show occasional single-character OCR-style noise
# (e.g. a letter substituted for a digit) but are always exactly 3 and 4
# characters long respectively -- so length, not strict digit/alpha typing,
# is the reliable anchor.
_DATE_RE = re.compile(r"(\d{2}-[A-Za-z0-9]{3}-[A-Za-z0-9]{4})(.*)$")

# --- ATA -> INSTALL_DATE span: proportional column fractions ---------------
# Measured once from real data-row word x-positions on the letterhead page
# layout, confirmed to predict the plain layout's real column positions to
# within ~1pt (see module docstring "Column geometry").
_FRACTIONS = {
    "DESCRIPTION": 0.0519,
    "PART_NUMBER": 0.2350,
    "SERIAL_NUMBER": 0.4344,
    "POSITION": 0.8197,
}
_FRAC_BOUNDARIES = [
    ("DESCRIPTION", 0.1435),
    ("PART_NUMBER", 0.3347),
    ("SERIAL_NUMBER", 0.6271),
]


def _bucket_by_fraction(frac: float) -> str:
    for name, upper in _FRAC_BOUNDARIES:
        if frac < upper:
            return name
    return "POSITION"


# --- INSTALL_DATE -> end-of-line span: per-layout absolute x boundaries ----
# Measured directly from real row word x-positions on each of the two
# confirmed page layouts (see module docstring). The CSI/DOCUMENT boundary
# sits in the confirmed small gap between a right-aligned narrow CSI value
# and the leftmost real DOCUMENT token on that layout.
_LAYOUTS = {
    # Each (name, upper) pair is that column's own UPPER x-boundary (i.e.
    # a token qualifies for that column when its x0 is less than this
    # value, having already failed every earlier column's boundary).
    # DOCUMENT is the implicit catch-all for anything at/after the last
    # (CSI) boundary.
    "letterhead": {
        "date_x": 449.0,
        "bounds": [
            ("TTSN", 528.5),
            ("TCSN", 598.0),
            ("TSI", 673.5),
            ("CSI", 731.0),
        ],
        "doc_boundary": 731.0,
    },
    "plain": {
        "date_x": 434.4,
        "bounds": [
            ("TTSN", 544.1),
            ("TCSN", 604.55),
            ("TSI", 665.0),
            ("CSI", 723.15),
        ],
        "doc_boundary": 723.15,
    },
}
_LAYOUT_MIDPOINT = (_LAYOUTS["letterhead"]["date_x"] + _LAYOUTS["plain"]["date_x"]) / 2


def _layout_for(date_x: float) -> dict:
    return _LAYOUTS["letterhead"] if date_x >= _LAYOUT_MIDPOINT else _LAYOUTS["plain"]


def _bucket_trailing(x0: float, layout: dict) -> str:
    for name, upper in layout["bounds"]:
        if x0 < upper:
            return name
    return "DOCUMENT"


# --- Header metadata --------------------------------------------------------
_TITLE_DATE_RE = re.compile(r"(\d{2}-[A-Za-z]{3}-\d{4})")
_AIRBUS_LINE_RE = re.compile(r"Airbus\s+(\S+)\s*-")
_TTSN_LABEL_RE = re.compile(r"TTSN\s+(\S+)")
_TCSN_LABEL_RE = re.compile(r"TCSN\s+(\S+)")


def _parse_header(lines: list[str]) -> dict:
    """Parse the repeating header block from a page's first ~6 text lines.
    Returns only the keys it successfully found -- callers merge onto a
    running "last known good" dict so an occasional corrupted page doesn't
    blank out metadata already established from an earlier page."""
    meta: dict = {}
    airbus_idx = None
    for i, line in enumerate(lines):
        if not meta.get("REPORT_DATE"):
            m = _TITLE_DATE_RE.search(line)
            if m and ("OCCM" in line.upper() or "STATUS" in line.upper() or "Date" in line):
                meta["REPORT_DATE"] = m.group(1)
        m = _AIRBUS_LINE_RE.search(line)
        if m:
            meta["_type_prefix"] = m.group(1)
            airbus_idx = i
    if airbus_idx is not None and airbus_idx + 1 < len(lines):
        reg_line = lines[airbus_idx + 1]
        toks = reg_line.split()
        if len(toks) >= 3 and "_type_prefix" in meta:
            meta["AIRCRAFT_TYPE"] = f"{meta.pop('_type_prefix')}-{toks[0]}"
            meta["AIRCRAFT_REG"] = toks[1]
            meta["MSN"] = toks[2]
        m = _TTSN_LABEL_RE.search(reg_line)
        if m:
            meta["REPORT_TTSN"] = m.group(1)
        if airbus_idx + 2 < len(lines):
            m = _TCSN_LABEL_RE.search(lines[airbus_idx + 2])
            if m:
                meta["REPORT_TCSN"] = m.group(1)
    meta.pop("_type_prefix", None)
    return meta


_HEADER_META_KEYS = (
    "AIRCRAFT_TYPE", "AIRCRAFT_REG", "MSN",
    "REPORT_TTSN", "REPORT_TCSN", "REPORT_DATE",
)

# --- Row clustering ----------------------------------------------------------
_TOP_TOLERANCE = 2.0


def _cluster_rows(words: list[dict]) -> list[list[dict]]:
    """Group words into visual line-clusters by their `top` coordinate,
    chain-merging consecutive tops within `_TOP_TOLERANCE`. Deliberately
    strict (2pt) so that a genuinely separate physical line -- a
    description-continuation line, or a wrapped document-prefix fragment
    a few points above/below a data row -- is NOT bridged into that row's
    own cluster and does not, in turn, bridge two adjacent real rows
    together (confirmed real row-to-row baseline spacing is ~20pt, far
    above any continuation-line gap seen, so this never merges two
    genuine rows)."""
    if not words:
        return []
    tops = sorted(set(round(w["top"], 1) for w in words))
    clusters: list[list[float]] = []
    cur = [tops[0]]
    for t in tops[1:]:
        if t - cur[-1] <= _TOP_TOLERANCE:
            cur.append(t)
        else:
            clusters.append(cur)
            cur = [t]
    clusters.append(cur)

    row_groups = []
    for cl in clusters:
        lo, hi = min(cl) - 0.5, max(cl) + 0.5
        row_words = [w for w in words if lo <= w["top"] <= hi]
        if row_words:
            row_groups.append(row_words)
    return row_groups


def _has_alpha(tok: str) -> bool:
    return any(c.isalpha() for c in tok)


def _split_glued_date(tokens: list[dict]) -> list[dict]:
    """A confirmed rare shape: the date token is glued directly onto the
    next value with no space at all. Split any token matching the date
    regex with trailing text into two synthetic word-entries sharing the
    original x0/top, so downstream column bucketing sees them separately."""
    out: list[dict] = []
    for w in tokens:
        m = _DATE_RE.match(w["text"])
        if m and m.group(2):
            out.append({**w, "text": m.group(1)})
            out.append({**w, "text": m.group(2)})
        else:
            out.append(w)
    return out


def _find_date_index(tokens: list[dict]) -> int | None:
    for i, w in enumerate(tokens):
        if _DATE_RE.match(w["text"]):
            return i
    return None


# Markers that identify the repeating header block and page footer, so
# they're excluded from row-clustering entirely (never mistaken for a data
# row, and never swept up as an "orphan" description/document fragment for
# the next real row). "Description" alone would also match every real
# row's own DESCRIPTION column-word text if a component were literally
# named that, but combined with "ATA" or "P/N" on the same physical line
# it is unambiguous -- these only ever co-occur on the column-header line
# itself in the real sample.
_HEADER_FOOTER_MARKERS = (
    "OCCM COMPONENTS STATUS",
    "Type Reg",
    "Airbus",
    "TTSN",  # the header's own "<reg> <msn> TTSN <hours>" line
    "TCSN",  # the header's own "TCSN <cycles>" line
    "nstallation",  # "Installation"/"lnstallation" sub-header, both spellings
    "Description P/N",  # column-header line (also catches corrupted P/N spacing)
    "Prepared by",
    "Page",
)


def _is_header_or_footer(tokens: list[dict]) -> bool:
    joined = " ".join(w["text"] for w in tokens)
    return any(marker in joined for marker in _HEADER_FOOTER_MARKERS)


def _is_data_row(tokens: list[dict]) -> bool:
    return _find_date_index(tokens) is not None


def _parse_data_row(tokens: list[dict]) -> dict:
    tokens = sorted(tokens, key=lambda w: w["x0"])
    tokens = _split_glued_date(tokens)
    date_idx = _find_date_index(tokens)
    ata_tok = tokens[0]
    date_tok = tokens[date_idx]
    ata_x = ata_tok["x0"]
    date_x = date_tok["x0"]

    rec: dict = {c: "" for c in CANONICAL_COLUMNS}
    rec["ATA"] = ata_tok["text"]
    rec["INSTALL_DATE"] = date_tok["text"]

    span = max(date_x - ata_x, 1.0)
    buckets: dict[str, list[str]] = {}
    for w in tokens[1:date_idx]:
        frac = (w["x0"] - ata_x) / span
        col = _bucket_by_fraction(frac)
        buckets.setdefault(col, []).append(w["text"])
    for name in ("DESCRIPTION", "PART_NUMBER", "SERIAL_NUMBER", "POSITION"):
        rec[name] = " ".join(buckets.get(name, []))

    layout = _layout_for(date_x)
    trail_buckets: dict[str, list[str]] = {}
    for w in tokens[date_idx + 1:]:
        col = _bucket_trailing(w["x0"], layout)
        trail_buckets.setdefault(col, []).append(w["text"])
    for name in ("TTSN", "TCSN", "TSI", "CSI", "DOCUMENT"):
        rec[name] = " ".join(trail_buckets.get(name, []))

    return rec


def _attach_orphan(rec: dict, tokens: list[dict], layout: dict) -> None:
    """Attribute an orphan (no-date) line's tokens to the FOLLOWING data
    row `rec`, per the confirmed "orphan fragments belong to the next row"
    rule in the module docstring. Letter-bearing tokens left of the
    DOCUMENT boundary are treated as a DESCRIPTION continuation prefix;
    tokens at/after the DOCUMENT boundary are treated as a DOCUMENT
    prefix. A digit-only token left of the DOCUMENT boundary is neither
    confidently -- it is kept out of both named columns and appended to
    STATUS_TRAIL instead."""
    tokens = sorted(tokens, key=lambda w: w["x0"])
    doc_boundary = layout["doc_boundary"]
    desc_words: list[str] = []
    doc_words: list[str] = []
    trail_words: list[str] = []
    for w in tokens:
        if w["x0"] >= doc_boundary:
            doc_words.append(w["text"])
        elif _has_alpha(w["text"]):
            desc_words.append(w["text"])
        else:
            trail_words.append(w["text"])
    if desc_words:
        rec["DESCRIPTION"] = (" ".join(desc_words) + " " + rec["DESCRIPTION"]).strip()
    if doc_words:
        rec["DOCUMENT"] = (" ".join(doc_words) + " " + rec["DOCUMENT"]).strip()
    if trail_words:
        rec["STATUS_TRAIL"] = (" ".join(trail_words) + " " + rec["STATUS_TRAIL"]).strip()


def _parse_page(words: list[dict], page_num: int, header_meta: dict) -> list[dict]:
    records: list[dict] = []
    pending_orphans: list[list[dict]] = []
    for tokens in _cluster_rows(words):
        if _is_header_or_footer(tokens):
            continue
        if _is_data_row(tokens):
            rec = _parse_data_row(tokens)
            date_x = None
            m_tok = tokens[_find_date_index(sorted(tokens, key=lambda w: w["x0"]))]
            date_x = m_tok["x0"]
            layout = _layout_for(date_x)
            for orphan in pending_orphans:
                _attach_orphan(rec, orphan, layout)
            pending_orphans = []
            for key in _HEADER_META_KEYS:
                rec[key] = header_meta.get(key, "")
            rec["_page"] = page_num
            records.append(rec)
        else:
            pending_orphans.append(tokens)
    # Any orphans left over at the bottom of the page (e.g. a footer
    # artifact, or a genuine wrapped fragment for a row on the NEXT page)
    # are dropped rather than misattributed -- confirmed the real sample's
    # per-page footer ("Prepared by: ...") always falls in this bucket and
    # is not a real record fragment.
    return records


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    header_meta: dict = {}
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if len(text) < 50:
                continue
            page_meta = _parse_header(text.splitlines()[:6])
            for k, v in page_meta.items():
                if v:
                    header_meta[k] = v

            words = page.extract_words()
            if not words:
                continue
            records.extend(_parse_page(words, page_num, header_meta))
    return records
