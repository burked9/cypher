"""Born-scanned "HARD TIME COMPONENTS STATUS" report -- full-page-raster
PDF, no usable text layer at all (confirmed directly: `page.get_text()`
returns empty on every page, and `page.get_drawings()` is empty while
`page.get_images()` holds exactly one full-page raster image per page --
the ruled grid visible on render is baked into that raster image, not
vector-drawn). Rendering to an image shows a clean, sharp, ordinary
printed report (not a photocopy artifact/handwriting case) -- every value
is machine-printed, so a per-column-strip OCR pass end to end is reliable
here.

Distinct from this project's other "Hard Time Components Status"-titled
variants: this file's own title line is the bare, unqualified phrase
"HARD TIME COMPONENTS STATUS" (no "FOR A/C-REGISTRATION" suffix like
`georgian_airways_ht_components_status.py`/`..._scanned.py`, no "REPORT"
suffix like `hard_time_day_fhr_cyc_matrix_scanned.py`), and its own
15-column ruled grid -- ATA / NOMENCLATURE / MPD NUMBER OR REQUIREMENT /
APPLICABLE / TASK DESCRIPTION / PN / SN / POS, then a 3-column
"INSTALLATION INFORMATION" group (DATE / AIRCRAFT (H/C) / COMP (H/C)
SINCE MAINT) and a 4-column "SERVICE INFORMATION" group (MAINTENANCE
REQUIREMENT / INTERVAL / LAST ACCOMPLISHED / NEXT (DATE/ACFT H/ACFT C))
-- has no overlap with any sibling module's own column set (checked
directly against `hard_time_status_mpd_cert_fin.py`'s MPD Item #/P/N
#/S/N #/DESCRIPTION/CERTIFICATES/FIN/TASK layout,
`hard_time_components_bordered_table.py`'s ATA/MPD REF./POS/PART
NUMBER/... layout, and `ht_components_status_ruled_grid.py`'s SL NO/MPD
REF/DESCRIPTION/... layout).

Header block (repeats verbatim at the top of every page, a small wordmark
graphic to the left plus three label/value columns to the right of the
title line)::

    <wordmark graphic>          HARD TIME COMPONENTS STATUS
    REGISTER: <tail>            SERIAL NUMBER: <MSN>       REPORT DATE: <dd-Mon-yy>
    MODEL: <type>                LINE NUMBER: <n>            TAH: <n>
    MANUFACTURE DATE: <date>    VARIABLE NUMBER: <code>     TAC: <n>

followed by the main ruled table, two header rows tall (row 1: blank x8 |
"INSTALLATION INFORMATION" x3 | "SERVICE INFORMATION" x4; row 2: the 15
actual column labels). Confirmed directly on the sample file that this
header block (both the title/metadata box and the two-row table header)
sits at the same page-fraction Y position on every page to within a few
pixels of scan-to-scan skew -- not hardcoded, though: `_find_data_start_y()`
below locates the real per-page top-of-data-row Y at runtime the same way
this project's other raster-grid HT variants do (e.g.
`aircraft_specification_file_htc_status_scanned.py`), since a few pixels
of skew is enough to misalign a hardcoded constant against this file's own
fairly tight ~36-54px single-line row pitch.

Column X-boundaries below are expressed as fractions of the rendered
page's own width (this project's usual convention for a raster-grid
table) -- derived directly from a numpy column-darkness scan of the ruled
grid's own vertical divider lines on the sample file's page 1, confirmed
against three further pages.

Row anchor: INTERVAL (e.g. "15000 FH", "5 YR", "10 YR", "Note",
"Unlimited") is used as the per-row Y anchor rather than TASK DESCRIPTION
or MAINTENANCE REQUIREMENT -- confirmed directly on the sample file: a
single physical/ruled row sometimes carries a *stacked, multi-line*
MAINTENANCE REQUIREMENT value when more than one task type applies under
one shared interval/date set (e.g. an Engine Firex Cylinder's own
"Hydrostatic Test" / "Overhaul" two-line cell, sharing one row's DATE/
AIRCRAFT (H/C)/INTERVAL/LAST ACCOMPLISHED/NEXT), which would double-count
that row if used as the row-clustering anchor; INTERVAL, by contrast, is
confirmed to stay single-line on every one of those same rows, while
still being non-blank on every real data row including special rows whose
PN/SN/POS/INSTALLATION-INFORMATION cells are replaced by a single spanning
note across the row (e.g. "Life Jackets" -> "See Life Vest Inventory",
"First Aid Kit"/"Medical Kit" -> "Will be installed by the next operator"
-- INTERVAL still reads "Note" on these).

Row grain: one row per ruled table row -- unlike several sibling HT
variants, this file does NOT blank/merge NOMENCLATURE, PART_NUMBER,
SERIAL_NUMBER or POSITION across a component's own multiple task rows;
each ruled row repeats its own identity cells in full (confirmed directly,
e.g. "Engine Firex Cylinder" / "33700002" / "56970D1" / "LH" is printed on
all three of its own separate task rows: the combined Hydrostatic
Test/Overhaul row, the Weight Check row and the squib Discard row). No
forward-fill is therefore needed or applied.

The special spanning-note rows described above (Life Jackets/First Aid
Kit/Medical Kit) render their note text centered across several ruled
columns at once (PART_NUMBER through COMP_HC_SINCE_MAINT). Rather than
attempt to detect and reconstruct that span, each affected column's own
per-column-strip OCR pass simply captures whatever fragment (if any) of
the centered text happens to fall inside that column's own X-band -- this
project's standard "never force a wrong split" handling of an irregular
merge, applied here to a horizontal span instead of a vertical one.

AIRCRAFT_HC, COMP_HC_SINCE_MAINT and NEXT_DUE cells sometimes stack two
figures on their own two printed lines within one ruled row (e.g. a main
landing gear row's AIRCRAFT_HC reading "58442" over "45260", its own
flight-hours and flight-cycles totals at installation; NEXT_DUE reading
"39943 FC (Acft MSN <msn>)" over "17-Apr-18" on the same physical row for
a component tracked by both a cycle limit and a calendar-date limit). The
two lines are joined space-separated into one field value rather than
guessed apart into separate FH/FC sub-columns -- the ruled grid renders
them as one cell with no internal delimiter to split on reliably, and
which figure is FH vs FC vs a plain date is not determinable from layout
alone on every row (some rows carry only one line, others two, depending
on which basis -- hours, cycles, calendar date -- applies to that specific
component).

Sensitivity note: page 4 of the sample file carries a signature block
(name, job title, "Attorney in Fact" certificate reference) BELOW the
ruled table, entirely outside every column's own X-band and well below
the last real data row's own Y position -- confirmed directly this text
is never picked up by any column's per-strip OCR pass or attached to any
row (the row-anchor clustering only clusters INTERVAL-column words that
are non-blank AND interval-shaped; anything OCR'd far below the last real
anchor simply has no anchor within tolerance and is dropped). No signer
name, job title or certificate number is captured into any output field.
"""
from __future__ import annotations
import re

