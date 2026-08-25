"""Hard Time Component Status — MPD-task-number layout (a known A321 file in the corpus).

Header::

    Aircraft
    AIRBUS A321-231 HOURS 49,740
    Hard Time Component Status
    MSN <MSN> CYCLES 43,630
    REG <tail no.> DATE 2019-09-30
    DOM 02-May-00
    MPD INTERVAL AMP INTERVAL LAST DONE NEXT DUE REMAIN
    ATA MPD TASK NO PART NUMBER SERIAL NUMBER PART DESCRIPTION POS TASK TYPE
    DY FH FC DY FH FC DATE FH FC DATE FH FC DY FH FC

Row example (single physical line — the common case)::

    21 213100-08-1 9024-15704-2 0172384 SAFETY VALVE ACFT-21-31-05-SAN OVHL 6385 50000 - 6385 50000 - 12-Apr-05 15,574 - 5-Oct-22 65,574 - 976 15,834 -

Column x-positions are identical on every page of both text-layer files in
the cluster, which is what this parser keys off instead of whitespace
tokens: PART DESCRIPTION and TASK TYPE are narrow enough that a long value
wraps onto its own line, split symmetrically above/below the row's
single-line numeric cells rather than growing the row evenly, e.g.::

    HEAT EXCHANGER, SHOP
    21 215200-01-1 753A0000-03 01164 ACFT-21-52-01-SQS 3285 12000 - 3285 12000 - TBD TBD - TBD TBD - TBD TBD -
    PRIMARY CLEANING

is one row: DESCRIPTION "HEAT EXCHANGER, PRIMARY", TASK_TYPE "SHOP CLEANING".
Unlike mm510 / STARS Trax / Georgian Airways HT (which leave a wrapped
DESCRIPTION blank rather than chase the wrap), this parses by x0 column and
stitches the wrap back in, because here the wrap is the majority shape, not
a minority — every OXYGEN GENERATOR / CE-NOTE-flanked row on pages 4-8
would otherwise lose its description entirely. Anchor: the row with a word
in the SERIAL NUMBER column (x0 280-390); PART DESCRIPTION (x0 390-525) and
TASK TYPE (x0 715-793) words on non-anchor lines are folded into whichever
neighbouring anchor row they sit closer to (usually the one immediately
above or below; never split further, since no row in the corpus needed a
3rd wrapped line on either side).

A stray "CE" / "NOTE" cross-reference marker sometimes prints as its own
2-line block (x0 ~795-824, over what would be the MPD_INTERVAL/DY cell) on
the same physical lines as a wrapped description. It falls outside every
named column bucket above and is dropped along with the rest of that cell.

The 15 trailing DY/FH/FC/DATE cells (MPD INTERVAL, AMP INTERVAL, LAST DONE,
NEXT DUE, REMAIN) sit on the row's own anchor line, but a blank TASK TYPE
occasionally shifts the first one left by roughly a cell width (a lone "-"
centers in its cell instead of left-aligning like real values do) — the
same unreliable-shift problem mpd_hard_time_list.py and Georgian Airways HT
document for their own trailing columns, so it's kept as one STATUS_TRAIL
string rather than mis-sliced into named cells.

MPD_TASK_NO is a literal "-" on a handful of rows (SURVIVAL KIT, LIFE VEST)
that track by calendar days only and carry no MPD task; ATA is recovered
from the task number's own leading 2-digit chapter when the ATA cell itself
is blank too (LIFE VEST's same-task continuation rows).

Corpus: a small cluster of files. Two have a real text layer and are
byte-identical (same report, filed under two different tail numbers/MSNs)
— that shared layout is what this parser targets. The third file is a
ScanSnap-style scan: 0 chars on every one of its 8 pages under
pdfplumber. It needs OCR, not this parser.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.ht_variants._base import merged_rules

NAME = "Hard Time Component Status (MPD Task No)"
SIGNATURES = [
    "MPD INTERVAL AMP INTERVAL",
    "MPD TASK NO",
]
CANONICAL_COLUMNS = [
    "ATA",
    "MPD_TASK_NO",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
    "POSITION",
    "TASK_TYPE",
    "STATUS_TRAIL",
]
_OVERRIDES = {
    "MPD_TASK_NO":   {"pattern": r"^\d{6}-[A-Z0-9]{1,3}-\d{1,2}$", "allow_empty": True},
    "SERIAL_NUMBER": {"allow_empty": True},
    "DESCRIPTION":   {"allow_empty": True},
    "POSITION":      {"allow_empty": True, "uppercase": True},
    "TASK_TYPE":     {"allow_empty": True},
    "STATUS_TRAIL":  {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# x0 column bounds, read off the header word positions (fixed across every
# page checked in both text-layer files).
_ATA_COL = (40, 80)
_TASK_COL = (80, 168)
_PN_COL = (168, 280)
_SN_COL = (280, 390)
_DESC_COL = (390, 525)
_POS_COL = (525, 715)
_TYPE_COL = (715, 793)

_TASK_RE = re.compile(r"^\d{6}-[A-Z0-9]{1,3}-\d{1,2}$")
# Last header sub-row ("DY FH FC ...") bottoms out at 167.5 on every page
# checked; data rows start at 172+. Filtering here also removes the
# repeated "ATA MPD TASK NO PART NUMBER SERIAL NUMBER ..." column-header
# line itself, which would otherwise false-positive as an anchor (its
# "SERIAL"/"NUMBER" words sit inside the SERIAL NUMBER column's x0 range).
_HEADER_BOTTOM = 169


def _group_lines(words: list[dict], y_tol: float = 2.0) -> list[list[dict]]:
    words = sorted(words, key=lambda w: (w["top"], w["x0"]))
    lines: list[list[dict]] = []
    for w in words:
        if lines and abs(w["top"] - lines[-1][0]["top"]) <= y_tol:
            lines[-1].append(w)
        else:
            lines.append([w])
    return lines


def _col_text(line: list[dict], col: tuple[int, int]) -> str:
    lo, hi = col
    return " ".join(w["text"] for w in line if lo <= w["x0"] < hi)


def _is_anchor(line: list[dict]) -> bool:
    lo, hi = _SN_COL
    return any(lo <= w["x0"] < hi for w in line)


def _split_gap(lines: list[list[dict]], a: int | None, b: int | None,
               below: dict[int, list[int]], above: dict[int, list[int]]) -> None:
    """Attribute the run of non-anchor lines strictly between anchors `a`
    and `b` (either may be a page edge) to whichever side they sit closer
    to, by actual vertical gap rather than an assumed even split."""
    lo = (a + 1) if a is not None else 0
    hi = b if b is not None else len(lines)
    a_bottom = max(w["bottom"] for w in lines[a]) if a is not None else None
    b_top = min(w["top"] for w in lines[b]) if b is not None else None
    for i in range(lo, hi):
        r_top = min(w["top"] for w in lines[i])
        r_bottom = max(w["bottom"] for w in lines[i])
        dist_a = (r_top - a_bottom) if a_bottom is not None else float("inf")
        dist_b = (b_top - r_bottom) if b_top is not None else float("inf")
        if a is not None and dist_a <= dist_b:
            below[a].append(i)
        elif b is not None:
            above[b].append(i)


def _parse_page(words: list[dict], page_num: int) -> list[dict]:
    words = [w for w in words if w["top"] >= _HEADER_BOTTOM]
    lines = _group_lines(words)
    anchors = [i for i, ln in enumerate(lines) if _is_anchor(ln)]
    if not anchors:
        return []
    above: dict[int, list[int]] = {i: [] for i in anchors}
    below: dict[int, list[int]] = {i: [] for i in anchors}
    boundaries = [None, *anchors, None]
    for a, b in zip(boundaries, boundaries[1:]):
        _split_gap(lines, a, b, below, above)

    records = []
    for idx in anchors:
        line = lines[idx]
        part_number = _col_text(line, _PN_COL).strip()
        if not part_number:
            continue    # every real row carries a PN; nothing to anchor on otherwise
        mpd_task_no = _col_text(line, _TASK_COL).strip()
        if mpd_task_no == "-":
            mpd_task_no = ""
        ata = _col_text(line, _ATA_COL).strip()
        if not ata and _TASK_RE.match(mpd_task_no):
            ata = mpd_task_no[:2]
        wrap_lines = [*above[idx], idx, *below[idx]]
        description = " ".join(
            t for t in (_col_text(lines[i], _DESC_COL).strip() for i in wrap_lines) if t)
        task_type = " ".join(
            t for t in (_col_text(lines[i], _TYPE_COL).strip() for i in wrap_lines) if t)
        records.append({
            "ATA": ata,
            "MPD_TASK_NO": mpd_task_no,
            "PART_NUMBER": part_number,
            "SERIAL_NUMBER": _col_text(line, _SN_COL).strip(),
            "DESCRIPTION": description,
            "POSITION": _col_text(line, _POS_COL).strip(),
            "TASK_TYPE": task_type,
            "STATUS_TRAIL": " ".join(w["text"] for w in line if w["x0"] >= _TYPE_COL[1]),
            "_page": page_num,
        })
    return records


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            records.extend(_parse_page(page.extract_words(), page_num))
    return records
