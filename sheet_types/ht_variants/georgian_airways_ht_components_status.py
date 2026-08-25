"""Georgian Airways "HARD TIME COMPONENTS STATUS" report (B737-700).

Header::

    GEORGIAN AIRWAYS
    HARD TIME COMPONENTS STATUS FOR A/C-REGISTRATION: <tail no.>
    Total FH: 52703 Total FC: 34326 As of Date: 03.08.2016
    A/C Type: B737-700 MSN: <MSN>
    LAST ACN AT INSTALLATION SPEC LIMIT NEXT DUE REMAINING
    COMPONENT PART NUMBER SERIAL NUMBER POSITION TASK
    MAINT. HOURS CYCLES DATE HOURS CYCLES DAYS HOURS CYCLES DATE HOURS CYCLES DAYS

Row example::

    24-120-00 Main and APU Battery 024147-000 0905200136A01 Auxiliary 28.12.2015 Deep Cycle 51067 33663 09.01.2016 2000 53067 364

Anchor: the `NN-NNN-NN` task code at line start (e.g. `24-120-00`). Nothing
else in this document — including every header/footer line above — matches
that shape, so no separate header-skip regex is needed the way sibling
parsers require one.

The 12-value MAINT/LIMIT/NEXT-DUE/REMAINING tail is column-ragged: blank
cells are dropped rather than represented, so the same tail shape (e.g.
"2190 14.12.2017 498") can mean different sub-columns on different rows
depending on which of hours/cycles/date the component is tracked by. That
makes a faithful per-sub-column split unreliable from whitespace tokens
alone (would need x-coordinate table extraction), so — same call TAP HT
makes for its trailing columns — the tail is kept as one STATUS_TRAIL
string.

TASK is the second reliable anchor: a closed vocabulary (_TASK_1/_TASK_2)
that always sits right before that tail. Whatever sits between the task
code and TASK is DESCRIPTION, optionally followed by PART_NUMBER (first
token containing a digit), SERIAL_NUMBER (token after it) and POSITION
(everything left over). Roughly a sixth of rows wrap DESCRIPTION onto the
physical line above the anchor (the numeric cells stay on the anchor line
because they're short; the multi-word description above must have wrapped
in its own narrower column, e.g. "Flight Crew Oxygen Mask" / anchor line /
"Regulator"). We don't stitch those neighbour lines back in — sibling
parsers (mm510, STARS Trax) draw the same line at not chasing every wrap
sub-layout — so those rows extract with DESCRIPTION empty but PART_NUMBER/
SERIAL_NUMBER/POSITION/TASK/STATUS_TRAIL unaffected.

Corpus note: a handful of files were triaged into this cluster by
filename. Only a couple have a real text layer (this parser); the rest
of the "HT Components Status-*" files are ScanSnap scans (image-only
pages, no text) and need OCR, not this parser. A file matching one such
name turned out to be a different operator entirely ("A/C Status Audit
Print") and was dropped from the cluster.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "Georgian Airways HT Components Status"
SIGNATURES = [
    "HARD TIME COMPONENTS STATUS FOR A/C-REGISTRATION",
]
CANONICAL_COLUMNS = [
    "ATA",
    "TASK_CODE",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "POSITION",
    "INSTALL_DATE",
    "TASK",
    "STATUS_TRAIL",
]
_OVERRIDES = {
    "TASK_CODE":     {"pattern": r"^\d{2}-\d{3}-\d{2}$"},
    "PART_NUMBER":   {"allow_empty": True},
    "SERIAL_NUMBER": {"allow_empty": True},
    "POSITION":      {"allow_empty": True, "uppercase": True},
    "INSTALL_DATE":  {"pattern": r"^\d{2}\.\d{2}\.\d{4}$", "allow_empty": True},
    "TASK":          {"allow_empty": True, "uppercase": True},
    "STATUS_TRAIL":  {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_CODE_RE = re.compile(r"^\d{2}-\d{3}-\d{2}$")
_DATE_RE = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")
# Digits-somewhere, punctuation-only-otherwise: distinguishes PART_NUMBER-
# shaped tokens ("024147-000", "5A3307-7") from description words and from
# bare dash/N-A placeholders, without requiring a letter (many PNs here are
# pure digit-and-dash, unlike the letter+digit shape used elsewhere in HT).
_PN_LIKE = re.compile(r"^(?=[A-Z0-9/-]*\d)[A-Z0-9/-]+$")
# Two typos ("Disard", "Restorarion") are verbatim in the source PDF, not
# OCR noise — matched as-is rather than "corrected" to avoid missing rows.
_TASK_1 = {
    "OPERATIONAL", "REPLACE", "OVERHAUL", "RESTORE", "DISCARD", "DISARD",
    "FUNCTIONAL", "FUNCT", "FNC", "TEST", "INSPECT", "RESTORARION",
}
_TASK_2 = {
    ("DEEP", "CYCLE"), ("HYDRO", "TEST"), ("WEIGHT", "CHK"), ("LIFE", "LIMIT"),
}


def _find_task(rest: list[str]) -> tuple[int, int]:
    for i, tok in enumerate(rest):
        if i + 1 < len(rest) and (tok.upper(), rest[i + 1].upper()) in _TASK_2:
            return i, 2
        if tok.upper() in _TASK_1:
            return i, 1
    return -1, 0


def _parse_line(line: str, page_num: int) -> dict | None:
    toks = line.split()
    if not toks or not _CODE_RE.match(toks[0]):
        return None
    ata_int = int(toks[0][:2])
    if not (20 <= ata_int <= 83):
        return None
    rest = toks[1:]
    task_idx, task_len = _find_task(rest)
    if task_idx < 0:
        return None
    task = " ".join(rest[task_idx:task_idx + task_len])
    status_trail = " ".join(rest[task_idx + task_len:])
    head = rest[:task_idx]
    install_date = ""
    if head and _DATE_RE.match(head[-1]):
        install_date = head.pop()
    pn_idx = next((i for i, t in enumerate(head) if _PN_LIKE.match(t)), None)
    if pn_idx is None:
        description, pn, sn, position = " ".join(head), "", "", ""
    else:
        description = " ".join(head[:pn_idx])
        pn = head[pn_idx]
        after_pn = head[pn_idx + 1:]
        sn = after_pn[0] if after_pn else ""
        position = " ".join(after_pn[1:])
    return {
        "ATA": toks[0][:2],
        "TASK_CODE": toks[0],
        "DESCRIPTION": description,
        "PART_NUMBER": pn,
        "SERIAL_NUMBER": sn,
        "POSITION": position,
        "INSTALL_DATE": install_date,
        "TASK": task,
        "STATUS_TRAIL": status_trail,
        "_page": page_num,
    }


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if len(text) < 80:
                continue
            for raw in text.splitlines():
                rec = _parse_line(raw.strip(), page_num)
                if rec is not None:
                    records.append(rec)
    return records