import numpy as np
from PIL import Image

from sheet_types.ht_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_words, ocr_text, page_count

NAME = "Hard Time Components Status (MPD Number or Requirement, Scanned)"

# Deliberately empty: this file's own plain-text layer is blank on every
# page (see module docstring), so a plain-text SIGNATURES phrase would
# never be checked against real page content anyway. Detected instead via
# `ocr_detect()` below, through the router's blank-text-layer OCR-fallback
# path (`sheet_types/ht.py`'s own `detect_variant()`).
SIGNATURES: list[str] = []

CANONICAL_COLUMNS = [
    "ATA",
    "NOMENCLATURE",
    "MPD_NUMBER_OR_REQUIREMENT",
    "APPLICABLE",
    "TASK_DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "POSITION",
    "INSTALL_DATE",
    "AIRCRAFT_HC",
    "COMP_HC_SINCE_MAINT",
    "MAINTENANCE_REQUIREMENT",
    "INTERVAL",
    "LAST_ACCOMPLISHED",
    "NEXT_DUE",
    # Header metadata -- same on every page of a given file, stamped on
    # every row (see module docstring for the header block layout).
    "AIRCRAFT_REG",
    "AIRCRAFT_MODEL",
    "MANUFACTURE_DATE",
    "AIRCRAFT_MSN",
    "LINE_NUMBER",
    "VARIABLE_NUMBER",
    "REPORT_DATE",
    "TAH",
    "TAC",
]

