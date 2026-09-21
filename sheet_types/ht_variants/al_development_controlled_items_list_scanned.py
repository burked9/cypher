"""AL Development Division / Planning Section -- MPD-task Controlled Items
List, scanned copy (no usable text layer at all -- confirmed directly on a
real corpus file: pdfplumber `extract_text()`/PyMuPDF `get_text()` both
return 0 characters on every page).

Same underlying report template/column layout as the born-digital sibling
`al_development_controlled_items_list.py` (see that module's own docstring
for the shared header/title story -- "AL DEVELOPMENT DIVISION" / "...ANNING
SECTION" banner, "MPD TASK Work Type ZONE Designaion ..." column-header
row), but this file's own pages are a straight image scan with no text
layer, so that sibling's plain-pdfplumber `SIGNATURES` can never fire here.
Unlike the sibling's own garbled-text-layer workaround (which folds
everything past the install date into one unparsed STATUS_TRAIL string),
this scanned copy's own table renders every column distinctly enough
(confirmed via a real per-column OCR pass across the full sample) that
each of its 23 columns is captured as its own field here rather than one
catch-all trailer.

Header (repeats verbatim, in the same two-block layout, on every page of
the sample -- confirmed directly, not just page 1)::

    <operator wordmark>     A/C            <reg>       CONTROLLED ITEMS LIST      Status Date: <date>
    AL DEVELOPMENT DIVISION A/C MSN:       <msn>                                  A/C FHs: <n>
    ...ANNING SECTION       A/C Model:     <type>                                 A/C FCs: <n>
                                                                                   A/C Manufacture Date: <date>

The banner's own leading "P" of "PLANNING SECTION" is cropped off by the
source scan itself on every page of the sample (confirmed directly -- not
an artifact of this module's own cropping), and the OCR read of the
remainder is inconsistent run to run ("LANNING"/"LANKING" both confirmed
directly), so this module's own `ocr_detect()` and header-metadata parsing
only rely on the reliably-read "SECTION" tail. Similarly, the page's own
operator-wordmark graphic overlaps the title line's own "CONTROLLED"
enough that OCR only ever recovers "CONTR" + "ED ITEMS LIST" with a gap
where "OLL" should be (confirmed directly) -- `ocr_detect()` anchors on
the un-obscured "ITEMS LIST" fragment instead of the full title phrase.

Column-header row (one row, 23 columns, present on every page)::

    MPD TASK | Work Type | ZONE | DESIGNAION | Vendor | PN | SN |
    Manufacture Date | Installation Date |
    Threshold{MO|FH|FC} | Interval{MO|FH|FC} |
    Last Check{DATE|FH|FC} | LIFE(MO) | LIFE LIMIT |
    NEXT DUE{DATE|FH|FC}

Column X-boundaries below are fixed fractions of the rendered page's own
width, measured directly from a real per-word OCR pass restricted to the
column-header row's own thin Y-band on the sample file (restricting the
scan to that one text-dense-but-narrow band, rather than the much taller
data-row region below it, was confirmed directly necessary: a vertical
pixel-darkness scan across the full data-row region gives an inconsistent
line count page to page on this particular scan -- the table's own ruled
divider lines are faint/broken in places, a real photocopy-quality issue,
not a bug in the scan technique -- while the same scan restricted to the
column-header row's own band gives the identical, correct 24-line (23
column) result at every threshold tried). Column widths are NOT re-derived
per page at runtime for that same reason -- a fixed-fraction layout (same
technique as `mm510_scanned.py`) sidesteps the unreliable divider-line
detection entirely, and the sample's own 4 pages all render at the same
size, so the fractions stay aligned without a per-page recalibration pass.

Row anchoring: EACH of the 23 columns is OCR'd as its own full-height
strip (one crop per column per page, not one whole-page pass) -- confirmed
directly necessary, not just a stylistic choice: a single whole-page OCR
pass over this file's own dense small-font table comes back badly garbled
across the board (far worse than any individual column's own narrow-crop
read), while per-column strips read cleanly, the same "OCR the page as
narrow strips, not one wide pass" lesson this project's other dense-table
OCR variants already apply.

ZONE is used as the per-row Y anchor -- confirmed directly the most
reliably-populated column in the real sample (present on every row seen,
including rows with no MPD_TASK_NO, VENDOR, PN or SN at all), and,
somewhat surprisingly, NOT vulnerable to Tesseract's own line-dedup quirk
here even where its own value repeats on several consecutive rows (e.g. a
run of five consecutive "200" rows was confirmed to come back as five
distinct OCR'd tokens, not collapsed to one) -- unlike this same template's
own MPD_TASK_NO and WORK_TYPE columns, BOTH of which were confirmed
directly to lose real rows to that exact dedup quirk when OCR'd as their
own full-column strip (a run of six consecutive identical MPD_TASK_NO
values came back as one single OCR'd token, silently dropping five real
rows). Those two columns are therefore only ever read from within an
already-anchored row's own Y-window here, never used as a row anchor
themselves.

Every column's own single-line value is vertically CENTRED inside its own
row's full height rather than top-aligned whenever that row's DESIGNAION
(or occasionally ZONE/VENDOR) wraps across multiple physical lines
(confirmed directly against real per-word OCR positions) -- so a row's own
Y-window is taken as the midpoint between this anchor and its immediate
neighbours on either side (half the gap to the previous anchor, half the
gap to the next), not a small fixed-radius tolerance around the anchor's
own top -- this keeps a vertically-centred short-cell value inside its own
row's window even on a tall, multi-line-wrapped row.

A ZONE-strip token is only accepted as a row anchor when it matches a
plausible zone-value shape (short, alnum plus the quote/ampersand/hyphen/
period punctuation this column's own real values use -- same shape family
as the born-digital sibling's own ZONE pattern) -- this excludes the
free-text "Note: 6 Mon or 12 Mon check interval..." line that sits below
the table's own last row on two of the sample's four pages (that phrase
contains a colon, never valid in a real ZONE value). A handwritten
sign-off block (name + stamp + role title) sits below that note on those
same two pages; stray 1-3 character OCR fragments from it can still
occasionally pass the shape check on their own, so every candidate row is
ALSO required to show at least one other, independently-read corroborating
signal (a non-empty WORK_TYPE, a non-empty PART_NUMBER, or an
INSTALL_DATE-shaped token) before it is emitted as a record -- confirmed
directly this drops every stray sign-off fragment in the sample (none of
which ever coincides with real PART_NUMBER/INSTALL_DATE/WORK_TYPE content
at the same Y position) while keeping every real row, including the ones
with a genuinely blank MPD_TASK_NO. No signer name from the sample is
written into this module either way.

LAST_CHECK_DATE and NEXT_DUE_DATE are NOT strict date-only fields -- a
handful of real rows in the sample carry genuine free text there instead
of a date (e.g. "Dec 2010 with Redelivery check", "Refer to Last A/C Ck
sheet", or a life-limited-part's own "REFER TO ENGINE LLP" bleeding across
several of this section's columns from its own merged source cell). Both
columns try a plain date-token match first and fall back to the raw
joined text rather than forcing a split or dropping the value -- same
"never guess a wrong split" convention as this package's other OCR
variants for a genuinely irregular/merged cell. MANUFACTURE_DATE and
INSTALL_DATE, by contrast, are confirmed date-only in every real row of
the sample that has a value at all, so those two stay strict.

Two source date formats are both accepted throughout (confirmed directly,
both appear in the same sample file for different rows): `D-Mon-YY` (e.g.
"12-Dec-10") and `DD/Mon/YYYY` (e.g. "05/Jan/2011").

Sensitivity note: the sample file's own header carries a real operator
wordmark, tail number/MSN/aircraft type and report dates, and a
handwritten sign-off block (name + role title) sits below the table on two
pages -- none of that is written into this module's code/comments (only
the generic column-header/title/banner phrases the template itself
prints, which are not document-specific). The header's own AIRCRAFT_REG/
MSN/AIRCRAFT_TYPE/STATUS_DATE/ACFT_FHS/ACFT_FCS/ACFT_MANUFACTURE_DATE
fields ARE extracted into row data at runtime (ordinary functional
extraction, not a hardcoded value in source code), same as this package's
other per-file header-metadata capture elsewhere. The sign-off block is
never parsed into any field (see the ZONE-anchor corroboration check
above); no signer name is written into this module regardless.
"""
from __future__ import annotations
import re

