"""Maintenance Status Report (Report ERM1) variant.

Format produced by an "Aircraft Inventory and Maintenance System" export
whose header reads:

    <date> <operator name> - <job title/department>  Page <n>
    Aircraft Inventory and Maintenance System
    MAINTENANCE STATUS REPORT Report ERM1
    AIRCRAFT: <reg>
    - TYPE/MODEL: <type> - S/N: <msn> -
    SORTED BY ATA CODE (ALL ITEMS) INCLUDES: - PARTS - AS OF <date>
    A/C HRS: <n> LANDINGS: <n> LANDINGS/MONTH: <n> HRS/LANDING: <n>

This is a sibling report ID from the same MIS export family as
occm_variants/maintenance_status_report_pr21.py (same header boilerplate,
same "Aircraft Inventory and Maintenance System" product name) but ERM1 is
the Hard-Time-flavoured template: every task row carries a Hard-Time-style
EVERY/LIFE LEFT/LAST DONE/NEXT DUE interval (calendar-months or flight-hours
based, never the PR21 sheet's C/M / O/C on-condition task codes). Confirmed
via direct pdfplumber inspection of a real sample: this file has a genuine
text layer (no OCR needed) and the header repeats verbatim on every page. A
dashed rule line (a run of `-` characters) always separates the repeated
header block from that page's data rows, same convention as PR21.

Column layout (confirmed by direct word-position inspection -- the header
prints across three physical lines, but resolves to one fixed set of column
x-positions reused by every data row):

    ATA CODE | STOCK # | PART #/SERIAL #/POS DESCRIPTION | TASKS OR REQUIRED
    EVERY | LIFE LEFT | LAST DONE (LOG REF) | TSN/TSO HOURS |
    AC H/C/D LANDINGS | NEXT DUE DATE

`STOCK #` is a declared column that never carries a value in the sample
file (its x-position is always blank on the data rows) -- kept as an
always-empty CANONICAL_COLUMNS entry rather than dropped, in case another
export from this template does populate it.

Row layout: each *component* (identified by ATA + PART_NUMBER) spans two or
more physical text lines that repeat per task:

    Numeric line: [ATA PART_NUMBER DESCRIPTION | TASK_NAME] EVERY LIFE_LEFT
        LAST_DONE TSN_HOURS LANDINGS NEXT_DUE
    Label line:   [SERIAL_NUMBER POSITION TASK_NAME | (nothing)]
        LIFE_LEFT_SECONDARY LOG_REF

Only the FIRST task of a component prints DESCRIPTION on its numeric line
(crowding TASK_NAME onto that task's label line, alongside SERIAL_NUMBER
and POSITION); every later task of the same component has a free
DESCRIPTION slot on its own numeric line, so TASK_NAME prints there
directly and its label line is just LIFE_LEFT_SECONDARY + LOG_REF. This
project's convention is column position, not fixed token order, so which
line "TASK_NAME" appears on is resolved generically: whichever of the two
lines does not already hold DESCRIPTION. ATA/PART_NUMBER/SERIAL_NUMBER/
POSITION/DESCRIPTION are component-level identity fields, parsed once per
component and stamped on every one of that component's task rows.

EVERY / LIFE_LEFT / LAST_DONE are each printed as either a calendar value
(a bare date for LAST_DONE, months for EVERY/LIFE_LEFT, unit "MOS") or an
hours-based value (a number + "HRS" for all three) depending on the task's
own basis -- confirmed by direct inspection, both bases appear in the real
sample. Per this project's "never guess a wrong split" convention, these
fields are kept as whatever raw text falls in their column (value, or
value+unit, or a date) rather than forcing one shape; no pattern rule is
applied to them so a legitimate value in either basis is never flagged.

LIFE_LEFT prints twice per task -- once on the numeric line, once again
(a different figure) on the label line directly below it. Both are kept,
as LIFE_LEFT and LIFE_LEFT_SECONDARY, without asserting what the second
figure specifically represents (not documented in the source report
itself) -- this mirrors PR21's STATUS_TRAIL convention of keeping
ambiguous secondary data verbatim rather than guessing its meaning.

POSITION is kept as a raw, unsplit span, same convention as PR21 -- it can
hold a bare side code (e.g. a two-letter side marker) or a side code plus
an inline position/zone marker, and there's no reliable way to tell which
sub-meaning applies token-by-token.

Header metadata (REPORT_DATE, AIRCRAFT_REG, AIRCRAFT_TYPE, MSN, AS_OF_DATE)
is parsed once from the header block (same regexes as PR21, same header
boilerplate) and stamped on every row. The first page of the real sample
lacks the "- TYPE/MODEL: ... - S/N: ... -" line (a summary/emergency-parts
sub-heading prints there instead on page 1 only) -- AIRCRAFT_TYPE/MSN are
simply blank on any row flushed before that line is first seen, matching
this project's existing convention for the same situation elsewhere
(records are stamped with whatever metadata is known AT FLUSH TIME, never
retroactively backfilled).
"""
from __future__ import annotations
import re
import pdfplumber
from collections import defaultdict

