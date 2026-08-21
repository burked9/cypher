"""OASES variant — OCCMs produced by Communications Software's OASES MIS.

OASES is a maintenance information system used by MROs and operators
worldwide (including FL Technics). Reports look quite different from AMOS:
each logical component spans **three lines** of extracted text:

    Line 1 (data):     ATA POS ZONE PN DESC...DESC SN LAST_BATCH_MOVEMENT_DATE
                       Days <since_new> <since_fit> <since_overhaul> <since_repair>
    Line 2 (hours):    Hours <since_new> <since_fit> <since_overhaul> <since_repair>
    Line 3 (landings): Landings <since_new> <since_fit> <since_overhaul> <since_repair>

The numeric matrix is 3 metrics × 4 categories = 12 values per component.
Each value may be `?` (missing) — we preserve those as empty strings so an
analyst can distinguish "missing in source" from "zero".

Strategy: walk the lines as a state machine. A "data" line is detected by a
leading 8-digit ATA token + a date matching `^\\d{1,2}[A-Za-z]{3}\\d{4}$`
near the end. The Hours and Landings lines are matched literally by their
leading keyword.

Variants of the OASES report exist (e.g. `(OASES Option : TR47)`); the
signatures below catch the FL Technics-rebranded "OASES Live system" header
and the bare "OASES Option" variant.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "OASES"
SIGNATURES = [
    # Explicit product/vendor names
    "FL Technics OASES",
    "OASES Live system",
    "OASES Option",
    # The "Aircraft Build" report header — common across rebrands; many
    # operator-customised OASES exports drop the "OASES" string but keep
    # this header verbatim.
    "Aircraft Build Report Date",
    "Aircraft Build Aircraft Reg",
    # Column-header signatures unique to OASES output:
    "Position Zone Part Number Description",
    "Last Batch Movement",
    # Time-matrix header — caught only by OASES reports
    "Since New Since Fit Since Overhaul",
]

# 8 identity columns + 12-value time matrix
CANONICAL_COLUMNS = [
    "ATA",
    "POSITION",
    "ZONE",
    "PART_NUMBER",
    "DESCRIPTION",
    "SERIAL_NUMBER",
    "LAST_BATCH_MOVEMENT",
    # Days
    "DAYS_SINCE_NEW", "DAYS_SINCE_FIT", "DAYS_SINCE_OVERHAUL", "DAYS_SINCE_REPAIR",
    # Hours
    "HOURS_SINCE_NEW", "HOURS_SINCE_FIT", "HOURS_SINCE_OVERHAUL", "HOURS_SINCE_REPAIR",
    # Landings
    "LANDINGS_SINCE_NEW", "LANDINGS_SINCE_FIT", "LANDINGS_SINCE_OVERHAUL", "LANDINGS_SINCE_REPAIR",
]

_OVERRIDES = {
    # OASES uses extended ATA codes (chapter + sub-codes), e.g. 21214101.
    # Drop the global 2-digit / 20-83 range rules — they don't apply here.
    "ATA":      {"pattern": r"^\d{6,8}$", "int_range": None},
    # POSITION on Embraer can be multi-token (`CTL II`, `SPDA/1`, `LH-SPL`)
    # or a single short letter on some operators. Allow space/slash/dot/dash.
    "POSITION": {"pattern": r"^[A-Z0-9][A-Z0-9./\- ]{0,15}$", "uppercase": True,
                 "allow_empty": True},
    # ZONE can be a decimal code (`1.47` on Airbus) or a text zone name
    # on Embraer (`WING`, `STUB`, `FWD`, `PYLON`, `I`/`II`/`III`, `L/H`).
    "ZONE":     {"pattern": r"^(?:\d+(?:\.\d+)?|[A-Z][A-Z0-9/\-]*)$",
                 "uppercase": True},
    "LAST_BATCH_MOVEMENT": {"pattern": r"^\d{1,2}[A-Za-z]{3}\d{4}$"},
    # All twelve "since" cells allow either a numeric value (incl. HH:MM
    # for hours), a `?`, or an empty string — no hard pattern.
}
RULES = merged_rules(_OVERRIDES)


_DATE_RE = re.compile(r"^\d{1,2}[A-Za-z]{3}\d{4}$")
_ATA8_RE = re.compile(r"^\d{6,8}$")
# Used to disambiguate Embraer multi-token POSITION rows — see _parse_line.
_ZONE_DECIMAL_RE = re.compile(r"^\d+(?:\.\d+)?$")


def _parse_data_line(line: str, page_num: int) -> dict | None:
    """Match the first of the three lines (the one with ATA + Date + Days + 4 values).
    Returns a partially-populated record (Hours/Landings filled in later)."""
    tokens = line.split()
    if len(tokens) < 11:
        return None
    if not _ATA8_RE.match(tokens[0]):
        return None

    # Walk from the end. Last token is the rightmost "since" value.
    # Pattern from end: <4 values> "Days" <date> <SN> <PN+desc...>
    # i.e. tokens[-5] == "Days", tokens[-6] == date, tokens[-7] == SN
    if tokens[-5] != "Days":
        return None
    if not _DATE_RE.match(tokens[-6]):
        return None

    days_vals = tokens[-4:]            # 4 values
    last_batch = tokens[-6]
    sn = tokens[-7]
    # Remaining: ATA, POS, ZONE, PN, DESC..., (before SN)
    head = tokens[:-7]
    if len(head) < 5:
        return None
    ata = head[0]
    # POSITION is normally a single token (e.g. `SPDA2`, `LEFT`) with ZONE at
    # head[2]. On Embraer OASES POSITION can be two tokens (`CTL II`,
    # `LH-SPL`), shifting everything one right. We disambiguate by checking
    # whether head[2] looks like a zone (decimal `1.47`); if not but head[3]
    # does, POSITION absorbed an extra token.
    if (len(head) >= 5
            and not _ZONE_DECIMAL_RE.match(head[2])
            and _ZONE_DECIMAL_RE.match(head[3])):
        pos = " ".join(head[1:3])
        zone = head[3]
        pn = head[4]
        desc = " ".join(head[5:])
    else:
        pos = head[1]
        zone = head[2]
        pn = head[3]
        desc = " ".join(head[4:])
    if not desc:
        return None

    rec = {c: "" for c in CANONICAL_COLUMNS}
    rec["ATA"] = ata
    rec["POSITION"] = pos
    rec["ZONE"] = zone
    rec["PART_NUMBER"] = pn
    rec["DESCRIPTION"] = desc
    rec["SERIAL_NUMBER"] = sn
    rec["LAST_BATCH_MOVEMENT"] = last_batch
    rec["DAYS_SINCE_NEW"]      = days_vals[0]
    rec["DAYS_SINCE_FIT"]      = days_vals[1]
    rec["DAYS_SINCE_OVERHAUL"] = days_vals[2]
    rec["DAYS_SINCE_REPAIR"]   = days_vals[3]
    rec["_page"] = page_num
    return rec


def _try_attach_hours_landings(rec: dict, line: str, keyword: str, cols: tuple[str, str, str, str]) -> bool:
    """If `line` begins with `keyword`, attach its 4 trailing values to `rec`.
    Returns True if attached, False otherwise (signal that the current record
    is complete or this line belongs to a different record)."""
    tokens = line.split()
    if len(tokens) < 5 or tokens[0] != keyword:
        return False
    vals = tokens[-4:]
    for c, v in zip(cols, vals):
        rec[c] = v
    return True


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if len(text) < 100:
                continue

            pending: dict | None = None   # partial record awaiting Hours/Landings
            for raw in text.splitlines():
                line = raw.strip()
                if not line:
                    continue

                # New data row?
                rec = _parse_data_line(line, page_num)
                if rec is not None:
                    if pending is not None:
                        records.append(pending)
                    pending = rec
                    continue

                # Try to attach as Hours continuation
                if pending is not None and _try_attach_hours_landings(
                    pending, line, "Hours",
                    ("HOURS_SINCE_NEW", "HOURS_SINCE_FIT",
                     "HOURS_SINCE_OVERHAUL", "HOURS_SINCE_REPAIR")
                ):
                    continue

                # Try to attach as Landings continuation
                if pending is not None and _try_attach_hours_landings(
                    pending, line, "Landings",
                    ("LANDINGS_SINCE_NEW", "LANDINGS_SINCE_FIT",
                     "LANDINGS_SINCE_OVERHAUL", "LANDINGS_SINCE_REPAIR")
                ):
                    # Landings is the last line; commit the record
                    records.append(pending)
                    pending = None
                    continue

                # Unknown line — discard any incomplete pending record
                # (heuristic: don't accumulate stale state across noise)
            # Page boundary — flush trailing pending if it has at least the data line
            if pending is not None:
                records.append(pending)
    return records
