"""KEEL-style Hard Time list — "HARD TIME LIST AS AT <date>" header, MPD-coded tasks.

Header (a known A300-600 file in the corpus)::

    Hours since 02-JUL-2021:0 DELIVERY DATE:07-Jul-21
    <tail no.> <MSN> HARD TIME LIST AS AT 5-Jul-2021 TAT:65,463:32 TAC:27,189 ...
    ATA MPN DESCRIPTION MPN MSN POSN INST DTE MPD TASK MPD DESCRIP COMPL DTE HRS CYS DYS HRS CYS DYS HRS CYS DYS DUE DTE

Two row shapes share the page, keyed off the MPD TASK column
(`\\d{2}-\\d{3}-\\d{2}`, e.g. `21-070-00`) — every data row carries one:

  * **Component row** — leads with the ATA chapter, carries PN/SN/POSN/
    install date, then its first MPD task::

        21 POSITIVE PRESSURE RELIEF VALVES 720737-6 9908067 INBD 2000-05-10 21-070-00 Func Chk 2020-06-02 17000 815 16185 2025-12-12

  * **Task-only row** — a component with more than one scheduled task
    prints the later ones on their own line, with no ATA/PN/SN/POSN
    repeated::

        23-060-00 Ops Ck of ULB 2019-07-01 2555 735 1820 2026-07-01

    ATA/PN/SN/POSN/INSTALL_DATE are forward-filled from the last component
    row (same approach as stars_trax.py). Sub-part lines nested under a
    component (a life-raft's "Cylinder"/"HYD" rows, the "IST NLA LIMIT"
    hose-assembly row) have neither shape at their head, but still carry
    their own MPD TASK, so they parse via the task-only path and inherit
    the parent's identity fields — their own PN/SN is dropped.

Anchor: the MPD TASK token. PN is the first head token (between ATA and
MPD TASK) with a digit and length >= 3 — reliable here because every
DESCRIPTION word in the corpus is pure alphabetic except "O2" (length 2,
below the threshold, so it's never mistaken for the PN). SN is simply the
token after PN; POSITION is whatever sits between SN and the first ISO
install date, when one is present.

The 3-line wrap layout (long description printed on the lines above/below
the data line, e.g. "Left air conditioning pack compressor ... switch"
wrapping around "21 572756-1 LH 21-110-01 Func Chk ...") only ever
recovers the middle line — the flanking lines carry no MPD TASK anchor of
their own and are silently dropped, the same tradeoff mm510.py documents
for its own wrap-task layout.

The three HRS/CYS/DYS triplets (actual / limit / remaining) shift left
whenever a cell is blank, so trailing numerics are kept as one unparsed
STATUS_TRAIL string rather than mis-sliced into named columns — the same
call oases_lifed_components.py and tap.py make for their own trailing
columns. DUE_DATE is still pulled out on its own because it reliably sits
as the last token on the line when present.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.ht_variants._base import merged_rules

NAME = "MPD Hard Time List"
SIGNATURES = [
    "HARD TIME LIST AS AT",
    "MPD TASK MPD DESCRIP",
]
CANONICAL_COLUMNS = [
    "ATA",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "POSITION",
    "INSTALL_DATE",
    "TASK_NUMBER",
    "TASK_DESCRIPTION",
    "COMPL_DATE",
    "DUE_DATE",
    "STATUS_TRAIL",
]
_OVERRIDES = {
    "DESCRIPTION":      {"allow_empty": True},   # wrap-layout mid-line carries no description text
    "SERIAL_NUMBER":    {"allow_empty": True},
    "POSITION":         {"allow_empty": True},
    "INSTALL_DATE":     {"pattern": r"^\d{4}-\d{2}-\d{2}$", "allow_empty": True},
    "TASK_NUMBER":      {"pattern": r"^\d{2}-\d{3}-\d{2}$"},
    "TASK_DESCRIPTION": {"allow_empty": True},
    "COMPL_DATE":       {"pattern": r"^\d{4}-\d{2}-\d{2}$", "allow_empty": True},
    "DUE_DATE":         {"pattern": r"^\d{4}-\d{2}-\d{2}$", "allow_empty": True},
    "STATUS_TRAIL":     {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_TASK_RE = re.compile(r"^\d{2}-\d{3}-\d{2}$")
_ATA_RE = re.compile(r"^\d{2}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_NUM_RE = re.compile(r"^\d+$")


def _codeish(tok: str) -> bool:
    return len(tok) >= 3 and any(c.isdigit() for c in tok)


def _parse_row(toks: list[str], cur: dict) -> dict | None:
    task_idx = next((i for i, t in enumerate(toks) if _TASK_RE.match(t)), None)
    if task_idx is None:
        return None

    if task_idx > 0 and _ATA_RE.match(toks[0]) and 20 <= int(toks[0]) <= 83:
        head = toks[1:task_idx]
        mpn_idx = next((i for i, t in enumerate(head) if _codeish(t)), None)
        if mpn_idx is None:
            return None    # leave `cur` untouched rather than guess the wrong component
        rest = head[mpn_idx + 2:]
        date_i = next((i for i, t in enumerate(rest) if _DATE_RE.match(t)), None)
        cur["ATA"] = toks[0]
        cur["DESCRIPTION"] = " ".join(head[:mpn_idx])
        cur["PART_NUMBER"] = head[mpn_idx]
        cur["SERIAL_NUMBER"] = head[mpn_idx + 1] if mpn_idx + 1 < len(head) else ""
        cur["POSITION"] = " ".join(rest[:date_i] if date_i is not None else rest)
        cur["INSTALL_DATE"] = rest[date_i] if date_i is not None else ""

    if not cur["PART_NUMBER"]:
        return None    # task-only row seen before any component row established identity

    tail = toks[task_idx + 1:]
    split_i = next((i for i, t in enumerate(tail) if _DATE_RE.match(t) or _NUM_RE.match(t)), None)
    if split_i is None:
        task_descr, compl_date, remainder = " ".join(tail), "", []
    elif _DATE_RE.match(tail[split_i]):
        task_descr, compl_date, remainder = " ".join(tail[:split_i]), tail[split_i], tail[split_i + 1:]
    else:
        task_descr, compl_date, remainder = " ".join(tail[:split_i]), "", tail[split_i:]
    due_date = ""
    if remainder and _DATE_RE.match(remainder[-1]):
        due_date, remainder = remainder[-1], remainder[:-1]

    return {
        "ATA": cur["ATA"],
        "DESCRIPTION": cur["DESCRIPTION"],
        "PART_NUMBER": cur["PART_NUMBER"],
        "SERIAL_NUMBER": cur["SERIAL_NUMBER"],
        "POSITION": cur["POSITION"],
        "INSTALL_DATE": cur["INSTALL_DATE"],
        "TASK_NUMBER": toks[task_idx],
        "TASK_DESCRIPTION": task_descr,
        "COMPL_DATE": compl_date,
        "DUE_DATE": due_date,
        "STATUS_TRAIL": " ".join(remainder),
    }


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    cur = {"ATA": "", "DESCRIPTION": "", "PART_NUMBER": "", "SERIAL_NUMBER": "",
           "POSITION": "", "INSTALL_DATE": ""}
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            for line in text.splitlines():
                toks = line.split()
                if not toks:
                    continue
                rec = _parse_row(toks, cur)
                if rec is not None:
                    rec["_page"] = page_num
                    records.append(rec)
    return records
