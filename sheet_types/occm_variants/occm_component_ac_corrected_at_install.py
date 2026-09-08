"""OCCM Component (Corrected A/C Data at Install / Component Data at Install)
-- born-digital, full text layer, coordinate-bucketed columns. Confirmed via
a direct pdfplumber pass over every page of one real sample file (no OCR
needed; extract() is synchronous).

This is a DIFFERENT format from occm_variants/occm_component_data_install_
current.py, even though both files happen to share the literal header
phrase "Component Data at Install" (confirmed directly -- this is why that
substring alone is NOT used as this module's SIGNATURES entry; see below).
The other module's two data groups are "at install" vs "current"; THIS
format has no "current" data at all -- both of its groups are historical
"at install" baselines that differ in what was corrected/recorded:

    OCCM COMPONENT
    A/C TSN <n>
    A/C CSN <n>
    AS OF <D-Mon-YY>
    Corrected A/C Data at Install
    Component Data at Install
    Posi (May be differ with A/C Log)
    Components P/N S/N
    tion
    TSN TSO CSN CSO TSN TSO CSN CSO Date

The header block above appears ONCE, on page 1 only (confirmed directly --
unlike several sibling OCCM variants, it does NOT repeat per page); AC_TSN /
AC_CSN / AS_OF_DATE are parsed once from page 1 and stamped onto every row
of every page. There is no MSN, source code, or title code anywhere in the
file (confirmed via direct inspection of every page, including the final
page's tail).

Column geometry (why word x-position bucketing, not token-count splitting):
The free-text columns' own header labels sit close to but not exactly on
the data words' x0 (e.g. header "P/N"/"S/N" land a few points right of the
actual data column), so text-column boundaries are set from the observed
DATA word clusters. The header row's numeric sub-labels (TSN/TSO/CSN/CSO,
twice, then Date) DO land on the data words' own x0 once measured directly
-- confirmed against rows scattered across the first, second and last pages
of the real sample.

Soft-validation / STATUS_TRAIL fallback, and why:
Each of the eight numeric sub-columns is bucketed independently by x0, so a
row missing some (or all) of them just leaves those buckets blank rather
than shifting later fields. Confirmed directly across every page of the
real sample: the second group's TSO and CSN... no -- TSO and CSO positions
are NEVER populated anywhere in the file (only that group's TSN and CSN
sub-columns ever carry a value) -- this is treated as legitimate sparse
data, not a parsing failure, and both empty sub-columns are simply left
blank on every row.

"." is a literal placeholder glyph meaning "no value recorded" -- confirmed
directly on the real sample -- and is treated the same as an empty bucket
(never treated as a decimal point or any other punctuation). "UNK"/"unk" is
a second, rarer placeholder glyph seen in the same numeric sub-columns,
handled the same way.

A genuine ambiguity (a POSITION continuation word landing inside what
should be a purely-numeric bucket, or more than one integer token landing
in the same bucket) is resolved the same "never guess a wrong split" way as
the sibling module: a lone non-numeric token in an otherwise-empty numeric
bucket is folded back onto POSITION; anything left over that still can't be
resolved to at most one integer token is captured verbatim into
STATUS_TRAIL for that row and all eight named numeric fields are left blank
for it, per this project's convention (see e.g. occm_variants/
occm_component_data_install_current.py, occm_variants/
multi_basis_accumulated_occm.py).

INSTALL_DATE: the real sample shows the ordinary D-Mon-YY(YY) shape on most
rows, but a confirmed minority render as DD.MM.YYYY, and a handful split
across two adjacent word tokens with no space between them (e.g. a raw
"<dd>.<mm>" token immediately followed by a raw ".<yyyy>" token on the same
line) -- the bucket's tokens are joined with NO separator (which reunites
that split shape correctly) rather than a space (which would not). Any
resulting value that still doesn't match either known date shape is left
as-is and flagged by validation rather than guessed at further.

Row validity: a real component row always carries at least one of
PART_NUMBER / SERIAL_NUMBER, and at least one digit in one of them
(confirmed on the sample). Rows with neither -- confirmed on the real
sample's last page, where a component position with nothing currently
fitted prints only a DESCRIPTION and a wrapped POSITION across one or two
extra physical lines, with no PN/SN/numeric data at all -- are dropped
rather than emitted as garbage records, per this project's convention.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "OCCM Component (Corrected A/C Data at Install)"
SIGNATURES = [
    # Deliberately NOT "Component Data at Install" alone -- that phrase is
    # also occm_component_data_install_current.py's own SIGNATURES entry
    # and is present verbatim in this file's header too (confirmed
    # directly), so using it here would be a duplicate, ambiguous anchor.
    # This module's own phrase below is unique to it (checked directly
    # against every existing SIGNATURES list in sheet_types/{occm,ht,llp}.py
    # and every variant file -- no collision either direction).
    "Corrected A/C Data at Install",
    "Posi (May be differ with A/C Log)",
]

CANONICAL_COLUMNS = [
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "POSITION",
    "TSN_AC_AT_INSTALL",
    "TSO_AC_AT_INSTALL",
    "CSN_AC_AT_INSTALL",
    "CSO_AC_AT_INSTALL",
    "TSN_COMPONENT_AT_INSTALL",
    "TSO_COMPONENT_AT_INSTALL",
    "CSN_COMPONENT_AT_INSTALL",
    "CSO_COMPONENT_AT_INSTALL",
    "INSTALL_DATE",
    # Ambiguous numeric-region text that can't be reliably split into the
    # eight named TSN/TSO/CSN/CSO columns above -- see module docstring.
    "STATUS_TRAIL",
    # Header metadata -- parsed once from page 1, stamped onto every row.
    "AC_TSN",
    "AC_CSN",
    "AS_OF_DATE",
]

_NUM_RULE = {"pattern": r"^\d+$", "int_range": (0, 300000), "allow_empty": True}
_OVERRIDES = {
    "PART_NUMBER": {
        "pattern": r"^[A-Z0-9][A-Z0-9.\-]*$",
        "no_spaces": False,
        "allow_empty": True,
    },
    "SERIAL_NUMBER": {
        "pattern": r"^[A-Z0-9/][A-Z0-9.\-/]*$",
        "no_spaces": False,
        "allow_empty": True,
    },
    "POSITION": {
        "pattern": r"^[A-Z0-9][A-Z0-9#()./\-' ]{0,40}$",
        "uppercase": True,
        "allow_empty": True,
    },
    "TSN_AC_AT_INSTALL": _NUM_RULE,
    "TSO_AC_AT_INSTALL": _NUM_RULE,
    "CSN_AC_AT_INSTALL": _NUM_RULE,
    "CSO_AC_AT_INSTALL": _NUM_RULE,
    "TSN_COMPONENT_AT_INSTALL": _NUM_RULE,
    "TSO_COMPONENT_AT_INSTALL": _NUM_RULE,
    "CSN_COMPONENT_AT_INSTALL": _NUM_RULE,
    "CSO_COMPONENT_AT_INSTALL": _NUM_RULE,
    "INSTALL_DATE": {
        "pattern": r"^(\d{1,2}-[A-Za-z]{3}-\d{2,4}|\d{1,2}\.\d{1,2}\.\d{4})$",
        "allow_empty": True,
    },
    "STATUS_TRAIL": {"allow_empty": True},
    "AC_TSN": {"pattern": r"^\d{1,6}$", "allow_empty": True},
    "AC_CSN": {"pattern": r"^\d{1,6}$", "allow_empty": True},
    "AS_OF_DATE": {"pattern": r"^\d{1,2}-[A-Za-z]{3}-\d{2,4}$", "allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# --- Column x-position anchors --------------------------------------------
# Measured directly off real data-row word coordinates (extract_words()) on
# the known sample: the text columns (DESCRIPTION/PART_NUMBER/SERIAL_NUMBER/
# POSITION) from rows scattered across the first, second and last pages; the
# eight numeric sub-columns and the trailing Date column against the
# column-header row's own word x0 (which, unlike the free-text labels, does
# line up with the data on this sample) cross-checked against many data rows.
_NAMED_COLS = [
    ("DESCRIPTION", 40.0),
    ("PART_NUMBER", 244.0),
    ("SERIAL_NUMBER", 299.0),
    ("POSITION", 358.0),
    ("TSN_AC_AT_INSTALL", 406.7),
    ("TSO_AC_AT_INSTALL", 449.6),
    ("CSN_AC_AT_INSTALL", 492.5),
    ("CSO_AC_AT_INSTALL", 535.4),
    ("TSN_COMPONENT_AT_INSTALL", 578.5),
    ("TSO_COMPONENT_AT_INSTALL", 621.2),
    ("CSN_COMPONENT_AT_INSTALL", 663.7),
    ("CSO_COMPONENT_AT_INSTALL", 706.3),
    ("INSTALL_DATE", 748.4),
]
_NUMERIC_COLS = [
    "TSN_AC_AT_INSTALL", "TSO_AC_AT_INSTALL", "CSN_AC_AT_INSTALL", "CSO_AC_AT_INSTALL",
    "TSN_COMPONENT_AT_INSTALL", "TSO_COMPONENT_AT_INSTALL",
    "CSN_COMPONENT_AT_INSTALL", "CSO_COMPONENT_AT_INSTALL",
]

_COL_NAMES = [c[0] for c in _NAMED_COLS]
_COL_X0 = [c[1] for c in _NAMED_COLS]
_BOUNDARIES: list[tuple[float, float]] = []
for _i in range(len(_COL_X0)):
    _lo = float("-inf") if _i == 0 else (_COL_X0[_i - 1] + _COL_X0[_i]) / 2
    _hi = float("inf") if _i == len(_COL_X0) - 1 else (_COL_X0[_i] + _COL_X0[_i + 1]) / 2
    _BOUNDARIES.append((_lo, _hi))

# Confirmed real-file quirk: DESCRIPTION is free text that regularly runs
# past the plain midpoint (142.0) between its own anchor (40.0) and
# PART_NUMBER's (244.0) -- a direct x0 histogram over every word in the real
# sample shows DESCRIPTION words spread continuously up to ~166, then a
# clean, empty gap from ~170 to ~230 before PART_NUMBER's own real cluster
# begins at ~240 -- so the boundary between these two columns specifically
# is overridden to 205.0 (the middle of that empty gap) rather than the
# plain geometric midpoint, which would otherwise misclassify a fair number
# of ordinary, unremarkable-length description words (e.g. a trailing
# parenthetical zone/position qualifier like "(<zone>)") as PART_NUMBER
# overflow.
_DESC_PN_BOUNDARY = 205.0
_BOUNDARIES[_COL_NAMES.index("DESCRIPTION")] = (
    _BOUNDARIES[_COL_NAMES.index("DESCRIPTION")][0], _DESC_PN_BOUNDARY
)
_BOUNDARIES[_COL_NAMES.index("PART_NUMBER")] = (
    _DESC_PN_BOUNDARY, _BOUNDARIES[_COL_NAMES.index("PART_NUMBER")][1]
)


def _bucket_for(x0: float) -> str:
    for name, (lo, hi) in zip(_COL_NAMES, _BOUNDARIES):
        if lo <= x0 < hi:
            return name
    return _COL_NAMES[-1]


# "." and "UNK"/"unk" are the two confirmed literal placeholder glyphs for
# "no value recorded" in the numeric sub-columns -- both treated as an
# empty bucket, never as real content or a decimal point.
_PLACEHOLDER_RE = re.compile(r"^(\.+|unk)$", re.I)
_DIGIT_RE = re.compile(r"^\d+$")

_HEADER_MARKERS = (
    "OCCM COMPONENT", "A/C TSN", "A/C CSN", "AS OF",
    "Corrected A/C Data at Install", "Component Data at Install",
    "Posi", "Components P/N",
)
_AC_TSN_RE = re.compile(r"^A/C\s+TSN\s+(\d+)\s*$")
_AC_CSN_RE = re.compile(r"^A/C\s+CSN\s+(\d+)\s*$")
_AS_OF_RE = re.compile(r"^AS\s+OF\s+(\d{1,2}-[A-Za-z]{3}-\d{2,4})\s*$")


def _parse_header(lines: list[str]) -> dict:
    meta = {"AC_TSN": "", "AC_CSN": "", "AS_OF_DATE": ""}
    for line in lines:
        s = line.strip()
        m = _AC_TSN_RE.match(s)
        if m:
            meta["AC_TSN"] = m.group(1)
            continue
        m = _AC_CSN_RE.match(s)
        if m:
            meta["AC_CSN"] = m.group(1)
            continue
        m = _AS_OF_RE.match(s)
        if m:
            meta["AS_OF_DATE"] = m.group(1)
    return meta


def _cluster_physical_lines(words: list[dict]) -> list[list[dict]]:
    """Group words into individual PRINTED lines by their `top` coordinate
    (2pt tolerance -- enough to merge same-line jitter without merging
    adjacent printed lines)."""
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

    line_groups = []
    for cl in clusters:
        lo, hi = min(cl) - 0.5, max(cl) + 0.5
        line_words = [w for w in words if lo <= w["top"] <= hi]
        if line_words:
            line_groups.append(line_words)
    return line_groups


def _group_logical_rows(words: list[dict]) -> list[list[dict]]:
    """Merge the printed lines that make up one logical record.

    Confirmed directly on the real sample: a genuine component record spans
    TWO (occasionally three) physical printed lines -- DESCRIPTION/PART_
    NUMBER/SERIAL_NUMBER/numeric data on the first, POSITION and/or
    INSTALL_DATE (sometimes a further wrapped POSITION word) on the next
    one or two -- and the gap between those lines is NOT reliably smaller
    than the gap to the following record's own first line (both are only a
    few points apart on some pages), so a fixed `top`-proximity tolerance
    cannot tell them apart. Instead, the DESCRIPTION column's x-position
    (see _NAMED_COLS) is used as the anchor: confirmed directly that only a
    record's own first physical line ever has a word landing in that
    x-range (continuation lines only ever carry POSITION and/or
    INSTALL_DATE words) -- so a new logical row starts exactly when a
    physical line contains a DESCRIPTION-bucket word, and every physical
    line up to (not including) the next such line belongs to the same
    logical row. Physical lines before the first anchor on a page (i.e.
    stray header text) are discarded rather than attached to nothing.
    """
    row_groups: list[list[dict]] = []
    for line_words in _cluster_physical_lines(words):
        starts_new = any(_bucket_for(w["x0"]) == "DESCRIPTION" for w in line_words)
        if starts_new:
            row_groups.append(list(line_words))
        elif row_groups:
            row_groups[-1].extend(line_words)
        # else: stray text before the first anchor on this page (header
        # remnants) -- discarded rather than attached to nothing.
    return row_groups


def _is_header_or_footer(joined: str) -> bool:
    if any(marker.upper() in joined.upper() for marker in _HEADER_MARKERS):
        return True
    # The column-header line's labels ("Components ... P/N S/N", "TSN TSO
    # CSN CSO ...") always start with one of these literal words -- never a
    # real component description -- so they're a reliable anchor regardless
    # of exactly how the header row's own line-wrapping renders.
    return joined.strip().startswith(("Components", "TSN TSO"))


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
    for name in ("DESCRIPTION", "PART_NUMBER", "SERIAL_NUMBER", "POSITION"):
        rec[name] = " ".join(buckets.get(name, []))
    # Confirmed real-file quirk: a split date (e.g. raw tokens "10.05" then
    # ".1998" on the same line) reunites correctly when joined with no
    # separator; joining with a space would not reproduce either known date
    # shape.
    rec["INSTALL_DATE"] = "".join(buckets.get("INSTALL_DATE", []))

    # Resolve each numeric bucket the same way as the sibling "at install /
    # current" module: 0 tokens (or only placeholder glyphs) -> blank; 1
    # real integer token -> that value; multiple tokens where exactly one is
    # a real integer and the rest are non-numeric, non-placeholder text ->
    # the non-numeric part is POSITION text that overflowed into this
    # bucket, moved back onto POSITION; anything else is an unresolvable
    # collision.
    ambiguous = False
    for name in _NUMERIC_COLS:
        toks = [t for t in buckets.get(name, []) if not _PLACEHOLDER_RE.match(t)]
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

    # A genuine component row always carries at least a PN or SN, and it
    # always contains at least one digit (confirmed on the sample). Rows
    # with neither are wrapped POSITION continuation fragments (confirmed on
    # the real sample's last page: a position with nothing currently fitted
    # prints only a DESCRIPTION and a wrapped POSITION across one or two
    # extra physical lines, with no PN/SN/numeric data at all) -- dropped
    # rather than emitted as garbage rows.
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
    header_meta: dict = {"AC_TSN": "", "AC_CSN": "", "AS_OF_DATE": ""}
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            if page_num == 1:
                # Confirmed real-file quirk: the header block (title / A/C
                # TSN / A/C CSN / AS OF / column headers) appears ONCE, on
                # page 1 only -- it does not repeat per page like several
                # sibling OCCM variants -- so it's parsed here just once and
                # carried forward for every later page.
                text = page.extract_text() or ""
                header_meta.update(
                    {k: v for k, v in _parse_header(text.splitlines()[:6]).items() if v}
                )

            words = page.extract_words()
            if not words:
                continue
            for row_words in _group_logical_rows(words):
                rec = _parse_row(row_words, page_num, header_meta)
                if rec is not None:
                    records.append(rec)
    return records
