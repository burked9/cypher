"""'OCCM LIST MSN <n>' variant — dot-dated OCCM list with a CON(dition) column.

Structurally close to `occm_tah_tac_at_install.py` (same trailing TAH-at-
install / TAC-at-install / TSN / CSN column group), but confirmed different
in two ways rather than merely stylistic: an extra CON column between
DESCRIPTION and POS, and dot-separated dates (`DD.MM.YYYY`) instead of that
sibling's dash-separated `D-Mon-YY`. Its own docstring already flags this
exact combination as a distinct format needing its own module.

Header block (confirmed on the real sample file, first lines of every
page)::

    OCCM LIST MSN <n>
    date: <DD.MM.YYYY>
    TSN:<n>
    CSN:<n>
    ATA PART NO. SERIAL NO. DESCRIPTION CON POS. INST-DATE TAH Inst TAC Inst TSN CSN

Per-row layout, whitespace-tokenized::

    ATA  PN  SN  DESCRIPTION...  CON  POS...  INST-DATE  TAH_INST  TAC_INST  TSN  CSN

A typical row::

    21 <pn> <sn> INJECTOR-WATER R <position> <date> <tah_inst> <tac_inst> <tsn> <csn>

CON is a short condition code. Confirmed vocabulary on the sample file,
exhaustively checked (every one of 1679 rows matched exactly this set,
zero unmatched): N, R, IT, OH, M, S. Parsing matches against this closed
set rather than a loose "1-3 uppercase letters" shape -- POSITION words
like "LAV", "AFT", "FWD" are themselves exactly 1-3 uppercase letters and
would otherwise collide with real CON tokens (confirmed: a loose shape
misparses rows like "LIGHT-CALL N LAV A", stealing the trailing "A" as
CON instead of the real "N"). The validation RULES pattern is kept looser
than this vocabulary (see _OVERRIDES below) so a future file with one or
two more codes from the same family doesn't get every row flagged, but
the *parser's* split point always uses the confirmed six.

POS is NOT always a single token -- confirmed multi-token positions on the
sample file, e.g. "AFT GALLEY", "ENG 1", "#2 LH", "MLG RH", "ROW 10 LH",
"18LV ONLY", "SLAT #2". This is the main reason CON can't simply be "the
token before POS": we locate CON by scanning the DESCRIPTION..POS span
for a token in the closed vocabulary and taking the *last* such match,
then treating everything to its left as DESCRIPTION and everything to its
right (up to INST-DATE) as POS. Taking the last match (not the first)
matters for a confirmed rare case (well under 1% of rows) where a lone
"N" (an OCR/text-layer rendering of "No." missing its period, e.g.
"FLAP TRACK N 3 LH") lands inside DESCRIPTION itself ahead of the real
CON token later in the same row -- picking the first match there would
misclassify the description's own "N" as CON and leave the real CON stuck
in POS.

SERIAL_NO and PART_NUMBER can carry a hyphenated/lettered prefix rather
than being purely alphanumeric (e.g. a serial like "C-ABC12345678") --
confirmed on a meaningful fraction of rows (roughly one in ten sampled),
not a rare edge case, so no tokenizer assumption here treats a hyphen as
a field separator within these two columns.

TAH Inst / TAC Inst / TSN / CSN cells are usually plain integers but the
literal sentinel "UNKNOWN" is common (roughly one row in three sampled) for
components with no recorded install baseline -- a real value, not a parse
failure. A small number of rows also carry an apparent upstream
spreadsheet-export artifact in PART_NUMBER or SERIAL_NUMBER (comma-decimal
scientific notation, or a non-Latin homoglyph letter substituted for a
Latin one) -- left verbatim rather than guessed at, same call as the
"at install" sibling module makes for its own rare corrupted cells.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "OCCM List MSN (Dot-Dated, With Condition)"
SIGNATURES = [
    "OCCM LIST MSN",
    "ATA PART NO. SERIAL NO. DESCRIPTION CON POS. INST-DATE TAH Inst TAC Inst TSN CSN",
]

CANONICAL_COLUMNS = [
    "ATA",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
    "CONDITION",
    "POSITION",
    "INSTALL_DATE",
    "TAH_AT_INSTALL",
    "TAC_AT_INSTALL",
    "TSN",
    "CSN",
]

# TAH/TAC/TSN/CSN cells are usually plain integers or the literal sentinel
# "UNKNOWN", but occasionally carry an upstream export artifact -- kept loose
# and left to the flag-friendly default validation, same as the "at install"
# sibling module's _LOOSE_NUM_RULE.
_LOOSE_NUM_RULE = {"pattern": r"^(?:\d+(?:[:.]\d+)?|UNKNOWN|#VALUE!)$"}

_OVERRIDES = {
    # Confirmed closed-ish vocabulary N/R/IT/OH/M/S -- kept as a loose
    # 1-3 uppercase-letter shape rather than a strict enum (see docstring).
    "CONDITION": {"pattern": r"^[A-Z]{1,3}$", "uppercase": True},
    "POSITION": {"pattern": r"^[A-Z0-9#()./\- ]{1,40}$", "uppercase": True},
    "INSTALL_DATE": {"pattern": r"^\d{2}\.\d{2}\.\d{4}$"},
    "TAH_AT_INSTALL": _LOOSE_NUM_RULE,
    "TAC_AT_INSTALL": _LOOSE_NUM_RULE,
    "TSN": _LOOSE_NUM_RULE,
    "CSN": _LOOSE_NUM_RULE,
    "DESCRIPTION": {"uppercase": True},
}
RULES = merged_rules(_OVERRIDES)

_ATA_RE = re.compile(r"^\d{2}$")
_DATE_RE = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")
# Closed vocabulary confirmed by exhaustive check against the sample file
# (see module docstring) -- deliberately NOT a loose shape-based regex,
# since several real POSITION words ("LAV", "AFT", "FWD") are themselves
# 1-3 uppercase letters and would otherwise collide.
_CON_VOCAB = frozenset({"N", "R", "IT", "OH", "M", "S"})


def _parse_line(line: str, page_num: int) -> dict | None:
    line = line.strip()
    if not line:
        return None
    toks = line.split()
    if len(toks) < 9:
        return None
    if not _ATA_RE.match(toks[0]):
        return None
    try:
        ata_int = int(toks[0])
    except ValueError:
        return None
    if not (20 <= ata_int <= 83):
        return None

    # Trailing 4 tokens are always TAH Inst / TAC Inst / TSN / CSN by
    # position -- sliced without validation here (see _LOOSE_NUM_RULE).
    tah, tac, tsn, csn = toks[-4:]

    date_idx = None
    for i in range(3, len(toks) - 4):
        if _DATE_RE.match(toks[i]):
            date_idx = i
            break
    if date_idx is None:
        return None

    pn, sn = toks[1], toks[2]
    middle = toks[3:date_idx]
    if not middle:
        return None

    # CON is the LAST token in the DESCRIPTION..POS span found in the closed
    # vocabulary -- see module docstring for why "last" (not "first")
    # matters on a confirmed rare edge case.
    con_idx = None
    for i, t in enumerate(middle):
        if t in _CON_VOCAB:
            con_idx = i
    if con_idx is None:
        return None

    description = " ".join(middle[:con_idx])
    condition = middle[con_idx]
    position = " ".join(middle[con_idx + 1:])
    if not description:
        return None

    return {
        "ATA": toks[0],
        "PART_NUMBER": pn,
        "SERIAL_NUMBER": sn,
        "DESCRIPTION": description,
        "CONDITION": condition,
        "POSITION": position,
        "INSTALL_DATE": toks[date_idx],
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
