"""A/C Installed Parts (Scanned) -- OCCM variant, no text layer at all
(confirmed via pdfplumber -- 0 chars on every page of the known real sample
file, a straight scan/rasterized export), so extraction is OCR throughout.

Title/header block, repeats on every page (confirmed directly)::

    <operator logo>                     Print Date : <date>
                                         Page <n> of <n>
                A/C Installed Parts
    A/C: <tail>
    P/N          S/N          Installed Position          Installed Date and Time

Confirmed directly: a small operator logo/wordmark sits top-left of the
header band on every page. It is intentionally NOT extracted into any
column here and no operator name is recorded anywhere in this module, per
this project's data-sensitivity convention (same approach as
`occm_variants/msn_occm_list_scanned.py`).

Row shape -- confirmed directly across a spread of sampled pages across the
whole real sample file (every page consistently yields the same row count
whether whole-page OCR text or word-level OCR is used): each record prints
as exactly two physical lines, a blank line, then the next record::

    <pn>  <sn>  [<position tokens...>]  <install_date> <install_time>
    <description text>

POSITION is empty on most rows but, when present, renders as anywhere from
one to a few whitespace-separated tokens (e.g. a bare "ONLY", a zone code
like "LH INBD" or "L/H O/B", a bare item-count token like "#6", or a
combined form like "E5 ONLY") -- so a fixed left-to-right token count
cannot anchor P/N vs S/N vs POSITION. Confirmed directly on a real sample
row (page 27 of the known real sample file) that P/N itself can ALSO
render as two tokens, e.g. a base code plus a trailing "REV.<letter>"
revision suffix -- so a naive "first token is P/N, second token is S/N"
split is wrong on that row (it would swallow the revision suffix into
S/N). Column assignment is therefore done by each OCR word's own X
position against the four column X-boundaries measured directly from the
repeated column-header row (see `_COL_BOUNDS` below, confirmed stable
across the first, ~mid, and near-last pages of the real sample file) --
every word whose left edge falls in a given column's X-range is joined
(space-separated) into that column's value, regardless of how many tokens
land there. INSTALL_DATE/INSTALL_TIME are then picked out of the rightmost
bucket by shape ("M/D/YYYY" / "HH:MM:SS", confirmed exactly this shape on
every real data row sampled) rather than by position, so a data line is
recognized by having a non-empty P/N, a non-empty S/N, and both a
date-shaped and a time-shaped token in the rightmost bucket -- not by
token count at all. DESCRIPTION is a genuine free-text line and is taken
verbatim from the next non-blank, non-header line following a matched
data line.

OCR approach: unlike several sibling scanned OCCM formats in this package
(e.g. `occm_variants/msn_occm_list_scanned.py`), a single whole-page
`ocr_words()` pass at psm 6 was confirmed directly, across a wide spread of
sampled pages of the real sample file, to come back clean and in correct
reading order -- no per-column-strip cropping is needed here. This is
consistent with this project's documented lesson that whole-page/whole-row
OCR risk is specific to some scans even when the render looks crisp: this
particular file's rows sit on generous vertical whitespace with no ruled
grid lines at all (confirmed by direct visual inspection of the rendered
page), unlike the dense ruled grids where whole-page OCR was confirmed to
garble.

Physical lines are recovered by clustering OCR word boxes on `top`
(y-position) with a tolerance wide enough to absorb the several-px jitter
seen within a single row's own tokens in the real sample (confirmed
directly, e.g. an S/N token's box can sit ~10px above its row's own P/N
token) while staying well short of the blank-line gap separating a data
row from its description line or the next record.

Known sensitive-content finding, confirmed directly by rendering the real
sample file's final page as an image: it carries a printed "Audit Date:" /
"Auditor Signature:" form block with a handwritten signature and
handwritten date filled in. This block does NOT match this module's data-row
shape (no P/N/S/N pair precedes its date), so it is never parsed as a data
row; it is also explicitly excluded (see `_BLOCK_LINE_RE` below) from ever
being attached as a DESCRIPTION value, as defense in depth even though the
row/description pairing logic was confirmed never to reach it on the real
sample file. No name, signature, or handwritten content is extracted into
any field by this module.
"""
from __future__ import annotations
import re

