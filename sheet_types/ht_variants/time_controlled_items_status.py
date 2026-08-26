"""TIME CONTROLLED ITEMS STATUS — per-aircraft hard-time export.

Header, values genericized below but the shape is real::

    TIME CONTROLLED ITEMS STATUS
    A/C REGN A/C TYPE A/C MSN A/C DOM A/C TAH A/C TAC DATE
    <tail> A320-232 <msn> <date> <hours> <cycles> <report-date>
    IT NE oM TASK REF TASK TYPE DESCRIPTION P/N S/N FIN INTERVAL ... [a badly
    garbled multi-line-wrapped column header -- not machine-parseable, see
    below]
    50000 FH 50000 FH 13705 FH
    1 213100-08-1 RST VALVE-SAFETY 1 9024-15704-03 1032153 6HL 07-Dec-2010 0
    0 AIR 21-Dec-2010 07-Dec-2010 0 0 36295 17161
    210 MO 06-Jun-28 DT 2320 DY

Each component is nominally a repeating 3-line block: a "limit" line (one or
more `<number> FH`/`FC` tokens -- the FH/FC thresholds this component is
tracked against, sometimes 2-3 of them for the same component), a "data"
line (leading item INDEX, TASK_REF, TASK_TYPE, DESCRIPTION, P/N, S/N, FIN,
then a wide ragged block of install/last-done dates and accumulated
hour/cycle figures), and a "trailer" line (a calendar interval + due date +
remaining-days figure, `<n> MO <date> DT <n> DY`). In practice the block
shape is far less regular than that 3-line summary suggests:

- Some components carry no FH/FC-tracked limit at all (calendar-only), so
  there's no leading limit line and the interval/due-date trailer is folded
  onto the data line itself instead of getting its own line.
- Some components are tracked under two distinct TASK_REF/TASK_TYPE pairs
  (e.g. one FH-based, one calendar-based) -- one printed on the line above
  the data line (glued onto that row's own limit-line text) and the other
  on the line below (glued onto the trailer). Both get folded into this
  module's TASK_REF/TASK_TYPE fields (space-joined) rather than dropped.
- On a handful of rows, TASK_REF/TASK_TYPE/DESCRIPTION are entirely absent
  from the data line and instead sit on the line immediately above it (the
  data line then starts straight at P/N).
- `page.extract_text()`'s natural reading order badly scrambles a sizeable
  minority of rows -- both the column-header line (shown above, genuinely
  unparseable) and some component DESCRIPTION values -- because this
  format's PDF renderer occasionally prints a row's DESCRIPTION text on a
  physical line fractionally offset in y from the rest of that row's
  tokens, and pdfplumber's text-flow heuristic doesn't always reunite them
  in left-to-right order. Confirmed by comparing `extract_text()` against
  `extract_words()` with explicit x/y coordinates: the same "garbled" row
  reads out perfectly in the correct order once words are grouped by
  y-position (top) and sorted by x0, the same fix this project's
  `time_controlled_components_status.py` uses for a different symptom of
  the same root cause (an MIS PDF renderer that doesn't guarantee visual
  row order in the text stream).

This module therefore extracts words with coordinates, groups them into
physical lines by y-position (tolerant of the sub-point jitter between
words nominally on the same visual line -- this incidentally also
re-unites most row/fragment pairs that sit within ~2.5pt of each other
into one physical line automatically), and classifies each line's tokens
into fields by x-position:

  - a bare integer at the INDEX column's x-range anchors a "core" row.
  - TASK_REF sits in a narrow column just right of INDEX; TASK_TYPE
    immediately right of that.
  - DESCRIPTION / PART_NUMBER / SERIAL_NUMBER / FIN share one wide x-range
    with no further fixed sub-boundary between them (column widths are
    data-dependent, not fixed-width) -- resolved by taking the *last three*
    tokens in that range as PART_NUMBER, SERIAL_NUMBER, FIN respectively
    (in that left-to-right order, matching the header's own P/N S/N FIN
    sequence) and treating everything before them as DESCRIPTION. Verified
    against every sampled row, including ones where DESCRIPTION is empty
    (only P/N, S/N, FIN present on the core line) and ones with an
    embedded index-like token inside DESCRIPTION (e.g. "VALVE-SAFETY 1").
  - anything at or past the limit/interval column's x-position (the FH/FC
    limit line, the MO/DT/DY trailer line, and the wide ragged
    installation-date/remaining-life block on the data line itself) is
    folded verbatim into one `STATUS_TRAIL` catch-all per component --
    same project convention as `hard_time_report_config_slot.py`'s and
    `time_controlled_components_status.py`'s own trailing blocks, since
    that block's own column header is the badly garbled, effectively
    unparseable line shown above and its printed width varies row to row.

Any line that isn't itself a core row (a limit line, a trailer line, a
stray TASK_REF/TASK_TYPE/DESCRIPTION fragment that didn't get folded into
its row's own physical line by the y-tolerance above, ...) is merged into
whichever core row is vertically closest to it, mirroring
`time_controlled_components_status.py`'s orphan-merge approach. Page
footer lines ("Page N of M") are dropped rather than merged.

Row grain: one row per component/task-line block (this format's own item
INDEX numbering), matching this project's established convention for
similarly ragged repeating blocks.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.ht_variants._base import merged_rules
from shared.cleanup import normalize_dashes

NAME = "Time Controlled Items Status"
SIGNATURES = [
    "TIME CONTROLLED ITEMS STATUS",
]

CANONICAL_COLUMNS = [
    "INDEX",
    "TASK_REF",
    "TASK_TYPE",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "FIN",
    "STATUS_TRAIL",
]

_OVERRIDES = {
    "INDEX":         {"pattern": r"^\d+$"},
    "TASK_REF":      {"pattern": r"^[0-9]{6}-[0-9]{2}-[0-9]{1,2}"
                                  r"(?:\s+[0-9]{6}-[0-9]{2}-[0-9]{1,2})*$",
                       "allow_empty": True},
    "TASK_TYPE":     {"pattern": r"^[A-Z]{2,4}(?:\s+[A-Z]{2,4})*$",
                       "uppercase": True, "allow_empty": True},
    "DESCRIPTION":   {"uppercase": True, "allow_empty": True},
    "PART_NUMBER":   {"pattern": r"^[A-Z0-9][A-Z0-9\-\./]*$", "uppercase": True,
                       "allow_empty": True},
    "SERIAL_NUMBER": {"pattern": r"^[A-Z0-9][A-Z0-9\-\./]*$", "uppercase": True,
                       "allow_empty": True},
    "FIN":           {"pattern": r"^[A-Z0-9][A-Z0-9\-/]*$", "uppercase": True,
                       "allow_empty": True},
    "STATUS_TRAIL":  {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Column x-position bins (PDF points), derived from real header/body
# coordinates on the sample files.
_IDX_MIN, _IDX_MAX = 45, 66
_TASK_REF_MIN = 66
_TASK_TYPE_MIN, _TASK_TYPE_MAX = 100, 130
# Trailing (limit-line / STATUS_TRAIL) column start. Left with headroom on
# both sides of the empty gap actually observed between the widest FIN
# value (~x0 285) and the narrowest limit-line value (~x0 304) across both
# sample files, since the exact split point drifts by a couple of points
# between files (confirmed: 301 alone clipped part of one file's limit-line
# lead token into the FIN/mid region -- see also the TASK_TYPE guard below).
_TRAIL_MIN_X = 295

# TASK_TYPE codes are short (2-5 uppercase letters, e.g. "RST"/"FNC"/"DIS").
# On some rows a hyphenated multi-word DESCRIPTION starts as little as ~2pt
# right of where a TASK_TYPE code could end (e.g. "EXCHANGER-HEAT," at x0
# ~127.7 immediately after "RST" at x0 ~101.4) -- too tight a gap to trust
# x-position alone, so a token in this band is only classified as TASK_TYPE
# when its own text also looks like one of these short alpha codes;
# anything else (however short its x0) falls through to the
# DESCRIPTION/PART_NUMBER/SERIAL_NUMBER/FIN region instead.
_TASK_TYPE_RE = re.compile(r"^[A-Z]{2,5}$")

_INDEX_RE = re.compile(r"^\d+$")
_FOOTER_RE = re.compile(r"^Page\s+\d+\s+of\s+\d+$", re.I)
# The column-header line ("TASK REF TASK TYPE DESCRIPTION P/N S/N FIN
# INTERVAL ...") repeats on every page; close enough to that page's first
# data row on at least one sampled page to otherwise pass the vertical
# merge-distance check below and pollute TASK_REF/TASK_TYPE/DESCRIPTION
# with header text. "P/N" and "S/N" (both literal, both together) only
# ever appear on this header line, never as real field values, so used
# here as a cheap, reliable skip marker.
# Fragments merge only if within this many PDF points (vertically) of the
# nearest core row; unrelated page furniture (title, aircraft-info line,
# repeated column headers) sits far outside it.
_MAX_MERGE_DIST = 15.0


def _group_lines(words: list[dict]) -> list[dict]:
    """Group words into physical lines, tolerant of sub-point 'top' jitter
    between words nominally on the same visual line. This incidentally
    reunites most row/fragment pairs that sit within ~2.5pt of each other
    (see module docstring) without any extra handling."""
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
    return _IDX_MIN <= first["x0"] < _IDX_MAX and bool(_INDEX_RE.match(first["text"]))


def _line_text(line: dict) -> str:
    return " ".join(w["text"] for w in line["words"])


def _bucket(words: list[dict]) -> tuple[list[str], list[str], list[str], list[str]]:
    """Split a physical line's words into (task_ref, task_type, mid, trail)
    token lists by x-position. `mid` covers both the DESCRIPTION/PART_NUMBER/
    SERIAL_NUMBER/FIN region and any stray token left of the TASK_REF
    column (treated as description-region content rather than dropped)."""
    task_ref: list[str] = []
    task_type: list[str] = []
    mid: list[str] = []
    trail: list[str] = []
    for w in words:
        x0 = w["x0"]
        if x0 >= _TRAIL_MIN_X:
            trail.append(w["text"])
        elif _TASK_TYPE_MIN <= x0 < _TASK_TYPE_MAX and _TASK_TYPE_RE.match(w["text"]):
            task_type.append(w["text"])
        elif _TASK_REF_MIN <= x0 < _TASK_TYPE_MIN:
            task_ref.append(w["text"])
        else:
            mid.append(w["text"])
    return task_ref, task_type, mid, trail


def _row_from_core(line: dict) -> dict:
    words = line["words"]
    index = words[0]["text"]
    task_ref, task_type, mid, trail = _bucket(words[1:])
    part_number = serial_number = fin = ""
    description = ""
    if len(mid) >= 3:
        fin = mid[-1]
        serial_number = mid[-2]
        part_number = mid[-3]
        description = " ".join(mid[:-3])
    elif len(mid) == 2:
        fin = mid[-1]
        serial_number = mid[-2]
    elif len(mid) == 1:
        fin = mid[-1]
    return {
        "INDEX": index,
        "TASK_REF": " ".join(task_ref),
        "TASK_TYPE": " ".join(task_type),
        "DESCRIPTION": description,
        "PART_NUMBER": part_number,
        "SERIAL_NUMBER": serial_number,
        "FIN": fin,
        "_trail": trail,
    }


def _merge_orphan(row: dict, line: dict, core_top: float) -> None:
    before = line["top"] < core_top
    task_ref, task_type, mid, trail = _bucket(line["words"])

    def _join(existing: str, frag_tokens: list[str]) -> str:
        if not frag_tokens:
            return existing
        frag = " ".join(frag_tokens)
        if not existing:
            return frag
        return f"{frag} {existing}" if before else f"{existing} {frag}"

    row["TASK_REF"] = _join(row["TASK_REF"], task_ref)
    row["TASK_TYPE"] = _join(row["TASK_TYPE"], task_type)
    row["DESCRIPTION"] = _join(row["DESCRIPTION"], mid)
    if trail:
        row["_trail"] = (trail + row["_trail"]) if before else (row["_trail"] + trail)


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
            if not words:
                continue
            for w in words:
                w["text"] = normalize_dashes(w["text"])
            lines = _group_lines(words)

            core_lines = [ln for ln in lines if _is_core(ln)]
            if not core_lines:
                continue
            rows = [_row_from_core(ln) for ln in core_lines]
            core_tops = [ln["top"] for ln in core_lines]

            for line in lines:
                if _is_core(line):
                    continue
                text = _line_text(line)
                if _FOOTER_RE.match(text):
                    continue
                if "P/N" in text and "S/N" in text:
                    continue
                best_idx, best_dist = None, None
                for i, top in enumerate(core_tops):
                    dist = abs(line["top"] - top)
                    if best_dist is None or dist < best_dist:
                        best_idx, best_dist = i, dist
                if best_idx is None or best_dist > _MAX_MERGE_DIST:
                    continue
                _merge_orphan(rows[best_idx], line, core_tops[best_idx])

            for row in rows:
                row["STATUS_TRAIL"] = " ".join(row.pop("_trail"))
                row["_page"] = page_num
                records.append(row)
    return records
