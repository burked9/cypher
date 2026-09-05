""""<facility> sn <msn> OCCM Component" — facility/MSN-headed OCCM status
report with a real (native) text layer, no OCR needed. Confirmed via a
direct pdfplumber pass across every page of one real sample file (25 pages,
~1079 data rows).

Header block (repeats verbatim at the top of every page)::

    <facility> sn <msn> OCCM Component
    TAH=<tah H:MM> TAC=<tac, apostrophe-thousands> as for <DD.Mon.YYYY>
    ATA PART NO. SERIAL NO. DESCRIPTION CON POS. INST-DATE TAH Inst TAC Inst TSI CSI TSN CSN

(the column-header row itself only appears once, on the first page — every
later page repeats just the two metadata lines above it, confirmed directly
across all 25 pages of the real sample).

Structurally close to `occm_list_msn_dotdate.py` (same general shape: an
ATA/PN/SN/DESCRIPTION/CON/POS/INST-DATE row with trailing accumulated-time
columns, and a CON condition-code column in the same slot) but confirmed
distinct in three ways, not merely stylistic:

1. Column order/count: this format's trailing group is six columns --
   TAH Inst, TAC Inst, TSI, CSI, TSN, CSN -- confirmed via the real file's
   own column-header row. `occm_list_msn_dotdate.py`'s trailing group is
   only four -- TAH Inst, TAC Inst, TSN, CSN -- with no TSI/CSI at all.
   Checked directly: no other module's column-header signature contains
   the literal phrase "TAH Inst TAC Inst TSI CSI TSN CSN" (grepped across
   every file in sheet_types/occm_variants/, sheet_types/{occm,ht,llp}.py,
   and sheet_types/{ht,llp}_variants/), so that full line is used as this
   module's sole SIGNATURES entry.
2. CON vocabulary: confirmed by an exhaustive scan of every one of the
   real sample file's ~1079 data rows: IN, IT, MO, NE, OH, RE, SV, TE.
   `occm_list_msn_dotdate.py`'s own confirmed vocabulary (N, R, IT, OH, M,
   S) is a *different* set -- only "IT" and "OH" are shared between the
   two.
3. Date format: INSTALL_DATE (and the header's own "as for" date) here is
   `DD.Mon.YYYY` with a three-letter month abbreviation (e.g. a date shaped
   like `<dd>.<Mon>.<yyyy>`) -- dot-separated but NOT purely numeric.
   `occm_list_msn_dotdate.py`'s dates are purely numeric dot-separated
   (`DD.MM.YYYY`). Confirmed via `sheet_types.occm.detect_variant()` on
   the real sample file: it did not match any existing variant (including
   `occm_list_msn_dotdate.py`) and returned "Unknown" before this module
   existed.

ATA is glued directly onto PART_NUMBER with no separating space on the
first row of a new ATA chapter, and blank (to be forward-filled by the
router's generic `forward_fill_ata` post-process) on every other row --
confirmed directly against the real sample file's 27 ATA chapters, each
appearing exactly once. Plain `extract_text()`/whitespace-tokenizing
cannot reliably separate a glued `<ata><pn>` pair from an all-numeric PN
that itself happens to start with two digits (confirmed: naive prefix
stripping misparses a real PN in the sample file that legitimately starts
with a 2-digit run, e.g. shaped like `<nn>NNN-NN`, as a false ATA+PN
split). This module instead reads `page.extract_words(x_tolerance=0.1)`
(a tight word-split tolerance -- the default tolerance merges the glued
ATA+PN into one token, confirmed directly) and buckets each word by its
x0 position against column boundaries measured from the real file's own
header row, which are identical across every page (confirmed directly).
ATA's own column band never produces a standalone word on continuation
rows -- it is genuinely absent from the underlying content stream, not
merely rendered as whitespace.

POSITION is not always a single token (e.g. two-word shapes like `<n>
<side>`, `<side> <fwd/aft>` are common) and is captured as all words whose
x0 falls in its column band, joined with spaces.

A confirmed rendering quirk (real, not corruption introduced by this
module): on a small minority of rows (31 of 1079, ~2.9%) the last
POSITION word is glued directly onto INSTALL_DATE with no separating
space, e.g. a shape like `<pos-tail><dd>.<Mon>.<yyyy>`. Where the trailing
substring cleanly matches the date pattern, this module splits it back
into POSITION-tail + INSTALL_DATE (recovered on 20 of the 31). The
remaining 11 show characters from POSITION and the date genuinely
interleaved at the byte level in the source content stream (confirmed: not
recoverable by any prefix/suffix split -- the two runs occupy overlapping
x-coordinates in the underlying PDF, a real upstream rendering defect).
These are left verbatim in POSITION with INSTALL_DATE blank rather than
guessed at, same convention as corrupted cells in sibling OCCM modules --
`clean_record` flags the resulting blank/malformed cells rather than
silently dropping or fabricating a value.

TAH Inst / TAC Inst / TSI / CSI / TSN / CSN cells are integers, sometimes
carrying an apostrophe thousands separator (e.g. a shape like `NN'NNN`,
confirmed real -- also seen in the header's own TAC figure, "TAC=" followed
by an apostrophe-grouped integer) and/or a colon-suffixed minutes component
(e.g. `NNNNN:NN`, an hours:minutes shape). The literal sentinel "UNKNOWN" is
also confirmed present. Kept loose (pattern-only, no int_range) rather than
strict, same call as `occm_list_msn_dotdate.py`'s own `_LOOSE_NUM_RULE`.

SERIAL_NUMBER carries the literal sentinel "N/A" on a handful of rows
(components with no recorded serial) -- a real value, not a parse failure,
left verbatim.
"""
from __future__ import annotations
import re
from collections import defaultdict

