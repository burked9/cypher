"""HARD TIME AIRCRAFT COMPONENTS STATUS -- OCR required despite a non-blank
pdfplumber text layer, because that text layer is unusable for most of the
page.

Confirmed directly on a real corpus file (4 pages): `page.extract_text()`
returns thousands of non-empty characters on every page (so the router's
own generic "blank text -> OCR fallback" check never fires), but most words
decode to visibly wrong characters -- letters like M/N/S/T/D/U are the ones
that come out garbled most often (e.g. "COMPONENTS" reads back as something
like "COiIPO}IE]{TS", "STATUS" as "sTATUS"), while several other letters
(A/C/R/F/E/G/I/L/P/K/W) and plain digits mostly decode correctly. Rendering
the page to an image and reading it visually, by contrast, shows a clean,
sharp, perfectly ordinary ruled table -- the PDF's own rendering path still
works fine; only pdfplumber's character-code-to-text mapping is broken for
a subset of glyphs. This is a different failure signature than this
package's other "broken font" OCR variant (which recovers pdfplumber's own
"(cid:<n>)" placeholder token throughout, i.e. total mapping failure) --
here the corruption is partial and inconsistent per letter, confirmed
directly not to follow any simple fixed substitution cipher (checked
directly across dozens of words: the same visual letter decodes
differently depending on neighbouring glyphs), so no decode table was
attempted; OCR is used instead, end to end, for every field except the one
title fragment below that happens to decode cleanly.

One short fragment of the page-1/2/4 header block -- "ACRF REG. :" --
decodes correctly and consistently (confirmed directly against a real
corpus file: present verbatim, byte-for-byte, on 3 of the file's 4 pages'
own `extract_text()` output; only missing on one interior page, which
doesn't matter since the router's own head-text scan reads the first 3
pages). This is used as this module's own SIGNATURES anchor, so normal
plain-text detection works despite the rest of the page being unusable --
no `ocr_detect()` fallback is needed or relied upon for the known source
file, though one is still provided per this package's interface
convention (see below).

Header block, repeats near-identically on every page (values below are the
real field shapes, genericised; OCR'd, not the broken pdfplumber decode)::

    HARD TIME AIRCRAFT COMPONENTS STATUS
    <operator wordmark>   AIRCRAFT TYPE/MODEL : <type>   CURRENT DATE : <date>
                           ACRF REG. : <registration>     ACRF TSN : <tsn>
    <department lines>     SN : <msn> ; LN : <line_no> ; VN : <vn>   ACRF CSN : <csn>

Header metadata (aircraft type, registration, MSN, line number, VN, report
date, aircraft TSN/CSN) is parsed once, from page 1's own header crop, via
OCR (a per-field crop is not needed here -- confirmed directly that a
single wide OCR pass across the header block resolves every field
reliably, unlike the data grid below it) and stamped on every row of the
file, per this project's usual header-metadata convention.

Main table, one header row, 18 columns::

    MPD Ref: | ATA | Description | Part Number | Serial Number | Position |
    MPD/AD/MFG Ref | Spec. Limit | Installed Date | Aircraft(TSN, CSN) |
    Component Running(Hours, Cycles, Days) |
    Component Remaining(Hours, Cycles, Days) | Expired Date

OCR approach: per-column-strip OCR, not whole-page or whole-row. A whole-
page OCR pass (`ocr_text()` at psm 6) is actually fairly readable on this
file (the background ruled grid helps Tesseract's own layout analysis), but
still unreliable for splitting a row into its own fields with confidence --
DESCRIPTION is free text of variable word count, PART_NUMBER occasionally
gets an OCR-introduced space in the middle of a single real value, and
POSITION is one or two words -- so a fixed-token-count split of a whole
OCR'd line risks a confidently wrong field boundary. Cropping down to one
ruled column's own width (full page height) and OCR'ing it on its own
avoids all of that ambiguity, at the cost of one OCR call per column per
page (18 columns here) -- same tradeoff this package's other per-column-
strip variants make (e.g. `occm_variants/msn_occm_list_scanned.py`,
`occm_variants/aircraft_kardex_status_broken_font_scanned.py`).

Column X-boundaries (px @ 300 DPI) below are derived directly from this
report's own real ruled-column text positions -- confirmed directly by
reading `pdfplumber`'s own per-character `x0`/`x1` positions on a real
corpus file (those positions are accurate even where the character's own
decoded *text* is wrong -- position and glyph identity are independent
failures here) across the first, a middle, and the last page; stable
across all of them.

Row anchoring: ATA is used as the per-row Y anchor (a bare 1-2 digit token,
OCRs very reliably in its own narrow column strip, one clean token per
row), the same choice `msn_occm_list_scanned.py` makes and for the same
reason -- MPD_REF repeats or goes blank on a component's own sibling rows
(e.g. an ESCAPE SLIDE row and its own RESERVOIR sibling row share one MPD
Ref, printed only on the first of the pair) and DESCRIPTION is free text,
neither of which anchors as cleanly as a bare small-int column. A
document-level "ATA <n>" section-divider line (this report prints one
before each new ATA chapter's first row) sits in the MPD_REF column's own
x-range, not the ATA column's, so it is never picked up as a stray anchor
by construction, not by extra filtering.

Every other column's OCR'd words are assigned to their nearest ATA anchor
by Y-distance, within a tolerance under half this file's own row pitch
(confirmed directly, ~11.3pt / ~47px @ 300 DPI between consecutive rows) --
this also transparently absorbs the occasional taller/wrapped DESCRIPTION
or MPD_AD_MFG_REF cell without special-case code, the same way the
reference module's own docstring describes.

Known limitation, confirmed directly against the real sample file: a
handful of PART_NUMBER cells get OCR-split into two adjacent word boxes
with no real space in the source value -- these are rejoined with no
separator (PART_NUMBER/SERIAL_NUMBER/MPD_REF/dates/numeric columns are all
genuinely space-free values in this source, so joined with no separator;
DESCRIPTION/POSITION/MPD_AD_MFG_REF/SPEC_LIMIT are genuine multi-word
free text or a number-plus-unit pair, joined with a single space). A rare
multi-line-wrapped DESCRIPTION cell's second line can land just outside
this module's Y-tolerance and get dropped rather than guessed onto a
neighbouring row -- per this project's soft-validation convention, this is
expected to surface as a shorter DESCRIPTION value rather than a silently
wrong one.

REM_HOURS/REM_CYCLES/REM_DAYS carry the literal string "N/A" on the
majority of real rows (only one of the three interval bases usually
applies to a given component) -- kept as a valid literal value rather than
treated as blank/missing, same convention as several sibling HT variants
in this package (e.g. `tci_list.py`'s own ND_H/ND_C/ND_DATE columns).
REM_DAYS/RUN_DAYS are also confirmed directly to carry a plain negative
integer on real rows (an already-overdue component, e.g. "-125") -- kept
as-is rather than treated as invalid.
"""
from __future__ import annotations
import re

