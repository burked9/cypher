"""ESN <n> Disc Sheet — CFM56-7B engine disc/rotor LLP tracking sheet.

Title line reads ``ESN <esn> Disc Sheet``. This is a single dense table per
engine position: one row per rotating LLP (disc, spool, shaft, seal, etc.),
plus a header info-block above the table carrying aircraft registration,
ESN, engine type, a handful of TSN/CSN totals (aircraft and engine, "since
last shop visit" pairs included), a "Lowest Cycles Remaining" headline
figure, and MFG/LSV/MRO dates. Header block example, values genericized::

    ESN <esn> Disc Sheet
    A/C Reg # <reg>                          Date of install
    POS. # <n> Disc Sheet Date <date>
    Engine <esn>              Delivery Date <date>
    Lowest Cycles Remaining <csn>
    A/C TSN <hh:mm> Eng T.S.N. <tsn> T.L.S.V. <tsn> T.S.L.S.V. <tsn>
    A/C CSN <csn>   Eng C.S.N. <csn> C.L.S.V. <csn> C.S.L.S.V. <csn>
    Engine Type <model> MFG Date        LSV Date <date> LSV MRO

("T.L.S.V." / "T.S.L.S.V." = TSN at/since Last Shop Visit; "C.L.S.V." /
"C.S.L.S.V." = the CSN equivalents. MFG Date and LSV MRO are frequently
blank on real files -- captured empty rather than guessed.)

Body table header (2-3 physical header lines, reconstructed)::

    -7B24 -7B26 -7B27/B1 Misc                      -7B24    -7B26   -7B27/B1
                              Engine Life
              Disc Life at Fit
    Description Part Number Serial Number TSN CSN  at Disc Fit  Life Life Life  % Life Remaining
                                    (Cycles)        Limit Used Limit Used Limit Used Limit Used
                                    (Cycles)                     Remaining Remaining Remaining

Row grain: one row per part. Columns, left to right: DESCRIPTION,
PART_NUMBER, SERIAL_NUMBER, TSN, CSN, then two adjacent cycle columns whose
headers stack across 1-3 physical header lines each -- "Disc Life at Fit"
(the part's own cycles at the time it was fitted into this position) and,
separately, "Engine Life at Disc Fit (Cycles)" (the engine's cycles at that
same moment) -- then 4 Limit/Used pairs (one per engine rating variant:
-7B24, -7B26, -7B27/B1, and a 4th "Misc" pair that is usually blank), then
3 "<rating> Life Remaining" columns (one each for -7B24/-7B26/-7B27B1;
"Misc" has no remaining column) and a final "% Life Remaining".

Column layout is x-position bin based (`extract_words`, bucketed by x0),
the same technique as `ht_variants/time_controlled_components_status.py`.
Row anchor: the DESCRIPTION column's x-range (this is the only column that
ever starts a physical line for a data row -- column headers and the page
footer never fall in that x-range past the header block, so gating on
`top` past the header band is enough to avoid false anchors).

PDF-extraction quirk this format needs handled explicitly: several rows'
trailing numeric columns visibly wrap onto *additional* physical lines
below the row's main (anchor) line -- e.g. a row's Description/Part
Number/Serial Number/CSN/Remaining-x2 print on the anchor line, its TSN and
Limit/Used values print on a 2nd physical line roughly half a normal row's
height below, and its Disc-Life-at-Fit/Engine-Life-at-Disc-Fit/%-Remaining
values print on a 3rd. Confirmed against the real sample file: every value
belonging to one such wrapped row lands in a column bin that is otherwise
empty *for that row* -- no bin is ever written to by two different physical
lines of the same row -- so merging every physical line up to (but not
including) the next DESCRIPTION-anchored line into one record is
unambiguous here, unlike the nearest-line-by-vertical-distance heuristic
`time_controlled_components_status.py` needs for its genuinely ragged
overflow. Every column bin below was measured directly against the real
sample file's word coordinates (not guessed), and every one of that file's
data rows was manually checked to land, in full, inside exactly one bin
per value -- so nothing here needed folding into a STATUS_TRAIL catch-all.

The "Misc" Limit/Used pair and the 4th rating column some competing sheets
carry are captured as their own LIMIT_MISC/USED_MISC columns; they are
blank on most rows in the real sample (no remaining-cycles/percentage
column exists for "Misc" at all -- confirmed against the header, not an
extraction gap), which the column rules allow.
"""
from __future__ import annotations

import re

import pdfplumber

