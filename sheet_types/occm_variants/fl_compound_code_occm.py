"""F/L Compound-Code OCCM List — single-line rows keyed on a compound
functional-location code.

Header (confirmed on real corpus files with a genuine pdfplumber text
layer)::

    <TAIL> [MSN <n>] OCCM List
    [ DATE : <dd-Mon-yyyy> ]
    F/L Material Description P/N S/N Install Date TSN CSN

A sibling sub-format drops the "[MSN ...]"/date lines and the trailing
TSN/CSN columns entirely::

    <TAIL> OCCM Components List
    F/L Material Description P/N S/N Install Date

Both sub-formats share the exact same column-header line prefix
``F/L Material Description P/N S/N Install Date`` (the sole SIGNATURES
anchor here), and both use the identical F/L compound code and row shape
for the columns they do have, so one module + one row-parser covers both;
the trailing TSN/CSN pair is simply left blank when absent.

F/L (functional location) is a compound code, one per row:
    <tail>-<ATA>-<subchapter>-<sequence>-<position code>
e.g. (genericized) ``REGXXXX-21-20-02-SSD``. The tail/registration prefix
is identical on every row in a file -- it is a cross-reference back to the
header, not per-row data -- so it is dropped rather than carried on every
record. The ATA chapter is pulled out into its own column (for
cross-format consistency / ATA-based tooling); everything from the ATA
chapter onward is also kept verbatim as POSITION_CODE, since the
sub-chapter/sequence/position segments don't follow a single fixed-width
shape (position codes are occasionally themselves hyphenated, e.g.
``...-01-F1-7``) and re-splitting them risks a wrong split more than it
helps.

MATERIAL DESCRIPTION may contain embedded asterisk-delimited annotations
(e.g. ``*A321&A330 EXC A320*``, ``*RTS/REP*``, ``*EC:2 / MTBR:9000*``).
These are inspected across many rows and are NOT consistently
open/close-delimited (some end in a second ``*``, many don't; a few use
``~`` instead) or consistently positioned (mid-description or trailing).
They're kept as part of the free-text DESCRIPTION rather than stripped or
split into their own column.

Row anchor: every row starts with the F/L compound code (``<tail>-DD-DD-``)
and ends with either ``INSTALL_DATE TSN CSN`` (ISO date, then a numeric
TSN and integer CSN) or just ``INSTALL_DATE`` alone. Whatever sits between
the F/L token and that trailing anchor is DESCRIPTION, PART_NUMBER,
SERIAL_NUMBER (last two tokens before the anchor = PN then SN).

Known limitation: a small number of rows (rare -- roughly 1 in several
hundred across the sampled files) have a genuinely blank source S/N. Since
extract_text() only gives us the token stream, not column x-positions,
these rows are indistinguishable from a normal 2-token PN+SN pair and the
last two tokens are read as PN then SN regardless -- which, for a blank-SN
row, silently shifts PART_NUMBER one token off. No reliable fix without
positional (x0/x1) extraction; flagged here rather than guessed around.
A second, separate glued-token quirk (also rare) sees the position-code
suffix of F/L run directly into the first description word with no space
(a pdfplumber text-extraction artifact, not a source-data issue) --
the glued text stays attached to POSITION_CODE rather than DESCRIPTION.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules
from shared.cleanup import normalize_dashes

NAME = "F/L Compound Code OCCM List"
SIGNATURES = [
    "F/L Material Description P/N S/N Install Date",
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

# TSN/CSN are absent entirely (not just occasionally blank) in the
# sibling sub-format that has no trailing time/cycle columns at all
# (see module docstring) -- allow_empty keeps that from flagging every
# single row of those files as an "empty" issue.
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

# Row-start anchor: F/L compound code, e.g. "REG1234-21-20-02-SSD".
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
