"""A/C Installed Parts Print -- born-digital OCCM variant, real text layer,
confirmed via a direct pdfplumber pass over every page of one real sample
file (no OCR needed; extract() is synchronous).

Header block (repeats on every page)::

    A/C Installed Parts Print Print Date: <date> <time>
    Page: <n> of <n>
    Installed

Column header (repeats every page)::

    A/C P/N S/N Position Date Time ATA Last RO

Confirmed real-file quirk: the leading "A/C" token on every data row is a
constant tail/aircraft identifier -- the same single value on all 744 data
rows across all 29 pages of the known sample. Per this project's
header-parsing convention (parse once, stamp on every row), it is
promoted to header-level metadata (AIRCRAFT_TAIL_CODE) rather than kept as
a per-row column: it is locked in from the first data row found and then
stamped onto every record for the rest of the file. REPORT_DATE (the
"Print Date:" value on the first page) is parsed the same way.

Row shape -- confirmed exactly 2 physical lines per data row on every one
of the 744 real data rows in the known sample: line 1 carries all of
P/N, S/N, Position, Date, Time, ATA and (optionally) Last RO; line 2 is a
single free-text DESCRIPTION line immediately below it, e.g.::

    <pn> <sn> <position tokens...> <date> <time> <ata> [<last_ro>]
    <description text>

POSITION renders as a variable number of whitespace-separated tokens (from
one token up to several, e.g. a bare position code, or a position code
followed by a side/zone qualifier such as "LT"/"RT"/"CTR"/"FWD"/"AFT", or
multi-word combinations like "ENG 1 RT"), so it cannot be anchored by a
fixed token count. Instead each line-1 row is anchored from the right:
ATA renders as a 2-2-digit code where the final segment is 1 or 2 digits
(e.g. "<chapter>-<section>-<n>", confirmed both "...-00" and shorter
single-digit-final forms in the real sample -- so it is validated against
that shape rather than the generic 2-digit chapter pattern used elsewhere
in this package, same convention as occm_variants/iberia_listado.py and
occm_variants/aircraft_rotables_report.py). TIME (a bare "HH:MM" token)
immediately precedes ATA and is used as the anchor for locating it; an
optional numeric LAST_RO token (a report/work-order reference) may follow
ATA. Everything between S/N and TIME is the POSITION+DATE span; if its
last token matches a "M/D/YYYY"-shaped date, that token is DATE and
everything before it is POSITION (rejoined with single spaces).

Confirmed real-file quirk, soft-validated rather than guessed: on 65 of
the 744 real data rows, the POSITION+DATE span's trailing tokens are
visibly character-interleaved in the extracted text -- e.g. a position
qualifier and the date digits appear woven together into unparseable
tokens (confirmed by direct inspection of the real sample's word-level
pdfplumber output; the same corruption pattern was also confirmed, via
`extract_words`, to originate in the source PDF's own text stream, not in
this module's line-grouping). On these rows the trailing token does not
cleanly match the date pattern, so per this project's "never guess a
wrong split" convention, POSITION and INSTALL_DATE are left empty rather
than guessed, and the raw, unmodified span is instead preserved verbatim
in STATUS_TRAIL (prefixed "POSITION/DATE (unparseable): ") so no data is
silently dropped. TIME, ATA and LAST_RO are unaffected on these rows (all
three anchors were confirmed to still parse cleanly on every one of the
65 rows) and are extracted normally.
"""
from __future__ import annotations
import re

import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "A/C Installed Parts Print"

SIGNATURES = [
    "A/C Installed Parts Print",
    "A/C P/N S/N Position Date Time ATA Last RO",
]

CANONICAL_COLUMNS = [
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "POSITION",
    "INSTALL_DATE",
    "INSTALL_TIME",
    "ATA",
    "LAST_RO",
    "DESCRIPTION",
    "STATUS_TRAIL",
    # Header metadata -- parsed once, stamped onto every row.
    "AIRCRAFT_TAIL_CODE",
    "REPORT_DATE",
]

