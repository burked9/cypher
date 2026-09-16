"""HARD TIME STATUS -- born-digital, full text layer, coordinate-bucketed
columns (confirmed directly via a `extract_words()` pass over the real
sample file: every page repeats the same fixed header block and every row's
tokens sit at consistent x-positions).

This is a different template from this project's other "Hard Time ..."
family: its own title line is the exact phrase "HARD TIME STATUS" and its
own header block carries "TSN:"/"CSN:"/"As of :"/"Reg.:"/"MSN:" labels
(all on the right side of the title, one per line) plus a four-line column
header ("Reference Maint Process / PART TIME INFO", "Qty Per / MPD /
Maint / Limiter", "ATADescription / Maint Manual / Type / Task / Position
/ P/N / S/N / Installed on / Last Interval / TSO/DSO / Remainning",
"Aircraft / Task Card / Frequency / Type") repeated verbatim at the top of
every page -- not a shared parser with any other HT variant in this
project (checked directly).

Header block (repeats verbatim at the top of every page)::

    HARD TIME STATUS                    TSN: <n>
                                         CSN: <n>
                                         As of : <dd.mm.yyyy>
                                         Reg.: <tail>
                                         MSN: <msn>
    Reference Maint Process         PART            TIME INFO
    Qty Per   MPD    Maint          Limiter
    ATADescription Maint Manual Type Task Position P/N S/N Installed on
        Last Interval TSO/DSO Remainning
    Aircraft  Task Card  Frequency          Type

Row grain: one row per tracked component/position. Columns, left to
right::

    ATA | DESCRIPTION | QTY_PER_AIRCRAFT |
    MAINT_MANUAL_REF | MPD_TASK_CARD | TYPE_CODE | MAINT_PROCESS |
    FREQUENCY | POSITION | PART_NUMBER | SERIAL_NUMBER |
    INSTALLED_ON | LAST_INTERVAL | LIMITER_VALUE | EXTRA_NOTE |
    LIMITER_UNIT | TSO_DSO | REMAINING

Column assignment is done by fixed x0-threshold bucketing (confirmed
directly against the real sample: ATA, MAINT_MANUAL_REF, MPD_TASK_CARD
and INSTALLED_ON all sit at exact, unvarying x0 values on every single row
across every page; the remaining columns vary within a narrow band that
never overlaps a neighbouring column's own band anywhere in the sample).

Row wrapping: a meaningful minority of rows carry one or more additional
physical text lines below their main line -- either an extra
MAINT_MANUAL_REF/MPD_TASK_CARD value (a component tracked against more
than one MPD task), an extra word or two of MAINT_PROCESS ("... TEST" /
"... CHECK" wrapping separately from its own first word), or an extra
word of POSITION (e.g. a "LH"/"RH" sub-position wrapping under an
"ENG 1"/"ENG 2" main position). These continuation lines never carry
their own ATA token, so they're recognised by that absence and merged
into the immediately preceding row by bucketing the continuation line's
own words with the exact same x0 thresholds and appending (space-joined)
into whichever field(s) they land in -- never treated as new rows, and
never dropped. This also correctly reconstructs the rare multi-line
free-text note that a couple of rows carry in place of a numeric
LIMITER_VALUE (confirmed in the sample: the note's own words happen to
fall inside the LIMITER_VALUE x-band on every one of its wrapped lines,
so plain continuation-append already reassembles it word-for-word without
any note-specific handling).

A small number of rows carry a short administrative note instead of a
genuine POSITION/PART_NUMBER/SERIAL_NUMBER triple -- confirmed in the
sample, e.g. a note that a group of like components is "covered by" a
different, group-level MPD reference rather than individually tracked
(landing to the right of the normal POSITION/PN/SN column band and so
already captured whole into EXTRA_NOTE, not split), and a note that a
component's status is tracked on a companion report rather than this one
(this second phrasing starts with a two-word marker landing squarely
inside the POSITION column x-band, so a naive x-only bucketing would
split its remaining words wrongly across POSITION/PART_NUMBER/
SERIAL_NUMBER). That second phrasing is recognised by its own two-word
opening marker (an exact, case-sensitive substring match -- not a guess:
this project's "never force a wrong split on ambiguous data" rule) and,
when found, the row's full POSITION+PART_NUMBER+SERIAL_NUMBER span is
moved to EXTRA_NOTE as one string and those three fields are left blank
for that row instead.

No signature/authorisation footer block was found anywhere in the real
sample file (checked directly, every page, including the last) -- no
person's name appears in this template at all, so there's nothing to
scrub before data rows begin or end.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.ht_variants._base import merged_rules
from shared.cleanup import normalize_dashes

NAME = "Hard Time Status (ATA Reference)"
SIGNATURES = [
    # Checked against every SIGNATURES list in occm.py/ht.py/llp.py and
    # every occm_variants/ht_variants/llp_variants module's own SIGNATURES
    # list; no collision found. Not a substring of, and does not contain
    # as a substring, any other variant's own signature phrase.
    "HARD TIME STATUS",
]

CANONICAL_COLUMNS = [
    "ATA",
    "DESCRIPTION",
    "QTY_PER_AIRCRAFT",
    "MAINT_MANUAL_REF",
    "MPD_TASK_CARD",
    "TYPE_CODE",
    "MAINT_PROCESS",
    "FREQUENCY",
    "POSITION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "INSTALLED_ON",
    "LAST_INTERVAL",
    "LIMITER_VALUE",
    "EXTRA_NOTE",
    "LIMITER_UNIT",
    "TSO_DSO",
    "REMAINING",
    # Header metadata -- same on every row of a given file.
    "AC_TSN",
    "AC_CSN",
    "REPORT_DATE",
    "AC_REG",
    "AC_MSN",
]

_DATE_RE = r"^\d{2}\.\d{2}\.\d{4}$"
_NUM_RE = r"^[\d.,']+$"

_OVERRIDES = {
    "DESCRIPTION":       {"allow_empty": True},
    "QTY_PER_AIRCRAFT":  {"pattern": r"^\d+$", "allow_empty": True},
    "MAINT_MANUAL_REF":  {"allow_empty": True},
    "MPD_TASK_CARD":     {"allow_empty": True},
    "TYPE_CODE":         {"pattern": r"^HT$", "uppercase": True, "allow_empty": True},
    "MAINT_PROCESS":     {"allow_empty": True},
    "FREQUENCY":         {"allow_empty": True},
    "POSITION":          {"allow_empty": True},
    # PART_NUMBER/SERIAL_NUMBER inherit the strict global pattern from
    # GLOBAL_RULES -- override only to allow the many rows in this
    # template where a component genuinely has no individually tracked
    # PN/SN (e.g. a note routes it elsewhere -- see EXTRA_NOTE above).
    "PART_NUMBER":       {"allow_empty": True},
    "SERIAL_NUMBER":     {"allow_empty": True},
    "INSTALLED_ON":      {"pattern": _DATE_RE, "allow_empty": True},
    # LAST_INTERVAL holds a date on most rows but a bare numeric
    # aircraft-time reading on others (whichever basis the row's own
    # LIMITER_UNIT/TSO_DSO tracks against) -- deliberately no pattern so
    # neither basis is flagged against the other.
    "LAST_INTERVAL":     {"allow_empty": True},
    # LIMITER_VALUE holds a number on the vast majority of rows but very
    # occasionally a short free-text note instead (see module docstring)
    # -- deliberately no pattern for the same reason as LAST_INTERVAL.
    "LIMITER_VALUE":     {"allow_empty": True},
    "EXTRA_NOTE":        {"allow_empty": True},
    "LIMITER_UNIT":      {"pattern": r"^(DYS|FH|FC)$", "uppercase": True, "allow_empty": True},
    "TSO_DSO":           {"pattern": r"^(TSO|DSO|CSN)$", "uppercase": True, "allow_empty": True},
    "REMAINING":         {"pattern": _NUM_RE, "allow_empty": True},
    "AC_TSN":            {"pattern": _NUM_RE, "allow_empty": True},
    "AC_CSN":            {"pattern": _NUM_RE, "allow_empty": True},
    "REPORT_DATE":       {"pattern": _DATE_RE, "allow_empty": True},
    "AC_REG":            {"pattern": r"^[A-Z0-9\-]+$", "uppercase": True, "allow_empty": True},
    "AC_MSN":            {"pattern": r"^\d+$", "allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Fixed x0 (PDF points) column boundaries, derived directly from the real
# sample file's own word coordinates (see module docstring). Assignment is
# a simple "which band does this word's x0 fall in" -- no nearest-neighbour
# needed, because none of these bands ever overlap on the sample file.
_ATA_X = 63.0
_DESC_X = 168.0
_QTY_X = 192.0
_MMR_X = 225.0
_TASK_CARD_X = 270.0
_TYPE_X = 296.0
_PROCESS_X = 348.0
_FREQ_X = 385.0
_POSITION_X = 433.0
_PN_X = 475.0
_SN_X = 510.0
_INSTALLED_X = 562.0
_LAST_INT_X = 605.0
_LIMITER_VAL_X = 645.0
_EXTRA_X = 700.0
_UNIT_X = 712.0
_TSO_DSO_X = 722.0

_FIELD_ORDER = [
    ("ATA", _ATA_X),
    ("DESCRIPTION", _DESC_X),
    ("QTY_PER_AIRCRAFT", _QTY_X),
    ("MAINT_MANUAL_REF", _MMR_X),
    ("MPD_TASK_CARD", _TASK_CARD_X),
    ("TYPE_CODE", _TYPE_X),
    ("MAINT_PROCESS", _PROCESS_X),
    ("FREQUENCY", _FREQ_X),
    ("POSITION", _POSITION_X),
    ("PART_NUMBER", _PN_X),
    ("SERIAL_NUMBER", _SN_X),
    ("INSTALLED_ON", _INSTALLED_X),
    ("LAST_INTERVAL", _LAST_INT_X),
    ("LIMITER_VALUE", _LIMITER_VAL_X),
    ("EXTRA_NOTE", _EXTRA_X),
    ("LIMITER_UNIT", _UNIT_X),
    ("TSO_DSO", _TSO_DSO_X),
    ("REMAINING", float("inf")),
]


def _field_for_x0(x0: float) -> str:
    for name, upper in _FIELD_ORDER:
        if x0 < upper:
            return name
    return "REMAINING"


_HEADER_META_RE = re.compile(
    r"HARD\s+TIME\s+STATUS|TSN:|CSN:|As\s+of\s*:|Reg\.:|MSN:|"
    r"ATADescription|Reference\s+Maint\s+Process|Qty\s+Per|"
    r"Aircraft\s+Task\s+Card|Installed\s+on|TSO/DSO|Remainning"
)
_ATA_RE = re.compile(r"^\d{1,2}$")

# Two-word opening marker for the "tracked on a companion report" note --
# see module docstring. Exact substring match, not a guess.
_COMPANION_NOTE_RE = re.compile(r"\bPLEASE\s+SEE\b", re.IGNORECASE)

_META_RE = {
    "AC_TSN":      re.compile(r"TSN:\s*(\S+)"),
    "AC_CSN":      re.compile(r"CSN:\s*(\S+)"),
    "REPORT_DATE": re.compile(r"As\s+of\s*:\s*(\S+)"),
    "AC_REG":      re.compile(r"Reg\.:\s*(\S+)"),
    "AC_MSN":      re.compile(r"MSN:\s*(\S+)"),
}


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


def _line_text(line: dict) -> str:
    return " ".join(w["text"] for w in line["words"])


def _bucket_line(words: list[dict]) -> dict[str, str]:
    buckets: dict[str, list[str]] = {}
    for w in words:
        field = _field_for_x0(w["x0"])
        buckets.setdefault(field, []).append(w["text"])
    return {field: " ".join(toks) for field, toks in buckets.items()}


def _apply_companion_note_override(row: dict) -> None:
    combined = " ".join(
        row.get(f, "") for f in ("POSITION", "PART_NUMBER", "SERIAL_NUMBER")
    ).strip()
    if combined and _COMPANION_NOTE_RE.search(combined):
        existing_extra = row.get("EXTRA_NOTE", "")
        row["EXTRA_NOTE"] = (combined + " " + existing_extra).strip()
        row["POSITION"] = ""
        row["PART_NUMBER"] = ""
        row["SERIAL_NUMBER"] = ""


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    meta = {k: "" for k in _META_RE}

    with pdfplumber.open(pdf_path) as pdf:
        if pdf.pages:
            head_text = normalize_dashes(pdf.pages[0].extract_text() or "")
            for field, rx in _META_RE.items():
                m = rx.search(head_text)
                if m:
                    meta[field] = m.group(1)

        current_row: dict | None = None

        for page_num, page in enumerate(pdf.pages, start=1):
            words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
            if not words:
                continue
            for w in words:
                w["text"] = normalize_dashes(w["text"])
            lines = _group_lines(words)

            for line in lines:
                text = _line_text(line)
                if _HEADER_META_RE.search(text):
                    # Repeated header/meta boilerplate -- never a data row
                    # and never a continuation of one.
                    continue

                ata_text = " ".join(
                    w["text"] for w in line["words"] if w["x0"] < _ATA_X
                )
                bucketed = _bucket_line(line["words"])

                if _ATA_RE.match(ata_text) and bucketed.get("TYPE_CODE") == "HT":
                    # New data row.
                    row = {col: "" for col in CANONICAL_COLUMNS}
                    for field, val in bucketed.items():
                        if field in row:
                            row[field] = val
                    _apply_companion_note_override(row)
                    row["_page"] = page_num
                    row.update(meta)
                    records.append(row)
                    current_row = row
                elif current_row is not None:
                    # Continuation line (extra MPD reference, wrapped
                    # MAINT_PROCESS/POSITION word, or a wrapped multi-line
                    # LIMITER_VALUE note) -- merge into the previous row.
                    for field, val in bucketed.items():
                        if field not in CANONICAL_COLUMNS or not val:
                            continue
                        existing = current_row.get(field, "")
                        current_row[field] = (existing + " " + val).strip() if existing else val
                    _apply_companion_note_override(current_row)
                # else: stray line before any row has been seen -- skip.

    return records