from sheet_types.occm_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_words, page_count

NAME = "A/C Installed Parts (Scanned)"

# This module's known source file has no text layer at all (confirmed via
# pdfplumber -- 0 chars on every page), so these SIGNATURES can never fire
# through occm.py's normal pdfplumber head-text match; real detection
# happens via ocr_detect() below. Deliberately left empty, same convention
# as this package's other purely-OCR variants (e.g.
# `occm_list_func_loc_scanned.py`).
SIGNATURES = []

CANONICAL_COLUMNS = [
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "POSITION",
    "INSTALL_DATE",
    "INSTALL_TIME",
    "DESCRIPTION",
    # Header metadata -- parsed once, stamped onto every row.
    "AIRCRAFT_TAIL_CODE",
    "REPORT_DATE",
]

_OVERRIDES = {
    # Confirmed directly: real POSITION values often lead with a bare "#"
    # item-count marker (e.g. "#7", "#2 RT") -- allowed as a leading char
    # alongside the usual alphanumeric start.
    "POSITION": {"pattern": r"^[A-Z0-9#][A-Z0-9 /#.\-]*$", "allow_empty": True},
    # Confirmed directly on a real sample page: some genuine S/N values
    # carry a literal embedded space (a "LOT <lot-code>" style value, e.g.
    # a lot-number-prefixed serial on a consumable-type part) -- the global
    # SERIAL_NUMBER rule (shared/aviation_rules.py) has no allowance for an
    # internal space, so it's widened here specifically for this format.
    "SERIAL_NUMBER": {"pattern": r"^[A-Z0-9/](?:[A-Z0-9 \-/]*[A-Z0-9/])?$", "allow_empty": True},
    "INSTALL_DATE": {"pattern": r"^\d{1,2}/\d{1,2}/\d{4}$", "allow_empty": True},
    "INSTALL_TIME": {"pattern": r"^\d{2}:\d{2}:\d{2}$", "allow_empty": True},
    # Header metadata -- a single value parsed once and stamped identically
    # on every row of the file, so a tight pattern here would either flag
    # every single row over one OCR misread in one place, or none at all --
    # neither is a useful per-row signal (same convention as this package's
    # other header-plus-body OCR variants, e.g.
    # `occm_variants/msn_occm_list_scanned.py`'s own header fields).
    "AIRCRAFT_TAIL_CODE": {"allow_empty": True},
    "REPORT_DATE": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Row anchor: a date-shaped and a time-shaped token, both located by shape
# within the rightmost column bucket (see module docstring on why POSITION
# -- and even P/N -- can't be anchored by a fixed token count).
_DATE_RE = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")
_TIME_RE = re.compile(r"^\d{1,2}:\d{2}:\d{2}$")

# Column X-boundaries (px @ 300dpi), the midpoints between each column's own
# header-word left-edge, measured directly across the first, ~mid, and
# near-last pages of the real sample file (confirmed stable: header word
# left-edges vary by at most a few px page to page). A word's own left edge
# (not its full span) decides its column -- confirmed sufficient even for
# the P/N-with-trailing-"REV.<letter>" row noted in the module docstring,
# since that second token's left edge (367px) still sits well inside the
# P/N column, short of the P/N-S/N boundary.
_COL_BOUNDS = [
    (0, 419, "PART_NUMBER"),      # header "P/N" starts ~200px
    (419, 808, "SERIAL_NUMBER"),  # header "S/N" starts ~637px
    (808, 1221, "POSITION"),      # header "Installed Position" starts ~979px
    (1221, 1e9, "DATE_TIME"),     # header "Installed Date and Time" starts ~1463px
]


def _column_for(left: float) -> str:
    for lo, hi, name in _COL_BOUNDS:
        if lo <= left < hi:
            return name
    return "DATE_TIME"

# Stray ruled-border/punctuation artifacts occasionally picked up as their
# own word box -- dropped before a line's tokens are inspected.
_NOISE_TOKEN_RE = re.compile(r"^[|\[\]_.,:;\-—–]+$")

# A candidate DESCRIPTION line with no letters at all is page furniture
# (a stray rule/punctuation OCR artifact), never real data.
_ALPHA_RE = re.compile(r"[A-Za-z]")

# Explicit defense-in-depth block list -- see module docstring's "Known
# sensitive-content finding". Matched independently of the natural
# pending-row-is-None skip (which was already confirmed sufficient on the
# real sample file) so a DESCRIPTION can never pick up this block's text
# even under a future/unseen page layout.
_BLOCK_LINE_RE = re.compile(r"AUDIT\s*DATE|AUDITOR\s*SIGNATURE", re.IGNORECASE)

# Header field anchors. "A/C" is tolerant of OCR's very common "A/C" ->
# "AIC" substitution (the forward slash misread as a capital I), same
# tolerance used in occm_variants/msn_occm_list_scanned.py.
_TAIL_RE = re.compile(r"A[/I]?C\s*:\s*([A-Z0-9\-]+)", re.IGNORECASE)
_REPORT_DATE_RE = re.compile(r"PRINT\s*DATE\s*:?\s*([\d/]+)", re.IGNORECASE)

# ocr_detect() anchor: the report's own bare title, "A/C Installed Parts"
# (no trailing "Print"), together with its column-header phrase "Installed
# Position". Checked directly (grep across every SIGNATURES list in
# sheet_types/{occm,ht,llp}.py and every existing occm_variants file): no
# other module's own SIGNATURES/ocr_detect anchor is "INSTALLED POSITION"
# (occm_part_status.py uses the phrase only in prose/docstring, never as an
# actual SIGNATURES entry). The bare title phrase "A/C Installed Parts" IS
# a substring of aircraft_installed_parts_print.py's own SIGNATURES entry
# "A/C Installed Parts Print" -- but that module is a born-digital variant
# reached only through the router's pdfplumber text-match path (its own
# known source file has a real text layer), never through this ocr_detect
# fallback, and this module's own known source file has no text layer at
# all for that path to match against in the first place -- so the two
# cannot collide on the same file either direction. Requiring BOTH phrases
# together (not the title alone) is an extra margin regardless.
_TITLE_RE = re.compile(r"A[/I]?C\s*INSTALLED\s*PARTS", re.IGNORECASE)
_COLHDR_RE = re.compile(r"INSTALLED\s*POSITION", re.IGNORECASE)


def _group_lines(words: list[dict], tol: float = 20.0) -> list[list[dict]]:
    """Cluster OCR word boxes into physical lines by `top` (y-position).
    Tolerance is wide enough to absorb the several-px jitter confirmed
    within a single row's own tokens on the real sample file, while
    staying well short of the blank-line gap that separates a data row
    from its own description line or the next record (see module
    docstring)."""
    ws = sorted(words, key=lambda w: (w["top"], w["left"]))
    lines: list[dict] = []
    for w in ws:
        if lines and abs(w["top"] - lines[-1]["top"]) <= tol:
            n = len(lines[-1]["words"])
            lines[-1]["words"].append(w)
            lines[-1]["top"] = (lines[-1]["top"] * n + w["top"]) / (n + 1)
        else:
            lines.append({"top": w["top"], "words": [w]})
    for line in lines:
        line["words"].sort(key=lambda w: w["left"])
    return [line["words"] for line in lines]


def _clean_words(line_words: list[dict]) -> list[dict]:
    return [w for w in line_words if not _NOISE_TOKEN_RE.match(w["text"])]


def _clean_tokens(line_words: list[dict]) -> list[str]:
    return [w["text"] for w in _clean_words(line_words)]


def _parse_row(line_words: list[dict]) -> dict | None:
    """Bucket a physical line's words by X-position (see `_COL_BOUNDS`
    above) and accept it as a data row only if P/N and S/N are both
    non-empty and the rightmost bucket contains both a date-shaped and a
    time-shaped token (see module docstring on why this replaces a fixed
    token-count anchor)."""
    buckets: dict[str, list[str]] = {"PART_NUMBER": [], "SERIAL_NUMBER": [], "POSITION": [], "DATE_TIME": []}
    for w in line_words:
        buckets[_column_for(w["left"])].append(w["text"])

    date_val = next((t for t in buckets["DATE_TIME"] if _DATE_RE.match(t)), None)
    time_val = next((t for t in buckets["DATE_TIME"] if _TIME_RE.match(t)), None)
    if date_val is None or time_val is None:
        return None
    pn = " ".join(buckets["PART_NUMBER"]).strip()
    sn = " ".join(buckets["SERIAL_NUMBER"]).strip()
    if not pn or not sn:
        return None
    return {
        "PART_NUMBER": pn,
        "SERIAL_NUMBER": sn,
        "POSITION": " ".join(buckets["POSITION"]).strip(),
        "INSTALL_DATE": date_val,
        "INSTALL_TIME": time_val,
    }


def _line_text(tokens: list[str]) -> str:
    return " ".join(tokens).strip()


def _parse_header(page_text: str, meta: dict) -> None:
    if not meta.get("AIRCRAFT_TAIL_CODE"):
        m = _TAIL_RE.search(page_text)
        if m:
            meta["AIRCRAFT_TAIL_CODE"] = m.group(1).upper()
    if not meta.get("REPORT_DATE"):
        m = _REPORT_DATE_RE.search(page_text)
        if m:
            meta["REPORT_DATE"] = m.group(1)


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback (see
    sheet_types/occm.py) -- this variant's known source file has no text
    layer at all, so it can never be found through the normal pdfplumber
    head-text match. Requires BOTH the report's own bare title and its
    column-header phrase (see _TITLE_RE/_COLHDR_RE above for the collision
    analysis)."""
    try:
        img = await render_page(pdf_path, 0, dpi=300)
        w, h = img.size
        crop = img.crop((0, 0, w, int(h * 0.2)))
        words = await ocr_words(crop, psm=6, min_conf=-1)
        text = " ".join(str(x.get("text", "")) for x in words)
        return bool(_TITLE_RE.search(text) and _COLHDR_RE.search(text))
    except Exception:
        return False


async def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    header_meta = {"AIRCRAFT_TAIL_CODE": "", "REPORT_DATE": ""}
    n_pages = await page_count(pdf_path)

    for page_index in range(n_pages):
        img = await render_page(pdf_path, page_index, dpi=300)
        words = await ocr_words(img, psm=6, min_conf=-1)
        if not words:
            continue

        lines = _group_lines(words)

        if not header_meta["AIRCRAFT_TAIL_CODE"] or not header_meta["REPORT_DATE"]:
            page_text = "\n".join(_line_text(_clean_tokens(lw)) for lw in lines)
            _parse_header(page_text, header_meta)

        pending_row: dict | None = None
        for line_words in lines:
            clean_words = _clean_words(line_words)
            if not clean_words:
                continue
            row = _parse_row(clean_words)
            if row is not None:
                if pending_row is not None:
                    # Previous data row had no following description line
                    # before the next data row started -- flush it as-is
                    # (DESCRIPTION left empty rather than guessed from
                    # unrelated text).
                    records.append(pending_row)
                row["DESCRIPTION"] = ""
                row.update(header_meta)
                row["_page"] = page_index + 1
                pending_row = row
                continue

            text = _line_text([w["text"] for w in clean_words])
            if not _ALPHA_RE.search(text):
                # Pure punctuation/rule-line OCR artifact -- page furniture,
                # never real data (see module docstring).
                continue
            if _BLOCK_LINE_RE.search(text):
                # Audit/signature block -- see module docstring's "Known
                # sensitive-content finding". Never attached as a
                # DESCRIPTION even if a row were somehow still pending.
                pending_row = None
                continue
            if pending_row is not None:
                pending_row["DESCRIPTION"] = text
                records.append(pending_row)
                pending_row = None
            # Else: stray unanchored line (title/column-header/page-footer
            # text) before any data row on this page -- dropped rather than
            # guessed onto a row.

        if pending_row is not None:
            # Last row on the page had no description line before the page
            # ended -- flush as-is rather than reading across the page
            # boundary (never confirmed necessary on the real sample file,
            # but kept as a safety net per this project's convention).
            records.append(pending_row)

    return records
