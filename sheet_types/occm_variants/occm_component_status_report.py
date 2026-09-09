"""OCCM COMPONENT STATUS report -- a per-aircraft component inventory headed
by (labels shown genericized; the real header text carries the same heavy
character-substitution corruption described below)::

    <operator name>
    OCCM COMPONENT STATUS
    MSN A/C REGISTRATION A/C TSN A/C CSN AS OF DATE
    <type> <msn> <reg> <tsn> <csn> <date>
    No ATA Location Description Part Number Serial Number InstallDate TSI CSI

followed by one row per installed/tracked component, e.g. (values
genericized)::

    <no> <ata> <location> <description...> <pn> <sn> <date> <tsi> <csi>

Confirmed on a single real file so far (singleton cluster) -- born-digital,
full text layer (`extract_text()`/`extract_words()` return real content on
every page, no OCR needed; `extract()` is synchronous). The text layer is
real but carries SEVERE, systematic character-substitution corruption --
consistent with an OCR pass somewhere upstream of this particular PDF's own
creation, the same "real but noisy text layer" pattern already documented
elsewhere in this project (see e.g. `llp_variants/engine_items_control_llp_
status.py`, `occm_variants/occm_components_status.py`). Confirmed corruption
examples seen directly in the sample (never "corrected", just described here
so the pattern is recognisable, and deliberately NOT reproducing the actual
corrupted strings verbatim -- only their shape): digit 0/O and 1/l/I
confusions throughout every numeric-looking field; multi-character header
labels scrambled beyond recognition (e.g. "MSN" and "A/C REGISTRATION"
rendered with substituted/transposed glyphs); a date value occasionally
rendered as one glued token with no recoverable separator at all. On the
worst-affected pages (confirmed directly: a handful of pages near the
middle/end of the sample), the corruption is severe enough that entire rows
collapse into a run of single-character tokens with no recoverable field
boundaries at all -- these rows are simply not recovered as clean records
(per this project's "never guess a wrong split" convention; a meaningful
per-file flagged-row rate is therefore expected and acceptable here, not a
bug to engineer away).

Row grain: one row per component. Columns, left to right: NO, ATA,
LOCATION, DESCRIPTION (may be more than one whitespace-split token),
PART_NUMBER, SERIAL_NUMBER, INSTALL_DATE, TSI, CSI. ATA and LOCATION are
occasionally missing entirely from a real row (confirmed directly: several
rows -- mostly in engine/APU-adjacent sections -- render with NO immediately
followed by DESCRIPTION, no ATA or LOCATION token at all); TSI and/or CSI
are occasionally missing too (confirmed: some rows carry only one trailing
numeric value, some carry none).

Row detection is positional/structural, not regex-on-exact-shape, per this
project's established handling of this exact corruption pattern (see the
two sibling modules named above). A strict per-row token-count or per-token
date regex was tried first and rejected: real INSTALL_DATE values render
with an unpredictable number of embedded spaces (confirmed directly --
e.g. a single date sometimes prints as one token, sometimes split across
two or three whitespace-separated fragments with a stray space next to a
separator), which breaks both fixed token-count row shapes and strict
per-token date patterns. The values are real, just inconsistently
whitespace-split by the upstream renderer.

Column geometry -- word x-position bucketing, not token counting:
Every word on the page (`extract_words()`) is assigned to a canonical
column purely by its own x0 position, using boundaries derived directly
from measuring real data-row word positions across the sample (NOT from
the column-header row's own label positions, which were confirmed to sit
at noticeably different x-offsets than where the data itself actually
starts). This makes row parsing immune to the embedded-space problem above:
a date value split into two or three word-fragments still lands correctly
in the INSTALL_DATE bucket and is simply joined with a single space,
verbatim, no matter how many fragments it was split into. The same
technique handles PART_NUMBER / SERIAL_NUMBER values that occasionally
render with an internal stray space for the same underlying reason.

Row clustering: words are grouped into row-clusters by chain-merging
consecutive (sorted, de-duplicated) `top` values within a small tolerance,
same technique as `occm_components_status.py`. This was measured directly
against the sample: a single logical row's own words can scatter across
several points of `top` (confirmed up to roughly 2-3pt of scatter within
one row, itself a symptom of the same upstream corruption), while
consecutive real rows are reliably spaced roughly 9-10pt apart -- well
clear of the chosen tolerance, so this never bridges two distinct rows
together.

Row validity: a cluster qualifies as a data row when (a) its top falls
below the page's header block (measured directly: the repeating title/
column-header block always sits above a fixed top on every page, data
rows always below it), (b) its INSTALL_DATE-bucket text contains at least
one digit (the header/column-header rows' own label text in that x-band
never does), and (c) it has some DESCRIPTION-or-LOCATION content and some
PART_NUMBER-or-SERIAL_NUMBER content. This was checked directly against
the sample: it accepts the large majority of real rows (including ones
missing ATA/LOCATION or missing TSI/CSI) and rejects the repeating title/
header block, page-footer artefacts, and stray out-of-band glyphs, without
needing to hardcode any operator name or other document-specific string as
a skip-line marker.

No digit-level "correction" (0/O, 1/l/I, etc.) is attempted anywhere in
this module on any column, per this project's "never guess a wrong split,
wrong data is worse than missing data" convention -- the raw extracted
text (words found in that column's x-range, joined with a single space,
exactly as pdfplumber returns them) is kept as-is. The shared global
ATA/PART_NUMBER/SERIAL_NUMBER rules already carry an OCR char-map that
runs during validation/cleanup (see `shared/aviation_rules.py`), so this
corruption is handled centrally rather than guessed at per-variant.

Header metadata (AIRCRAFT_TYPE, MSN, AIRCRAFT_REG, AIRCRAFT_TSN,
AIRCRAFT_CSN, AS_OF_DATE) is parsed once from the first page's own
aircraft-summary row -- confirmed to sit at a consistent position between
the title block and the column-header row on every page, and confirmed
clean (single-token-per-field, no embedded-space splitting) specifically
on the first page -- and stamped onto every row, same convention this
project's other header-plus-body OCCM variants use (e.g.
`oc_component_status.py`). Later pages repeat the same aircraft-summary
row but were confirmed to sometimes carry MORE corruption than the first
page (including, on the worst-affected pages, the single-character-token
collapse described above), so only the first page's row is used rather
than merging/overwriting across pages.
"""
from __future__ import annotations
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "OCCM Component Status Report"
SIGNATURES = [
    "OCCM COMPONENT STATUS",
]

