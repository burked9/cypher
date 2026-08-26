"""TIME CONTROLLED COMPONENTS STATUS — per-aircraft hard-time export.

Header, values genericized below but the shape is real::

    TIME CONTROLLED COMPONENTS STATUS
    AIRCRAFT MSN / REGISTRATION AIRCRAFT TYPE DATE OF MANUFACTURE ACFT TOTAL TIME ACFT TOTAL CYCLES DATE AS OF
    MSN <msn> / <tail> A319-112 Dec-02 48,179 30,145 11-Jul-20
    Installation Interval Next Due Remaining
    MPD / Other Last
    ATA Task Nomenclature Part Number Serial Number Pos
    Reference Done
    DATE FH FC FH FC Cal FH FC Calendar FH FC Day/s
    21 213100-08-1 Restoration Safety Valve 9024-15704-03 16115340 6HL 02-Mar-16 27-Jul-16 39311.00 22947.00 50000 210 M 89311.00 02-Sep-33 41132.00 4801

Row grain: one row per tracked component/MPD-task combination. Column
layout is a 2-tier header: ATA / MPD-Other-Reference / Task / Nomenclature /
Part Number / Serial Number / Pos / Last-Done Date, then an
Installation/Interval/Next-Due/Remaining block that is column-ragged --
some components are tracked by FH/FC only, some by Calendar only, some by
both, so the number of trailing sub-columns actually printed varies row to
row. Same project convention as `hard_time_report_config_slot.py`'s own
trailing block: kept verbatim as one `STATUS_TRAIL` catch-all string
rather than force-split into fixed sub-columns.

Row anchor: a leading 2-digit ATA chapter in its own left-hand column
(x-position based, not just "first token on the line" -- see below).

PDF-extraction quirk this format needs handled explicitly: when a field's
text is too wide for its column, the PDF renderer does NOT wrap it onto a
second visual line *within* the row -- it prints the overflow as a
separate physical text line immediately before or after the row's main
line, still left-aligned to that field's column x-position. Observed
across the MPD/Other Reference, Task, Nomenclature, and Serial Number
columns, e.g.::

    25 256241-03-1 Annual inspection after 15 YE Door Escape Slide-DOM Jul/13 D30664-709 M9411 DR1 LH 08-Jul-19 03-Aug-19 46484.00 28867.00 15 Y 31-Jul-28 2942
    256241-02-1
    25 Hydrostatic Test Gas Cylinder D18309-115 751-11418 DR1 LH 08-Jun-19 03-Aug-19 46484.00 28867.00 5 Y 01-Jun-24 1421

The lone `256241-02-1` line is the MPD/Other Reference value for the row
*below* it (that row's own main line jumps straight from ATA to Task with
no reference code in between). A plain "split on newline, anchor on
leading ATA + task-code" strategy -- the approach used by
`hard_time_report_config_slot.py`, a close structural precedent from a
different MIS family -- does not work unmodified here, because the task
code is not reliably present on the anchor line itself.

This module instead extracts words with x/y coordinates (`extract_words`),
groups them into physical lines by y-position, and classifies each line as
either a "core" row (has a bare 2-digit ATA token in the ATA column's
x-range) or an orphan overflow fragment. Each orphan fragment is merged
into whichever core row is vertically closest to it (row spacing is ~25pt;
an overflow fragment sits ~6-13pt from the row it belongs to, so nearest-
neighbour-by-y is unambiguous in practice), with its words bucketed into
the correct field by x-range and prepended/appended depending on whether
the fragment sits above or below the core line. Fragments with no core row
within a small vertical tolerance (page title, aircraft-info line, column
headers repeated on every page, page-footer) are discarded rather than
merged into an unrelated row.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.ht_variants._base import merged_rules

NAME = "Time Controlled Components Status"
SIGNATURES = [
    "TIME CONTROLLED COMPONENTS STATUS",
]

CANONICAL_COLUMNS = [
    "ATA",
    "MPD_REFERENCE",
    "TASK",
    "NOMENCLATURE",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "POS",
    "LAST_DONE_DATE",
    "INSTALLATION_DATE",
    "STATUS_TRAIL",
]

_OVERRIDES = {
    "MPD_REFERENCE": {"pattern": r"^[A-Z0-9][A-Z0-9\-\./ ]*[A-Z0-9]$",
                       "uppercase": True, "allow_empty": True},
    "TASK":          {"allow_empty": True},
    "NOMENCLATURE":  {"allow_empty": True},
    "POS":           {"pattern": r"^[A-Z0-9][A-Z0-9 /\-]*[A-Z0-9]$",
                       "uppercase": True, "allow_empty": True},
    "LAST_DONE_DATE": {"pattern": r"^\d{2}-[A-Za-z]{3}-\d{2}$"},
    "INSTALLATION_DATE": {"pattern": r"^\d{2}-[A-Za-z]{3}-\d{2}$"},
    "STATUS_TRAIL":  {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Column x-position bins (PDF points), derived from real header/body
# coordinates on the sample file. Anything at or past the last bin's upper
# bound is the ragged Installation/Interval/Next-Due/Remaining block and
# goes into STATUS_TRAIL verbatim.
_BINS = [
    (70, 100, "ATA"),
    (100, 195, "MPD_REFERENCE"),
    (195, 373, "TASK"),
    # PART_NUMBER is right-aligned within its column, so long values start
    # further left than short ones (observed x0 as low as ~578); the
    # boundary sits at 560 rather than nearer the typical ~594-620 start,
    # to keep those long values out of NOMENCLATURE without misclassifying
    # any real (left-aligned, one-word-per-token) nomenclature word, none
    # of which was observed past x0 ~540 on the sample file.
    (373, 560, "NOMENCLATURE"),
    (560, 690, "PART_NUMBER"),
    # POS is right-aligned like PART_NUMBER above -- a short value like
    # "FWD" can start as low as x0~793, well inside what would otherwise
    # look like the Serial Number band. Real Serial Number values on the
    # sample file never start past x0~744, leaving a wide untouched gap
    # to draw this boundary in.
    (690, 780, "SERIAL_NUMBER"),
    (780, 862, "POS"),
    (862, 905, "LAST_DONE_DATE"),
    (905, 1000, "INSTALLATION_DATE"),
]
_TRAIL_MIN_X = 1000

_ATA_RE = re.compile(r"^\d{2}$")
# Fragments are merged only if within this many PDF points (vertically) of
# the nearest core row; real header/title/footer lines sit far outside it.
_MAX_MERGE_DIST = 20.0


def _bin_for(x0: float) -> str:
    for lo, hi, field in _BINS:
        if lo <= x0 < hi:
            return field
    return "STATUS_TRAIL"


def _group_lines(words: list[dict]) -> list[dict]:
    """Group words into physical lines, tolerant of sub-point 'top' jitter
    between words nominally on the same visual line."""
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


def _is_core(line: dict) -> bool:
    first = line["words"][0]
    return 70 <= first["x0"] < 100 and bool(_ATA_RE.match(first["text"]))


def _row_from_core(line: dict) -> dict:
    row = {col: "" for col in CANONICAL_COLUMNS}
    trail: list[str] = []
    for w in line["words"]:
        if w["x0"] >= _TRAIL_MIN_X:
            trail.append(w["text"])
            continue
        field = _bin_for(w["x0"])
        row[field] = (row[field] + " " + w["text"]).strip()
    row["STATUS_TRAIL"] = " ".join(trail)
    return row


def _merge_orphan(row: dict, line: dict, core_top: float) -> None:
    before = line["top"] < core_top
    buckets: dict[str, list[str]] = {}
    for w in line["words"]:
        field = _bin_for(w["x0"]) if w["x0"] < _TRAIL_MIN_X else "STATUS_TRAIL"
        buckets.setdefault(field, []).append(w["text"])
    for field, texts in buckets.items():
        frag = " ".join(texts)
        existing = row.get(field, "")
        if not existing:
            row[field] = frag
        elif before:
            row[field] = f"{frag} {existing}"
        else:
            row[field] = f"{existing} {frag}"


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
            if not words:
                continue
            lines = _group_lines(words)

            core_lines = [ln for ln in lines if _is_core(ln)]
            if not core_lines:
                continue
            rows = [_row_from_core(ln) for ln in core_lines]
            core_tops = [ln["top"] for ln in core_lines]

            for line in lines:
                if _is_core(line):
                    continue
                # Nearest core row on this page, by vertical distance.
                best_idx, best_dist = None, None
                for i, top in enumerate(core_tops):
                    dist = abs(line["top"] - top)
                    if best_dist is None or dist < best_dist:
                        best_idx, best_dist = i, dist
                if best_idx is None or best_dist > _MAX_MERGE_DIST:
                    continue
                _merge_orphan(rows[best_idx], line, core_tops[best_idx])

            for row in rows:
                row["_page"] = page_num
                records.append(row)
    return records
