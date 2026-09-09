"""Condition Monitoring Components Status report -- a per-aircraft
component status listing headed by (labels genericized; the real header
text carries the same heavy character-substitution corruption described
below)::

    A/C: <reg> ON CONDITION] CONDITION MONITORING COMPONENTS STATUS <noise>
    MSN: <msn>
    TOTAL TIME: <n>FH
    TOTAL CYCLES: <n>FC
    ATA <garbled "DESCRIPTION"> <garbled "SERIAL NO"> <garbled "TSN">

followed by a dense, per-ATA-chapter block of component rows, e.g.
(values genericized)::

    <ata> <chapter name> <pn> <sn> <description...> ...
    <pn2> <description...> <position> ...
    , , <description continues...> , <date><unknown-sentinel>...
    ...

Confirmed on a single real file so far (singleton cluster) -- born-digital,
full text layer (`extract_text()`/`extract_words()` return real content on
every page, no OCR needed; `extract()` is synchronous, using pdfplumber
directly). The text layer is real but carries SEVERE character-substitution
corruption, the same "real but noisy text layer" pattern documented
elsewhere in this project (see e.g. `occm_variants/occm_uic_status.py` and
`occm_variants/occm_components_status.py`).

Row grain and reliability -- read this before trusting the output blindly:
this file's per-item structure is measurably MORE tangled than the sibling
modules named above. In those modules a logical row's own words scatter
across a wide-but-bounded `top` band (up to ~10-11pt) around one visual
anchor line. In THIS file's sample, checked directly across many pages,
fields belonging to one physical component are not just scattered in
position -- they are also reordered in content: e.g. an HOURS/CYCLES value
belonging to one component was observed rendering on a `top` line ABOVE
that component's own PART_NUMBER/SERIAL_NUMBER line, i.e. out of the
document's own logical row order, not merely off to the side of it. A
per-row top-tolerance clustering strategy (the approach used by every
sibling module above) was tried first and rejected for this reason: no
tolerance value was found, checked directly against the sample, that
reliably keeps one logical component's fields together without ALSO
bridging two distinct adjacent components together elsewhere on the same
page.

Row detection actually used here is anchor-based instead: a "row" is the
span of `top` values between one PART_NUMBER/SERIAL_NUMBER-shaped token
(see `_is_anchor_tok` -- a word whose x0 falls in the combined
PART_NUMBER/SERIAL_NUMBER column band, at least 4 characters long with at
least 3 digits, i.e. long enough not to be a bare position/continuation
fragment like "-1" or "2") and the next such token, measured directly
against the sample as a reasonably reliable indicator of "a new component
has started" even though individual field values within that span may
still arrive out of visual top-order (per above). Checked directly across
every page: the large majority of components in the sample do carry at
least one such anchor token, giving good (not perfect) row-boundary
recall.

Known gap, disclosed rather than hidden: a small residual of components in
the sample carry NEITHER a PART_NUMBER- nor SERIAL_NUMBER-shaped token at
all (confirmed directly -- e.g. a page whose only two components are minor
filter/valve items with no part or serial number rendered anywhere in
their own text). On any page where zero anchor tokens are found at all,
this module falls back to plain `top`-proximity line clustering (a few
points' tolerance, one row per visual line rather than one row per
component) so that content isn't silently dropped -- but this fallback
knowingly produces a LOWER-fidelity result: one component's fields may be
split across several output rows rather than merged into one. This
fallback was chosen over grouping such a page into one giant merged row,
which would have actively mixed unrelated components' hours/dates/serials
together -- a "wrong data is worse than missing data" call, per this
project's established convention. Checked directly: this fallback path
triggers on a small minority of pages in the sample.

Column geometry -- word x-position bucketing, not token counting (per the
same convention used across the OCCM anchor/x-bucket sibling modules):
every word within a detected row's `top` span is assigned to a column
purely by its own x0 position, using boundaries derived directly from
measuring real data-row word positions across the sample. A value split
into several word-fragments across the row's own multi-line span still
lands in the right column bucket and is simply joined with a single
space, verbatim, however many fragments it was split into, and in
whatever order pdfplumber returned them (sorted by `top` then `x0` before
joining, for readability, but NOT re-ordered against any assumption about
which fragment is semantically "first").

Given the reordering problem described above, this module deliberately
does NOT attempt to split the right-hand portion of each row (install
date / hours / cycles / TSN-ish values) into separate per-column fields:
those values were observed glued together (e.g. a date and an hours
figure concatenated with no separating space), duplicated across a row's
own multiple physical lines, and/or appearing out of order relative to
the row's own PART_NUMBER/SERIAL_NUMBER anchor. Forcing a fixed date /
hours / cycles split here would mean guessing which fragment is which
semantically, which this project's "never guess a wrong split, wrong data
is worse than missing data" convention rules out. Instead, per this
project's established fallback for exactly this situation (see e.g.
`occm_variants/serialised_components_report.py`'s own STATUS_TRAIL
column), everything right of the DESCRIPTION/POSITION columns is kept as
one free-text STATUS_TRAIL column, raw and unmodified, so no information
is discarded, but no field-level meaning is claimed for it either.

Row validity: a candidate row/cluster qualifies as a data row only when it
carries some DESCRIPTION content, or some PART_NUMBER/SERIAL_NUMBER
content, beyond bare punctuation -- this rejects clusters that are pure
comma/whitespace noise (common in this file's own row-continuation lines,
confirmed directly) without needing to hardcode any operator name, person
name, or other document-specific string as a skip-line marker.

No digit-level "correction" (0/O, 1/l/I, etc.) is attempted anywhere in
this module on any column, per this project's established convention --
the raw extracted text is kept as-is, joined verbatim. The shared global
ATA/PART_NUMBER/SERIAL_NUMBER rules already carry an OCR char-map that
runs centrally during validation/cleanup (see `shared/aviation_rules.py`).

ATA is captured only where it renders as a bare 2-digit chapter-header
token at the page's own left margin (its own column, well left of
PART_NUMBER) -- confirmed directly to appear once per chapter, not once
per row. Rows without their own ATA value are forward-filled from the
most recent valid one by the shared `forward_fill_ata()` post-process
(the same generic mechanism every other ATA-bearing OCCM variant in this
project relies on), not by anything in this module itself.

Header metadata (AIRCRAFT_REG, MSN, TOTAL_TIME_FH, TOTAL_CYCLES_FC) is
parsed once from the first page's own aircraft-summary block -- confirmed
to render legibly there -- and stamped onto every row, the same
convention this project's other header-plus-body OCCM variants use (e.g.
`occm_component_status_report.py`, `occm_uic_status.py`). Only the first
page's own rendering is used (per that same established convention),
since later pages were observed to carry the same summary block with
additional, inconsistent character-substitution noise on the numeric
suffixes (e.g. "FH" rendering as a different two-letter pair on some
pages) that the first page's own rendering does not show.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "Condition Monitoring Components Status"
SIGNATURES = [
    "CONDITION MONITORING COMPONENTS STATUS",
]

CANONICAL_COLUMNS = [
    "ATA",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
    "POSITION",
    # Everything right of POSITION (install date / hours / cycles / TSN-ish
    # values) -- kept as one free-text catch-all rather than a guessed
    # per-column split. See module docstring.
    "STATUS_TRAIL",
    # Header metadata -- parsed once, stamped onto every row.
    "AIRCRAFT_REG",
    "MSN",
    "TOTAL_TIME_FH",
    "TOTAL_CYCLES_FC",
]

_OVERRIDES = {
    # PART_NUMBER / SERIAL_NUMBER are frequently absent on a genuine row in
    # this file (see module docstring "Known gap") -- an empty value here
    # is normal, not a parse failure.
    "PART_NUMBER": {"allow_empty": True},
    "SERIAL_NUMBER": {"allow_empty": True},
    "DESCRIPTION": {"allow_empty": True},
    # POSITION / STATUS_TRAIL / header fields carry no GLOBAL_RULES entry
    # at all, so they pass through unruled (no pattern, no flag) -- left
    # out of this override dict deliberately, matching the established fix
    # for "one stamped header field over-flagging the whole file" (see
    # occm_uic_status.py's own AIRCRAFT_TSN/AIRCRAFT_CSN comment).
}
RULES = merged_rules(_OVERRIDES)

# --- Column geometry: x0 boundaries -----------------------------------------
# Derived directly from measuring real data-row word x0 positions across the
# sample (NOT from the column-header row's own label positions, which were
# confirmed to render only partially legibly -- see module docstring).
_ATA_MAX_X0 = 45.0
_LEFT_MAX_X0 = 170.0          # chapter-name text beside the ATA code; folded into DESCRIPTION
_PN_MAX_X0 = 235.0
_SN_MAX_X0 = 345.0
_DESC_MAX_X0 = 555.0
_POS_MAX_X0 = 620.0
# Anything at/after _POS_MAX_X0 is STATUS_TRAIL.

# The repeating title/header block (aircraft-summary lines, column-header
# row) always sits above this `top` on every page of the sample; the
# trailing signature/sign-off block and page-footer artefact always sit
# below the second bound. Measured directly across the sample.
_HEADER_MAX_TOP = 90.0
_FOOTER_MIN_TOP = 560.0

# Anchor token: a word whose x0 falls in the combined PART_NUMBER/
# SERIAL_NUMBER column band, long enough (>=4 chars, >=3 digits) not to be
# a bare position/continuation fragment (e.g. "-1", "2"). See module
# docstring "Row detection".
_ANCHOR_RE_SHORT = re.compile(r"^[-_]?\d{1,2}$")


def _is_anchor_tok(w: dict) -> bool:
    if not (_PN_MAX_X0 - 65.0 <= w["x0"] < _SN_MAX_X0):  # i.e. 170 <= x0 < 345
        return False
    t = w["text"]
    if _ANCHOR_RE_SHORT.match(t):
        return False
    digits = sum(c.isdigit() for c in t)
    return len(t) >= 4 and digits >= 3


_ATA_TOK_RE = re.compile(r"^\d{1,3}$")


def _bucket(w: dict) -> str:
    x0 = w["x0"]
    if x0 < _ATA_MAX_X0:
        # The ATA column only ever holds a bare 1-3 digit chapter code (see
        # module docstring) -- anything else landing in this x-band by
        # coincidence (a stray glyph, a mis-positioned fragment) is noise
        # for this column, not a real ATA value, so it's folded into
        # DESCRIPTION instead of polluting ATA with unparseable text.
        return "ATA" if _ATA_TOK_RE.match(w["text"]) else "DESCRIPTION"
    if x0 < _LEFT_MAX_X0:
        return "DESCRIPTION"  # chapter-name fragment, folded in -- see docstring
    if x0 < _PN_MAX_X0:
        return "PART_NUMBER"
    if x0 < _SN_MAX_X0:
        return "SERIAL_NUMBER"
    if x0 < _DESC_MAX_X0:
        return "DESCRIPTION"
    if x0 < _POS_MAX_X0:
        return "POSITION"
    return "STATUS_TRAIL"


_ROW_COLS = ("ATA", "PART_NUMBER", "SERIAL_NUMBER", "DESCRIPTION", "POSITION", "STATUS_TRAIL")


def _bucket_words(words: list[dict]) -> dict:
    buckets: dict[str, list[str]] = {}
    for w in sorted(words, key=lambda w: (round(w["top"], 1), w["x0"])):
        buckets.setdefault(_bucket(w), []).append(w["text"])
    rec = {c: " ".join(buckets.get(c, [])) for c in _ROW_COLS}
    # A leading "_" is a pervasive rendering-glyph substitution artifact on
    # this file's own PART_NUMBER/SERIAL_NUMBER values (confirmed directly
    # across the sample, e.g. an observed value consistently prefixed with
    # a stray underscore glyph not present in the same value elsewhere in
    # the same document) -- stripped here the same way GLOBAL_RULES already
    # strips other leading punctuation-artifact characters for these two
    # columns (see `_strip_leading_punct` in shared/cleanup.py), just for
    # a character that helper's fixed strip-set doesn't cover.
    rec["PART_NUMBER"] = rec["PART_NUMBER"].lstrip("_")
    rec["SERIAL_NUMBER"] = rec["SERIAL_NUMBER"].lstrip("_")
    return rec


def _is_data_row(rec: dict) -> bool:
    """Reject clusters that are pure punctuation/whitespace noise -- see
    module docstring "Row validity"."""
    combined = rec["DESCRIPTION"] + rec["PART_NUMBER"] + rec["SERIAL_NUMBER"]
    return bool(re.sub(r"[,\s]", "", combined))


def _rows_from_anchors(data_words: list[dict]) -> list[dict]:
    """Primary row-detection path: split `data_words` into spans bounded by
    anchor tokens (see `_is_anchor_tok` / module docstring "Row
    detection")."""
    anchors = sorted((w for w in data_words if _is_anchor_tok(w)), key=lambda w: w["top"])
    if not anchors:
        return []
    boundary_tops = []
    for a in anchors:
        if boundary_tops and a["top"] - boundary_tops[-1] < 3.0:
            continue
        boundary_tops.append(a["top"])

    page_min_top = min(w["top"] for w in data_words)
    page_max_top = max(w["top"] for w in data_words)

    rows = []
    for i, top in enumerate(boundary_tops):
        lo = page_min_top - 1.0 if i == 0 else top - 0.5
        hi = boundary_tops[i + 1] - 0.5 if i + 1 < len(boundary_tops) else page_max_top + 1.0
        span_words = [w for w in data_words if lo <= w["top"] < hi]
        if not span_words:
            continue
        rec = _bucket_words(span_words)
        if _is_data_row(rec):
            rows.append(rec)
    return rows


# Fallback (anchor-less pages only): plain top-proximity line clustering --
# lower fidelity (one row per visual line, not per component), see module
# docstring "Known gap".
_FALLBACK_TOP_TOLERANCE = 3.0


def _rows_from_line_clusters(data_words: list[dict]) -> list[dict]:
    tops = sorted(set(round(w["top"], 1) for w in data_words))
    clusters: list[list[float]] = []
    cur = [tops[0]]
    for t in tops[1:]:
        if t - cur[-1] <= _FALLBACK_TOP_TOLERANCE:
            cur.append(t)
        else:
            clusters.append(cur)
            cur = [t]
    clusters.append(cur)

    rows = []
    for cl in clusters:
        lo, hi = min(cl) - 0.5, max(cl) + 0.5
        line_words = [w for w in data_words if lo <= w["top"] <= hi]
        if not line_words:
            continue
        rec = _bucket_words(line_words)
        if _is_data_row(rec):
            rows.append(rec)
    return rows


# First page's own aircraft-summary block, e.g.::
#   A/C: <reg> ...
#   MSN: <msn>
#   TOTAL TIME: <n>FH
#   TOTAL CYCLES: <n>FC
_REG_RE = re.compile(r"a/c:\s*(\S+)", re.IGNORECASE)
_MSN_RE = re.compile(r"msn:\s*(\S+)", re.IGNORECASE)
_TT_RE = re.compile(r"total\s+time:\s*([0-9][0-9,.\']*)", re.IGNORECASE)
_TC_RE = re.compile(r"total\s+cycles:\s*([0-9][0-9,.\']*)", re.IGNORECASE)


def _parse_header(text: str) -> dict:
    meta = {"AIRCRAFT_REG": "", "MSN": "", "TOTAL_TIME_FH": "", "TOTAL_CYCLES_FC": ""}
    m = _REG_RE.search(text)
    if m:
        meta["AIRCRAFT_REG"] = m.group(1).rstrip(",")
    m = _MSN_RE.search(text)
    if m:
        meta["MSN"] = m.group(1).rstrip(",")
    m = _TT_RE.search(text)
    if m:
        meta["TOTAL_TIME_FH"] = m.group(1)
    m = _TC_RE.search(text)
    if m:
        meta["TOTAL_CYCLES_FC"] = m.group(1)
    return meta


_HEADER_META_KEYS = ("AIRCRAFT_REG", "MSN", "TOTAL_TIME_FH", "TOTAL_CYCLES_FC")


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    header_meta: dict = {}
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            if page_num == 1:
                header_meta = _parse_header(page.extract_text() or "")
            words = page.extract_words()
            if not words:
                continue
            data_words = [w for w in words if _HEADER_MAX_TOP < w["top"] < _FOOTER_MIN_TOP]
            if not data_words:
                continue

            rows = _rows_from_anchors(data_words)
            if not rows:
                # No anchor tokens found anywhere on this page -- fall back
                # to line-clustering rather than dropping the page's
                # content entirely (or merging unrelated components into
                # one row). See module docstring "Known gap".
                rows = _rows_from_line_clusters(data_words)

            for rec in rows:
                for key in _HEADER_META_KEYS:
                    rec[key] = header_meta.get(key, "")
                rec["_page"] = page_num
                records.append(rec)
    return records
