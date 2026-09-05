""""<reg> OCCM LIST - <asof> AT AIRCRAFT FH: <fh> FC: <fc>" — six-pair
FH/CYC time-matrix OCCM export with a real (native) text layer, no OCR
needed. Confirmed via a direct pdfplumber pass across every page of one
real sample file (a widebody airframe, several hundred rows across ~15
pages).

Header block (repeats verbatim at the top of every page)::

    <reg> OCCM LIST - <asof DDMMYY> AT AIRCRAFT FH: <fh H:MM> FC: <fc>
    Serial Part Parent Serial Slot Name FH-TSN CYC-TSN FH-TSO CYC-TSO
        FH-TSFR CYC-TSFR FH-TSR CYC-TSR FH-TSSV CYC-TSSV FH-TSI CYC-TSI
        Config Address Last Installed Date

The hyphens in both the title line and the six `FH-xxx`/`CYC-xxx` column
labels are U+2010 (HYPHEN), not the ASCII U+002D hyphen-minus — confirmed
by inspecting the raw extracted text directly. Every line is run through
`shared.cleanup.normalize_dashes()` before any regex/token parsing so a
plain ASCII `-` anchors correctly throughout this module.

Per-row layout, whitespace-tokenized (a typical clean row)::

    <sn> <pn> <parent_serial> <slot name tokens...> \
        <fh_tsn> <cyc_tsn> <fh_tso> <cyc_tso> <fh_tsfr> <cyc_tsfr> \
        <fh_tsr> <cyc_tsr> <fh_tssv> <cyc_tssv> <fh_tsi> <cyc_tsi> \
        <config_address> <last_installed_date>

FH cells are `H:MM` (hours:minutes, e.g. `46046:12` or `0:00`); CYC cells
are plain integers. SLOT_NAME is free text that may itself contain
` - `-separated segments (e.g. a location, a sub-assembly name and a FIN
code all joined with hyphens) — it is NOT split further, just captured
whole.

PARENT_SERIAL is NOT reliably the aircraft registration repeated on every
row, despite that being a reasonable first guess from the column header
alone ("Parent Serial") — confirmed directly: on the real sample file the
overwhelming majority of rows do carry the aircraft reg here, but a
meaningful minority instead carry a different serial-shaped token (an
assembly/sub-component serial, e.g. an HT-tagged item's own parent
assembly). PARENT_SERIAL is therefore captured verbatim per row rather
than assumed to equal the header's aircraft registration. AIRCRAFT_REG
(the header title line's own callsign, plus the as-of date/FH/FC figures)
is parsed once per page and stamped onto every row of that page separately
from PARENT_SERIAL.

CONFIG / ADDRESS are NOT split into two columns. The header names them as
two separate fields, but the real data gives no reliable way to tell where
one ends and the other begins: confirmed directly, the trailing cell
between the sixth CYC-TSI value and the install date is usually a single
undelimited digit run (e.g. `<8-digit code>`), occasionally two codes
joined with a bare colon (`<code>:<code>`), and on some rows entirely
BLANK — with the text-extraction order in that case instead placing a
verbatim repeat of the row's own SLOT_NAME text in that position (an
artifact of the underlying PDF's column layout, not real Config/Address
data). Splitting the digit-run case at a guessed offset, or treating the
repeated-description case as a real value, would both risk fabricating
data the source file doesn't actually contain — so this module keeps the
one raw trailing token as CONFIG_ADDRESS only when it is a single clean
token (a digit run, optionally with one embedded colon); every other
shape for that trailing cell (missing, multi-token, non-numeric) is left
out of CONFIG_ADDRESS entirely and folded into STATUS_TRAIL instead, so
the raw text survives for manual review rather than being silently
dropped or guessed into the wrong field.

The six FH/CYC pairs (TSN/TSO/TSFR/TSR/TSSV/TSI, in that column order) are
likewise only assigned to their twelve named columns when all six pairs
are present and well-formed on that row. A small minority of rows carry
only three FH/CYC pairs before the row's trailing cell — confirmed
directly, always alongside a missing Config/Address (the same blank-cell
pattern described above). Because plain whitespace tokenizing has no way
to know which three of the six named pairs a truncated row's values
actually belong to (the source PDF carries no per-cell position info once
reduced to a text stream), guessing they are always the *first* three
(TSN/TSO/TSFR) would risk mislabeling real data — so a row like this gets
all twelve FH/CYC columns left empty and its raw numeric tail preserved
in STATUS_TRAIL instead.

Row anchor: the trailing `DD/MM/YYYY` install-date token, confirmed
present on every real data row and absent from the two header lines and
two footer lines (`Prepared by ...` / `Page N of M`) that otherwise repeat
on every page.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules
from shared.cleanup import normalize_dashes

NAME = "OCCM List (At Aircraft FH)"
# Deliberately NOT a bare "OCCM LIST" signature -- that substring also
# matches occm_list_msn_dotdate.py ("OCCM LIST MSN"), occm_list_as_at.py
# ("OCCM LIST AS AT") and occm_list_for_registration.py ("OCCM LIST FOR"),
# and detection is plain substring matching, not anchored. Both signatures
# below are checked for collisions against every SIGNATURES list in
# sheet_types/{occm,ht,llp}.py and every existing variant file.
SIGNATURES = [
    "AT AIRCRAFT FH:",
    "Serial Part Parent Serial Slot Name",
]

CANONICAL_COLUMNS = [
    "SERIAL_NUMBER",
    "PART_NUMBER",
    "PARENT_SERIAL",
    "SLOT_NAME",
    "FH_TSN", "CYC_TSN",
    "FH_TSO", "CYC_TSO",
    "FH_TSFR", "CYC_TSFR",
    "FH_TSR", "CYC_TSR",
    "FH_TSSV", "CYC_TSSV",
    "FH_TSI", "CYC_TSI",
    "CONFIG_ADDRESS",
    "LAST_INSTALLED_DATE",
    # Ambiguous trailing data that can't be reliably split into the above
    # (see docstring: reduced FH/CYC pair counts, missing/multi-token
    # Config/Address, or a repeated-description text artifact).
    "STATUS_TRAIL",
    # Header metadata -- parsed once per page, stamped onto every row.
    "AIRCRAFT_REG",
    "AS_OF_DATE",
    "AC_FH_ASOF",
    "AC_FC_ASOF",
]

_FH_RULE = {"pattern": r"^\d{1,6}:\d{2}$"}
_CYC_RULE = {"pattern": r"^\d+$", "int_range": (0, 200000)}

_OVERRIDES = {
    "PARENT_SERIAL": {"pattern": r"^[A-Z0-9]{1,20}$", "uppercase": True},
    "SLOT_NAME": {"pattern": r"^[A-Z0-9 #/&().:\-]{1,120}$", "uppercase": True},
    "FH_TSN": _FH_RULE, "FH_TSO": _FH_RULE, "FH_TSFR": _FH_RULE,
    "FH_TSR": _FH_RULE, "FH_TSSV": _FH_RULE, "FH_TSI": _FH_RULE,
    "CYC_TSN": _CYC_RULE, "CYC_TSO": _CYC_RULE, "CYC_TSFR": _CYC_RULE,
    "CYC_TSR": _CYC_RULE, "CYC_TSSV": _CYC_RULE, "CYC_TSI": _CYC_RULE,
    # A single digit run, optionally with one embedded colon joining two
    # sub-codes -- see docstring for why this is never split further.
    "CONFIG_ADDRESS": {"pattern": r"^\d+(?::\d+)?$", "allow_empty": True},
    "LAST_INSTALLED_DATE": {"pattern": r"^\d{2}/\d{2}/\d{4}$"},
    "STATUS_TRAIL": {"allow_empty": True},
    "AIRCRAFT_REG": {"pattern": r"^[A-Z0-9]{1,20}$", "uppercase": True,
                      "allow_empty": True},
    "AS_OF_DATE": {"pattern": r"^\d{2}/\d{2}/\d{4}$", "allow_empty": True},
    "AC_FH_ASOF": dict(_FH_RULE, allow_empty=True),
    "AC_FC_ASOF": dict(_CYC_RULE, allow_empty=True),
}
RULES = merged_rules(_OVERRIDES)

_FH_RE = re.compile(r"^\d{1,6}:\d{2}$")
_CYC_RE = re.compile(r"^\d+$")
_DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")
_CONFIG_ADDR_RE = re.compile(r"^\d+(?::\d+)?$")

_HEADER_RE = re.compile(
    r"^(?P<reg>\S+)\s+OCCM LIST\s*-\s*(?P<asof>\d{6})\s+AT AIRCRAFT FH:\s*"
    r"(?P<fh>\d{1,6}:\d{2})\s+FC:\s*(?P<fc>\d+)\s*$"
)

_N_PAIRS = 6
_PAIR_NAMES = ["TSN", "TSO", "TSFR", "TSR", "TSSV", "TSI"]


def _asof_to_date(raw: str) -> str:
    """`DDMMYY` -> `DD/MM/YYYY`. Confirmed 2-digit year is safely 20xx on
    the real sample file (as-of date sits within days of the file's own
    latest install dates, all in the 2000s/2010s)."""
    if not re.match(r"^\d{6}$", raw):
        return ""
    dd, mm, yy = raw[0:2], raw[2:4], raw[4:6]
    return f"{dd}/{mm}/20{yy}"


def _parse_header(line: str) -> dict:
    m = _HEADER_RE.match(line.strip())
    if not m:
        return {}
    return {
        "AIRCRAFT_REG": m.group("reg"),
        "AS_OF_DATE": _asof_to_date(m.group("asof")),
        "AC_FH_ASOF": m.group("fh"),
        "AC_FC_ASOF": m.group("fc"),
    }


def _find_pairs_block(tokens: list[str], start_min: int) -> tuple[int, int, list[tuple[str, str]]]:
    """Find the earliest FH/CYC pair starting at or after `start_min`, then
    consume as many consecutive alternating (FH, CYC) pairs as are present,
    up to `_N_PAIRS`. Returns (block_start, block_end, pairs)."""
    n = len(tokens)
    for start in range(start_min, n - 1):
        if _FH_RE.match(tokens[start]) and _CYC_RE.match(tokens[start + 1]):
            pairs: list[tuple[str, str]] = []
            idx = start
            while (len(pairs) < _N_PAIRS and idx + 1 < n
                   and _FH_RE.match(tokens[idx]) and _CYC_RE.match(tokens[idx + 1])):
                pairs.append((tokens[idx], tokens[idx + 1]))
                idx += 2
            return start, idx, pairs
    return -1, -1, []


def _parse_data_line(line: str, page_num: int, header_meta: dict) -> dict | None:
    toks = line.split()
    if len(toks) < 7:
        return None
    if not _DATE_RE.match(toks[-1]):
        return None
    last_installed_date = toks[-1]
    body = toks[:-1]  # everything except the trailing date

    sn, pn, parent = body[0], body[1], body[2]
    block_start, block_end, pairs = _find_pairs_block(body, start_min=3)
    if block_start < 0:
        # No FH/CYC pairs recognisable at all -- not a data row we can trust.
        return None

    slot_name = " ".join(body[3:block_start])
    tail = body[block_end:]

    rec: dict = {c: "" for c in CANONICAL_COLUMNS}
    rec["SERIAL_NUMBER"] = sn
    rec["PART_NUMBER"] = pn
    rec["PARENT_SERIAL"] = parent
    rec["SLOT_NAME"] = slot_name
    rec["LAST_INSTALLED_DATE"] = last_installed_date
    rec.update(header_meta)
    rec["_page"] = page_num

    status_bits: list[str] = []

    if len(pairs) == _N_PAIRS:
        for name, (fh, cyc) in zip(_PAIR_NAMES, pairs):
            rec[f"FH_{name}"] = fh
            rec[f"CYC_{name}"] = cyc
        if len(tail) == 1 and _CONFIG_ADDR_RE.match(tail[0]):
            rec["CONFIG_ADDRESS"] = tail[0]
        elif tail:
            # Missing/ambiguous Config+Address (blank cell text-extraction
            # artifact, or a shape we don't recognise) -- never guessed,
            # kept raw for review. See docstring.
            status_bits.append(" ".join(tail))
    else:
        # Fewer than 6 pairs recognised: we cannot tell which of the six
        # named FH/CYC columns a truncated row's values belong to, so none
        # are assigned -- the raw pair values plus any trailing tail are
        # preserved verbatim instead. See docstring.
        raw_pairs = " ".join(f"{fh} {cyc}" for fh, cyc in pairs)
        status_bits.append(raw_pairs)
        if tail:
            status_bits.append(" ".join(tail))

    rec["STATUS_TRAIL"] = " ".join(b for b in status_bits if b).strip()
    return rec


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if len(text) < 50:
                continue
            text = normalize_dashes(text)
            header_meta: dict = {}
            for line in text.splitlines():
                stripped = line.strip()
                if not stripped:
                    continue
                if header_meta == {} and " OCCM LIST" in stripped and "AT AIRCRAFT FH:" in stripped:
                    header_meta = _parse_header(stripped)
                    continue
                if stripped.startswith("Serial Part Parent Serial Slot Name"):
                    continue
                if stripped.startswith("Prepared by"):
                    continue
                if re.match(r"^Page \d+ of \d+$", stripped):
                    continue
                rec = _parse_data_line(stripped, page_num, header_meta)
                if rec is not None:
                    records.append(rec)
    return records
