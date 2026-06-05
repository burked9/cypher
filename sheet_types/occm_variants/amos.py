"""AMOS variant — Aircraft Equipment List Report (full text layer, L1).

Parser strategy
---------------
- pdfplumber returns one row per line on every page.
- The ATA section header is glued onto the *first* row of each ATA section,
  e.g. ``"21 AIR CONDITIONING 1209-100 8743 SWITCH-PRESSURE 30HQ ..."`` —
  we strip that prefix when present and update `current_ata`.
- ATA carries forward across pages: subsequent rows have no section header,
  so we propagate the most recent ATA seen.
- Each row is tokenized; the **INST_DATE** (dotted form like ``01.Sep.2005``)
  is the strong anchor. Working outward from the date:
    * `TSN`, `CSN`            — next two tokens after the date
    * `RELEASE_LABEL`         — ends at the date; contains a forward slash
                                token group (e.g. ``A/C DELIVERY / 24310``)
    * `POS` (optional)        — short alphanumeric like ``30HQ`` immediately
                                before the release label
    * `PART_NUMBER`, `SERIAL_NUMBER` — first two tokens of the row
    * `DESCRIPTION`           — everything between SN and POS (or release)
- Wrap continuations: AMOS occasionally splits a long description across two
  lines (e.g. ``... PRESSU\nRE``). If the next line is short / alpha / starts
  with punctuation, it's appended to the previous record's DESCRIPTION.

Status: this parser handles the canonical AMOS layout. Edge cases (mid-row
description tokens that look like POS, releases without spaces around the
slash) are flagged via the soft-validation `_issues` column so an analyst can
spot them.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "AMOS"
SIGNATURES = [
    # Vendor / product signatures — present on AMOS-generated reports
    "AMOS",
    "swiss-as.com",
    "Aircraft Equipment List Report",
    # Column-header signatures — catch AMOS-format OCCMs that don't carry
    # the AMOS/Swiss-AS string in the header (operator-rebranded reports,
    # e.g. "OCCM-List <REG> MSN <N>" output). The column sequence
    # `PART NO. SERIAL NO. DESCRIPTION POS.` is highly distinctive — every
    # other variant orders columns differently.
    "PART NO. SERIAL NO. DESCRIPTION POS.",
    # Permissive variant (no full stops in some operators' renames)
    "PART NO SERIAL NO DESCRIPTION POS",
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
]

_OVERRIDES = {
    # AMOS section headers carry "21", "21-22", or "21-22-15" — accept the
    # dash-suffix forms. The base ATA rule only accepts "21" and would
    # flag every dashed value as bad_format.
    "ATA": {"pattern": r"^\d{2}(?:-\d{2}){0,2}$", "int_range": None},
    # POS is legitimately absent on ~63% of AMOS rows in this corpus (no
    # position recorded in the source PDF). Treat empty as silent — its
    # absence isn't an extraction failure.
    "POS": {"pattern": r"^[A-Z0-9]{2,10}$", "uppercase": True, "allow_empty": True},
    "RELEASE_LABEL": {"allow_empty": True},
    "INST_DATE": {"pattern": r"^\d{1,2}\.[A-Za-z]{3}\.\d{4}$"},
    "TSN": {},
    "CSN": {},
}
RULES = merged_rules(_OVERRIDES)

_DATE_RE = re.compile(r"^\d{1,2}\.[A-Za-z]{3}\.\d{4}$")
_SECTION_PREFIX_RE = re.compile(
    # ATA on AMOS section headers is `21`, `21-22`, or `21-22-15` — accept all
    # three. Without the dash-suffix forms the prefix never matches on AMOS
    # exports that use subchapter notation, leaving every subsequent row with
    # ATA empty (the source of ~15k AMOS ATA:empty flags).
    r"^(?P<ATA>\d{2}(?:-\d{2}){0,2})\s+(?P<SECTION>[A-Z][A-Z &/,\-]*[A-Z])\s+(?P<REST>\S.+)$"
)
# A POS code is short, all-uppercase-alphanumeric, with both letters and digits
_POS_RE = re.compile(r"^[A-Z0-9]{2,10}$")


def _looks_like_pos(token: str) -> bool:
    if not _POS_RE.match(token):
        return False
    has_alpha = any(c.isalpha() for c in token)
    has_digit = any(c.isdigit() for c in token)
    return has_alpha and has_digit


def _parse_row_tokens(tokens: list[str]) -> dict | None:
    """Parse a token list as a single AMOS data row. Returns dict or None."""
    if len(tokens) < 6:
        return None

    # Find the date anchor
    date_idx = None
    for i, t in enumerate(tokens):
        if _DATE_RE.match(t):
            date_idx = i
            break
    if date_idx is None:
        return None
    if date_idx + 2 >= len(tokens):
        return None  # no TSN/CSN after date
    if date_idx < 3:
        return None  # need at least PN, SN, something before date

    inst_date = tokens[date_idx]
    tsn = tokens[date_idx + 1]
    csn = tokens[date_idx + 2]
    # Anything past CSN is trailing junk — captured to _trailer
    trailer = " ".join(tokens[date_idx + 3:]) if date_idx + 3 < len(tokens) else ""

    # The release label always ends with " / <ID>". Find the standalone "/"
    # token (or a slash-bearing compound that's the rightmost release marker).
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

    # POS detection: walk back from the slash region looking for the nearest
    # POS-like token within a small window. POS is short, mixed alpha+digit
    # uppercase like "30HQ", "11HB", "4022HM". This anchors the release label's
    # left boundary correctly even when releases span multiple words such as
    # "A/C DELIVERY / 24310" or "TREE-REC:JPCRS107 / 60219".
    search_anchor = standalone_slash_idx if standalone_slash_idx is not None else embedded_slash_idx
    pos_idx = None
    # Only look back a few tokens — release labels rarely extend further than
    # ~5 tokens left of the slash.
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
        # No POS — use the slash region's left edge as best-effort release start.
        # For standalone "/" the release is "<word> / <id>" (3 tokens) at minimum.
        # For embedded "/" the release starts at that token.
        if standalone_slash_idx is not None:
            release_start = standalone_slash_idx - 1
        else:
            release_start = embedded_slash_idx
        desc_end_excl = release_start

    if release_start < 2 or desc_end_excl < 2:
        return None  # need PN + SN ahead of description
    if desc_end_excl < 3:
        return None  # need PN, SN, then description

    pn = tokens[0]
    sn = tokens[1]
    desc = " ".join(tokens[2:desc_end_excl])
    release_label = " ".join(tokens[release_start:date_idx])

    record = {
        "PART_NUMBER": pn,
        "SERIAL_NUMBER": sn,
        "DESCRIPTION": desc,
        "POS": pos,
        "RELEASE_LABEL": release_label,
        "INST_DATE": inst_date,
        "TSN": tsn,
        "CSN": csn,
    }
    if trailer:
        record["_trailer"] = trailer
    return record


def _strip_section_prefix(line: str) -> tuple[str, str]:
    """Return (new_ata_or_empty, line_remainder). When a section prefix is
    present, we both update ATA and try to parse the remainder as a row."""
    m = _SECTION_PREFIX_RE.match(line)
    if not m:
        return "", line
    ata = m.group("ATA")
    # ata may be "21", "21-22", or "21-22-15". Validate the chapter part.
    chapter = int(ata.split("-")[0])
    if not (20 <= chapter <= 83 or chapter == 0):
        return "", line
    rest = m.group("REST")
    # Sanity: REST should contain a date — otherwise the prefix match was a
    # false positive and we should leave the line alone.
    if not _DATE_RE.search(" ".join(rest.split())):
        return ata, ""  # section header line only
    return ata, rest


def _is_wrap_continuation(line: str) -> bool:
    """Short, mostly letters/punctuation continuation of a previous description."""
    if len(line) > 20:
        return False
    if not line:
        return False
    # Reject anything that contains digits (looks like data)
    if any(c.isdigit() for c in line):
        return False
    # Allow a leading punctuation char (e.g. ",RAM AIR")
    return all(c.isalpha() or c.isspace() or c in ",.-" for c in line)


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    current_ata = ""

    # First pass: gather all lines across all pages with their page numbers
    all_lines: list[tuple[int, str]] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if len(text) < 100:
                continue
            for raw in text.splitlines():
                s = raw.strip()
                if s:
                    all_lines.append((page_num, s))

    last_record: dict | None = None
    for page_num, line in all_lines:
        # Strip ATA section prefix if present
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
            records.append(rec)
            last_record = rec
            continue

        # Wrap continuation?
        if last_record is not None and _is_wrap_continuation(line_to_parse):
            last_record["DESCRIPTION"] = (last_record["DESCRIPTION"] + line_to_parse).strip()
            continue

        last_record = None

    return records
