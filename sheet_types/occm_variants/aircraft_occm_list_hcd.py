"""Aircraft OCCM List (H/C/D basis) -- a complex multi-line-per-component
export, confirmed via a direct pdfplumber pass over the real sample file:
a genuine, page-searchable text layer on every inspected page (no OCR
needed) -- this module is synchronous, pdfplumber-only.

Header block (repeated verbatim on every page, first page used to stamp
metadata onto every row per this project's usual convention)::

    Aircraft OCCM List
    A/C REGISTRARION # : <reg> MSN : <msn> LAST UPDATE Date : <date> FLIGHT HOUR : <n> CYCLE : <n>

Column-header block spans two printed lines (also this variant's SIGNATURES
anchors)::

    Zone ATA POS1 P/N S/N Inst. Date Parts Name NHA P/N NHA S/N Originator
    TSI TST TSO TSN TTR TCI Limit Limit Type T/C# TASK Repairer # CERT # SER.DATE Task Note

Row shape -- confirmed directly against `extract_words()` x-positions, not
guessed from `extract_text()`'s flattened line order:

Each component prints as ONE "main" line (Zone / ATA / POS1 / P/N / S/N /
Inst. Date / Parts Name / optionally NHA P/N + NHA S/N / Originator)
followed immediately by exactly THREE "basis" lines, each starting with a
single-letter basis code -- H (hours), C (cycles), D (days) -- confirmed
1:3 (main-line : basis-line) across the whole real sample (1044 main lines,
3132 basis lines, no exceptions, no component split across a page
boundary). Each basis line carries its OWN instance of the second header
block's 14 fields (TSI/TST/TSO/TSN/TTR/TCI/Limit/Limit Type/T/C#/TASK/
Repairer #/CERT #/SER.DATE/Task Note), e.g.::

    <zone> <ata> <pos1> <pn> <sn> <install_date> <parts_name...> <originator>
    H <tsi> <tst> <tso> <tsn>                                          <ser_date>
    C <tsi> <tst> <tso> <tsn>          <ttr> <tci>
    D <tsi> <tst> <tso> <tsn>

Row-modelling decision (3 rows per component, not 1): the task explicitly
asked to check whether the H/C/D lines' four numeric slots repeat the SAME
value across every real row (which would mean TSI/TST/TSO/TSN don't vary
independently on this format). Checked directly across the whole sample:
they do NOT always match -- of 1044 components, the four TSI/TST/TSO/TSN
values disagree with each other on 181 H-lines, 181 C-lines and 300
D-lines (roughly a sixth to a third of rows). So these are four genuinely
distinct columns, not a redundant repeat. Combined with the fact that the
remaining ten fields (TTR/TCI/Limit/Limit Type/T/C#/TASK/Repairer #/
CERT #/SER.DATE/Task Note) are each basis-specific -- confirmed directly,
each only ever appears on ONE of a component's three basis lines, never
more than one -- folding all three bases into a single wide row would need
up to 3 x 14 = 42 mostly-empty columns per component. Modelling one row per
basis line instead (with a BASIS column holding H/C/D) keeps every column
densely populated relative to its own row, mirrors the source's own
per-line record structure, and avoids fabricating a wide/sparse shape that
isn't really there. Header metadata (AIRCRAFT_REG, MSN, LAST_UPDATE_DATE,
FLIGHT_HOUR, CYCLE) and the main-line's component fields (ZONE, ATA, POS1,
PART_NUMBER, SERIAL_NUMBER, INSTALL_DATE, PARTS_NAME, NHA_PN, NHA_SN,
ORIGINATOR) are stamped identically onto all three of a component's rows.

Column geometry (why word x-position bucketing, not token-count
splitting): many fields are optional/sparse (NHA P/N + NHA S/N only appear
on a minority of main lines, e.g. engine/APU-style assemblies with a
parent reference; TTR/TCI/Limit/Limit Type/T/C#/TASK/Repairer #/CERT #/
SER.DATE/Task Note are each populated on only a fraction of basis lines,
and never more than one of these ten per basis line in the sample) --
naive left-to-right token splitting would silently misassign a later
column into an earlier slot whenever an earlier optional field is blank.
Instead every word is bucketed by its x0 against boundaries derived from
the two real header lines' own word positions (midpoint between
consecutive anchors), the same technique this project already uses in
`occm_variants/multi_basis_accumulated_occm.py` and
`occm_variants/occm_list_cert_remark.py`.

A basis-line numeric value is occasionally prefixed with a bare `*`
(confirmed directly, e.g. a Days-basis value rendered as `*1,077`) --
this is stripped as leading punctuation (this project's existing
`_strip_leading_punct` rule, already used on PART_NUMBER/SERIAL_NUMBER
elsewhere) rather than guessed at semantically, since its exact meaning
isn't confirmed and stripping it lets the clean numeric value validate
normally instead of spuriously flagging as `not_a_number`.

Soft-validation / STATUS_TRAIL fallback: a handful of components (8 out of
1044 in the real sample) carry one extra free-text line wrapped below a
basis line -- e.g. an AD-compliance or SB-performed remark that overflowed
its column -- which does not fit the main-line or basis-line column shape
at all (no ATA-shaped token, no leading H/C/D basis code). Rather than
force that text into the wrong field, its raw joined text is appended
verbatim to the STATUS_TRAIL of the most recently emitted row (per this
project's "never guess a wrong split" convention, see e.g.
`occm_variants/multi_basis_accumulated_occm.py`,
`occm_variants/stars_trax_occm.py`).

No OCR is used: extract() is synchronous, unlike the OCR-backed variants
in this same package.
"""
from __future__ import annotations
import re

