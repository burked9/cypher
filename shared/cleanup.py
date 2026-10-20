"""Per-cell normalization and soft validation.

Pipeline applied to each cell with rules:
    1. sequence_map        — multi-character OCR substitutions (e.g. "-'" → "7")
    2. char_map            — single-character OCR substitutions
    3. strip pipes         — always
    4. no_spaces           — collapse internal whitespace
    5. uppercase           — when configured
    6. field-specific      — e.g. revert_I_in_pn_prefix
    7. pattern validation  — regex check (soft; flags rather than rejects)
    8. range check         — int_range on numeric fields

`forward_fill_ata` post-processes a sequence of records: when ATA is missing
on a row, it inherits the most recently seen valid ATA. We track the most
recent ATA in the user-specified range (default 20-83) and record an
`_imputed:ATA` flag on rows whose ATA was filled this way, so the analyst
sees that the value came from inference, not the source PDF.

`normalize_date` converts the corpus's many date formats to ISO 8601 (YYYY-MM-DD).
"""
from __future__ import annotations
import re
from datetime import datetime


# Unicode dash variants that PDF writers occasionally emit instead of the
# plain ASCII U+002D hyphen-minus. These break regex anchors that expect
# `-` (e.g. date patterns, part-number shapes). One corpus file uses
# U+2010 throughout; other corpus files have shown U+2011/2013/2014/2212.
_DASH_TRANS = str.maketrans({
    "‐": "-",  # HYPHEN
    "‑": "-",  # NON-BREAKING HYPHEN
    "‒": "-",  # FIGURE DASH
    "–": "-",  # EN DASH
    "—": "-",  # EM DASH
    "−": "-",  # MINUS SIGN
})


def normalize_dashes(text: str) -> str:
    """Replace Unicode dash variants with ASCII hyphen-minus. Callers should
    invoke this on raw PDF text BEFORE regex parsing — the existing OCR_CHAR_MAP
    pipeline runs per-cell, which is too late if row-anchor regexes have
    already failed to match."""
    return text.translate(_DASH_TRANS)


def _revert_I_in_pn_prefix(value: str) -> str:
    """Within the first 4 characters of a PN, revert any '1' that has letters
    on both sides to 'I'. PNs commonly start with 1-3 capital letters
    (e.g. "SIC5059") and OCR misreads I as 1. The bounded scan keeps us safe
    from clobbering legitimate digit-letter mixes deeper in the PN.

    Examples:
        "S1C5059-13-10" -> "SIC5059-13-10"
        "B372BAM0511"   -> "B372BAM0511"   (no letter neighbour on both sides)
        "1209-100"      -> "1209-100"      (does not start with a letter)
    """
    if not value or not value[0].isalpha():
        return value
    chars = list(value)
    upper_bound = min(4, len(chars) - 1)
    for i in range(1, upper_bound):
        if chars[i] == "1":
            left = chars[i - 1].isalpha()
            right = chars[i + 1].isalpha()
            if left and right:
                chars[i] = "I"
    return "".join(chars)


# Per-file normalisation counters — caller resets via reset_normalize_counters()
# before processing each file, then reads the dict to report "stripped N
# leading-punctuation PNs/SNs from this file." Module-level on purpose:
# the cleanup pipeline is a per-call function and we don't want to thread
# a context object through every clean_cell invocation.
_NORMALIZE_COUNTERS: dict[str, int] = {"leading_punct": 0}


def reset_normalize_counters() -> None:
    """Reset normalisation counters; call before each per-file batch."""
    for k in _NORMALIZE_COUNTERS:
        _NORMALIZE_COUNTERS[k] = 0


def get_normalize_counters() -> dict[str, int]:
    """Return a snapshot of normalisation counters since the last reset."""
    return dict(_NORMALIZE_COUNTERS)


