"""OCCM UIC status report -- a per-aircraft component status listing headed
by (labels shown genericized; the real header text carries the same heavy
character-substitution corruption described below)::

    <operator name / logo, rendered as glyph noise on every page>
    OCCM UIC <reg> (MSN <msn>), TSN: <tsn>, CSN: <csn>
    ATA COMPONENT PN COMPONENT SN COMPONENT DESCRIPTION POSITION DATE HOURS CYCLES TSI CSI TSN CSN

followed by one row per installed/tracked component, e.g. (values
genericized)::

    <ata> <pn> <sn> <description...> <position> <date> <hours> <cycles> <tsi> <csi> <tsn> <csn>

Confirmed on a single real file so far (singleton cluster) -- born-digital,
full text layer (`extract_text()`/`extract_words()` return real content on
every page, no OCR needed; `extract()` is synchronous). The text layer is
real but carries SEVERE, systematic character-substitution corruption --
the same "real but noisy text layer" pattern already documented elsewhere in
this project (see e.g. `occm_variants/occm_components_status.py` and
`occm_variants/occm_component_status_report.py`). Confirmed corruption
examples seen directly in the sample (never "corrected", just described here
so the pattern is recognisable, and deliberately NOT reproducing the actual
corrupted strings verbatim -- only their shape): digit 0/O and 1/l/I
confusions throughout every numeric-looking field; a stray logo/cover-page
glyph run bleeding onto the top of every page's own header block (worst on
page 1, per the caller's own note); multi-character column-header labels
scrambled beyond recognition on some pages (e.g. "POSITION" and "DATE"
rendered with substituted glyphs) while the same header renders comparatively
cleanly on other pages -- confirmed directly, this project's established
reason for never keying row detection off the header row's own text; and a
value occasionally rendered as more than one whitespace-split token with an
extra stray single-character fragment attached (e.g. a serial number's own
column picking up one extra garbled glyph token beside the real value).
A literal "UNK" placeholder appears in the last four numeric columns (TSI,
CSI, TSN, CSN) on many rows -- confirmed directly, a valid sentinel meaning
"not tracked/unknown", not a parse failure, and therefore not corrected or
rejected anywhere in this module.

Row grain: one row per component. Columns, left to right: ATA, PART_NUMBER,
SERIAL_NUMBER, DESCRIPTION (may be more than one whitespace-split token),
POSITION, INSTALL_DATE, HOURS, CYCLES, TSI, CSI, TSN, CSN.

Row detection is positional/structural, not regex-on-exact-shape, per this
project's established handling of this exact corruption pattern (see the two
sibling modules named above). A strict per-row token-count check was tried
first and rejected: a real row's own words scatter across a noticeably wider
`top` band than the ~2-3pt seen in those sibling modules -- measured directly
against this sample, up to roughly 10-11pt of scatter within one logical row
(e.g. the INSTALL_DATE token, and occasionally a second PART_NUMBER-column
fragment, land several points off the row's own main word cluster) -- while
consecutive real rows are reliably spaced roughly 13pt apart, still well
clear of the wider tolerance this file needs. A fixed per-row token count
also does not hold: DESCRIPTION width varies token-to-token, and POSITION
occasionally arrives as a single token or as two (e.g. a side qualifier plus
a location word).

Column geometry -- word x-position bucketing, not token counting: every word
on the page (`extract_words()`) is assigned to a canonical column purely by
its own x0 position, using boundaries derived directly from measuring real
data-row word positions across the sample (NOT from the column-header row's
own label positions, which were confirmed to sit at noticeably different
x-offsets on some pages than where the data itself actually starts -- see
"Row detection" above re: the header row's own unreliable text). This makes
row parsing immune to the embedded-space / stray-fragment problem above: a
value split into two or three word-fragments, or carrying one extra stray
glyph token, still lands in the right column bucket and is simply joined
with a single space, verbatim, however many fragments it was split into.

Row clustering: words are grouped into row-clusters by chain-merging
consecutive (sorted, de-duplicated) `top` values within a tolerance measured
directly against this sample (wider than the ~2.5pt used in the sibling
modules above, per the "up to ~10-11pt of scatter" note above) -- chosen to
be comfortably smaller than the ~13pt real row-to-row spacing measured
directly across the sample, so it never bridges two distinct rows together
while still reliably pulling in a row's own stray fragments.

Row validity: a cluster qualifies as a data row when (a) its top falls below
the page's own header/title block (measured directly: the repeating title/
column-header block and the per-page aircraft-summary line always sit above
a fixed top on every page, data rows always below it), (b) it has some
PART_NUMBER-or-SERIAL_NUMBER content and some DESCRIPTION content, and (c)
at least one of HOURS, CYCLES or INSTALL_DATE contains a digit. (c) is what
actually separates a real row from two kinds of noise that otherwise land
with non-empty PART_NUMBER/SERIAL_NUMBER/DESCRIPTION purely by x-position
coincidence: the page-footer "Page <n> of <total>" artefact, and (on the
final page only) a trailing signature/sign-off block -- neither carries any
digit in those three columns. This was checked directly against the sample:
together these three conditions accept the large majority of real rows and
reject the repeating title/header block, the per-page aircraft-summary
line, page-footer page-number artefacts, and the final page's trailing
signature/sign-off block, without needing to hardcode any operator name,
person name, or other document-specific string as a skip-line marker.

No digit-level "correction" (0/O, 1/l/I, etc.) is attempted anywhere in this
module on any column, per this project's "never guess a wrong split, wrong
data is worse than missing data" convention -- the raw extracted text (words
found in that column's x-range, joined with a single space, exactly as
pdfplumber returns them) is kept as-is. The shared global ATA/PART_NUMBER/
SERIAL_NUMBER rules already carry an OCR char-map that runs during
validation/cleanup (see `shared/aviation_rules.py`), so this corruption is
handled centrally rather than guessed at per-variant.

Header metadata (AIRCRAFT_REG, MSN, AIRCRAFT_TSN, AIRCRAFT_CSN) is parsed
once from the first page's own aircraft-summary line -- confirmed to render
as a single legible line ("OCCM UIC <reg> (MSN <msn>), TSN: <tsn>, CSN:
<csn>", modulo the "OCCM"/"UIC" run itself sometimes gluing together or
picking up a stray glyph) on every page checked, but only the first page's
own rendering is used, since that is the one instance confirmed clean and
unambiguous by direct inspection -- and stamped onto every row, same
convention this project's other header-plus-body OCCM variants use (e.g.
`occm_component_status_report.py`, `oc_component_status.py`).
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "OCCM UIC Status"
SIGNATURES = [
    "OCCMUIC",
]

CANONICAL_COLUMNS = [
    "ATA",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
    "POSITION",
    "INSTALL_DATE",
    "HOURS",
    "CYCLES",
    "TSI",
    "CSI",
    "TSN",
    "CSN",
    # Header metadata -- parsed once, stamped onto every row.
    "AIRCRAFT_REG",
    "MSN",
    "AIRCRAFT_TSN",
    "AIRCRAFT_CSN",
]

# TSI/CSI/TSN/CSN carry a literal "UNK" sentinel on many real rows (see
# module docstring), so no numeric int_range check is used here -- a
# hard-numeric rule would misclassify that valid sentinel as a parse
# failure. Embedded-space artefacts (a value split across two word
# fragments, see docstring) are tolerated by the pattern too.
_NUM_OR_UNK = {"allow_empty": True, "pattern": r"^(UNK|[0-9][0-9,.'\s]*)$"}
_OVERRIDES = {
    "POSITION": {"allow_empty": True},
    "INSTALL_DATE": {"allow_empty": True},
    "HOURS": _NUM_OR_UNK,
    "CYCLES": _NUM_OR_UNK,
    "TSI": _NUM_OR_UNK,
    "CSI": _NUM_OR_UNK,
    "TSN": _NUM_OR_UNK,
    "CSN": _NUM_OR_UNK,
    "AIRCRAFT_REG": {"allow_empty": True},
    "MSN": {"pattern": r"^[A-Za-z0-9]{2,10}$", "allow_empty": True},
    # Header-level context, not per-row tracked data -- the same raw value is
    # stamped on every row, so a strict numeric pattern here would turn one
    # corrupted (or merely unusually-formatted) header field into a
    # near-100%-flagged file without surfacing anything about the row's own
    # data quality. Kept as free text, matching the established fix pattern
    # in occm_component_status_report.py's AIRCRAFT_TSN/AIRCRAFT_CSN fields.
    "AIRCRAFT_TSN": {"allow_empty": True},
    "AIRCRAFT_CSN": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# --- Row clustering ----------------------------------------------------------
# Chain-merge tolerance for grouping words into visual row-clusters by their
# `top` coordinate -- see module docstring "Row clustering". Wider than the
# ~2.5pt used by sibling modules for the less-scattered corruption pattern:
# measured directly against this sample, a row's own stray fragments (a
# split INSTALL_DATE token, an extra PART_NUMBER-column fragment) can land
# up to ~10-11pt from the row's main cluster, while consecutive real rows
# are reliably ~13pt apart -- this tolerance stays comfortably under that
# row-to-row spacing.
_TOP_TOLERANCE = 5.0

# The repeating title/header block (logo noise, "OCCM UIC ... TSN ... CSN
# ..." summary line, column-header row) always sits above this `top` on
# every page of the sample; every real data row's own main cluster sits
# below it. Measured directly (column-header row tops ~95-101; first real
# data row's own top ~107-111 on every page checked).
_HEADER_BLOCK_MAX_TOP = 105.0

# --- Column geometry: x0 boundaries -----------------------------------------
# Each (name, upper) pair is that column's own upper x0 boundary (a word
# qualifies for that column when its x0 is less than this value, having
# already failed every earlier column's boundary). CSN is the implicit
# catch-all for anything at/after the last (TSN) boundary. Derived directly
# from measuring real data-row word x0 positions across the sample (see
# module docstring "Column geometry") -- NOT from the column-header row's
# own (unreliable, sometimes differently-positioned) label text.
_BOUNDS = [
    ("ATA", 100.0),
    ("PART_NUMBER", 182.0),
    ("SERIAL_NUMBER", 290.0),
    ("DESCRIPTION", 446.0),
    ("POSITION", 500.0),
    ("INSTALL_DATE", 543.0),
    ("HOURS", 578.0),
    ("CYCLES", 615.0),
    ("TSI", 650.0),
    ("CSI", 684.0),
    ("TSN", 717.0),
]

# The first page's own aircraft-summary line, e.g.::
#   OCCM UIC <reg> (MSN <msn>), TSN: <tsn>, CSN: <csn>
# Tolerant of the "OCCM"/"UIC" run gluing together or picking up a stray
# glyph between them (confirmed directly: renders as e.g. "OCCMUIC" on the
# sample's first page), and of a trailing comma landing inside the captured
# TSN group (stripped below).
_SUMMARY_RE = re.compile(
    r"OCCM\s*U\w*C\s+(\S+)\s*\(MSN\s+(\S+?)\)\s*,?\s*"
    r"TSN:\s*([0-9.,:]+),?\s*CSN:\s*([0-9.,]+)",
    re.IGNORECASE,
)


def _bucket(x0: float) -> str:
    for name, upper in _BOUNDS:
        if x0 < upper:
            return name
    return "CSN"


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


_ROW_COLS = (
    "ATA", "PART_NUMBER", "SERIAL_NUMBER", "DESCRIPTION", "POSITION",
    "INSTALL_DATE", "HOURS", "CYCLES", "TSI", "CSI", "TSN", "CSN",
)


def _bucket_row(tokens: list[dict]) -> tuple[dict, float]:
    tokens = sorted(tokens, key=lambda w: w["x0"])
    top = min(w["top"] for w in tokens)
    buckets: dict[str, list[str]] = {}
    for w in tokens:
        buckets.setdefault(_bucket(w["x0"]), []).append(w["text"])
    rec = {c: " ".join(buckets.get(c, [])) for c in _ROW_COLS}
    return rec, top


def _has_digit(s: str) -> bool:
    return any(c.isdigit() for c in s)


def _is_data_row(rec: dict, top: float) -> bool:
    if top < _HEADER_BLOCK_MAX_TOP:
        return False
    if not rec["PART_NUMBER"] and not rec["SERIAL_NUMBER"]:
        return False
    if not rec["DESCRIPTION"]:
        return False
    # A real row always carries at least one genuine time/date value in one
    # of these three columns (confirmed directly across the sample). This
    # is what actually separates a real data row from page-footer artefacts
    # ("Page <n> of <total>", which lands with SERIAL_NUMBER/DESCRIPTION
    # non-empty purely by x-position coincidence) and the trailing
    # signature/sign-off block on the final page (same coincidence) --
    # neither carries any digit in HOURS/CYCLES/INSTALL_DATE.
    if not (_has_digit(rec["HOURS"]) or _has_digit(rec["CYCLES"])
            or _has_digit(rec["INSTALL_DATE"])):
        return False
    return True


def _parse_summary_line(text: str) -> dict:
    """Parse the first page's aircraft-summary line (AIRCRAFT_REG, MSN,
    AIRCRAFT_TSN, AIRCRAFT_CSN) -- see module docstring."""
    m = _SUMMARY_RE.search(text)
    if not m:
        return {}
    reg, msn, tsn, csn = m.groups()
    return {
        "AIRCRAFT_REG": reg.rstrip(","),
        "MSN": msn.rstrip(","),
        "AIRCRAFT_TSN": tsn.rstrip(","),
        "AIRCRAFT_CSN": csn.rstrip(","),
    }


_HEADER_META_KEYS = ("AIRCRAFT_REG", "MSN", "AIRCRAFT_TSN", "AIRCRAFT_CSN")


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    header_meta: dict = {}
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            if page_num == 1:
                header_meta = _parse_summary_line(page.extract_text() or "")
            words = page.extract_words()
            if not words:
                continue
            for cl in _cluster_rows(words):
                rec, top = _bucket_row(cl)
                if not _is_data_row(rec, top):
                    continue
                for key in _HEADER_META_KEYS:
                    rec[key] = header_meta.get(key, "")
                rec["_page"] = page_num
                records.append(rec)
    return records
