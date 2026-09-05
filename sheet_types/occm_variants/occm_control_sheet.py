"""OCCM Control Sheet -- born-digital, full text layer, coordinate-bucketed
columns (confirmed via a direct pdfplumber pass over the real sample file:
`extract_text()`/`extract_words()` return full content on every page, no OCR
needed). Synchronous `extract()`.

Header block (repeats verbatim at the top of every page)::

    OCCM Control Sheet
    Revision: <n>
    Aircraft Type: <type> Reference Date: <date>
    Registration: <reg> TSN: <n>
    MSN: <msn> CSN: <n>
    DESCRIPTION Part Number Serial Number Position Installation Date FH FC TSI CSI ATA

Parsed once from the first page and stamped on every row, same convention
this project's other header-plus-body OCCM variants use.

Unusual column order (confirmed directly against the real header row's own
word positions via `extract_words()`, not assumed) -- ATA is the LAST
column here, not the first as in several sibling OCCM variants::

    DESCRIPTION | PART_NUMBER | SERIAL_NUMBER | POSITION | INSTALLATION_DATE |
    FH | FC | TSI | CSI | ATA

A recurring "ATA <n> - <chapter name>" section-heading line breaks up the
body every so often (e.g. a line like "ATA <n> - <chapter name> -
GENERAL"). These carry no token in the ATA column's own x-band (confirmed:
every word on that line sits well to the left of it), so they are dropped
outright by a literal `^ATA \\d+\\s*-` prefix match rather than risking them
being swept up as an orphan wrap-fragment of a neighbouring data row.

A page footer line ("Rev. <n> <n> of <n> Prepared by <company>") repeats on
every page and is dropped by its own literal "Rev." prefix -- not by the
company name, which is real-corpus-specific and never hardcoded here.

Data-row geometry -- word x-position bucketing (same technique as
`oc_component_status.py`), not token-count splitting, because DESCRIPTION is
free text of variable width and SERIAL_NUMBER occasionally wraps onto its
own physical line(s) around the anchor row.

Row anchor: a 2-digit token landing in the ATA x-position band -- confirmed
present on every real data row.

One flavour of line-wrap is confirmed directly on the real sample file: a
SERIAL_NUMBER value too wide for its own row can spill across up to three
physical lines -- a leading fragment printed just above the row's own
anchor line, the row itself (with that column left blank), and a trailing
fragment printed just below, e.g.::

    <sn prefix, no other columns populated>
    <description> <pn> <install_date> <fh> <fc> <tsi> <csi> <ata>
    <sn suffix, no other columns populated>

Handled by attaching each non-anchor physical line to whichever anchor row
(previous or next) it sits vertically closer to, prepending if that row's
anchor line comes after it (leading overflow) or appending if before
(trailing overflow) -- a fixed, deterministic rule rather than a per-case
guess, per this project's "never guess a wrong split" convention.
"""
from __future__ import annotations
import re

import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "OCCM Control Sheet"
SIGNATURES = [
    "OCCM Control Sheet",
    "DESCRIPTION Part Number Serial Number Position Installation Date FH FC TSI CSI ATA",
]

CANONICAL_COLUMNS = [
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "POSITION",
    "INSTALLATION_DATE",
    "FH",
    "FC",
    "TSI",
    "CSI",
    "ATA",
    # Header metadata -- same on every row of a given file.
    "REVISION",
    "AIRCRAFT_TYPE",
    "REFERENCE_DATE",
    "AIRCRAFT_REG",
    "TSN",
    "MSN",
    "CSN",
]

# FH/FC/TSI/CSI: plain integers, or the literal placeholder "UNK" seen
# throughout the real sample where a figure isn't tracked for that
# component.
_NUM_OR_UNK = r"^(?:UNK|\d+)$"
_OVERRIDES = {
    "POSITION": {"allow_empty": True},
    "INSTALLATION_DATE": {"pattern": r"^\d{1,2}-[A-Za-z]{3}-\d{2,4}$"},
    "FH": {"pattern": _NUM_OR_UNK, "allow_empty": True},
    "FC": {"pattern": _NUM_OR_UNK, "allow_empty": True},
    "TSI": {"pattern": _NUM_OR_UNK, "allow_empty": True},
    "CSI": {"pattern": _NUM_OR_UNK, "allow_empty": True},
    "REVISION": {"pattern": r"^\d+$", "allow_empty": True},
    "AIRCRAFT_TYPE": {"allow_empty": True},
    "REFERENCE_DATE": {"allow_empty": True},
    "AIRCRAFT_REG": {"pattern": r"^[A-Z0-9\-]+$", "uppercase": True, "allow_empty": True},
    "TSN": {"pattern": r"^\d+$", "allow_empty": True},
    "MSN": {"pattern": r"^[A-Z0-9]+$", "uppercase": True, "allow_empty": True},
    "CSN": {"pattern": r"^\d+$", "allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# --- Column layout ---------------------------------------------------------
# x0 boundaries (PDF points), read from the header row's own word positions
# via extract_words(), then adjusted past the plain header-label midpoint in
# the PART_NUMBER/SERIAL_NUMBER band (a wrapped PART_NUMBER continuation
# token can land as far right as x0~302, while the earliest confirmed real
# SERIAL_NUMBER start is x0~329.8 -- the boundary sits between the two so
# neither bleeds into the other's column), confirmed directly against real
# rows.
_FIELDS = [
    "DESCRIPTION", "PART_NUMBER", "SERIAL_NUMBER", "POSITION",
    "INSTALLATION_DATE", "FH", "FC", "TSI", "CSI", "ATA",
]
_BOUNDS = [0, 233, 320, 405, 460, 555, 600, 645, 690, 733, 10 ** 6]

_ATA_RE = re.compile(r"^\d{2}$")
_HEADER_PREFIXES = (
    "OCCM Control Sheet", "Revision:", "Aircraft Type:", "Registration:",
    "MSN:", "DESCRIPTION Part Number",
)
_SECTION_HEADER_RE = re.compile(r"^ATA\s+\d+\s*-")

_META_RE_REVISION = re.compile(r"Revision:\s*(\S+)")
_META_RE_1 = re.compile(r"Aircraft Type:\s*(\S+)\s+Reference Date:\s*(\S+)")
_META_RE_2 = re.compile(r"Registration:\s*(\S+)\s+TSN:\s*(\S+)")
_META_RE_3 = re.compile(r"MSN:\s*(\S+)\s+CSN:\s*(\S+)")


def _parse_meta(text: str) -> dict:
    meta: dict[str, str] = {}
    m = _META_RE_REVISION.search(text)
    if m:
        meta["REVISION"] = m.group(1)
    m = _META_RE_1.search(text)
    if m:
        meta["AIRCRAFT_TYPE"] = m.group(1)
        meta["REFERENCE_DATE"] = m.group(2)
    m = _META_RE_2.search(text)
    if m:
        meta["AIRCRAFT_REG"] = m.group(1)
        meta["TSN"] = m.group(2)
    m = _META_RE_3.search(text)
    if m:
        meta["MSN"] = m.group(1)
        meta["CSN"] = m.group(2)
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
        if not stripped:
            continue
        if any(stripped.startswith(p) for p in _HEADER_PREFIXES):
            continue
        if stripped.startswith("Rev."):
            continue
        if _SECTION_HEADER_RE.match(stripped):
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
