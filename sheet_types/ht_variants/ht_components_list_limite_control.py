"""Born-digital "HT COMPONENTS LIST" report, word-position-bucketed columns
(confirmed via a direct pdfplumber `extract_words()` pass over the real
sample file: text is present and well-positioned on every page, no OCR
needed).

Header block (repeats verbatim at the top of every page after page 1 --
page 1 itself omits the title line and starts directly at the metadata
line below; both forms are handled)::

    <A/C REG> * HT COMPONENTS LIST
    <A/C REG> SN: <msn> ACFT TT: <hours> ACFT TC: <cycles> DATE: <dd/m/yyyy>
                                       Installed  Last Insp.  Time/Cycles
    Item ATA Description Part Number Serial Number Limite Control Check
        Time Utilized  Days Remaining  Due  Doct Task Card  Note
                                       Date       Date       Remaining

Row grain: one row per tracked component, or -- for an Item that groups
more than one physically tracked sub-part under one description (e.g. a
device plus its own separately-life-limited internal cell/cylinder) -- one
row per sub-part, with ITEM left blank on every row after the first for
that group (confirmed directly: these continuation rows repeat the same
ATA chapter and carry their own PART_NUMBER/LIMIT/dates, just no new Item
number).

Columns, left to right::

    ITEM | ATA | DESCRIPTION | PART_NUMBER | SERIAL_NUMBER |
    LIMIT_VALUE | LIMIT_UNIT | CONTROL_CHECK |
    INSTALLED_DATE | LAST_INSP_DATE |
    UTILIZED | REMAINING | DAYS_REMAINING | DUE_DATE | TASK_CARD | NOTE

Column assignment is done by fixed x0 bucketing (confirmed directly via
`extract_words()`: every column's data tokens sit in a distinct,
non-overlapping x-band repeated identically across all three pages of the
sample file). LIMIT_UNIT carries the tracking basis (e.g. a day count, a
flight-hour count, or a cycle count); CONTROL_CHECK carries the
maintenance action/check type associated with the limit (single- or
two-word, e.g. a replace/restore/discard/overhaul action or a named
functional/hydrostatic/weight check).

UTILIZED, REMAINING and DAYS_REMAINING are three independently-populated
numeric bands, not a fixed-count triplet: REMAINING (in the limit's own
native unit) is populated only when that differs meaningfully from
DAYS_REMAINING (the calendar-day count to the DUE_DATE) -- confirmed
directly: a day-based-limit row sometimes carries only UTILIZED +
DAYS_REMAINING (two numbers), sometimes all three with REMAINING equal to
DAYS_REMAINING, while every flight-hour/cycle-based-limit row carries all
three with REMAINING in hours/cycles and DAYS_REMAINING as the separate
calendar projection. Rather than guess which shape a given row uses,
tokens are bucketed by their own x0 against the three fixed column bands,
so each column is simply blank where the source PDF renders no token
there -- never force-assigned by position count.

A very small number of rows (confirmed exactly two in the sample file,
both a device whose life-limited stock is tracked on a separate inventory
list rather than by discrete serial number) carry the free-text note "SEE
INVENTORY" spanning what would otherwise be the PART_NUMBER column band.
Splitting it there would break the phrase across two fields and land half
of it under PART_NUMBER, which is data corruption dressed as a column
value -- so this exact two-word phrase is detected on the word list before
bucketing and kept whole in DESCRIPTION, leaving PART_NUMBER blank for
those rows.

TASK_CARD is usually a bare reference code, but one row in the sample
file spells out the literal word "TASK" ahead of its own code where no
DUE_DATE was computed for that row -- kept as-is (free text, not
force-parsed) rather than guessed apart.

Header metadata (aircraft registration, MSN, total time, total cycles,
report date) is parsed once from page 1's own metadata line and stamped
on every row.

The trailing page-footer line ("Issued by <department>" plus a plain
"<date> N of M" line) carries no numbered-item content and is skipped by
the same row-detection check used for the header rows -- neither line has
a bare 1-2 digit ATA token in the ATA column band. No personally-
identifying content (an individual's name) was found anywhere in the
sample file's text layer; the footer's own "Issued by" line names only a
department, not a person.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.ht_variants._base import merged_rules
from shared.cleanup import normalize_dashes

NAME = "HT Components List (Limite/Control/Check)"

SIGNATURES = [
    # This template's own header-row phrase, verbatim, present on every
    # page (unlike the "<REG> * HT COMPONENTS LIST" title line, which the
    # sample file's own first page omits). Checked against every
    # SIGNATURES list in occm.py/ht.py/llp.py and every
    # occm_variants/ht_variants/llp_variants module (including a plain
    # grep for "Limite Control" / "LIMITE CONTROL"); no collision found.
    "LIMITE CONTROL CHECK",
    # Backup anchor: the report's own bare title line. Present on this
    # sample file's continuation pages, not its first page, so it is kept
    # as a secondary signature rather than the primary one. Checked
    # against every SIGNATURES list in occm.py/ht.py/llp.py and every
    # occm_variants/ht_variants/llp_variants module (including a plain
    # grep for "HT COMPONENTS LIST"); no collision found -- distinct from
    # ht_components_status_ruled_grid.py's own "HT COMPONENTS STATUS"
    # (STATUS, not LIST; different word, not a substring in either
    # direction).
    "HT COMPONENTS LIST",
]

CANONICAL_COLUMNS = [
    "ITEM",
    "ATA",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "LIMIT_VALUE",
    "LIMIT_UNIT",
    "CONTROL_CHECK",
    "INSTALLED_DATE",
    "LAST_INSP_DATE",
    "UTILIZED",
    "REMAINING",
    "DAYS_REMAINING",
    "DUE_DATE",
    "TASK_CARD",
    "NOTE",
    # Header metadata -- same on every row of a given file.
    "AC_REG",
    "AC_MSN",
    "AC_TT",
    "AC_TC",
    "REPORT_DATE",
]

_DATE_RE = r"^\d{1,2}-[A-Za-z]{3}-\d{2}$"
_NUM_RE = r"^-?[\d.,]+$"

_OVERRIDES = {
    "ITEM":            {"pattern": r"^\d+$", "allow_empty": True},
    "PART_NUMBER":      {"allow_empty": True},
    "SERIAL_NUMBER":    {"allow_empty": True},
    "LIMIT_VALUE":      {"pattern": r"^\d+$", "allow_empty": True},
    "LIMIT_UNIT":       {"pattern": r"^[A-Za-z]+$", "allow_empty": True},
    "CONTROL_CHECK":    {"pattern": r"^[A-Za-z]+(?:\s[A-Za-z]+)*$",
                          "allow_empty": True},
    "INSTALLED_DATE":   {"pattern": _DATE_RE, "allow_empty": True},
    "LAST_INSP_DATE":   {"pattern": _DATE_RE, "allow_empty": True},
    "UTILIZED":         {"pattern": _NUM_RE, "allow_empty": True},
    "REMAINING":        {"pattern": _NUM_RE, "allow_empty": True},
    "DAYS_REMAINING":   {"pattern": _NUM_RE, "allow_empty": True},
    "DUE_DATE":         {"pattern": _DATE_RE, "allow_empty": True},
    "TASK_CARD":        {"allow_empty": True},
    "NOTE":             {"allow_empty": True},
    "AC_REG":           {"pattern": r"^[A-Z0-9\-]+$", "uppercase": True,
                          "allow_empty": True},
    "AC_MSN":           {"pattern": _NUM_RE, "allow_empty": True},
    "AC_TT":            {"pattern": _NUM_RE, "allow_empty": True},
    "AC_TC":            {"pattern": _NUM_RE, "allow_empty": True},
    "REPORT_DATE":      {"pattern": r"^\d{1,2}/\d{1,2}/\d{4}$",
                          "allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Left edges (PDF points) of each column band, from the real header/body
# coordinates on the sample file -- confirmed identical across all three
# of its pages.
_ITEM_X = 71.0
_ATA_X = 93.0
_DESC_X = 228.0
_PN_X = 270.0
_SN_X = 332.0
_LIMIT_VAL_X = 369.0
_LIMIT_UNIT_X = 403.0
_CONTROL_X = 446.0
_INSTALLED_X = 478.0
_LAST_INSP_X = 515.0
_UTILIZED_X = 576.0
_REMAINING_X = 610.0
_DAYS_REM_X = 660.0
_DUE_X = 690.0
_TASK_X = 770.0

_HEADER_ROW_RE = re.compile(r"^Item\s+ATA\s+Description")
_ATA_RE = re.compile(r"^\d{1,2}$")
_FOOTER_ROW_RE = re.compile(r"^Issued\s+by\b")

_META_RE = re.compile(
    r"(\S+)\s+SN:\s*([\d.,]+)\s+ACFT\s+TT:\s*([\d.,]+)\s+"
    r"ACFT\s+TC:\s*([\d.,]+)\s+DATE:\s*(\S+)"
)


def _group_lines(words: list[dict]) -> list[dict]:
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


def _line_text(line: dict) -> str:
    return " ".join(w["text"] for w in line["words"])


def _fix_see_inventory(words: list[dict]) -> None:
    """The two-word phrase "SEE INVENTORY" (see module docstring) has its
    second word rendered past the DESCRIPTION/PART_NUMBER boundary on the
    sample file's own two rows that use it. Detected here, ahead of
    bucketing, and pulled back into the DESCRIPTION band so the phrase
    stays whole instead of being split across two output fields."""
    for i in range(len(words) - 1):
        a, b = words[i], words[i + 1]
        if (a["text"] == "SEE" and b["text"] == "INVENTORY"
                and a["x0"] < _DESC_X <= b["x0"]):
            b["x0"] = a["x0"]


def _row_from_line(line: dict) -> dict:
    row = {col: "" for col in CANONICAL_COLUMNS}
    buckets: dict[str, list[dict]] = {col: [] for col in CANONICAL_COLUMNS}
    for w in line["words"]:
        x0 = w["x0"]
        if x0 < _ITEM_X:
            buckets["ITEM"].append(w)
        elif x0 < _ATA_X:
            buckets["ATA"].append(w)
        elif x0 < _DESC_X:
            buckets["DESCRIPTION"].append(w)
        elif x0 < _PN_X:
            buckets["PART_NUMBER"].append(w)
        elif x0 < _SN_X:
            buckets["SERIAL_NUMBER"].append(w)
        elif x0 < _LIMIT_VAL_X:
            buckets["LIMIT_VALUE"].append(w)
        elif x0 < _LIMIT_UNIT_X:
            buckets["LIMIT_UNIT"].append(w)
        elif x0 < _CONTROL_X:
            buckets["CONTROL_CHECK"].append(w)
        elif x0 < _INSTALLED_X:
            buckets["INSTALLED_DATE"].append(w)
        elif x0 < _LAST_INSP_X:
            buckets["LAST_INSP_DATE"].append(w)
        elif x0 < _UTILIZED_X:
            buckets["UTILIZED"].append(w)
        elif x0 < _REMAINING_X:
            buckets["REMAINING"].append(w)
        elif x0 < _DAYS_REM_X:
            buckets["DAYS_REMAINING"].append(w)
        elif x0 < _DUE_X:
            buckets["DUE_DATE"].append(w)
        elif x0 < _TASK_X:
            buckets["TASK_CARD"].append(w)
        else:
            buckets["NOTE"].append(w)
    for field, ws in buckets.items():
        if ws:
            row[field] = " ".join(w["text"] for w in ws)
    return row


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    meta = {"AC_REG": "", "AC_MSN": "", "AC_TT": "", "AC_TC": "", "REPORT_DATE": ""}

    with pdfplumber.open(pdf_path) as pdf:
        if pdf.pages:
            head_text = normalize_dashes(pdf.pages[0].extract_text() or "")
            m = _META_RE.search(head_text)
            if m:
                meta["AC_REG"] = m.group(1)
                meta["AC_MSN"] = m.group(2)
                meta["AC_TT"] = m.group(3)
                meta["AC_TC"] = m.group(4)
                meta["REPORT_DATE"] = m.group(5)

        for page_num, page in enumerate(pdf.pages, start=1):
            words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
            if not words:
                continue
            for w in words:
                w["text"] = normalize_dashes(w["text"])
            _fix_see_inventory(words)
            lines = _group_lines(words)

            for line in lines:
                text = _line_text(line)
                if _HEADER_ROW_RE.match(text) or _FOOTER_ROW_RE.match(text):
                    continue
                ata_text = " ".join(w["text"] for w in line["words"] if _ITEM_X <= w["x0"] < _ATA_X)
                has_control = any(_LIMIT_UNIT_X <= w["x0"] < _CONTROL_X for w in line["words"])
                if not (_ATA_RE.match(ata_text) and has_control):
                    # Not a recognisable data row (header/metadata line,
                    # page furniture) -- skip rather than force it into a
                    # row.
                    continue
                row = _row_from_line(line)
                row["_page"] = page_num
                row.update(meta)
                records.append(row)

    return records