import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "OCCM Component Status (Facility/MSN Header)"
# Deliberately NOT a bare "OCCM Component" substring -- that phrase is also
# a *prefix* of occm_component_list.py's own signature ("OCCM Component
# List"), and SIGNATURES matching is plain substring, not anchored, so a
# bare "OCCM Component" here would risk stealing that module's real files.
# This column-header line is confirmed unique instead (see docstring point
# 1 above for the grep that checked it against every SIGNATURES list in
# sheet_types/{occm,ht,llp}.py and every variant file).
SIGNATURES = [
    "ATA PART NO. SERIAL NO. DESCRIPTION CON POS. INST-DATE TAH Inst TAC Inst TSI CSI TSN CSN",
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
    "TSI",
    "CSI",
    "TSN",
    "CSN",
    # Header metadata -- parsed once per page, stamped onto every row.
    "FACILITY_CODE",
    "MSN",
    "AS_OF_DATE",
    "AC_TAH_ASOF",
    "AC_TAC_ASOF",
]

# TAH/TAC/TSI/CSI/TSN/CSN cells are integers, optionally apostrophe-grouped
# and/or colon-suffixed, or the literal sentinel "UNKNOWN" -- see docstring.
_LOOSE_NUM_RULE = {"pattern": r"^(?:\d+(?:'\d{3})*(?::\d+)?|UNKNOWN|N/A)$"}

_OVERRIDES = {
    # Confirmed closed vocabulary IN/IT/MO/NE/OH/RE/SV/TE (see docstring) --
    # kept as a loose 1-3 uppercase-letter shape rather than a strict enum,
    # same call as occm_list_msn_dotdate.py's own CONDITION override.
    "CONDITION": {"pattern": r"^[A-Z]{1,3}$", "uppercase": True},
    "POSITION": {"pattern": r"^[A-Z0-9#()./\- ]{1,40}$", "uppercase": True,
                 "allow_empty": True},
    "INSTALL_DATE": {"pattern": r"^\d{2}\.[A-Za-z]{3}\.\d{4}$",
                      "allow_empty": True},
    "TAH_AT_INSTALL": _LOOSE_NUM_RULE,
    "TAC_AT_INSTALL": _LOOSE_NUM_RULE,
    "TSI": _LOOSE_NUM_RULE,
    "CSI": _LOOSE_NUM_RULE,
    "TSN": _LOOSE_NUM_RULE,
    "CSN": _LOOSE_NUM_RULE,
    "DESCRIPTION": {"uppercase": True},
    "FACILITY_CODE": {"pattern": r"^[A-Z0-9]{1,10}$", "uppercase": True,
                       "allow_empty": True},
    "MSN": {"pattern": r"^\d+$", "allow_empty": True},
    "AS_OF_DATE": {"pattern": r"^\d{2}\.[A-Za-z]{3}\.\d{4}$",
                   "allow_empty": True},
    "AC_TAH_ASOF": dict(_LOOSE_NUM_RULE, allow_empty=True),
    "AC_TAC_ASOF": dict(_LOOSE_NUM_RULE, allow_empty=True),
}
RULES = merged_rules(_OVERRIDES)

# Column x0 boundaries, measured directly from the real sample file's own
# header row (identical on every page it appears on) via
# `page.extract_words(x_tolerance=0.1)`. Boundaries sit at the midpoint
# between adjacent header word x0 positions, well clear of every observed
# data-word x0 in each band (confirmed directly across the whole file --
# see module docstring).
_COLUMN_BOUNDS = [
    ("ATA", 0, 90),
    ("PART_NUMBER", 90, 160),
    ("SERIAL_NUMBER", 160, 224),
    ("DESCRIPTION", 224, 370),
    ("CONDITION", 370, 410),
    ("POSITION", 410, 450),
    ("INSTALL_DATE", 450, 510),
    ("TAH_AT_INSTALL", 510, 550),
    ("TAC_AT_INSTALL", 550, 590),
    ("TSI", 590, 630),
    ("CSI", 630, 670),
    ("TSN", 670, 710),
    ("CSN", 710, 100_000),
]