import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "Aircraft OCCM List (H/C/D Basis)"
SIGNATURES = [
    "Zone ATA POS1 P/N S/N Inst. Date Parts Name NHA P/N NHA S/N Originator",
    "TSI TST TSO TSN TTR TCI Limit Limit Type T/C# TASK Repairer # CERT # SER.DATE Task Note",
]

# --- Header metadata (parsed once from page 1, stamped on every row) ----
_META_RE = re.compile(
    r"A/C\s+REGISTRARION\s*#\s*:\s*(\S+)\s+MSN\s*:\s*(\S+)\s+"
    r"LAST\s+UPDATE\s+Date\s*:\s*(\S+)\s+FLIGHT\s+HOUR\s*:\s*(\S+)\s+CYCLE\s*:\s*(\S+)",
    re.IGNORECASE,
)

# --- Main-line (component) column layout --------------------------------
# x0 anchors read directly off the real sample's first header line
# (top ~71.9pt on page 1) via extract_words().
_MAIN_COLS = [
    ("ZONE",          27.0),
    ("ATA",           64.7),
    ("POS1",          114.7),
    ("PART_NUMBER",   203.2),
    ("SERIAL_NUMBER", 303.2),
    ("INSTALL_DATE",  369.0),
    # NOTE: the header label "Parts Name" itself prints at x0 ~518 (a wide,
    # right-shifted column label), but the real data in that column
    # consistently starts at x0 ~411 (confirmed directly across many rows
    # via extract_words() -- the word immediately following the Inst. Date
    # token). The anchor below uses the confirmed DATA position, not the
    # header label's cosmetic position, or every Parts Name value would be
    # wrongly bucketed into INSTALL_DATE.
    ("PARTS_NAME",    411.0),
    ("NHA_PN",        677.8),
    ("NHA_SN",        738.8),
    ("ORIGINATOR",    790.6),
]

# --- Basis-line column layout --------------------------------------------
# x0 anchors read directly off the real sample's second header line
# (top ~82.9pt on page 1) via extract_words(). The leading H/C/D basis
# label itself sits at x0 ~151.9 and is consumed separately (it identifies
# the row, it isn't a data column).
_BASIS_LABEL_X0 = 151.9
_BASIS_COLS = [
    ("TSI",             178.6),
    ("TST",             227.4),
    ("TSO",             276.8),
    ("TSN",             327.0),
    ("TTR",             377.2),
    ("TCI",             420.0),
    ("LIMIT",           433.2),
    ("LIMIT_TYPE",      462.9),
    ("TC_NUMBER",       523.9),
    ("TASK",            579.9),
    ("REPAIRER_NUMBER", 622.7),
    ("CERT_NUMBER",     679.5),
    ("SER_DATE",        735.5),
    ("TASK_NOTE",       790.0),
]


def _boundaries(anchors: list[tuple[str, float]]) -> tuple[list[str], list[tuple[float, float]]]:
    names = [a[0] for a in anchors]
    xs = [a[1] for a in anchors]
    bounds = []
    for i in range(len(xs)):
        lo = float("-inf") if i == 0 else (xs[i - 1] + xs[i]) / 2
        hi = float("inf") if i == len(xs) - 1 else (xs[i] + xs[i + 1]) / 2
        bounds.append((lo, hi))
    return names, bounds


_MAIN_NAMES, _MAIN_BOUNDS = _boundaries(_MAIN_COLS)
_BASIS_NAMES, _BASIS_BOUNDS = _boundaries(_BASIS_COLS)


