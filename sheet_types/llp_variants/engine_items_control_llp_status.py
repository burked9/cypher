""""Items Control for Engine" LLP status report -- a per-engine list of
life-limited parts headed by a title line resembling::

    <operator abbrev> ITEMS CONTROL FOR ENGINE <engine model> S/N:<esn> Page No. 1
    <garbled aero-engine header line> ETSN= <n>, ECSN <n>, INST: COM POS E <date>
    <garbled property/systems line> PROPERTY: <operator> PROCESS DATE <date>
    ENGINE LIFE LIMITED PARTS
    PART NAME PART NUMBER SERIAL T.S.N. C.S.N. CYCLES CYCLES
    NUMBER LIMIT REMAIN

followed by one row per LLP, e.g. (values genericized)::

    CONE SEG CPR INLET 51A046 CBDUAT6702 2396 548 30000 29452

Confirmed on a single real file so far (singleton cluster). The text layer
is real (pdfplumber extracts real characters, not a blank/raster page) but
carries systematic character-substitution corruption -- consistent with an
OCR pass somewhere upstream of this particular PDF's own creation, a
pattern already seen elsewhere in this project. Confusable characters seen
in the sample include 0/O/^/M, S/5, and scrambled letters inside the
description and header text; PART_NUMBER and SERIAL_NUMBER are comparatively
clean.

Row grain: one row per life-limited part. Columns, left to right: PART NAME
(free-text description), PART NUMBER, SERIAL NUMBER, then four trailing
numeric fields -- T.S.N., C.S.N., CYCLES LIMIT, CYCLES REMAIN.

Row detection is purely positional/structural, not regex-on-shape, because
individual characters inside any given token can be corrupted in ways that
break a strict "letters then digits" pattern (e.g. a serial number's final
digit misread as a letter). Every real data row has exactly this shape:
description words, then PART_NUMBER, then SERIAL_NUMBER, then 4 trailing
tokens -- so a line qualifies as a data row when:
  - it has at least 7 whitespace-split tokens,
  - the token 5 places from the end (the serial-number slot) contains both
    a letter and a digit and is a plausible SN length (6-13 chars), and
  - the token 6 places from the end (the part-number slot) contains a digit.
This was checked directly against the sample file: it accepts every one of
the ~40 real data rows and rejects every title/metadata/column-header line,
without needing to hardcode any operator name or other document-specific
string as a skip-line marker.

TSN and CSN are effectively constant across the sample file's rows (a
report-date total-time/total-cycles pair repeated on every line, not a
parsing bug) -- confirmed: 38 of 40 rows carry an identical TSN and an
identical CSN; the other 2 rows have a corrupted CSN token with no digit
left in it at all.

Numeric-field corruption is real but irregular (e.g. a trailing "000" is
sometimes rendered as "^", "M", "ra", or dropped entirely, with no fixed
1:1 substitution that recovers the true value safely in every case).
Per this project's "never guess a wrong split, wrong data is worse than
missing data" convention, no digit-level auto-correction is attempted here.
TSN/CSN/CYCLES_LIMIT/CYCLES_REMAIN are kept as their raw extracted text and
validated with an ordinary digits-only pattern + range via `merged_rules()`
-- rows with corrupted digits simply flag as `bad_format` (or `not_a_number`
for the range check) rather than silently receiving a fabricated value.
Since each of the 4 trailing fields occupies an unambiguous fixed token
position (unlike some other LLP variants in this project where an
overlapping-glyph problem makes the token *count* itself unpredictable),
there is no split-ambiguity here to fall back to a STATUS_TRAIL catch-all
for -- only within-token digit corruption, which the flag mechanism already
surfaces honestly.
"""
from __future__ import annotations
import pdfplumber

from sheet_types.llp_variants._base import merged_rules

NAME = "Engine Items Control LLP Status"
SIGNATURES = [
    "ITEMS CONTROL FOR",
]

CANONICAL_COLUMNS = [
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "TSN",
    "CSN",
    "CYCLES_LIMIT",
    "CYCLES_REMAIN",
]

_NUM_RULE = {"pattern": r"^\d{1,6}$", "int_range": (0, 100000)}
_OVERRIDES = {
    "TSN": _NUM_RULE,
    "CSN": _NUM_RULE,
    "CYCLES_LIMIT": {"pattern": r"^\d{1,6}$", "int_range": (0, 60000)},
    "CYCLES_REMAIN": {"pattern": r"^\d{1,6}$", "int_range": (0, 60000)},
}
RULES = merged_rules(_OVERRIDES)


def _has_digit(tok: str) -> bool:
    return any(c.isdigit() for c in tok)


def _has_alpha(tok: str) -> bool:
    return any(c.isalpha() for c in tok)


def _parse_row(line: str) -> dict | None:
    toks = line.split()
    if len(toks) < 7:
        return None
    sn = toks[-5]
    pn = toks[-6]
    if not (_has_digit(sn) and _has_alpha(sn) and 6 <= len(sn) <= 13):
        return None
    if not _has_digit(pn):
        return None
    desc = " ".join(toks[:-6])
    if not desc:
        return None
    tsn, csn, limit, remain = toks[-4:]
    return {
        "DESCRIPTION": desc,
        "PART_NUMBER": pn,
        "SERIAL_NUMBER": sn,
        "TSN": tsn,
        "CSN": csn,
        "CYCLES_LIMIT": limit,
        "CYCLES_REMAIN": remain,
    }


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if len(text) < 50:
                continue
            for raw in text.splitlines():
                line = raw.rstrip()
                if not line.strip():
                    continue
                rec = _parse_row(line)
                if rec is None:
                    continue
                rec["_page"] = page_num
                records.append(rec)
    return records
