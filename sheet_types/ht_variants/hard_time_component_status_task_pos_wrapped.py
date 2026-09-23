"""Hard Time Component Status — two-row wrapped header layout (a small
cluster of A321 files, distinct from hard_time_component_status_mpd_task.py
despite sharing the "MPD INTERVAL AMP INTERVAL" phrase in their header).

Header (three physical lines, main column line split differently from the
sibling module above)::

    Aircraft
    AIRBUS A321-231 HOURS <hrs>
    Hard Time Component Status
    MSN <MSN> CYCLES <cyc>
    REG <tail> DATE <date>
    DOM <dom>
    MPD TASK TASK MPD INTERVAL AMP INTERVAL LAST DONE NEXT DUE REMAIN INSTALLED DATE
    ATA PART NUMBER SERIAL NUMBER PART DESCRIPTION POS
    NO TYPE DY FH FC DY FH FC DATE FH FC DATE FH FC DY FH FC DATE FH FC

The middle line here is "ATA PART NUMBER SERIAL NUMBER PART DESCRIPTION POS"
alone (no "MPD TASK NO" prefix, no "TASK TYPE" suffix on that line) — the
"NO"/"TYPE" sub-labels sit on the third line instead, and "MPD"/"TASK" (for
MPD TASK NO) sit on the first line. In the sibling module's own known-good
files, by contrast, those two labels sit on the SAME single middle line as
ATA/PART NUMBER/SERIAL NUMBER/PART DESCRIPTION/POS/TASK TYPE. The column
x-positions differ accordingly (narrower ATA/TASK/PN/SN/DESC/POS bands here),
which is why that module's fixed bounds cannot parse this layout: its
PART_NUMBER band, calibrated to this file's own DESCRIPTION+POS bands
instead, absorbs description text and drops the real part number, and its
SERIAL_NUMBER band picks up numeric interval-cell fragments instead — a
clean 100%-flagged signature collision rather than silent corruption, since
every value_pattern / format check downstream still fires.

Row example (single physical line, the common case)::

    21 213100-08-1 9024-15704-2 0172384 SAFETY VALVE <TAIL>-21-31-05-SAN OVHL 6385 50000 - 6385 50000 - 12-Apr-05 0 - 5-Oct-22 65,574 - 976 15,834 - 29-May-07 15,574 13,302

Wrap behaviour is the same idea as the sibling module: PART DESCRIPTION and
TASK TYPE are narrow enough that a long value wraps onto its own line(s),
split above/below the row's own single-line numeric cells rather than
growing the row evenly, e.g.::

    HEAT EXCHANGER,
    21 215200-01-1 753A0000-03 01164 <POS> 3285 12000 - 3285 12000 - ...
    PRIMARY                                      SHOP
                                                  CLEANING

is one row: DESCRIPTION "HEAT EXCHANGER, PRIMARY", TASK_TYPE "SHOP CLEANING"
— both wrap symmetrically, sometimes only above, sometimes only below,
occasionally with the wrap line shared between the row above and the row
below (a lone "SHOP"/"CLEANING" pair prints as the TYPE-wrap for the row
whose anchor line follows it more closely than the row whose anchor line
precedes it). Anchor: the row with a word in the SERIAL NUMBER column
(x0 125-177); PART DESCRIPTION (x0 177-239) and TASK TYPE (x0 325-358) words
on non-anchor lines are folded into whichever neighbouring anchor row they
sit closer to (by actual vertical gap, never split further — no row in the
sample needed a 3rd wrapped line on either side).

The trailing DY/FH/FC/DATE cells (MPD INTERVAL, AMP INTERVAL, LAST DONE,
NEXT DUE, REMAIN, INSTALLED DATE — one more trailing group than the sibling
module's own files have) sit on the row's own anchor line and are kept as
one STATUS_TRAIL string rather than mis-sliced into named cells, same
rationale as the sibling module: a blank/short cell can shift a neighbour by
roughly a cell width and there is no reliable way to re-anchor mid-trail.

A rare source-PDF artifact seen once in the sample: a single row prints with
every character double-struck (a bold-simulation technique — the same glyph
run painted twice at a near-zero offset), which pdfplumber's word merging
turns into a doubled string ("756A0000-06" -> "775566AA00000000--0066").
This is not a parsing bug; MPD_TASK_NO's own strict pattern override (below)
and the global ATA pattern both fail to match the doubled text, so the row
is flagged rather than silently passed through.

Corpus: a small cluster of files sharing this exact two-row-wrapped header
shape and these exact x0 column bounds.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.ht_variants._base import merged_rules

NAME = "Hard Time Component Status (Task/Pos Wrapped Header)"
SIGNATURES = [
    "ATA PART NUMBER SERIAL NUMBER PART DESCRIPTION POS",
    "MPD TASK TASK MPD INTERVAL",
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
# page checked in the sample file). Narrower than the sibling module's own
# bounds -- this layout's ATA/TASK/PN/SN/DESC/POS/TYPE cells all sit further
# left, with a bigger trailing STATUS_TRAIL block (one extra DATE/FH/FC
# group: INSTALLED DATE).
_ATA_COL = (14, 33)
_TASK_COL = (33, 75)
_PN_COL = (75, 125)
_SN_COL = (125, 177)
_DESC_COL = (177, 239)
_POS_COL = (239, 325)
_TYPE_COL = (325, 358)

_TASK_RE = re.compile(r"^\d{6}-[A-Z0-9]{1,3}-\d{1,2}$")
# Third header sub-row ("NO TYPE DY FH FC ...") bottoms out below this on
# every page checked; data rows start after it. Filtering here also drops
# the repeated "ATA PART NUMBER SERIAL NUMBER PART DESCRIPTION POS" column
# header line itself, which would otherwise false-positive as an anchor
# (its "SERIAL"/"NUMBER" words sit inside the SERIAL NUMBER column's x0
# range).
_HEADER_BOTTOM = 76


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
