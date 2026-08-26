"""Israel Aerospace Industries (IAI) dual-rating engine LLP status --
"Life Limited Parts for: <engine model> (<suffix>)". A one-page, scanned
(no text layer) report for an engine that can be operated/rated under
either of two related model numbers, so every part row (and the header
summary) tracks cycles used/limit/remaining TWICE -- once per rating --
side by side, rather than once.

Confirmed directly (rendered and read, not just signature-matched) on a
small set of real files sharing this exact layout: same header block
shape and table columns; one has a genuinely empty (0-char) text layer,
the other carries a garbled embedded text layer (an upstream OCR pass
baked into the PDF at creation time, similar to what
ihi_engine_llp_time_cycle_record.py documents for its own format) that
still leaves this format's title phrase and work-record label intact --
see the SIGNATURES comment below. A further candidate file, initially
grouped into the same cluster by an automated similarity pass on
filename/folder alone, was checked directly and does NOT belong here --
it has a real (clean) embedded text layer, a differently-worded title
("ENGINE LIFE LIMITED PARTS FOR <model>", no colon after "for" and no
parenthesised suffix), and an 11-column-wide per-row layout rather than
this format's TSN/CSN + one 6-value split-by-rating block. It is out of
scope for this module and would need its own variant if ever wanted.

Header block (values below are illustrative, not from any real file)::

    FAA CRS No.<code>
    EASA APPROVAL No. <approval-no>
    Life Limited Parts for: <MODEL_A> (<suffix>)
    Eng s/n: <esn> ENG. WORK RECORD NO.: <work-record>
    Customer: <operator>
    TSN: <hours>
    CSN: <cycles> TSO : <hours>
    Cycles remaining: <MODEL_A> (<suffix>) : <n> <MODEL_B> (<suffix>) : <n> CSO : <n>

Table columns: Description / P/N / S/N / TSN / CSN / then two further
column-pairs each split by the two ratings -- Total Cycles, Cycles Limit,
Remaining Cycles -- then Remarks.

Two data-row shapes share that layout:

  - A module-summary row (its DESCRIPTION literally ends in "MODULE", e.g.
    an illustrative "LPC MODULE"/"HPC MODULE") -- these report only the
    module assembly's own running TSN/CSN, no per-rating life-limit
    figures at all (blank cells across the rest of the row on the source
    page). Confirmed reliable: every row whose trailing numeric run reads
    back as exactly TSN/CSN (2 values) on a clean scan carries "MODULE" in
    its description, and vice versa -- so detection keys off that word,
    not the trailing count (see below for why the count alone isn't safe).
  - A real LLP-tracked part row underneath, e.g. an illustrative
    "HUB FRONT COMP. <pn> <sn> <tsn> <csn> <total_A> <total_B> <limit_A>
    <limit_B> <remain_A> <remain_B>" -- 8 trailing numeric values.

Trailing-value count is NOT used as the primary signal for which shape a
row is, because OCR quality varies a lot between scans of this exact
format: on a lower-fidelity source page, real 8-value rows regularly OCR
down to 0-7 recovered numeric tokens (adjacent digits fusing into one
token, a table rule glyph breaking the numeric run, thousands separators
misread) well before ever reaching a real module row's genuine 2. Forcing
a positional split onto anything short of the full 8 would routinely
mis-assign a genuine LIFE-LIMIT/REMAINING figure into a TOTAL-CYCLES slot
on these degraded rows. Instead: DESCRIPTION containing "MODULE" is the
row-shape signal; TSN/CSN are always the first 1-2 recovered numeric
tokens; and anything recovered beyond that but short of the full
8-value set for a non-module row is kept verbatim in a catch-all field
(TRAILING_CYCLES_RAW) rather than guessed into a specific named slot --
the same call this package's other OCR-heavy siblings make for their own
ragged trailing blocks (see e.g. elal_internal_parts_list.py's
TSO_HOURS/CSO_CYCLES handling and pro_rata_engine_llp.py's
OTHER_THRUST_RATING_VALUES).
"""
from __future__ import annotations
import re

from sheet_types.llp_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text

NAME = "IAI Dual-Rating Engine LLP"

