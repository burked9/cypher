"""Multi-basis accumulated-time OCCM export (real text layer, no OCR needed).

A very wide, dense single-line-per-component table. The header carries a
top row grouping five accumulated-time *bases* (how a component's running
totals are counted from):

    NEW ACCUMULATED / OHAU ACCUMULATED / REPA ACCUMULATED / BENC ACCUMULATED
    / INST ACCUMULATED

i.e. since-new / since-overhaul / since-repair / since-bench-check /
since-install. Under that, a second header row gives the per-component
fields followed by the same four sub-columns (HOURS, CYCLES, DAYOP, DAYCA)
repeated once per basis group above::

    IMMAT Last Flight A/C HOURS A/C CYCLES LVL CDN POS ATA/IPC MARK NB MPN
    MSN DESCRIPTION INSTALL DATE
    HOURS CYCLES DAYOP DAYCA   (x5, one block per basis group)

Example header/data shape (values genericized -- placeholders only, no real
aircraft data)::

    NEW ACCUMULATED OHAU ACCUMULATED REPA ACCUMULATED BENC ACCUMULATED INST ACCUMULATED
    IMMAT Last Flight A/C HOURS A/C CYCLES LVL CDN POS ATA/IPC MARK NB MPN MSN DESCRIPTION INSTALL DATE HOURS CYCLES DAYOP DAYCA ...
    <reg> <ddmmmyy> <n> <n> <lvl> <cdn> <pos> <ata_ipc> <mark_nb> <pn> <sn> <desc> <dd/mm/yyyy> <n> <n> <n> <n> ...

Field-name notes (confirmed against the real sample, not guessed):
    - IMMAT is the aircraft registration, repeated identically on every
      row of the file (this variant does not track per-position registration
      changes -- there's only ever one aircraft per export in the sample).
    - MPN, despite the header literally reading "MPN", is the component's
      real MANUFACTURER PART NUMBER in this template (alphanumeric, often
      hyphenated) -- mapped to this project's shared PART_NUMBER column so
      it gets the same OCR normalization / pattern rules as every other
      variant.
    - The header's "MSN" column is, despite the label, NOT the aircraft
      manufacturer serial number -- its values vary per row/component
      (confirmed directly against the sample), so it's really the
      COMPONENT's serial number. Mapped to this project's shared
      SERIAL_NUMBER column, not treated as an airframe MSN field.
    - MARK NB is a distinct reference/tracking code (not obviously a part
      number shape -- no internal hyphens observed), kept as its own
      MARK_NB column rather than folded into PART_NUMBER.
    - ATA/IPC is a single combined code column (not split ATA + IPC) --
      values did not consistently decompose into a clean 2-digit ATA
      chapter, so it's kept as one opaque code column rather than force-fit
      into this project's global 2-digit `ATA` rule (which would also
      wrongly trigger router.py's forward-fill-ATA post-process).

Column geometry (why word x-position bucketing, not token-count splitting):
The header's first 12 fields have irregular widths, but the five repeated
HOURS/CYCLES/DAYOP/DAYCA sub-groups land at consistent x-offsets confirmed
directly against `extract_words()` on the sample's header row. Because many
rows have one or more of the five basis groups blank (e.g. a component with
no bench-check history yet), naive left-to-right token splitting would
silently misassign later columns into earlier slots. Instead every data
word is bucketed by its x0 against boundaries derived from the header's own
word positions (mid-points between consecutive header anchors) -- a missing
value in any column just leaves that bucket empty rather than shifting
everything after it. This is the same category of fix this project uses
elsewhere for ragged/optional-column tables.

Soft-validation / STATUS_TRAIL fallback:
A small fraction of rows (some components flagged "final configuration /
not installed" in the source, plus a handful of genuinely garbled/wrapped
lines where a component's DESCRIPTION or ATA/IPC value spilled across what
should have been a single visual line) fail a basic "is this bucket a
clean integer" check across the 20 numeric sub-columns. Rather than force
those tokens into the wrong HOURS/CYCLES/DAYOP/DAYCA slot (which would
silently fabricate structure that isn't really there), the ENTIRE raw text
of the numeric region for that row is captured verbatim into one
STATUS_TRAIL catch-all column and all 20 named numeric fields are left
blank for that row -- per this project's "never guess a wrong split"
convention (see e.g. occm_variants/stars_trax_occm.py,
llp_variants/oases_lifed_components_llp.py).

No OCR is used: a direct pdfplumber pass over the sample confirmed a full,
clean text layer (extract() is synchronous, unlike the OCR-backed variants
in this same package).
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "Multi-Basis Accumulated OCCM"
SIGNATURES = [
    "NEW ACCUMULATED",
    "OHAU ACCUMULATED",
    "BENC ACCUMULATED",
    "IMMAT Last Flight",
]

# --- Column layout -----------------------------------------------------
# x0 anchors below were read directly off the sample's header row via
# pdfplumber's extract_words() (header text top ~156pt on page 1); the
# midpoint between consecutive anchors is used as the bucket boundary so a
# data word lands in whichever column's anchor it's closest to. Only the
# five repeated basis-group blocks share a perfectly regular pitch --
# the first 12 fields have irregular header-label widths, which is fine
# since bucketing is x0-based, not width-based.
_NAMED_COLS = [
    ("REGISTRATION",     48.3),
    ("LAST_FLIGHT_DATE", 101.2),
    ("AC_HOURS",         172.3),
    ("AC_CYCLES",        241.9),
    ("LVL",              312.4),
    ("CDN",              351.1),
    ("POS",              391.4),
    ("ATA_IPC",          432.7),
    ("MARK_NB",          492.7),
    ("PART_NUMBER",      559.1),   # source header label: "MPN"
    ("SERIAL_NUMBER",    643.8),   # source header label: "MSN" (component SN, not aircraft MSN)
    ("DESCRIPTION",      723.8),
    ("INSTALL_DATE",     816.7),
]

_BASIS_GROUPS = ["NEW", "OHAU", "REPA", "BENC", "INST"]
_GROUP_X0 = [897.0, 1124.8, 1352.5, 1580.2, 1808.0]
_SUBCOLS = ["HOURS", "CYCLES", "DAYOP", "DAYCA"]
_SUB_OFFSETS = [0.0, 60.1, 119.5, 173.9]

_NUMERIC_COLS: list[str] = []
_ALL_COLS = list(_NAMED_COLS)
for _gi, _g in enumerate(_BASIS_GROUPS):
    for _si, _s in enumerate(_SUBCOLS):
        _name = f"{_g}_{_s}"
        _NUMERIC_COLS.append(_name)
        _ALL_COLS.append((_name, _GROUP_X0[_gi] + _SUB_OFFSETS[_si]))

_COL_NAMES = [c[0] for c in _ALL_COLS]
_COL_X0 = [c[1] for c in _ALL_COLS]
_BOUNDARIES: list[tuple[float, float]] = []
for _i in range(len(_COL_X0)):
    _lo = float("-inf") if _i == 0 else (_COL_X0[_i - 1] + _COL_X0[_i]) / 2
    _hi = float("inf") if _i == len(_COL_X0) - 1 else (_COL_X0[_i] + _COL_X0[_i + 1]) / 2
    _BOUNDARIES.append((_lo, _hi))

# Where the numeric (basis-group) region starts, for capturing the whole
# region verbatim into STATUS_TRAIL when it can't be trusted column-by-column.
_NUMERIC_REGION_START = _GROUP_X0[0] - 30.0


def _bucket_for(x0: float) -> str:
    for name, (lo, hi) in zip(_COL_NAMES, _BOUNDARIES):
        if lo <= x0 < hi:
            return name
    return _COL_NAMES[-1]


CANONICAL_COLUMNS = [c[0] for c in _NAMED_COLS] + _NUMERIC_COLS + ["STATUS_TRAIL"]

_OVERRIDES = {
    "REGISTRATION":     {"pattern": r"^[A-Z0-9]{4,7}$", "uppercase": True},
    "LAST_FLIGHT_DATE": {"pattern": r"^\d{2}[A-Z]{3}\d{2}$", "uppercase": True},
    "AC_HOURS":         {"pattern": r"^\d+$", "int_range": (0, 200000)},
    "AC_CYCLES":        {"pattern": r"^\d+$", "int_range": (0, 200000)},
    "LVL":              {"pattern": r"^[A-Z0-9]{1,2}$", "uppercase": True, "allow_empty": True},
    "CDN":              {"pattern": r"^[A-Z]{1,2}$", "uppercase": True, "allow_empty": True},
    "POS":              {"pattern": r"^[A-Z0-9]{1,6}$", "uppercase": True, "allow_empty": True},
    "ATA_IPC":          {"pattern": r"^\d{4,8}$", "uppercase": True, "allow_empty": True},
    "MARK_NB":          {"pattern": r"^[A-Z0-9]{1,10}$", "uppercase": True, "allow_empty": True},
    # PART_NUMBER / SERIAL_NUMBER: no override -- inherit the shared global
    # OCR-normalization + pattern rules used by every other variant.
    "DESCRIPTION":      {"uppercase": True, "allow_empty": True},
    "INSTALL_DATE":      {"pattern": r"^\d{2}/\d{2}/\d{4}$", "allow_empty": True},
    "STATUS_TRAIL":     {"allow_empty": True},
}
for _basis_col in _NUMERIC_COLS:
    _OVERRIDES[_basis_col] = {"pattern": r"^\d+$", "int_range": (0, 200000), "allow_empty": True}

RULES = merged_rules(_OVERRIDES)

_INT_RE = re.compile(r"^[-+]?\d{1,3}(?:[,.']\d{3})*$|^[-+]?\d+$")
_HEADER_MARKERS = ("ACCUMULATED", "IMMAT")


def _is_header_row(joined_text: str) -> bool:
    return any(marker in joined_text for marker in _HEADER_MARKERS)


def _cluster_rows(words: list[dict]) -> list[list[dict]]:
    """Group words into visual rows by their `top` coordinate.

    Row height in the sample is a consistent ~14.4pt; a 2pt tolerance
    clusters words belonging to the same printed line without merging
    adjacent lines.
    """
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


def _parse_row(row_words: list[dict], page_num: int) -> dict | None:
    joined = " ".join(w["text"] for w in row_words)
    if _is_header_row(joined):
        return None

    row_words = sorted(row_words, key=lambda w: w["x0"])
    buckets: dict[str, list[str]] = {}
    for w in row_words:
        col = _bucket_for(w["x0"])
        buckets.setdefault(col, []).append(w["text"])

    rec: dict = {}
    for name, _ in _NAMED_COLS:
        rec[name] = " ".join(buckets.get(name, []))

    # Numeric basis-group region: only trust the column-by-column split if
    # every populated sub-column holds exactly one clean integer token.
    # Anything else (multi-word overflow, non-numeric text like a
    # "not installed" status phrase, a truncated/garbled continuation
    # line) means the positional assumption broke down for this row --
    # fold the whole region into STATUS_TRAIL instead of guessing.
    pure = True
    for name in _NUMERIC_COLS:
        vals = buckets.get(name, [])
        if len(vals) > 1 or (len(vals) == 1 and not _INT_RE.match(vals[0])):
            pure = False
            break

    if pure:
        for name in _NUMERIC_COLS:
            vals = buckets.get(name, [])
            rec[name] = vals[0] if vals else ""
        status_trail = ""
    else:
        for name in _NUMERIC_COLS:
            rec[name] = ""
        region_words = [w["text"] for w in row_words if w["x0"] >= _NUMERIC_REGION_START]
        status_trail = " ".join(region_words)

    rec["STATUS_TRAIL"] = status_trail
    rec["_page"] = page_num
    return rec


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            words = page.extract_words()
            if not words:
                continue
            for row_words in _cluster_rows(words):
                rec = _parse_row(row_words, page_num)
                if rec is not None:
                    records.append(rec)
    return records
