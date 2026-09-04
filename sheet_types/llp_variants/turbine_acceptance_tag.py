"""Honeywell "TURBINE ACCEPTANCE TAG & TRACEABILITY INPUT" -- a one-page APU
(auxiliary power unit, e.g. GTCP331 series) traceability/life-limits tag
issued at APU acceptance/overhaul.

Header block (values genericized -- see module docstring conventions)::

    TURBINE ACCEPTANCE TAG & TRACEABILITY INPUT
    'ART NO: <apu_pn> SERIAL NO.: <apu_sn> CUSTOMER: <operator>
    n440DEL: <model> SERIES :<s1> <s2> DATE: <dd> <MON> <yyyy>
    WO NO.: <wo> TSR/rSN: <tsr> /<tsn> CSR/CSN:<c1> <c2> /<csn>

The apostrophe/garbled-prefix labels ("'ART NO:" for "PART NO:", "n440DEL:"
for "MODEL:") are confirmed real on the one known source file -- pdfplumber
extracts real (non-blank) text, but it carries the same kind of systematic
character corruption seen elsewhere in this project's Honeywell-adjacent
corpus (stray "^"/"'"/leading garbage glyphs). Header fields are therefore
matched on the stable *suffix* of each label ("DEL:" for MODEL, "ART NO:"
for PART NO) rather than an exact label string, and are anchored away from
the table's own "PART NO." / "SERIAL NO." column headers by requiring the
":" + inline value shape the header line has and the column-header line
does not.

"SERIES :<s1> <s2>" and "CSR/CSN:<c1> <c2> /<csn>" each split what should be
one short value across two separate whitespace-joined tokens (confirmed:
the header's flowed text literally reads "SERIES :7 3" and "CSR/CSN:0 0
/<csn>" on the sample) -- both are reassembled by concatenating the two
digit tokens rather than treated as two fields.

Body: two distinct row-blocks under one form.

  1. The life-limited-parts table proper (columns: DESCRIPTION, PART NO.,
     SERIAL NO., LOT NO, TSN, CSN, TSI, CSI, LIFE LIMITS) -- this is what
     this module extracts.
  2. A following "APU - ACCESSORIES RECORD" block (columns: DESCRIPTION,
     PART NO., SERIAL NO., SERIES, CHG NOS, REMARKS) -- accessory
     identification records with no TSN/CSN/life-limit data of any kind.
     Deliberately OUT OF SCOPE for this module: an LLP-status sheet type
     tracks parts against a life limit, and this block carries none --
     folding it into CANONICAL_COLUMNS would mean padding every one of its
     rows with N/A life-tracking fields that were never on the form to
     begin with, which is a worse shape than simply not extracting them
     here. (A future OCCM/HT-side "APU accessories" variant could pick
     this block up on its own terms if this data class is ever needed.)

Row grain (LLP table only), confirmed directly against every row of the one
known source file via word-position inspection (not just a naive text
dump, which visually interleaves sub-line fragments out of top-to-bottom
row order in a couple of cases -- see below): one row per life-limited
part, columns left to right DESCRIPTION | PART NO. | SERIAL NO. | LOT NO |
TSN | CSN | TSI | CSI | LIFE LIMITS. "LIFE LIMITS" is either a bare "NA"
(no life limit -- e.g. some impellers) or "<n>,<nnn> CYC". A dash "-"
anywhere in TSI/CSI/LOT NO means "no data for this field", not zero.

Two confirmed layout quirks in the extracted text, handled explicitly
rather than assumed away:

  - LOT NO is almost always blank and, when blank, prints as a lone "-" on
    its OWN physical line just below the row's other fields (not inline
    with them) -- e.g. a row's DESC/PN/SN/TSN/CSN/TSI/CSI/LIFE all land on
    one text line, immediately followed by a line containing only "-".
    That trailing "-" is folded back into the preceding row's LOT_NO,
    rather than misread as a new (blank-description) row.
  - On the sample file, one row's CSN/TSI/CSI/LIFE-LIMITS block is emitted
    on its own physical line ABOVE that row's own DESCRIPTION/PART
    NO./SERIAL NO./TSN line (confirmed via pdfplumber word y-positions --
    genuinely out of visual top-to-bottom order, not a mis-split of one
    line). That orphaned line has no DESCRIPTION/PART-NO of its own to
    anchor it, so it cannot be identified as "belonging" to any row until
    the FOLLOWING line turns out to be a row with those same fields still
    empty; it is buffered and merged into the next row's first empty
    trailing slots (in TSN/CSN/TSI/CSI order) rather than either being
    silently dropped or misattributed to the row before it. Confirmed:
    exactly one such orphan line occurs in the known source file, and the
    merge lands it on the correct row (its DESCRIPTION and PART NO. are
    physically nearest to, and immediately follow, the orphan line).
    Stray single/double-letter OCR-noise tokens riding along on an orphan
    line (seen on the sample as trailing garbage after a genuine "NA") are
    dropped -- they match no column shape and aren't data, unlike the
    numeric/dash/NA tokens around them.

Per this project's "never guess a wrong split" convention, a data row whose
trailing token count doesn't cleanly resolve to the expected TSN/CSN/TSI/CSI
(+ optional LOT NO) shape is NOT force-fit: any left-over tokens are kept
verbatim in STATUS_TRAIL (same convention/name as
llp_variants/lan_engine_control_fleet_llp.py) instead of being dropped or
guessed into a field. Likewise a LOT_NO value that isn't a plain digit
string or "-" (an OCR-corrupted stray character was observed taking that
slot on the sample file) is kept as extracted and left to the RULES
pattern check to flag, rather than silently accepted or discarded.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.llp_variants._base import merged_rules

NAME = "Turbine Acceptance Tag & Traceability Input"
SIGNATURES = [
    "TURBINE ACCEPTANCE TAG",
]

CANONICAL_COLUMNS = [
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "LOT_NO",
    "TSN",
    "CSN",
    "TSI",
    "CSI",
    "LIFE_LIMIT",
    "STATUS_TRAIL",
    # Header (APU-level) metadata -- same on every row of a given file.
    # Prefixed APU_/TAG_ throughout so it can never be confused with the
    # per-row PART_NUMBER/SERIAL_NUMBER/TSN/CSN columns above.
    "APU_PART_NUMBER",
    "APU_SERIAL_NUMBER",
    "APU_MODEL",
    "APU_SERIES",
    "TAG_DATE",
    "WORK_ORDER",
    "CUSTOMER",
    "APU_TSR",
    "APU_TSN",
    "APU_CSR",
    "APU_CSN",
]

_NUM_OR_DASH = {"pattern": r"^(\d+|-)$", "allow_empty": True}
_OVERRIDES = {
    "LOT_NO": _NUM_OR_DASH,
    "TSN": {"pattern": r"^(\d+|UNK|-)$", "allow_empty": True},
    "CSN": {"pattern": r"^(\d+|UNK|-)$", "allow_empty": True},
    "TSI": {"pattern": r"^-?$", "allow_empty": True},
    "CSI": {"pattern": r"^-?$", "allow_empty": True},
    "LIFE_LIMIT": {"pattern": r"^(NA|[\d,]+\s?CYC)$", "allow_empty": True},
    "STATUS_TRAIL": {"allow_empty": True},
    "APU_PART_NUMBER":   {"pattern": r"^[A-Z0-9\-]+$", "uppercase": True},
    "APU_SERIAL_NUMBER": {"pattern": r"^[A-Z0-9\-]+$", "uppercase": True},
    "APU_MODEL":         {"pattern": r"^[A-Z0-9\-]+$", "uppercase": True},
    "APU_SERIES":        {"pattern": r"^\d{1,3}$", "allow_empty": True},
    "TAG_DATE":          {"pattern": r"^\d{1,2}\s[A-Z]{3}\s\d{4}$", "allow_empty": True},
    "WORK_ORDER":        {"pattern": r"^\d+$", "allow_empty": True},
    "APU_TSR": {"pattern": r"^\d+$", "allow_empty": True},
    "APU_TSN": {"pattern": r"^\d+$", "allow_empty": True},
    "APU_CSR": {"pattern": r"^\d+$", "allow_empty": True},
    "APU_CSN": {"pattern": r"^\d+$", "allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_SECTION_START_RE = re.compile(
    r"^DESCRIPTION\s+PART\s+NO\.?\s+SERIAL\s+NO\.?\s+LOT\s+NO\s+TSN\s+CSN\s+TSI\s+CSI\s+LIFE",
    re.I,
)
_SECTION_END_RE = re.compile(r"ACCESSORIES\s+RECORD", re.I)
_PN_RE = re.compile(r"^\d{4,7}-\d{1,3}(?:-\d{1,3})?$")
# A bare 1-3 letter lowercase token riding along on an otherwise
# numeric/dash/NA orphan trailing line -- confirmed OCR noise on the
# sample, never real column data (see module docstring).
_NOISE_TOK_RE = re.compile(r"^[a-z]{1,3}$")
_NUM_COMMA_RE = re.compile(r"^[\d,]+$")
_SLOTS = ("TSN", "CSN", "TSI", "CSI")

# Header regexes -- each anchored on a stable label suffix/shape so garbled
# leading glyphs (confirmed real on the sample: "'ART NO:", "n440DEL:")
# don't need to be predicted exactly.
_PN_SN_CUSTOMER_RE = re.compile(
    r"ART NO:\s*(\S+)\s+SERIAL NO\.?:\s*(\S+)\s+CUSTOMER:\s*(.+)$", re.M
)
_MODEL_RE = re.compile(r"DEL:\s*(\S+)")
_SERIES_RE = re.compile(r"SERIES\s*:?\s*(\d)\s+(\d)\b")
_DATE_RE = re.compile(r"\bDATE:\s*(\d{1,2})\s+([A-Z]{3})\s+(\d{4})")
_WO_RE = re.compile(r"WO\s*NO\.?:\s*(\S+)")
_TSR_TSN_RE = re.compile(r"TSR/\S*SN:\s*(\S+)\s*/\s*(\S+)")
_CSR_CSN_RE = re.compile(r"CSR/CSN:(\d)\s+(\d)\s*/\s*(\S+)")


def _parse_meta(text: str) -> dict:
    meta: dict[str, str] = {}
    m = _PN_SN_CUSTOMER_RE.search(text)
    if m:
        meta["APU_PART_NUMBER"] = m.group(1)
        meta["APU_SERIAL_NUMBER"] = m.group(2)
        meta["CUSTOMER"] = m.group(3).strip()
    m = _MODEL_RE.search(text)
    if m:
        meta["APU_MODEL"] = m.group(1)
    m = _SERIES_RE.search(text)
    if m:
        meta["APU_SERIES"] = m.group(1) + m.group(2)
    m = _DATE_RE.search(text)
    if m:
        meta["TAG_DATE"] = f"{m.group(1)} {m.group(2)} {m.group(3)}"
    m = _WO_RE.search(text)
    if m:
        meta["WORK_ORDER"] = m.group(1)
    m = _TSR_TSN_RE.search(text)
    if m:
        meta["APU_TSR"], meta["APU_TSN"] = m.group(1), m.group(2)
    m = _CSR_CSN_RE.search(text)
    if m:
        meta["APU_CSR"] = m.group(1) + m.group(2)
        meta["APU_CSN"] = m.group(3)
    return meta


def _split_life(trailing: list[str]) -> tuple[str, list[str]]:
    """Peel a trailing "<n>,<nnn> CYC" or bare "NA" life-limit tail off the
    end of a trailing-token list. Returns (life_limit, remaining_tokens)."""
    if (len(trailing) >= 2 and trailing[-1] == "CYC"
            and _NUM_COMMA_RE.match(trailing[-2])):
        return f"{trailing[-2]} {trailing[-1]}", trailing[:-2]
    if trailing and trailing[-1] == "NA":
        return trailing[-1], trailing[:-1]
    return "", trailing


def _map_trailing(trailing: list[str]) -> tuple[str, dict[str, str], str]:
    """Map the tokens between SERIAL NO. and the life-limit tail onto
    LOT_NO (only present when there are 5) + TSN/CSN/TSI/CSI, in that
    fixed left-to-right order. Anything left over (more than 5 tokens --
    not seen on the known sample) is kept verbatim rather than guessed
    into a slot."""
    lot = ""
    vals = {s: "" for s in _SLOTS}
    if len(trailing) == 5:
        lot, trailing = trailing[0], trailing[1:]
    if len(trailing) <= 4:
        for slot, val in zip(_SLOTS, trailing):
            vals[slot] = val
        return lot, vals, ""
    return lot, vals, " ".join(trailing)


def _llp_block(lines: list[str]) -> list[str]:
    start = end = None
    for i, line in enumerate(lines):
        if start is None and _SECTION_START_RE.search(line.strip()):
            start = i + 1
        elif start is not None and _SECTION_END_RE.search(line):
            end = i
            break
    if start is None:
        return []
    return lines[start:end if end is not None else len(lines)]


def _parse_rows(lines: list[str]) -> list[dict]:
    records: list[dict] = []
    last: dict | None = None
    pending_orphan: list[str] | None = None

    for line in lines:
        toks = line.split()
        if not toks:
            continue

        pn_idx = next((i for i, t in enumerate(toks) if _PN_RE.match(t)), None)
        if pn_idx is not None:
            desc = " ".join(toks[:pn_idx])
            pn = toks[pn_idx]
            rest = toks[pn_idx + 1:]
            sn = rest[0] if rest else ""
            trailing = rest[1:]
            life, trailing = _split_life(trailing)
            lot, vals, trail_note = _map_trailing(trailing)

            rec = {c: "" for c in CANONICAL_COLUMNS}
            rec["DESCRIPTION"] = desc
            rec["PART_NUMBER"] = pn
            rec["SERIAL_NUMBER"] = sn
            rec["LOT_NO"] = lot
            rec["TSN"], rec["CSN"], rec["TSI"], rec["CSI"] = (
                vals["TSN"], vals["CSN"], vals["TSI"], vals["CSI"]
            )
            rec["LIFE_LIMIT"] = life
            rec["STATUS_TRAIL"] = trail_note

            if pending_orphan is not None:
                o_life, o_rest = _split_life(pending_orphan)
                empty_slots = [s for s in _SLOTS if not rec[s]]
                for slot, val in zip(empty_slots, o_rest):
                    rec[slot] = val
                leftover = o_rest[len(empty_slots):]
                if leftover:
                    rec["STATUS_TRAIL"] = (
                        f"{rec['STATUS_TRAIL']} {' '.join(leftover)}".strip()
                    )
                if o_life and not rec["LIFE_LIMIT"]:
                    rec["LIFE_LIMIT"] = o_life
                pending_orphan = None

            records.append(rec)
            last = rec
            continue

        if toks == ["-"]:
            # Blank-LOT_NO continuation line for the row just emitted.
            if last is not None and not last["LOT_NO"]:
                last["LOT_NO"] = "-"
            continue

        # Orphan trailing-values line (no DESCRIPTION/PART NO. of its own)
        # -- buffered to fill the NEXT row's still-empty trailing slots.
        # Bare short-lowercase noise tokens are dropped; they match no
        # column shape (see module docstring).
        meaningful = [t for t in toks if not _NOISE_TOK_RE.match(t)]
        if meaningful:
            pending_orphan = meaningful

    return records


def extract(pdf_path: str) -> list[dict]:
    with pdfplumber.open(pdf_path) as pdf:
        text = pdf.pages[0].extract_text() or ""
    meta = _parse_meta(text)
    block = _llp_block(text.splitlines())
    records = _parse_rows(block)
    for rec in records:
        for k, v in meta.items():
            rec[k] = v
    return records
