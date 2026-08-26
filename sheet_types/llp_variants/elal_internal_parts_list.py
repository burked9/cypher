"""EL AL Israel Airlines internal-parts LLP status — "LIST OF INTERNAL PARTS
FOR DATE DD/MM/YYYY".

Source format: a single-page, per-engine LLP snapshot printed by EL AL's
own MIS. Header carries a REASON line, the engine model, engine number, and
running totals (T.T / T.C / T.S.O / a since-overhaul cycles figure). The
table itself is one row per module/disk/bearing, grouped under six module
headers (e.g. an "<X> Module" row for each of the low/high pressure
compressor and turbine sections, plus the gearboxes).

Row format (values below are illustrative, not from any real file)::

    Hub        50B500   AB1234      40000  10000  15000  5000
    └ stage ─┘└── PN ─┘└── SN ───┘└TOTAL_H┘└TOTAL_C┘└LIFE_C┘└REM_C┘

Two special row shapes:

  - Bearings ("No. N Brg.") carry no tracked life limit at all — the row
    ends after TOTAL_HOURS/TOTAL_CYCLES (only 2 trailing numeric tokens).
  - The six module-summary rows (one per module/gearbox) do not report a
    disk-style life limit either; instead the trailing pair is replaced by
    literal "T.S.O <hours>" / "C.S.0 <cycles>" labelled figures — the
    module's own time/cycles since overhaul, not a life-limit or
    remaining-life figure. Example::

        Module   50X000   AB1234      40000  10000  T.S.0  2000  C.S.0  800

    These are kept (not dropped) with LIFE_LIMIT_CYCLES/REMAINING_CYCLES
    left empty and the TSO/CSO figures captured in their own columns —
    collapsing them into the disk-style fields would misrepresent them as
    a life limit that was never printed.

This format never prints an hours-based life limit or remaining-hours
figure for any row (published limits here are cycle-based only), so no
LIFE_LIMIT_HOURS / REMAINING_HOURS columns exist in the schema.

The anchor used to locate PART_NUMBER within each row is the producer's
fixed PN shape -- two digits, one letter, three digits, optional numeric
suffix (e.g. "NNLNNN" or "NNLNNN-NN") -- which is a reliable pivot: STAGE
is everything before it, SERIAL_NUMBER is the token right after it, and
the remaining trailing tokens are the numeric tail parsed positionally.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.llp_variants._base import merged_rules

NAME = "EL AL Internal Parts List"
SIGNATURES = [
    "LIST OF INTERNAL PARTS",
]

CANONICAL_COLUMNS = [
    "STAGE",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "TOTAL_HOURS",
    "TOTAL_CYCLES",
    "LIFE_LIMIT_CYCLES",
    "REMAINING_CYCLES",
    "TSO_HOURS",   # module-summary rows only
    "CSO_CYCLES",  # module-summary rows only
    # Header metadata -- same on every row
    "ESN",
    "ENGINE_MODEL",
    "ENGINE_TSN",
    "ENGINE_TCN",
    "ENGINE_TSO",
    "ENGINE_CSO",
    "STATUS_DATE",
    "REASON",
]

_HOUR_RULE = {"pattern": r"^\d+$", "int_range": (0, 80000), "allow_empty": True}
_CYCLE_RULE = {"pattern": r"^\d+$", "int_range": (0, 55000),
               "int_range_review": (0, 30000), "allow_empty": True}
_OVERRIDES = {
    "TOTAL_HOURS":        _HOUR_RULE,
    "TOTAL_CYCLES":       _CYCLE_RULE,
    "LIFE_LIMIT_CYCLES":  _CYCLE_RULE,
    "REMAINING_CYCLES":   _CYCLE_RULE,
    "TSO_HOURS":          _HOUR_RULE,
    "CSO_CYCLES":         _CYCLE_RULE,
    "ENGINE_TSN":         _HOUR_RULE,
    "ENGINE_TCN":         _CYCLE_RULE,
    "ENGINE_TSO":         _HOUR_RULE,
    "ENGINE_CSO":         _CYCLE_RULE,
    "ESN":                {"pattern": r"^[A-Z]?\d{4,8}$", "allow_empty": True},
    "ENGINE_MODEL":       {"allow_empty": True},
    "STATUS_DATE":        {"pattern": r"^\d{2}/\d{2}/\d{4}$", "allow_empty": True},
    "REASON":             {"allow_empty": True},
    "STAGE":              {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Anchor: 2 digits, 1 letter, 3 digits, optional "-NN"/"-NNN" suffix.
_PN_RE = re.compile(r"^\d{2}[A-Za-z]\d{3}(?:-\d{2,3})?$")
_NUM_RE = re.compile(r"^\d+$")

_SKIP_FRAGMENTS = (
    "LIST OF INTERNAL PARTS",
    "REASON:",
    "PREPARED BY",
    "Q.C.APPROVAL",
    "Total Life Limits",
    "Remaninq Life",
    "Staqe MFGPN",
    "Page",
)


def _is_skip_line(line: str) -> bool:
    return any(frag in line for frag in _SKIP_FRAGMENTS)


def _normalize_label(tok: str) -> str:
    """Collapse a T.S.O/C.S.0-style label token to a bare "TSO"/"CSO" for
    comparison, tolerant of the punctuation and O/0 noise this producer's
    export shows across files (periods vs commas, letter-O vs digit-0)."""
    cleaned = re.sub(r"[^A-Za-z0-9]", "", tok).upper()
    return cleaned.replace("0", "O")


def _parse_meta(text: str) -> dict:
    meta: dict[str, str] = {}
    lines = text.splitlines()[:10]
    for line in lines:
        m = re.search(r"FOR DATE\s+(\d{2}/\d{2}/\d{4})", line)
        if m:
            meta["STATUS_DATE"] = m.group(1)
        m = re.search(r"^REASON:\s*(.+)", line.strip())
        if m:
            meta["REASON"] = m.group(1).strip()
        m = re.match(r"^Engine\s+([A-Za-z0-9\-]+)\s*$", line.strip())
        if m:
            meta["ENGINE_MODEL"] = m.group(1)
        m = re.search(r"Engine\s*No\.?\s+(\S+)", line)
        if m:
            meta["ESN"] = m.group(1)
        m = re.search(r"^T\.T\s+(\d+)", line.strip())
        if m:
            meta["ENGINE_TSN"] = m.group(1)
        m = re.search(r"^T\.C\s+(\d+)", line.strip())
        if m:
            meta["ENGINE_TCN"] = m.group(1)
        m = re.search(r"^T\.S\.O\s+(\d+)", line.strip())
        if m:
            meta["ENGINE_TSO"] = m.group(1)
        m = re.search(r"^C[.,]?S[.,]?[OG]\s+(\d+)", line.strip())
        if m:
            meta["ENGINE_CSO"] = m.group(1)
    return meta


def _find_pn_index(toks: list[str]) -> int | None:
    for i, t in enumerate(toks):
        if _PN_RE.match(t):
            return i
    return None


def _parse_row(line: str) -> dict | None:
    s = line.strip()
    if not s or _is_skip_line(s):
        return None
    toks = s.split()
    pn_idx = _find_pn_index(toks)
    if pn_idx is None or pn_idx == 0 or pn_idx + 1 >= len(toks):
        return None

    stage = " ".join(toks[:pn_idx])
    pn = toks[pn_idx]
    sn = toks[pn_idx + 1]
    tail = toks[pn_idx + 2:]

    rec: dict[str, str] = {c: "" for c in CANONICAL_COLUMNS}
    rec["STAGE"] = stage
    rec["PART_NUMBER"] = pn
    rec["SERIAL_NUMBER"] = sn

    if len(tail) == 6 and all(_NUM_RE.match(t) for t in (tail[0], tail[1], tail[3], tail[5])) \
            and _normalize_label(tail[2]) == "TSO" and _normalize_label(tail[4]) == "CSO":
        # Module-summary row: trailing pair is TSO/CSO, not a life limit.
        rec["TOTAL_HOURS"] = tail[0]
        rec["TOTAL_CYCLES"] = tail[1]
        rec["TSO_HOURS"] = tail[3]
        rec["CSO_CYCLES"] = tail[5]
    elif len(tail) == 4 and all(_NUM_RE.match(t) for t in tail):
        rec["TOTAL_HOURS"] = tail[0]
        rec["TOTAL_CYCLES"] = tail[1]
        rec["LIFE_LIMIT_CYCLES"] = tail[2]
        rec["REMAINING_CYCLES"] = tail[3]
    elif len(tail) == 2 and all(_NUM_RE.match(t) for t in tail):
        # Bearing-style row: no life limit tracked for this part.
        rec["TOTAL_HOURS"] = tail[0]
        rec["TOTAL_CYCLES"] = tail[1]
    else:
        return None

    return rec


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        full_text = "\n".join((p.extract_text() or "") for p in pdf.pages)
        meta = _parse_meta(full_text)
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            for raw in text.splitlines():
                rec = _parse_row(raw)
                if rec is None:
                    continue
                rec["_page"] = page_num
                for k, v in meta.items():
                    rec[k] = v
                records.append(rec)
    return records