from sheet_types.ht_variants._base import merged_rules

NAME = "Maintenance Status Report (ERM1)"
SIGNATURES = [
    "MAINTENANCE STATUS REPORT Report ERM1",
]

CANONICAL_COLUMNS = [
    "ATA",
    "STOCK_NUMBER",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "POSITION",
    "DESCRIPTION",
    "TASK",
    "EVERY",
    "LIFE_LEFT",
    "LIFE_LEFT_SECONDARY",
    "LAST_DONE",
    "TSN_HOURS",
    "LANDINGS",
    "NEXT_DUE",
    "LOG_REF",
    "AIRCRAFT_REG",
    "AIRCRAFT_TYPE",
    "MSN",
    "REPORT_DATE",
    "AS_OF_DATE",
]

_OVERRIDES = {
    # Full ATA chapter-section-subject code (e.g. "25-03-00"), not the
    # bare 2-digit chapter the global default expects -- disable the
    # global int_range too, same as PR21's own ATA override.
    "ATA": {"pattern": r"^\d{2}-\d{2}-\d{2}$", "int_range": None, "uppercase": True},
    # POSITION is deliberately kept as a raw, unsplit span (see module
    # docstring) -- permissive pattern, not asserting a specific shape.
    "POSITION": {"pattern": r"^.+$", "uppercase": True},
    "TASK": {"uppercase": True},
    "LOG_REF": {"pattern": r"^\(.*\)$", "allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_DASH_LINE_RE = re.compile(r"^-{10,}$")

# Column x0 boundaries in points, half-open [lo, hi) -- confirmed by direct
# word-position inspection of the real sample (see module docstring).
_COL_BOUNDS = [
    ("ATA", 55, 100),
    ("PART_SERIAL", 110, 140),
    ("POS", 140, 218),
    ("DESC_TASK", 218, 373),
    ("EVERY", 373, 425),
    ("LIFE", 430, 490),
    ("LASTDONE_OR_LOGREF", 490, 560),
    ("TSN_HOURS", 560, 605),
    ("LANDINGS", 605, 650),
    ("NEXTDUE", 650, 720),
]

_REPORT_DATE_RE = re.compile(r"^([A-Za-z]+ \d{1,2},\s*\d{4})\b")
_AIRCRAFT_REG_RE = re.compile(r"AIRCRAFT:\s*(\S+)")
_TYPE_MSN_RE = re.compile(r"TYPE/MODEL:\s*(\S+)\s*-\s*S/N:\s*(\S+)")
_AS_OF_RE = re.compile(r"AS OF\s*(\d{2}/\d{2}/\d{4})")


def _bucket_row(words: list) -> dict:
    out: dict = defaultdict(list)
    for w in sorted(words, key=lambda w: w["x0"]):
        for name, lo, hi in _COL_BOUNDS:
            if lo <= w["x0"] < hi:
                out[name].append(w["text"])
                break
    return {k: " ".join(v) for k, v in out.items()}


def _parse_header(head_text: str) -> dict:
    meta = {
        "REPORT_DATE": "",
        "AIRCRAFT_REG": "",
        "AIRCRAFT_TYPE": "",
        "MSN": "",
        "AS_OF_DATE": "",
    }
    m = _REPORT_DATE_RE.search(head_text)
    if m:
        meta["REPORT_DATE"] = m.group(1)
    m = _AIRCRAFT_REG_RE.search(head_text)
    if m:
        meta["AIRCRAFT_REG"] = m.group(1)
    m = _TYPE_MSN_RE.search(head_text)
    if m:
        meta["AIRCRAFT_TYPE"] = m.group(1)
        meta["MSN"] = m.group(2)
    m = _AS_OF_RE.search(head_text)
    if m:
        meta["AS_OF_DATE"] = m.group(1)
    return meta


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    meta = {
        "REPORT_DATE": "",
        "AIRCRAFT_REG": "",
        "AIRCRAFT_TYPE": "",
        "MSN": "",
        "AS_OF_DATE": "",
    }

    component: dict | None = None
    current: dict | None = None

    def flush():
        nonlocal current
        if current is not None and component is not None:
            rec = dict(component)
            rec.update(current)
            rec.update(meta)
            records.append(rec)
        current = None

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            words = page.extract_words()
            if not words:
                continue

            if not meta["AIRCRAFT_REG"] or not meta["AIRCRAFT_TYPE"]:
                parsed = _parse_header(page.extract_text() or "")
                for k, v in parsed.items():
                    if v and not meta[k]:
                        meta[k] = v

            rows: dict = defaultdict(list)
            for w in words:
                rows[round(w["top"], 1)].append(w)
            tops = sorted(rows.keys())

            divider_idx = None
            for i, t in enumerate(tops):
                row_words = rows[t]
                if len(row_words) == 1 and _DASH_LINE_RE.match(row_words[0]["text"]):
                    divider_idx = i
                    break
            if divider_idx is None:
                # No table body on this page (e.g. a stray cover/summary
                # page) -- header metadata was still scanned above.
                continue

            for t in tops[divider_idx + 1:]:
                cols = _bucket_row(rows[t])
                has_every = bool(cols.get("EVERY"))
                has_ata = bool(cols.get("ATA"))
                has_part_serial = bool(cols.get("PART_SERIAL"))

                if has_every:
                    # Numeric line -- starts a new task, so the previous
                    # pending task (if any) is now complete.
                    flush()
                    if has_ata:
                        component = {
                            "ATA": cols.get("ATA", ""),
                            "STOCK_NUMBER": "",
                            "PART_NUMBER": cols.get("PART_SERIAL", ""),
                            "SERIAL_NUMBER": "",
                            "POSITION": "",
                            "DESCRIPTION": cols.get("DESC_TASK", ""),
                        }
                        task_name = ""
                    else:
                        if component is None:
                            # Stray numeric line before any component was
                            # seen (shouldn't happen on a well-formed page,
                            # but don't guess a component identity if it
                            # does) -- skip rather than fabricate.
                            continue
                        task_name = cols.get("DESC_TASK", "")
                    current = {
                        "TASK": task_name,
                        "EVERY": cols.get("EVERY", ""),
                        "LIFE_LEFT": cols.get("LIFE", ""),
                        "LIFE_LEFT_SECONDARY": "",
                        "LAST_DONE": cols.get("LASTDONE_OR_LOGREF", ""),
                        "TSN_HOURS": cols.get("TSN_HOURS", ""),
                        "LANDINGS": cols.get("LANDINGS", ""),
                        "NEXT_DUE": cols.get("NEXTDUE", ""),
                        "LOG_REF": "",
                        "_page": page_num,
                    }
                    continue

                # Label line -- fills in the pending task's secondary data,
                # and (only for a component's first task) its SERIAL_NUMBER/
                # POSITION/TASK_NAME.
                if has_part_serial and component is not None:
                    component["SERIAL_NUMBER"] = cols.get("PART_SERIAL", "")
                    component["POSITION"] = cols.get("POS", "")
                    if current is not None and cols.get("DESC_TASK"):
                        current["TASK"] = cols.get("DESC_TASK", "")

                if current is not None:
                    if cols.get("LIFE"):
                        current["LIFE_LEFT_SECONDARY"] = cols["LIFE"]
                    if cols.get("LASTDONE_OR_LOGREF"):
                        current["LOG_REF"] = cols["LASTDONE_OR_LOGREF"]

            # Deliberately no per-page flush: a component's task list can
            # continue past a page break with no repeated header line, so
            # `current`/`component` carry over to the next page's loop.

    flush()
    return records