# One known file (0-char text layer, genuinely scanned) needs ocr_detect()
# below to be reachable at all. The other carries a garbled embedded text
# layer -- confirmed by direct pdfplumber extraction: most of the header
# reads as scrambled OCR-derived noise (e.g. the producer's own name reads
# as an unrecognizable jumble of substituted characters), but this exact
# title phrase and the work-record label both happen to survive largely
# intact (illustrative reconstruction of the pattern actually observed:
# "Life Limited Parts for: PW4O6O <.3i", "WORK RECORD NO.: <garbled
# digits+letter>") -- so this phrase is kept here (not left empty) to
# reach that file via the ordinary text-layer signature path;
# ocr_detect() below is what catches the other, truly text-less file.
# Checked for collisions against every SIGNATURES list in
# sheet_types/{occm,ht,llp}.py and every existing variant file (including
# pro_rata_engine_llp.py's "LIFE LIMITED PARTS FOR A" top-level entry --
# that one needs an "A" right after "for", this one needs a colon, so
# they never overlap).
SIGNATURES = [
    "Life Limited Parts for:",
]

CANONICAL_COLUMNS = [
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "TSN",
    "CSN",
    "TOTAL_CYCLES_A",
    "TOTAL_CYCLES_B",
    "CYCLES_LIMIT_A",
    "CYCLES_LIMIT_B",
    "REMAINING_CYCLES_A",
    "REMAINING_CYCLES_B",
    # Ragged/partial-OCR trailing tokens that couldn't be safely mapped to
    # one of the 6 named fields above -- see module docstring.
    "TRAILING_CYCLES_RAW",
    "REMARKS",
    # File-level metadata -- same on every row of a given file.
    "ESN",
    "WORK_RECORD_NO",
    "OPERATOR",
    "ENGINE_MODEL_A",
    "ENGINE_MODEL_B",
    "ENGINE_TSN",
    "ENGINE_CSN",
    "ENGINE_TSO",
    "ENGINE_CYCLES_REMAIN_A",
    "ENGINE_CYCLES_REMAIN_B",
    "ENGINE_CSO",
    "FAA_CRS_NO",
    "EASA_APPROVAL_NO",
]

_HOUR_RULE = {"pattern": r"^\d+(\.\d+)?$", "int_range": (0, 90000), "allow_empty": True}
_CYCLE_RULE = {"pattern": r"^\d+$", "int_range": (0, 55000),
               "int_range_review": (0, 30000), "allow_empty": True}
