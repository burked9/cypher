"""OC/CM Status (by ATA chapter) -- born-digital, full text layer, coordinate-
bucketed columns (same technique as `occm_report.py` / `occm_summary_list.py`).

Confirmed on one real file in the corpus (clean text layer via pdfplumber
`extract_text()`/`extract_words()` on every page)::

    <date>
    OC/CM status
    <reg> <msn> FH: <n> FC: <n>
    NO DESCRIPTION P/N S/N POS DATE INSTALLED TSN CSN
    ATA <n> - <chapter description>
    <no> <description> <pn> <sn> <pos> <date> <tsn> <csn>
    <no> <description> <pn> <sn> <pos> <date> <tsn> <csn>

Rows are grouped under repeated "ATA <n> - <description>" section-heading
lines rather than carrying ATA as a per-row column. The heading text is
NOT forward-filled by the generic `forward_fill_ata()` post-process in
`sheet_types/occm.py` (that helper expects a bare 2-digit `ATA` column, not
a full heading string) -- this module forward-fills its own `ATA_CHAPTER`
field onto every row beneath a heading itself, as the running heading text
is read one section at a time while walking the page/row stream in
document order.

This is a genuinely different column layout from another "OC/CM status"
singleton seen the same day (`<reg>`/`<msn>`-flavoured, flat columns
DESCRIPTION/P/N/S/N/ATA/POS/DATE INSTALLED/AIRCRAFT TIME/TSI/TSN with ATA
as an inline per-row column, no section headings) -- confirmed by direct
inspection of this format's real source file, which instead has NO as its
leading per-row column, a distinct 8-column header line
("NO DESCRIPTION P/N S/N POS DATE INSTALLED TSN CSN"), and ATA carried
only as a section heading. That column-header line is this module's
detection anchor precisely because it does not appear in the sibling
format.

Column x-boundaries (PDF points), derived from real header + data-row word
coordinates on the known source file -- consistent across every inspected
page:
    NO | DESCRIPTION | PART_NUMBER | SERIAL_NUMBER | POS | DATE_INSTALLED |
    TSN | CSN
A section-heading line ("ATA <n> - ...") starts with a literal "ATA" token
that lands well to the right of the NO column -- it is detected by that
leading token, not by x-position, and is never itself bucketed as a data
row.

Row anchoring is more involved than a simple leading-NO-digit test, because
the known source file has two real (non-error) row shapes:

  1. The common case -- NO, DESCRIPTION, PART_NUMBER, SERIAL_NUMBER, POS,
     DATE_INSTALLED, TSN, CSN all print on one physical line.

  2. A confirmed real quirk -- some component instances print with NO left
     blank (never a stray render error: PART_NUMBER/SERIAL_NUMBER/
     DATE_INSTALLED/TSN/CSN are all still fully populated on that line, and
     the surrounding rows' own NO values are sequential and undisturbed).
     Seen repeatedly across the file (extra galley-oven/actuator/light/
     antenna/snubber/elevator instances sharing an outer item's
     description). A blank-NO line with both PART_NUMBER and
     SERIAL_NUMBER populated is therefore *also* treated as a new row
     (with NO left empty) rather than folded into the previous row --
     folding it in would silently corrupt two real components' data into
     one record.

Long field values occasionally wrap across physical lines -- confirmed
twice on the known source file, in each case splitting NO+DESCRIPTION(+a
POS prefix) onto one line and PART_NUMBER+SERIAL_NUMBER+DATE_INSTALLED+
TSN+CSN(+a POS suffix) onto the next (occasionally a third line carrying
only a POS tail). Handled as: a blank-NO, PART_NUMBER+SERIAL_NUMBER-bearing
line is folded into the previous row instead of starting a new one when
that previous row is itself still missing PART_NUMBER or SERIAL_NUMBER
(i.e. it's this row's own overflow, not an unrelated extra instance); any
further non-anchor line within normal row spacing is folded in as trailing
overflow the same way `occm_report.py` handles it. A single further rare
case -- a fragment of one row's DESCRIPTION printing ahead of that row's
own anchor line (occm_report.py's "leading overflow") -- is not specially
handled here (confirmed only once in the whole known source file) and
lands, imperfectly, on the preceding row's POS field instead; soft
validation flags it rather than silently guessing a corrected split.

TSN/CSN are frequently the literal string ``UNKNOWN`` instead of a number
(confirmed real data on the known source file, not a parse failure).

File-level header metadata (<date>, aircraft reg, MSN, flight hours,
flight cycles) is parsed once from the first page's top block and stamped
onto every row as REPORT_DATE / AIRCRAFT_REG / MSN / AIRCRAFT_FH /
AIRCRAFT_FC, mirroring the header-metadata-stamping convention used
elsewhere in this project (e.g. several `llp_variants/*.py` modules'
AIRCRAFT_REG/MSN/REPORT_DATE handling).
"""
from __future__ import annotations
import re

