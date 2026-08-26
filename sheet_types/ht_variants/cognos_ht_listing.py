"""Cognos-generated "<tail> HT Listing <date>" export.

Header, values genericized below but the shape is real::

    <tail> HT Listing <date>
    ATA Slot Name Equipment ID Serial Number Part Number Location Install Date TSN TSO TSR CSN CSO CSR Last Date Done / Next Due Date Available Trigger Life Limit Life Limit Life Limit Life Remaining Life Remaining Life Remaining AMS
    Mfg Date (FH/FC/DAYS) (FH) (Cycles) (Days) (FH) (Cycles) (Days)
    21 FAN-RH RECIRC 210HG 00110903 VR4100-04 RH 26/03/2017 UNK UNK 3332:13 UNK UNK 1481 08/03/2017 09/01/2020FH 8000 4667:47 212151-01-01-CX
    21 VLV-FLOW CTRL P1 511HB 00372 964F0000-02 1 27/01/2018 84702:36 84702:36 1196:59 21579.8 21579.8 535 19/07/2017 22/07/2019FC 2000 1399 215100-01-1

This report re-prints its 3-line column header at the top of every page
(the header's own x-positions drift by a handful of PDF points from one
export to the next, and even the header-vs-body indent within a single
export is not consistent -- see below), but each data row is always one
self-contained physical text line -- no wrapping, no orphan continuation
fragments straddling rows.

Row grain: one row per component. ATA, Slot Name (component description,
one or more words), Equipment ID (a short FIN-like position code),
Serial Number, Part Number, and Install Date are clean, reliably-present
fields; Location is present on most but not all rows (blank on e.g. some
avionics LRU rows with no L/R or numbered position). Everything from TSN
onward -- TSN/TSO/TSR/CSN/CSO/CSR, Last-Date-Done, a Next-Due-Date with a
trigger-basis code glued directly onto it with no separating space (e.g.
"09/01/2020FH"), the ragged ATA/FH/Cycles/Days Life-Limit and
Life-Remaining block, and a trailing AMS task-reference code (occasionally
a comma-separated list of several codes) -- is dense, column-ragged (which
of FH/Cycles/Days actually gets a value depends on which basis the part is
tracked against) and low per-field value split out individually, so it's
folded into one `STATUS_TRAIL` catch-all string, same call this project's
other HT variants with a similar dense trailing block make (see
`hard_time_report_config_slot.py`, `time_controlled_components_status.py`,
`air_france_ccinv_aircraft_inventory.py`).

Column boundaries are derived dynamically per page from that page's own
header line rather than hardcoded, because the absolute x-position of
each column drifts between exports of this same report (observed several
PDF points of drift across different files, plausibly due to
component-description or file-name-in-header width differences shifting
the whole table), and because the header word for a column is not
reliably positioned at that column's true left edge -- on some exports a
header label sits a few points to the *right* of where the narrowest
real data value in that column starts (Cognos appears to pad/pack header
text independently of the data grid). Taking the midpoint between each
pair of adjacent header labels as the bin boundary, rather than a header
label's own x0, absorbs that slop reliably across every sample checked.

Row anchor: a leading 2-digit ATA-chapter token, positioned (by x0) in the
ATA column's bin on its physical line.

Known edge case: on rows where Slot Name is unusually long (several
words), its last word can land just past the SLOT_NAME/EQUIPMENT_ID
midpoint boundary and get pulled into EQUIPMENT_ID instead (observed e.g.
a component whose slot name's last word is "ASSY", landing ~2.5pt over
the boundary). EQUIPMENT_ID's pattern rule has no embedded-space allowance,
so this correctly soft-flags the affected row rather than silently
misrepresenting it.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.ht_variants._base import merged_rules

NAME = "Cognos HT Listing"
SIGNATURES = [
    "HT LISTING",
    "SLOT NAME EQUIPMENT ID SERIAL NUMBER PART NUMBER LOCATION INSTALL DATE",
]

CANONICAL_COLUMNS = [
    "ATA",
    "SLOT_NAME",
    "EQUIPMENT_ID",
    "SERIAL_NUMBER",
    "PART_NUMBER",
    "LOCATION",
    "INSTALL_DATE",
    "STATUS_TRAIL",
]

_OVERRIDES = {
    "SLOT_NAME":     {"uppercase": True, "allow_empty": True},
    "EQUIPMENT_ID":  {"pattern": r"^[A-Z0-9][A-Z0-9\-/#]*$", "uppercase": True,
                       "allow_empty": True},
    # Location is often a single character/digit ("1", "A") but sometimes
    # two tokens (a side plus a numbered position, e.g. "LH 1") -- allow
    # an embedded space, and don't require 2+ characters.
    "LOCATION":      {"pattern": r"^[A-Z0-9](?:[A-Z0-9/\- ]*[A-Z0-9])?$", "uppercase": True,
                       "allow_empty": True},
    "INSTALL_DATE":  {"pattern": r"^\d{2}/\d{2}/\d{4}$", "allow_empty": True},
    "STATUS_TRAIL":  {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_ATA_RE = re.compile(r"^\d{2}$")
# Column order as printed in the header's first line, used to derive
# per-page bin boundaries from that page's own header word positions.
_HEADER_LABELS = [
    ("ATA", "ATA"),
    ("SLOT_NAME", "Slot"),
    ("EQUIPMENT_ID", "Equipment"),
    ("SERIAL_NUMBER", "Serial"),
    ("PART_NUMBER", "Part"),
    ("LOCATION", "Location"),
    ("INSTALL_DATE", "Install"),
]
_TRAIL_ANCHOR = "TSN"  # first word of the report's 2nd header sub-line;
                       # its x0 becomes the right edge of INSTALL_DATE's bin.


def _group_lines(words: list[dict]) -> list[dict]:
    ws = sorted(words, key=lambda w: (w["top"], w["x0"]))
    lines: list[dict] = []
    for w in ws:
        if lines and abs(w["top"] - lines[-1]["top"]) <= 2.5:
            lines[-1]["words"].append(w)
        else:
            lines.append({"top": w["top"], "words": [w]})
    for line in lines:
        line["words"].sort(key=lambda w: w["x0"])
    return lines


def _find_header_bounds(lines: list[dict]) -> list[float] | None:
    """Locate this page's header line(s) and return the ordered list of bin
    boundaries (right edge of each column in `_HEADER_LABELS`, plus the
    right edge of INSTALL_DATE from the TSN sub-header), or None if this
    page has no recognizable header."""
    header_line = None
    for line in lines:
        if line["words"] and line["words"][0]["text"] == "ATA":
            header_line = line
            break
    if header_line is None:
        return None

    label_x0s: list[float] = []
    idx = 0
    words = header_line["words"]
    for _, label in _HEADER_LABELS:
        found = None
        for i in range(idx, len(words)):
            if words[i]["text"] == label:
                found = words[i]["x0"]
                idx = i + 1
                break
        if found is None:
            return None
        label_x0s.append(found)

    trail_x0 = None
    header_top = header_line["top"]
    for line in lines:
        if 0 < (line["top"] - header_top) <= 15 and line["words"] and \
                line["words"][0]["text"] == _TRAIL_ANCHOR:
            trail_x0 = line["words"][0]["x0"]
            break
    if trail_x0 is None:
        # Fall back to a fixed offset past Install Date if the TSN
        # sub-header line wasn't found on this page for some reason.
        trail_x0 = label_x0s[-1] + 45

    label_x0s.append(trail_x0)
    boundaries = [
        (label_x0s[i] + label_x0s[i + 1]) / 2 for i in range(len(label_x0s) - 1)
    ]
    return boundaries


def _bin_for(x0: float, boundaries: list[float]) -> int:
    for i, edge in enumerate(boundaries):
        if x0 < edge:
            return i
    return len(boundaries)


_FIELD_NAMES = ["ATA", "SLOT_NAME", "EQUIPMENT_ID", "SERIAL_NUMBER",
                "PART_NUMBER", "LOCATION", "INSTALL_DATE", "STATUS_TRAIL"]


def _is_data_line(line: dict, boundaries: list[float]) -> bool:
    # ATA is always the line's first (leftmost) token, so a plain regex
    # match on it is sufficient -- no need for the (unreliable, see below)
    # ATA/SLOT_NAME boundary here.
    first = line["words"][0]
    return bool(_ATA_RE.match(first["text"]))


def _row_from_line(line: dict, boundaries: list[float]) -> dict:
    """`boundaries[0]` (the ATA/SLOT_NAME midpoint) is deliberately unused
    for splitting: on every sample checked, the "Slot" header label sits
    well to the right of where real slot-name data actually starts (Cognos
    packs the 2-word "Slot Name" label somewhere inside its own wide
    column rather than at the column's left edge), so the header-midpoint
    heuristic that works cleanly for every other adjacent column pair puts
    the first description word into the ATA bin instead. ATA has a fixed,
    unambiguous grain (it's always line[0], a bare 2-digit token) so it's
    assigned directly instead, and the remaining words are classified
    against `boundaries[1:]` (SLOT_NAME onward)."""
    row = {col: "" for col in CANONICAL_COLUMNS}
    words = line["words"]
    row["ATA"] = words[0]["text"]
    rest_boundaries = boundaries[1:]
    rest_fields = _FIELD_NAMES[1:]
    for w in words[1:]:
        bin_idx = _bin_for(w["x0"], rest_boundaries)
        field = rest_fields[bin_idx]
        row[field] = (row[field] + " " + w["text"]).strip()
    return row


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    last_boundaries: list[float] | None = None
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
            if not words:
                continue
            lines = _group_lines(words)

            boundaries = _find_header_bounds(lines)
            if boundaries is None:
                boundaries = last_boundaries
            if boundaries is None:
                continue
            last_boundaries = boundaries

            for line in lines:
                if not line["words"]:
                    continue
                if not _is_data_line(line, boundaries):
                    continue
                row = _row_from_line(line, boundaries)
                row["_page"] = page_num
                records.append(row)
    return records
