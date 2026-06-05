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
"""
from __future__ import annotations
import re
from typing import Tuple, List


# Unicode dash variants that PDF writers occasionally emit instead of the
# plain ASCII U+002D hyphen-minus. These break regex anchors that expect
# `-` (e.g. date patterns, part-number shapes). MSN507 OCCM uses U+2010
# throughout; other corpus files have shown U+2011/2013/2014/2212.
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


def clean_cell(value: str, rule: dict | None) -> Tuple[str, List[str]]:
    issues: List[str] = []
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


def _maybe_check_pn_master(record: dict, issue_bits: List[str]) -> None:
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


def clean_record(record: dict, column_rules: dict) -> dict:
    """Apply rules across a record. Adds an `_issues` field summarizing problems.

    If a PN master Bloom filter is loaded (`shared/pn_master.bloom`), each
    record additionally gets a `_pn_known: True/False` field; PNs that aren't
    in the master appear as `PART_NUMBER:unknown_pn` in `_issues`. With no
    master loaded, this is a silent no-op."""
    issue_bits: List[str] = []
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
