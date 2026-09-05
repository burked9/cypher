"""Components List (Status Matrix) OCCM -- born-digital, full text layer,
3-physical-lines-per-row dense status matrix.

Confirmed on one real file in the corpus (clean text layer via pdfplumber
`extract_text()`/`extract_words()` on every page). Page header block::

    Components List
    Plane <reg> TS Util <n> TSN <n>
    To Date <date> CS Util <n> CSN <n>

...followed by a genuinely ambiguous 4-line column-group header that
repeats on every page::

    Airplane / At Inst / At Inst / Ctrl Type / Next Inspection
    ATA / Full ATA code / PN / TSN / TSN / TSO / HRS / HRS / TSN / TSO / HRS / Source
    Description / ManufSN / CSN / CSN / CSO / CLS / CLS / CSN / CSO / CLS
    Pos / InstDate / OvhDateDSO / Days / Days / DSO / Days / Due Date

Each component occupies exactly 3 physical data lines beneath that header
(confirmed across every page of the known source file -- 857/857 rows
parsed at exactly 3 lines each once the ATA-anchor regex was widened to
accept any all-digit token, see below). Word x-position clustering
(same coordinate-bucketing technique used by `occm_report.py` /
`occm_status_by_ata_chapter.py`) shows the row's 3 lines share two fixed
left-hand columns and otherwise expand into a wide bank of numeric
sub-columns whose header labels ("TSN"/"CSN"/"TSO"/"CSO"/"HRS"/"CLS")
repeat 2-3x across different sub-groups (at-install, remaining, next
inspection) with NO reliable per-file anchor to tell one repeat of "TSN"
apart from another purely from the header text. Example (values
genericized; token shapes preserved, none copied verbatim from the real
file)::

    <ata> <pn> <n>
    <description words...> <manufsn> <n> <n>
    <pos> <n.n.yyyy>

Rather than guess which numeric slot is "at-install TSN" vs "next
inspection TSN" vs "CSN" etc (this project's "never guess a wrong split"
convention -- a wrong guess here would silently mislabel utilization
figures), only the two left-hand columns are extracted as clean fields
per physical line:
    Line 1 (ATA line):         ATA far-left, PART_NUMBER at the shared
                                mid column.
    Line 2 (Description line): DESCRIPTION far-left (variable word count),
                                MANUF_SN at the same shared mid column.
    Line 3 (Pos/date line):    no clean left-hand fields (Pos and dates
                                share the same ambiguous mid/right bank).
Everything else -- all of the TSN/CSN/TSO/CSO/HRS/CLS numeric bank on
lines 1-2, the "Source" annotation, and the whole of line 3 (Pos,
InstDate, OvhDate, Due Date) -- is kept verbatim as a single
STATUS_TRAIL catch-all field (pipe-separated per source line, left-to-
right word order preserved) rather than split into columns that could be
wrong.

File-level header metadata (aircraft registration, TS/CS utilization,
TSN/CSN, report "to" date) repeats verbatim on every page and is parsed
once from the first page, then stamped onto every row as AIRCRAFT_REG /
TS_UTIL / TSN / TO_DATE / CS_UTIL / CSN -- the header-metadata-stamping
convention used elsewhere in this project (e.g. `occm_status_by_ata_
chapter.py`'s AIRCRAFT_REG/MSN/REPORT_DATE handling, several
`llp_variants/*.py` modules).

One real anomaly confirmed in the corpus: a single row's ATA-line leading
token was a 5-digit value instead of the usual 2-digit ATA chapter code
(kept as-is and left to the global ATA rule's soft `bad_format`/
`out_of_range` flag -- this project drops nothing, it only flags). The
anchor regex therefore matches any all-digit token in the ATA column's
x-range, not just 2-digit ones, so that row isn't silently merged into
its neighbour.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "Components List (Status Matrix)"

SIGNATURES = [
    # This module's own 4-line column-group header -- each of these lines
    # is a distinctive, exact-order word sequence unique to this template
    # (checked for collisions against every SIGNATURES list in
    # sheet_types/{occm,ht,llp}.py and every existing variant file: no
    # hits for "Full ATA code", "Ctrl Type", "OvhDateDSO", or
    # "Pos InstDate OvhDateDSO" anywhere else in the project).
    "ATA Full ATA code PN TSN TSN TSO HRS HRS TSN TSO HRS Source",
    "Pos InstDate OvhDateDSO",
]

CANONICAL_COLUMNS = [
    "ATA",
    "PART_NUMBER",
    "DESCRIPTION",
    "MANUF_SN",
    "STATUS_TRAIL",
    # File-level metadata -- same on every row.
    "AIRCRAFT_REG",
    "TS_UTIL",
    "TSN",
    "TO_DATE",
    "CS_UTIL",
    "CSN",
]

_OVERRIDES = {
    # MANUF_SN charset confirmed across the known source file: uppercase
    # alphanumerics plus a small set of separator/annotation characters
    # ('-', '/', '*', parentheses, '#'). Kept permissive and allow_empty --
    # this field is not cross-checked against any master list.
    "MANUF_SN": {
        "pattern": r"^[A-Z0-9#/().*\-]+$",
        "uppercase": True,
        "allow_empty": True,
    },
    "STATUS_TRAIL": {"allow_empty": True},
    "AIRCRAFT_REG": {"pattern": r"^[A-Z0-9\-]+$", "uppercase": True, "allow_empty": True},
    "TS_UTIL": {"pattern": r"^[\d.]+$", "allow_empty": True},
    "TO_DATE": {"pattern": r"^\d{1,2}\.\d{1,2}\.\d{4}$", "allow_empty": True},
    "CS_UTIL": {"pattern": r"^[\d.]+$", "allow_empty": True},
    "CSN": {"pattern": r"^[\d.]+$", "allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Left-hand column x-boundaries (PDF points), derived from real header +
# data-row word coordinates on the known source file -- consistent across
# every inspected page. Anything at or beyond _MID_END falls into the wide,
# deliberately-unsplit numeric bank (STATUS_TRAIL).
_LEFT_END = 160.0   # ATA / DESCRIPTION column
_MID_END = 205.0    # PN / ManufSN / Pos column
_ANCHOR_X_MAX = 60.0  # ATA token must land in the far-left column

_ATA_ANCHOR_RE = re.compile(r"^\d+$")

_HEADER_PLANE_RE = re.compile(
    r"^Plane\s+(?P<reg>\S+)\s+TS\s+Util\s+(?P<ts_util>[\d.]+)\s+TSN\s+(?P<tsn>[\d.]+)$"
)
_HEADER_TODATE_RE = re.compile(
    r"^To\s+Date\s+(?P<to_date>\S+)\s+CS\s+Util\s+(?P<cs_util>[\d.]+)\s+CSN\s+(?P<csn>[\d.]+)$"
)

_HEADER_LINE_PREFIXES = (
    "Components List",
    "Plane ",
    "To Date",
    "Airplane At Inst",
    "ATA Full ATA code",
    "Description ManufSN",
    "Pos InstDate",
)
_FOOTER_RE = re.compile(r"^\d{1,2}\.\d{1,2}\.\d{4}\s+Page\s+\d+\s+of\s+\d+$")


def _group_lines(words: list[dict]) -> list[list[dict]]:
    """Cluster words into physical lines by y-position. Uses a fixed
    reference top per cluster (the first word's `top`) rather than a
    running mean -- a running mean drifts enough on this file's dense grid
    to wrongly split a single visual line into several one-word clusters."""
    ws = sorted(words, key=lambda w: (round(w["top"]), w["x0"]))
    lines: list[list[dict]] = []
    cur: list[dict] = []
    ref_top: float | None = None
    for w in ws:
        if cur and abs(w["top"] - ref_top) > 3.0:
            lines.append(cur)
            cur = []
            ref_top = None
        cur.append(w)
        if ref_top is None:
            ref_top = w["top"]
    if cur:
        lines.append(cur)
    for line in lines:
        line.sort(key=lambda w: w["x0"])
    return lines


def _line_text(line: list[dict]) -> str:
    return " ".join(w["text"] for w in line)


def _is_header_or_footer(text: str) -> bool:
    if _FOOTER_RE.match(text):
        return True
    return any(text.startswith(pfx) for pfx in _HEADER_LINE_PREFIXES)


def _is_anchor(line: list[dict]) -> bool:
    first = line[0]
    return first["x0"] < _ANCHOR_X_MAX and bool(_ATA_ANCHOR_RE.match(first["text"]))


def _split_line(line: list[dict]) -> tuple[str, str, list[str]]:
    """Split one physical line into (left_col, mid_col, trailing_tokens)
    by x-position, per this module's fixed column boundaries."""
    left_toks = [w["text"] for w in line if w["x0"] < _LEFT_END]
    mid_toks = [w["text"] for w in line if _LEFT_END <= w["x0"] < _MID_END]
    trail_toks = [w["text"] for w in line if w["x0"] >= _MID_END]
    return " ".join(left_toks), " ".join(mid_toks), trail_toks


def _parse_record(lines: list[list[dict]], page_num: int) -> dict:
    ata_line = lines[0]
    ata_text, pn, ata_trail = _split_line(ata_line)

    desc = ""
    manuf_sn = ""
    desc_trail: list[str] = []
    if len(lines) > 1:
        desc, manuf_sn, desc_trail = _split_line(lines[1])

    trail_parts: list[str] = []
    if ata_trail:
        trail_parts.append(" ".join(ata_trail))
    if desc_trail:
        trail_parts.append(" ".join(desc_trail))
    for extra_line in lines[2:]:
        text = _line_text(extra_line)
        if text:
            trail_parts.append(text)

    return {
        "ATA": ata_text,
        "PART_NUMBER": pn,
        "DESCRIPTION": desc,
        "MANUF_SN": manuf_sn,
        "STATUS_TRAIL": " | ".join(trail_parts),
        "_page": page_num,
    }


def _extract_page_records(page, page_num: int) -> list[dict]:
    words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
    if not words:
        return []
    lines = _group_lines(words)

    data_lines = [ln for ln in lines if not _is_header_or_footer(_line_text(ln))]

    records: list[dict] = []
    cur: list[list[dict]] | None = None
    for ln in data_lines:
        if _is_anchor(ln):
            if cur is not None:
                records.append(_parse_record(cur, page_num))
            cur = [ln]
        else:
            if cur is None:
                # Unanchored noise before the first anchor on this page
                # (shouldn't happen once header/footer lines are excluded,
                # but dropped rather than guessed onto a row if it does).
                continue
            cur.append(ln)
    if cur is not None:
        records.append(_parse_record(cur, page_num))
    return records


def _parse_header_meta(first_page_text: str) -> dict:
    """Parse the fixed top-of-page block:
        Plane <reg> TS Util <n> TSN <n>
        To Date <date> CS Util <n> CSN <n>
    Returns whatever fields are found; missing fields are simply absent
    from the dict (never guessed). Repeats verbatim on every page, but is
    only parsed once (from page 1) per this project's header-metadata
    convention."""
    meta: dict[str, str] = {}
    for line in first_page_text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = _HEADER_PLANE_RE.match(line)
        if m:
            meta["AIRCRAFT_REG"] = m.group("reg")
            meta["TS_UTIL"] = m.group("ts_util")
            meta["TSN"] = m.group("tsn")
            continue
        m = _HEADER_TODATE_RE.match(line)
        if m:
            meta["TO_DATE"] = m.group("to_date")
            meta["CS_UTIL"] = m.group("cs_util")
            meta["CSN"] = m.group("csn")
    return meta


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    meta: dict[str, str] = {}
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if page_num == 1 or not meta:
                found = _parse_header_meta(text)
                if found:
                    meta = found
            for row in _extract_page_records(page, page_num):
                for key, val in meta.items():
                    row[key] = val
                records.append(row)
    return records
