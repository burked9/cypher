"""AMOS-LLP variant — Component Equipment List Report for LLP-tracked parts.

Source format is structurally identical to the OCCM AMOS variant — same
producer (Swiss-AS AMOS, "Aircraft Equipment List Report" / "Component
Equipment List Report"), same `dd.Mmm.yyyy` install-date anchor, same
`A/C DELIVERY / 110969`-style release labels, same multi-line description
wraps.

What's different for LLP is that each data row is followed by a REQUIREMENT
row that carries the life-limit fields:

    32 LANDING GEAR 1840-0021 L1939 PIN/BOLT N LH MLG A/C DELIVERY / 110969 15.Dec.2011 19267:31 16229
    REQUIREMENT DIM DUE AT INTERVAL TSR EXPECTED TO GO
    LIFE LIMIT  C  56'000  56'000  16'229  04.Mar.2038  39'771 (71%)

Parser strategy: re-use the OCCM AMOS row-tokeniser for the data row, then
when the very next non-header line starts with "LIFE LIMIT", attach those
fields to the current record. Description wraps continue to work the same way.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.llp_variants._base import merged_rules

NAME = "AMOS LLP"
SIGNATURES = [
    "Component Equipment List Report",
    "produced by AMOS",
    "swiss-as.com",
    # Column-header signature (catches operator-rebranded copies)
    "PART NO. SERIAL NO. DESCRIPTION COND POS.",
    "REQUIREMENT DIM DUE AT INTERVAL TSR EXPECTED TO GO",
]

CANONICAL_COLUMNS = [
    "ATA",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
    "POS",
    "RELEASE_LABEL",
    "INST_DATE",
    "TSN",
    "CSN",
    # LLP-specific
    "LIFE_LIMIT_DIM",      # "C" = cycles, "F" = flight hours, "M" = months
    "DUE_AT",              # cycle (or hour) value at which due
    "INTERVAL",            # life-limit interval
    "TSR",                 # time-since-repair (cycles for LLP)
    "EXPECTED_DATE",
    "REMAIN_CYCLES",       # split out of original "39'771 (71%)" REMAINING
    "REMAIN_PCT",
]

# Hours can run to ~80k; cycles capped at 0..45000 per the engine-LLP rule.
# Landing-gear LLPs (cycle limits 50-80k) will trip the cycle range — that's
# intentional, it's a useful signal for the subject classifier downstream.
_HOUR_RULE  = {"pattern": r"^[\d',]+$", "int_range": (0, 80000)}
_CYCLE_RULE = {"pattern": r"^[\d',]+$", "int_range": (0, 55000),
               "int_range_review": (0, 30000)}
_OVERRIDES = {
    "POS": {"pattern": r"^[A-Z0-9]{2,10}$", "uppercase": True},
    "INST_DATE": {"pattern": r"^\d{1,2}\.[A-Za-z]{3}\.\d{4}$"},
    "EXPECTED_DATE": {"pattern": r"^\d{1,2}\.[A-Za-z]{3}\.\d{4}$"},
    "CSN":           _CYCLE_RULE,
    "DUE_AT":        _CYCLE_RULE,
    "INTERVAL":      _CYCLE_RULE,
    "TSR":           _CYCLE_RULE,
    "REMAIN_CYCLES": _CYCLE_RULE,
    "REMAIN_PCT":    {"pattern": r"^\d{1,3}%?$"},
}
RULES = merged_rules(_OVERRIDES)

_DATE_RE = re.compile(r"^\d{1,2}\.[A-Za-z]{3}\.\d{4}$")
_DATE_SEARCH_RE = re.compile(r"\b\d{1,2}\.[A-Za-z]{3}\.\d{4}\b")
_SECTION_PREFIX_RE = re.compile(
    r"^(?P<ATA>\d{2})\s+(?P<SECTION>[A-Z][A-Z &/,\-]*[A-Z])\s+(?P<REST>\S.+)$"
)
_POS_RE = re.compile(r"^[A-Z0-9]{2,10}$")
_NUM_RE = re.compile(r"^[\d',.]+$")  # AMOS uses ' as thousands separator: 56'000


def _looks_like_pos(token: str) -> bool:
    if not _POS_RE.match(token):
        return False
    has_alpha = any(c.isalpha() for c in token)
    has_digit = any(c.isdigit() for c in token)
    return has_alpha and has_digit


def _parse_row_tokens(tokens: list[str]) -> dict | None:
    """Parse a data row (the line *before* the LIFE LIMIT line)."""
    if len(tokens) < 6:
        return None

    date_idx = None
    for i, t in enumerate(tokens):
        if _DATE_RE.match(t):
            date_idx = i
            break
    if date_idx is None or date_idx + 2 >= len(tokens) or date_idx < 3:
        return None

    inst_date = tokens[date_idx]
    tsn = tokens[date_idx + 1]
    csn = tokens[date_idx + 2]

    # Release label ends with " / <ID>" — find the slash.
    standalone_slash_idx = None
    for i in range(date_idx - 1, -1, -1):
        if tokens[i] == "/":
            standalone_slash_idx = i
            break
    embedded_slash_idx = None
    if standalone_slash_idx is None:
        for i in range(date_idx - 1, -1, -1):
            if "/" in tokens[i]:
                embedded_slash_idx = i
                break
    if standalone_slash_idx is None and embedded_slash_idx is None:
        return None

    search_anchor = standalone_slash_idx if standalone_slash_idx is not None else embedded_slash_idx
    pos_idx = None
    for i in range(search_anchor - 1, max(search_anchor - 6, 1), -1):
        if _looks_like_pos(tokens[i]):
            pos_idx = i
            break

    has_pos = pos_idx is not None
    pos = tokens[pos_idx] if has_pos else ""

    if has_pos:
        release_start = pos_idx + 1
        desc_end_excl = pos_idx
    else:
        if standalone_slash_idx is not None:
            release_start = standalone_slash_idx - 1
        else:
            release_start = embedded_slash_idx
        desc_end_excl = release_start

    if release_start < 2 or desc_end_excl < 3:
        return None

    pn = tokens[0]
    sn = tokens[1]
    desc = " ".join(tokens[2:desc_end_excl])
    release_label = " ".join(tokens[release_start:date_idx])

    return {
        "PART_NUMBER": pn,
        "SERIAL_NUMBER": sn,
        "DESCRIPTION": desc,
        "POS": pos,
        "RELEASE_LABEL": release_label,
        "INST_DATE": inst_date,
        "TSN": tsn,
        "CSN": csn,
    }


_PCT_RE = re.compile(r"^\(?(\d{1,3})%?\)?$")


def _parse_life_limit_line(line: str) -> dict | None:
    """LIFE LIMIT C 56'000 56'000 16'229 04.Mar.2038 39'771 (71%)"""
    s = line.strip()
    if not s.upper().startswith("LIFE LIMIT"):
        return None
    rest = s[len("LIFE LIMIT"):].strip()
    toks = rest.split()
    if len(toks) < 4:
        return None
    date_idx = None
    for i, t in enumerate(toks):
        if _DATE_RE.match(t):
            date_idx = i
            break
    if date_idx is None or date_idx < 3:
        return None
    dim = toks[0]
    due_at = toks[date_idx - 3]
    interval = toks[date_idx - 2]
    tsr = toks[date_idx - 1]
    expected = toks[date_idx]
    # Split "39'771 (71%)" → REMAIN_CYCLES + REMAIN_PCT
    remain_cycles, remain_pct = "", ""
    tail = toks[date_idx + 1:]
    if tail:
        remain_cycles = tail[0]
        if len(tail) >= 2:
            m = _PCT_RE.match(tail[1])
            if m:
                remain_pct = m.group(1) + "%"
    return {
        "LIFE_LIMIT_DIM": dim,
        "DUE_AT": due_at,
        "INTERVAL": interval,
        "TSR": tsr,
        "EXPECTED_DATE": expected,
        "REMAIN_CYCLES": remain_cycles,
        "REMAIN_PCT": remain_pct,
    }


def _strip_section_prefix(line: str) -> tuple[str, str]:
    m = _SECTION_PREFIX_RE.match(line)
    if not m:
        return "", line
    ata = m.group("ATA")
    if not (20 <= int(ata) <= 83 or ata == "00"):
        return "", line
    rest = m.group("REST")
    if not _DATE_SEARCH_RE.search(rest):
        return ata, ""
    return ata, rest


def _is_wrap_continuation(line: str) -> bool:
    if len(line) > 25:
        return False
    if not line:
        return False
    if any(c.isdigit() for c in line):
        return False
    return all(c.isalpha() or c.isspace() or c in ",.-()" for c in line)


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    current_ata = ""

    all_lines: list[tuple[int, str]] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if len(text) < 50:
                continue
            for raw in text.splitlines():
                s = raw.strip()
                if s:
                    all_lines.append((page_num, s))

    last_record: dict | None = None
    for page_num, line in all_lines:
        # Skip the "REQUIREMENT DIM DUE AT INTERVAL ..." sub-header — it's
        # purely formatting and carries no data.
        if line.upper().startswith("REQUIREMENT") and "DUE AT" in line.upper():
            continue

        # LIFE LIMIT line → attach to the last record
        ll = _parse_life_limit_line(line)
        if ll is not None and last_record is not None:
            for k, v in ll.items():
                last_record[k] = v
            continue

        new_ata, remainder = _strip_section_prefix(line)
        if new_ata:
            current_ata = new_ata
            line_to_parse = remainder
        else:
            line_to_parse = line
        if not line_to_parse:
            last_record = None
            continue

        tokens = line_to_parse.split()
        rec = _parse_row_tokens(tokens)
        if rec is not None:
            rec["ATA"] = current_ata
            rec["_page"] = page_num
            # Initialise LLP columns so downstream code sees a stable schema
            for c in ("LIFE_LIMIT_DIM", "DUE_AT", "INTERVAL", "TSR",
                      "EXPECTED_DATE", "REMAIN_CYCLES", "REMAIN_PCT"):
                rec.setdefault(c, "")
            records.append(rec)
            last_record = rec
            continue

        if last_record is not None and _is_wrap_continuation(line_to_parse):
            last_record["DESCRIPTION"] = (last_record["DESCRIPTION"] + " " + line_to_parse).strip()
            continue

        # If we get here it wasn't a parseable line — but DON'T reset
        # last_record, because the LIFE LIMIT line might still be coming.
        # Only the REQUIREMENT sub-header / blank line reset works.

    return records