_HEADER1_RE = re.compile(
    r"^(?P<facility>\S+)\s+sn\s+(?P<msn>\d+)\s+OCCM Component\s*$",
    re.IGNORECASE,
)
_HEADER2_RE = re.compile(
    r"^TAH=(?P<tah>[\d:]+)\s+TAC=(?P<tac>[\d']+)\s+as for\s+"
    r"(?P<asof>\d{2}\.[A-Za-z]{3}\.\d{4})\s*$",
    re.IGNORECASE,
)
_HEADER_ROW_START = ("ATA", "PART", "NO.")
_FOOTER_RE = re.compile(r"^\d+\s+og\s+\d+$")
# Recovers a POSITION word glued directly onto INSTALL_DATE with no space
# (see docstring) -- captures any leading POSITION-tail text plus the
# trailing clean date.
_DATE_TAIL_RE = re.compile(r"^(?P<prefix>.*?)(?P<date>\d{2}\.[A-Za-z]{3}\.\d{4})$")


def _bucket_for(x0: float) -> str | None:
    for name, lo, hi in _COLUMN_BOUNDS:
        if lo <= x0 < hi:
            return name
    return None


def _normalize_thousands(raw: str) -> str:
    """Strip apostrophe thousands separators (e.g. a shape like `NN'NNN`)
    for a clean numeric value. Confirmed real formatting quirk on the
    header's TAC figure and on many per-row TAH/TAC/TSI/CSI/TSN/CSN cells,
    not corruption."""
    return raw.replace("'", "")


def _parse_header(line: str) -> dict:
    m = _HEADER1_RE.match(line.strip())
    if m:
        return {"FACILITY_CODE": m.group("facility"), "MSN": m.group("msn")}
    m = _HEADER2_RE.match(line.strip())
    if m:
        return {
            "AC_TAH_ASOF": m.group("tah"),
            "AC_TAC_ASOF": _normalize_thousands(m.group("tac")),
            "AS_OF_DATE": m.group("asof"),
        }
    return {}


def _parse_row_words(words: list[dict]) -> dict[str, list[str]]:
    rec: dict[str, list[str]] = defaultdict(list)
    for w in words:
        b = _bucket_for(w["x0"])
        if b is not None:
            rec[b].append(w["text"])
    return rec


def _recover_glued_date(rec: dict[str, list[str]]) -> None:
    """If INSTALL_DATE is missing but POSITION's last word ends with a
    clean date suffix glued on with no space, split it back out (see
    docstring for the confirmed rate and the unrecoverable minority)."""
    if rec.get("INSTALL_DATE") or not rec.get("POSITION"):
        return
    toks = rec["POSITION"]
    m = _DATE_TAIL_RE.match(toks[-1])
    if not m:
        return
    prefix = m.group("prefix")
    new_toks = toks[:-1] + ([prefix] if prefix else [])
    rec["POSITION"] = new_toks
    rec["INSTALL_DATE"] = [m.group("date")]


def _parse_data_line(words: list[dict], page_num: int, header_meta: dict) -> dict | None:
    rec = _parse_row_words(words)
    if "PART_NUMBER" not in rec:
        return None
    _recover_glued_date(rec)

    out: dict = {c: "" for c in CANONICAL_COLUMNS}
    for col in ("ATA", "PART_NUMBER", "SERIAL_NUMBER", "DESCRIPTION",
                "CONDITION", "POSITION", "INSTALL_DATE", "TAH_AT_INSTALL",
                "TAC_AT_INSTALL", "TSI", "CSI", "TSN", "CSN"):
        if col in rec:
            out[col] = " ".join(rec[col])
    out.update(header_meta)
    out["_page"] = page_num
    return out


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    header_meta: dict = {}
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            words = page.extract_words(x_tolerance=0.1)
            rows: dict[int, list[dict]] = defaultdict(list)
            for w in words:
                rows[round(w["top"])].append(w)
            for top in sorted(rows.keys()):
                ws = sorted(rows[top], key=lambda w: w["x0"])
                texts = [w["text"] for w in ws]
                if not texts:
                    continue
                joined = " ".join(texts)
                meta = _parse_header(joined)
                if meta:
                    header_meta.update(meta)
                    continue
                if tuple(texts[:3]) == _HEADER_ROW_START:
                    continue
                if _FOOTER_RE.match(joined):
                    continue
                rec = _parse_data_line(ws, page_num, header_meta)
                if rec is not None:
                    records.append(rec)
    return records