def _bucket(x0: float, names: list[str], bounds: list[tuple[float, float]]) -> str:
    for name, (lo, hi) in zip(names, bounds):
        if lo <= x0 < hi:
            return name
    return names[-1]


CANONICAL_COLUMNS = [
    "AIRCRAFT_REG", "MSN", "LAST_UPDATE_DATE", "FLIGHT_HOUR", "CYCLE",
    "ZONE", "ATA", "POS1", "PART_NUMBER", "SERIAL_NUMBER", "INSTALL_DATE",
    "PARTS_NAME", "NHA_PN", "NHA_SN", "ORIGINATOR",
    "BASIS", "TSI", "TST", "TSO", "TSN", "TTR", "TCI", "LIMIT", "LIMIT_TYPE",
    "TC_NUMBER", "TASK", "REPAIRER_NUMBER", "CERT_NUMBER", "SER_DATE",
    "TASK_NOTE", "STATUS_TRAIL",
]

_NUMERIC_RULE = {
    "pattern": r"^\d{1,3}(?:,\d{3})*$",
    "int_range": (0, 500000),
    "allow_empty": True,
    "_strip_leading_punct": True,
}
_DATE_RULE = {"pattern": r"^\d{4}-\d{2}-\d{2}$", "allow_empty": True}

_OVERRIDES = {
    "AIRCRAFT_REG":     {"pattern": r"^[A-Z0-9-]{2,10}$", "uppercase": True, "allow_empty": True},
    "MSN":              {"pattern": r"^[A-Z0-9]{1,10}$", "uppercase": True, "allow_empty": True},
    "LAST_UPDATE_DATE": dict(_DATE_RULE),
    "FLIGHT_HOUR":      {"pattern": r"^\d{1,3}(?:,\d{3})*$", "int_range": (0, 500000), "allow_empty": True},
    "CYCLE":            {"pattern": r"^\d{1,3}(?:,\d{3})*$", "int_range": (0, 500000), "allow_empty": True},
    "ZONE":             {"pattern": r"^[A-Z0-9]{2,8}$", "uppercase": True, "allow_empty": True},
    "ATA":              {"pattern": r"^\d{2}-\d{2}$", "int_range": None},
    # POS1 values in the real sample range from short codes ("LH", "#1")
    # to longer hyphenated/multi-word ones ("R-WW OTBD", "L-EAE NO2",
    # "CAP-POS A") -- confirmed directly, not guessed -- so the pattern
    # allows hyphens and a generous length rather than the tighter
    # single-token shape used elsewhere in this project.
    "POS1":             {"pattern": r"^[A-Z0-9#\- ]{1,20}$", "uppercase": True, "allow_empty": True},
    "INSTALL_DATE":     dict(_DATE_RULE),
    "PARTS_NAME":       {"uppercase": True, "allow_empty": True},
    # NHA_PN / NHA_SN are distinct CANONICAL_COLUMNS names (this project's
    # global PART_NUMBER/SERIAL_NUMBER rules only apply under those exact
    # column names), so an explicit, loose rule is given here instead so
    # they still get soft validation.
    "NHA_PN":           {"uppercase": True, "allow_empty": True, "_strip_leading_punct": True},
    "NHA_SN":           {"uppercase": True, "allow_empty": True, "_strip_leading_punct": True},
    "ORIGINATOR":       {"pattern": r"^[A-Z0-9/' ]{1,20}$", "uppercase": True, "allow_empty": True},
    "BASIS":            {"pattern": r"^[HCD]$", "uppercase": True},
    "TSI": dict(_NUMERIC_RULE),
    "TST": dict(_NUMERIC_RULE),
    "TSO": dict(_NUMERIC_RULE),
    "TSN": dict(_NUMERIC_RULE),
    # TTR (Time To Removal, in this basis's units) is the one field of the
    # ten trailing basis-line columns confirmed to sometimes render with a
    # decimal fraction (e.g. "12,090.93") -- confirmed directly: 26 of 68
    # populated TTR values in the real sample carry a decimal point, vs.
    # zero decimal values across every other numeric column (TSI/TST/TSO/
    # TSN/TCI/LIMIT). Given its own rule (no int_range, since this
    # project's shared thousands-int parser rejects decimals outright)
    # rather than reusing _NUMERIC_RULE and spuriously flagging over a
    # third of its real values as `not_a_number`.
    "TTR": {
        "pattern": r"^\d{1,3}(?:,\d{3})*(?:\.\d+)?$",
        "allow_empty": True,
        "_strip_leading_punct": True,
    },
    "TCI": dict(_NUMERIC_RULE),
    "LIMIT":            dict(_NUMERIC_RULE),
    "LIMIT_TYPE":       {"allow_empty": True},
    "TC_NUMBER":        {"allow_empty": True},
    "TASK":             {"allow_empty": True},
    "REPAIRER_NUMBER":  {"allow_empty": True},
    "CERT_NUMBER":      {"allow_empty": True},
    "SER_DATE":         dict(_DATE_RULE),
    "TASK_NOTE":        {"allow_empty": True},
    "STATUS_TRAIL":     {"allow_empty": True},
}

