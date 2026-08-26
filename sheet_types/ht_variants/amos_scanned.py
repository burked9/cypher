"""AMOS "Aircraft Equipment List Report" — scanned copy, OCR required.

Same underlying template as the born-digital `amos.py` sibling in this
package (which wraps `sheet_types/occm_variants/amos.py`), but every known
source file in this cluster is a flat scanned image per page with **no
text layer at all** (confirmed via pdfplumber: 0 extractable chars on
every page of every file), so `amos.py`'s plain-pdfplumber signature match
never fires and the born-digital parser never sees this file. This module
renders each page and OCRs it directly instead — like several other
scanned HT/OCCM siblings in this project, it cannot run purely on
pdfplumber text and must never be imported unconditionally from the
router.

Layout, confirmed on real files in the corpus (a multi-line vertical HT
layout, values genericized below but the shape is real)::

    ATA | DESCRIPTION | PART NO. | SERIAL NO. | DESCRIPTION | POS. |
        RELEASE NO./LABEL NO. | INST-DATE | TSN | CSN
    <ata> <section-name> <part-no> <serial-no> <description> <pos> |
        <release-no>/<label-no> | <inst-date> | <tsn> | <csn>
    REQUIREMENT | TASKCARD | DIM | DUE AT | INTERVAL | TSR | EXPECTED | TOGO
    <action, e.g. BENCH CHECK/CLEANING/OVERHAUL/RESTORATION> | <taskcard> ...

Each equipment row is immediately followed by an HT-continuation pair (a
column-header line, then a values line) carrying REQUIREMENT/TASKCARD/
DUE AT/INTERVAL/TSR/EXPECTED/TOGO — mirrors the same continuation-line
shape `amos.py`'s docstring describes for the born-digital version of this
report. Those fields aren't required for this project's downstream use
(position fingerprint of HT components per airframe family), so this
parser skips both continuation lines entirely rather than try to recover
them from OCR noise.

OCR quality on the data grid is mediocre — a ruled/bordered table, small
print, and dense multi-column rows mean individual characters inside
PART_NUMBER/SERIAL_NUMBER regularly get misread (digits swapped for
letters, stray leading noise characters glued onto the first token of a
row from a misread border). Given that, only two things are trusted as
strong anchors, same idea as `occm_variants/sriwijaya_b737_occm.py`:

  * **INST-DATE** — matched via the month-name abbreviation (Jan..Dec),
    which OCRs far more reliably than the surrounding digits since it's
    3-4 known letter shapes rather than arbitrary digits/punctuation.
  * **RELEASE NO./LABEL NO.** — the nearest token containing a literal
    ``/`` walking backward from the date. TSN/CSN are then just the two
    tokens immediately after the date, and POS is the token immediately
    before the release token.

PART_NUMBER and SERIAL_NUMBER are recovered as the first two tokens after
the (optional) leading ATA + ATA-chapter-name pair, with a light noise
filter dropping short digit-free leading tokens (misread border glyphs).
This split is best-effort — occasional word leakage between the two
columns is expected on the noisiest rows — so both columns are kept
generously permissive (`allow_empty`, loose pattern) rather than validated
strictly, the same call the OCCM-side Sriwijaya sibling makes for its own
noisy columns.
"""
from __future__ import annotations
import re

from sheet_types.ht_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, page_count

NAME = "AMOS HT Aircraft Equipment List Report (Scanned)"

# Deliberately empty. Every known source file has no text layer at all, so
# this SIGNATURES list can never actually match through the router's plain
# pdfplumber text-signature path (see sheet_types/ht.py detect_variant) --
# a born-digital copy of this same report already routes to the amos.py
# sibling above it in ht.py's VARIANTS list, via SIGNATURES it shares with
# it ("Aircraft Equipment List Report" etc.). Detection for the scanned
# files this module targets happens structurally via ocr_detect() below,
# same pattern as aircraft_rotables_ht_scanned.py in this package.
SIGNATURES: list[str] = []

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
    "ATA": {"pattern": r"^\d{2}$", "int_range": None, "allow_empty": True},
    "PART_NUMBER": {"pattern": r"^[A-Z0-9][A-Z0-9\-]*$", "allow_empty": True,
                     "uppercase": True},
    "SERIAL_NUMBER": {"pattern": r"^[A-Z0-9][A-Z0-9\-/]*$", "allow_empty": True,
                       "uppercase": True},
    "DESCRIPTION": {"allow_empty": True},
    "POS": {"pattern": r"^[A-Z0-9\-]{1,12}$", "uppercase": True, "allow_empty": True},
    "RELEASE_LABEL": {"allow_empty": True},
    "INST_DATE": {"allow_empty": True},
    "TSN": {"allow_empty": True},
    "CSN": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_MONTH_RE = re.compile(r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|0ct|Nov|Dec)", re.I)
_YEAR_RE = re.compile(r"\d{4}")
# Border/leader glyphs OCR sometimes emits as their own tokens (misread
# table rules, indentation dots) -- never real data. Underscores/dots/
# hyphens in runs of 2+ are the same kind of artifact; single ASCII
# hyphens inside part numbers and dates are left alone.
_BORDER_RE = re.compile(r"[|\[\]<>=~()`*\"'«»‘’“”–—_]+")
_SEP_RUN_RE = re.compile(r"_{2,}|\.{3,}|-{3,}")
# Continuation-block header/value lines and page furniture -- never a data
# row, so skipped outright rather than fed to the date-anchor parser.
_SKIP_RE = re.compile(
    r"REQUIREMENT|TASKCARD|DUE\s*AT|INTERVAL|TOGO|EXPECTED|"
    r"Aircraft\s+Equipment|Page\s+\d|All\s+rotables|Sub\s+items|"
    r"Group\s+by|A/?C\s+Data", re.I)
