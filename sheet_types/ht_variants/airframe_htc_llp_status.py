"""AIRFRAME HTC/LLP STATUS -- born-digital, real ruled (bordered) table.

Header (page 1 only)::

    AIRFRAME HTC/LLP STATUS <operator name>
    AIRCRAFT TYPE:<type> DATE:<dd.mm.yyyy> <hh:mm>
    MSN: <msn> Current aircraft FH<hours>
    DOM:<dd-mm-yyyy> Current aircraft FC<cycles>
    REG (TAIL) NUMBER<tail>

followed by the main ruled data table, one header row, repeated verbatim
at the top of every page::

    ATA chapter | MP Item | System Reference | PART DESCRIPTION | P/N |
    S/N | Position | Task description | Threshold | Interval/Life limit
    DIM | Install Date | Since NEW/Since LSV Days/FH/FC | Next due |
    Remain | Remarks

Confirmed directly: `page.find_tables()` returns exactly one table per
page whose own first extracted row starts with the literal header cell
"ATA chapter" -- a real ruled table (`page.lines` shows 14 vertical
ruling segments per page, giving 15 columns), so pdfplumber's own
cell-boundary detection is used directly rather than re-deriving column
edges from word x-positions. The page-1 aircraft-header block above the
table is plain text, not a second ruled table -- `find_tables()` never
returns it, confirmed directly across the sample file.

Row grain: one row per tracked hard-time/LLP-limited component or task.
Several source cells wrap across 2-5 physical lines within one ruled
cell (e.g. a Position cell reading "11HM2\\nCONDENSER\\nP2", or a Next-due
cell reading "25.12.2028\\n69627.93\\nFH" -- a calendar-basis figure and an
hours-basis figure stacked in the same cell with no ruled sub-division
between them). These are joined with a single space rather than
force-split into separate basis columns, following this project's
convention of not guessing a column split the source table itself
doesn't draw. THRESHOLD and INTERVAL_LIFE_LIMIT are kept as two distinct
columns (confirmed independently populated with different values on some
rows -- e.g. one sample row reads THRESHOLD "3552 Days" and
INTERVAL_LIFE_LIMIT "3652 Days" at the same time), so they are not
merged despite the visual similarity of their contents on most rows
(THRESHOLD reads empty far more often than not in the sample file).

ATA_CHAPTER carries the ATA code plus its wrapped chapter-name text as
one field (e.g. "21-00 AIR CONDITIONING"); a word broken across the wrap
with no hyphen (e.g. "CONDITIONI"/"NG") is joined with a plain space,
not re-glued into a single word, since there is no reliable way to tell
a genuine two-word break from a wrapped single word without a dictionary
lookup -- consistent with "never guess a wrong split" applied in the
opposite direction (never guess a wrong *join*, either).

A handful of description-family cells (SYSTEM_REFERENCE / PART_DESCRIPTION
/ TASK_DESCRIPTION) carry a `(cid:NNN)` placeholder in place of a glyph
pdfplumber's font decode could not map (seen on 8 of 54 sample pages, 20
occurrences total, always inside a free-text description cell, e.g.
"EXCHANGER(cid:150)HEAT" where an en-dash glyph has no direct Unicode
mapping in the embedded font). These placeholders are stripped to a plain
ASCII hyphen rather than left as literal `(cid:150)` text, since the
surrounding context in every occurrence checked is a dash/hyphen
position.

Each ruled table row is only accepted into `records` when its own
ATA_CHAPTER cell starts with the `NN-NN` code pattern (e.g. "21-00");
this is cross-checked directly against an independent line-regex count
of the raw page text on the sample file (339 ruled-table data rows vs.
339 independently-detected `NN-NN`-leading lines -- an exact match, so
no row is silently dropped or duplicated by the table-boundary
detection).

The last page of the sample file carries a blank two-line signature
footer ("Prepared by:____ / Checked by:____ / Verified by:____") below
the ruled table, rendered with a doubled-character font-encoding glitch
on that one page's header/footer text only (confirmed directly: the
ruled table's own data row on that page decodes cleanly, only the
surrounding plain-text header/footer glyphs on that specific page are
doubled) -- outside the data table's own bbox either way, so it is never
captured as a data row, and it carries no name in the sample file (both
signature lines are blank).

Header metadata (operator, aircraft type, MSN, date of manufacture,
current aircraft FH/FC, report date/time, registration/tail number) is
parsed once from page 1's own plain-text header block and stamped on
every row.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.ht_variants._base import merged_rules
from shared.cleanup import normalize_dashes

NAME = "Airframe HTC/LLP Status"
SIGNATURES = [
    # This template's own title line, verbatim. Checked against every
    # SIGNATURES list in occm.py/ht.py/llp.py and every
    # occm_variants/ht_variants/llp_variants module (including a plain
    # grep for "HTC/LLP", "HTC / LLP" and "HTC LLP"); no collision found.
    # Not a substring of, and does not contain as a substring,
    # htll_status.py's own "HT-LL STATUS"/"HT&LLP STATUS" (different
    # abbreviation, "HTC" not "HT", and a different punctuation form).
    "AIRFRAME HTC/LLP STATUS",
]

CANONICAL_COLUMNS = [
    "ATA_CHAPTER",
    "MP_ITEM",
    "SYSTEM_REFERENCE",
    "PART_DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "POSITION",
    "TASK_DESCRIPTION",
    "THRESHOLD",
    "INTERVAL_LIFE_LIMIT",
    "INSTALL_DATE",
    "SINCE_LSV",
    "NEXT_DUE",
    "REMAIN",
    "REMARKS",
    # Header metadata -- same on every row of a given file.
    "OPERATOR",
    "AIRCRAFT_TYPE",
    "MSN",
    "DOM",
    "REG_TAIL",
    "CURRENT_AIRCRAFT_FH",
    "CURRENT_AIRCRAFT_FC",
    "REPORT_DATE",
]

_DATE_DOTTED_RE = r"^\d{1,2}\.\d{1,2}\.\d{4}( \d{1,2}:\d{2})?$"
_DATE_DASHED_RE = r"^\d{1,2}-\d{1,2}-\d{4}$"

_OVERRIDES = {
    "ATA_CHAPTER":          {"pattern": r"^\d{2}-\d{2}\b.*$", "allow_empty": True},
    "MP_ITEM":              {"allow_empty": True},
    "SYSTEM_REFERENCE":     {"allow_empty": True},
    "PART_DESCRIPTION":     {"allow_empty": True},
    "POSITION":             {"allow_empty": True},
    "TASK_DESCRIPTION":     {"allow_empty": True},
    "THRESHOLD":            {"allow_empty": True},
    "INTERVAL_LIFE_LIMIT":  {"allow_empty": True},
    "INSTALL_DATE":         {"pattern": _DATE_DASHED_RE, "allow_empty": True},
    "SINCE_LSV":            {"allow_empty": True},
    "NEXT_DUE":             {"allow_empty": True},
    "REMAIN":               {"allow_empty": True},
    "REMARKS":              {"allow_empty": True},
    "OPERATOR":             {"allow_empty": True},
    "AIRCRAFT_TYPE":        {"allow_empty": True},
    "MSN":                  {"pattern": r"^\d+$", "allow_empty": True},
    "DOM":                  {"pattern": _DATE_DASHED_RE, "allow_empty": True},
    "REG_TAIL":             {"pattern": r"^[A-Z0-9\-]+$", "uppercase": True,
                              "allow_empty": True},
    "CURRENT_AIRCRAFT_FH":  {"pattern": r"^[\d.]+$", "allow_empty": True},
    "CURRENT_AIRCRAFT_FC":  {"pattern": r"^[\d.]+$", "allow_empty": True},
    "REPORT_DATE":          {"pattern": _DATE_DOTTED_RE, "allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_HEADER_FIRST_CELL = "ATA chapter"
_ATA_ROW_RE = re.compile(r"^\d{2}-\d{2}\b")
_CID_RE = re.compile(r"\(cid:\d+\)")

_HEADER_LINE_RES = {
    "AIRCRAFT_TYPE": re.compile(r"AIRCRAFT TYPE:(\S+)"),
    "REPORT_DATE_D": re.compile(r"DATE:(\S+)"),
    "REPORT_DATE_T": re.compile(r"DATE:\S+\s+(\d{1,2}:\d{2})"),
    "MSN": re.compile(r"MSN:\s*(\S+)"),
    "CURRENT_AIRCRAFT_FH": re.compile(r"Current aircraft FH([\d.]+)"),
    "DOM": re.compile(r"DOM:(\S+)"),
    "CURRENT_AIRCRAFT_FC": re.compile(r"Current aircraft FC([\d.]+)"),
    "REG_TAIL": re.compile(r"REG \(TAIL\) NUMBER(\S+)"),
}
_TITLE_LINE_RE = re.compile(r"^AIRFRAME HTC/LLP STATUS\s+(.+)$")


def _join_wrapped_lines(value: str) -> str:
    """Join a ruled cell's physical lines. A line that already ends with a
    trailing hyphen (e.g. "ALT750-\\n11528", "CM215200-\\n041.32S(SBI)") had
    its hyphen printed as part of the original value before the wrap, not
    inserted by the wrap itself -- confirmed directly against several such
    cells in the sample file, all single continuous codes (part/reference/
    serial numbers) broken mid-value at a hyphen that is genuinely part of
    the value. Those are re-joined with no space. Every other line break
    (e.g. a chapter name wrapped with no hyphen, "CONDITIONI"/"NG") is
    joined with a single space, since there is no reliable way to tell a
    genuine two-word break from a wrapped single word without a dictionary
    lookup -- this project's "never guess a wrong split" convention applied
    in the opposite direction (never guess a wrong join, either)."""
    lines = value.split("\n")
    out = lines[0] if lines else ""
    for line in lines[1:]:
        if out.endswith("-"):
            out += line
        else:
            out += " " + line
    return out


def _clean_cell(value: str | None) -> str:
    if not value:
        return ""
    text = _join_wrapped_lines(value)
    text = " ".join(text.split())
    text = _CID_RE.sub("-", text)
    return normalize_dashes(text)


def _parse_header_meta(page) -> dict:
    meta = {
        "OPERATOR": "",
        "AIRCRAFT_TYPE": "",
        "MSN": "",
        "DOM": "",
        "REG_TAIL": "",
        "CURRENT_AIRCRAFT_FH": "",
        "CURRENT_AIRCRAFT_FC": "",
        "REPORT_DATE": "",
    }
    text = page.extract_text() or ""
    date_part = ""
    time_part = ""
    for line in text.split("\n"):
        m = _TITLE_LINE_RE.match(line.strip())
        if m:
            meta["OPERATOR"] = m.group(1).strip()
            continue
        m = _HEADER_LINE_RES["AIRCRAFT_TYPE"].search(line)
        if m:
            meta["AIRCRAFT_TYPE"] = m.group(1)
        m = _HEADER_LINE_RES["REPORT_DATE_D"].search(line)
        if m:
            date_part = m.group(1)
        m = _HEADER_LINE_RES["REPORT_DATE_T"].search(line)
        if m:
            time_part = m.group(1)
        m = _HEADER_LINE_RES["MSN"].search(line)
        if m:
            meta["MSN"] = m.group(1)
        m = _HEADER_LINE_RES["CURRENT_AIRCRAFT_FH"].search(line)
        if m:
            meta["CURRENT_AIRCRAFT_FH"] = m.group(1)
        m = _HEADER_LINE_RES["DOM"].search(line)
        if m:
            meta["DOM"] = m.group(1)
        m = _HEADER_LINE_RES["CURRENT_AIRCRAFT_FC"].search(line)
        if m:
            meta["CURRENT_AIRCRAFT_FC"] = m.group(1)
        m = _HEADER_LINE_RES["REG_TAIL"].search(line)
        if m:
            meta["REG_TAIL"] = m.group(1)
    meta["REPORT_DATE"] = (date_part + (" " + time_part if time_part else "")).strip()
    return meta


def _find_data_table(page):
    for table in page.find_tables():
        rows = table.extract()
        if not rows:
            continue
        first_cell = (rows[0][0] or "").strip()
        if first_cell == _HEADER_FIRST_CELL:
            return table, rows
    return None, None


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []

    with pdfplumber.open(pdf_path) as pdf:
        meta = {}
        if pdf.pages:
            meta = _parse_header_meta(pdf.pages[0])

        for page_num, page in enumerate(pdf.pages, start=1):
            _, rows = _find_data_table(page)
            if not rows:
                continue

            data_rows = rows
            if data_rows and (data_rows[0][0] or "").strip() == _HEADER_FIRST_CELL:
                data_rows = data_rows[1:]

            for raw in data_rows:
                if len(raw) < 15:
                    continue
                ata_chapter = _clean_cell(raw[0])
                if not _ATA_ROW_RE.match(ata_chapter):
                    # Not a recognisable data row -- skip rather than
                    # force it into a row.
                    continue
                row = {
                    "ATA_CHAPTER": ata_chapter,
                    "MP_ITEM": _clean_cell(raw[1]),
                    "SYSTEM_REFERENCE": _clean_cell(raw[2]),
                    "PART_DESCRIPTION": _clean_cell(raw[3]),
                    "PART_NUMBER": _clean_cell(raw[4]),
                    "SERIAL_NUMBER": _clean_cell(raw[5]),
                    "POSITION": _clean_cell(raw[6]),
                    "TASK_DESCRIPTION": _clean_cell(raw[7]),
                    "THRESHOLD": _clean_cell(raw[8]),
                    "INTERVAL_LIFE_LIMIT": _clean_cell(raw[9]),
                    "INSTALL_DATE": _clean_cell(raw[10]),
                    "SINCE_LSV": _clean_cell(raw[11]),
                    "NEXT_DUE": _clean_cell(raw[12]),
                    "REMAIN": _clean_cell(raw[13]),
                    "REMARKS": _clean_cell(raw[14]),
                }
                row["_page"] = page_num
                row.update(meta)
                records.append(row)

    return records
