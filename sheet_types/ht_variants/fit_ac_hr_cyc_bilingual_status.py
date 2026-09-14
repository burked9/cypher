"""Bilingual (Chinese/English) HT component-status export -- born-digital,
full text layer, coordinate-bucketed columns (confirmed via a direct
pdfplumber pass over the real sample file: `extract_words()` returns full
content on every page, no OCR needed).

This report has NO plain-English title printed on the page itself (the
title-like phrase associated with this file lives only in the source
filename/catalog metadata, not in the PDF's own text layer) -- detection
instead anchors on this template's own distinctive bilingual column-header
row, which prints cleanly as one line via `extract_text()`::

    Description P/N S/N MPD号 FIT A/C Hr FIT A/C Cyc Current A/C T. Remaining Remarks
    No Due Date Interval DOM Installation Date

Header metadata block (repeats verbatim at the top of every page, values
in the order they're printed)::

    出厂日期 DOM： <aircraft manufacture date>  <registration><title glyph run, glued to
        the registration token with no separating space in the source
        content stream>  现机身小时 现机身起落
    截止日期：<reference date>  <current A/C hours>  <current A/C cycles>

The registration token is glued directly to the following Chinese title
text with no space in between (confirmed directly via `extract_words()`:
one single token spans both) -- parsed with a leading
alphanumeric-plus-hyphen run rather than matched as a whole token, so the
trailing glued characters are simply dropped rather than kept as part of
the registration.

Row grain: one row per tracked component/interval-instance. Columns, left
to right (x0 bands, confirmed directly against every row on both pages of
the sample file -- see `_BANDS` below)::

    NO | DESCRIPTION | PART_NUMBER | SERIAL_NUMBER | DUE_DATE | INTERVAL |
    MPD_NO | DOM | FIT_AC_HR | FIT_AC_CYC | CURRENT_AC_T | REMAINING |
    INSTALLATION_DATE | REMARKS

Column-ragged, same convention as this project's other HT variants: a
component is tracked by whichever basis applies to it (FH, cycles,
calendar, landings, or a mix), so most rows leave several of the
DOM/FIT_AC_HR/FIT_AC_CYC/CURRENT_AC_T/REMAINING cells blank -- confirmed
directly against many rows, never a case of a genuinely present value
being dropped. DUE_DATE itself is rendered in two different date shapes
on different rows of the SAME column (`M/D/YYYY` on some rows, `YYYY/MM/DD`
on others) -- both accepted by one pattern below rather than picking one
and flagging the other as bad.

DESCRIPTION/PART_NUMBER/SERIAL_NUMBER never wrap onto a second physical
line in the ordinary case (the page is wide enough that even long
component names fit on one line) -- confirmed directly: only INTERVAL
(a free-text maintenance-action description, frequently in Chinese) wraps,
and only for a couple of components in the whole file that are tracked
under two separate due-date/interval instances at once (see below).

Two-instance rows: a small number of components (confirmed on this file:
just the "Portable ELT" pair) are tracked under two independent
due-date/interval/MPD/installation-date combinations at once, printed as
extra physical lines both above AND below the row's own anchor line
(unlike every other multi-line HT variant in this project, where wrap
lines are pure overflow of a single value). Splitting these into two
separate output records would require guessing which of several similarly
laid-out neighbour lines belongs to which due-date instance -- a genuine
"never guess a wrong split" situation. Instead, all of DUE_DATE/MPD_NO/
INSTALLATION_DATE keep every distinct value found for the row, joined with
"; " when more than one appears (INTERVAL is always joined this way
regardless of count, since it's expected free text spanning multiple
physical lines by this template's own design) -- lossless, and it costs
nothing on the ~98% of rows that only ever have one value per column.
Extra lines are attached to the row using the SAME row-grain rule as every
other row: nearest preceding anchor by physical line order. This
occasionally attributes an extra-instance line to the wrong neighbouring
row when that line is physically printed above its own component's own
anchor row (confirmed: this happens for the two components noted above);
rather than add per-line lookahead heuristics to guess the "right" row
for such lines -- fragile given only two real examples to generalise
from -- both affected rows simply carry the co-mingled values, which is
still fully visible to an analyst reviewing the semicolon-joined cells,
never silently dropped or silently misattributed to a single guessed
value.

A short component-name wrap that spans a page break appears twice in the
source PDF (once trailing the previous page, once leading the row's own
page) -- confirmed directly (identical wrapped text, byte-for-byte, at
the bottom of one page and the top of the next). Trailing orphan lines at
the bottom of a page (after the last anchor row, before the "<n> of <m>"
footer) are carried forward and prepended to the FIRST anchor row's own
DESCRIPTION on the following page, so this doesn't produce a blank/partial
description on the row it belongs to.

A "<n> of <m>" footer repeats on every page and is dropped by an exact-line
regex match.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.ht_variants._base import merged_rules
from shared.cleanup import normalize_dashes

NAME = "Bilingual FIT A/C Hr/Cyc HT Status"
SIGNATURES = [
    # Checked against every SIGNATURES list in occm.py/ht.py/llp.py and
    # every occm_variants/ht_variants/llp_variants module; no collision --
    # this exact two-column combo ("FIT A/C Hr" next to "FIT A/C Cyc") does
    # not appear in any other variant or router file (the nearest
    # look-alike, occm_variants/assembly_configuration_status_report.py's
    # "Current A/C Times", is a different phrase entirely).
    "FIT A/C Hr FIT A/C Cyc",
]

CANONICAL_COLUMNS = [
    "NO",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DUE_DATE",
    "INTERVAL",
    "MPD_NO",
    "DOM",
    "FIT_AC_HR",
    "FIT_AC_CYC",
    "CURRENT_AC_T",
    "REMAINING",
    "INSTALLATION_DATE",
    "REMARKS",
    # Header metadata -- same on every row of a given file.
    "AIRCRAFT_DOM",
    "REGISTRATION",
    "REFERENCE_DATE",
    "AC_CURRENT_HR",
    "AC_CURRENT_CYC",
]

# Accepts both date shapes seen in this template's own DUE_DATE/DOM/
# INSTALLATION_DATE columns: M/D/YYYY and YYYY/MM/DD, non-zero-padded.
_DATE_RE = r"^(?:\d{1,2}/\d{1,2}/\d{4}|\d{4}/\d{1,2}/\d{1,2})$"
_NUM_RE = r"^[\d,]+$"

_OVERRIDES = {
    "NO":                 {"pattern": r"^\d+$"},
    "PART_NUMBER":        {"allow_empty": True},
    "SERIAL_NUMBER":      {"allow_empty": True},
    "DUE_DATE":           {"pattern": _DATE_RE, "allow_empty": True},
    "INTERVAL":           {"allow_empty": True},
    "MPD_NO":             {"allow_empty": True},
    "DOM":                {"pattern": _DATE_RE, "allow_empty": True},
    "FIT_AC_HR":          {"pattern": _NUM_RE, "allow_empty": True},
    "FIT_AC_CYC":         {"pattern": _NUM_RE, "allow_empty": True},
    "CURRENT_AC_T":       {"pattern": _NUM_RE, "allow_empty": True},
    "REMAINING":          {"pattern": _NUM_RE, "allow_empty": True},
    "INSTALLATION_DATE":  {"pattern": _DATE_RE, "allow_empty": True},
    "REMARKS":            {"allow_empty": True},
    "AIRCRAFT_DOM":       {"pattern": r"^\d{4}-\d{1,2}-\d{1,2}$", "allow_empty": True},
    "REGISTRATION":       {"pattern": r"^[A-Z0-9\-]+$", "uppercase": True,
                            "allow_empty": True},
    "REFERENCE_DATE":     {"pattern": r"^\d{4}-\d{1,2}-\d{1,2}$", "allow_empty": True},
    "AC_CURRENT_HR":      {"pattern": _NUM_RE, "allow_empty": True},
    "AC_CURRENT_CYC":     {"pattern": _NUM_RE, "allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_FOOTER_RE = re.compile(r"^\d+\s+of\s+\d+$")

# Left edge (x0, PDF points) of each column band, confirmed directly
# against `extract_words()` output for every row on both pages of the
# sample file -- values are consistently left-aligned within their own
# band (unlike some sibling templates' right-aligned numeric columns), so
# a simple half-open range per column is reliable without needing
# nearest-header-x snapping.
_BANDS = [
    ("NO", 0),
    ("DESCRIPTION", 55),
    ("PART_NUMBER", 270),
    ("SERIAL_NUMBER", 385),
    ("DUE_DATE", 540),
    ("INTERVAL", 600),
    ("MPD_NO", 760),
    ("DOM", 870),
    ("FIT_AC_HR", 970),
    ("FIT_AC_CYC", 1060),
    ("CURRENT_AC_T", 1140),
    ("REMAINING", 1250),
    ("INSTALLATION_DATE", 1320),
    ("REMARKS", 1420),
]


def _band_for(x0: float) -> str:
    field = _BANDS[0][0]
    for name, left in _BANDS:
        if x0 >= left:
            field = name
        else:
            break
    return field


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


# Metadata is parsed from raw page text (not word bands) since it's a
# handful of one-off values rather than tabular data.
_AIRCRAFT_DOM_RE = re.compile(r"DOM\s*[:：]\s*(\d{4}-\d{1,2}-\d{1,2})")
_REG_RE = re.compile(r"\d{4}-\d{1,2}-\d{1,2}\s+([A-Za-z0-9][A-Za-z0-9\-]*)")
_REF_DATE_RE = re.compile(r"截止日期[:：]\s*(\d{4}-\d{1,2}-\d{1,2})")
_CURRENT_TOTALS_RE = re.compile(
    r"截止日期[:：]\s*\d{4}-\d{1,2}-\d{1,2}\s+([\d,]+)\s+([\d,]+)"
)


def _parse_meta(head_text: str) -> dict:
    meta = {k: "" for k in ("AIRCRAFT_DOM", "REGISTRATION", "REFERENCE_DATE",
                             "AC_CURRENT_HR", "AC_CURRENT_CYC")}
    m = _AIRCRAFT_DOM_RE.search(head_text)
    if m:
        meta["AIRCRAFT_DOM"] = m.group(1)
    m = _REG_RE.search(head_text)
    if m:
        meta["REGISTRATION"] = m.group(1)
    m = _REF_DATE_RE.search(head_text)
    if m:
        meta["REFERENCE_DATE"] = m.group(1)
    m = _CURRENT_TOTALS_RE.search(head_text)
    if m:
        meta["AC_CURRENT_HR"] = m.group(1)
        meta["AC_CURRENT_CYC"] = m.group(2)
    return meta


def _new_row() -> dict:
    row = {col: "" for col in CANONICAL_COLUMNS}
    return row


def _apply_line(row: dict, line: dict, is_anchor: bool) -> None:
    """Merge one physical line's tokens into `row`, bucketing each token by
    its x0 band. NO/DESCRIPTION/PART_NUMBER/SERIAL_NUMBER are set only from
    the anchor line. INTERVAL always appends (expected free text). Every
    other band fills empty, or joins with "; " on a genuinely different
    value for the same field (see module docstring: two-instance rows)."""
    bucket: dict[str, list[str]] = {}
    for w in line["words"]:
        field = _band_for(w["x0"])
        if field == "NO" and not is_anchor:
            continue
        bucket.setdefault(field, []).append(w["text"])

    for field in ("NO", "DESCRIPTION", "PART_NUMBER", "SERIAL_NUMBER"):
        if field not in bucket:
            continue
        if not is_anchor:
            # Only DESCRIPTION may legitimately continue on a carried-over
            # orphan line (page-break wrap); NO/PN/SN never do.
            if field != "DESCRIPTION":
                continue
        text = " ".join(bucket[field])
        if field == "DESCRIPTION" and row[field]:
            row[field] = f"{row[field]} {text}".strip()
        else:
            row[field] = text

    if "INTERVAL" in bucket:
        text = " ".join(bucket["INTERVAL"])
        row["INTERVAL"] = f"{row['INTERVAL']} {text}".strip()

    for field in ("DUE_DATE", "MPD_NO", "DOM", "FIT_AC_HR", "FIT_AC_CYC",
                   "CURRENT_AC_T", "REMAINING", "INSTALLATION_DATE", "REMARKS"):
        if field not in bucket:
            continue
        text = " ".join(bucket[field])
        if not row[field]:
            row[field] = text
        elif text not in row[field].split("; "):
            # NOTE: "|" is not usable as a join separator here -- the
            # shared cleanup pipeline (`shared/cleanup.py`) unconditionally
            # strips "|" characters from every cell as an OCR/table-border
            # artifact, which would silently collapse this back down to a
            # single space and make the two joined values unreadable.
            row[field] = f"{row[field]}; {text}"


def _is_pure_description(line: dict) -> bool:
    """True when every token on this line falls in the DESCRIPTION band --
    i.e. it carries no due-date/interval/MPD/etc. data of its own. Used to
    tell a genuine component-name wrap (which belongs to whichever anchor
    row it's adjacent to) apart from an extra due-date/interval instance
    line (which must stay attached to the row it was printed next to --
    see module docstring on two-instance rows)."""
    return all(_band_for(w["x0"]) == "DESCRIPTION" for w in line["words"])


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    meta = {}

    with pdfplumber.open(pdf_path) as pdf:
        if pdf.pages:
            head_text = normalize_dashes(pdf.pages[0].extract_text() or "")
            meta = _parse_meta(head_text)

        for page in pdf.pages:
            words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
            if not words:
                continue
            for w in words:
                w["text"] = normalize_dashes(w["text"])
            lines = _group_lines(words)
            # Table content starts below the (repeated) two-line bilingual
            # header block; every data row's own top is >= 106 on this
            # template, well clear of the header (which ends at top ~90).
            lines = [ln for ln in lines if ln["top"] > 100]
            if not lines:
                continue

            current_row: dict | None = None
            page_rows: list[dict] = []
            # Pure-description-band orphan lines seen since the last row
            # was opened (or since the start of the page). A component
            # name that wraps onto its own line immediately above the
            # row's anchor line is printed this way on this template --
            # confirmed directly (see module docstring). Anything printed
            # after the LAST anchor on a page, with no further anchor to
            # attach to before the page ends, is dropped rather than
            # guessed at (confirmed on this file: that trailing text is a
            # byte-identical duplicate of the wrap already captured
            # leading the next page's own anchor row, so nothing is lost).
            pending_description: list[dict] = []

            for line in lines:
                text = " ".join(w["text"] for w in line["words"])
                if _FOOTER_RE.match(text):
                    continue
                has_no = any(
                    w["x0"] < _BANDS[1][1] and w["text"].isdigit()
                    for w in line["words"]
                )
                if has_no:
                    current_row = _new_row()
                    if pending_description:
                        current_row["DESCRIPTION"] = " ".join(
                            w["text"] for ln in pending_description for w in ln["words"]
                        ).strip()
                        pending_description = []
                    _apply_line(current_row, line, is_anchor=True)
                    page_rows.append(current_row)
                elif _is_pure_description(line):
                    pending_description.append(line)
                elif current_row is not None:
                    _apply_line(current_row, line, is_anchor=False)
                # else: a non-description orphan before any anchor has
                # opened on this page -- never observed in this file;
                # dropped rather than guessed at.

            for row in page_rows:
                row.update(meta)
                records.append(row)

    return records
