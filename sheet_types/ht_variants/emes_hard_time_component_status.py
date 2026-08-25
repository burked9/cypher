"""e.MES "Hard Time Component Status" report (Korean HL-registered fleet).

Header (a known file in the corpus)::

    Hard Time Component Status
    A/C # : <tail no.> MSN : <MSN> A/C TSN : 70866.50 A/C CSN : 29078 Date : 20171116
    T/C # Task HT P/N S/N POS Description Interval Installation Information Due Information Remaining
    Code Class
    FH FC Days SER Date INST Date A/C TSN A/C Due Date A/C TSN A/C FH CY Days
    CSN CSN

Footer on every page: "<n> of <N> from e.MES" -- names the generating
system and is the signature anchor, since the report TITLE alone ("Hard
Time Component Status") is shared verbatim by two unrelated formats already
in this package (aercap_hard_time_component_status.py, and the title
fragment quoted in hard_time_component_status_mpd_task.py's own docstring)
-- neither matches this file's column layout (T/C # ... POS Description
Interval Installation Information Due Information Remaining), confirmed by
direct comparison, so this is a distinct variant despite the shared title.

Row example::

    21-100-00-01-03 RST LRU 182820-3 21937 LH PRI HEAT EXCHANGER 2000 2016-09-05 2016-10-10 66409.52 27296 29296 218

Anchor: T/C # (task code), shape `NN-NNN-NN[-NN]` or `NN-ESR-NN` (ATA is
always the leading 2 digits). TASK_TYPE and HT_CLASS follow positionally
(closed vocab in this corpus -- RST/DIS/OPC/FNC/GVI/DVI/RPL and LRU/SRU/A/C
-- but read positionally rather than validated against that vocab, since
the position is unambiguous). PART_NUMBER/SERIAL_NUMBER are positional too.

POSITION and DESCRIPTION are not split: this report interleaves them with
no reliable delimiter ("LH PRI HEAT EXCHANGER" is POS="LH PRI" + a
description, "MAIN 48 AMP MAIN BATTERY" is POS="MAIN" + a description that
itself starts with a number) -- same call htll_status.py makes for its own
DESC/FIN ambiguity. The combined DESCRIPTION is recovered reliably by
scanning backward from the row's first ISO date (SER Date) and
re-absorbing any trailing integer/comma-number/"-" tokens that belong to
the ragged INTERVAL columns, stopping at the first token that isn't
numeric-shaped -- e.g. for "...MAIN 48 AMP MAIN BATTERY 2000 2017-07-13..."
the "48" survives inside DESCRIPTION because "BATTERY", not "48", is the
token adjacent to the numeric run.

The remaining INTERVAL(FH,FC,Days)/SER_DATE/INST_DATE/A-C-TSN/A-C-CSN/
[DUE_DATE]/[DUE A/C TSN or CSN]/REMAINING tail is column-ragged -- blank
cells are dropped rather than represented, exactly the trailing-columns
tradeoff every sibling HT parser makes -- so it is kept as one
STATUS_TRAIL string rather than mis-sliced into named cells.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.ht_variants._base import merged_rules

NAME = "e.MES Hard Time Component Status"
SIGNATURES = [
    "FROM E.MES",
    "T/C # TASK HT",
]
CANONICAL_COLUMNS = [
    "ATA",
    "TASK_CODE",
    "TASK_TYPE",
    "HT_CLASS",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
    "STATUS_TRAIL",
]
_OVERRIDES = {
    "TASK_CODE": {"pattern": r"^\d{2}(?:-(?:\d{1,3}|ESR))+$"},
    "TASK_TYPE": {"pattern": r"^[A-Z]{2,4}$"},
    "HT_CLASS": {"pattern": r"^(?:LRU|SRU|A/C)$"},
    "STATUS_TRAIL": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_TASK_CODE_RE = re.compile(r"^\d{2}(?:-(?:\d{1,3}|ESR))+$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_NUMERICISH_RE = re.compile(r"^-$|^\d[\d,]*(?:\.\d+)?$")


def _split_desc_trail(tokens: list[str]) -> tuple[str, str]:
    date_idx = next((i for i, t in enumerate(tokens) if _DATE_RE.match(t)), None)
    if date_idx is None:
        return " ".join(tokens), ""
    end = date_idx
    while end > 0 and _NUMERICISH_RE.match(tokens[end - 1]):
        end -= 1
    return " ".join(tokens[:end]), " ".join(tokens[end:])


def _parse_line(line: str, page_num: int) -> dict | None:
    toks = line.split()
    if len(toks) < 6 or not _TASK_CODE_RE.match(toks[0]):
        return None
    ata = toks[0][:2]
    if not (20 <= int(ata) <= 83):
        return None
    description, status_trail = _split_desc_trail(toks[5:])
    if not description:
        return None
    return {
        "ATA": ata,
        "TASK_CODE": toks[0],
        "TASK_TYPE": toks[1],
        "HT_CLASS": toks[2],
        "PART_NUMBER": toks[3],
        "SERIAL_NUMBER": toks[4],
        "DESCRIPTION": description,
        "STATUS_TRAIL": status_trail,
        "_page": page_num,
    }


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            for raw in text.splitlines():
                rec = _parse_line(raw.strip(), page_num)
                if rec is not None:
                    records.append(rec)
    return records