def clean_cell(value: str, rule: dict | None) -> tuple[str, list[str]]:
    issues: list[str] = []
    if value is None:
        value = ""
    s = value.strip()

    if rule is None:
        return s, issues

    # 1. Multi-char sequence replacements (longest-first ordering must be
    #    enforced by the caller in `sequence_map`'s list order).
    seq_map = rule.get("sequence_map")
    if seq_map:
        for src, dst in seq_map:
            if src in s:
                s = s.replace(src, dst)

    # 2. Single-character substitutions
    char_map = rule.get("char_map")
    if char_map:
        s = "".join(char_map.get(ch, ch) for ch in s)

    # 3. Always strip pipes (OCR artifacts from table borders)
    s = s.replace("|", "").strip()

    # 3b. Strip leading punctuation from PN / SN values. Several MIS
    # exports (seen across a handful of HT/OCCM formats in the corpus) use
    # leading `.`, `,` or `..` as indentation markers for sub-component
    # rows in the source PDF. The dots are formatting artefacts, not
    # real characters in the part-number — strip them so downstream
    # consumers see the clean PN rather than a `PART_NUMBER:bad_format`
    # flag they have to work around.
    #
    # `_strip_leading_punct_count` is a global counter that lets callers
    # (build_positions_db.py) emit a "stripped N PNs in this file" log
    # line. It's reset per file via `reset_normalize_counters()`.
    if rule.get("_strip_leading_punct"):
        stripped = s.lstrip(".,;:•·*")
        if stripped != s:
            _NORMALIZE_COUNTERS["leading_punct"] += 1
            s = stripped

    # 4. Collapse internal whitespace where forbidden
    if rule.get("no_spaces"):
        s = re.sub(r"\s+", "", s)

    # 5. Uppercase
    if rule.get("uppercase"):
        s = s.upper()

    # 6. Field-specific reverts
    if rule.get("revert_I_in_pn_prefix"):
        s = _revert_I_in_pn_prefix(s)

    if not s:
        # Optional columns: rule sets allow_empty so empty is silent.
        if not rule.get("allow_empty"):
            issues.append("empty")
        return s, issues

    # 7. Pattern validation
    pat = rule.get("pattern")
    if pat and not re.match(pat, s):
        issues.append("bad_format")

    # 8. Numeric range — two-tier:
    #    int_range        — HARD bound. Out-of-range → `out_of_range`.
    #    int_range_review — SOFT bound (strictly tighter than int_range).
    #                       Inside the hard bound but outside the soft one →
    #                       `over_review_band`. Used to surface rows for
    #                       analyst review without flagging them as junk.
    # Accepts thousand-separated integers across the three conventions seen
    # in the corpus: comma (23,443), dot (23.443) and apostrophe (23'443).
    rng = rule.get("int_range")
    rev = rule.get("int_range_review")
    if rng or rev:
        n: int | None
        if rule.get("strict_int") and s.isdigit():
            n = int(s)
        else:
            n = _parse_thousands_int(s)
        if n is None:
            if s:
                issues.append("not_a_number")
        else:
            if rng:
                lo, hi = rng
                if not (lo <= n <= hi):
                    issues.append("out_of_range")
                elif rev:
                    rlo, rhi = rev
                    if not (rlo <= n <= rhi):
                        issues.append("over_review_band")
            elif rev:
                rlo, rhi = rev
                if not (rlo <= n <= rhi):
                    issues.append("over_review_band")

    return s, issues


_THOUSANDS_RE = re.compile(r"^[-+]?\d{1,3}(?:[,.\']\d{3})*$|^[-+]?\d+$")


def _parse_thousands_int(s: str) -> int | None:
    """Parse an integer that may carry comma / dot / apostrophe thousands
    separators. Returns None if `s` isn't a clean integer of any supported
    flavour. Decimals are rejected — these fields should be whole cycles."""
    s = s.strip()
    if not s:
        return None
    if not _THOUSANDS_RE.match(s):
        return None
    cleaned = s.replace(",", "").replace("'", "").replace(".", "")
    try:
        return int(cleaned)
    except ValueError:
        return None


