"""AL Development Division / Planning Section — MPD-task Controlled Items List.

Header (a known A320-family file in the corpus)::

    A/C Reg.: <tail no.> CONTROLLED ITEMS LIST Status Date: 16-Oct-10
    A/C MSN: <MSN> A/C FHs: 24,501
    A/C Model: A320-214 A/C FCs: 14,604
    AL DEVELOPMENT DIVISION A/C Manufactue Date: Aug-1999
    PLANNING SECTION
    MPD TASK Work Type ZONE DESIGNAION Vendor PN SN Man ...

The same template also ships under a "SAFETY EQUIPMENTS" title (a filtered
subset of the same report, same header/column layout, same garbling
behaviour) — confirmed a same-format sub-variant, not a distinct format, so
one module covers both. One sample file in the cluster also drops the "AL
DEVELOPMENT DIVISION" / "PLANNING SECTION" banner lines and prepends an
extra leading MSN-number column to every data row; both quirks are handled
below rather than assumed universal.

**Known source-file data quirk**: `pdfplumber.extract_text()` mangles the
column-header line and, on an irregular subset of rows, the free-text
description/vendor portion, into letter-interleaved noise -- e.g. a
DESCRIPTION that should read "REMOVE PRIMARY HEAT EXCHANGERS FOR CLEANING."
sometimes comes back as "A RI ER M C OO VN ED MIT AIO INN HIN EG A TP A EC
XK C HANGERS FOR CLEANING." on some rows of the very same task, while
appearing clean on others. This looks like a text-layer/overlay quirk in
the source PDFs, not a Cypher bug, and it is NOT confined to the header --
a handful of rows even have their WORK_TYPE or ZONE token scrambled the
same way. Given that, this parser does not attempt to un-scramble text: it
anchors only on tokens that are reliably clean across the corpus (the
leading MPD task code, a PART_NUMBER/SERIAL_NUMBER pair, and the dates that
follow them) and folds everything else -- WORK_TYPE/ZONE included, when
garbled -- into best-effort fields rather than guessing a split.

Row shape (single physical line; wrapped continuation lines above/below,
e.g. a component-group heading like "AIR CONDITIONING PACK" or a wrapped
tail like "RESTORATION" on its own line, are not chased -- same tradeoff
mpd_hard_time_list.py documents for its own wrap layout)::

    213100-08-1 RESTORATION 262 <description...> Nord- Micro 9024-15704-2 9932111 1-Jan-99 27-Aug-99 210 50000 210 50000 27-Aug-99 0 20-Feb-17 50000

Anchor sequence, left to right:

  1. MPD_TASK_NO -- `NNNNNN-XX-N` (middle group is usually 2 digits, but a
     handful of engine-LLP-referred rows use an alpha code instead, e.g.
     "722100-C1-1"); this is the row anchor, matched against every line.
     One sample file prefixes each data row with an extra leading MSN
     column before the task code -- detected generically (first token
     isn't a task code but the second token is) rather than hard-coded to
     any particular MSN value.
  2. WORK_TYPE -- closed-ish vocabulary (RESTORATION, Cleaning, HST,
     Overhaul, Discard, Replacement, Test, Weight, and the two-word
     Leak/Capacity/Functional/Workshop "... Check" forms seen in the
     corpus). Matched against the vocabulary first; a token that doesn't
     match anything known (the rare fully-garbled case, e.g. WORK_TYPE
     itself scrambled to "WO CR HK ES CH KOP" for "Workshop Check") is
     still captured as one best-effort token rather than dropped.
  3. ZONE -- the next single token, taken as-is (garbled/quoted zone
     suffixes like `841"FR"` or a scrambled "2 31 rd0" split are common
     enough that only the first token is trusted; anything past it folds
     into DESCRIPTION).
  4. DESCRIPTION -- everything between ZONE and the PART_NUMBER/SERIAL_
     NUMBER pair, kept as one raw best-effort string (this also swallows
     the Vendor name, which cannot be reliably separated from a garbled
     description column).
  5. PART_NUMBER / SERIAL_NUMBER -- the two tokens immediately before the
     first D-Mon-YY-shaped date on the line. Rows with no date at all
     (life-vest/life-raft SHEET-number rows, engine-LLP "REFER TO ENGINE
     LLP" rows) have no reliable PN/SN pair and are left blank rather than
     guessed.
  6. MANUFACTURE_DATE / INSTALL_DATE -- when two date-shaped tokens sit
     back to back right after the PN/SN pair, the first is treated as
     manufacture date and the second as install date (matches the header's
     "Manufacture ... Installation" column pair); when only one date-shaped
     token is present, it is INSTALL_DATE and MANUFACTURE_DATE is blank.
  7. STATUS_TRAIL -- every token after that: the threshold/interval/life-
     limit numeric columns. Their count and left/right alignment shifts
     row to row (a blank threshold cell isn't padded), so -- same call
     mpd_hard_time_list.py and hard_time_component_status_mpd_task.py make
     for their own trailing columns -- this is kept as one unparsed string
     rather than mis-sliced into named cells.

Corpus: a small cluster of files sharing this exact header/column layout,
filed under two report-title variants ("CONTROLLED ITEMS LIST" and "SAFETY
EQUIPMENTS") that are the same underlying export with a different content
filter, not different formats.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.ht_variants._base import merged_rules

NAME = "AL Development Division Controlled Items List (MPD Task)"
SIGNATURES = [
    "MPD TASK Work Type ZONE",
    "AL DEVELOPMENT DIVISION",
]
CANONICAL_COLUMNS = [
    "MPD_TASK_NO",
    "WORK_TYPE",
    "ZONE",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "MANUFACTURE_DATE",
    "INSTALL_DATE",
    "STATUS_TRAIL",
]
_OVERRIDES = {
    "WORK_TYPE":         {"allow_empty": True},
    # ZONE doubles as a component-position "designation" in this format's
    # merged "ZONE DESIGNAION" header column -- legitimate values include
    # plain ATA zone numbers (e.g. "262") *and* non-numeric position labels
    # (e.g. "AFT", "N1", "3L", `841"FR"`), so the global numeric-only ZONE
    # pattern would false-flag most of this variant's real data. Loosened
    # to accept any short alphanumeric token (with the quote/period
    # punctuation this format's labels carry) instead.
    "ZONE":              {"pattern": r"^[A-Za-z0-9][A-Za-z0-9\"'.]*$", "allow_empty": True},
    "DESCRIPTION":       {"allow_empty": True},
    "SERIAL_NUMBER":     {"allow_empty": True},
    "MANUFACTURE_DATE":  {"pattern": r"^\d{1,2}[-/][A-Za-z]{3,9}[-/]\d{2,4}$", "allow_empty": True},
    "INSTALL_DATE":      {"pattern": r"^\d{1,2}[-/][A-Za-z]{3,9}[-/]\d{2,4}$", "allow_empty": True},
    "STATUS_TRAIL":      {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_TASK_RE = re.compile(r"^\d{6}-[A-Z0-9]{1,3}-\d{1,2}$")
_DATE_RE = re.compile(r"^\d{1,2}[-/][A-Za-z]{3,9}[-/]\d{2,4}$")

# Multi-word WORK_TYPE values: first-word -> requires a following "Check".
_WORK_TYPE_MULTI_FIRST = {"leak", "capacity", "functional", "workshop"}
# Single-token WORK_TYPE vocabulary (case-insensitive).
_WORK_TYPE_SINGLE = {
    "restoration", "cleaning", "replacement", "hst", "overhaul",
    "charging", "discard", "test", "weight",
}


def _match_work_type(tokens: list[str], i: int) -> tuple[str, int]:
    if (i + 1 < len(tokens) and tokens[i].lower() in _WORK_TYPE_MULTI_FIRST
            and tokens[i + 1].lower() == "check"):
        return f"{tokens[i]} {tokens[i + 1]}", i + 2
    if i < len(tokens) and tokens[i].lower() in _WORK_TYPE_SINGLE:
        return tokens[i], i + 1
    if i < len(tokens):
        # Unknown/garbled work-type token -- best-effort single token
        # rather than guessing further (see module docstring).
        return tokens[i], i + 1
    return "", i


def _parse_line(line: str) -> dict | None:
    toks = line.split()
    if not toks:
        return None
    start = 0
    if not _TASK_RE.match(toks[0]):
        # Some pages prefix every data row with an extra leading MSN column.
        if len(toks) > 1 and _TASK_RE.match(toks[1]):
            start = 1
        else:
            return None
    task_no = toks[start]
    i = start + 1
    work_type, i = _match_work_type(toks, i)
    zone = toks[i] if i < len(toks) else ""
    if zone:
        i += 1
    rest = toks[i:]

    date_idx = next((k for k, t in enumerate(rest) if _DATE_RE.match(t)), None)
    if date_idx is None:
        return {
            "MPD_TASK_NO": task_no,
            "WORK_TYPE": work_type,
            "ZONE": zone,
            "DESCRIPTION": " ".join(rest),
            "PART_NUMBER": "",
            "SERIAL_NUMBER": "",
            "MANUFACTURE_DATE": "",
            "INSTALL_DATE": "",
            "STATUS_TRAIL": "",
        }

    pn_i, sn_i = date_idx - 2, date_idx - 1
    part_number = rest[pn_i] if pn_i >= 0 else ""
    serial_number = rest[sn_i] if sn_i >= 0 else ""
    description = " ".join(rest[:max(pn_i, 0)])

    if date_idx + 1 < len(rest) and _DATE_RE.match(rest[date_idx + 1]):
        mfg_date = rest[date_idx]
        install_date = rest[date_idx + 1]
        trail = rest[date_idx + 2:]
    else:
        mfg_date = ""
        install_date = rest[date_idx]
        trail = rest[date_idx + 1:]

    return {
        "MPD_TASK_NO": task_no,
        "WORK_TYPE": work_type,
        "ZONE": zone,
        "DESCRIPTION": description,
        "PART_NUMBER": part_number,
        "SERIAL_NUMBER": serial_number,
        "MANUFACTURE_DATE": mfg_date,
        "INSTALL_DATE": install_date,
        "STATUS_TRAIL": " ".join(trail),
    }


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            for line in text.splitlines():
                rec = _parse_line(line)
                if rec is not None:
                    rec["_page"] = page_num
                    records.append(rec)
    return records