CANONICAL_COLUMNS = [
    "NO",
    "ATA",
    "LOCATION",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "INSTALL_DATE",
    "TSI",
    "CSI",
    # Header metadata -- parsed once, stamped onto every row.
    "AIRCRAFT_TYPE",
    "MSN",
    "AIRCRAFT_REG",
    "AIRCRAFT_TSN",
    "AIRCRAFT_CSN",
    "AS_OF_DATE",
]

_TIME_RULE = {"allow_empty": True, "int_range": (0, 200000)}
_OVERRIDES = {
    "NO": {"pattern": r"^[A-Za-z0-9]{1,6}$", "allow_empty": True},
    "LOCATION": {"allow_empty": True},
    "INSTALL_DATE": {"allow_empty": True},
    "TSI": _TIME_RULE,
    "CSI": _TIME_RULE,
    "AIRCRAFT_TYPE": {"allow_empty": True},
    "MSN": {"pattern": r"^[A-Za-z0-9]{2,8}$", "allow_empty": True},
    "AIRCRAFT_REG": {"allow_empty": True},
    # Header-level context, not per-row tracked data -- the same raw value
    # is stamped on all 648 rows, so a strict numeric pattern here would
    # turn one corrupted header field into a 100%-flagged file (confirmed:
    # this file's own header CSN is genuinely corrupted, e.g. a digit
    # misread as a letter) without surfacing anything about the row's own
    # data quality. Kept as free text, matching how other purely-contextual
    # header fields (AIRCRAFT_TYPE, AIRCRAFT_REG) are already handled here.
    "AIRCRAFT_TSN": {"allow_empty": True},
    "AIRCRAFT_CSN": {"allow_empty": True},
    "AS_OF_DATE": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# --- Row clustering ----------------------------------------------------------
# Chain-merge tolerance for grouping words into visual row-clusters by their
# `top` coordinate -- see module docstring "Row clustering".
_TOP_TOLERANCE = 2.5

# The repeating title/header block (operator name, report title, column
# labels) always sits above this `top` on every page of the sample; every
# real data row sits below it. Measured directly (column-header row tops
# ~150-153; first real data row tops ~161+ on every page checked).
_HEADER_BLOCK_MAX_TOP = 155.0

# The aircraft-summary row (AIRCRAFT_TYPE/MSN/AIRCRAFT_REG/.../AS_OF_DATE)
# sits between the column-LABEL row (top ~131-133 on every page checked)
# and the column-header row (top ~150-153) on every page. Measured
# directly: its own top is consistently in the ~138-146 band -- narrow
# enough to not catch the column-label row just above it (confirmed
# directly: the two rows' tops are ~8pt apart on every page checked, well
# outside this band's own width).
_SUMMARY_ROW_TOP_LO = 138.0
_SUMMARY_ROW_TOP_HI = 146.0

# --- Column geometry: x0 boundaries -----------------------------------------
# Each (name, upper) pair is that column's own upper x0 boundary (a word
# qualifies for that column when its x0 is less than this value, having
# already failed every earlier column's boundary). CSI is the implicit
# catch-all for anything at/after the last (TSI) boundary. Derived directly
# from measuring real data-row word x0 positions across the sample (see
# module docstring "Column geometry") -- NOT from the column-header row's
# own (differently-positioned) label text.
_BOUNDS = [
    ("NO", 42.0),
    ("ATA", 58.0),
    ("LOCATION", 118.0),
    ("DESCRIPTION", 292.0),
    ("PART_NUMBER", 365.0),
    ("SERIAL_NUMBER", 448.0),
    ("INSTALL_DATE", 498.0),
    ("TSI", 533.0),
]


def _bucket(x0: float) -> str:
    for name, upper in _BOUNDS:
        if x0 < upper:
            return name
    return "CSI"


def _cluster_rows(words: list[dict]) -> list[list[dict]]:
    """Group words into visual line-clusters by their `top` coordinate,
    chain-merging consecutive tops within `_TOP_TOLERANCE` -- see module
    docstring "Row clustering"."""
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


def _has_digit(s: str) -> bool:
    return any(c.isdigit() for c in s)


def _bucket_row(tokens: list[dict]) -> tuple[dict, float]:
    tokens = sorted(tokens, key=lambda w: w["x0"])
    top = min(w["top"] for w in tokens)
    buckets: dict[str, list[str]] = {}
    for w in tokens:
        buckets.setdefault(_bucket(w["x0"]), []).append(w["text"])
    row_cols = ("NO", "ATA", "LOCATION", "DESCRIPTION", "PART_NUMBER",
                "SERIAL_NUMBER", "INSTALL_DATE", "TSI", "CSI")
    rec = {c: " ".join(buckets.get(c, [])) for c in row_cols}
    return rec, top


def _is_data_row(rec: dict, top: float) -> bool:
    if top < _HEADER_BLOCK_MAX_TOP:
        return False
    if not _has_digit(rec["INSTALL_DATE"]):
        return False
    if not rec["DESCRIPTION"] and not rec["LOCATION"]:
        return False
    if not rec["PART_NUMBER"] and not rec["SERIAL_NUMBER"]:
        return False
    return True


def _parse_summary_row(words: list[dict]) -> dict:
    """Parse the first page's aircraft-summary row (AIRCRAFT_TYPE, MSN,
    AIRCRAFT_REG, AIRCRAFT_TSN, AIRCRAFT_CSN, AS_OF_DATE) -- see module
    docstring. Reuses the same column x0-buckets as data rows: this row's
    six values land, in order, in the NO/LOCATION/DESCRIPTION/PART_NUMBER/
    SERIAL_NUMBER/INSTALL_DATE bands (confirmed directly against the real
    first-page row)."""
    for cl in _cluster_rows(words):
        top = min(w["top"] for w in cl)
        if _SUMMARY_ROW_TOP_LO <= top <= _SUMMARY_ROW_TOP_HI:
            buckets: dict[str, list[str]] = {}
            for w in sorted(cl, key=lambda w: w["x0"]):
                buckets.setdefault(_bucket(w["x0"]), []).append(w["text"])
            return {
                "AIRCRAFT_TYPE": " ".join(buckets.get("NO", [])),
                "MSN": " ".join(buckets.get("LOCATION", [])),
                "AIRCRAFT_REG": " ".join(buckets.get("DESCRIPTION", [])),
                "AIRCRAFT_TSN": " ".join(buckets.get("PART_NUMBER", [])),
                "AIRCRAFT_CSN": " ".join(buckets.get("SERIAL_NUMBER", [])),
                "AS_OF_DATE": " ".join(buckets.get("INSTALL_DATE", [])),
            }
    return {}


_HEADER_META_KEYS = (
    "AIRCRAFT_TYPE", "MSN", "AIRCRAFT_REG",
    "AIRCRAFT_TSN", "AIRCRAFT_CSN", "AS_OF_DATE",
)


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    header_meta: dict = {}
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            words = page.extract_words()
            if not words:
                continue
            if page_num == 1:
                header_meta = _parse_summary_row(words)
            for cl in _cluster_rows(words):
                rec, top = _bucket_row(cl)
                if not _is_data_row(rec, top):
                    continue
                for key in _HEADER_META_KEYS:
                    rec[key] = header_meta.get(key, "")
                rec["_page"] = page_num
                records.append(rec)
    return records
