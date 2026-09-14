""""MAINTENANCE DUE REPORT" MIS export (program id "PGM: PORP96RR" printed in
the page header), one record block per limited-life/hard-time position.

Header (repeated per page)::

    DATE <dd-mm-yy>          <op letterhead>  PGM: PORP96RR
    TIME <hh:mm:ss>          MAINTENANCE DUE REPORT  USER: <user id>
    PAGE: <n>
    A/C: <reg> HOURS: <hh:mm> CYCLES: <n> EFFECTIVITY DATE: <date>
    <type/lease line>  LAST LOG PAGE NO.: <n> <n>
    ______SCHEDULE______________ACTUAL______________REMAINING________ Complete By
    Hours    Cycles Days  Hours    Cycles Days  Hours     Cycles Days  Date

Record block (5 lines, then an underscore rule line)::

    S/N:<serial> Position:<position>  <sched h> <sched c> <sched d>  <actual h> <actual c> <actual d>  <remaining h> <remaining c> <remaining d>  <complete-by date>
    Part Code: <ata3> <subsys2> <seq4> <part number> <TSO-EXPIRE|SCHED-HOUR|SCHED-DAYS>
    <description> T.S.O.
    Time since Install: <h:mm> <cycles> <days>
    A/C time at Install: [<h:mm> <cycles>]

Each of SCHEDULE/ACTUAL/REMAINING's three sub-columns is populated only when
that measure applies to the part's tracked interval type (e.g. a
SCHED-DAYS part shows only a days figure in SCHEDULE, an hours-tracked
TSO-EXPIRE part usually shows only ACTUAL hours/cycles/days), so most
records leave several of these nine cells blank -- confirmed against every
record line in this file, never a case of a genuinely present value being
dropped.

Anchor quirk worth documenting: the very first record's `S/N:.../Position:`
line on every page comes back from pdfplumber's own `extract_text()` and
`extract_words()` fully letter-spaced ("S / N : A L T 2 1 9 ...") while
every other record's identical-looking line on the same page extracts
cleanly. Character-level inspection shows the PDF itself renders that row
as literal fixed-pitch glyphs -- including real explicit space *characters*
padding almost the entire row width -- while subsequent rows on the page
don't carry that padding; pdfplumber's word segmenter treats each of those
real space glyphs as a word break. Rather than try to out-guess
pdfplumber's heuristics with a different x/word tolerance (which only
trades one failure mode for another), this parser bypasses `extract_text`/
`extract_words` for that one row shape entirely: it reads `page.chars`
directly, drops literal space glyphs, and buckets the remaining characters
into fixed x0 column bands (derived from the header row's own "Hours
Cycles Days" x-positions, then confirmed against every non-spread record
row in this file) to reassemble each field regardless of how pdfplumber
would have tokenized it. This also makes the parser immune if a future
file from the same generator has the spacing bug on a different row.

The other four lines per record (Part Code / description / "Time since
Install" / "A/C time at Install") never exhibited the spread bug in this
file, so they're read the ordinary way, matched positionally within each
5-line block (block boundaries found by locating the "S/N:" line, ignoring
its internal spacing). A record only becomes a row here when Part Code,
"Time since Install" and "A/C time at Install" all matched their expected
shape -- a block that doesn't fit is skipped rather than guessed at.

PART_CODE keeps the three-group prefix ("<ata3> <subsys2> <seq4>") as one
raw string rather than splitting it into separate columns: while the shape
is completely regular in this file (regex-verified against every row),
nothing in the header text actually labels what the three groups mean
individually, so splitting them would be asserting semantics the source
doesn't state. The trailing token is the real part number and is kept
separately as PART_NUMBER since the header's "Part Code:" phrasing and
this token's shape (matches this project's shared PART_NUMBER rule
cleanly) mark it unambiguously as the part number.

INTERVAL_TYPE is a closed three-value vocabulary (TSO-EXPIRE / SCHED-HOUR /
SCHED-DAYS) confirmed across every record in this file; a record whose Part
Code line doesn't end in one of those three tokens fails the block match
above and is skipped rather than accepted with an unrecognised interval
type.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.ht_variants._base import merged_rules

NAME = "Maintenance Due Report (PORP96RR)"
SIGNATURES = [
    "MAINTENANCE DUE REPORT",
    "PGM: PORP96RR",
]
CANONICAL_COLUMNS = [
    "SERIAL_NUMBER",
    "POSITION",
    "PART_CODE",
    "PART_NUMBER",
    "INTERVAL_TYPE",
    "DESCRIPTION",
    "SCHED_HOURS",
    "SCHED_CYCLES",
    "SCHED_DAYS",
    "ACTUAL_HOURS",
    "ACTUAL_CYCLES",
    "ACTUAL_DAYS",
    "REMAINING_HOURS",
    "REMAINING_CYCLES",
    "REMAINING_DAYS",
    "COMPLETE_BY_DATE",
    "TSI_HOURS",
    "TSI_CYCLES",
    "TSI_DAYS",
    "ACI_HOURS",
    "ACI_CYCLES",
]

_HHMM = r"\d{1,6}:\d{2}"
_INT = r"\d{1,6}"
_DATE = r"\d{2}/\d{2}/\d{4}"

_OVERRIDES = {
    # Required on every record.
    "POSITION": {},
    "PART_CODE": {"pattern": r"^\d{3} \d{2} \d{4}$"},
    "INTERVAL_TYPE": {"pattern": r"^(TSO-EXPIRE|SCHED-HOUR|SCHED-DAYS)$"},
    "ACTUAL_HOURS": {"pattern": rf"^{_HHMM}$"},
    "ACTUAL_CYCLES": {"pattern": rf"^{_INT}$", "allow_empty": True},
    "ACTUAL_DAYS": {"pattern": rf"^{_INT}$", "allow_empty": True},
    "COMPLETE_BY_DATE": {"pattern": rf"^{_DATE}$"},
    "TSI_HOURS": {"pattern": rf"^{_HHMM}$"},
    "TSI_CYCLES": {"pattern": rf"^{_INT}$"},
    "TSI_DAYS": {"pattern": rf"^{_INT}$"},
    # Genuinely optional per the interval-type-dependent column population
    # documented above -- blank is normal, not a defect.
    "SCHED_HOURS": {"pattern": rf"^{_HHMM}$", "allow_empty": True},
    "SCHED_CYCLES": {"pattern": rf"^{_INT}$", "allow_empty": True},
    "SCHED_DAYS": {"pattern": rf"^{_INT}$", "allow_empty": True},
    "REMAINING_HOURS": {"pattern": rf"^{_HHMM}$", "allow_empty": True},
    "REMAINING_CYCLES": {"pattern": rf"^{_INT}$", "allow_empty": True},
    "REMAINING_DAYS": {"pattern": rf"^{_INT}$", "allow_empty": True},
    # Blank when a part was installed new (no prior A/C-time-at-install
    # figure to report) -- seen for real in this file.
    "ACI_HOURS": {"pattern": rf"^{_HHMM}$", "allow_empty": True},
    "ACI_CYCLES": {"pattern": rf"^{_INT}$", "allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# --- Row-0 (S/N: / Position: / Schedule-Actual-Remaining / Complete-By)
# column bands, in points from the page's left edge. Derived from the
# header row's own "Hours"/"Cycles"/"Days"/"Date" word x0 positions
# (SCHEDULE starts ~183.6, ACTUAL ~266.4, REMAINING ~349.2, Date ~432.0)
# and confirmed against every record row's actual field x0 in this file --
# see module docstring for why this is read from page.chars rather than
# extract_text()/extract_words().
_ROW0_BUCKETS = [
    ("SN", 0, 70),
    ("POSITION", 70, 180),
    ("SCHED_HOURS", 180, 216),
    ("SCHED_CYCLES", 216, 241),
    ("SCHED_DAYS", 241, 266),
    ("ACTUAL_HOURS", 266, 302),
    ("ACTUAL_CYCLES", 302, 327),
    ("ACTUAL_DAYS", 327, 349),
    ("REMAINING_HOURS", 349, 385),
    ("REMAINING_CYCLES", 385, 410),
    ("REMAINING_DAYS", 410, 432),
    ("COMPLETE_BY_DATE", 432, 999999),
]

_PART_CODE_RE = re.compile(
    r"^Part Code:\s+(\d{3} \d{2} \d{4})\s+(\S+)\s+(TSO-EXPIRE|SCHED-HOUR|SCHED-DAYS)$"
)
_TSI_RE = re.compile(
    rf"^Time since Install:\s+({_HHMM})\s+({_INT})\s+({_INT})$"
)
_ACI_RE = re.compile(
    rf"^A/C time at Install:(?:\s+({_HHMM})\s+({_INT}))?$"
)
_DESC_SUFFIX = " T.S.O."


def _bucket_of(x0: float) -> str | None:
    for name, lo, hi in _ROW0_BUCKETS:
        if lo <= x0 < hi:
            return name
    return None


def _row0_records(page) -> list[dict]:
    """Reassemble every record's S/N:/Position:/schedule row directly from
    character positions -- see module docstring for why extract_text()/
    extract_words() aren't used for this line."""
    rows: dict[float, list] = {}
    for c in page.chars:
        if c["text"] == " ":
            continue
        rows.setdefault(round(c["top"], 1), []).append(c)
    out = []
    for top in sorted(rows):
        chars = sorted(rows[top], key=lambda c: c["x0"])
        if "".join(c["text"] for c in chars[:4]) != "S/N:":
            continue
        fields: dict[str, list[str]] = {}
        for c in chars:
            b = _bucket_of(c["x0"])
            if b:
                fields.setdefault(b, []).append(c["text"])
        out.append({k: "".join(v) for k, v in fields.items()})
    return out


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            row0_list = _row0_records(page)
            if not row0_list:
                continue
            lines = (page.extract_text() or "").splitlines()
            starts = [
                i for i, l in enumerate(lines)
                if l.replace(" ", "").startswith("S/N:")
            ]
            if len(starts) != len(row0_list):
                # Row-count mismatch between the char-bucket reconstruction
                # and the plain-text line scan -- can't safely zip the two
                # per docstring, so skip this page rather than risk
                # pairing a record's schedule/date data with the wrong
                # Part Code/description/install-time block.
                continue
            for idx, start in enumerate(starts):
                block = lines[start:start + 5]
                if len(block) < 5:
                    continue
                pc_m = _PART_CODE_RE.match(block[1].strip())
                tsi_m = _TSI_RE.match(block[3].strip())
                aci_m = _ACI_RE.match(block[4].strip())
                if not (pc_m and tsi_m and aci_m):
                    continue
                desc = block[2].strip()
                if desc.endswith(_DESC_SUFFIX):
                    desc = desc[: -len(_DESC_SUFFIX)]
                row0 = row0_list[idx]
                records.append({
                    "SERIAL_NUMBER": row0.get("SN", "").removeprefix("S/N:"),
                    "POSITION": row0.get("POSITION", "").removeprefix("Position:"),
                    "PART_CODE": pc_m.group(1),
                    "PART_NUMBER": pc_m.group(2),
                    "INTERVAL_TYPE": pc_m.group(3),
                    "DESCRIPTION": desc,
                    "SCHED_HOURS": row0.get("SCHED_HOURS", ""),
                    "SCHED_CYCLES": row0.get("SCHED_CYCLES", ""),
                    "SCHED_DAYS": row0.get("SCHED_DAYS", ""),
                    "ACTUAL_HOURS": row0.get("ACTUAL_HOURS", ""),
                    "ACTUAL_CYCLES": row0.get("ACTUAL_CYCLES", ""),
                    "ACTUAL_DAYS": row0.get("ACTUAL_DAYS", ""),
                    "REMAINING_HOURS": row0.get("REMAINING_HOURS", ""),
                    "REMAINING_CYCLES": row0.get("REMAINING_CYCLES", ""),
                    "REMAINING_DAYS": row0.get("REMAINING_DAYS", ""),
                    "COMPLETE_BY_DATE": row0.get("COMPLETE_BY_DATE", ""),
                    "TSI_HOURS": tsi_m.group(1),
                    "TSI_CYCLES": tsi_m.group(2),
                    "TSI_DAYS": tsi_m.group(3),
                    "ACI_HOURS": aci_m.group(1) or "",
                    "ACI_CYCLES": aci_m.group(2) or "",
                    "_page": page_num,
                })
    return records
