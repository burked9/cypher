"""OCCM Component Inventory — "MSN <msn> OCCM COMPONENT INVENTORY" layout.

Real text layer (confirmed via a direct pdfplumber pass on a known source
file) -- no OCR needed, plain synchronous `extract()`.

Header (once per page)::

    MSN <msn> OCCM COMPONENT INVENTORY
    ORG Zone Part Description ATA Part Number Serial/Lot Number Pos Installed Date

Per-row layout (single line when it fits)::

    [ORG] DESCRIPTION... ATA PART_NUMBER SERIAL_OR_LOT_NUMBER [POS...] INSTALLED_DATE

Example (values genericized; token shapes preserved)::

    <org> SENSOR-EXAMPLE DESCRIPTION <ata> <pn> <sn> <pos> <date>

Fields, all confirmed directly against the known source file:

  - ORG: an org/zone-agent code shaped `[A-Z]{2}\\d{3}` (e.g. two letters
    then three digits). Frequently ABSENT -- many rows start directly with
    the description instead (confirmed on numerous rows in the known
    source file).
  - ZONE: present in the column header text, but never populated with a
    value on any row of the known source file -- the ATA column always
    follows description text directly, with no separate zone token
    between them. Kept in CANONICAL_COLUMNS for schema completeness (and
    in case another source file of this format does populate it) but
    always emitted empty here; there is no reliable token to anchor a
    zone value on even if one existed, since ATA/zone are both bare 2-3
    digit numbers and only ATA's known position (immediately before
    PART_NUMBER) is reliably anchorable.
  - PART_DESCRIPTION: free text, one or more words. ATA is the anchor:
    the first standalone 2-digit token in the ATA range (20-83) after
    any leading ORG code is treated as ATA, and everything between the
    (optional) ORG and that token is the description.
  - ATA / PART_NUMBER / SERIAL_OR_LOT_NUMBER: as per the header order.
  - POS: optional, zero or more trailing tokens between
    SERIAL_OR_LOT_NUMBER and INSTALLED_DATE (e.g. side/position codes).
    Confirmed non-ASCII single-character position values appear in the
    known source file (e.g. an ideographic "left"/"right" character used
    in place of "LH"/"RH") -- preserved verbatim, not transliterated.
  - INSTALLED_DATE: ISO `YYYY-MM-DD`.

Two rendering quirks confirmed directly against the known source file's
pdfplumber text layer, both handled here:

  1. Glued POS+DATE tokens. When a row's POS text is short, pdfplumber's
     line reconstruction sometimes emits it concatenated directly onto
     the following INSTALLED_DATE token with no space (e.g. a POS value
     "OUTBD" glued to a date literal). Detected by matching the ISO date
     pattern as a *suffix* of the last token rather than requiring the
     whole token to be a date; any leading text on that token is folded
     back into POS. A small number of rows show clearly spurious
     digit/slash-only prefixes glued the same way (confirmed on the
     known source file); these look like a rendering overlap artifact
     rather than real column text and are dropped rather than appended
     to POS.

  2. Multi-line PART_DESCRIPTION wrapping. When a description is too
     long to fit the row's other columns on one visual line, pdfplumber
     renders it as three consecutive physical lines: a description-only
     line, then the row's own ORG/ATA/PART_NUMBER/SERIAL_OR_LOT_NUMBER/
     POS/INSTALLED_DATE line (with an EMPTY description slot, since ATA
     immediately follows any ORG code with no description tokens between
     them), then a second description-only line. Confirmed directly
     against pdfplumber word coordinates on the known source file: both
     the leading and trailing description-only lines sit at the same
     x-position as the row's own description column, not the POS column,
     even when the trailing line is a short token that could otherwise be
     mistaken for a POS value. Handled here by: only pairing an adjacent
     description-only line to a data row when that row's own inline
     description came back empty (the reliable signal that a wrap
     happened), and consuming each description-only line at most once, so
     a normal (non-wrapped) row immediately following a wrapped one is
     never mistakenly re-fed the wrapped row's own trailing line.
     Joining: if the leading fragment ends in a literal hyphen, the next
     fragment is concatenated directly (mid-word split); otherwise a
     single space is inserted (separate-word split). Both shapes are
     confirmed present in the known source file.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "OCCM Component Inventory"
SIGNATURES = [
    "OCCM COMPONENT INVENTORY",
    "ORG Zone Part Description ATA Part Number Serial/Lot Number Pos Installed Date",
]

CANONICAL_COLUMNS = [
    "MSN",
    "ORG",
    "ZONE",
    "PART_DESCRIPTION",
    "ATA",
    "PART_NUMBER",
    "SERIAL_OR_LOT_NUMBER",
    "POS",
    "INSTALLED_DATE",
]

_OVERRIDES = {
    "MSN": {"pattern": r"^\d{3,6}$"},
    "ORG": {"pattern": r"^[A-Z]{2}\d{3}$", "uppercase": True, "allow_empty": True},
    # Never populated in the known source file -- see module docstring.
    "ZONE": {"pattern": r"^\d{2,3}$", "allow_empty": True},
    "PART_DESCRIPTION": {"uppercase": True},
    # ATA / PART_NUMBER already have suitable global rules keyed by these
    # exact column names (see shared/aviation_rules.py) -- no override
    # needed, merged_rules() picks them up automatically.
    "SERIAL_OR_LOT_NUMBER": {
        "pattern": r"^[A-Z0-9/](?:[A-Z0-9\-/]*[A-Z0-9/])?$",
        "uppercase": True,
    },
    "POS": {"allow_empty": True},
    "INSTALLED_DATE": {"pattern": r"^\d{4}-\d{2}-\d{2}$"},
}
RULES = merged_rules(_OVERRIDES)

_TITLE_RE = re.compile(r"^MSN\s+(\d+)\s+OCCM COMPONENT INVENTORY", re.I)
_HEADER_LINE_RE = re.compile(
    r"^ORG\s+Zone\s+Part\s+Description\s+ATA\s+Part\s+Number\s+"
    r"Serial/Lot\s+Number\s+Pos\s+Installed\s+Date$",
    re.I,
)
_FOOTER_PREFIXES = ("TITLE :", "SIGNATURE :", "DATE :")

_ORG_RE = re.compile(r"^[A-Z]{2}\d{3}$")
_ATA_TOKEN_RE = re.compile(r"^\d{2}$")
_ATA_LO, _ATA_HI = 20, 83
_DATE_SUFFIX_RE = re.compile(r"(\d{4}-\d{2}-\d{2})$")
_PURE_DIGIT_SLASH_RE = re.compile(r"^[\d/]+$")


def _is_noise_line(line: str) -> bool:
    if not line:
        return True
    if _TITLE_RE.match(line):
        return True
    if _HEADER_LINE_RE.match(line):
        return True
    if line.startswith(_FOOTER_PREFIXES):
        return True
    return False


def _parse_data_line(line: str) -> dict | None:
    """Parse one physical line as a full data row. Returns None if the line
    doesn't anchor on a trailing installed-date -- i.e. it's either noise
    or a bare description-continuation line to be picked up by the caller."""
    tokens = line.split()
    if len(tokens) < 4:
        return None
    last = tokens[-1]
    m = _DATE_SUFFIX_RE.search(last)
    if not m:
        return None
    date = m.group(1)
    glued_prefix = last[: m.start()]

    body = tokens[:-1]
    idx0 = 0
    org = ""
    if body and _ORG_RE.match(body[0]):
        org = body[0]
        idx0 = 1

    ata_idx = None
    for i in range(idx0, len(body)):
        t = body[i]
        if _ATA_TOKEN_RE.match(t):
            v = int(t)
            if _ATA_LO <= v <= _ATA_HI:
                ata_idx = i
                break
    if ata_idx is None:
        return None

    desc_tokens = body[idx0:ata_idx]
    ata = body[ata_idx]
    rest = body[ata_idx + 1:]
    if len(rest) < 2:
        return None
    pn, sn = rest[0], rest[1]
    pos_tokens = rest[2:]

    if glued_prefix and not _PURE_DIGIT_SLASH_RE.match(glued_prefix):
        # Genuine trailing POS text glued onto the date token (see
        # docstring quirk #1). A digit/slash-only prefix is dropped as a
        # rendering artifact instead.
        pos_tokens = pos_tokens + [glued_prefix]

    return {
        "org": org,
        "desc_tokens": desc_tokens,
        "ata": ata,
        "pn": pn,
        "sn": sn,
        "pos": " ".join(pos_tokens),
        "date": date,
    }


def _join_desc(parts: list[str]) -> str:
    if not parts:
        return ""
    result = parts[0]
    for p in parts[1:]:
        result = result + p if result.endswith("-") else result + " " + p
    return result


def _extract_page(text: str, page_num: int, msn: str) -> list[dict]:
    from shared.cleanup import normalize_dashes
    text = normalize_dashes(text)
    lines = [ln.strip() for ln in text.splitlines()]
    filtered = [ln for ln in lines if not _is_noise_line(ln)]
    n = len(filtered)
    parsed = [_parse_data_line(ln) for ln in filtered]

    consumed_loose: set[int] = set()
    records: list[dict] = []
    for i, p in enumerate(parsed):
        if p is None:
            continue
        own_desc = " ".join(p["desc_tokens"]).strip()
        parts: list[str] = []
        if own_desc:
            parts.append(own_desc)
        else:
            # Empty inline description is the reliable signal that this
            # row's description wrapped onto the neighbouring bare lines
            # (see docstring quirk #2).
            j = i - 1
            if j >= 0 and parsed[j] is None and j not in consumed_loose and filtered[j]:
                parts.append(filtered[j])
                consumed_loose.add(j)
            k = i + 1
            if k < n and parsed[k] is None and k not in consumed_loose and filtered[k]:
                parts.append(filtered[k])
                consumed_loose.add(k)

        rec = {
            "MSN": msn,
            "ORG": p["org"],
            "ZONE": "",
            "PART_DESCRIPTION": _join_desc(parts),
            "ATA": p["ata"],
            "PART_NUMBER": p["pn"],
            "SERIAL_OR_LOT_NUMBER": p["sn"],
            "POS": p["pos"],
            "INSTALLED_DATE": p["date"],
            "_page": page_num,
        }
        records.append(rec)
    return records


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    msn = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if len(text) < 20:
                continue
            if not msn:
                m = _TITLE_RE.match(text.strip().splitlines()[0]) if text.strip() else None
                if m:
                    msn = m.group(1)
            records.extend(_extract_page(text, page_num, msn))
    return records
