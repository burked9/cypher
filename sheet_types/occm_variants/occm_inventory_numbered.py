"""OCCM Inventory (Numbered-Row) — word-position-based parser.

Real text layer (confirmed via pdfplumber) -- no OCR needed.

Title block (page 1 only)::

    ON CONDITION COMPONENT MONITORING STATUS
    AIRCRAFT REG / MSN  AIRCRAFT MODEL  AIRCRAFT HOURS  AIRCRAFT CYCLES  DATE AS OF
    <reg> / MSN <msn>   <model>         <hours>         <cycles>         <date>

Per-page column header::

    NO ATA PART DESCRIPTION PART NUMBER SERIAL NUMBER POSITION DATE INSTALLED TSN CSN

Per-row layout (single line when description fits)::

    <no> <ata> <description...> <pn> <sn> [<position...>] <dd/mm/yyyy> <tsn> <csn>

The "NO" column is a sequential row number starting at 1.

Multi-line descriptions: when a description is too long, it wraps onto
one or two adjacent physical lines (above and/or below the data line).
These continuation lines carry words only in the DESCRIPTION column
(x0 ~ 115) and no row number in the NO column -- detected and attached
to the nearest data row.

Position may be empty (confirmed on at least one row), single-token,
or multi-token (e.g. two-word values).

Parsing uses pdfplumber word-level extraction with x-coordinate
thresholds derived from the consistent column positions confirmed
across all pages of a known source file.
"""
from __future__ import annotations

import re
from collections import defaultdict

import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "OCCM Inventory (Numbered Row)"
SIGNATURES = [
    "ON CONDITION COMPONENT MONITORING STATUS",
    "NO ATA PART DESCRIPTION PART NUMBER SERIAL NUMBER POSITION DATE INSTALLED TSN CSN",
]

CANONICAL_COLUMNS = [
    "ATA",
    "PART_DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "POSITION",
    "DATE_INSTALLED",
    "TSN",
    "CSN",
]

_OVERRIDES: dict = {
    "PART_DESCRIPTION": {"uppercase": True},
    "POSITION": {"allow_empty": True},
    "DATE_INSTALLED": {"pattern": r"^\d{2}/\d{2}/\d{4}$"},
    "TSN": {"pattern": r"^\d+$"},
    "CSN": {"pattern": r"^\d+$"},
}
RULES = merged_rules(_OVERRIDES)

# ── Column x-boundaries (confirmed consistent across all pages) ────────
# Each column's left edge (x0) is stable; words are assigned to the
# column whose range contains their x0.
_COL_BOUNDS = [
    # (x0_min, x0_max, column_name)
    # Values derived from pdfplumber word x0 positions confirmed across
    # every page of the known source file. Column data x0 values are
    # highly consistent (NO ~75, ATA ~90.5, DESC 115-250, PN ~287,
    # SN ~404, POS ~497.6, DATE ~540.5, TSN ~608.3, CSN ~658.3).
    # Boundaries are set at the midpoint of each inter-column gap.
    (60, 88, "NO"),
    (88, 113, "ATA"),
    (113, 268, "PART_DESCRIPTION"),
    (268, 395, "PART_NUMBER"),
    (395, 485, "SERIAL_NUMBER"),
    (485, 535, "POSITION"),
    (535, 600, "DATE_INSTALLED"),
    (600, 650, "TSN"),
    (650, 800, "CSN"),
]

_HEADER_WORDS = frozenset(
    "NO ATA PART DESCRIPTION NUMBER SERIAL POSITION DATE INSTALLED TSN CSN".split()
)

_DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")


def _assign_column(x0: float) -> str | None:
    for lo, hi, name in _COL_BOUNDS:
        if lo <= x0 < hi:
            return name
    return None


def _group_by_y(words: list[dict], tol: float = 3.0) -> list[list[dict]]:
    """Group words into lines by y-position with tolerance."""
    if not words:
        return []
    sorted_words = sorted(words, key=lambda w: (w["top"], w["x0"]))
    lines: list[list[dict]] = []
    current_line: list[dict] = [sorted_words[0]]
    current_y = sorted_words[0]["top"]
    for w in sorted_words[1:]:
        if abs(w["top"] - current_y) <= tol:
            current_line.append(w)
        else:
            lines.append(current_line)
            current_line = [w]
            current_y = w["top"]
    lines.append(current_line)
    return lines


