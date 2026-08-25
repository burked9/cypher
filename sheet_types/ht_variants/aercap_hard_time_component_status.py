"""AerCap "HARD TIME COMPONENT STATUS" general component list
(a known B767-3Q8ER file in the corpus, AerCap lessor letterhead).

Header (repeated per page)::

    AerCap Ireland Limited, 4450 Atlantic Avenue
    Westpark, Shannon, Co. Clare, Republic of Ireland
    A/C TYPE : B767-3Q8ER
    A/C REG.: <tail no.> HARD TIME COMPONENT STATUS
    A/C serial : <MSN>
    A/C TTSN : 75,757 DATE : 10-May-19
    A/C TCSN : 12,180
    INTERVAL LAST DONE COMP.TIMELINE LAST DONE A/C TIMELINE (@INSTL) NEXT DUE REMAINED
    ATA MP ITEM PARTS DESCRPTION POSITION, ZONE PART NUMBER SERIAL NUMBER TAG No. FH CY DAYS FH CY DATE FH CY DATE FH CY DATE FH CY DAYS REMARKS

Row example::

    3535-011-01(AMP) CYLINDER, OXYGEN, PORT. 11.0 CABIN,200,65 CA 9700C1ABF23A ST78283 WO#299443 1825 UNK UNK 1-Jul-14 61974 10306 1-Dec-14 30-Jun-19 51 WORTH TO GO

File quirk (the reason this file first looked garbled): the PDF is 10
pages, but only 5 pages of real content -- pages 1-5 are a noisy overlaid
re-render of the SAME 5 pages that repeat cleanly at pages 6-10 ("Page 1 of
5" through "Page 5 of 5" appear on both halves; confirmed by comparing
first-row text page-by-page). The noisy half isn't simple OCR: on page 1
alone the characters split into two font populations sitting at nearly
identical (x0, top) -- 8574 chars in Helvetica 4pt, 6827 in Times-Bold
3.5pt -- so pdfplumber's default word-order-by-x0 reconstruction
interleaves both copies character-by-character (e.g. the letterhead reads
"AAeetrCCjapp tIrreeldlnaOn d..." instead of "AerCap Ireland..."). Other
noisy pages pair Helvetica with Courier or Times-Roman instead, so there is
no single reliable font filter across the whole noisy half -- rather than
build a fragile per-page font-population splitter, this parser leans on
the row anchor below, which the noisy half's interleaved text does not
reproduce cleanly enough to match: real extraction against the source file
pulls records only from the clean second half.

Anchor: ATA and MP ITEM (task code) print back-to-back with no space
("3535-011-01(AMP)" = ATA "35" + task "35-011-01(AMP)"; "5252-075-00" = ATA
"52" + task "52-075-00") -- reconstructed via a same-prefix backreference
rather than assumed fixed-width, since the task code's own digit groups can
carry a trailing "(AMP)" suffix. A handful of Airworthiness-Directive rows
use "AD <AD-number>" as the task code instead, with no ATA repeated (e.g.
"28AD 2009-23-04" = ATA "28" + task "AD 2009-23-04") -- matched as a second
alternative.

DESCRIPTION/POSITION/ZONE/PART_NUMBER/SERIAL_NUMBER/TAG No. are NOT split
into separate columns. Sibling parsers (Georgian, mpd_hard_time_list,
hard_time_component_status_mpd_task) fold only their *trailing* FH/CY/DATE
run into one STATUS_TRAIL because that run alone is column-ragged; here the
raggedness starts immediately after the task code -- PART_NUMBER shapes
alone range over "9700C1ABF23A", "MC10-08-109", "2-7680-2", "255T2110-4"
and "PBS7-3" in this one file, POSITION is comma-joined with ZONE on some
rows ("CABIN,200,65 CA") and bare on others ("COCKPIT"), and an unlabeled
TAG-No.-like code sits after SERIAL_NUMBER on many rows ("WO#299443") --
nothing in the extracted text reliably marks any of those boundaries.
Rather than guess a split that would look confidently precise and
sometimes be silently wrong in an airworthiness record, everything from
right after the task code to end of line is kept as one STATUS_TRAIL
string. ATA + TASK_CODE are still enough to group/search the sheet by
chapter and task.

Some components print follow-on maintenance actions as their own line with
no ATA/task-code prefix at all -- e.g. an "...INSP./WT..." row is followed
by bare "PORTABLE HALON FIREX, OVH 2190 1-Mar-15 27-Feb-21 659 WORTH TO GO"
/ "...PROOF TEST..." lines. These inherit ATA/TASK_CODE from the last
anchored row, the same forward-fill call mpd_hard_time_list.py makes for
its own task-only rows. They're recognised by carrying a real date or
ending in the REMARKS vocabulary (WORTH TO GO / OVERDUE) while not being a
known non-data header/footer line -- REMARKS itself is blank often enough
(no trailing "WORTH TO GO") that it can't be required on every row.

`normalize_dashes` runs on extracted text before line-splitting: this file
prints some STATUS_TRAIL tokens with U+2010 HYPHEN instead of ASCII "-"
(e.g. "23‐406"), the same class of PDF-writer quirk occm/llp variants
already normalise for.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.ht_variants._base import merged_rules
from shared.cleanup import normalize_dashes

NAME = "AerCap Hard Time Component Status"
SIGNATURES = [
    "COMP.TIMELINE",
    "A/C TIMELINE (@INSTL)",
]
CANONICAL_COLUMNS = [
    "ATA",
    "TASK_CODE",
    "STATUS_TRAIL",
]
_OVERRIDES = {
    "TASK_CODE": {
        "pattern": r"^\d{2}-\d{1,3}-\d{2}(?:\([A-Za-z]+\))?$|^AD \d{4}-\d{2}-\d{2}$",
    },
    "STATUS_TRAIL": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_MAIN_RE = re.compile(
    r"^(\d{2})(\d{2}-\d{1,3}-\d{2}(?:\([A-Za-z]+\))?|AD \d{4}-\d{2}-\d{2})\s+(.*)$"
)
_DATE_RE = re.compile(r"\d{1,2}-[A-Za-z]{3}-\d{2,4}")
# Known non-data lines (letterhead/header/footer/annotation block). Checked
# before the date/remarks heuristic below so those lines -- several of
# which legitimately contain a date, e.g. "A/C TTSN : ... DATE : 10-May-19"
# -- are never mistaken for a follow-on task line.
_SKIP_PREFIXES = (
    "AerCap", "Westpark", "A/C ", "INTERVAL", "ATA MP ITEM",
    "All rights reserved", "ANNOTATION", "Name:", "Signature:",
)


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    cur_ata, cur_task = "", ""
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = normalize_dashes(page.extract_text() or "")
            for raw in text.splitlines():
                line = raw.strip()
                if not line or line.startswith(_SKIP_PREFIXES):
                    continue
                m = _MAIN_RE.match(line)
                if m:
                    if 20 <= int(m.group(1)) <= 83:
                        cur_ata, cur_task, trail = m.group(1), m.group(2), m.group(3)
                        records.append({
                            "ATA": cur_ata, "TASK_CODE": cur_task, "STATUS_TRAIL": trail,
                            "_page": page_num,
                        })
                    continue    # anchor-shaped line either way -- never also a continuation row
                if not cur_task:
                    continue    # no component identity established yet on this page run
                if _DATE_RE.search(line) or line.endswith(("WORTH TO GO", "OVERDUE")):
                    records.append({
                        "ATA": cur_ata, "TASK_CODE": cur_task, "STATUS_TRAIL": line,
                        "_page": page_num,
                    })
    return records