from PIL import Image

from sheet_types.ht_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, ocr_words, page_count

NAME = "Hard Time Aircraft Components Status (Broken Font)"

# See module docstring -- this fragment decodes correctly through
# pdfplumber's own broken character mapping even though most of the rest
# of the page does not, so ordinary plain-text SIGNATURES matching works.
# Checked against every SIGNATURES list in occm.py/ht.py/llp.py and every
# existing occm_variants/ht_variants/llp_variants module's own SIGNATURES
# list (plus a plain grep for "ACRF"); no collision found. The nearest
# look-alike, occm.py's own "AIRCRAFT REG. :", is a different phrase
# (neither a substring of the other) used for a different operator/sheet
# type's scanned file.
SIGNATURES = [
    "ACRF REG. :",
]

CANONICAL_COLUMNS = [
    "MPD_REF",
    "ATA",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "POSITION",
    "MPD_AD_MFG_REF",
    "SPEC_LIMIT",
    "INSTALLED_DATE",
    "TSN",
    "CSN",
    "RUN_HOURS",
    "RUN_CYCLES",
    "RUN_DAYS",
    "REM_HOURS",
    "REM_CYCLES",
    "REM_DAYS",
    "EXPIRED_DATE",
    # Header metadata -- parsed once (page 1) and stamped on every row.
    "AIRCRAFT_TYPE",
    "AIRCRAFT_REG",
    "MSN",
    "LINE_NO",
    "VN",
    "REPORT_DATE",
    "AC_TSN",
    "AC_CSN",
]

