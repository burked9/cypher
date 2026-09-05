"""O/C Component Status -- born-digital, full text layer, coordinate-bucketed
columns (confirmed via a direct pdfplumber pass over the real sample file:
`extract_text()`/`extract_words()` return full content on every page, no OCR
needed). Synchronous `extract()`.

Header block (repeats verbatim at the top of every page)::

    O/C COMPONENT STATUS
    A/C TYPE: <type> REGISTRATION: <reg> As Date of: <date>
    ENGINE TYPE: <engine> MPD REV: <n> MSN: <msn> Airframe Hours: <n> FH
    MANUFACTURE DATE: <date> FIRST FLIGHT DATE: <date> Airframe Cycles: <n> FC
    Part No Serial No Description Zone FIN No ATA Installation Details TSN CSN TSI/TSR CSI/CSR Certificate N°

Parsed once from the first page and stamped on every row, same convention
this project's other header-plus-body OCCM variants use. AIRFRAME_HOURS and
AIRFRAME_CYCLES occasionally print with an embedded thousands-separator
space (e.g. a cycles figure rendered as two space-separated tokens) --
captured verbatim, space included, same as the TSN/CSN/TSI_TSR/CSI_CSR body
columns below.

A page footer line ("Prepared by: <company> ... <n> of <n>") repeats on
every page and is dropped by its literal, generic "Prepared by:" prefix --
not by the company name, which is real-corpus-specific and never hardcoded
here.

Data-row geometry -- word x-position bucketing (same technique as
`occm_report.py` / `occm_component_status_dual_basis.py`), not token-count
splitting, because DESCRIPTION is free text of variable width and several
numeric columns (TSN/CSN/TSI_TSR/CSI_CSR) render with an embedded
thousands-separator space (e.g. a figure printed as two whitespace-split
tokens like "<n> <n>,00" for one value), which a naive `split()` would
misattribute:

    PART_NUMBER | SERIAL_NUMBER | DESCRIPTION | ZONE | FIN | ATA |
    INSTALLATION_DETAILS | TSN | CSN | TSI_TSR | CSI_CSR | CERTIFICATE_NO

Column x-boundaries (PDF points) below were derived directly from the real
header row's own word positions via `extract_words()`, then adjusted where
a data row's own values ran wider than the naive midpoint between two
header labels (confirmed directly: e.g. a long DESCRIPTION value's trailing
word, and a stray single extra glyph tokenized separately from the FIN
value immediately before it, both needed the boundary pushed further right
than the plain header-label midpoint to land in the correct column on every
inspected page).

Row anchor: a 2-digit token landing in the ATA x-position band -- confirmed
present on every real data row.

Two flavours of line-wrap are confirmed directly on the real sample file,
both handled by attaching a non-anchor physical line to whichever anchor
row (previous or next) it sits vertically closer to, prepending if that
row's anchor line comes after it or appending if before -- this is a
best-effort, deterministic attribution for a genuinely ambiguous source
layout (per this project's "never guess a wrong split" convention, applied
here at the whole-line level: each fragment is assigned by one fixed rule,
not guessed per case):

  1. Trailing overflow -- CERTIFICATE_NO (and occasionally DESCRIPTION) can
     spill onto one or more physical lines directly beneath a row whose own
     line already ended, before the next row's anchor line appears.

  2. Leading overflow -- DESCRIPTION can instead print BEFORE its own row's
     anchor line, split across the tail end of the description and its
     start, e.g.::

         <description prefix, no other columns populated>
         <pn> <sn> <description suffix> <zone> <fin> <ata> <install_date> ...

A recurring page footer's stray 2-digit page-number token (e.g. "... <n> of
<n>") can coincidentally land in the ATA x-band; the footer line is dropped
by its own literal prefix before anchor detection runs, so it is never
mistaken for a data row.
"""
from __future__ import annotations
import re

import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "O/C Component Status"
SIGNATURES = [
    "O/C COMPONENT STATUS",
    "Part No Serial No Description Zone FIN No ATA Installation Details",
]

CANONICAL_COLUMNS = [
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
    "ZONE",
    "FIN",
    "ATA",
    "INSTALLATION_DETAILS",
    "TSN",
    "CSN",
    "TSI_TSR",
    "CSI_CSR",
    "CERTIFICATE_NO",
    # Header metadata -- same on every row of a given file.
    "AIRCRAFT_TYPE",
    "AIRCRAFT_REG",
    "REPORT_DATE",
    "ENGINE_TYPE",
    "MPD_REV",
    "MSN",
    "AIRFRAME_HOURS",
    "MANUFACTURE_DATE",
    "FIRST_FLIGHT_DATE",
    "AIRFRAME_CYCLES",
]