_OVERRIDES = {
    # This report's ATA renders as "<chapter>-<section>-<n>" (n is 1 or 2
    # digits) -- not a bare 2-digit chapter -- same convention as
    # iberia_listado.py / aircraft_rotables_report.py.
    "ATA": {"pattern": r"^\d{2}-\d{2}-\d{1,2}$", "int_range": None},
    "POSITION": {"pattern": r"^[A-Z0-9][A-Z0-9 .()/\-]*$", "allow_empty": True},
    "INSTALL_DATE": {"pattern": r"^\d{1,2}/\d{1,2}/\d{4}$", "allow_empty": True},
    "INSTALL_TIME": {"pattern": r"^\d{2}:\d{2}$", "allow_empty": True},
    "LAST_RO": {"pattern": r"^\d+$", "allow_empty": True},
    "STATUS_TRAIL": {"allow_empty": True},
    "AIRCRAFT_TAIL_CODE": {"pattern": r"^[A-Z0-9\-]+$", "uppercase": True, "allow_empty": True},
    "REPORT_DATE": {"pattern": r"^\d{1,2}/\d{1,2}/\d{4}$", "allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_DATE_RE = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")
_TIME_RE = re.compile(r"^\d{2}:\d{2}$")
_ATA_RE = re.compile(r"^\d{2}-\d{2}-\d{1,2}$")
_LAST_RO_RE = re.compile(r"^\d+$")

_REPORT_DATE_RE = re.compile(r"Print Date:\s*(\d{1,2}/\d{1,2}/\d{4})")

_HEADER_LINE_PREFIXES = (
    "A/C Installed Parts Print",
    "Page:",
    "Installed",
    "A/C P/N S/N Position",
)


def _group_lines(words: list[dict]) -> list[list[dict]]:
    """Cluster words into physical lines by y-position (tolerant of
    sub-point 'top' jitter between words nominally on the same visual
    line). Same technique as installed_parts_list.py."""
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
    return [line["words"] for line in lines]


def _line_text(tokens: list[str]) -> str:
    return " ".join(tokens)


def _is_header_or_footer(text: str) -> bool:
    return any(text.startswith(pfx) for pfx in _HEADER_LINE_PREFIXES)


def _is_data_row(tokens: list[str]) -> bool:
    """Anchor: at least AC + PN + SN + a TIME token + an ATA token."""
    return (
        len(tokens) >= 6
        and any(_TIME_RE.match(t) for t in tokens)
        and any(_ATA_RE.match(t) for t in tokens)
    )


def _parse_row(tokens: list[str]) -> dict | None:
    if not _is_data_row(tokens):
        return None
    # Locate ATA (last ATA-shaped token) and the TIME token immediately
    # before it.
    ata_idx = None
    for i in range(len(tokens) - 1, -1, -1):
        if _ATA_RE.match(tokens[i]):
            ata_idx = i
            break
    if ata_idx is None or ata_idx < 1 or not _TIME_RE.match(tokens[ata_idx - 1]):
        return None
    time_idx = ata_idx - 1

    ac = tokens[0]
    pn = tokens[1]
    sn = tokens[2] if len(tokens) > 2 else ""
    middle = tokens[3:time_idx]
    time_val = tokens[time_idx]
    ata = tokens[ata_idx]
    last_ro = ""
    if ata_idx + 1 < len(tokens) and _LAST_RO_RE.match(tokens[ata_idx + 1]):
        last_ro = tokens[ata_idx + 1]

    position = ""
    install_date = ""
    status_trail = ""
    if middle and _DATE_RE.match(middle[-1]):
        install_date = middle[-1]
        position = " ".join(middle[:-1])
    elif middle:
        # Confirmed real-file quirk: position/date span is character-
        # interleaved and unparseable on this row (see module docstring).
        # Never guess a split -- fold the raw span into STATUS_TRAIL.
        status_trail = "POSITION/DATE (unparseable): " + " ".join(middle)

    return {
        "PART_NUMBER": pn,
        "SERIAL_NUMBER": sn,
        "POSITION": position,
        "INSTALL_DATE": install_date,
        "INSTALL_TIME": time_val,
        "ATA": ata,
        "LAST_RO": last_ro,
        "STATUS_TRAIL": status_trail,
        "_ac": ac,
    }


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    header_meta = {"AIRCRAFT_TAIL_CODE": "", "REPORT_DATE": ""}
    tail_locked = False
    date_locked = False

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            if not date_locked:
                text = page.extract_text() or ""
                m = _REPORT_DATE_RE.search(text)
                if m:
                    header_meta["REPORT_DATE"] = m.group(1)
                    date_locked = True

            words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
            if not words:
                continue

            lines = _group_lines(words)
            pending_row: dict | None = None
            for line_words in lines:
                tokens = [w["text"] for w in line_words]
                text = _line_text(tokens)
                if _is_header_or_footer(text):
                    continue
                row = _parse_row(tokens)
                if row is not None:
                    if pending_row is not None:
                        # Previous data row had no following description
                        # line before the next data row started -- flush
                        # it as-is (DESCRIPTION left empty rather than
                        # guessed from unrelated text).
                        records.append(pending_row)
                    if not tail_locked and row["_ac"]:
                        header_meta["AIRCRAFT_TAIL_CODE"] = row["_ac"]
                        tail_locked = True
                    row.pop("_ac", None)
                    row["DESCRIPTION"] = ""
                    row.update(header_meta)
                    row["_page"] = page_num
                    pending_row = row
                else:
                    if pending_row is not None:
                        pending_row["DESCRIPTION"] = text
                        records.append(pending_row)
                        pending_row = None
                    # Else: stray unanchored line before any data row on
                    # this page -- dropped rather than guessed onto a row.
            if pending_row is not None:
                records.append(pending_row)
                pending_row = None
    return records