from sheet_types.ht_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, ocr_words, page_count

NAME = "AL Development Division Controlled Items List (Scanned)"

# Deliberately empty -- the known source files have no text layer at all
# (confirmed: 0 pdfplumber/PyMuPDF-extractable chars on every page), so this
# module is only ever reached via ocr_detect()'s blank-text fallback below,
# never the router's normal pdfplumber-text SIGNATURES match. The born-
# digital sibling al_development_controlled_items_list.py owns the plain-
# text "MPD TASK Work Type ZONE" / "AL DEVELOPMENT DIVISION" SIGNATURES
# phrases for the text-layer path; that module carries no ocr_detect() of
# its own, so there is no collision on the OCR-fallback path this module
# uses instead (checked directly).
SIGNATURES: list[str] = []

CANONICAL_COLUMNS = [
    "MPD_TASK_NO",
    "WORK_TYPE",
    "ZONE",
    "DESIGNATION",
    "VENDOR",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "MANUFACTURE_DATE",
    "INSTALL_DATE",
    "THRESHOLD_MO",
    "THRESHOLD_FH",
    "THRESHOLD_FC",
    "INTERVAL_MO",
    "INTERVAL_FH",
    "INTERVAL_FC",
    "LAST_CHECK_DATE",
    "LAST_CHECK_FH",
    "LAST_CHECK_FC",
    "LIFE_MO",
    "LIFE_LIMIT",
    "NEXT_DUE_DATE",
    "NEXT_DUE_FH",
    "NEXT_DUE_FC",
    # Header metadata -- parsed once per page, stamped onto every row of
    # that page.
    "AIRCRAFT_REG",
    "MSN",
    "AIRCRAFT_TYPE",
    "STATUS_DATE",
    "ACFT_FHS",
    "ACFT_FCS",
    "ACFT_MANUFACTURE_DATE",
]

