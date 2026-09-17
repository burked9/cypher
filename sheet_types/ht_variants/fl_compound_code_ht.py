"""F/L Compound-Code HT List — single-line rows keyed on a compound
functional-location code.

This is the Hard-Time-flavored sibling of
`occm_variants/fl_compound_code_occm.py`: same source MIS system, same F/L
compound-code row shape and same column-header line, but emitted with a
"Hard Time"-titled header instead of an "OCCM"-titled one when the export
is filtered to hard-time-limited positions (the same OCCM/HT export-split
pattern this project's `remaining_potentials.py` pair documents for its
own MIS family).

Header (confirmed on a real file with a genuine pdfplumber text layer,
tail genericized below)::

    <TAIL> Hard Time Components List
    F/L Material Description P/N S/N Install Date

No trailing TSN/CSN columns were observed on the one sample file checked
(unlike the sibling OCCM module's primary sub-format, which does have
them) -- CANONICAL_COLUMNS still carries TSN/CSN for cross-format
consistency with that sibling and in case a sibling HT sub-format with
those columns turns up later, exactly as the OCCM module already does for
its own no-TSN/CSN sub-format; they are simply always blank for this
sub-format and `allow_empty` keeps that from flagging every row.

F/L (functional location) is a compound code, one per row:
    <tail>-<ATA>-<subchapter>-<sequence>-<position code>
e.g. (genericized) ``REGXXXX-21-26-02-SAE``. The tail/registration prefix
is identical on every row in a file -- it is a cross-reference back to the
header, not per-row data -- so it is dropped rather than carried on every
record. The ATA chapter is pulled into its own column; everything from the
ATA chapter onward is also kept verbatim as POSITION_CODE, since the
sub-chapter/sequence/position segments don't follow one fixed-width shape
(re-splitting them risks a wrong split more than it helps).

MATERIAL DESCRIPTION may contain embedded asterisk-delimited annotations
(e.g. ``*RTS/PML/CCL*``, ``*MEL*``, ``*TCS*``) and stray punctuation
(commas, parentheses, apostrophes). These are kept as part of the free-text
DESCRIPTION rather than stripped or split into their own column, same call
the sibling OCCM module makes for the same reason.

Row anchor: every row starts with the F/L compound code (``<tail>-DD-DD-``)
and ends with either ``INSTALL_DATE TSN CSN`` or just ``INSTALL_DATE``
alone (same two-shape trailing anchor as the sibling module). Whatever
sits between the F/L token and that trailing anchor is DESCRIPTION,
PART_NUMBER, SERIAL_NUMBER (last two tokens before the anchor = PN then
SN) -- verified against every row of the one sample file checked: every
row splits cleanly this way, none required forcing an ambiguous split.

Known limitation, inherited from the sibling module: a genuinely blank
source S/N would be indistinguishable from a normal 2-token PN+SN pair
using extract_text()'s plain token stream (no x-position data), which
would silently shift PART_NUMBER one token off for that row. None were
observed in the one sample file checked, but no reliable fix exists
without positional extraction, so this is flagged here rather than
guessed around, same as the sibling module.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.ht_variants._base import merged_rules
from shared.cleanup import normalize_dashes

NAME = "F/L Compound Code HT List"
SIGNATURES = [
    # This file's own title-line phrase. Deliberately NOT the shared
    # "F/L Material Description P/N S/N Install Date" column-header line --
    # that exact phrase is also occm_variants/fl_compound_code_occm.py's own
    # SIGNATURES anchor (same source MIS template family, OCCM-flavored
    # export), so it can't disambiguate HT from OCCM on its own. This title
    # phrase says "Hard Time" instead of "OCCM", so it's mutually exclusive
    # with that sibling's own two title phrases ("... OCCM List" / "...
    # OCCM Components List"). Checked against every SIGNATURES list in
    # occm.py/ht.py/llp.py and every occm_variants/ht_variants/llp_variants
    # module's own SIGNATURES list (including a plain grep for "hard time
    # components list", case-insensitive); no collision found. Also checked
    # this project's one other "HARD TIME COMPONENT LIST" (singular
    # "COMPONENT")-titled variant, hard_time_component_list.py -- that
    # phrase requires "COMPONENT" immediately followed by a space then
    # "LIST", but this file's title has "COMPONENTS" (plural) there
    # instead, so neither phrase is a substring of the other.
    "Hard Time Components List",
]

CANONICAL_COLUMNS = [
    "ATA",
    "POSITION_CODE",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "INSTALL_DATE",
    "TSN",
    "CSN",
]

# TSN/CSN are absent entirely (not just occasionally blank) in this
# sub-format -- allow_empty keeps that from flagging every single row as
# an "empty" issue, same as the sibling OCCM module.
_NUM_RULE = {"pattern": r"^\d+(?:\.\d+)?$", "allow_empty": True}
_INT_RULE = {"pattern": r"^\d+$", "int_range": (0, 55000), "int_range_review": (0, 30000),
             "allow_empty": True}
_OVERRIDES = {
    "POSITION_CODE": {"pattern": r"^\d{2}-.+$", "uppercase": True},
    "INSTALL_DATE": {"pattern": r"^\d{4}-\d{2}-\d{2}$"},
    "TSN": _NUM_RULE,
    "CSN": _INT_RULE,
}
RULES = merged_rules(_OVERRIDES)

# Row-start anchor: F/L compound code, e.g. "REG1234-21-26-02-SAE".
_FL_LINE_RE = re.compile(r"^\S+-\d{2}-\d{2}-")
# Trailing anchors.
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_NUM_RE = re.compile(r"^\d+(?:\.\d+)?$")
_INT_RE = re.compile(r"^\d+$")


def _split_fl(fl: str) -> tuple[str, str]:
    """Return (ata, position_code) from an F/L compound code, dropping the
    leading tail/registration prefix (assumed dash-free -- true of every
    registration/tail seen in the corpus so far)."""
    if "-" not in fl:
        return "", fl
    _tail, rest = fl.split("-", 1)
    m = re.match(r"^(\d{2})-", rest)
    ata = m.group(1) if m else ""
    return ata, rest


def _parse_line(line: str, page_num: int) -> dict | None:
    line = line.strip()
    if not _FL_LINE_RE.match(line):
        return None
    toks = line.split()
    if len(toks) < 4:
        return None
    fl = toks[0]

    if len(toks) >= 4 and _DATE_RE.match(toks[-3]) and _NUM_RE.match(toks[-2]) and _INT_RE.match(toks[-1]):
        date, tsn, csn = toks[-3], toks[-2], toks[-1]
        rest_toks = toks[1:-3]
    elif _DATE_RE.match(toks[-1]):
        date, tsn, csn = toks[-1], "", ""
        rest_toks = toks[1:-1]
    else:
        return None

    if len(rest_toks) < 2:
        return None
    pn = rest_toks[-2]
    sn = rest_toks[-1]
    desc = " ".join(rest_toks[:-2])
    if not desc:
        return None

    ata, position_code = _split_fl(fl)
    return {
        "ATA": ata,
        "POSITION_CODE": position_code,
        "DESCRIPTION": desc,
        "PART_NUMBER": pn,
        "SERIAL_NUMBER": sn,
        "INSTALL_DATE": date,
        "TSN": tsn,
        "CSN": csn,
        "_page": page_num,
    }


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = normalize_dashes(page.extract_text() or "")
            for line in text.splitlines():
                rec = _parse_line(line, page_num)
                if rec is not None:
                    records.append(rec)
    return records