_DATE_RE = r"^\d{1,2}-[A-Za-z]{3}-\d{2,4}$"
# A "." in place of the expected "," thousands separator is a confirmed
# recurring OCR misread on this file's own numeric columns at this
# module's OCR settings (e.g. "45.785" for "45,785") -- tolerated here
# rather than force-corrected, per this project's "never guess" convention
# for a soft-validation pattern (the value is carried through exactly as
# OCR'd either way; this only affects whether it gets flagged).
_NA_NUM_RE = r"^(?:-?[\d,.]+|N/A)$"
_NUM_RE = r"^-?[\d,.]+$"

_OVERRIDES = {
    "MPD_REF": {"pattern": r"^\d{2}-\d{3}-\d{2}$", "allow_empty": True},
    # Repeats blank on a component's own sibling rows (see module
    # docstring) -- allow_empty rather than forward-filled, since this
    # project's convention is to carry the source's own blank cells
    # through rather than guess a value the source itself omitted.
    "POSITION": {"allow_empty": True},
    "MPD_AD_MFG_REF": {
        # Genuinely heterogeneous across rows (years/months/a flight-hour
        # or flight-cycle interval, e.g. "3Y", "8 MO", "2,000FC", "3 YEARS")
        # -- a comma or an internal space is confirmed to land in either
        # the number or between the number and its own unit depending on
        # the row (both real source formatting and an occasional OCR-
        # introduced gap), so this stays a loose charset check rather than
        # a fixed number+unit pattern.
        "pattern": r"^[\dA-Za-z,\s]+$",
        "allow_empty": True,
    },
    "SPEC_LIMIT": {
        "pattern": r"^[\d,]+\s+(FC|FH|Days)$",
        "allow_empty": True,
    },
    "INSTALLED_DATE": {"pattern": _DATE_RE, "allow_empty": True},
    "TSN": {"pattern": _NUM_RE, "allow_empty": True},
    "CSN": {"pattern": _NUM_RE, "allow_empty": True},
    "RUN_HOURS": {"pattern": _NA_NUM_RE, "allow_empty": True},
    "RUN_CYCLES": {"pattern": _NA_NUM_RE, "allow_empty": True},
    "RUN_DAYS": {"pattern": _NA_NUM_RE, "allow_empty": True},
    "REM_HOURS": {"pattern": _NA_NUM_RE, "allow_empty": True},
    "REM_CYCLES": {"pattern": _NA_NUM_RE, "allow_empty": True},
    "REM_DAYS": {"pattern": _NA_NUM_RE, "allow_empty": True},
    "EXPIRED_DATE": {"pattern": _DATE_RE + r"|^N/A$", "allow_empty": True},
    # Header metadata -- same value stamped on every row of the file, so a
    # tight per-row pattern here would either flag every row over one OCR
    # misread in one place, or none at all -- same reasoning this
    # package's other header-plus-body OCR variants use (e.g.
    # `occm_variants/msn_occm_list_scanned.py`'s own header fields).
    "AIRCRAFT_TYPE": {"allow_empty": True},
    "AIRCRAFT_REG": {"allow_empty": True},
    "MSN": {"allow_empty": True},
    "LINE_NO": {"allow_empty": True},
    "VN": {"allow_empty": True},
    "REPORT_DATE": {"allow_empty": True},
    "AC_TSN": {"allow_empty": True},
    "AC_CSN": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Column X-boundaries (px @ 300dpi) -- see module docstring. Always paired
# with `render_page(..., dpi=300)`, never a different DPI, so these stay
# valid.
_COLUMNS = [
    (142, 279, "MPD_REF"),
    (279, 353, "ATA"),
    (353, 731, "DESCRIPTION"),
    (731, 1010, "PART_NUMBER"),
    (1010, 1200, "SERIAL_NUMBER"),
    (1200, 1403, "POSITION"),
    (1403, 1564, "MPD_AD_MFG_REF"),
    (1564, 1765, "SPEC_LIMIT"),
    (1765, 1951, "INSTALLED_DATE"),
    (1951, 2085, "TSN"),
    (2085, 2207, "CSN"),
    (2207, 2366, "RUN_HOURS"),
    (2366, 2540, "RUN_CYCLES"),
    (2540, 2693, "RUN_DAYS"),
    (2693, 2823, "REM_HOURS"),
    (2823, 2956, "REM_CYCLES"),
    (2956, 3080, "REM_DAYS"),
    (3080, 3383, "EXPIRED_DATE"),
]
# Genuine multi-word free text, or a number-plus-unit pair -- joined with a
# single space. Every other column is a genuinely space-free source value
# (see module docstring), joined with no separator.
_JOIN_SPACE = {"DESCRIPTION", "POSITION", "MPD_AD_MFG_REF", "SPEC_LIMIT"}

# Stray ruled-border artifacts occasionally picked up as their own word box.
_NOISE_TOKEN_RE = re.compile(r"^[|\[\]_\-—–]+$")

# A faint printed mark (confirmed directly: visible as a thin/blurred glyph
# in the rendered image itself at this column's own crop, not purely a
# software OCR guess -- see module docstring) recurs at a fixed position
# inside several PART_NUMBER/SERIAL_NUMBER/MPD_AD_MFG_REF values on this
# file and gets OCR'd as one of a variety of stray punctuation-ish
# characters depending on the row (":", "(", "<", "'", "\xb0" [degree],
# "\xa2"/"\xa5"/"€" [currency signs often standing in for a
# comma/hyphen the source itself renders too faintly to resolve], curly
# quotes). None of these characters is ever a legitimate part of a part
# number, serial number, or interval code in this project's own domain
# conventions (see `shared/aviation_rules.py`'s own field conventions), so
# they are stripped outright here rather than guessed into a specific
# digit or separator -- per this project's "never guess a wrong split"
# rule, dropping an unrecoverable character is preferred over silently
# inventing one. Genuine free-text columns (DESCRIPTION/POSITION, which
# can carry real parentheses, e.g. "SMOKE HOOD ( PBE)") are deliberately
# NOT run through this stripper.
_ARTIFACT_CHAR_RE = re.compile(r"[)(<>{}‘’“”:;\xa2\xa3\xa5€\xb0\xa7!+\\|~`']")
_ARTIFACT_PRONE_COLS = {"PART_NUMBER", "SERIAL_NUMBER", "MPD_AD_MFG_REF"}

# Row anchor: a bare 1-2 digit ATA chapter code (see module docstring for
# why ATA, not MPD_REF or DESCRIPTION, anchors each row), restricted to a
# real ATA-chapter range so a stray 1-digit OCR fragment from the last
# page's own signature block (e.g. "Verified by :" reading back a bare "4"
# in this column's own x-range) can't seed a spurious row -- same bounds
# `shared/aviation_rules.py`'s own global ATA rule uses.
_ATA_TOKEN_RE = re.compile(r"^\d{1,2}$")
_ATA_MIN, _ATA_MAX = 20, 83

# Y-tolerance for assigning a non-ATA column's word to its nearest ATA
# anchor -- measured directly against this file's own row pitch (~47px @
# 300dpi between consecutive rows); comfortably under half that.
_ANCHOR_TOLERANCE_PX = 22

_TYPE_RE = re.compile(r"TYPE\s*/?\s*MODEL\s*:?\s*([A-Z0-9\-]+)")
_REG_RE = re.compile(r"REG\.?\s*:?\s*([A-Z0-9\-]+)")
# Negative lookbehind excludes "ACRF TSN"/"ACRF CSN" (their own "SN" is
# always preceded by a letter -- T/C -- on this file's real header text;
# the bare MSN field's own "SN :" is always preceded by whitespace).
_MSN_RE = re.compile(r"(?<![A-Z])SN\s*:?\s*(\d+)")
_LN_RE = re.compile(r"LN\s*:?\s*(\d+)")
_VN_RE = re.compile(r"VN\s*:?\s*[^A-Z0-9]?([A-Z0-9]+)")
_DATE_HDR_RE = re.compile(r"CURRENT\s*DATE\s*:?\s*(\S+)")
_AC_TSN_RE = re.compile(r"TSN\s*:?\s*([\d,]+)")
_AC_CSN_RE = re.compile(r"CSN\s*:?\s*([\d,]+)")

_HEADER_FIELDS = [
    "AIRCRAFT_TYPE", "AIRCRAFT_REG", "MSN", "LINE_NO", "VN",
    "REPORT_DATE", "AC_TSN", "AC_CSN",
]


def _col_bounds(name: str) -> tuple[int, int]:
    for lo, hi, col in _COLUMNS:
        if col == name:
            return lo, hi
    raise KeyError(name)


async def _ocr_column(img, name: str, y0: int, y1: int, scale: int = 2) -> list[tuple[float, str]]:
    """OCR one column's full-height strip and return (top, text) pairs in
    original-image page coordinates (see module docstring for why a
    column-width crop is used rather than a whole-row or whole-page pass)."""
    lo, hi = _col_bounds(name)
    x0 = max(0, int(lo))
    x1 = min(img.width, int(hi))
    crop = img.crop((x0, y0, x1, y1))
    if scale != 1:
        crop = crop.resize((crop.width * scale, crop.height * scale), Image.LANCZOS)
    words = await ocr_words(crop, psm=6, min_conf=-1)
    out = []
    for w in words:
        text = str(w.get("text", "")).strip()
        if not text or _NOISE_TOKEN_RE.match(text):
            continue
        out.append((y0 + w["top"] / scale, text))
    return out


def _nearest_anchor_idx(top: float, anchors: list[float]) -> int | None:
    best_idx, best_dist = None, None
    for i, a in enumerate(anchors):
        d = abs(top - a)
        if best_dist is None or d < best_dist:
            best_idx, best_dist = i, d
    if best_idx is not None and best_dist <= _ANCHOR_TOLERANCE_PX:
        return best_idx
    return None


def _join(tokens: list[str], col_name: str) -> str:
    sep = " " if col_name in _JOIN_SPACE else ""
    text = sep.join(tokens).strip(" |[]_-—–")
    if col_name in _ARTIFACT_PRONE_COLS:
        text = _ARTIFACT_CHAR_RE.sub("", text)
    return text


def _parse_header_text(text: str, meta: dict) -> None:
    upper = text.upper()
    for pat, key in (
        (_TYPE_RE, "AIRCRAFT_TYPE"),
        (_REG_RE, "AIRCRAFT_REG"),
        (_MSN_RE, "MSN"),
        (_LN_RE, "LINE_NO"),
        (_VN_RE, "VN"),
        (_DATE_HDR_RE, "REPORT_DATE"),
        (_AC_TSN_RE, "AC_TSN"),
        (_AC_CSN_RE, "AC_CSN"),
    ):
        if meta.get(key):
            continue
        m = pat.search(upper)
        if m:
            meta[key] = m.group(1)


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback. Not
    expected to fire for the known source file (its text layer is never
    blank -- see module docstring; it's found via plain-text SIGNATURES
    instead), kept for interface consistency and in case a more severely
    corrupted copy of this template turns up with an unusably short text
    layer."""
    try:
        img = await render_page(pdf_path, 0, dpi=300)
        w, h = img.size
        crop = img.crop((0, 0, w, int(h * 0.22)))
        text = (await ocr_text(crop, psm=6)).upper()
        return "AIRCRAFT COMPONENTS STATUS" in text and "ACRF REG" in text
    except Exception:
        return False


def _extract_page_rows(columns_words: dict[str, list[tuple[float, str]]]) -> list[dict]:
    ata_tokens = [
        (top, t) for top, t in columns_words["ATA"]
        if _ATA_TOKEN_RE.match(t) and _ATA_MIN <= int(t) <= _ATA_MAX
    ]
    if not ata_tokens:
        return []
    ata_tokens.sort(key=lambda p: p[0])
    anchors = [top for top, _ in ata_tokens]
    ata_values = [t for _, t in ata_tokens]

    other_cols = [name for _, _, name in _COLUMNS if name != "ATA"]
    buckets: list[dict[str, list[str]]] = [{name: [] for name in other_cols} for _ in anchors]
    for col_name in other_cols:
        for top, text in columns_words[col_name]:
            idx = _nearest_anchor_idx(top, anchors)
            if idx is not None:
                buckets[idx][col_name].append(text)

    rows = []
    for i, ata in enumerate(ata_values):
        b = buckets[i]
        description = _join(b["DESCRIPTION"], "DESCRIPTION")
        part_number = _join(b["PART_NUMBER"], "PART_NUMBER")
        serial_number = _join(b["SERIAL_NUMBER"], "SERIAL_NUMBER")
        if not description and not part_number and not serial_number:
            # No real cell content attached to this ATA anchor at all --
            # almost certainly page furniture (e.g. an "ATA <n>" section
            # divider whose own text sits outside the ATA column's x-range
            # but whose row-pitch happened to still leave a stray token
            # nearby) rather than a genuine data row.
            continue
        rows.append({
            "MPD_REF": _join(b["MPD_REF"], "MPD_REF"),
            "ATA": ata,
            "DESCRIPTION": description,
            "PART_NUMBER": part_number,
            "SERIAL_NUMBER": serial_number,
            "POSITION": _join(b["POSITION"], "POSITION"),
            "MPD_AD_MFG_REF": _join(b["MPD_AD_MFG_REF"], "MPD_AD_MFG_REF"),
            "SPEC_LIMIT": _join(b["SPEC_LIMIT"], "SPEC_LIMIT"),
            "INSTALLED_DATE": _join(b["INSTALLED_DATE"], "INSTALLED_DATE"),
            "TSN": _join(b["TSN"], "TSN"),
            "CSN": _join(b["CSN"], "CSN"),
            "RUN_HOURS": _join(b["RUN_HOURS"], "RUN_HOURS"),
            "RUN_CYCLES": _join(b["RUN_CYCLES"], "RUN_CYCLES"),
            "RUN_DAYS": _join(b["RUN_DAYS"], "RUN_DAYS"),
            "REM_HOURS": _join(b["REM_HOURS"], "REM_HOURS"),
            "REM_CYCLES": _join(b["REM_CYCLES"], "REM_CYCLES"),
            "REM_DAYS": _join(b["REM_DAYS"], "REM_DAYS"),
            "EXPIRED_DATE": _join(b["EXPIRED_DATE"], "EXPIRED_DATE"),
        })
    return rows


async def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    header_meta = {k: "" for k in _HEADER_FIELDS}
    n_pages = await page_count(pdf_path)
    for page_index in range(n_pages):
        img = await render_page(pdf_path, page_index, dpi=300)
        w, h = img.size

        if not all(header_meta.values()):
            crop = img.crop((0, 0, w, int(h * 0.22)))
            header_text = await ocr_text(crop, psm=6)
            _parse_header_text(header_text, header_meta)

        # Data grid starts just below the repeated column-header row, which
        # sits at roughly the same fixed fractional position on every page
        # (confirmed directly); any page furniture above the first real row
        # (an "ATA <n>" divider) or below the last one (page footer, the
        # last page's signature block) is filtered out downstream by
        # requiring a genuine ATA anchor with at least one attached data
        # cell.
        y0 = int(h * 0.20)
        columns_words = {}
        for _, _, col_name in _COLUMNS:
            columns_words[col_name] = await _ocr_column(img, col_name, y0, h)

        for rec in _extract_page_rows(columns_words):
            rec["_page"] = page_index + 1
            rec.update(header_meta)
            records.append(rec)
    return records
