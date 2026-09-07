"""Maintenance Status Report (Report PR21) variant.

Format produced by an "Aircraft Inventory and Maintenance System" export
whose header reads:

    <date> <operator name> - <job title/department>  Page <n>
    Aircraft Inventory and Maintenance System
    MAINTENANCE STATUS REPORT Report PR21
    AIRCRAFT: <reg>
    - TYPE/MODEL: <type> - S/N: <msn> -
    SORTED BY ATA CODE (ALL ITEMS) INCLUDES: - PARTS- ON COND.- COND. MONITOR - AS OF <date>
    A/C HRS: <n> LANDINGS: <n> LANDINGS/MONTH: <n> HRS/LANDING: <n>

Confirmed via direct pdfplumber inspection of a real sample: this file has
a genuine text layer (no OCR needed) and the header repeats verbatim on
every page. A dashed rule line (a run of `-` characters) always separates
the repeated header block from that page's data rows, so it is used as the
per-page anchor between "header noise" and "table body" rather than trying
to match every possible header/sub-section line by name.

Some later pages in the sample replace the "- TYPE/MODEL: ... - S/N: ... -"
line with a component-group label instead (e.g. a landing-gear or engine
sub-inventory heading) — this doesn't matter here since AIRCRAFT_TYPE/MSN
are parsed once (from the first page that has them) and stamped on every
row, per this project's convention, rather than re-parsed per page.

Row layout (confirmed by direct inspection — each logical record spans two
or more physical text lines):

    Line 1: ATA  PART_NUMBER  DESCRIPTION...  TASK_CODE  LAST_DONE_VALUE
            LAST_DONE_UNIT  NEXT_DUE_VALUE  NEXT_DUE_UNIT
        e.g. `<ata> <pn> <description words> C/M <n> HRS <n> HRS`
        TASK_CODE is always literally `C/M` or `O/C`, used as the anchor to
        split PART_NUMBER/DESCRIPTION (before it) from the two LAST_DONE /
        NEXT_DUE value+unit pairs (after it). NEXT_DUE can be the literal
        `n/a` instead of a value+unit pair.
    Line 2 (always immediately follows): SERIAL_NUMBER  ...  (LOG_REF)
        e.g. `<sn> <position/task marker tokens> (<log ref>)`
        The trailing `(...)` token, if present, is LOG_REF. Everything
        between SERIAL_NUMBER and LOG_REF is kept as one raw POSITION
        field rather than split further: on the real file this middle
        span sometimes holds just a position code, sometimes a position
        plus an inline task-marker token (e.g. a repeated "since new"/
        "since overhaul" style marker), and there is no reliable way to
        tell which sub-meaning applies token-by-token — splitting it would
        risk a wrong guess, so per this project's convention it is kept
        whole instead.

    Additional lines (0 or more) may follow line 2 for the same component,
    each restating TASK_CODE with a different LAST_DONE/NEXT_DUE pair (an
    accumulated/alternate time basis for the same part — e.g. time-since-
    new vs. time-since-overhaul) or a single trailing `(<log ref>)` line on
    its own. These continuation lines don't carry their own PART_NUMBER/
    ATA/SERIAL_NUMBER, so rather than guess how to fold them into the
    primary row's columns, they are appended verbatim to STATUS_TRAIL.

A new record starts only when a line's first token is ATA-shaped (either
`-` or digits/optional dashes, e.g. `<ata>-<ata>-<ata>` or a truncated
`<ata>-<ata>-`) AND the line contains a TASK_CODE token. Anything else
between one such line and the next is treated as this record's line 2 (if
first) or STATUS_TRAIL continuation (otherwise).

Header metadata (REPORT_DATE, AIRCRAFT_REG, AIRCRAFT_TYPE, MSN, AS_OF_DATE)
is parsed once from the header block and stamped on every row.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "Maintenance Status Report (PR21)"
SIGNATURES = [
    "MAINTENANCE STATUS REPORT",
    "Aircraft Inventory and Maintenance System",
]

CANONICAL_COLUMNS = [
    "ATA",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
    "POSITION",
    "TASK_CODE",
    "LAST_DONE",
    "NEXT_DUE",
    "LOG_REF",
    "STATUS_TRAIL",
    "AIRCRAFT_REG",
    "AIRCRAFT_TYPE",
    "MSN",
    "REPORT_DATE",
    "AS_OF_DATE",
]

_OVERRIDES = {
    # ATA here is either a literal "-" placeholder or a chapter code with
    # optional subchapter groups, sometimes truncated ("28-57-", "30-00-").
    "ATA": {"pattern": r"^(?:-|\d{2}(?:-\d{2}(?:-\d{2})?)?-?)$", "int_range": None, "uppercase": True},
    # POSITION is deliberately kept as a raw, unsplit span (see module
    # docstring) -- permissive pattern, not asserting a specific shape.
    "POSITION": {"pattern": r"^.+$", "uppercase": True},
    "TASK_CODE": {"pattern": r"^(?:C/M|O/C)$", "uppercase": True},
    "LAST_DONE": {"pattern": r"^(?:n/a|-?[\d,]+\.\d+\s+[A-Z]+)$"},
    "NEXT_DUE": {"pattern": r"^(?:n/a|-?[\d,]+\.\d+\s+[A-Z]+)$"},
    "LOG_REF": {"pattern": r"^\(.*\)$"},
}
RULES = merged_rules(_OVERRIDES)

_ATA_START_RE = re.compile(r"^(?:-|\d{2}(?:-\d{2}(?:-\d{2})?)?-?)$")
_TASK_CODES = ("C/M", "O/C")
_VALUE_RE = re.compile(r"^-?[\d,]+\.\d+$")
_LOG_REF_RE = re.compile(r"^\(.+\)$")

_REPORT_DATE_RE = re.compile(r"^([A-Za-z]+ \d{1,2},\s*\d{4})\b")
_AIRCRAFT_REG_RE = re.compile(r"AIRCRAFT:\s*(\S+)")
_TYPE_MSN_RE = re.compile(r"TYPE/MODEL:\s*(\S+)\s*-\s*S/N:\s*(\S+)")
_AS_OF_RE = re.compile(r"AS OF\s*(\d{2}/\d{2}/\d{4})")

_DASH_LINE_RE = re.compile(r"^-{10,}$")


def _parse_line1(tokens: list[str]) -> dict | None:
    task_idx = None
    for code in _TASK_CODES:
        if code in tokens:
            task_idx = tokens.index(code)
            break
    if task_idx is None or task_idx < 2:
        return None

    ata = tokens[0]
    part_number = tokens[1]
    description = " ".join(tokens[2:task_idx])
    task_code = tokens[task_idx]
    after = tokens[task_idx + 1:]

    last_done = ""
    next_due = ""
    extra: list[str] = []

    if after and after[0] == "n/a":
        last_done = "n/a"
        after = after[1:]
    elif len(after) >= 2 and _VALUE_RE.match(after[0]):
        last_done = f"{after[0]} {after[1]}"
        after = after[2:]
    else:
        extra.extend(after)
        after = []

    if after:
        if after[0] == "n/a":
            next_due = "n/a"
            after = after[1:]
        elif len(after) >= 2 and _VALUE_RE.match(after[0]):
            next_due = f"{after[0]} {after[1]}"
            after = after[2:]
        else:
            extra.extend(after)
            after = []

    extra.extend(after)

    return {
        "ATA": ata,
        "PART_NUMBER": part_number,
        "DESCRIPTION": description,
        "TASK_CODE": task_code,
        "LAST_DONE": last_done,
        "NEXT_DUE": next_due,
        "SERIAL_NUMBER": "",
        "POSITION": "",
        "LOG_REF": "",
        "STATUS_TRAIL": " ".join(extra) if extra else "",
    }


def _apply_line2(record: dict, tokens: list[str]) -> None:
    if not tokens:
        return
    serial = tokens[0]
    rest = tokens[1:]
    log_ref = ""
    if rest and _LOG_REF_RE.match(rest[-1]):
        log_ref = rest[-1]
        rest = rest[:-1]
    record["SERIAL_NUMBER"] = serial
    record["POSITION"] = " ".join(rest)
    record["LOG_REF"] = log_ref


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

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if len(text) < 50:
                continue
            lines = [ln for ln in text.splitlines() if ln.strip()]

            # Split header block (before the dashed rule) from the table
            # body (after it) -- see module docstring.
            divider_idx = None
            for i, ln in enumerate(lines):
                if _DASH_LINE_RE.match(ln.strip()):
                    divider_idx = i
                    break

            if divider_idx is None:
                # No table on this page (e.g. a stray cover/summary page) --
                # still worth scanning for header metadata, but no rows.
                if not meta["AIRCRAFT_REG"]:
                    meta.update({k: v for k, v in _parse_header(text).items() if v})
                continue

            header_block = "\n".join(lines[:divider_idx])
            if not meta["AIRCRAFT_REG"] or not meta["AIRCRAFT_TYPE"]:
                parsed = _parse_header(header_block)
                for k, v in parsed.items():
                    if v and not meta[k]:
                        meta[k] = v

            body_lines = lines[divider_idx + 1:]

            current: dict | None = None
            awaiting_line2 = False
            trail: list[str] = []

            def _flush():
                if current is not None:
                    current["STATUS_TRAIL"] = " | ".join(
                        t for t in ([current["STATUS_TRAIL"]] + trail) if t
                    )
                    current["_page"] = page_num
                    current.update(meta)
                    records.append(current)

            for raw in body_lines:
                line = raw.strip()
                if not line:
                    continue
                tokens = line.split()

                if _ATA_START_RE.match(tokens[0]) and any(c in tokens for c in _TASK_CODES):
                    rec = _parse_line1(tokens)
                    if rec is not None:
                        _flush()
                        current = rec
                        trail = []
                        awaiting_line2 = True
                        continue
                    # Looked ATA-shaped but didn't parse as a valid line1 --
                    # fall through and treat as a continuation line instead
                    # of guessing a malformed record.

                if awaiting_line2 and current is not None:
                    _apply_line2(current, tokens)
                    awaiting_line2 = False
                    continue

                if current is not None:
                    trail.append(line)

            _flush()

    return records