def forward_fill_ata(records: list[dict], lo: int = 20, hi: int = 83,
                     col: str = "ATA") -> list[dict]:
    """Forward-fill the ATA column where empty, using the most recent valid value.

    A value is considered valid when it's a 1-3 digit string whose integer form
    is within [lo, hi]. Rows whose ATA is filled this way receive an
    `_imputed:ATA` marker appended to their `_issues` field so the analyst can
    distinguish source data from imputed data.

    Returns the same list (records mutated in place) for convenience.
    """
    current = ""
    for rec in records:
        raw = str(rec.get(col, "")).strip()
        if raw.isdigit() and lo <= int(raw) <= hi:
            current = raw.zfill(2)
            rec[col] = current
        elif raw == "" and current:
            rec[col] = current
            existing = rec.get("_issues", "")
            tag = "_imputed:ATA"
            if existing:
                bits = [b for b in existing.split(",") if b != f"{col}:empty"]
                bits.append(tag)
                rec["_issues"] = ",".join(bits)
            else:
                rec["_issues"] = tag
    return records


def _maybe_check_pn_master(record: dict, issue_bits: list[str]) -> None:
    """If a PN master Bloom filter is loaded, add `_pn_known` to the record
    and append `PART_NUMBER:unknown_pn` to issues when the PN isn't recognised.
    Silently no-op when no master is bundled."""
    try:
        from shared import pn_master   # local import: avoid hard dep at module load
    except Exception:
        return
    if not pn_master.is_loaded():
        return
    pn = record.get("PART_NUMBER")
    if pn is None:
        return
    pn_str = str(pn).strip()
    if not pn_str:
        return
    known = pn_master.is_known_pn(pn_str)
    record["_pn_known"] = known
    if known is False:
        issue_bits.append("PART_NUMBER:unknown_pn")


_MONTH_MAP = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
    "JANUARY": 1, "FEBRUARY": 2, "MARCH": 3, "APRIL": 4, "JUNE": 6,
    "JULY": 7, "AUGUST": 8, "SEPTEMBER": 9, "OCTOBER": 10,
    "NOVEMBER": 11, "DECEMBER": 12,
    "ENE": 1, "FEV": 2, "ABR": 4, "MAI": 5, "AGO": 8, "SET": 9,
    "OUT": 10, "DEZ": 12, "DIC": 12,
}

_DATE_PATTERNS = [
    re.compile(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$"),
    re.compile(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})$"),
    re.compile(r"^(\d{1,2})[-/.]([A-Za-z]{3,9})[-/.](\d{4})$"),
    re.compile(r"^(\d{1,2})[-/.]([A-Za-z]{3,9})[-/.](\d{2})$"),
    re.compile(r"^([A-Za-z]{3,9})[-/.\s](\d{1,2})[-/.,\s]+(\d{4})$"),
    re.compile(r"^([A-Za-z]{3,9})[-/.\s](\d{1,2})[-/.,\s]+(\d{2})$"),
    re.compile(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{2})$"),
]


def normalize_date(value: str) -> str:
    """Convert a date string to ISO 8601 (YYYY-MM-DD).

    Handles the formats seen across the aviation PDF corpus:
        2024-05-13, 13/05/2024, 13-May-24, 13.05.2024, 20-May-05,
        May 13, 2024, 13/05/24, 13.Mai.2024, etc.

    Returns the original string unchanged if parsing fails.
    """
    s = value.strip()
    if not s:
        return s
    s = normalize_dashes(s)
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return s

    for i, pat in enumerate(_DATE_PATTERNS):
        m = pat.match(s)
        if not m:
            continue
        try:
            g1, g2, g3 = m.group(1), m.group(2), m.group(3)
            if i == 0:
                y, mo, d = int(g1), int(g2), int(g3)
            elif i == 1:
                d, mo, y = int(g1), int(g2), int(g3)
            elif i in (2, 3):
                d = int(g1)
                mo = _MONTH_MAP.get(g2.upper())
                if mo is None:
                    continue
                y = int(g3)
            elif i in (4, 5):
                mo = _MONTH_MAP.get(g1.upper())
                if mo is None:
                    continue
                d = int(g2)
                y = int(g3)
            elif i == 6:
                d, mo, y = int(g1), int(g2), int(g3)
            else:
                continue

            if y < 100:
                y += 2000 if y <= 50 else 1900
            dt = datetime(y, mo, d)
            return dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            continue
    return value


