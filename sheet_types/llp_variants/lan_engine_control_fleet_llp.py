"""LAN-family "ENGINE CONTROL FLEET ENGINES" engine LLP status report.

Confirmed on a single real file so far (singleton cluster). Header block::

    <report generation date/time>
    <operator name>
    ENGINE CONTROL FLEET ENGINES
    PLACE & POS <place code> <position>
    ENGINE TT <tt> TC <tc>
    STATUS DATE & MFL <date> <mfl>
    ENGINE S/N <esn>
    Limits Disk Total Disk Remain
    Disk Disk S/N Disk P/N Hours Cycles Hours Cycles Hours Cycles

followed by one line per disk, e.g. (values genericized)::

    LPC Hub F ABCDEF1234 50X301 0 15000 27412 6256

Row grain: one row per LLP disk. DESCRIPTION, DISK_SERIAL_NUMBER and
DISK_PART_NUMBER are anchored reliably -- the serial number is always an
all-caps letters+digits token 9-11 chars long (e.g. "ABCDEF1234"), found by
scanning the line's tokens; everything before it is the description, and
the token right after it is the part number (2 digits + letter + 3 digits,
optionally "-NN").

The trailing numeric block (per the header: Limits/Total-Disk/Remain, each
split into Hours and Cycles -- 6 sub-values in principle) is NOT split into
individual columns here. `extract_text()` on this file is genuinely messy:
a stray checkmark-like glyph (`V`, `^`, `/`, `\\/`, `y`, `i`, ...) --
apparently from an overlapping graphic/checkbox column pdfplumber's text-flow
interleaves into the row -- lands at an unpredictable position in the
trailing token run on most rows, and on several rows a stray digit-only
token (e.g. a lone "7" or "3") is glued in *before* the real first number,
which would silently shift a positional Hours/Cycles split by one column.
Word-position clustering (`extract_words` + y-clustering, the approach used
in `ht_variants/time_controlled_components_status.py` for a similar
column-overflow problem) was tried and tested worse here: this format's
logical rows are frequently split across 2-3 distinct y-positions with only
~1-3pt of vertical separation, so grouping by y alone fragments a single row
into multiple pieces more often than plain `extract_text()` already
reassembles them correctly. Given the noise lands inconsistently even in
the "Limits Hours" sub-column that is otherwise always literally "0", the
whole trailing block (everything after DISK_PART_NUMBER, including glyph
noise) is kept verbatim in STATUS_TRAIL per this project's "never guess a
wrong split" convention, rather than risk a silently-misaligned Hours/Cycles
split on an unknown fraction of rows.

A further complication: on some rows the tail of the Remain block overflows
onto its own orphan physical text line entirely (e.g. a lone "1 8 744"),
immediately following the row it belongs to in line order. These orphan
lines are appended onto the preceding row's STATUS_TRAIL rather than
dropped or mistaken for a new row (they never contain a serial-number-shaped
token, so they can't be confused with one).

File-level metadata (OPERATOR, PLACE_CODE, POSITION, ENGINE_TT, ENGINE_TC,
STATUS_DATE, MFL, ESN) is parsed once from the header block and stamped on
every row, matching every other variant here. OPERATOR is read generically
from whichever line precedes the "ENGINE CONTROL FLEET ENGINES" title line,
rather than hardcoded, since only one real example of this format has been
seen.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.llp_variants._base import merged_rules

NAME = "LAN Engine Control Fleet LLP"
SIGNATURES = [
    "ENGINE CONTROL FLEET ENGINES",
]

CANONICAL_COLUMNS = [
    "DESCRIPTION",
    "DISK_SERIAL_NUMBER",
    "DISK_PART_NUMBER",
    "STATUS_TRAIL",
    # File-level metadata -- same on every row
    "OPERATOR",
    "PLACE_CODE",
    "POSITION",
    "ENGINE_TT",
    "ENGINE_TC",
    "STATUS_DATE",
    "MFL",
    "ESN",
]

_HOUR_RULE = {"pattern": r"^[\d.,']+$", "int_range": (0, 80000)}
_CYCLE_RULE = {"pattern": r"^[\d.,']+$", "int_range": (0, 55000),
               "int_range_review": (0, 30000)}
_OVERRIDES = {
    "DISK_SERIAL_NUMBER": {"pattern": r"^[A-Z0-9]+$", "uppercase": True},
    "DISK_PART_NUMBER": {"pattern": r"^\d{2}[A-Z]\d{3}(-\d{2})?$",
                          "uppercase": True},
    "STATUS_TRAIL": {"allow_empty": True},
    "OPERATOR": {"allow_empty": True},
    "PLACE_CODE": {"allow_empty": True, "uppercase": True},
    "POSITION": {"pattern": r"^\d+$", "allow_empty": True},
    "ENGINE_TT": _HOUR_RULE,
    "ENGINE_TC": _CYCLE_RULE,
    "STATUS_DATE": {"pattern": r"^\d{2}-\d{2}-\d{4}$"},
    "MFL": {"pattern": r"^\d+$", "allow_empty": True},
    "ESN": {"pattern": r"^\d+$"},
}
RULES = merged_rules(_OVERRIDES)

# All-caps letters-then-digits token, 9-11 chars -- shape observed for every
# disk serial number on the sample file (e.g. "ABCDEF1234", "GHIJKL5678").
_SN_RE = re.compile(r"^[A-Z]{3,7}[0-9]{2,7}$")
# Disk part number: 2 digits, a letter, 3 digits, optional "-NN" suffix.
# A stray checkmark-like glyph is sometimes glued directly onto the end of
# this token with no space (e.g. "50N486-01V") -- only the matched prefix
# is kept as the part number.
_PN_RE = re.compile(r"^(\d{2}[A-Z]\d{3}(?:-\d{2})?)")

_HEADER_PREFIXES = (
    "April", "PLACE", "ENGINE TT", "STATUS DATE", "ENGINE S/N",
    "Limits", "Disk Disk", "Disk ", "Disk\t",
)


def _is_header_or_meta_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return True
    if s.upper() == "ENGINE CONTROL FLEET ENGINES":
        return True
    return any(s.startswith(p) for p in _HEADER_PREFIXES)


def _parse_meta(text: str) -> dict:
    meta: dict[str, str] = {}
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s.upper() == "ENGINE CONTROL FLEET ENGINES" and i > 0:
            meta["OPERATOR"] = lines[i - 1].strip()
        m = re.match(r"PLACE\s*&\s*POS\s+(\S+)\s+(\S+)", s)
        if m:
            meta["PLACE_CODE"], meta["POSITION"] = m.group(1), m.group(2)
        m = re.match(r"ENGINE TT\s+(\S+)\s+TC\s+(\S+)", s)
        if m:
            meta["ENGINE_TT"], meta["ENGINE_TC"] = m.group(1), m.group(2)
        m = re.match(r"STATUS DATE\s*&\s*MFL\s+(\S+)\s+(\S+)", s)
        if m:
            meta["STATUS_DATE"], meta["MFL"] = m.group(1), m.group(2)
        m = re.match(r"ENGINE S/N\s+(\S+)", s)
        if m:
            meta["ESN"] = m.group(1)
    return meta


def _parse_row(line: str) -> dict | None:
    toks = line.split()
    sn_idx = None
    for idx, t in enumerate(toks):
        if _SN_RE.match(t):
            sn_idx = idx
            break
    if sn_idx is None:
        return None
    desc = " ".join(toks[:sn_idx])
    if not desc:
        return None
    sn = toks[sn_idx]
    rest = toks[sn_idx + 1:]
    if not rest:
        return None
    pn_raw = rest[0]
    m = _PN_RE.match(pn_raw)
    if not m:
        return None
    pn = m.group(1)
    trail_tokens = [pn_raw[len(pn):]] if len(pn_raw) > len(pn) else []
    trail_tokens += rest[1:]
    trail = " ".join(t for t in trail_tokens if t)

    rec = {c: "" for c in CANONICAL_COLUMNS}
    rec["DESCRIPTION"] = desc
    rec["DISK_SERIAL_NUMBER"] = sn
    rec["DISK_PART_NUMBER"] = pn
    rec["STATUS_TRAIL"] = trail
    return rec


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        full_text = "\n".join((p.extract_text() or "") for p in pdf.pages)
        meta = _parse_meta(full_text)
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if len(text) < 50:
                continue
            last_rec = None
            for raw in text.splitlines():
                line = raw.rstrip()
                if not line.strip():
                    continue
                if _is_header_or_meta_line(line):
                    continue
                rec = _parse_row(line)
                if rec is not None:
                    for k, v in meta.items():
                        rec[k] = v
                    rec["_page"] = page_num
                    records.append(rec)
                    last_rec = rec
                    continue
                # No serial-number-shaped token on this line -- it's an
                # orphan overflow fragment of the previous row's trailing
                # block (see docstring), not a new row.
                if last_rec is not None:
                    frag = line.strip()
                    last_rec["STATUS_TRAIL"] = (
                        f"{last_rec['STATUS_TRAIL']} {frag}".strip()
                    )
    return records
