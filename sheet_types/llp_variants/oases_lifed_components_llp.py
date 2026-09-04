"""OASES "Lifed Component Report" -- LLP side.

Sibling of `ht_variants/oases_lifed_components.py`, which handles this same
OASES MIS export (`OASES Option : TR42`) for the Hard Time side. Sample
header (genericized)::

    Lifed Component Report          Report Date : <date> Page : 1 of <n>
    Aircraft Reg Model MSN Manufacture Date Airframe TSN Airframe CSN
    <reg> <model> <msn> <date> <tsn> <csn>

A single "Lifed Component Report" lists every lifed position on the
aircraft in one continuous per-ATA-chapter table -- calendar/hours-limited
Hard Time items (task types like Restoration, Overhaul, Functional
Check/Test, Battery Replacement, OPS Check) interleaved with true
life-limited parts (cycle-limited landing-gear, engine, and
tail/empennage components whose task type reads `Discard <GROUP> LLP`,
e.g. `Discard LG LLP`, `Discard ENG LLP`, `Discard TE LLP`,
`Discard APU LLP`). The HT sibling extracts every row regardless of task
type; this module is the row-level filter that keeps only the rows whose
task-type phrase carries that `LLP` marker token -- confirmed against the
real sample file: plain `Discard` (no `LLP` qualifier) also appears on a
few calendar-life consumable rows (e.g. a smoke-detector battery, a life
vest) that are Hard-Time discards, not cycle-limited LLPs, and those are
correctly excluded by requiring the marker.

Per-record body layout (same as the HT sibling)::

    <PN>  <ANCHOR>  Discard <GROUP> LLP  Date  <LAST_DONE>  <NEXT_DUE>  ...trail...
    <SN>  <continuation description>     Days (Calendar)  <numerics>
    <continuation>     Fleet Hours    <numerics>
                       Landings       <numerics>

where `<ANCHOR>` is the slashed identifier `<8-digit ATA-task>/<POS>/<level>`
and `<GROUP>` is a short code identifying which LLP family the part
belongs to (landing gear, engine, tail/empennage, APU, etc). Confirmed
groups seen in the sample: `LG`, `ENG`, `TE`, `APU`.

Row detection is anchor-based, matching the HT sibling, but deliberately
loosened at the token-shape level: the sample file's landing-gear and
engine LLP section is corrupted more heavily than the HT sibling's own
sample was written against -- specifically, the OCR pass upstream of this
PDF's own creation frequently inserts a stray space *inside* the anchor's
final `<level>.<sublevel>` segment (e.g. `7.34` renders as `7 .34`, `7.44`
as `7n .44`), which breaks a strict single-token
`\d{8}/<POS>/\d+\.\d+` regex. Since the ATA chapter and PART_NUMBER/POSITION
split is what downstream position-fingerprinting actually needs -- not the
sub-level precision -- the anchor pattern here only requires the token to
contain two slash-delimited segments after the leading 8-digit block
(`\d{8}/<non-slash-token>/<anything>`); whatever trails the second slash is
kept as ZONE_LEVEL best-effort (frequently truncated by the same stray-space
split) rather than validated against a strict shape. This was checked
directly against the sample file: loosening the anchor this way recovers
94 of 153 raw "task type contains LLP" candidate lines (the strict
single-token HT-style anchor recovers only 40) -- the other candidates are
lines where the OCR pass merged/scrambled the anchor token so badly no
digit-only ATA block survives at all (e.g. digits interleaved with stray
letters and spaces mid-token), which are correctly left unparsed rather
than guessed.

TASK_TYPE and LLP_GROUP are read directly off the anchor line (`Discard`
and the short group code immediately before the `LLP` marker token).
LAST_DONE / NEXT_DUE are the first two `DDMmmYYYY`-shaped date tokens
following the marker. Per this project's "never guess a wrong split"
convention, everything else on the anchor line after those two dates --
reference/card-schedule numbers whose column count and shape are not
confirmed consistent across every real row, and any extra date-shaped
token from a garbled `DOM` sub-line merging into the same physical line --
is folded into a single STATUS_TRAIL catch-all rather than force-split
into named columns. SERIAL_NUMBER is left blank for the same reason the HT
sibling leaves it blank: it lives on the continuation line below the
anchor in this document family, not on the anchor line itself, and a
positional continuation-line join is not reliable enough here to attempt
(the same OCR corruption that splits the anchor token also merges or
reorders the Days/Hours/Landings continuation lines in several places in
the sample).
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.llp_variants._base import merged_rules

NAME = "OASES Lifed Component Report (LLP)"
SIGNATURES = [
    "Lifed Component Report",
]
CANONICAL_COLUMNS = [
    "ATA",
    "POSITION",
    "ZONE_LEVEL",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "LLP_GROUP",
    "TASK_TYPE",
    "LAST_DONE",
    "NEXT_DUE",
    "STATUS_TRAIL",
]
_OVERRIDES = {
    "ATA":         {"pattern": r"^\d{2}$", "int_range": (20, 83)},
    "POSITION":    {"allow_empty": True},
    "ZONE_LEVEL":  {"allow_empty": True},
    "LLP_GROUP":   {"pattern": r"^[A-Za-z]{2,5}$", "allow_empty": True, "uppercase": True},
    "TASK_TYPE":   {"allow_empty": True},
    "LAST_DONE":   {"pattern": r"^\d{1,2}[A-Z][a-z]{2}\d{4}$", "allow_empty": True},
    "NEXT_DUE":    {"pattern": r"^\d{1,2}[A-Z][a-z]{2}\d{4}$", "allow_empty": True},
    # SN lives on a continuation line below the anchor in this document
    # family -- leave blank rather than guessing the wrong token (same
    # reasoning as the HT sibling's own SERIAL_NUMBER override).
    "SERIAL_NUMBER": {"allow_empty": True},
    "STATUS_TRAIL": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Loosened anchor: `<8-digit ATA-task>/<non-slash segment>/<anything>`.
# See module docstring for why this is looser than the HT sibling's
# single-token `\d{8}/<POS>/\d+\.\d+` pattern.
_ANCHOR = re.compile(r"^(\d{8})/([^/\s]+)/(.+)$")
# Date in `DDMmmYYYY` form (`23Nov2012`).
_DATE_RE = re.compile(r"^\d{1,2}[A-Z][a-z]{2}\d{4}$")
_HEADER_SKIP = re.compile(
    r"Lifed Component Report|Aircraft Reg|Chapter \d|Part\s+Serial|"
    r"Life\s+Remaining|Level\s*\(Variation\)|^Page\s|OASES Option|"
    r"Days\s*\(Calendar\)|Fleet\s+Hours|^Landings\b|Manufacture Date|"
    r"Threshold|Card\s+Schedule|Last\s+Limit\s*/\s*Interval|Section\s*/\s*Last", re.I)


def _is_llp_marker(tok: str) -> bool:
    """True if `tok`, stripped of any non-letter noise, is exactly "LLP"."""
    return re.sub(r"[^A-Za-z]", "", tok).upper() == "LLP"


def _parse_record_line(line: str, page_num: int) -> dict | None:
    """Try to parse the *anchor* line of an LLP record into a row dict.

    Returns None both for non-record lines (headers, continuation lines)
    and for genuine Hard-Time anchor lines that don't carry the `LLP`
    marker token -- this module only ever emits life-limited-part rows.
    """
    if _HEADER_SKIP.search(line):
        return None
    toks = line.split()
    if len(toks) < 5:
        return None
    anchor_idx = None
    ata = position = zone_level = ""
    for i, t in enumerate(toks):
        m = _ANCHOR.match(t)
        if m:
            anchor_idx = i
            ata_full, pos, level = m.groups()
            ata = ata_full[:2]
            position = pos
            zone_level = level
            break
    if anchor_idx is None or anchor_idx == 0:
        return None
    try:
        ata_int = int(ata)
    except ValueError:
        return None
    if not (20 <= ata_int <= 83):
        return None
    pn = toks[0]
    tail = toks[anchor_idx + 1:]
    # Find the LLP marker token within the tail (task-type phrase, e.g.
    # "Discard LG LLP"). No marker => not an LLP row, skip it.
    llp_idx = None
    for k, t in enumerate(tail):
        if _is_llp_marker(t):
            llp_idx = k
            break
    if llp_idx is None:
        return None
    # The task-type keyword is "Discard", located by content rather than by
    # position -- the anchor's own <level>.<sublevel> segment is frequently
    # split across a stray extra token (e.g. "7" then ".34") by the same
    # OCR corruption the loosened anchor above already works around, which
    # would otherwise land ahead of "Discard" in the tail and be
    # mistaken for the task type at a fixed offset.
    task_idx = None
    for k, t in enumerate(tail[:llp_idx]):
        if re.sub(r"[^A-Za-z]", "", t).lower() == "discard":
            task_idx = k
            break
    if task_idx is not None:
        task_type = tail[task_idx]
        llp_group = " ".join(tail[task_idx + 1:llp_idx])
    else:
        # "Discard" itself didn't survive OCR intact -- fall back to
        # whatever token sits immediately before the LLP marker as the
        # group code, leave TASK_TYPE blank rather than guess.
        task_type = ""
        llp_group = tail[llp_idx - 1] if llp_idx >= 1 else ""
    # Everything after the marker: a literal "Date" label, then LAST_DONE /
    # NEXT_DUE date tokens, then trailing reference/card-schedule tokens
    # (and occasionally a stray extra date from a garbled DOM sub-line).
    rest = [t for t in tail[llp_idx + 1:] if t.lower() != "date"]
    last_done = next_due = ""
    trail_tokens: list[str] = []
    for t in rest:
        if _DATE_RE.match(t):
            if not last_done:
                last_done = t
            elif not next_due:
                next_due = t
            else:
                trail_tokens.append(t)
        else:
            trail_tokens.append(t)
    status_trail = " ".join(trail_tokens)
    if not pn:
        return None
    return {
        "ATA": ata,
        "POSITION": position,
        "ZONE_LEVEL": zone_level,
        "PART_NUMBER": pn,
        "SERIAL_NUMBER": "",
        "LLP_GROUP": llp_group,
        "TASK_TYPE": task_type,
        "LAST_DONE": last_done,
        "NEXT_DUE": next_due,
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
                rec = _parse_record_line(raw.strip(), page_num)
                if rec is not None:
                    records.append(rec)
    return records