def _is_header_line(cols: dict) -> bool:
    """True if the line is the repeating column-header row."""
    all_text = " ".join(
        " ".join(cols.get(c, [])) for c in ("NO", "ATA", "PART_DESCRIPTION")
    ).upper()
    if "NO" in cols and "ATA" in cols:
        no_text = " ".join(cols["NO"]).upper()
        ata_text = " ".join(cols["ATA"]).upper()
        if no_text == "NO" and ata_text == "ATA":
            return True
    # Also catch header fragments
    word_set = set(all_text.split())
    if word_set & _HEADER_WORDS and len(word_set & _HEADER_WORDS) >= 3:
        return True
    return False


def _line_to_cols(line_words: list[dict]) -> dict[str, list[str]]:
    """Assign each word on a line to its column by x-position."""
    cols: dict[str, list[str]] = defaultdict(list)
    for w in sorted(line_words, key=lambda w: w["x0"]):
        col = _assign_column(w["x0"])
        if col:
            cols[col].append(w["text"])
    return dict(cols)


def _is_data_line(cols: dict) -> bool:
    """A data line has a numeric NO and a date in DATE_INSTALLED."""
    no_tokens = cols.get("NO", [])
    date_tokens = cols.get("DATE_INSTALLED", [])
    if not no_tokens or not date_tokens:
        return False
    if not no_tokens[0].isdigit():
        return False
    date_str = " ".join(date_tokens)
    if not _DATE_RE.match(date_str):
        return False
    return True


def _is_desc_only(cols: dict) -> bool:
    """A continuation line has words only in the DESCRIPTION column."""
    desc = cols.get("PART_DESCRIPTION", [])
    if not desc:
        return False
    other_cols = {k for k in cols if k != "PART_DESCRIPTION"}
    return len(other_cols) == 0


def _extract_page(page: pdfplumber.page.Page, page_num: int) -> list[dict]:
    words = page.extract_words()
    if not words:
        return []

    lines = _group_by_y(words)
    col_lines = [_line_to_cols(line) for line in lines]

    # Build records: pair data lines with adjacent description-only lines
    records: list[dict] = []
    consumed: set[int] = set()

    for i, cols in enumerate(col_lines):
        if _is_header_line(cols):
            consumed.add(i)
            continue
        if not _is_data_line(cols):
            continue

        desc_parts: list[str] = []
        inline_desc = " ".join(cols.get("PART_DESCRIPTION", []))

        if inline_desc:
            # Row has its own description -- no continuation lines needed.
            desc_parts.append(inline_desc)
        else:
            # Empty inline description is the reliable signal that this
            # row's description wrapped onto neighbouring bare lines
            # (confirmed on the known source file).

            # Look backwards for description continuation
            j = i - 1
            while j >= 0 and j not in consumed and _is_desc_only(col_lines[j]):
                desc_parts.insert(0, " ".join(col_lines[j]["PART_DESCRIPTION"]))
                consumed.add(j)
                j -= 1

            # Look forwards for description continuation
            k = i + 1
            while k < len(col_lines) and k not in consumed and _is_desc_only(col_lines[k]):
                desc_parts.append(" ".join(col_lines[k]["PART_DESCRIPTION"]))
                consumed.add(k)
                k += 1

        full_desc = _join_desc(desc_parts)

        rec = {
            "ATA": " ".join(cols.get("ATA", [])),
            "PART_DESCRIPTION": full_desc,
            "PART_NUMBER": " ".join(cols.get("PART_NUMBER", [])),
            "SERIAL_NUMBER": " ".join(cols.get("SERIAL_NUMBER", [])),
            "POSITION": " ".join(cols.get("POSITION", [])),
            "DATE_INSTALLED": " ".join(cols.get("DATE_INSTALLED", [])),
            "TSN": " ".join(cols.get("TSN", [])),
            "CSN": " ".join(cols.get("CSN", [])),
            "_page": page_num,
        }
        records.append(rec)

    return records


def _join_desc(parts: list[str]) -> str:
    """Join description fragments, respecting mid-word hyphen splits."""
    if not parts:
        return ""
    result = parts[0]
    for p in parts[1:]:
        if result.endswith("-"):
            result = result + p
        else:
            result = result + " " + p
    return result


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if len(text) < 20:
                continue
            records.extend(_extract_page(page, page_num))
    return records
