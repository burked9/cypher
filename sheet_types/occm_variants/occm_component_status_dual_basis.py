"""OCCM Component Status (Dual-Basis TSN/TSI/LSN/LSI) -- born-digital, full
text layer, coordinate-bucketed columns (real pdfplumber pass confirmed a
clean text layer on every page of the known sample; no OCR needed).

Header block (repeats verbatim at the top of every page)::

    ON CONDITION COMPONENTS REPORT
    A/C TYPE: <type> DATE: <date> <date2>
    A/C REG: <reg> AIRFRAME HOURS: <hours> <hours2>
    A/C MSN: <msn> AIRFRAME CYCLES: <cycles> <cycles2>
    ATA P/N DESCRIPTION S/N POS MPCODE INST. DATE UNIT TSN TSI LSN LSI

The header prints TWO figures side by side for both hours and cycles (and
two dates). Confirmed against the real sample: the first figure/date lines
up with the report's own generation date and matches the TSN values seen on
the bulk of that page's H-unit data rows almost exactly, while the second
figure/date is noticeably older and slightly lower. The most plausible read
is that the OCCM subsystem's own snapshot lags the main utilization feed by
some weeks/months, i.e. first pair = "as of report date", second pair = "as
of the OCCM subsystem's last internal refresh" -- but this project's
convention is to never guess at a semantic label it can't confirm, so both
are captured verbatim as REPORT_DATE/REPORT_DATE_2 and
AIRFRAME_HOURS/AIRFRAME_HOURS_2 (same for cycles) rather than asserting
which one means what.

Data-row geometry -- this is the interesting part. The column header names
a single TSN/TSI/LSN/LSI block, but the real per-row rendering is NOT
"one row, four values" for most rows. A single component instead typically
prints as TWO physical rows sharing every other field verbatim, one with
UNIT="H" and one with UNIT="LDG"::

    <ata> <pn> <desc...> <sn> <pos> <mpcode> <install_date> LDG <n1> <n2>
    <ata> <pn> <desc...> <sn> <pos> <mpcode> <install_date> H   <n1> <n2>

Confirmed directly via `extract_words()` x-position on the real sample: the
two numbers on the UNIT="H" row are right-aligned under the header's own
TSN/TSI column positions, while the two numbers on the UNIT="LDG" row for
the very same component are right-aligned under the LSN/LSI column
positions instead -- i.e. UNIT is not a value alongside TSN/TSI, it tells
you WHICH pair of the four named columns that particular physical row is
actually populating (hours-basis -> TSN/TSI, landings-basis -> LSN/LSI).
A smaller number of rows print all four values on one line at once (UNIT is
then usually "H", sometimes the combined token "H/LDG", rarely "D"); those
still validate correctly under the same x-position bucketing since the
extra pair simply lands in the LSN/LSI buckets on that same row. A further
block of rows (an engine's QEC/LRU accessory list, appearing under a plain
section-heading line rather than a per-row ATA) carries no ATA and no UNIT
token at all, with all four numeric values (frequently all "0" for a
just-installed part) landing directly under TSN/TSI/LSN/LSI with nothing in
between -- handled the same way by the same bucketing, no special case
needed.

Column x-boundaries (PDF points), derived from the real header row's own
word positions via `extract_words()` and confirmed stable across every
inspected page. Bucketing is x0-based (nearest preceding anchor), not
token-count based, precisely because ATA, POS, UNIT and any subset of the
four numeric columns can each independently be blank on a given row without
shifting anything after it:

    ATA | PART_NUMBER | DESCRIPTION | SERIAL_NUMBER | POSITION | MPCODE |
    INSTALL_DATE | UNIT | TSN | TSI | LSN | LSI

ATA in the source is not a bare 2-digit chapter -- it is a longer
alphanumeric extended code (commonly 4-6 characters, e.g. a 6-digit
"<chapter><section><subject>" string, occasionally a 4-digit chapter+
section only). Per this project's established convention (see e.g.
`b777_annex8_occm.py`, `mm510.py`), the raw code is kept verbatim in its own
ATA_FULL column and the leading 2 characters are additionally lifted into
the shared 2-digit ATA column so this variant still participates in the
router's generic ATA-chapter validation/forward-fill.

A DESCRIPTION that wraps onto a second physical line continues as a bare
word (or short phrase) sitting only in the DESCRIPTION x-position bucket,
with every other bucket empty on that line -- merged onto the previous
record's DESCRIPTION rather than treated as its own row.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "OCCM Component Status (Dual-Basis TSN/TSI/LSN/LSI)"
SIGNATURES = [
    "ATA P/N DESCRIPTION S/N POS MPCODE INST. DATE UNIT TSN TSI LSN LSI",
]

CANONICAL_COLUMNS = [
    "ATA",
    "ATA_FULL",
    "PART_NUMBER",
    "DESCRIPTION",
    "SERIAL_NUMBER",
    "POSITION",
    "MPCODE",
    "INSTALL_DATE",
    "UNIT",
    "TSN",
    "TSI",
    "LSN",
    "LSI",
    # Header metadata -- same on every row of a given file.
    "AIRCRAFT_TYPE",
    "REPORT_DATE",
    "REPORT_DATE_2",
    "AIRCRAFT_REG",
    "AIRFRAME_HOURS",
    "AIRFRAME_HOURS_2",
    "AIRCRAFT_MSN",
    "AIRFRAME_CYCLES",
    "AIRFRAME_CYCLES_2",
]

# --- Column layout -------------------------------------------------------
# x0 anchors below were read directly off the sample's header row via
# pdfplumber's extract_words() and confirmed against many data rows across
# the file -- each is a hard, fixed left-margin the real column's own value
# starts at (numeric columns match to within 0.1pt everywhere in the file).
#
# Bucketing is NOT plain midpoint-between-anchors. A reserved column
# (DESCRIPTION most often, occasionally SERIAL_NUMBER or POSITION) can hold
# text wide enough to run well past the halfway point to the next column's
# anchor without actually reaching it -- confirmed directly on the sample
# (e.g. a wrapped multi-word DESCRIPTION pushes a trailing word's x0 past
# the DESCRIPTION/SERIAL_NUMBER midpoint while the real SERIAL_NUMBER token
# still starts exactly at its own fixed anchor). Likewise a wide month name
# (e.g. "December", "September") pushes that row's trailing ", YYYY" year
# token as far right as x0=571, well past the plain INSTALL_DATE/UNIT
# midpoint, while genuine UNIT tokens never start before x0=599.9.
#
# Each anchor below is instead a hard left-margin: every genuine value in
# that column starts within ~0.1pt of it everywhere in the sample. A word is
# matched to a column by exact anchor proximity FIRST (tight tolerance --
# this is what correctly finds the real SERIAL_NUMBER/POSITION/MPCODE/UNIT/
# numeric token even when the previous column has overflowed close by).
# Only a word that matches no anchor closely falls back to "nearest
# preceding anchor" (floor), which is what correctly keeps overflow text
# (a wrapped DESCRIPTION word, a spilled year) attributed to the column it
# actually overflowed from rather than bleeding into its neighbour.
_TOLERANCE = 2.0
_NAMED_COLS = [
    ("ATA_FULL",      15.8),
    ("PART_NUMBER",   49.6),
    ("DESCRIPTION",   165.4),
    ("SERIAL_NUMBER", 295.9),
    ("POSITION",      381.7),
    ("MPCODE",        473.8),
    ("INSTALL_DATE",  524.1),
    ("UNIT",          599.9),
    ("TSN",           642.6),
    ("TSI",           688.8),
    ("LSN",           735.1),
    ("LSI",           781.4),
]
_COL_NAMES = [c[0] for c in _NAMED_COLS]
_COL_X0 = [c[1] for c in _NAMED_COLS]


def _bucket_for(x0: float) -> str:
    for name, anchor in zip(_COL_NAMES, _COL_X0):
        if abs(x0 - anchor) <= _TOLERANCE:
            return name
    best = _COL_NAMES[0]
    for name, anchor in zip(_COL_NAMES, _COL_X0):
        if anchor <= x0:
            best = name
        else:
            break
    return best


_OVERRIDES = {
    "ATA_FULL":     {"pattern": r"^[A-Z0-9]{1,10}$", "uppercase": True, "allow_empty": True},
    "POSITION":     {"pattern": r"^[A-Z0-9 ./\-]{1,20}$", "uppercase": True, "allow_empty": True},
    "MPCODE":       {"pattern": r"^[A-Z]{2}$", "uppercase": True, "allow_empty": True},
    "INSTALL_DATE": {"pattern": r"^[A-Za-z]+ \d{1,2}, \d{4}$", "allow_empty": True},
    "UNIT":         {"pattern": r"^(H|LDG|D|H/LDG)$", "uppercase": True, "allow_empty": True},
    "TSN":          {"pattern": r"^\d+(\.\d+)?$", "allow_empty": True},
    "TSI":          {"pattern": r"^\d+(\.\d+)?$", "allow_empty": True},
    "LSN":          {"pattern": r"^\d+(\.\d+)?$", "allow_empty": True},
    "LSI":          {"pattern": r"^\d+(\.\d+)?$", "allow_empty": True},
    "AIRCRAFT_TYPE":      {"pattern": r"^[A-Z0-9\-]+$", "uppercase": True, "allow_empty": True},
    "REPORT_DATE":        {"pattern": r"^\d{1,2}-[A-Za-z]{3}-\d{4}$", "allow_empty": True},
    "REPORT_DATE_2":      {"pattern": r"^\d{1,2}-[A-Za-z]{3}-\d{2}$", "allow_empty": True},
    "AIRCRAFT_REG":       {"pattern": r"^[A-Z0-9\-]+$", "uppercase": True, "allow_empty": True},
    "AIRFRAME_HOURS":     {"pattern": r"^[\d,]+:\d{2}$", "allow_empty": True},
    "AIRFRAME_HOURS_2":   {"pattern": r"^\d+$", "allow_empty": True},
    "AIRCRAFT_MSN":       {"pattern": r"^[A-Z0-9]+$", "uppercase": True, "allow_empty": True},
    "AIRFRAME_CYCLES":    {"pattern": r"^\d+$", "allow_empty": True},
    "AIRFRAME_CYCLES_2":  {"pattern": r"^\d+$", "allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_MPCODE_RE = re.compile(r"^[A-Z]{2}$")
_HEADER_MARKERS = ("ATA", "P/N", "DESCRIPTION", "S/N", "MPCODE")

_META_RE_TYPE = re.compile(r"A/C TYPE:\s*(\S+)\s+DATE:\s*(\S+)\s+(\S+)")
_META_RE_REG = re.compile(r"A/C REG:\s*(\S+)\s+AIRFRAME HOURS:\s*([\d,:]+)\s+(\S+)")
_META_RE_MSN = re.compile(r"A/C MSN:\s*(\S+)\s+AIRFRAME CYCLES:\s*(\S+)\s+(\S+)")


def _parse_meta(text: str) -> dict:
    meta: dict[str, str] = {}
    m = _META_RE_TYPE.search(text)
    if m:
        meta["AIRCRAFT_TYPE"] = m.group(1)
        meta["REPORT_DATE"] = m.group(2)
        meta["REPORT_DATE_2"] = m.group(3)
    m = _META_RE_REG.search(text)
    if m:
        meta["AIRCRAFT_REG"] = m.group(1)
        meta["AIRFRAME_HOURS"] = m.group(2)
        meta["AIRFRAME_HOURS_2"] = m.group(3)
    m = _META_RE_MSN.search(text)
    if m:
        meta["AIRCRAFT_MSN"] = m.group(1)
        meta["AIRFRAME_CYCLES"] = m.group(2)
        meta["AIRFRAME_CYCLES_2"] = m.group(3)
    return meta


def _cluster_rows(words: list[dict]) -> list[list[dict]]:
    """Group words into visual rows by their `top` coordinate. Rows in the
    sample are separated by a consistent ~8.4pt pitch; a small tolerance
    clusters words on the same printed line without merging adjacent ones."""
    if not words:
        return []
    tops = sorted(set(round(w["top"], 1) for w in words))
    clusters: list[list[float]] = []
    cur = [tops[0]]
    for t in tops[1:]:
        if t - cur[-1] <= 1.5:
            cur.append(t)
        else:
            clusters.append(cur)
            cur = [t]
    clusters.append(cur)

    row_groups = []
    for cl in clusters:
        lo, hi = min(cl) - 0.3, max(cl) + 0.3
        row_words = [w for w in words if lo <= w["top"] <= hi]
        if row_words:
            row_groups.append(row_words)
    return row_groups


def _is_header_or_meta_row(joined: str) -> bool:
    if "AIRFRAME" in joined or "A/C TYPE" in joined or "A/C REG" in joined or "A/C MSN" in joined:
        return True
    if all(marker in joined for marker in _HEADER_MARKERS):
        return True
    if joined.startswith("ON CONDITION COMPONENTS") or joined.startswith("PRODUCED BY"):
        return True
    return False


def _parse_row(row_words: list[dict]) -> dict | None:
    joined = " ".join(w["text"] for w in row_words)
    if _is_header_or_meta_row(joined):
        return None

    row_words = sorted(row_words, key=lambda w: w["x0"])
    buckets: dict[str, list[str]] = {}
    for w in row_words:
        col = _bucket_for(w["x0"])
        buckets.setdefault(col, []).append(w["text"])

    mpcode_val = " ".join(buckets.get("MPCODE", []))
    install_date_val = " ".join(buckets.get("INSTALL_DATE", []))
    if not _MPCODE_RE.match(mpcode_val) or not install_date_val:
        return None

    rec: dict = {c: "" for c in CANONICAL_COLUMNS}
    for name, _ in _NAMED_COLS:
        rec[name] = " ".join(buckets.get(name, []))
    rec["ATA"] = rec["ATA_FULL"][:2]
    return rec


def _is_wrap_continuation(row_words: list[dict]) -> bool:
    """A description-only continuation line: every word in the row falls in
    the DESCRIPTION x-position bucket, nothing else populated."""
    if not row_words:
        return False
    for w in row_words:
        if _bucket_for(w["x0"]) != "DESCRIPTION":
            return False
    return True


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    meta: dict[str, str] = {}
    with pdfplumber.open(pdf_path) as pdf:
        first_text = pdf.pages[0].extract_text() or "" if pdf.pages else ""
        meta = _parse_meta(first_text)

        last_record: dict | None = None
        for page_num, page in enumerate(pdf.pages, start=1):
            words = page.extract_words()
            if not words:
                continue
            for row_words in _cluster_rows(words):
                rec = _parse_row(row_words)
                if rec is not None:
                    for k, v in meta.items():
                        rec[k] = v
                    rec["_page"] = page_num
                    records.append(rec)
                    last_record = rec
                    continue
                if last_record is not None and _is_wrap_continuation(row_words):
                    extra = " ".join(w["text"] for w in sorted(row_words, key=lambda w: w["x0"]))
                    last_record["DESCRIPTION"] = (last_record["DESCRIPTION"] + " " + extra).strip()
                    continue
                last_record = None
    return records
