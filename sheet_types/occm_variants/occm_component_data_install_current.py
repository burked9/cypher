"""OC/CM Component Data (paired "at install" / "current" basis) -- born-
digital, full text layer, coordinate-bucketed columns. Confirmed via a
direct pdfplumber pass over every page of one real sample file (no OCR
needed; extract() is synchronous).

Header block (repeats verbatim at the top of every page)::

    <code> OC/CM(MSN<msn>)
    As of <D-Mon-YY or D-Mon-YYYY>
    Component Data at Install Current Component Data
    Components P/N S/N POS TSN TSO CSN CSO Install Date TSN TSO CSN CSO

`<code>` is a short source/carrier code (letters, digits, occasionally an
apostrophe) -- captured verbatim as SOURCE_CODE, never assumed to mean
anything more specific. `<msn>` and the "As of" date are parsed once and
stamped onto every row as MSN / AS_OF_DATE.

Confirmed real-file quirk: on the file's FIRST page only, the as-of date's
trailing 2-digit year is rendered as a separate word one space to the right
of the rest of the date (e.g. the raw text reads like ``As of <d-mon-yy>
<yy>``, joining to a normal 4-digit year) -- every other page renders the
same date as one clean token. Both shapes are handled: if a lone 1-2 digit
trailing token follows the date on the header line, it is concatenated
(no space) onto the date rather than treated as a separate field.

Column geometry (why word x-position bucketing, not token-count splitting):
The column header's own word positions are NOT reliable column anchors for
the free-text fields (Components/P.N/S.N/POS render noticeably left of
their own header labels -- confirmed directly by comparing header vs. data
word x0 on the real sample), so text-column boundaries are set from the
observed DATA word clusters instead of the header labels. The eight
numeric sub-columns (TSN/TSO/CSN/CSO at install, then again current) DO
land at the header's own word x-positions once measured directly against
several real rows (confirmed against both a "light" section, mostly
airframe systems, and a distinct "heavy" section of engine-position
components later in the same file -- both share the same eight anchors).
Bucketing every word by x0 means a row missing one or more of the eight
numeric values (extremely common -- see below) just leaves that bucket
empty rather than shifting everything after it.

Soft-validation / STATUS_TRAIL fallback, and why:
CSN/CSO "at install" are populated on only a small minority of rows in the
real sample -- most rows carry just TSN/TSO at install (hours only, no
cycles recorded at that historical point). This is treated as legitimate
sparse data, not a parsing failure: each of the eight numeric buckets is
filled independently, and an empty bucket is simply left blank.

A separate, rarer shape is a genuine ambiguity: occasionally the POSITION
text for a row is long enough that a trailing word of it lands inside what
should be a purely-numeric bucket (e.g. a wrapped qualifier like "(FWD
CBN)" landing next to a TSN value). Because POSITION is known to be a
free-text field that can run long, and a numeric bucket should only ever
hold zero or one pure-integer token, this specific shape is resolved
without guessing: any non-numeric word found in a numeric bucket is moved
back onto POSITION (it is always the row's own overflowing position text,
never a random word), leaving at most one integer token in that bucket.
If, after that, a numeric bucket still holds more than one token (a shape
not seen as explainable overflow -- e.g. an upstream spreadsheet-export
artifact like a stray "#REF!" alongside real numbers), the ENTIRE raw
numeric-region text for that row is captured verbatim into STATUS_TRAIL and
all eight named numeric fields are left blank for that row, per this
project's "never guess a wrong split" convention (see e.g.
occm_variants/multi_basis_accumulated_occm.py, occm_variants/
occm_list_at_aircraft_fh.py).

Row validity: a real component row always carries at least one of
PART_NUMBER / SERIAL_NUMBER (confirmed on the sample: every genuine
component line has one or both). Rows with neither are wrapped-line
continuation fragments, page footer/signature-block noise (e.g. a
"Printed by ..." / "Status ... dated on ..." footer, or the page's own
handwritten-signature-line artifact), or the column-header line itself
wrapping its own "cso" sub-label onto a second physical line -- none of
these are real records and are dropped rather than emitted as garbage rows.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "OC/CM Component Data (Install / Current)"
SIGNATURES = [
    "Component Data at Install",
    "Components P/N S/N POS TSN TSO CSN",
]

CANONICAL_COLUMNS = [
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "POSITION",
    "TSN_AT_INSTALL",
    "TSO_AT_INSTALL",
    "CSN_AT_INSTALL",
    "CSO_AT_INSTALL",
    "INSTALL_DATE",
    "TSN_CURRENT",
    "TSO_CURRENT",
    "CSN_CURRENT",
    "CSO_CURRENT",
    # Ambiguous numeric-region text that can't be reliably split into the
    # eight named TSN/TSO/CSN/CSO columns above -- see module docstring.
    "STATUS_TRAIL",
    # Header metadata -- parsed once, stamped onto every row.
    "SOURCE_CODE",
    "MSN",
    "AS_OF_DATE",
]

_NUM_RULE = {"pattern": r"^\d+$", "int_range": (0, 300000), "allow_empty": True}
_OVERRIDES = {
    # Compound/dual PN values are confirmed real (a component occasionally
    # carries two space-separated designators in this column) -- allow an
    # optional second alphanumeric token rather than collapsing the space
    # (which would glue two distinct designators into one bogus token) or
    # flagging every such row as bad_format.
    "PART_NUMBER": {
        "pattern": r"^[A-Z0-9][A-Z0-9.\-]*(?: [A-Z0-9][A-Z0-9.\-]*)?$",
        "no_spaces": False,
    },
    # Same confirmed dual-designator quirk as PART_NUMBER above, seen on a
    # handful of rows in the SERIAL_NUMBER column instead.
    "SERIAL_NUMBER": {
        "pattern": r"^[A-Z0-9/][A-Z0-9.\-/]*(?: [A-Z0-9/][A-Z0-9.\-/]*)?$",
        "no_spaces": False,
    },
    "POSITION": {
        "pattern": r"^[A-Z0-9][A-Z0-9#()./\-' ]{0,40}$",
        "uppercase": True,
        "allow_empty": True,
    },
    "TSN_AT_INSTALL": _NUM_RULE,
    "TSO_AT_INSTALL": _NUM_RULE,
    "CSN_AT_INSTALL": _NUM_RULE,
    "CSO_AT_INSTALL": _NUM_RULE,
    "TSN_CURRENT": _NUM_RULE,
    "TSO_CURRENT": _NUM_RULE,
    "CSN_CURRENT": _NUM_RULE,
    "CSO_CURRENT": _NUM_RULE,
    "INSTALL_DATE": {"pattern": r"^\d{4}-\d{1,2}-\d{1,2}$", "allow_empty": True},
    "STATUS_TRAIL": {"allow_empty": True},
    "SOURCE_CODE": {"pattern": r"^[A-Za-z0-9'\-]{1,12}$", "allow_empty": True},
    "MSN": {"pattern": r"^\d{3,6}$", "allow_empty": True},
    "AS_OF_DATE": {"pattern": r"^\d{1,2}-[A-Za-z]{3}-\d{2,4}$", "allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# --- Column x-position anchors --------------------------------------------
# Measured directly off real data-row word coordinates (extract_words()) on
# the known sample: the text columns (DESCRIPTION/PART_NUMBER/SERIAL_NUMBER/
# POSITION) from several ordinary rows, the eight numeric columns cross-
# checked against both a mostly-empty-CSN "light" section and a fully
# populated "heavy" (engine-position) section elsewhere in the same file.
_NAMED_COLS = [
    ("DESCRIPTION", 76.0),
    ("PART_NUMBER", 235.0),
    ("SERIAL_NUMBER", 300.0),
    ("POSITION", 359.0),
    ("TSN_AT_INSTALL", 429.0),
    ("TSO_AT_INSTALL", 468.0),
    ("CSN_AT_INSTALL", 507.0),
    ("CSO_AT_INSTALL", 546.0),
    ("INSTALL_DATE", 590.0),
    ("TSN_CURRENT", 630.0),
    ("TSO_CURRENT", 671.0),
    ("CSN_CURRENT", 712.0),
    ("CSO_CURRENT", 753.0),
]
_NUMERIC_COLS = [
    "TSN_AT_INSTALL", "TSO_AT_INSTALL", "CSN_AT_INSTALL", "CSO_AT_INSTALL",
    "TSN_CURRENT", "TSO_CURRENT", "CSN_CURRENT", "CSO_CURRENT",
]

_COL_NAMES = [c[0] for c in _NAMED_COLS]
_COL_X0 = [c[1] for c in _NAMED_COLS]
_BOUNDARIES: list[tuple[float, float]] = []
for _i in range(len(_COL_X0)):
    _lo = float("-inf") if _i == 0 else (_COL_X0[_i - 1] + _COL_X0[_i]) / 2
    _hi = float("inf") if _i == len(_COL_X0) - 1 else (_COL_X0[_i] + _COL_X0[_i + 1]) / 2
    _BOUNDARIES.append((_lo, _hi))


def _bucket_for(x0: float) -> str:
    for name, (lo, hi) in zip(_COL_NAMES, _BOUNDARIES):
        if lo <= x0 < hi:
            return name
    return _COL_NAMES[-1]


_HEADER1_RE = re.compile(r"^(?P<code>\S+)\s+OC/CM\(MSN(?P<msn>\d+)\)\s*$")
_HEADER2_RE = re.compile(
    r"^As of\s+(?P<date>\d{1,2}-[A-Za-z]{3}-\d{2,4})(?:\s+(?P<extra>\d{1,2}))?\s*$"
)
_HEADER_MARKERS = (
    "OC/CM(", "As of", "Component Data at Install", "Components P/N",
    "Printed by", "Status", "Team Manager", "Maintenance Engineering",
)
_DIGIT_RE = re.compile(r"^\d+$")


def _parse_header(lines: list[str]) -> dict:
    meta = {"SOURCE_CODE": "", "MSN": "", "AS_OF_DATE": ""}
    for line in lines:
        m1 = _HEADER1_RE.match(line.strip())
        if m1:
            # A stray leading hyphen is a confirmed rendering artifact on a
            # handful of pages (the header title's own code, otherwise
            # identical throughout the file) -- stripped so SOURCE_CODE is
            # stable across every row rather than varying page to page.
            meta["SOURCE_CODE"] = m1.group("code").lstrip("-")
            meta["MSN"] = m1.group("msn")
            continue
        m2 = _HEADER2_RE.match(line.strip())
        if m2:
            date = m2.group("date")
            extra = m2.group("extra")
            if extra:
                date = date + extra
            meta["AS_OF_DATE"] = date
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


def _is_header_or_footer(joined: str) -> bool:
    if any(marker in joined for marker in _HEADER_MARKERS):
        return True
    # The column-header line's "P/N" and "S/N" labels occasionally extract
    # as "PIN"/"SIN" or "S/N" run together with neighbouring text (a
    # font/slash-rendering quirk, confirmed on the real sample -- varies by
    # page). The line always starts with the literal word "Components"
    # (never a real component description), so that alone is a reliable
    # anchor regardless of how the rest of the line renders.
    return joined.startswith("Components")


def _parse_row(row_words: list[dict], page_num: int, header_meta: dict) -> dict | None:
    joined = " ".join(w["text"] for w in row_words)
    if _is_header_or_footer(joined):
        return None

    row_words = sorted(row_words, key=lambda w: w["x0"])
    buckets: dict[str, list[str]] = {}
    for w in row_words:
        col = _bucket_for(w["x0"])
        buckets.setdefault(col, []).append(w["text"])

    rec: dict = {c: "" for c in CANONICAL_COLUMNS}
    for name in ("DESCRIPTION", "PART_NUMBER", "SERIAL_NUMBER", "POSITION", "INSTALL_DATE"):
        rec[name] = " ".join(buckets.get(name, []))

    # Resolve each numeric bucket: 0 tokens -> blank; 1 pure-integer token
    # -> that value; multiple tokens where exactly one is a pure integer
    # and the rest are non-numeric -> the non-numeric part is POSITION text
    # that overflowed into this bucket, moved back onto POSITION; anything
    # else (more than one integer token, or a non-numeric token alongside
    # more than one integer) is an unresolvable collision.
    ambiguous = False
    for name in _NUMERIC_COLS:
        toks = buckets.get(name, [])
        if not toks:
            rec[name] = ""
            continue
        if len(toks) == 1:
            if _DIGIT_RE.match(toks[0]):
                rec[name] = toks[0]
            else:
                ambiguous = True
            continue
        nums = [t for t in toks if _DIGIT_RE.match(t)]
        nonnums = [t for t in toks if not _DIGIT_RE.match(t)]
        if len(nums) == 1 and nonnums:
            rec["POSITION"] = (rec["POSITION"] + " " + " ".join(nonnums)).strip()
            rec[name] = nums[0]
        else:
            ambiguous = True

    if ambiguous:
        region_words = [w["text"] for w in row_words if _bucket_for(w["x0"]) in _NUMERIC_COLS]
        rec["STATUS_TRAIL"] = " ".join(region_words)
        for name in _NUMERIC_COLS:
            rec[name] = ""
    else:
        rec["STATUS_TRAIL"] = ""

    # Normalize the rare middle-dot artifact seen in one section's install
    # dates (e.g. "2012·5-30") to the ordinary ASCII-hyphen shape used
    # everywhere else in the file, before pattern validation runs.
    if rec["INSTALL_DATE"]:
        rec["INSTALL_DATE"] = rec["INSTALL_DATE"].replace("·", "-")

    # A genuine component row always carries at least a PN or SN, and it
    # always contains at least one digit (confirmed on the sample -- every
    # real PN/SN in this file has one). Rows with neither, or with only
    # punctuation/underscore fragments (a handwritten-signature-line
    # artifact that occasionally deposits a stray character or two inside
    # this column's x-range), are continuation/footer/signature noise --
    # dropped rather than emitted as garbage records.
    pn, sn = rec["PART_NUMBER"], rec["SERIAL_NUMBER"]
    if not pn and not sn:
        return None
    if not any(ch.isdigit() for ch in pn) and not any(ch.isdigit() for ch in sn):
        return None
    if not rec["DESCRIPTION"]:
        return None

    rec.update(header_meta)
    rec["_page"] = page_num
    return rec


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    header_meta: dict = {"SOURCE_CODE": "", "MSN": "", "AS_OF_DATE": ""}
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            page_meta = _parse_header(text.splitlines()[:3])
            # Header repeats identically on every page; keep the last
            # successfully-parsed value rather than overwriting with blanks
            # if a later page's header line fails to match for any reason.
            for k, v in page_meta.items():
                if v:
                    header_meta[k] = v

            words = page.extract_words()
            if not words:
                continue
            for row_words in _cluster_rows(words):
                rec = _parse_row(row_words, page_num, header_meta)
                if rec is not None:
                    records.append(rec)
    return records
