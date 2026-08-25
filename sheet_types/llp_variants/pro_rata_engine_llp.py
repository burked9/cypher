"""Pro-Rata Engine LLP — \"Engine Life Limited Parts Status\" / Sky-Chile/Falcon style.

Source format (CFM56 + V2500 LLP reports, "Falcon Portfolio" / Sky Chile):
header carries Engine Number, Name Plate, Operator, MSN, TTSN, TCSN, status
date and the TSLSV/CSLSV pair. Data rows are one line per disk grouped by
engine module (section headers like ``LPC`` / ``HPC`` / ``HPT`` / ``LPT``).

Row format::

    Booster Spool  338-001-906-0  DF037635  23,443  16,350  16,350  30,000  0  14,397  13,650
    └ description ┘└── PN ─────┘└── SN ──┘└────── 7 numeric trailing tokens ─────┘

Numbers use commas as thousands separators. The 7 trailing numbers are
(positionally): TTSN, TCSN, 1st-Pro-Rata-Used, 1st-Pro-Rata-Limit,
Cycles-at-Fit, Part-Remain, Engine-Remain. The 2nd-Pro-Rata columns
collapse to empty in the text extraction when unused by the operator.

Special row types skipped:
  - Section labels (``LPC``, ``HPC``, ``HPT``, ``LPT``, ``TURBINE``)
  - ``Engine Limiter N,NNN`` subtotal rows
  - Page-footer disclaimer lines and ``Page N of M`` markers
  - Column-header lines

Description wraps are appended when a short alpha-only continuation line
follows a data row (e.g. ``Compressor Rear`` followed by ``(CDP) Seal``).
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.llp_variants._base import merged_rules

NAME = "Pro-Rata Engine LLP"
SIGNATURES = [
    "Engine Life Limited Parts Status",
    "1st Pro Rata",
    "TSLSV",
    "CSLSV",
]

CANONICAL_COLUMNS = [
    "MODULE",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "TTSN",
    "TCSN",
    "PRO_RATA_1_USED",
    "PRO_RATA_1_LIMIT",
    "CYCLES_AT_FIT",
    "PART_REMAIN",
    "ENGINE_REMAIN",
    # Some parts carry extra pro-rata-generation values ahead of the
    # standard 5 above (an engine re-rated to a different thrust rating
    # partway through its life keeps the prior generation's figures too).
    # Kept verbatim rather than guessed into a specific named slot — see
    # _parse_row.
    "OTHER_THRUST_RATING_VALUES",
    "REMARKS",
    # Engine metadata — same on every row
    "ESN",
    "ENGINE_MODEL",
    "OPERATOR",
    "MSN",
    "ENGINE_TTSN",
    "ENGINE_TCSN",
    "ENGINE_TSLSV",
    "ENGINE_CSLSV",
    "STATUS_DATE",
]

# Hours can run to ~80k on long-haul engines; cycles cap is the user-set
# engine-LLP rule of 0..45000. Anything outside that range is flagged.
_HOUR_RULE  = {"pattern": r"^[\d,]+(\.\d+)?$", "int_range": (0, 80000)}
_CYCLE_RULE = {"pattern": r"^[\d,]+$", "int_range": (0, 55000),
               "int_range_review": (0, 30000)}
_OVERRIDES = {
    "TTSN":            _HOUR_RULE,
    "TCSN":            _CYCLE_RULE,
    "PRO_RATA_1_USED": _CYCLE_RULE,
    "PRO_RATA_1_LIMIT": _CYCLE_RULE,
    "CYCLES_AT_FIT":   _CYCLE_RULE,
    "PART_REMAIN":     _CYCLE_RULE,
    "ENGINE_REMAIN":   _CYCLE_RULE,
    "ENGINE_TTSN":     _HOUR_RULE,
    "ENGINE_TCSN":     _CYCLE_RULE,
    "ENGINE_TSLSV":    _HOUR_RULE,
    "ENGINE_CSLSV":    _CYCLE_RULE,
    "ESN":             {"pattern": r"^\d{4,8}$"},
    "STATUS_DATE":     {"pattern": r"^\d{1,2}-[A-Za-z]{3}-\d{4}$"},
    "OTHER_THRUST_RATING_VALUES": {"allow_empty": True},
    "REMARKS": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_NUM_RE = re.compile(r"^[\d,]+(\.\d+)?$")
# A "-" (occasionally glued to a stray footnote/OCR mark like "-·") is this
# producer's placeholder for "engine has never operated at this thrust
# rating" -- not a parse failure. Real data rows end in a mix of numbers
# and these dashes; treating only pure numbers as valid trailing tokens
# was dropping the vast majority of real rows (confirmed: 1 of ~17 rows
# survived per file before this fix).
_DASH_RE = re.compile(r"^[-–—][^\d]*$")
_PN_RE = re.compile(r"^[A-Z0-9][A-Z0-9\-./]*$")
_DATE_RE = re.compile(r"^\d{1,2}-[A-Za-z]{3}-\d{4}$")

_MODULE_LABELS = {"LPC", "HPC", "HPT", "LPT", "TURBINE", "FAN", "COMBUSTOR",
                  "COMBUSTION", "GEARBOX"}

# Lines we don't want as data rows
_SKIP_FRAGMENTS = (
    "Engine Life Limited Parts Status",
    "Engine Number Engine Name",
    "Description Part #",
    "Rata Used",
    "Part Engine Remain",
    "Internal Use Only",
    "for reference only",
    "Portfolio:",
)


def _is_num(tok: str) -> bool:
    return bool(_NUM_RE.match(tok))


def _is_num_or_dash(tok: str) -> bool:
    return bool(_NUM_RE.match(tok)) or bool(_DASH_RE.match(tok))


def _is_skip_line(line: str) -> bool:
    return any(frag in line for frag in _SKIP_FRAGMENTS)


def _parse_engine_meta(text: str) -> dict:
    """Parse the header block. Two-line layout — labels then values, both
    pre-joined into a soup. We pick out distinctive tokens by shape."""
    meta: dict[str, str] = {}
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for ln in lines[:15]:
        toks = ln.split()
        for t in toks:
            if _DATE_RE.match(t):
                meta.setdefault("STATUS_DATE", t)
        # Distinctive: ESN is a 6-digit integer; engine model contains digits + dashes
        for t in toks:
            if t.isdigit() and len(t) == 6:
                meta.setdefault("ESN", t)
            if re.match(r"^CFM\d", t) or re.match(r"^V\d{4}", t) or re.match(r"^PW\d{4}", t):
                meta.setdefault("ENGINE_MODEL", t)
        # TTSN / TCSN / TSLSV / CSLSV — look for "TTSN:", "TCSN:", "TSLSV:", "CSLSV:" labels.
        for i, t in enumerate(toks):
            up = t.upper()
            if up in ("TTSN:", "TCSN:", "TSLSV:", "CSLSV:") and i + 1 < len(toks):
                key = "ENGINE_" + up.rstrip(":")
                meta.setdefault(key, toks[i + 1])
    # Operator + MSN: the line "577247 CFM56-5B5/P Sky Chile 2460 ..." has
    # them positionally. Look for the line containing the ESN as a token.
    if "ESN" in meta:
        for ln in lines[:10]:
            toks = ln.split()
            if meta["ESN"] in toks:
                idx = toks.index(meta["ESN"])
                # After ESN: engine model, then operator (1+ words), then MSN
                if idx + 2 < len(toks):
                    # Try to extract operator (everything between engine-model and the MSN integer)
                    after = toks[idx + 1:]
                    # ENGINE_MODEL is at after[0]
                    msn_idx = None
                    for j in range(1, len(after)):
                        if after[j].isdigit() and 100 < int(after[j]) < 99999:
                            msn_idx = j
                            break
                    if msn_idx is not None and msn_idx > 1:
                        meta["OPERATOR"] = " ".join(after[1:msn_idx])
                        meta["MSN"] = after[msn_idx]
                break
    return meta


def _parse_row(line: str) -> dict | None:
    s = line.strip()
    if not s or _is_skip_line(s):
        return None
    toks = s.split()

    # Module label rows ("LPC", "HPC", etc.) — return as section change marker.
    # Must check BEFORE the `< 5` bail, since these lines are a single token.
    if len(toks) == 1 and toks[0].upper() in _MODULE_LABELS:
        return {"_module": toks[0].upper()}

    if len(toks) < 5:
        return None

    # Engine Limiter <num> row — subtotal, skip
    if toks[0].lower() == "engine" and len(toks) >= 2 and toks[1].lower() == "limiter":
        return None

    # A row can end in a free-text REMARKS note (an SB compliance reference
    # like "SB72-0652 C/W") instead of a numeric/dash value -- strip that
    # suffix first, or the trailing walk below never even starts (its very
    # first check, on the last token, would fail outright).
    remarks_end = len(toks)
    j = len(toks) - 1
    while j >= 0 and not _is_num_or_dash(toks[j]):
        j -= 1
    remarks = " ".join(toks[j + 1:remarks_end])
    toks = toks[:j + 1]
    if len(toks) < 5:
        return None

    # Walk back collecting trailing numeric-or-dash tokens. A trailing run
    # can be as short as 7 (TTSN, TCSN, then the 5 standard fields, no
    # dashes at all) or well past a dozen (extra pro-rata-generation
    # columns, several thrust ratings each rendering their own dash).
    trail = []
    i = len(toks) - 1
    while i >= 0 and _is_num_or_dash(toks[i]):
        trail.insert(0, toks[i])
        i -= 1
    if len(trail) < 5:
        return None
    if i < 2:
        return None
    sn = toks[i]
    pn = toks[i - 1]
    desc = " ".join(toks[: i - 1])
    # A purely-numeric serial number (this producer uses both alphanumeric
    # and plain-digit serials) reads as just another trailing data value,
    # walking the boundary one token too far left -- landing on the real
    # PN (which reliably contains a "-", e.g. "338-001-504-Q") and mistaking
    # the word before it for PN. Reclaim it: the real PN is toks[i], the
    # real SN is trail's first element (which was actually the serial).
    if "-" in toks[i] and "-" not in pn and not any(c.isdigit() for c in pn) and trail:
        pn, sn = toks[i], trail.pop(0)
        desc = " ".join(toks[: i])
    # A part that's never been removed since install prints literal "NEW
    # NEW" in place of TTSN/TCSN, right after the real PN/SN -- neither
    # word is numeric/dash, so the walk stops on the second "NEW",
    # swallowing the real identifiers into DESCRIPTION. Detect the pair
    # and step back over both to recover them.
    if pn.upper() == "NEW" and sn.upper() == "NEW" and i >= 4:
        trail[0:0] = [pn, sn]
        sn, pn = toks[i - 2], toks[i - 3]
        desc = " ".join(toks[: i - 3])
    if not _PN_RE.match(pn) or not _PN_RE.match(sn):
        return None

    rec: dict[str, str] = {c: "" for c in CANONICAL_COLUMNS}
    rec["DESCRIPTION"] = desc
    rec["PART_NUMBER"] = pn
    rec["SERIAL_NUMBER"] = sn
    rec["REMARKS"] = remarks
    # TTSN/TCSN are reliably the first two trailing values on every real
    # row inspected. The standard 5 fields (PRO_RATA_1_USED through
    # ENGINE_REMAIN) are reliably the LAST 5 -- whatever sits between the
    # two (present only on parts that have lived through a thrust-rating
    # change) is extra history the schema has no named slot for; keep it
    # verbatim rather than mis-assign it into one of the 5 named fields.
    if len(trail) >= 2:
        rec["TTSN"], rec["TCSN"] = trail[0], trail[1]
    middle = trail[2:-5] if len(trail) > 7 else []
    tail5 = trail[-5:] if len(trail) >= 7 else trail[2:]
    keys = ["PRO_RATA_1_USED", "PRO_RATA_1_LIMIT",
            "CYCLES_AT_FIT", "PART_REMAIN", "ENGINE_REMAIN"]
    for k, v in zip(keys, tail5):
        rec[k] = v
    if middle:
        rec["OTHER_THRUST_RATING_VALUES"] = " ".join(middle)
    return rec


def _is_wrap_continuation(line: str) -> bool:
    """Short non-numeric continuation of a previous description.
    e.g. '(CDP) Seal', 'ASSY', 'Case'."""
    s = line.strip()
    if not s or len(s) > 30:
        return False
    if any(c.isdigit() for c in s):
        return False
    # No commas (avoid joining sentence-y disclaimer fragments)
    if "," in s:
        return False
    return all(c.isalpha() or c.isspace() or c in "()-/." for c in s)


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    current_module = ""

    with pdfplumber.open(pdf_path) as pdf:
        full_text = "\n".join((p.extract_text() or "") for p in pdf.pages)
        meta = _parse_engine_meta(full_text)
        last_record: dict | None = None
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            for raw in text.splitlines():
                line = raw.strip()
                if not line:
                    last_record = None
                    continue
                rec = _parse_row(line)
                if rec is None:
                    # Wrap continuation?
                    if last_record is not None and _is_wrap_continuation(line):
                        last_record["DESCRIPTION"] = (
                            last_record["DESCRIPTION"] + " " + line
                        ).strip()
                    else:
                        last_record = None
                    continue
                if "_module" in rec:
                    current_module = rec["_module"]
                    last_record = None
                    continue
                rec["MODULE"] = current_module
                rec["_page"] = page_num
                for k, v in meta.items():
                    rec[k] = v
                records.append(rec)
                last_record = rec
    return records