_STRICT_DATE_RE = r"^\d{1,2}[-/][A-Za-z]{3}[-/]\d{2,4}$"
_NUM_RE = r"^\d[\d,]*$"

_OVERRIDES = {
    "WORK_TYPE": {"allow_empty": True},
    # Loosened from the global numeric-only ZONE pattern -- same reasoning
    # as the born-digital sibling's own override: real values here include
    # quoted/lettered position suffixes (e.g. 415"1A", 831'FL') and a
    # wrapped "126 NO.2"-style two-line value, not just a bare ATA zone
    # number.
    "ZONE": {"pattern": r"^[A-Za-z0-9][A-Za-z0-9 \"'.&/-]*$", "allow_empty": True, "uppercase": True},
    "DESIGNATION": {"allow_empty": True},
    "VENDOR": {"allow_empty": True},
    "PART_NUMBER": {"allow_empty": True},
    "SERIAL_NUMBER": {"allow_empty": True},
    "MANUFACTURE_DATE": {"pattern": _STRICT_DATE_RE, "allow_empty": True},
    "INSTALL_DATE": {"pattern": _STRICT_DATE_RE, "allow_empty": True},
    "THRESHOLD_MO": {"pattern": _NUM_RE, "allow_empty": True},
    "THRESHOLD_FH": {"pattern": _NUM_RE, "allow_empty": True},
    "THRESHOLD_FC": {"pattern": _NUM_RE, "allow_empty": True},
    "INTERVAL_MO": {"pattern": _NUM_RE, "allow_empty": True},
    "INTERVAL_FH": {"pattern": _NUM_RE, "allow_empty": True},
    "INTERVAL_FC": {"pattern": _NUM_RE, "allow_empty": True},
    # Free text tolerated -- see module docstring.
    "LAST_CHECK_DATE": {"allow_empty": True},
    "LAST_CHECK_FH": {"pattern": _NUM_RE, "allow_empty": True},
    "LAST_CHECK_FC": {"pattern": _NUM_RE, "allow_empty": True},
    "LIFE_MO": {"pattern": _NUM_RE, "allow_empty": True},
    "LIFE_LIMIT": {"pattern": _NUM_RE, "allow_empty": True},
    "NEXT_DUE_DATE": {"allow_empty": True},
    "NEXT_DUE_FH": {"pattern": _NUM_RE, "allow_empty": True},
    "NEXT_DUE_FC": {"pattern": _NUM_RE, "allow_empty": True},
    # Header metadata -- a single OCR misread here shouldn't flag every row
    # of the page, same reasoning this package's other header-plus-body OCR
    # variants use.
    "AIRCRAFT_REG": {"allow_empty": True},
    "MSN": {"allow_empty": True},
    "AIRCRAFT_TYPE": {"allow_empty": True},
    "STATUS_DATE": {"allow_empty": True},
    "ACFT_FHS": {"allow_empty": True},
    "ACFT_FCS": {"allow_empty": True},
    "ACFT_MANUFACTURE_DATE": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_DPI = 300

# Column X-boundaries, as a fraction of the rendered page's own width -- see
# module docstring for how these were derived (a fixed-fraction layout,
# not a per-page divider-line scan).
_COLUMNS = [
    (0.08464, 0.13053, "MPD_TASK_NO"),
    (0.13053, 0.18125, "WORK_TYPE"),
    (0.18125, 0.20747, "ZONE"),
    (0.20747, 0.34739, "DESIGNATION"),
    (0.34739, 0.39413, "VENDOR"),
    (0.39413, 0.44058, "PART_NUMBER"),
    (0.44058, 0.48789, "SERIAL_NUMBER"),
    (0.48789, 0.52210, "MANUFACTURE_DATE"),
    (0.52210, 0.55971, "INSTALL_DATE"),
    (0.55971, 0.58678, "THRESHOLD_MO"),
    (0.58678, 0.61299, "THRESHOLD_FH"),
    (0.61299, 0.63976, "THRESHOLD_FC"),
    (0.63976, 0.66629, "INTERVAL_MO"),
    (0.66629, 0.69251, "INTERVAL_FH"),
    (0.69251, 0.71900, "INTERVAL_FC"),
    (0.71900, 0.75833, "LAST_CHECK_DATE"),
    (0.75833, 0.78570, "LAST_CHECK_FH"),
    (0.78570, 0.81049, "LAST_CHECK_FC"),
    (0.81049, 0.83128, "LIFE_MO"),
    (0.83128, 0.86892, "LIFE_LIMIT"),
    (0.86892, 0.90596, "NEXT_DUE_DATE"),
    (0.90596, 0.93417, "NEXT_DUE_FH"),
    (0.93417, 0.95754, "NEXT_DUE_FC"),
]

_TEXT_JOIN_COLS = {"WORK_TYPE", "ZONE", "DESIGNATION", "VENDOR"}
_CODE_COLS = {"MPD_TASK_NO", "PART_NUMBER", "SERIAL_NUMBER"}
_STRICT_DATE_COLS = {"MANUFACTURE_DATE", "INSTALL_DATE"}
_LOOSE_DATE_COLS = {"LAST_CHECK_DATE", "NEXT_DUE_DATE"}
_NUM_COLS = {
    "THRESHOLD_MO", "THRESHOLD_FH", "THRESHOLD_FC",
    "INTERVAL_MO", "INTERVAL_FH", "INTERVAL_FC",
    "LAST_CHECK_FH", "LAST_CHECK_FC",
    "LIFE_MO", "LIFE_LIMIT",
    "NEXT_DUE_FH", "NEXT_DUE_FC",
}

_DATE_TOKEN_RE = re.compile(r"\d{1,2}[-/][A-Za-z]{3}[-/]\d{2,4}")
_NUM_TOKEN_RE = re.compile(r"\d[\d,]*")
_CODE_STRIP_CHARS = " _\"'`‘’“”.,;:()[]{}|~="

# Row-anchor shape/vocabulary checks -- see module docstring.
_ZONE_TOKEN_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9"\'.&/-]{0,12}$')
_TASK_RE = re.compile(r"^\d{6}-[A-Z0-9]{1,3}-\d{1,2}$")
_WORK_TYPE_MULTI_FIRST = {"leak", "capacity", "functional", "workshop"}
_WORK_TYPE_SINGLE = {
    "restoration", "cleaning", "replacement", "hst", "overhaul",
    "charging", "discard", "test", "weight",
}


def _is_work_type_vocab(text: str) -> bool:
    cleaned = text.strip(_CODE_STRIP_CHARS).lower()
    return cleaned in _WORK_TYPE_SINGLE or cleaned in _WORK_TYPE_MULTI_FIRST


def _row_has_work_type_vocab(work_type_field: str) -> bool:
    return any(_is_work_type_vocab(w) for w in work_type_field.split())

# Y-tolerance for merging two ZONE-strip word tops into the same anchor
# (e.g. a stray split OCR box for one physical token) -- comfortably under
# the tightest real row-to-row pitch confirmed in the sample (~70px @ 300
# DPI for a single-line row).
_ANCHOR_MERGE_PX = 20
# Fallback row pitch (px @ 300 DPI) used to bound the first/last row's own
# open Y-edge on a page -- the median of this page's own real anchor gaps
# is used instead whenever at least two anchors are found; this is only a
# floor for the (rare) single-anchor-page case.
_DEFAULT_PITCH_PX = 90


async def _ocr_column(img, name: str, y0: int, y1: int) -> list[tuple[float, str]]:
    """OCR one column's full-height strip and return (top, text) pairs in
    original-image page coordinates -- see module docstring for why every
    column is read this way rather than one whole-page pass."""
    w = img.width
    for lo, hi, col in _COLUMNS:
        if col == name:
            x0, x1 = int(lo * w), int(hi * w)
            break
    else:
        raise KeyError(name)
    if y1 <= y0:
        return []
    crop = img.crop((x0, y0, x1, y1))
    words = await ocr_words(crop, psm=6, min_conf=-1)
    out = []
    for wd in words:
        text = str(wd.get("text", "")).strip()
        if not text:
            continue
        out.append((y0 + wd["top"], text))
    return out


def _clean_field(name: str, tokens: list[tuple[float, str]]) -> str:
    ordered = [t for _, t in sorted(tokens, key=lambda t: t[0])]
    if name in _TEXT_JOIN_COLS:
        text = " ".join(ordered)
        return " ".join(text.split())
    if name in _CODE_COLS:
        text = " ".join(ordered)
        text = " ".join(text.split())
        return text.strip(_CODE_STRIP_CHARS)
    if name in _STRICT_DATE_COLS:
        text = " ".join(ordered)
        m = _DATE_TOKEN_RE.search(text)
        return m.group(0) if m else ""
    if name in _LOOSE_DATE_COLS:
        text = " ".join(ordered)
        m = _DATE_TOKEN_RE.search(text)
        if m:
            return m.group(0)
        # Free-text fallback -- see module docstring (e.g. "REFER TO
        # ENGINE LLP", "Refer to Last A/C Ck sheet").
        return " ".join(text.split()).strip(_CODE_STRIP_CHARS)
    if name in _NUM_COLS:
        text = " ".join(ordered)
        found = _NUM_TOKEN_RE.findall(text)
        return max(found, key=len) if found else ""
    return " ".join(ordered)


def _tokens_in_window(col_tokens: list[tuple[float, str]], y0: float, y1: float) -> list[tuple[float, str]]:
    return [t for t in col_tokens if y0 <= t[0] < y1]


async def _parse_header(img) -> dict:
    """Page header metadata -- two side-by-side label:value blocks (see
    module docstring). Parsed by fixed line index within each block's own
    OCR'd text rather than by regex label matching, since OCR noise on the
    labels themselves (e.g. "A/C" reading as "AIC") is common but the
    LINE ORDER is fixed by the template and each line's own trailing
    whitespace-separated token is reliably the value regardless of how
    noisy its own label read."""
    fields = ["AIRCRAFT_REG", "MSN", "AIRCRAFT_TYPE",
              "STATUS_DATE", "ACFT_FHS", "ACFT_FCS", "ACFT_MANUFACTURE_DATE"]
    meta = {k: "" for k in fields}
    w, h = img.size

    left_crop = img.crop((int(w * 0.34), 0, int(w * 0.55), int(h * 0.10)))
    left_text = await ocr_text(left_crop, psm=6)
    left_lines = [ln.strip() for ln in left_text.splitlines() if ln.strip()]
    left_keys = ["AIRCRAFT_REG", "MSN", "AIRCRAFT_TYPE"]
    for key, line in zip(left_keys, left_lines):
        toks = line.split()
        if toks:
            meta[key] = toks[-1].strip(_CODE_STRIP_CHARS)

    right_crop = img.crop((int(w * 0.75), 0, w, int(h * 0.10)))
    right_text = await ocr_text(right_crop, psm=6)
    right_lines = [ln.strip() for ln in right_text.splitlines() if ln.strip()]
    right_keys = ["STATUS_DATE", "ACFT_FHS", "ACFT_FCS", "ACFT_MANUFACTURE_DATE"]
    for key, line in zip(right_keys, right_lines):
        toks = line.split()
        if toks:
            meta[key] = toks[-1].strip(_CODE_STRIP_CHARS)

    return meta


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback (see
    sheet_types/ht.py) -- this variant's SIGNATURES is deliberately empty
    (see module docstring).

    Requires the bare "SECTION" banner word (the source scan's own leading
    "P" of "PLANNING" is missing on every page of the sample and the OCR
    read of the remainder is inconsistent run to run -- "LANNING"/
    "LANKING" both confirmed directly -- so only the reliably-read
    "SECTION" tail is anchored on), the "DEVELOPMENT" banner word, and the
    un-obscured "ITEMS LIST" fragment of the title (the title's own
    "CONTROLLED" is partly covered by the operator wordmark graphic on the
    sample). Checked directly (grep) against every SIGNATURES list in
    occm.py/ht.py/llp.py and every occm_variants/ht_variants/llp_variants
    module's own SIGNATURES/ocr_detect anchor text -- no collision found
    (every other "SECTION" occurrence anywhere in the project is a plain
    Python identifier/field name, never a SIGNATURES or ocr_detect anchor
    string); the born-digital sibling al_development_controlled_items_
    list.py owns the plain-text "AL DEVELOPMENT DIVISION"/"MPD TASK Work
    Type ZONE" phrases for its own (different) SIGNATURES-based detection
    path and carries no ocr_detect() of its own."""
    try:
        img = await render_page(pdf_path, 0, dpi=_DPI)
        w, h = img.size
        crop = img.crop((0, 0, w, int(h * 0.14)))
        text = (await ocr_text(crop, psm=6)).upper()
        return "DEVELOPMENT" in text and "SECTION" in text and "ITEMS LIST" in text
    except Exception:
        return False


def _median(values: list[float]) -> float:
    s = sorted(values)
    n = len(s)
    if n == 0:
        return _DEFAULT_PITCH_PX
    mid = n // 2
    if n % 2:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2


async def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    header_meta: dict[str, str] = {}
    n_pages = await page_count(pdf_path)

    # Header/data divider sits just below the column-header row on every
    # page of the sample (confirmed directly, ~y=0.135 of page height at
    # 300 DPI) -- data scanning starts a little below that.
    y0_frac = 0.135

    for page_index in range(n_pages):
        img = await render_page(pdf_path, page_index, dpi=_DPI)
        w, h = img.size
        y0 = int(h * y0_frac)
        y1 = h

        page_meta = await _parse_header(img)
        if not header_meta:
            header_meta = page_meta
        else:
            for k, v in page_meta.items():
                if v and not header_meta.get(k):
                    header_meta[k] = v

        col_tokens: dict[str, list[tuple[float, str]]] = {}
        for _, _, name in _COLUMNS:
            col_tokens[name] = await _ocr_column(img, name, y0, y1)

        # Anchors are the union of three independently-read signals, not
        # ZONE alone -- confirmed directly necessary: ZONE is the most
        # reliably-populated column overall (see module docstring), but an
        # occasional single row's own ZONE token still comes back blank or
        # shape-rejected, which -- if ZONE were the only anchor source --
        # would silently fold that row into a neighbouring row's own
        # window instead of getting one of its own. MPD_TASK_NO's and
        # WORK_TYPE's own well-known dedup weakness (see module docstring)
        # only matters for a column used as the PRIMARY, sole anchor
        # source; used here as a secondary, unioned-in signal, a dedup'd-
        # away MPD_TASK_NO/WORK_TYPE value just means that one extra
        # signal doesn't fire for that particular row, not that the row is
        # lost outright, since ZONE (or the other of this pair) still
        # anchors it.
        raw_anchors: list[float] = []
        for top, text in col_tokens["ZONE"]:
            if _ZONE_TOKEN_RE.match(text.strip(_CODE_STRIP_CHARS)):
                raw_anchors.append(top)
        for top, text in col_tokens["MPD_TASK_NO"]:
            if _TASK_RE.match(text.strip(_CODE_STRIP_CHARS).upper()):
                raw_anchors.append(top)
        for top, text in col_tokens["WORK_TYPE"]:
            if _is_work_type_vocab(text):
                raw_anchors.append(top)
        raw_anchors.sort()
        merged: list[float] = []
        for a in raw_anchors:
            if merged and a - merged[-1] <= _ANCHOR_MERGE_PX:
                continue
            merged.append(a)
        anchors = merged
        if not anchors:
            continue

        gaps = [anchors[i + 1] - anchors[i] for i in range(len(anchors) - 1)]
        pitch = _median(gaps) if gaps else _DEFAULT_PITCH_PX

        for i, atop in enumerate(anchors):
            prev_top = anchors[i - 1] if i > 0 else atop - pitch
            next_top = anchors[i + 1] if i + 1 < len(anchors) else atop + pitch
            row_y0 = (prev_top + atop) / 2
            row_y1 = (atop + next_top) / 2

            row: dict[str, str] = {}
            for _, _, name in _COLUMNS:
                toks = _tokens_in_window(col_tokens[name], row_y0, row_y1)
                row[name] = _clean_field(name, toks)

            # Corroboration check -- see module docstring. A genuine row
            # always has at least one of these independently-read,
            # STRUCTURALLY-VALIDATED signals (a real work-type vocabulary
            # word, a real task-code shape, a real date shape, or a
            # digit-bearing part number) alongside its own anchor; a stray
            # sign-off/footnote fragment -- free-form prose, not a
            # structured field -- was confirmed directly never to produce
            # any of these (merely requiring a NON-EMPTY WORK_TYPE/
            # PART_NUMBER was tried first and confirmed too loose: ordinary
            # prose words from the sign-off block landed in those same
            # X-bands and passed a bare non-empty check).
            work_type_ok = _row_has_work_type_vocab(row["WORK_TYPE"])
            task_ok = bool(_TASK_RE.match(row["MPD_TASK_NO"].strip(_CODE_STRIP_CHARS).upper()))
            date_ok = bool(row["INSTALL_DATE"])
            pn_ok = bool(row["PART_NUMBER"]) and any(c.isdigit() for c in row["PART_NUMBER"])
            if not (work_type_ok or task_ok or date_ok or pn_ok):
                continue

            row["_page"] = page_index + 1
            row.update(header_meta)
            records.append(row)

    return records
