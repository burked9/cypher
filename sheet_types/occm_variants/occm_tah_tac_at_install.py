"""OCCM List variant with explicit "at install" AC hours/cycles columns.

Header line (confirmed in real-corpus triage):

    ATA Partno Serialno Description Pos Inst-Date TAH@INS TAC@INS TSN CSN

Per-row layout, whitespace-tokenized::

    ATA  PN  SN  DESCRIPTION...  POS  INST-DATE  TAH@INS  TAC@INS  TSN  CSN

A typical row::

    21 1209-100 14058 PRESSURE SWITCH 17HQ 12-Mar-11 36056 18943 11115 9933

TAH@INS / TAC@INS are the aircraft's total hours/cycles *at the time this
component was installed* -- distinct from TSN/CSN, which are the
component's own time/cycles since new. POS is always present (a real
position code, or the literal placeholder "ONLY" when no discrete position
applies).

Confirmed edge case: INST-DATE is occasionally replaced with a free-text
note pointing at another document instead of an actual date (seen on a
meaningful minority of rows in one real file -- roughly one row in eight).
The phrase has a fixed shape: "See last operator (<name>) doc." -- we match
it generically via regex rather than any specific operator name, and keep
POS split out correctly (it still precedes the free text) while INST_DATE
carries the full note verbatim rather than being dropped as unparseable.

A rarer edge case (well under 1% of rows in the same file): the TSN or CSN
cell itself is corrupted upstream of the PDF (an apparent Excel-export
artifact, e.g. a stray "#VALUE!" or a colon-separated value like
"28051:37" where a plain integer was expected). We don't attempt to
interpret these -- they're captured verbatim in TSN/CSN and left for
`clean_record`'s pattern validation to flag.

Sibling formats seen in the same header family but NOT covered by this
module (confirmed structurally different, not merely stylistic):
  - A layout with an extra ATA-description column and no TAH@INS/TAC@INS
    pair at all (header starts "ATA Description Partno Serialno
    Description Pos. Inst-Date TSN CSN").
  - A layout with an extra condition-code column between DESCRIPTION and
    POS, dot-separated dates (DD.MM.YYYY instead of D-Mon-YY), and
    "TAH Inst"/"TAC Inst" instead of "TAH@INS"/"TAC@INS" in the header.
Both would need their own variant module if/when more examples turn up.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "OCCM List (TAH/TAC at Install)"
SIGNATURES = [
    "ATA Partno Serialno Description Pos Inst-Date TAH@INS TAC@INS TSN CSN",
    "TAH@INS TAC@INS",
]

CANONICAL_COLUMNS = [
    "ATA",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
    "POSITION",
    "INSTALL_DATE",
    "TAH_AT_INSTALL",
    "TAC_AT_INSTALL",
    "TSN",
    "CSN",
]

# TSN/CSN/TAH/TAC cells are usually plain integers or the literal sentinel
# "UNKNOWN", but occasionally carry an upstream export artifact (colon or
# "#VALUE!") -- kept loose here and left to the flag-friendly default
# validation rather than a strict pattern that would just flag everything.
_LOOSE_NUM_RULE = {"pattern": r"^(?:\d+(?:[:.]\d+)?|UNKNOWN|#VALUE!)$"}

_OVERRIDES = {
    "POSITION": {"pattern": r"^[A-Z0-9][A-Z0-9./\-]{0,12}$", "uppercase": True},
    # Normal rows carry a D-Mon-YY date; the free-text "See last operator
    # (...) doc." substitution is a legitimate value too (genuinely unknown
    # install date), not a parsing failure -- allow both shapes.
    "INSTALL_DATE": {
        "pattern": r"^(?:\d{1,2}-[A-Za-z]{3}-\d{2}|See last operator \(.*\) doc\.)$",
    },
    "TAH_AT_INSTALL": _LOOSE_NUM_RULE,
    "TAC_AT_INSTALL": _LOOSE_NUM_RULE,
    "TSN": _LOOSE_NUM_RULE,
    "CSN": _LOOSE_NUM_RULE,
    "DESCRIPTION": {"uppercase": True},
}
RULES = merged_rules(_OVERRIDES)

_ATA_RE = re.compile(r"^\d{2}$")
_DATE_RE = re.compile(r"^\d{1,2}-[A-Za-z]{3}-\d{2}$")
_FREETEXT_START = "See"


def _parse_line(line: str, page_num: int) -> dict | None:
    line = line.strip()
    if not line:
        return None
    toks = line.split()
    if len(toks) < 8:
        return None
    if not _ATA_RE.match(toks[0]):
        return None
    try:
        ata_int = int(toks[0])
    except ValueError:
        return None
    if not (20 <= ata_int <= 83):
        return None

    # Trailing 4 tokens are always TAH@INS / TAC@INS / TSN / CSN by position,
    # regardless of their content (plain int, "UNKNOWN", or a rare corrupted
    # cell) -- we don't validate here, just slice; validation happens later
    # via RULES/clean_record.
    tah, tac, tsn, csn = toks[-4:]
    pn, sn = toks[1], toks[2]
    middle = toks[3:-4]
    if not middle:
        return None

    if _DATE_RE.match(middle[-1]):
        install_date = middle[-1]
        if len(middle) < 2:
            return None
        pos = middle[-2]
        description = " ".join(middle[:-2])
    elif _FREETEXT_START in middle:
        see_idx = middle.index(_FREETEXT_START)
        install_date = " ".join(middle[see_idx:])
        if see_idx < 1:
            return None
        pos = middle[see_idx - 1]
        description = " ".join(middle[:see_idx - 1])
    else:
        return None

    if not pos or not description:
        return None

    return {
        "ATA": toks[0],
        "PART_NUMBER": pn,
        "SERIAL_NUMBER": sn,
        "DESCRIPTION": description,
        "POSITION": pos,
        "INSTALL_DATE": install_date,
        "TAH_AT_INSTALL": tah,
        "TAC_AT_INSTALL": tac,
        "TSN": tsn,
        "CSN": csn,
        "_page": page_num,
    }


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            for raw in text.splitlines():
                rec = _parse_line(raw, page_num)
                if rec is not None:
                    records.append(rec)
    return records
