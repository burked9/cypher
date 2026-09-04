"""OCCM component list, born-digital sibling of `occm_report_scanned.py` --
same 6-column grid, real text layer, no OCR needed.

Confirmed on one real file in the corpus (full clean text layer via
pdfplumber `extract_text()`/`extract_words()` on every page) -- a
multi-page A-series-airframe component listing with the same simple
ruled grid as the scanned variant's known source file::

    MSN <n> <mon>-<yyyy>
    ATA INSTALL DATE POSITION PN SN DESCRIPTION
    21 <date> <position> LT <pn> <sn> MACHINE, AIR CYCLE (LHT)
    21 <date> <position> RT <pn> <sn> MACHINE, AIR CYCLE (LHT)
    21 <date> <position> RT <pn> <sn> VALVE-FLOW CONTROL (LHT)

POSITION is variable-width in plain whitespace-split terms -- it can be one
token ("22HQ") or several ("35HN ONLY", "14HG RT", "1CA1 LT", "CON27 2 LT").
Rather than guess a token count, this module extracts words with x/y
coordinates and buckets each physical line's words into the 6 columns by
x-position (same technique as `ht_variants/time_controlled_components_status.py`),
so a multi-word POSITION lands in one field regardless of how many tokens
it has.

Two kinds of line-wrap are confirmed on the known source file when a field
is too wide for its column:

  1. Trailing overflow -- the common case. The row's own ATA/date/POSITION/
     PN/SN/DESCRIPTION print on one physical line as usual, and a long
     POSITION or DESCRIPTION value spills its tail onto the very next
     physical line, still left-aligned to that field's own column, e.g.::

         27 <date> <position> <pn> <sn> ACTUATOR-ROTARY, SLAT B (LHT)
         RT INBD

     ("RT INBD" is the rest of that row's POSITION value, landing in the
     POSITION column's x-range on its own line.) Handled by merging any
     non-anchor line into the *preceding* row when it carries no ATA-column
     token of its own.

  2. Leading overflow -- rare (confirmed twice in the one known source
     file, both on the same recurring long DESCRIPTION value), and
     genuinely awkward: the row's ATA chapter and the *start* of its
     DESCRIPTION print BEFORE the row's own date/POSITION/PN/SN line, e.g.::

         22 FMGC, FLIGHT MANAGEMENT & GUIDANCE
         COMPUTER (LHT) UPGRADE FMGC OBRM IAW
         <date> <position> LT <pn> <sn> SB A20-22-1545

     Here the row's real anchor (a date-shaped token) only appears on the
     third physical line. A line carrying a bare ATA-column token with no
     date on it is never itself a real row -- it is always the start of a
     following row's overflow -- so any such line, together with any
     further non-anchor lines before the next dated line, is merged
     forward into the *following* row instead (ATA and the DESCRIPTION
     prefix are recovered from it; per this project's "never guess a wrong
     split" rule, a run with no following dated line on the same page --
     e.g. right at a page boundary -- is dropped rather than guessed onto
     an unrelated row).

Row anchor: a token matching `D/Mon/YY` (1-2 digit day, 3-letter month, 2-4
digit year) anywhere on the physical line -- confirmed present on every
real data row, including both wrap cases above, and never present on a
pure overflow fragment. ATA is deliberately NOT used as the anchor, since
leading-overflow lines can carry a bare ATA token with no date at all.

A page-corner "DRAFT" watermark reprints on every page of the known source
file, far left and pinned to the bottom margin (well below any real data
row); it is dropped by position rather than by matching the literal word,
so a genuine part description that happened to contain the same word would
not be affected.
"""
from __future__ import annotations
import re

import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "OCCM Report"

SIGNATURES = [
    "ATA INSTALL DATE POSITION PN SN DESCRIPTION",
]

CANONICAL_COLUMNS = [
    "ATA",
    "INSTALL_DATE",
    "POSITION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
]