# The header's own TSN/TSO figures print with a 2-decimal-place hours
# fraction (e.g. "69064.00", "14798.06") -- unlike every per-row TSN/CSN
# value inspected, which is always a whole cycle/hour count. This
# project's shared thousands-separator parser (shared/cleanup.py's
# `_parse_thousands_int`) deliberately rejects any decimal remainder that
# isn't a 3-digit thousands group, by design ("these fields should be
# whole cycles") -- so int_range can't be applied to a genuinely
# fractional-hours field without every real value misflagging as
# not_a_number. Format is still checked via `pattern`; only the
# range/soft-band check is skipped for these two fields.
_HOUR_RULE_DECIMAL = {"pattern": r"^[\d,]+(\.\d+)?$", "allow_empty": True}
_OVERRIDES = {
    "TSN":                    _HOUR_RULE,
    "CSN":                    _CYCLE_RULE,
    "TOTAL_CYCLES_A":         _CYCLE_RULE,
    "TOTAL_CYCLES_B":         _CYCLE_RULE,
    "CYCLES_LIMIT_A":         _CYCLE_RULE,
    "CYCLES_LIMIT_B":         _CYCLE_RULE,
    "REMAINING_CYCLES_A":     _CYCLE_RULE,
    "REMAINING_CYCLES_B":     _CYCLE_RULE,
    "TRAILING_CYCLES_RAW":    {"allow_empty": True},
    "REMARKS":                {"allow_empty": True},
    "ESN":                    {"pattern": r"^[A-Z]?\d{4,8}$", "allow_empty": True},
    "WORK_RECORD_NO":         {"allow_empty": True},
    "OPERATOR":               {"allow_empty": True},
    "ENGINE_MODEL_A":         {"allow_empty": True},
    "ENGINE_MODEL_B":         {"allow_empty": True},
    "ENGINE_TSN":             _HOUR_RULE_DECIMAL,
    "ENGINE_CSN":             _CYCLE_RULE,
    "ENGINE_TSO":             _HOUR_RULE_DECIMAL,
    "ENGINE_CYCLES_REMAIN_A": _CYCLE_RULE,
    "ENGINE_CYCLES_REMAIN_B": _CYCLE_RULE,
    "ENGINE_CSO":             _CYCLE_RULE,
    "FAA_CRS_NO":             {"allow_empty": True},
    "EASA_APPROVAL_NO":       {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_DPI = 250
_PSM = 6

# Producer's own P/N shape on every part row inspected: 2 digits, 1
# letter, 3 digits, optional "-NN"/"-NNN" suffix -- same anchor
# elal_internal_parts_list.py uses for its own sibling format.
_PN_RE = re.compile(r"^\d{2}[A-Za-z]\d{3}(?:-\d{2,3})?$")
_NUM_RE = re.compile(r"^[\d,]+(\.\d+)?$")

# Isolated ruled-grid-line/scan-noise tokens (a lone "_", ".", "|", "~",
# "-", or a smart quote) that OCR emits as their own whitespace-separated
# token, plus the same characters glued onto the edges of an otherwise
# real token (e.g. "CENCDF7859:" or "5193;") -- confirmed by direct
# comparison against a clean render of the same row. Never legitimate
# mid-token content for this producer's PART_NUMBER (hyphen only, never at
# the edges after this strip), SERIAL_NUMBER (plain alnum), or numeric
# fields, so stripping only the edges -- not the middle -- is safe.
_NOISE_TOKEN_RE = re.compile(r'^[-_.|~`\'",;:*=]+$')
_STRIP_RE = re.compile(r'^[-_.|~`\'",;:*=]+|[-_.|~`\'",;:*=]+$')

_SKIP_FRAGMENTS = (
    "FAA CRS",
    "EASA APPROVAL",
    "Life Limited Parts for",
    "Eng s/n",
    "Customer:",
    "TSN:",
    "CSN:",
    "Cycles remaining",
    "Description",
    "Remark:",
    "Inspector Sign",
    "Date:",
    "Signature",
    "Page",
)

_FOR_RE = re.compile(r"Life\s+Limited\s+Parts\s+for\s*:?\s*([A-Z0-9]+)\s*\(([^)]*)\)", re.I)
_WR_RE = re.compile(r"WORK\s+RECORD\s+NO\.?\s*:?\s*(\S+)", re.I)
_FAA_RE = re.compile(r"FAA\s+CRS\s+No\.?\s*([A-Z0-9]+)", re.I)
_EASA_RE = re.compile(r"EASA\s+APPROVAL\D*(\d[\d.]*\d)", re.I)
_ESN_RE = re.compile(r"Eng\s*s\s*/\s*n\s*:?\s*(\S+)", re.I)
_CUST_RE = re.compile(r"Customer\s*:?\s*(.+)", re.I)
_TSN_RE = re.compile(r"^\s*TSN\s*:?\s*([\d,]+(?:\.\d+)?)", re.I | re.M)
_CSNTSO_RE = re.compile(r"^\s*CSN\s*:?\s*([\d,]+)\s+TSO\s*:?\s*([\d,]+(?:\.\d+)?)", re.I | re.M)
_REMAIN_RE = re.compile(
    r"Cycles\s+remaining\s*:?\s*([A-Z0-9]+)\s*\(([^)]*)\)\s*:?\s*([\d,]+)\s+"
    r"([A-Z0-9]+)\s*\(([^)]*)\)\s*:?\s*([\d,]+)\s+CSO\s*:?\s*([\d,]+)", re.I)


def _clean_tokens(line: str) -> list[str]:
    out = []
    for t in line.split():
        if _NOISE_TOKEN_RE.match(t):
            continue
        c = _STRIP_RE.sub("", t)
        if c:
            out.append(c)
    return out


def _is_skip_line(line: str) -> bool:
    return any(frag.upper() in line.upper() for frag in _SKIP_FRAGMENTS)


def _find_pn_index(toks: list[str]) -> int | None:
    for i, t in enumerate(toks):
        if _PN_RE.match(t):
            return i
    return None


def _parse_meta(text: str) -> dict:
    meta: dict[str, str] = {}
    m = _FAA_RE.search(text)
    if m:
        meta["FAA_CRS_NO"] = m.group(1)
    m = _EASA_RE.search(text)
    if m:
        meta["EASA_APPROVAL_NO"] = m.group(1)
    m = _ESN_RE.search(text)
    if m:
        meta["ESN"] = m.group(1)
    m = _WR_RE.search(text)
    if m:
        meta["WORK_RECORD_NO"] = m.group(1)
    m = _CUST_RE.search(text)
    if m:
        meta["OPERATOR"] = m.group(1).strip()
    m = _TSN_RE.search(text)
    if m:
        meta["ENGINE_TSN"] = m.group(1)
    m = _CSNTSO_RE.search(text)
    if m:
        meta["ENGINE_CSN"] = m.group(1)
        meta["ENGINE_TSO"] = m.group(2)
    m = _REMAIN_RE.search(text)
    if m:
        model_a, suffix_a, remain_a, model_b, suffix_b, remain_b, cso = m.groups()
        meta["ENGINE_MODEL_A"] = f"{model_a}({suffix_a})" if suffix_a else model_a
        meta["ENGINE_MODEL_B"] = f"{model_b}({suffix_b})" if suffix_b else model_b
        meta["ENGINE_CYCLES_REMAIN_A"] = remain_a
        meta["ENGINE_CYCLES_REMAIN_B"] = remain_b
        meta["ENGINE_CSO"] = cso
    elif "FOR" not in meta:
        m = _FOR_RE.search(text)
        if m:
            model, suffix = m.groups()
            meta.setdefault("ENGINE_MODEL_A", f"{model}({suffix})" if suffix else model)
    return meta


def _parse_row(line: str) -> dict | None:
    s = line.strip()
    if not s or _is_skip_line(s):
        return None
    toks = _clean_tokens(s)
    pn_idx = _find_pn_index(toks)
    if pn_idx is None or pn_idx == 0 or pn_idx + 1 >= len(toks):
        return None

    description = " ".join(toks[:pn_idx])
    pn = toks[pn_idx]
    sn = toks[pn_idx + 1]
    rest = toks[pn_idx + 2:]

    j = 0
    while j < len(rest) and _NUM_RE.match(rest[j]):
        j += 1
    nums = rest[:j]
    remarks = " ".join(rest[j:])

    rec: dict[str, str] = {c: "" for c in CANONICAL_COLUMNS}
    rec["DESCRIPTION"] = description
    rec["PART_NUMBER"] = pn
    rec["SERIAL_NUMBER"] = sn
    rec["REMARKS"] = remarks

    if "MODULE" in description.upper():
        # Module-summary row -- only TSN/CSN are ever printed, see docstring.
        if len(nums) >= 1:
            rec["TSN"] = nums[0]
        if len(nums) >= 2:
            rec["CSN"] = nums[1]
        if len(nums) > 2:
            rec["TRAILING_CYCLES_RAW"] = " ".join(nums[2:])
        return rec

    if len(nums) >= 8:
        (rec["TSN"], rec["CSN"], rec["TOTAL_CYCLES_A"], rec["TOTAL_CYCLES_B"],
         rec["CYCLES_LIMIT_A"], rec["CYCLES_LIMIT_B"],
         rec["REMAINING_CYCLES_A"], rec["REMAINING_CYCLES_B"]) = nums[:8]
        if len(nums) > 8:
            rec["TRAILING_CYCLES_RAW"] = " ".join(nums[8:])
        return rec

    if not nums:
        return None

    # Ragged (1-7 recovered tokens): don't force a positional split onto
    # the 6 named cycle fields -- OCR degradation on this scan quality
    # regularly drops/merges tokens (see docstring), and a wrong split
    # would misrepresent a real LIFE-LIMIT or REMAINING figure as a
    # TOTAL-CYCLES one. Keep TSN/CSN (reliably the first 1-2 values) and
    # fold the rest into the catch-all.
    if len(nums) >= 1:
        rec["TSN"] = nums[0]
    if len(nums) >= 2:
        rec["CSN"] = nums[1]
    if len(nums) > 2:
        rec["TRAILING_CYCLES_RAW"] = " ".join(nums[2:])
    return rec


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 header OCR check for the router's blank-text fallback.
    Requires both the "Life Limited Parts for: <model> (<suffix>)" title
    phrase AND the "WORK RECORD NO" label -- checked together specifically
    to avoid the near-miss sibling format described in the module
    docstring (title text "ENGINE LIFE LIMITED PARTS FOR <model>", no
    colon, no parenthesised suffix -- _FOR_RE requires the parentheses and
    so never matches it)."""
    try:
        img = await render_page(pdf_path, 0, dpi=_DPI)
        crop = img.crop((0, 0, img.width, int(img.height * 0.35)))
        text = await ocr_text(crop, psm=_PSM)
        return bool(_FOR_RE.search(text)) and bool(_WR_RE.search(text))
    except Exception:
        return False


async def extract(pdf_path: str) -> list[dict]:
    img = await render_page(pdf_path, 0, dpi=_DPI)
    text = await ocr_text(img, psm=_PSM)
    meta = _parse_meta(text)

    records: list[dict] = []
    for raw in text.splitlines():
        rec = _parse_row(raw)
        if rec is None:
            continue
        for k, v in meta.items():
            rec[k] = v
        rec["_page"] = 1
        records.append(rec)
    return records