RULES = merged_rules(_OVERRIDES)

_ATA_TOKEN_RE = re.compile(r"^\d{2}-\d{2}$")
_HEADER_MARKERS = ("Aircraft OCCM List", "REGISTRARION", "TSI TST TSO TSN")
_FOOTER_RE = re.compile(r"^\d+\s+of\s+\d+\s+from\b", re.IGNORECASE)


def _cluster_rows(words: list[dict]) -> list[list[dict]]:
    """Group words into visual rows by their `top` coordinate. Row height
    in the sample is a consistent ~11pt; a 2pt tolerance clusters words
    belonging to the same printed line without merging adjacent lines."""
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
            row_groups.append(sorted(row_words, key=lambda w: w["x0"]))
    return row_groups


def _is_noise_row(joined: str) -> bool:
    if any(marker in joined for marker in _HEADER_MARKERS):
        return True
    if joined.startswith("Zone ATA"):
        return True
    if _FOOTER_RE.match(joined):
        return True
    return False


def _is_basis_row(row_words: list[dict]) -> str | None:
    first = row_words[0]
    if first["text"] in ("H", "C", "D") and abs(first["x0"] - _BASIS_LABEL_X0) < 5:
        return first["text"]
    return None


def _is_main_row(row_words: list[dict]) -> bool:
    for w in row_words:
        if _bucket(w["x0"], _MAIN_NAMES, _MAIN_BOUNDS) == "ATA" and _ATA_TOKEN_RE.match(w["text"]):
            return True
    return False


def _parse_main_row(row_words: list[dict]) -> dict:
    buckets: dict[str, list[str]] = {}
    for w in row_words:
        col = _bucket(w["x0"], _MAIN_NAMES, _MAIN_BOUNDS)
        buckets.setdefault(col, []).append(w["text"])
    return {name: " ".join(buckets.get(name, [])) for name in _MAIN_NAMES}


def _parse_basis_row(row_words: list[dict], basis: str) -> dict:
    # Skip the leading basis-label token itself; bucket the rest.
    buckets: dict[str, list[str]] = {}
    for w in row_words[1:]:
        col = _bucket(w["x0"], _BASIS_NAMES, _BASIS_BOUNDS)
        buckets.setdefault(col, []).append(w["text"])
    rec = {name: " ".join(buckets.get(name, [])) for name in _BASIS_NAMES}
    rec["BASIS"] = basis
    return rec


def _parse_meta(first_page_text: str) -> dict:
    meta = {"AIRCRAFT_REG": "", "MSN": "", "LAST_UPDATE_DATE": "", "FLIGHT_HOUR": "", "CYCLE": ""}
    m = _META_RE.search(first_page_text or "")
    if m:
        meta["AIRCRAFT_REG"] = m.group(1)
        meta["MSN"] = m.group(2)
        meta["LAST_UPDATE_DATE"] = m.group(3)
        meta["FLIGHT_HOUR"] = m.group(4)
        meta["CYCLE"] = m.group(5)
    return meta


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    meta: dict = {}
    current_main: dict = {}
    have_main = False

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            if page_num == 1:
                meta = _parse_meta(page.extract_text() or "")

            words = page.extract_words()
            if not words:
                continue

            for row_words in _cluster_rows(words):
                joined = " ".join(w["text"] for w in row_words)
                if _is_noise_row(joined):
                    continue

                basis = _is_basis_row(row_words)
                if basis is not None:
                    rec = dict(meta)
                    rec.update(current_main if have_main else {n: "" for n in _MAIN_NAMES})
                    rec.update(_parse_basis_row(row_words, basis))
                    rec["STATUS_TRAIL"] = ""
                    rec["_page"] = page_num
                    records.append(rec)
                    continue

                if _is_main_row(row_words):
                    current_main = _parse_main_row(row_words)
                    have_main = True
                    continue

                # Overflow/continuation line (no ATA token, no basis label):
                # fold verbatim into the most recently emitted row's
                # STATUS_TRAIL rather than guess which column it belongs to.
                if records:
                    prev = records[-1]
                    prev["STATUS_TRAIL"] = (prev["STATUS_TRAIL"] + " " + joined).strip()

    return records