from sheet_types.llp_variants._base import merged_rules

NAME = "ESN Disc Sheet"
SIGNATURES = [
    "Disc Sheet",
    "Lowest Cycles Remaining",
]

CANONICAL_COLUMNS = [
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "TSN",
    "CSN",
    "DISC_LIFE_AT_FIT_CYCLES",
    "ENGINE_LIFE_AT_DISC_FIT_CYCLES",
    "LIMIT_7B24",
    "USED_7B24",
    "LIMIT_7B26",
    "USED_7B26",
    "LIMIT_7B27B1",
    "USED_7B27B1",
    "LIMIT_MISC",
    "USED_MISC",
    "REMAINING_7B24",
    "REMAINING_7B26",
    "REMAINING_7B27B1",
    "PCT_LIFE_REMAINING",
    # Header metadata, stamped on every row.
    "AIRCRAFT_REG",
    "ESN",
    "POSITION",
    "ENGINE_TYPE",
    "DISC_SHEET_DATE",
    "DELIVERY_DATE",
    "LOWEST_CYCLES_REMAINING",
    "AC_TSN",
    "AC_CSN",
    "ENGINE_TSN",
    "ENGINE_CSN",
    "ENGINE_TSN_LSV",
    "ENGINE_CSN_LSV",
    "ENGINE_TSN_SINCE_LSV",
    "ENGINE_CSN_SINCE_LSV",
    "MFG_DATE",
    "LSV_DATE",
    "MRO_DATE",
]

