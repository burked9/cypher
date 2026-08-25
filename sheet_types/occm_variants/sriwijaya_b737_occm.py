"""Sriwijaya Air B737-85P OCCM — scanned, no text layer, OCR required.

Confirmed on a small cluster of real files in the corpus (real-corpus
triage): several page-range "Form TP-015" exports of the same underlying
report, plus the full multi-page original those slices were taken from.
All known files are a single flat scanned image per page with **no text
layer at all** (confirmed via pdfplumber: 0 chars, 1 embedded image, on
every page of every file), so this module renders each page and OCRs it
directly via pytesseract — like Part M / N3 Engine Overhaul LLP elsewhere
in this project, it cannot run under Pyodide and must never be imported
unconditionally from the router. See the try/except around this import in
`sheet_types/occm.py`.

Header, every page (OCR'd cleanly despite the noisy grid below it, values
genericized below but the layout/shape is real)::

    ON CONDITION AND CONDITION MONITORING AIRCRAFT COMPONENTS STATUS
    Sriwijaya Air   AIRCRAFT TYPE/MODEL : B737-85P   CURRENT DATE : <date>
                    ACRF REG. : <registration>       ACRF TSN : <tsn>
    MAINTENANCE PLANNING AND CONTROL   SN: <msn>; LN: <line_no>; VN: <vn>   ACRF CSN : <csn>

Same 14-column template as the existing `on_condition_monitoring_occm`
sibling (ATA QTY INDEX TYPE DESCRIPTION PART_NUMBER SERIAL_NUMBER POSITION
INSTALL_DATE TSN CSN HOURS CYCLES DAYS) — this is the same underlying
form, just a scanned copy that variant's plain-pdfplumber text extraction
never sees (head text is empty, so its SIGNATURES never get compared
against anything).

OCR quality is poor specifically on the data grid: a dotted/ruled leader
between sparse columns regularly gets misread as runs of letters
("Ss——«", "CCCC") rather than symbols a simple border-character strip
could catch, and the decimal point in the trailing numeric block is
unreliably dropped ("31413") or split into its own token ("6 875" for
"6.875"). Real example row (OCR'd, whitespace as printed)::

    21 2 1 OM AirConditionerCheck Valve 3z02N4e-t 1363 LH Otay 18 4 56.819 31413 6 875

Given that, only two anchors are trusted: the leading ATA/QTY/INDEX/TYPE
block (OCRs reliably — small integers and a 2-letter code), and the
trailing run of numeric-looking tokens walked back from EOL (tolerant of
the dropped/split decimal above, and of stray non-digit characters glued
to a token by a misread leader dot). Everything between them —
DESCRIPTION, PART_NUMBER, SERIAL_NUMBER, POSITION, INSTALL_DATE — is
corrupted too unpredictably to split with any confidence (unlike the
clean-text sibling, which anchors on the date to walk backward for these
fields) and is kept together as DESCRIPTION rather than guess at a field
boundary and risk a confidently wrong PART_NUMBER — the same call
`standard_occm.py` makes for its A305 sub-format. A wrong DESCRIPTION
split would be worse than none for cross-operator part-pricing use, since
nothing downstream re-checks it against the source scan.
"""
from __future__ import annotations
import re

from sheet_types.occm_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, page_count

NAME = "Sriwijaya B737-85P OCCM (Scanned)"

# Never actually fires through the router's normal text-signature match --
# every known source file has no text layer at all (see module docstring).
# Kept for interface consistency and in case a born-digital copy turns up.
# More specific than the generic title `on_condition_monitoring_occm` owns
# (airframe sub-model, not just the shared form title) so a born-digital
# copy of THIS operator/airframe routes here rather than to that generic
# sibling, PROVIDED this module is registered ahead of it in occm.py's
# VARIANTS list -- real detection for the scanned files this module was
# actually built for happens via ocr_detect() below, independent of list
# order (see that function's own docstring).
SIGNATURES = [
    "AIRCRAFT TYPE/MODEL : B737-85P",
]

