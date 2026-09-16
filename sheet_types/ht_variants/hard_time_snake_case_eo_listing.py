"""Born-digital HT export whose own column-header row prints literal
snake_case field labels ("eo ata_chapter pn sn pn_description
installed_position installed_date actual_hours actual_cycles Task
Requirement schedule_hours schedule_cycles schedule_days due_date
due_at_hours due_at_cycles remain_hours remain_minutes remain_cycles
remain_days nha_pn nha_sn") -- confirmed directly via pdfplumber on the
real sample file: full extractable text layer on every page, no OCR
needed. Same snake_case-header-label convention as this project's
`occm_variants/occm_list_pn_description_rotated_scanned.py` sibling (that
module's own docstring calls this phrasing "an unusual enough phrasing ...
this package's other OCCM variants all use plain-English or all-caps
header phrases, never an underscore-joined header label") -- same source
MIS vendor family, OCCM side there (scanned/rotated), HT side here
(born-digital, upright). Different report, different column set, no
shared parser; confirmed no SIGNATURES collision between the two (that
module's own SIGNATURES list is deliberately empty -- scanned-only,
detected via its own `ocr_detect()` -- so there is nothing to collide
with here even in principle).

Header block (repeats verbatim at the top of every page)::

    <operator wordmark -- confirmed to render with a broken font
     encoding/substituted glyphs on at least one page of the real sample
     file, garbling a couple of characters; the wordmark itself carries no
     tracked data and is not read by this module>
    Components <sep> Hard Time Components <sep> Aircraft
    A/C-Reg: <tail>  AC-Model: <type>  MSN: <msn>
    Current Aircraft Hours: <hh:mm>  Current Aircraft Date: <dd-mm-yyyy>
    Current Aircraft Cycles: <n>
    Statement :
    eo ata_chapter pn sn pn_description installed_position installed_date
    actual_hours actual_cycles Task Requirement schedule_hours
    schedule_cycles schedule_days due_date due_at_hours due_at_cycles
    remain_hours remain_minutes remain_cycles remain_days nha_pn nha_sn

Row grain: one row per tracked hard-time requirement. A component with
more than one applicable task (e.g. a functional check AND a restoration)
prints once per task, each its own row -- confirmed directly, e.g. a
single valve serial number recurs across three rows in the real sample
file, one with an empty `TASK_REQUIREMENT` (the component's own overall
next-due summary line, `EO` printing the literal token "TSO" rather than a
task/EO reference) and two with a populated `TASK_REQUIREMENT` (one row
per named task). `EO` is free text throughout -- confirmed directly to
carry several unrelated shapes across the sample file (the literal token
"TSO", numeric task-number-shaped values, an "AC-<n>EO-<n>" shaped value,
and short free-text labels for non-serialized consumable-style items) with
no single consistent pattern, so it is captured verbatim rather than
pattern-validated.

Columns, left to right::

    EO | ATA_CHAPTER | PN | SN | PN_DESCRIPTION | INSTALLED_POSITION |
    INSTALLED_DATE | ACTUAL_HOURS | ACTUAL_CYCLES | TASK_REQUIREMENT |
    SCHEDULE_HOURS | SCHEDULE_CYCLES | SCHEDULE_DAYS | DUE_DATE |
    DUE_AT_HOURS | DUE_AT_CYCLES | REMAIN_HOURS | REMAIN_MINUTES |
    REMAIN_CYCLES | REMAIN_DAYS | NHA_PN | NHA_SN

PN/SN/INSTALLED_DATE/ACTUAL_HOURS/ACTUAL_CYCLES/SCHEDULE_*/DUE_*/REMAIN_*
are blank together on a small minority of rows in the real sample file --
confirmed directly, these are consumable-style items (e.g. a fire-
extinguisher squib) tracked only by a discard interval/date with no
serialized PN/SN or accumulated-hours history captured in this export, not
a parsing gap. TASK_REQUIREMENT is blank on close to a third of rows --
confirmed directly, these are a component's own overall next-due summary
row rather than a named task. NHA_PN/NHA_SN (next-higher-assembly part/
serial) are populated on only a handful of rows in the real sample file --
confirmed directly, most tracked items have no separately-recorded parent
assembly in this export. All of the above are `allow_empty` accordingly.

Column assignment is by nearest-preceding-header-x snapping (confirmed
directly via `extract_words()`: each header label's own x0 repeats
identically across every page, and every data word's x0 sits at or after
its own column's header x and strictly before the next column's, even for
the widest observed values in each free-text column -- e.g. the widest
`PN_DESCRIPTION` value seen across the whole sample file, "MAIN LANDING
GEAR, COMPLETE (LT)", never approaches `INSTALLED_POSITION`'s own header
x, and the widest `TASK_REQUIREMENT` value, "SPECIAL DETAILED INSPECTION",
never approaches `SCHEDULE_HOURS`'s own header x).

Two confirmed rendering quirks, both handled below rather than guessed
around:

1. A small number of rows have their own `PN_DESCRIPTION` fragment (or,
   on wrapped multi-word descriptions, an entire second physical line of
   it) rendered a couple of points above or below the rest of that same
   logical row -- confirmed directly, the vertical gap between such a
   fragment and its own row's other fields is a fraction of the ~6.5pt
   gap between two consecutive genuine rows. The same top-tolerance
   physical-line grouping this project's other coordinate-based HT
   variants use (e.g. `hard_time_component_list.py`) merges these back
   into one row correctly without needing special-case row-continuation
   logic, and is not close enough to the real row-to-row gap to ever
   merge two genuinely different rows.

2. `NHA_PN` and `NHA_SN` are rendered immediately adjacent with no space
   character between them on every row where both are populated in the
   real sample file (e.g. a PN "201581001" directly followed by an SN
   "MDL2447" with no separating glyph) -- confirmed directly at the
   character level: the gap between the last character of `NHA_PN` and
   the first of `NHA_SN` is small enough that `extract_words()`'s default
   tolerance merges them into one token, while the same gap is
   confirmed, by direct measurement, to be several times wider than the
   gap between two characters genuinely inside one value and comfortably
   narrower than a real inter-column gap elsewhere on the row -- so a
   reduced `x_tolerance` on the whole-page `extract_words()` call (below
   the confirmed `NHA_PN`/`NHA_SN` boundary gap, but still above every
   genuine intra-value character gap and every genuine inter-word space
   width measured elsewhere in the file) reliably splits the two values
   at their true header-x boundary -- not a guessed field split, a
   character-gap-measured one, and it is applied globally to every column
   rather than special-cased to this one field pair since it is confirmed
   not to affect any other column's own word grouping.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.ht_variants._base import merged_rules
from shared.cleanup import normalize_dashes

NAME = "Hard Time Snake-Case EO Listing"
SIGNATURES = [
    # The full column-header line, verbatim. Checked against every
    # SIGNATURES list in occm.py/ht.py/llp.py and every existing
    # occm_variants/ht_variants/llp_variants module (including a plain
    # grep for "ata_chapter", "installed_position", "pn_description",
    # "nha_pn", "schedule_hours" and "remain_minutes"); no collision
    # found. The nearest look-alike, occm_variants/
    # occm_list_pn_description_rotated_scanned.py, shares this same
    # snake_case-header-label convention (same source MIS vendor family)
    # but a different column set and a deliberately empty SIGNATURES list
    # of its own (that module is scanned-only, detected via its own
    # ocr_detect() instead), so there is nothing to collide with there.
    "EO ATA_CHAPTER PN SN PN_DESCRIPTION INSTALLED_POSITION INSTALLED_DATE "
    "ACTUAL_HOURS ACTUAL_CYCLES TASK REQUIREMENT SCHEDULE_HOURS "
    "SCHEDULE_CYCLES SCHEDULE_DAYS DUE_DATE DUE_AT_HOURS DUE_AT_CYCLES "
    "REMAIN_HOURS REMAIN_MINUTES REMAIN_CYCLES REMAIN_DAYS NHA_PN NHA_SN",
]

CANONICAL_COLUMNS = [
    "EO",
    "ATA_CHAPTER",
    "PN",
    "SN",
    "PN_DESCRIPTION",
    "INSTALLED_POSITION",
    "INSTALLED_DATE",
    "ACTUAL_HOURS",
    "ACTUAL_CYCLES",
    "TASK_REQUIREMENT",
    "SCHEDULE_HOURS",
    "SCHEDULE_CYCLES",
    "SCHEDULE_DAYS",
    "DUE_DATE",
    "DUE_AT_HOURS",
    "DUE_AT_CYCLES",
    "REMAIN_HOURS",
    "REMAIN_MINUTES",
    "REMAIN_CYCLES",
    "REMAIN_DAYS",
    "NHA_PN",
    "NHA_SN",
    # Header metadata -- same on every row of a given file.
    "AC_REG",
    "AC_MODEL",
    "MSN",
    "CURRENT_AC_HOURS",
    "CURRENT_AC_DATE",
    "CURRENT_AC_CYCLES",
]

_DATE_RE = r"^\d{2}/\d{2}/\d{4}$"
_NUM_RE = r"^-?[\d,]+$"

_OVERRIDES = {
    "EO":                  {"allow_empty": True},
    "ATA_CHAPTER":         {"pattern": r"^\d{1,2}$"},
    "PN":                  {"allow_empty": True},
    "SN":                  {"allow_empty": True},
    "PN_DESCRIPTION":      {"allow_empty": True},
    "INSTALLED_POSITION":  {"allow_empty": True},
    "INSTALLED_DATE":      {"pattern": _DATE_RE, "allow_empty": True},
    "ACTUAL_HOURS":        {"pattern": _NUM_RE, "allow_empty": True},
    "ACTUAL_CYCLES":       {"pattern": _NUM_RE, "allow_empty": True},
    "TASK_REQUIREMENT":    {"allow_empty": True},
    "SCHEDULE_HOURS":      {"pattern": _NUM_RE, "allow_empty": True},
    "SCHEDULE_CYCLES":     {"pattern": _NUM_RE, "allow_empty": True},
    "SCHEDULE_DAYS":       {"pattern": _NUM_RE, "allow_empty": True},
    "DUE_DATE":            {"pattern": _DATE_RE, "allow_empty": True},
    "DUE_AT_HOURS":        {"pattern": _NUM_RE, "allow_empty": True},
    "DUE_AT_CYCLES":       {"pattern": _NUM_RE, "allow_empty": True},
    "REMAIN_HOURS":        {"pattern": _NUM_RE, "allow_empty": True},
    "REMAIN_MINUTES":      {"pattern": _NUM_RE, "allow_empty": True},
    "REMAIN_CYCLES":       {"pattern": _NUM_RE, "allow_empty": True},
    "REMAIN_DAYS":         {"pattern": _NUM_RE, "allow_empty": True},
    "NHA_PN":              {"allow_empty": True},
    "NHA_SN":              {"allow_empty": True},
    "AC_REG":              {"pattern": r"^[A-Z0-9\-]+$", "uppercase": True,
                             "allow_empty": True},
    "AC_MODEL":            {"allow_empty": True},
    "MSN":                 {"pattern": r"^[A-Z0-9]+$", "uppercase": True,
                             "allow_empty": True},
    "CURRENT_AC_HOURS":    {"allow_empty": True},
    "CURRENT_AC_DATE":     {"pattern": r"^\d{2}-\d{2}-\d{4}$", "allow_empty": True},
    "CURRENT_AC_CYCLES":   {"pattern": _NUM_RE, "allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Left edges (PDF points) of each column, taken directly from the header
# row's own word x0 positions on the real sample file (repeats
# identically across every page). Each data word is assigned to the
# right-most column whose own header x is <= the word's own x0 -- never a
# fixed left-to-right token count, so a multi-word free-text value (e.g.
# PN_DESCRIPTION, TASK_REQUIREMENT, INSTALLED_POSITION) is captured
# correctly regardless of how many words it spans.
_FIELDS = [
    "EO", "ATA_CHAPTER", "PN", "SN", "PN_DESCRIPTION", "INSTALLED_POSITION",
    "INSTALLED_DATE", "ACTUAL_HOURS", "ACTUAL_CYCLES", "TASK_REQUIREMENT",
    "SCHEDULE_HOURS", "SCHEDULE_CYCLES", "SCHEDULE_DAYS", "DUE_DATE",
    "DUE_AT_HOURS", "DUE_AT_CYCLES", "REMAIN_HOURS", "REMAIN_MINUTES",
    "REMAIN_CYCLES", "REMAIN_DAYS", "NHA_PN", "NHA_SN",
]
_FIELD_X = [
    24.8, 68.9, 98.3, 137.3, 174.4, 262.7,
    299.9, 341.6, 371.6, 404.3,
    451.6, 489.3, 522.9, 563.1,
    595.5, 626.6, 660.5, 690.0,
    724.7, 754.9, 783.2, 801.1,
]

# Reduced word-join tolerance (default `extract_words()` tolerance merges
# NHA_PN directly into NHA_SN on every row where both are populated --
# see module docstring point 2 -- while this value stays comfortably
# above every genuine intra-value character gap and inter-word space
# width measured elsewhere in the file).
_X_TOLERANCE = 1.5

_ATA_RE = re.compile(r"^\d{1,2}$")
_PAGE_FOOTER_RE = re.compile(r"^Page\s+\d+\s+of\s+\d+$")

_META_RE = {
    "AC_REG":            re.compile(r"A/C-Reg:\s*(\S+)"),
    "AC_MODEL":          re.compile(r"AC-Model:\s*(\S+)"),
    "MSN":               re.compile(r"\bMSN:\s*(\S+)"),
    "CURRENT_AC_HOURS":  re.compile(r"Current Aircraft Hours:\s*(\S+)"),
    "CURRENT_AC_DATE":   re.compile(r"Current Aircraft Date:\s*(\S+)"),
    "CURRENT_AC_CYCLES": re.compile(r"Current Aircraft Cycles:\s*(\S+)"),
}


def _field_for_x(x0: float) -> str:
    best_i = 0
    for i, fx in enumerate(_FIELD_X):
        if fx <= x0 + 0.5:
            best_i = i
        else:
            break
    return _FIELDS[best_i]


def _group_lines(words: list[dict]) -> list[dict]:
    ws = sorted(words, key=lambda w: (w["top"], w["x0"]))
    lines: list[dict] = []
    for w in ws:
        if lines and abs(w["top"] - lines[-1]["top"]) <= 2.5:
            lines[-1]["words"].append(w)
            lines[-1]["top"] = (lines[-1]["top"] + w["top"]) / 2
        else:
            lines.append({"top": w["top"], "words": [w]})
    for line in lines:
        line["words"].sort(key=lambda w: w["x0"])
    return lines


def _row_from_line(line: dict) -> dict:
    row = {col: "" for col in CANONICAL_COLUMNS}
    buckets: dict[str, list[str]] = {f: [] for f in _FIELDS}
    for w in line["words"]:
        buckets[_field_for_x(w["x0"])].append(w["text"])
    for field, toks in buckets.items():
        row[field] = " ".join(toks)
    return row


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    meta = {k: "" for k in _META_RE}

    with pdfplumber.open(pdf_path) as pdf:
        if pdf.pages:
            head_text = normalize_dashes(pdf.pages[0].extract_text() or "")
            head_text = head_text.split("Statement")[0]
            for field, rx in _META_RE.items():
                m = rx.search(head_text)
                if m:
                    meta[field] = m.group(1)

        for page_num, page in enumerate(pdf.pages, start=1):
            words = page.extract_words(use_text_flow=False,
                                        keep_blank_chars=False,
                                        x_tolerance=_X_TOLERANCE)
            if not words:
                continue
            for w in words:
                w["text"] = normalize_dashes(w["text"])
            lines = _group_lines(words)

            for line in lines:
                ata_text = " ".join(
                    w["text"] for w in line["words"]
                    if 46.9 <= w["x0"] < 83.6
                )
                if _PAGE_FOOTER_RE.match(" ".join(w["text"] for w in line["words"])):
                    continue
                if not _ATA_RE.match(ata_text):
                    # Not a recognisable data row (aircraft-info header
                    # line, breadcrumb, "Statement :" label, or stray page
                    # furniture) -- skip rather than force it into a row.
                    continue
                row = _row_from_line(line)
                row["_page"] = page_num
                row.update(meta)
                records.append(row)

    return records