_CYCLE_RULE = {"pattern": r"^(\d+|N/L)$", "allow_empty": True}
_PCT_RULE = {"pattern": r"^\d{1,3}\.\d{2}%$", "allow_empty": True}
_DATE_RULE = {"pattern": r"^\d{2}\.\d{2}\.\d{4}$", "allow_empty": True}
_OVERRIDES = {
    "TSN": _CYCLE_RULE,
    "CSN": _CYCLE_RULE,
    "DISC_LIFE_AT_FIT_CYCLES": _CYCLE_RULE,
    "ENGINE_LIFE_AT_DISC_FIT_CYCLES": _CYCLE_RULE,
    "LIMIT_7B24": _CYCLE_RULE, "USED_7B24": _CYCLE_RULE,
    "LIMIT_7B26": _CYCLE_RULE, "USED_7B26": _CYCLE_RULE,
    "LIMIT_7B27B1": _CYCLE_RULE, "USED_7B27B1": _CYCLE_RULE,
    "LIMIT_MISC": _CYCLE_RULE, "USED_MISC": _CYCLE_RULE,
    "REMAINING_7B24": _CYCLE_RULE,
    "REMAINING_7B26": _CYCLE_RULE,
    "REMAINING_7B27B1": _CYCLE_RULE,
    "PCT_LIFE_REMAINING": _PCT_RULE,
    "ESN": {"pattern": r"^\d{4,8}$", "allow_empty": True},
    "AIRCRAFT_REG": {"pattern": r"^[A-Z0-9\-]{4,8}$", "uppercase": True, "allow_empty": True},
    "POSITION": {"pattern": r"^\S+$", "allow_empty": True},
    "ENGINE_TYPE": {"pattern": r"^CFM56-7B\w*$", "uppercase": True, "allow_empty": True},
    "DISC_SHEET_DATE": _DATE_RULE,
    "DELIVERY_DATE": _DATE_RULE,
    "MFG_DATE": _DATE_RULE,
    "LSV_DATE": _DATE_RULE,
    "MRO_DATE": _DATE_RULE,
    "LOWEST_CYCLES_REMAINING": {"pattern": r"^\d+$", "allow_empty": True},
    "AC_TSN": {"pattern": r"^\d+:\d{2}$", "allow_empty": True},
    "AC_CSN": {"pattern": r"^\d+$", "allow_empty": True},
    "ENGINE_TSN": {"pattern": r"^\d+$", "allow_empty": True},
    "ENGINE_CSN": {"pattern": r"^\d+$", "allow_empty": True},
    "ENGINE_TSN_LSV": {"pattern": r"^\d+$", "allow_empty": True},
    "ENGINE_CSN_LSV": {"pattern": r"^\d+$", "allow_empty": True},
    "ENGINE_TSN_SINCE_LSV": {"pattern": r"^\d+$", "allow_empty": True},
    "ENGINE_CSN_SINCE_LSV": {"pattern": r"^\d+$", "allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Column x-position bins (PDF points), measured directly against the real
# sample file's word coordinates. DESCRIPTION doubles as the row anchor:
# any physical line past the header band that has a word starting in this
# bin begins a new row.
_BINS = [
    (0, 235, "DESCRIPTION"),
    (235, 343, "PART_NUMBER"),
    (343, 460, "SERIAL_NUMBER"),
    (460, 530, "TSN"),
    (530, 590, "CSN"),
    (590, 685, "DISC_LIFE_AT_FIT_CYCLES"),
    (685, 785, "ENGINE_LIFE_AT_DISC_FIT_CYCLES"),
    (785, 850, "LIMIT_7B24"),
    (850, 935, "USED_7B24"),
    (935, 1010, "LIMIT_7B26"),
    (1010, 1065, "USED_7B26"),
    (1065, 1135, "LIMIT_7B27B1"),
    (1135, 1180, "USED_7B27B1"),
    (1180, 1230, "LIMIT_MISC"),
    (1230, 1285, "USED_MISC"),
    (1285, 1355, "REMAINING_7B24"),
    (1355, 1430, "REMAINING_7B26"),
    (1430, 1505, "REMAINING_7B27B1"),
    (1505, 1650, "PCT_LIFE_REMAINING"),
]
# Numeric bins are digit-group fragments of one number split by a literal
# thousands-separator space in the source PDF (e.g. "18" + "628" -> 18628),
# so they join with no separator; DESCRIPTION is real multi-word text and
# joins with a space.
_SPACE_JOIN_FIELDS = {"DESCRIPTION"}

# Column headers and the page footer sit above this y-position on the real
# sample file; the data table itself starts below it. Gating on this keeps
# metadata-block lines (which do have words in the DESCRIPTION x-range,
# e.g. "A/C Reg #") from being mistaken for row anchors.
_DATA_TOP_MIN = 380.0
_ANCHOR_MAX_X = 235.0
# The "Page X of Y" footer sits well to the right (observed x0 ~1511 on the
# real sample), inside the PCT_LIFE_REMAINING bin -- without this filter it
# silently gets appended onto whichever row was last seen, since it isn't a
# DESCRIPTION-anchored line either.
_FOOTER_RE = re.compile(r"^page\s+\d+\s+of\s+\d+$", re.I)


def _bin_for(x0: float) -> str | None:
    for lo, hi, field in _BINS:
        if lo <= x0 < hi:
            return field
    return None


def _group_lines(words: list[dict]) -> list[dict]:
    ws = sorted(words, key=lambda w: (w["top"], w["x0"]))
    lines: list[dict] = []
    for w in ws:
        if lines and abs(w["top"] - lines[-1]["top"]) <= 2.5:
            lines[-1]["words"].append(w)
            lines[-1]["top"] = (lines[-1]["top"] + w["top"]) / 2
        else:
            lines.append({"top": w["top"], "words": [w]})
    for line in lines:
        line["words"].sort(key=lambda w: w["x0"])
    return lines


def _is_footer(line: dict) -> bool:
    text = " ".join(w["text"] for w in line["words"])
    return bool(_FOOTER_RE.match(text.strip()))


def _is_anchor(line: dict) -> bool:
    if line["top"] < _DATA_TOP_MIN:
        return False
    return any(w["x0"] < _ANCHOR_MAX_X for w in line["words"])


def _new_row() -> dict:
    return {col: "" for col in CANONICAL_COLUMNS}


def _apply_line(row: dict, line: dict) -> None:
    buckets: dict[str, list[str]] = {}
    for w in line["words"]:
        field = _bin_for(w["x0"])
        if field is None:
            continue
        buckets.setdefault(field, []).append(w["text"])
    for field, texts in buckets.items():
        sep = " " if field in _SPACE_JOIN_FIELDS else ""
        frag = sep.join(texts)
        existing = row.get(field, "")
        row[field] = f"{existing}{sep}{frag}" if existing else frag


def _num(raw: str | None) -> str:
    if not raw:
        return ""
    return re.sub(r"[ ,]", "", raw).strip()


def _parse_header_metadata(text: str) -> dict:
    meta: dict[str, str] = {}

    def grab(pattern: str, key: str, collapse: bool = False):
        m = re.search(pattern, text)
        if not m:
            return
        val = m.group(1).strip()
        meta[key] = _num(val) if collapse else val

    grab(r"ESN\s+(\d+)\s+Disc Sheet", "ESN")
    grab(r"A/C\s*Reg\s*#\s*(.+?)\s+Date", "AIRCRAFT_REG")
    grab(r"POS\.\s*#\s*(\S+)\s+Disc Sheet Date", "POSITION")
    grab(r"Disc Sheet Date\s*([\d.]+)", "DISC_SHEET_DATE")
    grab(r"Delivery Date\s*([\d.]+)", "DELIVERY_DATE")
    grab(r"Lowest Cycles Remaining\s*([\d ]+?)(?=\s*(?:A/C|$))", "LOWEST_CYCLES_REMAINING", collapse=True)
    grab(r"A/C\s*TSN\s*(\d+:\d+)", "AC_TSN")
    grab(r"A/C\s*CSN\s*([\d ]+?)(?=\s*Eng)", "AC_CSN", collapse=True)
    grab(r"Eng\s*T\.S\.N\.\s*([\d ]+?)(?=\s*T\.L\.S\.V\.)", "ENGINE_TSN", collapse=True)
    grab(r"Eng\s*C\.S\.N\.\s*([\d ]+?)(?=\s*C\.L\.S\.V\.)", "ENGINE_CSN", collapse=True)
    grab(r"T\.L\.S\.V\.\s*([\d ]+?)(?=\s*T\.S\.L\.S\.V\.)", "ENGINE_TSN_LSV", collapse=True)
    grab(r"C\.L\.S\.V\.\s*([\d ]+?)(?=\s*C\.S\.L\.S\.V\.)", "ENGINE_CSN_LSV", collapse=True)
    # These two are always the last field on their header line -- the
    # trailing value is followed by a newline (or true end of text), not
    # by another labelled field, so "$" alone (without re.MULTILINE) never
    # matches since this text isn't the last line of the page. Anchor on
    # an explicit newline-or-end lookahead instead.
    grab(r"T\.S\.L\.S\.V\.\s*([\d ]+?)(?=\n|$)", "ENGINE_TSN_SINCE_LSV", collapse=True)
    grab(r"C\.S\.L\.S\.V\.\s*([\d ]+?)(?=\n|$)", "ENGINE_CSN_SINCE_LSV", collapse=True)
    grab(r"Engine Type\s*([A-Z0-9\-]+)", "ENGINE_TYPE")
    grab(r"MFG Date\s*([\d.]{6,10})\s*LSV Date", "MFG_DATE")
    grab(r"LSV Date\s*([\d.]+)", "LSV_DATE")
    grab(r"LSV MRO\s*([\d.]+)(?=\n|$)", "MRO_DATE")

    # "A/C Reg # <reg-prefix>- <reg-suffix>" -- the PDF's text layer inserts
    # a stray space after the reg's hyphen (confirmed on the real sample
    # file); collapse all internal whitespace rather than leave it (real
    # registrations never contain spaces).
    if "AIRCRAFT_REG" in meta:
        meta["AIRCRAFT_REG"] = re.sub(r"\s+", "", meta["AIRCRAFT_REG"])

    for key in ("ESN", "POSITION", "AIRCRAFT_REG", "ENGINE_TYPE",
                "DISC_SHEET_DATE", "DELIVERY_DATE", "LOWEST_CYCLES_REMAINING",
                "AC_TSN", "AC_CSN", "ENGINE_TSN", "ENGINE_CSN",
                "ENGINE_TSN_LSV", "ENGINE_CSN_LSV",
                "ENGINE_TSN_SINCE_LSV", "ENGINE_CSN_SINCE_LSV",
                "MFG_DATE", "LSV_DATE", "MRO_DATE"):
        meta.setdefault(key, "")
    return meta


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        full_text = "\n".join((p.extract_text() or "") for p in pdf.pages)
        meta = _parse_header_metadata(full_text)

        for page_num, page in enumerate(pdf.pages, start=1):
            words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
            if not words:
                continue
            lines = [ln for ln in _group_lines(words)
                     if ln["top"] >= _DATA_TOP_MIN and not _is_footer(ln)]
            if not lines:
                continue

            rows: list[dict] = []
            current: dict | None = None
            for line in lines:
                if _is_anchor(line):
                    current = _new_row()
                    rows.append(current)
                if current is None:
                    # Stray data-band line with no anchor seen yet on this
                    # page (shouldn't happen on the real sample -- the first
                    # data line is always an anchor -- but skip defensively
                    # rather than crash or misattribute).
                    continue
                _apply_line(current, line)

            for row in rows:
                if not row["DESCRIPTION"]:
                    continue
                row["_page"] = page_num
                row.update(meta)
                records.append(row)
    return records