_OVERRIDES = {
    "ATA": {"allow_empty": True},
    "NOMENCLATURE": {"allow_empty": True, "uppercase": True},
    "MPD_NUMBER_OR_REQUIREMENT": {"allow_empty": True},
    "APPLICABLE": {"allow_empty": True, "uppercase": True},
    "TASK_DESCRIPTION": {"allow_empty": True},
    "PART_NUMBER": {"allow_empty": True},
    "SERIAL_NUMBER": {"allow_empty": True},
    "POSITION": {"allow_empty": True, "uppercase": True},
    "INSTALL_DATE": {"allow_empty": True},
    "AIRCRAFT_HC": {"allow_empty": True},
    "COMP_HC_SINCE_MAINT": {"allow_empty": True},
    "MAINTENANCE_REQUIREMENT": {"allow_empty": True},
    "INTERVAL": {"allow_empty": True},
    "LAST_ACCOMPLISHED": {"allow_empty": True},
    "NEXT_DUE": {"allow_empty": True},
    # Header metadata -- a single OCR misread here shouldn't flag every
    # row of the file, same reasoning this package's other header-plus-body
    # OCR variants use.
    "AIRCRAFT_REG": {"allow_empty": True},
    "AIRCRAFT_MODEL": {"allow_empty": True},
    "MANUFACTURE_DATE": {"allow_empty": True},
    "AIRCRAFT_MSN": {"allow_empty": True},
    "LINE_NUMBER": {"allow_empty": True},
    "VARIABLE_NUMBER": {"allow_empty": True},
    "REPORT_DATE": {"allow_empty": True},
    "TAH": {"allow_empty": True},
    "TAC": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Column X-boundaries, as a fraction of the rendered page's own width --
# derived directly from a numpy column-darkness scan of the ruled grid's
# own vertical divider lines (see module docstring).
_COLUMNS = [
    (0.02929, 0.04593, "ATA"),
    (0.04593, 0.11005, "NOMENCLATURE"),
    (0.11005, 0.15993, "MPD_NUMBER_OR_REQUIREMENT"),
    (0.15993, 0.20428, "APPLICABLE"),
    (0.20428, 0.34482, "TASK_DESCRIPTION"),
    (0.34482, 0.39113, "PART_NUMBER"),
    (0.39113, 0.43587, "SERIAL_NUMBER"),
    (0.43587, 0.46041, "POSITION"),
    (0.46041, 0.49921, "INSTALL_DATE"),
    (0.49921, 0.56611, "AIRCRAFT_HC"),
    (0.56611, 0.62867, "COMP_HC_SINCE_MAINT"),
    (0.62867, 0.69477, "MAINTENANCE_REQUIREMENT"),
    (0.69477, 0.74703, "INTERVAL"),
    (0.74703, 0.81908, "LAST_ACCOMPLISHED"),
    (0.81908, 0.91173, "NEXT_DUE"),
]

_ANCHOR_COL = "INTERVAL"

_HEADER_FIELDS = [
    "AIRCRAFT_REG", "AIRCRAFT_MODEL", "MANUFACTURE_DATE", "AIRCRAFT_MSN",
    "LINE_NUMBER", "VARIABLE_NUMBER", "REPORT_DATE", "TAH", "TAC",
]

# A ruled-border sliver at a column's own left/right edge occasionally OCRs
# as a lone punctuation "word" ("|", "_", "=", "—") floating at the same Y
# as a real text row -- dropped before joining a cell's tokens, since no
# genuine value in this file is pure punctuation.
_PURE_PUNCT_RE = re.compile(r"^[|_=~—\-:;.,]+$")
_CODE_STRIP_CHARS = " _\"'`‘’“”.,;:()[]{}|~=—"

# Same-row anchor-word merge tolerance, expressed as a fraction of the
# rendered page's own height -- used only to merge INTERVAL's own
# multi-word values ("10" + "YR" as two separate OCR tokens) into a single
# row anchor. Measured directly against this file's own INTERVAL-column
# word gaps at a 300dpi render: same-row multi-word values sit ~0-1px
# apart, while the tightest *distinct-row* gaps (consecutive single-line
# "Discard squib..."/"...Firex Cylinder..." rows) measured only ~24-26px
# apart -- comfortably clear of this tolerance either way. (Row *content*
# assignment for the other 14 columns does NOT use this tolerance -- see
# the midpoint-boundary approach in `extract()` below, which is what
# actually keeps a tight row pair's own text from bleeding into each
# other while still capturing a taller wrapped-text row in full.)
_ANCHOR_TOLERANCE_FRAC = 0.004

_TITLE_RE = re.compile(r"HARD TIME COMPONENTS STATUS", re.IGNORECASE)
# "MPD NUMBER" -- this file's own column-header fragment. NOT the full
# "...NUMBER OR REQUIREMENT" phrase: confirmed directly a plain psm=6 OCR
# pass over the combined title+metadata+column-header crop reads the two-
# row grouped header out of visual (not logical) reading order -- "MPD
# NUMBER" ends one OCR'd line, but "REQUIREMENT" resurfaces several lines
# later (after the NOMENCLATURE/APPLICABLE/... column-name row, which
# OCR reads in between) rather than immediately after "OR", so a
# contiguous "NUMBER OR REQUIREMENT" match never fires despite the source
# column header reading that way visually. "MPD NUMBER" alone survives
# intact and is still checked against every SIGNATURES list in
# occm.py/ht.py/llp.py and every occm_variants/ht_variants/llp_variants
# module's own SIGNATURES list, plus a plain grep for "MPD NUMBER"; no
# collision found anywhere else in the project.
_SUBTITLE_RE = re.compile(r"MPD NUMBER", re.IGNORECASE)

_REGISTER_RE = re.compile(r"REGISTER:\s*(\S+)", re.IGNORECASE)
_MODEL_RE = re.compile(r"MODEL:\s*(\S+)", re.IGNORECASE)
_MANUFACTURE_DATE_RE = re.compile(r"MANUFACTURE DATE:\s*(\S+)", re.IGNORECASE)
_AIRCRAFT_MSN_RE = re.compile(r"SERIAL NUMBER:\s*(\S+)", re.IGNORECASE)
_LINE_NUMBER_RE = re.compile(r"LINE NUMBER:\s*(\S+)", re.IGNORECASE)
_VARIABLE_NUMBER_RE = re.compile(r"VARIABLE NUMBER:\s*(\S+)", re.IGNORECASE)
_REPORT_DATE_RE = re.compile(r"REPORT DATE:\s*(\S+)", re.IGNORECASE)
_TAH_RE = re.compile(r"\bTAH:\s*(\S+)", re.IGNORECASE)
_TAC_RE = re.compile(r"\bTAC:\s*(\S+)", re.IGNORECASE)


def _col_bounds(w: int, name: str) -> tuple[int, int]:
    for lo, hi, col in _COLUMNS:
        if col == name:
            return int(lo * w), int(hi * w)
    raise KeyError(name)


def _table_x_span(w: int) -> tuple[int, int]:
    return int(_COLUMNS[0][0] * w), int(_COLUMNS[-1][1] * w)


def _row_dark_frac(arr: np.ndarray, x0: int, x1: int) -> np.ndarray:
    sub = arr[:, x0:x1]
    dark = sub < 200
    return dark.sum(axis=1) / sub.shape[1]


def _find_header_and_data_y(img) -> tuple[int, int]:
    """Locate this page's own header-metadata-box bottom Y (top of the
    ruled table) and the ruled table's own header-row bottom Y (top of the
    first real data row). Not hardcoded -- confirmed directly a few pixels
    of scan-to-scan skew shift these Y positions slightly page to page
    (see module docstring)."""
    arr = np.array(img.convert("L"))
    h, w = arr.shape
    x0, x1 = _table_x_span(w)
    frac = _row_dark_frac(arr, x0, x1)
    ys = [y for y in range(0, int(h * 0.3)) if frac[y] > 0.3]
    groups: list[list[int]] = []
    for y in ys:
        if groups and y - groups[-1][-1] <= 3:
            groups[-1].append(y)
        else:
            groups.append([y])
    if not groups:
        return int(h * 0.155), int(h * 0.19)
    header_top = groups[0][0]
    # Three groups expected above the first data row: the table's own top
    # border, a partial divider under the two grouped column headers only
    # (INSTALLATION INFORMATION / SERVICE INFORMATION -- narrower than the
    # full table width, so a weaker but still-detectable band), and the
    # header row's own bottom border (confirmed directly against a
    # rendered crop on all 4 sample pages -- see module docstring).
    data_start = groups[2][-1] + 2 if len(groups) > 2 else groups[-1][-1] + 2
    return header_top, data_start


async def _ocr_column(img, name: str, y0: int, y1: int, scale: int = 2) -> list[tuple[float, float, str]]:
    x0, x1 = _col_bounds(img.width, name)
    crop = img.crop((x0, y0, x1, y1))
    if scale != 1:
        crop = crop.resize((crop.width * scale, crop.height * scale), Image.LANCZOS)
    words = await ocr_words(crop, psm=6, min_conf=-1)
    out = []
    for wd in words:
        text = str(wd.get("text", "")).strip()
        if not text or _PURE_PUNCT_RE.match(text):
            continue
        top = y0 + wd["top"] / scale
        left = wd.get("left", 0) / scale
        out.append((top, left, text))
    return out


# Two words on the same printed line can come back from Tesseract with
# slightly different (or even tied/reversed) "top" values -- confirmed
# directly on this file's own NOMENCLATURE column (e.g. "Turbine"/"Inlet"
# tied at the same top, and a wrapped "Escape"/"Slide" pair whose own tops
# sometimes reverse by a pixel or two). Sorting by bare "top" alone can
# therefore scramble same-line word order. Words are bucketed into lines
# first (anything within this many px of the same top -- well under this
# file's own single-line row height -- counts as "the same printed line"),
# then each line's own words are ordered left-to-right, and lines
# themselves top-to-bottom.
_LINE_BUCKET_PX = 8


def _clean_field(name: str, tokens: list[tuple[float, float, str]]) -> str:
    lines: list[list[tuple[float, float, str]]] = []
    for top, left, text in sorted(tokens, key=lambda item: item[0]):
        if lines and abs(top - lines[-1][0][0]) <= _LINE_BUCKET_PX:
            lines[-1].append((top, left, text))
        else:
            lines.append([(top, left, text)])
    ordered_lines = [
        [text for _, _, text in sorted(line, key=lambda item: item[1])]
        for line in lines
    ]
    text = " ".join(" ".join(line) for line in ordered_lines)
    if name in ("ATA", "PART_NUMBER", "SERIAL_NUMBER", "POSITION"):
        text = text.strip(_CODE_STRIP_CHARS)
    return text


async def _parse_header(img) -> dict:
    meta = {k: "" for k in _HEADER_FIELDS}
    w, h = img.size
    header_top, _ = _find_header_and_data_y(img)
    crop = img.crop((0, 0, w, max(header_top, 1)))
    crop = crop.resize((crop.width * 2, crop.height * 2), Image.LANCZOS)
    text = await ocr_text(crop, psm=6)

    def grab(rx: re.Pattern) -> str:
        m = rx.search(text)
        return m.group(1).strip(_CODE_STRIP_CHARS) if m else ""

    meta["AIRCRAFT_REG"] = grab(_REGISTER_RE)
    meta["AIRCRAFT_MODEL"] = grab(_MODEL_RE)
    meta["MANUFACTURE_DATE"] = grab(_MANUFACTURE_DATE_RE)
    meta["AIRCRAFT_MSN"] = grab(_AIRCRAFT_MSN_RE)
    meta["LINE_NUMBER"] = grab(_LINE_NUMBER_RE)
    meta["VARIABLE_NUMBER"] = grab(_VARIABLE_NUMBER_RE)
    meta["REPORT_DATE"] = grab(_REPORT_DATE_RE)
    meta["TAH"] = grab(_TAH_RE)
    meta["TAC"] = grab(_TAC_RE)
    return meta


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback.
    Requires BOTH this file's own bare title line ("HARD TIME COMPONENTS
    STATUS", no "FOR A/C-REGISTRATION"/"REPORT" suffix) AND its own
    distinctive "...NUMBER OR REQUIREMENT" column-header fragment --
    checked against every SIGNATURES list in occm.py/ht.py/llp.py and
    every occm_variants/ht_variants/llp_variants module's own SIGNATURES
    list, plus a plain grep for "NUMBER OR REQUIREMENT"; no collision
    found anywhere else. The bare title phrase alone is NOT used (it is a
    substring of `georgian_airways_ht_components_status_scanned.py`'s own
    combined "GEORGIAN AIRWAYS" + "HARD TIME COMPONENTS STATUS" ocr_detect
    check, though that check additionally requires "GEORGIAN AIRWAYS" and
    this file never has it -- the "NUMBER OR REQUIREMENT" fragment is a
    second, independent anchor kept for defense in depth regardless)."""
    try:
        img = await render_page(pdf_path, 0, dpi=300)
        w, h = img.size
        crop = img.crop((0, 0, w, int(h * 0.23)))
        text = (await ocr_text(crop, psm=6)).upper()
        return bool(_TITLE_RE.search(text) and _SUBTITLE_RE.search(text))
    except Exception:
        return False


async def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    header_meta = {k: "" for k in _HEADER_FIELDS}
    n_pages = await page_count(pdf_path)

    for page_index in range(n_pages):
        img = await render_page(pdf_path, page_index, dpi=300)
        h = img.height

        if not all(header_meta.values()):
            page_meta = await _parse_header(img)
            for k, v in page_meta.items():
                if v and not header_meta[k]:
                    header_meta[k] = v

        _, data_start = _find_header_and_data_y(img)

        col_words: dict[str, list[tuple[float, float, str]]] = {}
        for _, _, name in _COLUMNS:
            col_words[name] = await _ocr_column(img, name, data_start, h)

        tol = _ANCHOR_TOLERANCE_FRAC * h
        # INTERVAL words come back one OCR *word* at a time (e.g. "15000"
        # and "FH" as two separate tokens on the same physical line) --
        # cluster same-line words together first, then use each cluster's
        # own mean Y as the row anchor. A per-word shape check (rejecting
        # "15000" or "FH" in isolation for not looking like a whole
        # interval value on its own) would wrongly discard the great
        # majority of real rows, so clustering, not shape-matching, is
        # what separates real row anchors from stray noise here -- any
        # cluster with non-empty joined text counts as a row (confirmed
        # directly: INTERVAL is non-blank on every real row in the sample
        # file, see module docstring).
        anchor_words = sorted(col_words[_ANCHOR_COL], key=lambda item: item[0])
        clustered: list[float] = []
        for top, _left, text in anchor_words:
            if not text.strip():
                continue
            if clustered and abs(top - clustered[-1]) <= tol:
                continue
            clustered.append(top)

        # NOTE: a secondary anchor source (falling back to
        # MPD_NUMBER_OR_REQUIREMENT when INTERVAL OCR's blank on a real
        # row -- confirmed directly this happens on a handful of the
        # file's own "spanning note" rows, see module docstring) was tried
        # and rejected: a tall, multi-task combined row's own
        # MPD_NUMBER_OR_REQUIREMENT cell legitimately spans several
        # printed lines stacked near the TOP of that row while INTERVAL
        # sits vertically centred in the same (much taller) row, so a
        # distance-from-nearest-anchor gate big enough to catch a genuinely
        # missing row's own isolated MPD line also fired on those same
        # legitimate multi-line MPD cells within an already-anchored tall
        # row, over-splitting it into extra, mostly-blank rows (confirmed
        # directly: it added 15 spurious rows for every ~4 genuine misses
        # it recovered). Reconstructing this file's own real per-row Y
        # boundaries would need the ruled grid's own horizontal divider
        # lines rather than anchor-point heuristics -- not attempted here.
        # A handful of "spanning note" rows (Life Jackets, Medical Kit,
        # First Aid Kit, Chemical Oxygen Generators, Portable Water Firex)
        # are therefore a known, accepted source of an occasional merged-
        # row record in this variant's own output when INTERVAL's own OCR
        # pass misses that one row entirely.

        # Assign every other column's words to the nearest row by midpoint
        # boundary, not by a fixed +/- tolerance window around each row's
        # own anchor. A fixed window can't satisfy both this file's tight
        # ~24-26px single-line row pairs (squib/cylinder Discard rows) AND
        # its own much taller wrapped-text rows (a 2-3 line TASK
        # DESCRIPTION, or a NOMENCLATURE that wraps onto a second line) at
        # the same time -- confirmed directly: a tolerance loose enough to
        # capture a wrapped NOMENCLATURE's second line bled a neighbouring
        # tight row's own ATA/NOMENCLATURE/MPD_NUMBER_OR_REQUIREMENT text
        # into both rows at once, while a tolerance tight enough to keep
        # those tight rows separate cut off the second line of a wrapped
        # cell in a taller row elsewhere on the very same page. Splitting
        # at the midpoint between each pair of consecutive row anchors
        # instead gives every row exactly the vertical span the ruled grid
        # itself gives it -- a short row's own span is only as tall as the
        # gap to its tight neighbour, while a tall wrapped row's span
        # stretches all the way to ITS neighbour, comfortably covering
        # every wrapped line inside it.
        # The LAST row on a page has no next anchor to cap it against, so a
        # naive "extend to the page bottom" bound would sweep in whatever
        # sits below the ruled table itself -- on this file's own last
        # page, a signature block (signer name, job title, "Attorney in
        # Fact" certificate reference) that must never end up in any
        # output field (see module docstring's sensitivity note; confirmed
        # directly this signature text WAS captured into PART_NUMBER/
        # SERIAL_NUMBER/etc. before this cap was added). Instead, the last
        # row's own bottom bound mirrors the gap to ITS OWN previous row
        # (this file's rows are close enough in height page to page that a
        # symmetric gap is a safe, conservative stand-in for that row's
        # real ruled bottom border), falling back to a small fixed pad on
        # a page with only one detected row.
        bounds: list[tuple[float, float]] = []
        for i, atop in enumerate(clustered):
            lo = data_start if i == 0 else (clustered[i - 1] + atop) / 2
            if i < len(clustered) - 1:
                hi = (atop + clustered[i + 1]) / 2
            elif i > 0:
                hi = min(h, atop + (atop - clustered[i - 1]) / 2)
            else:
                hi = min(h, atop + h * 0.02)
            bounds.append((lo, hi))

        for (lo, hi), atop in zip(bounds, clustered):
            row: dict[str, str] = {}
            for _, _, name in _COLUMNS:
                toks = [(top, left, text) for top, left, text in col_words[name]
                        if lo <= top < hi]
                row[name] = _clean_field(name, toks)
            row["_page"] = page_index + 1
            row.update(header_meta)
            records.append(row)

    return records
