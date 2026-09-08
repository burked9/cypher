"""OC/CM Components (paired "INSTALLATION" / "CURRENT" data columns) --
born-digital, full text layer, coordinate-bucketed columns. Confirmed via a
direct pdfplumber pass over every page of one real sample file (no OCR
needed; extract() is synchronous).

Header block (repeats verbatim at the top of every page)::

    OC/CM COMPONENTS
    <aircraft type>
    AIRCRAFT REG. : <reg> CURRENT DATE : <D-Mon-YY>
    MSN : <msn> TOTAL AIRCRAFT HOURS : <n>
    MFD : <D-Mon-YY> TOTAL AIRCRAFT CYCLES : <n>
    INSTALLATION CURRENT
    Item ATA DESCRIPTION PART NO. SERIAL NO. POSITION REMARKS
                                  DATE TAT TAC TSN CSN

AIRCRAFT_TYPE / AIRCRAFT_REG / CURRENT_DATE / MSN / MFD /
TOTAL_AIRCRAFT_HOURS / TOTAL_AIRCRAFT_CYCLES are parsed once per page (kept
across pages if a later page's header line fails to match) and stamped onto
every row.

This is a DIFFERENT format from occm_variants/occm_component_data_install_
current.py: that module's paired groups are each four columns wide
(TSN/TSO/CSN/CSO at install, then the same four again current) with no
report-native item number or free-text REMARKS column; this format's
"INSTALLATION" group holds DATE/TAT/TAC (an install-date plus the total
aircraft hours/cycles recorded AT that installation) and its "CURRENT"
group holds just TSN/CSN (the component's own accumulated time/cycles
since new, as of the report's own CURRENT DATE) -- both a narrower pair of
groups and a differently-shaped header block. Confirmed no shared
SIGNATURES phrase between the two modules.

Unicode dash normalisation: the sample file renders every hyphen (dates,
reg, part/serial numbers, the aircraft type) as U+2010 HYPHEN rather than
ASCII U+002D -- normalized via shared.cleanup.normalize_dashes on each
page's raw text BEFORE any regex/anchor parsing runs (per that helper's own
docstring: char-map-based per-cell fixups in the shared cleanup pipeline
run too late for row-anchor regexes that already failed to match).

Column geometry (why word x-position bucketing, not token-count splitting):
DESCRIPTION is free text of very uneven length -- on a handful of rows it
overflows past where PART_NO.'s own column normally starts (confirmed
directly: a wrapped qualifier trailing a component name lands close to,
but always short of, the real PART_NO. data column's x0). Because of that,
the DESCRIPTION/PART_NUMBER boundary is deliberately placed well clear of
DESCRIPTION's observed overflow rather than at the naive midpoint between
the two columns' own anchors -- every other column boundary here IS a
simple midpoint between adjacent anchors, all measured directly off real
DATA word x0 (not the column header labels, which for several columns land
noticeably right of their own data, the same header/data mismatch pattern
already confirmed in the sibling module above). The four right-aligned
numeric columns (TAT/TAC under INSTALLATION, TSN/CSN under CURRENT) shift
x0 with their own value's digit width (right-justified), so each of their
four boundaries is set from the full observed spread of real data x0 for
that column, not a single sample point. POSITION has the same kind of
overflow as DESCRIPTION: a handful of rows carry a two-token POSITION
value (e.g. a trailing single-letter or "#<n>" qualifier) whose second
token lands well past POSITION's typical x0, out near where INSTALL_DATE's
own column starts -- confirmed directly against several such rows, with a
clear gap short of INSTALL_DATE's real date values -- so POSITION's own
upper boundary is set past that overflow rather than at a naive midpoint,
the same reasoning as the DESCRIPTION/PART_NUMBER boundary above.

Row validity, and why it needs no marker-string matching at all: every
genuine data row's line begins with two clean integers -- the report's own
Item sequence number, then the ATA chapter -- landing in the first two
column buckets. The repeating page header/column-header block, the page-
number footer, and the closing signature block (names, job titles) never
have that shape (confirmed directly against every page, including the
report's final page), so requiring both buckets to hold exactly one
digit-only token is a sufficient, robust row filter on its own.

Soft-validation / "never guess a wrong split" and STATUS_TRAIL fallback:
A numeric bucket (TAT/TAC/TSN/CSN) is very often empty on the real sample
(a component installed at build carries a `0`/`0` INSTALLATION pair
alongside the aircraft's own current totals, rather than truly missing
data) -- an empty bucket is left blank, not treated as a failure. A single
token in a numeric bucket is kept verbatim even when it isn't a clean
integer (the sample has at least one row where TSN/CSN both read the
literal placeholder "UNK" instead of a number) -- this is a legitimate
source value, not a parser ambiguity, so it is NOT redirected to
STATUS_TRAIL; the shared cleanup pipeline's own soft `int_range` check
flags it (`not_a_number`) for analyst review instead of this parser
silently guessing or discarding it. The genuine ambiguity this project's
"never guess" convention exists for is a real *split* collision -- more
than one token landing in what should be a single-value numeric bucket
(the same shape documented in occm_variants/occm_component_data_install_
current.py and occm_variants/multi_basis_accumulated_occm.py) -- which has
not been observed on the real sample but is still guarded here: any such
row has its entire raw numeric-region text captured verbatim into
STATUS_TRAIL, with all four named numeric fields left blank, rather than
assigning tokens to fields by guesswork.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules
from shared.cleanup import normalize_dashes

NAME = "OC/CM Components (Installation / Current)"
SIGNATURES = [
    "AIRCRAFT REG. :",
    "MFD :",
]

CANONICAL_COLUMNS = [
    "ITEM",
    "ATA",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "POSITION",
    "INSTALL_DATE",
    "TAT_AT_INSTALL",
    "TAC_AT_INSTALL",
    "TSN_CURRENT",
    "CSN_CURRENT",
    "REMARKS",
    # Ambiguous numeric-region text that can't be reliably split into the
    # four named TAT/TAC/TSN/CSN columns above -- see module docstring.
    "STATUS_TRAIL",
    # Header metadata -- parsed once per page, stamped onto every row.
    "AIRCRAFT_TYPE",
    "AIRCRAFT_REG",
    "CURRENT_DATE",
    "MSN",
    "MFD",
    "TOTAL_AIRCRAFT_HOURS",
    "TOTAL_AIRCRAFT_CYCLES",
]

_DATE_RULE = {"pattern": r"^\d{1,2}-[A-Za-z]{3}-\d{2,4}$", "allow_empty": True}
_NUM_RULE = {"int_range": (0, 300000), "allow_empty": True}
_OVERRIDES = {
    "ITEM": {"pattern": r"^\d{1,6}$"},
    "PART_NUMBER": {"allow_empty": True},
    "SERIAL_NUMBER": {"allow_empty": True},
    "POSITION": {
        "pattern": r"^[A-Z0-9][A-Z0-9#()./\-' ]{0,40}$",
        "uppercase": True,
        "allow_empty": True,
    },
    "INSTALL_DATE": _DATE_RULE,
    "TAT_AT_INSTALL": _NUM_RULE,
    "TAC_AT_INSTALL": _NUM_RULE,
    "TSN_CURRENT": _NUM_RULE,
    "CSN_CURRENT": _NUM_RULE,
    "REMARKS": {"allow_empty": True},
    "STATUS_TRAIL": {"allow_empty": True},
    "AIRCRAFT_TYPE": {
        "pattern": r"^[A-Z0-9\-]{2,20}$",
        "uppercase": True,
        "allow_empty": True,
    },
    "AIRCRAFT_REG": {
        "pattern": r"^[A-Z0-9\-]{2,12}$",
        "uppercase": True,
        "allow_empty": True,
    },
    "CURRENT_DATE": _DATE_RULE,
    "MSN": {"pattern": r"^\d{3,6}$", "allow_empty": True},
    "MFD": _DATE_RULE,
    "TOTAL_AIRCRAFT_HOURS": {"int_range": (0, 300000), "allow_empty": True},
    "TOTAL_AIRCRAFT_CYCLES": {"int_range": (0, 300000), "allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# --- Column x-position boundaries -------------------------------------
# Measured directly off real data-row word coordinates (extract_words())
# on the known sample, across every page (not just page 1) -- see module
# docstring for why DESCRIPTION/PART_NUMBER isn't a naive anchor midpoint,
# and why the four numeric columns each use a measured spread rather than
# a single point.
_BOUNDARIES: list[tuple[str, float, float]] = [
    ("ITEM", float("-inf"), 49.0),
    ("ATA", 49.0, 70.0),
    ("DESCRIPTION", 70.0, 217.0),
    ("PART_NUMBER", 217.0, 285.0),
    ("SERIAL_NUMBER", 285.0, 380.0),
    # POSITION's upper bound is set well past its typical x0 (392-394) --
    # a POSITION value occasionally carries a trailing qualifier word (e.g.
    # "<code> B" / "<code> #1") that overflows out to x0 ~429-434 on the
    # real sample, confirmed directly against several such rows -- there is
    # a confirmed clear gap before INSTALL_DATE's own real data (x0 >= ~446)
    # starts.
    ("POSITION", 380.0, 440.0),
    ("INSTALL_DATE", 440.0, 480.0),
    ("TAT_AT_INSTALL", 480.0, 522.0),
    ("TAC_AT_INSTALL", 522.0, 565.0),
    ("TSN_CURRENT", 565.0, 605.0),
    ("CSN_CURRENT", 605.0, 648.0),
    ("REMARKS", 648.0, float("inf")),
]
_NUMERIC_COLS = ["TAT_AT_INSTALL", "TAC_AT_INSTALL", "TSN_CURRENT", "CSN_CURRENT"]
_DIGIT_RE = re.compile(r"^\d+$")


def _bucket_for(x0: float) -> str:
    for name, lo, hi in _BOUNDARIES:
        if lo <= x0 < hi:
            return name
    return _BOUNDARIES[-1][0]


# --- Header parsing -----------------------------------------------------
_LINE_REG_RE = re.compile(
    r"^AIRCRAFT REG\.\s*:\s*(?P<reg>\S+)\s+CURRENT DATE\s*:\s*(?P<date>\S+)\s*$"
)
_LINE_MSN_RE = re.compile(
    r"^MSN\s*:\s*(?P<msn>\S+)\s+TOTAL AIRCRAFT HOURS\s*:\s*(?P<hours>[\d,]+)\s*$"
)
_LINE_MFD_RE = re.compile(
    r"^MFD\s*:\s*(?P<mfd>\S+)\s+TOTAL AIRCRAFT CYCLES\s*:\s*(?P<cycles>[\d,]+)\s*$"
)
_META_KEYS = (
    "AIRCRAFT_TYPE", "AIRCRAFT_REG", "CURRENT_DATE", "MSN", "MFD",
    "TOTAL_AIRCRAFT_HOURS", "TOTAL_AIRCRAFT_CYCLES",
)


def _parse_header(lines: list[str]) -> dict:
    """Parse the fixed 5-line header block (title / type / reg+date /
    msn+hours / mfd+cycles). AIRCRAFT_TYPE has no anchor phrase of its own
    -- it's identified positionally, as the one header line that isn't the
    title and doesn't match any of the other three regexes, seen before the
    "INSTALLATION"/"Item" column-header lines that close the block."""
    meta: dict = {}
    for line in lines:
        s = line.strip()
        if not s:
            continue
        su = s.upper()
        if su.startswith("OC/CM COMPONENTS"):
            continue
        m = _LINE_REG_RE.match(s)
        if m:
            meta["AIRCRAFT_REG"] = m.group("reg")
            meta["CURRENT_DATE"] = m.group("date")
            continue
        m = _LINE_MSN_RE.match(s)
        if m:
            meta["MSN"] = m.group("msn")
            meta["TOTAL_AIRCRAFT_HOURS"] = m.group("hours")
            continue
        m = _LINE_MFD_RE.match(s)
        if m:
            meta["MFD"] = m.group("mfd")
            meta["TOTAL_AIRCRAFT_CYCLES"] = m.group("cycles")
            continue
        if su.startswith("INSTALLATION") or su.startswith("ITEM"):
            break
        if "AIRCRAFT_TYPE" not in meta:
            meta["AIRCRAFT_TYPE"] = s
    return meta


def _cluster_rows(words: list[dict]) -> list[list[dict]]:
    """Group words into visual rows by their `top` coordinate (2pt
    tolerance -- enough to merge same-line jitter without merging adjacent
    printed lines)."""
    if not words:
        return []
    tops = sorted(set(round(w["top"], 1) for w in words))
    clusters: list[list[float]] = []
    cur = [tops[0]]
    for t in tops[1:]:
        if t - cur[-1] <= 2.0:
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


def _parse_row(row_words: list[dict], page_num: int, header_meta: dict) -> dict | None:
    row_words = sorted(row_words, key=lambda w: w["x0"])
    buckets: dict[str, list[str]] = {}
    for w in row_words:
        col = _bucket_for(w["x0"])
        buckets.setdefault(col, []).append(w["text"])

    # A genuine data row's line always starts with the report's own Item
    # sequence number, then a 2-digit ATA chapter, both landing as single
    # digit-only tokens in the first two buckets. The repeating page
    # header, column-header lines, page-number footer and closing
    # signature block never have that shape -- this single check is a
    # sufficient row filter with no marker-string matching needed (see
    # module docstring).
    item_toks = buckets.get("ITEM", [])
    ata_toks = buckets.get("ATA", [])
    if len(item_toks) != 1 or not _DIGIT_RE.match(item_toks[0]):
        return None
    if len(ata_toks) != 1 or not _DIGIT_RE.match(ata_toks[0]):
        return None

    rec: dict = {c: "" for c in CANONICAL_COLUMNS}
    rec["ITEM"] = item_toks[0]
    rec["ATA"] = ata_toks[0]
    for name in ("DESCRIPTION", "PART_NUMBER", "SERIAL_NUMBER", "POSITION", "REMARKS"):
        rec[name] = " ".join(buckets.get(name, []))

    # INSTALL_DATE is a single left-to-right token (D-Mon-YY), never split
    # across a collision on the real sample -- joined defensively anyway.
    rec["INSTALL_DATE"] = " ".join(buckets.get("INSTALL_DATE", []))

    # Resolve each numeric bucket: 0 tokens -> blank; 1 token -> kept
    # verbatim (even a non-numeric placeholder like "UNK" -- a legitimate
    # source value, soft-flagged downstream rather than guessed at here);
    # more than one token is a genuine split collision -- fold the entire
    # raw numeric-region text into STATUS_TRAIL rather than guess which
    # token belongs to which column (see module docstring).
    ambiguous = False
    for name in _NUMERIC_COLS:
        toks = buckets.get(name, [])
        if not toks:
            rec[name] = ""
        elif len(toks) == 1:
            rec[name] = toks[0]
        else:
            ambiguous = True

    if ambiguous:
        region_words = [w["text"] for w in row_words if _bucket_for(w["x0"]) in _NUMERIC_COLS]
        rec["STATUS_TRAIL"] = " ".join(region_words)
        for name in _NUMERIC_COLS:
            rec[name] = ""
    else:
        rec["STATUS_TRAIL"] = ""

    rec.update(header_meta)
    rec["_page"] = page_num
    return rec


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    header_meta: dict = {k: "" for k in _META_KEYS}
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            raw_text = page.extract_text() or ""
            text = normalize_dashes(raw_text)
            page_meta = _parse_header(text.splitlines()[:6])
            # Header repeats identically on every page; keep the last
            # successfully-parsed value rather than overwriting with blanks
            # if a later page's header line fails to match for any reason.
            for k, v in page_meta.items():
                if v:
                    header_meta[k] = v

            words = page.extract_words()
            if not words:
                continue
            # Normalize dashes on each word's own text too -- extract_words()
            # returns them independently of extract_text() above.
            for w in words:
                w["text"] = normalize_dashes(w["text"])

            for row_words in _cluster_rows(words):
                rec = _parse_row(row_words, page_num, header_meta)
                if rec is not None:
                    records.append(rec)
    return records