CANONICAL_COLUMNS = [
    "ATA",
    "QTY",
    "INDEX",
    "TYPE",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "POSITION",
    "INSTALL_DATE",
    "TSN",
    "CSN",
    "HOURS",
    "CYCLES",
    "DAYS",
]

# Trailing figures print with a European dotted-thousands style (54.866 =
# 54866) and OCR drops or relocates the dot unpredictably -- same call
# `on_condition_monitoring_occm.py` makes for its clean-text sibling: kept
# as raw strings rather than validated against an int_range.
_NUM_RULE = {"pattern": r"^[\d.,]+$", "allow_empty": True}
_OVERRIDES = {
    "QTY":           {"pattern": r"^\d{1,3}$"},
    "INDEX":         {"pattern": r"^\d{1,3}$"},
    "TYPE":          {"pattern": r"^[A-Z]{2}$"},
    # Always empty from this variant -- see module docstring.
    "PART_NUMBER":   {"allow_empty": True},
    "SERIAL_NUMBER": {"allow_empty": True},
    "POSITION":      {"allow_empty": True},
    "INSTALL_DATE":  {"allow_empty": True},
    "TSN": _NUM_RULE, "CSN": _NUM_RULE, "HOURS": _NUM_RULE,
    "CYCLES": _NUM_RULE, "DAYS": _NUM_RULE,
}
RULES = merged_rules(_OVERRIDES)

# Every row prints inside a ruled table -- pipes, brackets and stray "="/"~"
# from broken gridlines OCR as their own standalone tokens (raw, unlike the
# hand-cleaned samples in the module docstring), which would otherwise shift
# every positional token index off by one. Strip them before tokenizing, same
# idea as n3_engine_overhaul_llp.py's `_NOISE_RE`. Em/en-dash and 2+ runs of
# underscore/dot/hyphen are the misread dotted leader between sparse columns
# -- never real data, unlike the single ASCII hyphens inside part numbers and
# dates, which this deliberately leaves alone.
_BORDER_RE = re.compile(r"[|\[\]<>=~()`*\"'«»‘’“”–—]+")
_SEP_RUN_RE = re.compile(r"[_]{2,}|\.{3,}|-{3,}")

# Optional single leading letter absorbs a leader/border glyph OCR misread
# as a letter instead of a symbol ("L21" for "21") -- confirmed against the
# noisiest known scan, where a plain border-character strip wouldn't help
# since the artifact IS a letter, not a stray symbol.
_ATA_TOK_RE = re.compile(r"^[A-Za-z]?(\d{2})$")
# A lone unrecovered digit in this position OCRs as "+" often enough (seen
# in QTY/INDEX on multiple files) to accept and pass through as-is rather
# than drop an otherwise-good row over it -- character-level cleanup of the
# survivors is RULES/OCR_CHAR_MAP's job (shared/aviation_rules.py), not
# extract()'s.
_INT_TOK_RE = re.compile(r"^(\d{1,3}|\+)$")
_TYPE_TOK_RE = re.compile(r"^[A-Za-z]{2}$")


def _num_core(tok: str) -> str | None:
    """True numeric fields here never mix letters with digits; a corrupted
    date like "Ot-May-99" does (and must NOT be mistaken for a trailing
    TSN/CSN/HOURS/CYCLES/DAYS token just because it ends in digits, or the
    whole trailing block shifts). Tolerate at most one stray leading
    character (a border glyph or digit misread as a letter, e.g. "S14" for
    "14") and a single embedded hyphen standing in for a dropped decimal
    point ("34-413" for "34.413") -- both confirmed OCR failure modes here,
    unlike a genuine letter run anywhere else in the token.
    """
    if not tok:
        return None
    body = tok if tok[0].isdigit() else tok[1:]
    if not body or not re.fullmatch(r"[\d.,/-]+", body) or not any(c.isdigit() for c in body):
        return None
    return body.replace("-", ".").replace("/", "")


