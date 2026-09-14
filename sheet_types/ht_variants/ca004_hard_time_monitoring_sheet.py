"""CA-004 Hard Time Monitoring Sheet -- born-digital, full text layer,
coordinate-bucketed columns (confirmed via a direct pdfplumber pass over the
real sample file: `extract_words()` returns full content on every page, no
OCR needed).

Same "Aircraft Type: <type> Reference Date: <date> / <label>: <reg> TSN:
<n> / MSN: <msn> CSN: <n>" header boilerplate family as this project's
`occm_variants/occm_control_sheet.py` sibling (same MIS template family,
HT side instead of OCCM side) -- confirmed genuinely different title,
column layout, and section-break convention, not a shared parser. One
quirk specific to this template: its own registration-line label is
rendered with a single substituted character (a generic label typo baked
into the source template itself, not corpus-specific) -- matched with a
single-character wildcard below rather than hardcoded to one spelling.

Header block (repeats verbatim at the top of every page)::

    CA-004 Hard Time Monitoring Sheet
    Aircraft Type: <type>                      Reference Date: <date>
    Re<?>istration: <tail>                     TSN: <hours:minutes>
    MSN: <msn>                                  CSN: <cycles>
    Original
    Last Accomplished          Interval        Next Due        Remaining
    Description  Part Number  Serial Number                    Comment
                  FH  FC  Date   FH  FC  Days    FH  FC  Date    FH  FC  Days

Row grain: one row per tracked component. Columns, left to right::

    DESCRIPTION | PART_NUMBER | SERIAL_NUMBER |
    LAST_ACC_FH | LAST_ACC_FC | LAST_ACC_DATE |
    INTERVAL_FH | INTERVAL_FC | INTERVAL_DAYS |
    NEXT_DUE_FH | NEXT_DUE_FC | NEXT_DUE_DATE |
    REMAINING_FH | REMAINING_FC | REMAINING_DAYS |
    COMMENT

Each component is tracked by whichever basis applies to it (FH-only,
FC-only, calendar-only, or a mix) -- the untracked sub-columns are simply
blank on that row, rendered as a literal "-" placeholder in the
Last-Accomplished/Interval block and a literal "/" placeholder in the
Next-Due/Remaining block. Both placeholder glyphs are normalized to an
empty string here (rather than kept as literal text) so an analyst
filtering on "has a value" doesn't have to know this template's own
placeholder vocabulary; confirmed this is a print-time formatting
convention (both glyphs appear identically on section-heading rows, which
carry no real data at all -- see below) and not a real character.

ATA is not printed per component row -- only on its own "ATA <n>"
section-heading row above each group (all of that row's numeric columns
carry the blank placeholder, confirmed via `extract_words()`: none of the
12 sub-column tokens on such a line is ever anything but "-"/"/"). These
heading rows are recognised and dropped rather than emitted as a
component, with the ATA number forward-filled onto every component row
that follows, the same section-header-carries-ATA convention this
project's other section-organized HT variants use (e.g.
`time_controlled_items_report.py`).

DESCRIPTION line-wrap: this template's renderer does not wrap a
too-long DESCRIPTION onto a second visual line *within* the row -- it
prints the overflow as a separate physical text line immediately above
and/or below the row's own anchor line (confirmed directly: some
components wrap onto the line above only, some onto the line below only,
and at least one onto both, e.g. a name split "<first half>" / "<anchor
row: rest of name>" / "<continuation>" across three consecutive physical
lines with the PN/SN/data sandwiched in the middle). No column other than
DESCRIPTION is ever affected by this (confirmed: every overflow fragment
carries text only in the DESCRIPTION x-range, nothing in PART_NUMBER,
SERIAL_NUMBER, or the numeric block). Handled the same way this project's
`time_controlled_components_status.py` handles its own row-external
overflow fragments: group words into physical lines by y-position, flag a
line as an anchor ("core") row when it carries any token in the numeric
block's x-range, and merge every non-anchor ("orphan") line's text into
whichever anchor row is vertically closest to it -- prepending if the
orphan sits above that row, appending if below.

Numeric sub-columns are assigned by nearest-header-x snapping rather than
fixed cut-off bins: confirmed directly (via `extract_words()`) that every
one of the 12 Last-Accomplished/Interval/Next-Due/Remaining sub-columns'
own header label sits at a fixed x-position repeated identically on every
page, but the data values under it are right-aligned, so a wide value
(e.g. a 5-6 digit FH figure) starts well to the left of its header label
and can start closer to the *previous* sub-column's header than its own.
Snapping each token to whichever of the 12 known header x-positions it is
closest to (rather than a fixed left/right cut-off between adjacent
sub-columns) resolves this correctly in every case checked, including
rows tracked on FC alone, FH alone, or a mix of FH/FC/Days on the same
row -- confirmed against several such rows directly.

Header metadata (aircraft type, reference date, registration, TSN, MSN,
CSN) is parsed once from the first page and stamped on every row, the
same convention `occm_control_sheet.py` uses for its own sibling header
block.

A "Page <n> of <m>" footer repeats on every page and is dropped by an
exact-line match; it is not caught by the numeric-block/x-position anchor
check by accident (its own tokens happen to land inside that x-range) so
it is filtered explicitly rather than relying on the anchor heuristic
alone.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.ht_variants._base import merged_rules
from shared.cleanup import normalize_dashes

NAME = "CA-004 Hard Time Monitoring Sheet"
SIGNATURES = [
    # Checked against every SIGNATURES list in occm.py/ht.py/llp.py and
    # every occm_variants/ht_variants/llp_variants module; no collision
    # found. (occm_variants/occm_control_sheet.py shares this template
    # family's generic header boilerplate -- "Aircraft Type:"/"Reference
    # Date:"/"MSN:"/"CSN:" -- but its own title is "OCCM Control Sheet",
    # a distinct phrase from this one.)
    "Hard Time Monitoring Sheet",
]

CANONICAL_COLUMNS = [
    "ATA",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "LAST_ACC_FH",
    "LAST_ACC_FC",
    "LAST_ACC_DATE",
    "INTERVAL_FH",
    "INTERVAL_FC",
    "INTERVAL_DAYS",
    "NEXT_DUE_FH",
    "NEXT_DUE_FC",
    "NEXT_DUE_DATE",
    "REMAINING_FH",
    "REMAINING_FC",
    "REMAINING_DAYS",
    "COMMENT",
    # Header metadata -- same on every row of a given file.
    "AIRCRAFT_TYPE",
    "REFERENCE_DATE",
    "REGISTRATION",
    "TSN",
    "MSN",
    "CSN",
]

_DATE_RE = r"^\d{2}-[A-Za-z]{3}-\d{2}$"
# FH/FC/Days/TSN/CSN figures: plain or comma-grouped integers, optionally
# with a ":MM" minutes suffix (this template renders some hour-basis
# figures as HH:MM, e.g. a TSN or a remaining-hours count).
_NUM_RE = r"^[\d,]+(?::\d{2})?$"

_OVERRIDES = {
    "ATA":            {"allow_empty": True},
    "PART_NUMBER":    {"allow_empty": True},
    "SERIAL_NUMBER":  {"allow_empty": True},
    "LAST_ACC_FH":    {"pattern": _NUM_RE, "allow_empty": True},
    "LAST_ACC_FC":    {"pattern": _NUM_RE, "allow_empty": True},
    "LAST_ACC_DATE":  {"pattern": _DATE_RE, "allow_empty": True},
    "INTERVAL_FH":    {"pattern": _NUM_RE, "allow_empty": True},
    "INTERVAL_FC":    {"pattern": _NUM_RE, "allow_empty": True},
    "INTERVAL_DAYS":  {"pattern": _NUM_RE, "allow_empty": True},
    "NEXT_DUE_FH":    {"pattern": _NUM_RE, "allow_empty": True},
    "NEXT_DUE_FC":    {"pattern": _NUM_RE, "allow_empty": True},
    "NEXT_DUE_DATE":  {"pattern": _DATE_RE, "allow_empty": True},
    "REMAINING_FH":   {"pattern": _NUM_RE, "allow_empty": True},
    "REMAINING_FC":   {"pattern": _NUM_RE, "allow_empty": True},
    "REMAINING_DAYS": {"pattern": _NUM_RE, "allow_empty": True},
    "COMMENT":        {"allow_empty": True},
    "AIRCRAFT_TYPE":  {"pattern": r"^[A-Z0-9\-]+$", "uppercase": True,
                        "allow_empty": True},
    "REFERENCE_DATE": {"pattern": _DATE_RE, "allow_empty": True},
    "REGISTRATION":   {"pattern": r"^[A-Z0-9\-]+$", "uppercase": True,
                        "allow_empty": True},
    "TSN":            {"pattern": _NUM_RE, "allow_empty": True},
    "MSN":            {"pattern": r"^\d+$", "allow_empty": True},
    "CSN":            {"pattern": _NUM_RE, "allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_ATA_HEADER_RE = re.compile(r"^ATA\s+(\d{1,2})$")
_PAGE_FOOTER_RE = re.compile(r"^Page\s+\d+\s+of\s+\d+$")
_BLANK_TOKENS = {"-", "/"}

# Left edges of the DESCRIPTION / PART_NUMBER / SERIAL_NUMBER columns
# (PDF points), from the real header/body coordinates on the sample file.
_PN_X = 165.0
_SN_X = 218.0
_NUM_X = 280.0     # start of the 12-column Last-Acc/Interval/NextDue/Remaining block
_COMMENT_X = 668.0  # gap between the widest real REMAINING_DAYS value (~658) and
                    # the narrowest real COMMENT value (~679) observed on the
                    # sample file; the two never come closer than ~20pt.

# Header x-position of each of the 12 numeric sub-columns, in the fixed
# left-to-right order they're printed -- confirmed identical on every
# page via `extract_words()`.
_NUM_FIELDS = [
    "LAST_ACC_FH", "LAST_ACC_FC", "LAST_ACC_DATE",
    "INTERVAL_FH", "INTERVAL_FC", "INTERVAL_DAYS",
    "NEXT_DUE_FH", "NEXT_DUE_FC", "NEXT_DUE_DATE",
    "REMAINING_FH", "REMAINING_FC", "REMAINING_DAYS",
]
_NUM_HEADER_X = [295.6, 337.2, 375.5, 407.4, 436.6, 469.5,
                 506.9, 536.5, 564.3, 597.8, 628.1, 653.6]

_META_RE = {
    "AIRCRAFT_TYPE":  re.compile(r"Aircraft Type:\s*(\S+)"),
    "REFERENCE_DATE": re.compile(r"Reference Date:\s*(\S+)"),
    # This template's own label is rendered with one substituted letter
    # (a template-level rendering quirk, not corpus-specific) -- matched
    # with a single-character wildcard rather than one fixed spelling.
    "REGISTRATION":   re.compile(r"Re.istration:\s*(\S+)"),
    "TSN":            re.compile(r"TSN:\s*(\S+)"),
    "MSN":            re.compile(r"MSN:\s*(\S+)"),
    "CSN":            re.compile(r"CSN:\s*(\S+)"),
}


def _nearest_num_field(x0: float) -> str:
    best_i, best_dist = 0, abs(x0 - _NUM_HEADER_X[0])
    for i in range(1, len(_NUM_HEADER_X)):
        dist = abs(x0 - _NUM_HEADER_X[i])
        if dist < best_dist:
            best_i, best_dist = i, dist
    return _NUM_FIELDS[best_i]


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


def _header_bottom(lines: list[dict]) -> float:
    """Top y of the page's own sub-column header row (four "FH" + four "FC"
    tokens) -- everything above it (title/aircraft-info/column-header
    lines) is page furniture, not table content."""
    for line in lines:
        texts = [w["text"] for w in line["words"]]
        if texts.count("FH") == 4 and texts.count("FC") == 4:
            return line["top"]
    return 0.0


def _line_text(line: dict) -> str:
    return " ".join(w["text"] for w in line["words"])


def _is_blank(s: str) -> str:
    return "" if s in _BLANK_TOKENS else s


# On a small number of rows the source PDF's own text layer places zero gap
# between the last DESCRIPTION word and the PART_NUMBER value (confirmed
# directly via `extract_words()`: e.g. "SUPPORT,LH115A5311-9" comes back as
# one token, x0 in the DESCRIPTION column, with nothing at all in the
# PART_NUMBER column's x-range for that row) -- a genuine no-space-in-the-
# source-stream quirk, the same category as this template's COMMENT-column
# gluing (see module docstring), just landing on a different column pair.
# Rather than leave PART_NUMBER silently empty (which `allow_empty` would
# never flag, hiding the problem), split the trailing PN-shaped run off the
# final DESCRIPTION word -- but ONLY as a fallback when the PN column
# genuinely produced no token of its own, so this never overrides a real,
# separately-tokenized PART_NUMBER value.
_GLUED_PN_RE = re.compile(r"^(?P<desc>.*?[A-Za-z,])(?P<pn>[0-9][0-9A-Za-z]*-[0-9A-Za-z-]+)$")


def _row_from_core(line: dict) -> dict:
    row = {col: "" for col in CANONICAL_COLUMNS}
    desc_words, pn_words, sn_words, comment_words = [], [], [], []
    for w in line["words"]:
        x0 = w["x0"]
        if x0 < _PN_X:
            desc_words.append(w["text"])
        elif x0 < _SN_X:
            pn_words.append(w["text"])
        elif x0 < _NUM_X:
            sn_words.append(w["text"])
        elif x0 < _COMMENT_X:
            field = _nearest_num_field(x0)
            row[field] = _is_blank((row[field] + " " + w["text"]).strip())
        else:
            comment_words.append(w["text"])
    if not pn_words and desc_words:
        m = _GLUED_PN_RE.match(desc_words[-1])
        if m:
            desc_words = desc_words[:-1] + [m.group("desc")]
            pn_words = [m.group("pn")]
    row["DESCRIPTION"] = " ".join(desc_words)
    row["PART_NUMBER"] = _is_blank(" ".join(pn_words))
    row["SERIAL_NUMBER"] = _is_blank(" ".join(sn_words))
    row["COMMENT"] = " ".join(comment_words)
    return row


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    meta = {k: "" for k in _META_RE}

    with pdfplumber.open(pdf_path) as pdf:
        # Header metadata is identical on every page; parse it once from
        # page 1.
        if pdf.pages:
            head_text = normalize_dashes(pdf.pages[0].extract_text() or "")
            for field, rx in _META_RE.items():
                m = rx.search(head_text)
                if m:
                    meta[field] = m.group(1)

        current_ata = ""
        for page_num, page in enumerate(pdf.pages, start=1):
            words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
            if not words:
                continue
            for w in words:
                w["text"] = normalize_dashes(w["text"])
            lines = _group_lines(words)
            header_bottom = _header_bottom(lines)
            lines = [ln for ln in lines if ln["top"] > header_bottom + 1]
            if not lines:
                continue

            classified: list[tuple[str, dict]] = []
            for line in lines:
                text = _line_text(line)
                if _PAGE_FOOTER_RE.match(text):
                    continue
                has_numeric = any(_NUM_X <= w["x0"] < _COMMENT_X for w in line["words"])
                desc_text = " ".join(w["text"] for w in line["words"] if w["x0"] < _PN_X)
                m_ata = _ATA_HEADER_RE.match(desc_text)
                if m_ata and has_numeric:
                    classified.append(("ATA", line))
                    continue
                classified.append(("CORE" if has_numeric else "ORPHAN", line))

            core_rows: list[dict] = []
            core_tops: list[float] = []
            for kind, line in classified:
                if kind == "ATA":
                    current_ata = _ATA_HEADER_RE.match(
                        " ".join(w["text"] for w in line["words"] if w["x0"] < _PN_X)
                    ).group(1).zfill(2)
                    continue
                if kind == "CORE":
                    row = _row_from_core(line)
                    row["ATA"] = current_ata
                    row["_page"] = page_num
                    core_rows.append(row)
                    core_tops.append(line["top"])

            for kind, line in classified:
                if kind != "ORPHAN" or not core_tops:
                    continue
                best_idx, best_dist = 0, abs(line["top"] - core_tops[0])
                for i in range(1, len(core_tops)):
                    dist = abs(line["top"] - core_tops[i])
                    if dist < best_dist:
                        best_idx, best_dist = i, dist
                frag = _line_text(line)
                target = core_rows[best_idx]
                if line["top"] < core_tops[best_idx]:
                    target["DESCRIPTION"] = f"{frag} {target['DESCRIPTION']}".strip()
                else:
                    target["DESCRIPTION"] = f"{target['DESCRIPTION']} {frag}".strip()

            for row in core_rows:
                row.update(meta)
                records.append(row)

    return records