# TSN/CSN/TSI_TSR/CSI_CSR: plain integers, optionally with a thousands
# separator (space, comma or dot) and/or a decimal-comma remainder, or the
# literal placeholder "UNK" seen throughout the real sample where a figure
# isn't tracked for that component.
_NUM_OR_UNK = r"^(?:UNK|\d+(?:[ ,.]\d{3})*(?:,\d{1,2})?)$"
_OVERRIDES = {
    "FIN":                {"allow_empty": True},
    # Month abbreviations in the real sample mix English ("Sep", "Dec") and
    # French ("nov", "déc", "janv") forms, both title- and lower-case --
    # confirmed directly across the file, so the pattern only checks shape.
    "INSTALLATION_DETAILS": {"pattern": r"^\d{1,2}-[A-Za-zÀ-ÿ]{3,5}-\d{2,4}$"},
    "TSN":                {"pattern": _NUM_OR_UNK, "allow_empty": True},
    "CSN":                {"pattern": _NUM_OR_UNK, "allow_empty": True},
    "TSI_TSR":            {"pattern": _NUM_OR_UNK, "allow_empty": True},
    "CSI_CSR":            {"pattern": _NUM_OR_UNK, "allow_empty": True},
    # Certificate references are highly variable free text ("EASA F1 N°
    # <n>", "TC N° <n>", "FAA FORM 8130-3 N° <n>", or a bare number) --
    # confirmed directly across the file; not pattern-checked.
    "CERTIFICATE_NO":     {"allow_empty": True},
    "AIRCRAFT_TYPE":      {"allow_empty": True},
    "AIRCRAFT_REG":       {"pattern": r"^[A-Z0-9\-]+$", "uppercase": True, "allow_empty": True},
    "REPORT_DATE":        {"allow_empty": True},
    "ENGINE_TYPE":        {"allow_empty": True},
    "MPD_REV":            {"pattern": r"^\d+$", "allow_empty": True},
    "MSN":                {"pattern": r"^[A-Z0-9]+$", "uppercase": True, "allow_empty": True},
    "AIRFRAME_HOURS":     {"allow_empty": True},
    "MANUFACTURE_DATE":   {"allow_empty": True},
    "FIRST_FLIGHT_DATE":  {"allow_empty": True},
    "AIRFRAME_CYCLES":    {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# --- Column layout ---------------------------------------------------------
# x0 boundaries (PDF points), read from the header row's own word positions
# via extract_words() and widened past the plain header-label midpoint in
# the DESCRIPTION/ZONE and ZONE/FIN bands, and past the plain FIN/ATA
# midpoint, to keep confirmed real overflow (a long DESCRIPTION value's
# trailing word; a FIN value's occasional stray extra glyph, tokenized
# separately by the source PDF) landing in the correct column rather than
# bleeding into its neighbour -- both confirmed directly against real rows.
_FIELDS = [
    "PART_NUMBER", "SERIAL_NUMBER", "DESCRIPTION", "ZONE", "FIN", "ATA",
    "INSTALLATION_DETAILS", "TSN", "CSN", "TSI_TSR", "CSI_CSR", "CERTIFICATE_NO",
]
_BOUNDS = [0, 209, 373.6, 615, 660, 745, 788.6, 899, 1025.5, 1116.4, 1206.5, 1311.7, 10 ** 6]

_ATA_RE = re.compile(r"^\d{2}$")
_HEADER_PREFIXES = ("O/C COMPONENT", "A/C TYPE", "ENGINE TYPE", "MANUFACTURE DATE", "Part No")

_META_RE_1 = re.compile(r"A/C TYPE:\s*(\S+)\s+REGISTRATION:\s*(\S+)\s+As Date of:\s*(\S+)")
_META_RE_2 = re.compile(r"ENGINE TYPE:\s*(\S+)\s+MPD REV:\s*(\S+)\s+MSN:\s*(\S+)\s+Airframe Hours:\s*([\d,.\s]+?)\s*FH")
_META_RE_3 = re.compile(r"MANUFACTURE DATE:\s*(\S+)\s+FIRST FLIGHT DATE:\s*(\S+)\s+Airframe Cycles:\s*([\d,.\s]+?)\s*FC")


def _parse_meta(text: str) -> dict:
    meta: dict[str, str] = {}
    m = _META_RE_1.search(text)
    if m:
        meta["AIRCRAFT_TYPE"] = m.group(1)
        meta["AIRCRAFT_REG"] = m.group(2)
        meta["REPORT_DATE"] = m.group(3)
    m = _META_RE_2.search(text)
    if m:
        meta["ENGINE_TYPE"] = m.group(1)
        meta["MPD_REV"] = m.group(2)
        meta["MSN"] = m.group(3)
        meta["AIRFRAME_HOURS"] = m.group(4).strip()
    m = _META_RE_3.search(text)
    if m:
        meta["MANUFACTURE_DATE"] = m.group(1)
        meta["FIRST_FLIGHT_DATE"] = m.group(2)
        meta["AIRFRAME_CYCLES"] = m.group(3).strip()
    return meta


def _bucket(x0: float) -> str:
    for i in range(len(_BOUNDS) - 1):
        if _BOUNDS[i] <= x0 < _BOUNDS[i + 1]:
            return _FIELDS[i]
    return _FIELDS[-1]


def _has_ata_token(words: list[dict]) -> bool:
    return any(_bucket(w["x0"]) == "ATA" and _ATA_RE.match(w["text"]) for w in words)


def _bucket_words(words: list[dict]) -> dict:
    row = {f: "" for f in _FIELDS}
    for w in sorted(words, key=lambda w: w["x0"]):
        f = _bucket(w["x0"])
        row[f] = (row[f] + " " + w["text"]).strip()
    return row


def _group_lines(words: list[dict]) -> list[dict]:
    """Cluster words into physical lines by y-position, tolerant of
    sub-point 'top' jitter between words nominally on the same line."""
    ws = sorted(words, key=lambda w: (w["top"], w["x0"]))
    lines: list[dict] = []
    for w in ws:
        if lines and abs(w["top"] - lines[-1]["top"]) <= 2.5:
            lines[-1]["words"].append(w)
            lines[-1]["top"] = (lines[-1]["top"] + w["top"]) / 2
        else:
            lines.append({"top": w["top"], "words": [w]})
    return lines


def _extract_page(page) -> list[dict]:
    words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
    if not words:
        return []
    lines = _group_lines(words)

    real_lines = []
    for line in lines:
        text = " ".join(w["text"] for w in sorted(line["words"], key=lambda w: w["x0"]))
        stripped = text.strip()
        if stripped == "," or not stripped:
            continue
        if any(stripped.startswith(p) for p in _HEADER_PREFIXES):
            continue
        if stripped.startswith("Prepared by"):
            continue
        real_lines.append(line)

    anchors = [i for i, line in enumerate(real_lines) if _has_ata_token(line["words"])]
    anchor_set = set(anchors)

    rows: list[dict] = []
    row_by_anchor: dict[int, dict] = {}
    for i in anchors:
        row = _bucket_words(real_lines[i]["words"])
        rows.append(row)
        row_by_anchor[i] = row

    for i, line in enumerate(real_lines):
        if i in anchor_set:
            continue
        prev_a = max((a for a in anchors if a < i), default=None)
        next_a = min((a for a in anchors if a > i), default=None)
        if prev_a is None and next_a is None:
            continue  # no anchor row on this page to attach an orphan fragment to
        if prev_a is None:
            target_idx = next_a
        elif next_a is None:
            target_idx = prev_a
        else:
            gap_prev = real_lines[i]["top"] - real_lines[prev_a]["top"]
            gap_next = real_lines[next_a]["top"] - real_lines[i]["top"]
            target_idx = prev_a if gap_prev <= gap_next else next_a
        is_leading = target_idx == next_a
        target_row = row_by_anchor[target_idx]
        frag = _bucket_words(line["words"])
        for f, val in frag.items():
            if not val:
                continue
            if not target_row[f]:
                target_row[f] = val
            elif is_leading:
                target_row[f] = f"{val} {target_row[f]}".strip()
            else:
                target_row[f] = f"{target_row[f]} {val}".strip()

    return rows


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    meta: dict[str, str] = {}
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            if page_num == 1:
                meta = _parse_meta(page.extract_text() or "")
            for row in _extract_page(page):
                row.update(meta)
                row["_page"] = page_num
                records.append(row)
    return records