_OVERRIDES = {
    "POSITION":      {"allow_empty": True},
    "PART_NUMBER":   {"allow_empty": True},
    "SERIAL_NUMBER": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Column x-boundaries (PDF points), derived from real header + data-row word
# coordinates on the known source file -- consistent across every inspected
# page (a wide gap with no words in it separates each pair of columns).
# ATA | INSTALL_DATE | POSITION | PART_NUMBER | SERIAL_NUMBER | DESCRIPTION.
_BOUNDS = [0, 70, 130, 208, 275, 365, 10**6]
_FIELDS = ["ATA", "INSTALL_DATE", "POSITION", "PART_NUMBER", "SERIAL_NUMBER", "DESCRIPTION"]

_DATE_RE = re.compile(r"^\d{1,2}/[A-Za-z]{3}/\d{2,4}$")
_ATA_RE = re.compile(r"^\d{1,2}$")
# Row spacing on the known source file's data grid is ~12pt; a genuine
# overflow fragment sits well inside that, so a much larger gap (e.g. a
# section break) is not mistaken for one and merged into the wrong row.
_MAX_LINE_GAP = 20.0
_WATERMARK_TOP_FRAC = 0.90


def _bucket(x0: float) -> str:
    for i in range(len(_BOUNDS) - 1):
        if _BOUNDS[i] <= x0 < _BOUNDS[i + 1]:
            return _FIELDS[i]
    return "DESCRIPTION"


def _group_lines(words: list[dict], page_height: float) -> list[dict]:
    """Cluster words into physical lines by y-position (tolerant of
    sub-point 'top' jitter between words nominally on the same visual
    line), dropping the page-corner watermark by position."""
    kept = [w for w in words if not (w["text"] == "DRAFT" and w["top"] > page_height * _WATERMARK_TOP_FRAC)]
    ws = sorted(kept, key=lambda w: (w["top"], w["x0"]))
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


def _is_anchor(line: dict) -> bool:
    return any(_DATE_RE.match(w["text"]) for w in line["words"])


def _has_ata_token(line: dict) -> bool:
    return any(_bucket(w["x0"]) == "ATA" and _ATA_RE.match(w["text"]) for w in line["words"])


def _bucket_line(line: dict) -> dict:
    row = {f: "" for f in _FIELDS}
    for w in line["words"]:
        field = _bucket(w["x0"])
        row[field] = (row[field] + " " + w["text"]).strip()
    return row


def _extract_page(page) -> list[dict]:
    words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
    if not words:
        return []
    lines = _group_lines(words, page.height)

    rows: list[dict] = []
    pending_forward: list[dict] = []  # leading-overflow fragments awaiting the next anchor
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if _is_anchor(line):
            row = _bucket_line(line)
            # Fold in any leading-overflow fragments collected before this
            # anchor (rare wrap case -- see module docstring). Each fold
            # prepends, so fragments are walked newest-first (closest to
            # the anchor) to land the chronologically-earliest fragment
            # leftmost in the final text.
            for frag in reversed(pending_forward):
                for field, text in frag.items():
                    if not text:
                        continue
                    row[field] = f"{text} {row[field]}".strip() if row[field] else text
            pending_forward = []
            rows.append(row)
        elif _has_ata_token(line):
            # Start (or continuation) of a leading-overflow run for the
            # *next* anchor -- hold it rather than attaching to whatever
            # row came before, since it belongs to a row we haven't seen
            # the anchor line for yet.
            pending_forward.append(_bucket_line(line))
        elif rows and not pending_forward and (line["top"] - lines[i - 1]["top"]) <= _MAX_LINE_GAP:
            # Trailing overflow of the most recently closed row (common
            # case -- see module docstring).
            frag = _bucket_line(line)
            for field, text in frag.items():
                if not text:
                    continue
                rows[-1][field] = f"{rows[-1][field]} {text}".strip() if rows[-1][field] else text
        elif pending_forward:
            # Mid-run continuation of an in-progress leading-overflow run
            # (e.g. the second physical line of a wrapped DESCRIPTION
            # before the anchor line finally appears).
            pending_forward.append(_bucket_line(line))
        # else: unanchored noise with nothing to attach to (e.g. a page
        # title/header line) -- dropped rather than guessed onto a row.
        i += 1

    # A leading-overflow run with no following anchor on this page (e.g.
    # right at a page break) can't be safely placed -- drop it rather than
    # guessing which row it belongs to.
    return rows


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            for row in _extract_page(page):
                row["_page"] = page_num
                records.append(row)
    return records