def _is_noise_tok(tok: str) -> bool:
    """A lone stray punctuation mark (a border glyph split from its
    neighbour by whitespace the OCR pass introduced, e.g. a "]" that landed
    on its own) -- skip over it rather than let it look like the end of the
    trailing numeric block, but don't skip anything with a real letter in
    it (that's the date/description boundary, and must still stop the
    walk)."""
    return bool(tok) and not any(c.isalnum() for c in tok)


def _parse_line(line: str, page_num: int) -> dict | None:
    s = _SEP_RUN_RE.sub(" ", _BORDER_RE.sub(" ", line))
    toks = s.split()
    if len(toks) < 9:
        return None

    m = _ATA_TOK_RE.match(toks[0])
    if not m:
        return None
    ata_int = int(m.group(1))
    if not (20 <= ata_int <= 83):
        return None
    if not (_INT_TOK_RE.match(toks[1]) and _INT_TOK_RE.match(toks[2])):
        return None
    if not _TYPE_TOK_RE.match(toks[3]):
        return None

    # Walk back from EOL collecting numeric-ish tokens (TSN/CSN/HOURS/
    # CYCLES/DAYS), tolerant of a dropped or space-split decimal point.
    # Capped so a row with no real trailing block doesn't eat the header.
    trail: list[str] = []
    i = len(toks) - 1
    while i >= 4 and len(trail) < 7:
        core = _num_core(toks[i])
        if core is not None:
            trail.insert(0, core)
        elif not _is_noise_tok(toks[i]):
            break
        i -= 1
    if len(trail) < 4:
        return None

    middle = toks[4:i + 1]
    if not middle:
        return None

    tsn, csn, hours, cycles = trail[:4]
    # >4 leftover tokens means the decimal point split DAYS into two OCR
    # tokens (see module docstring) -- rejoin rather than drop the extras.
    days = ".".join(trail[4:]) if len(trail) > 4 else ""

    return {
        "ATA": m.group(1),
        "QTY": toks[1],
        "INDEX": toks[2],
        "TYPE": toks[3].upper(),
        "DESCRIPTION": " ".join(middle),
        "PART_NUMBER": "",
        "SERIAL_NUMBER": "",
        "POSITION": "",
        "INSTALL_DATE": "",
        "TSN": tsn,
        "CSN": csn,
        "HOURS": hours,
        "CYCLES": cycles,
        "DAYS": days,
        "_page": page_num,
    }


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback (see
    sheet_types/occm.py) -- this variant's SIGNATURES can never match
    through the normal pdfplumber text-extract path since every known
    source file has no text layer at all.

    Anchors on the title line, which OCRs clean on every known file even
    though the data grid below it doesn't (see module docstring), plus
    "85P" to stay specific to this airframe sub-model rather than shadow a
    born-digital B737-800 file that should route to the plain-text
    `on_condition_monitoring_occm` sibling instead.
    """
    try:
        img = await render_page(pdf_path, 0, dpi=300)
        w, h = img.size
        # "85P" sits on the header's 2nd line, not the title itself -- 0.15
        # confirmed too tight on the noisiest known scan (crops before that
        # line resolves at this DPI even though the title above it is
        # already legible); 0.25 recovered it on all known files without
        # pulling in the data grid.
        crop = img.crop((0, 0, w, int(h * 0.25)))
        text = (await ocr_text(crop, psm=6)).upper()
        return "CONDITION MONITORING" in text and "85P" in text
    except Exception:
        return False


async def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    n_pages = await page_count(pdf_path)
    for page_index in range(n_pages):
        img = await render_page(pdf_path, page_index, dpi=300)
        text = await ocr_text(img, psm=6)
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            rec = _parse_line(line, page_index + 1)
            if rec is not None:
                records.append(rec)
    return records