import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "OC/CM Status By ATA Chapter"

SIGNATURES = [
    # This module's own column-header line -- confirmed distinct from the
    # sibling "OC/CM status" format's own header line (see module
    # docstring), and checked for collisions against every SIGNATURES list
    # in sheet_types/{occm,ht,llp}.py and every existing variant file.
    "NO DESCRIPTION P/N S/N POS DATE INSTALLED TSN CSN",
]

CANONICAL_COLUMNS = [
    "NO",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "POS",
    "DATE_INSTALLED",
    "TSN",
    "CSN",
    "ATA_CHAPTER",
    # File-level metadata -- same on every row.
    "AIRCRAFT_REG",
    "MSN",
    "REPORT_DATE",
    "AIRCRAFT_FH",
    "AIRCRAFT_FC",
]

_OVERRIDES = {
    # NO is blank on a confirmed subset of real rows (see module docstring)
    # -- not a failure to flag.
    "NO":             {"pattern": r"^\d*$", "allow_empty": True},
    "POS":            {"pattern": r"^[A-Z0-9/.#\- ]{1,25}$", "uppercase": True,
                        "allow_empty": True},
    "DATE_INSTALLED": {"pattern": r"^\d{1,2}-[A-Za-z]{3}-\d{2,4}$"},
    "TSN":            {"pattern": r"^(?:\d+|UNKNOWN)$"},
    "CSN":            {"pattern": r"^(?:\d+|UNKNOWN)$"},
    # Section-heading text, forward-filled onto every row -- free-form after
    # the "ATA <n>" prefix (confirmed one real chapter heading in the
    # corpus omits the space before its dash, e.g. "ATA 80- STARTING").
    "ATA_CHAPTER":    {"pattern": r"^ATA\s+\d{2}\b.*$", "uppercase": True},
    "AIRCRAFT_REG":   {"pattern": r"^[A-Z0-9\-]+$", "uppercase": True, "allow_empty": True},
    "MSN":            {"pattern": r"^\d+$", "allow_empty": True},
    "REPORT_DATE":    {"pattern": r"^\d{2}\.\d{2}\.\d{4}$", "allow_empty": True},
    "AIRCRAFT_FH":    {"pattern": r"^\d+$", "allow_empty": True},
    "AIRCRAFT_FC":    {"pattern": r"^\d+$", "allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Column x-boundaries (PDF points): NO | DESCRIPTION | PART_NUMBER |
# SERIAL_NUMBER | POS | DATE_INSTALLED | TSN | CSN. The DESCRIPTION/
# PART_NUMBER boundary sits in an unusually tight ~6pt gap (186.2 vs
# 192.5 in real observed word x0s) because PART_NUMBER is a right-aligned
# column and some real part numbers are long enough (14-15 chars) to
# start almost as far left as a genuine DESCRIPTION overflow word can
# reach -- both extremes were confirmed directly against real word
# coordinates before picking 189 as the split.
_BOUNDS = [0, 34, 189, 275, 340, 388, 460, 503, 10**6]
_FIELDS = [
    "NO", "DESCRIPTION", "PART_NUMBER", "SERIAL_NUMBER", "POS",
    "DATE_INSTALLED", "TSN", "CSN",
]

_NO_RE = re.compile(r"^\d+$")
# Row spacing on the known source file's data grid is ~9.3pt; a genuine
# overflow fragment sits well inside that, so a much larger gap (e.g. a
# section break or unrelated stray line) is not mistaken for one and
# merged into the wrong row.
_MAX_LINE_GAP = 20.0

_REPORT_DATE_RE = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")
_HEADER_META_RE = re.compile(
    r"^(?P<reg>[A-Z0-9\-]+)\s+(?P<msn>\d+)\s+FH:\s*(?P<fh>\d+)\s+FC:\s*(?P<fc>\d+)$"
)


def _bucket(x0: float) -> str:
    for i in range(len(_BOUNDS) - 1):
        if _BOUNDS[i] <= x0 < _BOUNDS[i + 1]:
            return _FIELDS[i]
    return _FIELDS[-1]


def _group_lines(words: list[dict]) -> list[dict]:
    """Cluster words into physical lines by y-position (tolerant of
    sub-point 'top' jitter between words nominally on the same visual
    line), same technique as `occm_report.py` / `occm_summary_list.py`."""
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


def _is_ata_header(line: dict) -> bool:
    """A section-heading line's leftmost word is the literal token "ATA",
    printed well to the right of the NO column -- confirmed on every
    inspected chapter heading in the known source file, and never the
    leading word of a genuine data row."""
    if not line["words"]:
        return False
    return line["words"][0]["text"] == "ATA"


def _has_no_leader(line: dict) -> bool:
    """A real data row's leftmost word is a bare-integer NO token landing
    in the NO column's x-range."""
    if not line["words"]:
        return False
    first = line["words"][0]
    return bool(_NO_RE.match(first["text"])) and _bucket(first["x0"]) == "NO"


def _has_full_component(line: dict) -> bool:
    """PART_NUMBER and SERIAL_NUMBER buckets both populated -- looks like a
    complete component instance even without its own NO. Confirmed real
    overflow fragments (a wrapped POS/DESCRIPTION tail) never carry both
    at once -- see module docstring."""
    buckets = {_bucket(w["x0"]) for w in line["words"]}
    return "PART_NUMBER" in buckets and "SERIAL_NUMBER" in buckets


def _bucket_line(line: dict) -> dict:
    row = {f: "" for f in _FIELDS}
    for w in line["words"]:
        field = _bucket(w["x0"])
        row[field] = (row[field] + " " + w["text"]).strip()
    return row


def _row_incomplete(row: dict) -> bool:
    return not row["PART_NUMBER"] or not row["SERIAL_NUMBER"]


def _merge_fragment(row: dict, frag: dict) -> None:
    for field, text in frag.items():
        if not text:
            continue
        row[field] = f"{row[field]} {text}".strip() if row[field] else text


def _extract_page(page, state: dict) -> list[dict]:
    words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
    if not words:
        return []
    lines = _group_lines(words)

    rows: list[dict] = []
    for i, line in enumerate(lines):
        if _is_ata_header(line):
            state["ata_chapter"] = " ".join(w["text"] for w in line["words"])
            state["started"] = True
            continue
        if not state.get("started"):
            # Front-matter above the first ATA heading (date/title line,
            # the "<reg> <msn> FH:/FC:" line, the column-header line) --
            # never real data, and the reg/msn/FH/FC line in particular
            # would otherwise pass the full-component test below (its
            # reg and MSN tokens land in the PART_NUMBER/SERIAL_NUMBER
            # x-ranges by coincidence).
            continue

        close_gap = bool(rows) and i > 0 and (line["top"] - lines[i - 1]["top"]) <= _MAX_LINE_GAP

        if _has_no_leader(line):
            row = _bucket_line(line)
            row["ATA_CHAPTER"] = state["ata_chapter"]
            rows.append(row)
        elif close_gap and rows and _row_incomplete(rows[-1]) and _has_full_component(line):
            # This row's own overflow onto a second physical line (see
            # module docstring) -- not an unrelated extra instance.
            _merge_fragment(rows[-1], _bucket_line(line))
        elif _has_full_component(line):
            # A confirmed real quirk: an extra component instance with no
            # NO of its own (see module docstring) -- a genuine additional
            # row, not overflow of the previous one.
            row = _bucket_line(line)
            row["ATA_CHAPTER"] = state["ata_chapter"]
            rows.append(row)
        elif close_gap:
            # Trailing overflow of the most recently started row (e.g. a
            # long POS value spilling onto its own line).
            _merge_fragment(rows[-1], _bucket_line(line))
        # else: unanchored noise with nothing to attach to (e.g. the
        # page-1 title block) -- dropped rather than guessed onto a row.
    return rows


def _parse_header_meta(first_page_text: str) -> dict:
    """Parse the fixed top-of-file block:
        <date>
        OC/CM status
        <reg> <msn> FH: <n> FC: <n>
    Returns whatever fields are found; missing fields are simply absent
    from the dict (never guessed)."""
    meta: dict[str, str] = {}
    lines = [l.strip() for l in first_page_text.splitlines() if l.strip()]
    for line in lines[:5]:
        m = _REPORT_DATE_RE.match(line)
        if m and "REPORT_DATE" not in meta:
            meta["REPORT_DATE"] = line
            continue
        m = _HEADER_META_RE.match(line)
        if m:
            meta["AIRCRAFT_REG"] = m.group("reg")
            meta["MSN"] = m.group("msn")
            meta["AIRCRAFT_FH"] = m.group("fh")
            meta["AIRCRAFT_FC"] = m.group("fc")
    return meta


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    state = {"ata_chapter": "", "started": False}
    meta: dict[str, str] = {}
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if page_num == 1:
                meta = _parse_header_meta(text)
            for row in _extract_page(page, state):
                row["_page"] = page_num
                for key, val in meta.items():
                    row[key] = val
                records.append(row)
    return records