DATE_COLUMNS = frozenset({
    "INSTALL_DATE", "DATE", "LAST_DONE_DATE", "NEXT_DUE_DATE",
    "REMOVAL_DATE", "EXPIRY_DATE", "OVERHAUL_DATE", "MANUFACTURE_DATE",
    "LAST_SHOP_VISIT_DATE", "FITMENT_DATE", "COMPLIANCE_DATE",
    "DUE_DATE", "LAST_DATE", "DONE_DATE", "CERT_DATE", "D.O.M",
})


def normalize_dates_in_record(record: dict) -> dict:
    """Normalise all date-like columns in a record to ISO 8601."""
    for col in record:
        if col.startswith("_"):
            continue
        if col.upper() in DATE_COLUMNS or col.upper().endswith("_DATE"):
            val = record[col]
            if isinstance(val, str) and val.strip():
                record[col] = normalize_date(val)
    return record


CANONICAL_ORDER_OCCM = [
    "ATA", "PART_NUMBER", "SERIAL_NUMBER", "DESCRIPTION",
    "POSITION", "FIN", "INSTALL_DATE", "REMARKS",
]
CANONICAL_ORDER_HT = [
    "ATA", "PART_NUMBER", "SERIAL_NUMBER", "DESCRIPTION",
    "POSITION", "FIN", "MPD_TASK", "INTERVAL",
    "LAST_DONE_DATE", "NEXT_DUE_DATE", "REMAINING",
]
CANONICAL_ORDER_LLP = [
    "ATA", "PART_NUMBER", "SERIAL_NUMBER", "DESCRIPTION",
    "POSITION", "CYCLES_LIMIT", "CYCLES_TSN", "CYCLES_REMAINING",
]

_CANONICAL_ORDERS = {
    "OCCM": CANONICAL_ORDER_OCCM,
    "HT": CANONICAL_ORDER_HT,
    "LLP": CANONICAL_ORDER_LLP,
}


def canonical_column_order(columns: list[str], sheet_type: str) -> list[str]:
    """Reorder columns to a canonical order for the given sheet type.

    Known columns appear first in canonical order. Remaining columns
    (variant-specific extras) follow in their original order. Internal
    columns (_issues, _page, etc.) always come last.
    """
    order = _CANONICAL_ORDERS.get(sheet_type, [])
    order_set = set(order)
    internal = [c for c in columns if c.startswith("_")]
    normal = [c for c in columns if not c.startswith("_")]
    ordered = [c for c in order if c in set(normal)]
    extras = [c for c in normal if c not in order_set]
    return ordered + extras + internal


def clean_record(record: dict, column_rules: dict) -> dict:
    """Apply rules across a record. Adds an `_issues` field summarizing problems.

    If a PN master Bloom filter is loaded (`shared/pn_master.bloom`), each
    record additionally gets a `_pn_known: True/False` field; PNs that aren't
    in the master appear as `PART_NUMBER:unknown_pn` in `_issues`. With no
    master loaded, this is a silent no-op."""
    issue_bits: list[str] = []
    for col, val in list(record.items()):
        if col.startswith("_"):
            continue
        cleaned, issues = clean_cell(str(val), column_rules.get(col))
        record[col] = cleaned
        for iss in issues:
            issue_bits.append(f"{col}:{iss}")
    _maybe_check_pn_master(record, issue_bits)
    record["_issues"] = ",".join(issue_bits)
    return record