_ACTION_RE = re.compile(
    r"^(BENCH\s*CHECK|CLEANING|OVERHAUL|RESTORATION|REPLACE|INSPECT|"
    r"REPAIR|TEST|DISCARD|CHECK)\b", re.I)
_ATA_TOK_RE = re.compile(r"^\d{2}$")


def _clean_line(line: str) -> str:
    s = _SEP_RUN_RE.sub(" ", _BORDER_RE.sub(" ", line))
    return " ".join(s.split())


def _find_date_idx(tokens: list[str]) -> tuple[int, int] | None:
    """Locate the INST-DATE anchor -- either a single token carrying both
    the month name and a 4-digit year, or a month-only token immediately
    followed by a separate year token (OCR occasionally splits the two)."""
    for i, t in enumerate(tokens):
        if _MONTH_RE.search(t):
            if _YEAR_RE.search(t):
                return i, i
            if i + 1 < len(tokens) and _YEAR_RE.search(tokens[i + 1]):
                return i, i + 1
    return None


def _has_digit(tok: str) -> bool:
    return any(c.isdigit() for c in tok)


def _parse_line(line: str, cur_ata: str, page_num: int) -> tuple[dict, str] | None:
    line = _clean_line(line)
    if not line or _SKIP_RE.search(line) or _ACTION_RE.match(line):
        return None
    toks = line.split()
    if len(toks) < 5:
        return None

    d = _find_date_idx(toks)
    if d is None:
        return None
    d0, d1 = d
    if d1 + 2 >= len(toks):
        return None
    inst_date = " ".join(toks[d0:d1 + 1])
    tsn, csn = toks[d1 + 1], toks[d1 + 2]

    # RELEASE NO./LABEL NO. is the nearest slash-bearing token walking back
    # from the date -- capped so an unrelated "/" earlier in the row (rare)
    # doesn't get picked up.
    rel_idx = None
    for i in range(d0 - 1, max(d0 - 6, -1), -1):
        if "/" in toks[i]:
            rel_idx = i
            break
    if rel_idx is None:
        return None
    pos_idx = rel_idx - 1 if rel_idx - 1 >= 0 else None
    limit = pos_idx if pos_idx is not None else rel_idx

    ata = cur_ata
    start = 0
    new_section = False
    if _ATA_TOK_RE.match(toks[0]):
        ata = toks[0]
        start = 1
        new_section = True
    # A new ATA section's first row carries the chapter name (a long
    # alphabetic word, e.g. "GENERAL", "PRESSURIZATION") ahead of the real
    # PART_NUMBER -- skip it, but only right after a fresh ATA token, so an
    # ordinary description word later in the row is never mistaken for one.
    if new_section and start < limit and toks[start].isalpha() and len(toks[start]) >= 4:
        start += 1
    # Misread border glyphs land as short digit-free tokens ("PT", "id") --
    # skip them too; real part numbers always carry at least one digit.
    while start < limit and not _has_digit(toks[start]) and len(toks[start]) <= 3:
        start += 1
    if start + 2 > limit:
        return None

    pn, sn = toks[start], toks[start + 1]
    desc = " ".join(toks[start + 2:limit])
    pos = toks[pos_idx] if pos_idx is not None else ""
    release = toks[rel_idx]

    record = {
        "ATA": ata,
        "PART_NUMBER": pn,
        "SERIAL_NUMBER": sn,
        "DESCRIPTION": desc,
        "POS": pos,
        "RELEASE_LABEL": release,
        "INST_DATE": inst_date,
        "TSN": tsn,
        "CSN": csn,
        "_page": page_num,
    }
    return record, ata


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback (see
    sheet_types/ht.py) -- this variant's SIGNATURES is deliberately empty
    (see module docstring) since every known source file has no text
    layer at all.

    Anchors on the report title, which OCRs cleanly even though the data
    grid below it doesn't, plus the "Requirements:" checkbox line that
    sits directly under the aircraft header on every known file -- present
    on this report but not on other scanned HT siblings that route through
    the same OCR fallback (e.g. aircraft_rotables_ht_scanned.py's form has
    no such checkbox row).
    """
    try:
        img = await render_page(pdf_path, 0, dpi=300)
        w, h = img.size
        crop = img.crop((0, 0, w, int(h * 0.3)))
        text = (await ocr_text(crop, psm=6)).upper()
        return ("EQUIPMENT" in text and "REPORT" in text
                and "REQUIREMENT" in text)
    except Exception:
        return False


async def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    n_pages = await page_count(pdf_path)
    cur_ata = ""
    for page_index in range(n_pages):
        img = await render_page(pdf_path, page_index, dpi=300)
        text = await ocr_text(img, psm=6)
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            result = _parse_line(line, cur_ata, page_index + 1)
            if result is not None:
                rec, cur_ata = result
                records.append(rec)
    return records
