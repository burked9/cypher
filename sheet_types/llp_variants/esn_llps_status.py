"""AMOS-produced "ESN <esn> LLPs Status (<label>)" report — a per-engine
life-limited-parts rollup for a CFM56-5B powerplant, "produced by AMOS
www.swiss-as.com" per its footer (same producer as `amos.py`'s "Component
Equipment List Report", but a completely different template: no REQUIREMENT/
LIFE LIMIT sub-lines, no ATA section headers, and — critically — no text
layer at all on the known source file, so this module is OCR-only, unlike
`amos.py`).

Confirmed against the real sample file: 0 characters recovered from
`fitz`/pdfplumber's text extraction on its single page — a clean,
computer-rendered raster (crisp ruled grid, flat fills, no photograph
artifacts or skew), not a scanned/photographed form. This module renders
the page and OCRs it via `shared/ocr_bridge.py`'s async primitives
(`render_page()`/`ocr_text()`/`ocr_words()`) for the same reason every
other OCR-capable variant in this codebase does — see that module's
docstring for why the split from raw fitz/pytesseract exists (Pyodide has
neither available natively).

Layout, confirmed directly against the rendered page: a title band reading
"ESN <esn> LLPs Status (<label>)" with a report-number/date/time box to its
right, then a single 4-column ruled table (Description | TSN | CSN | Togo).
The table's FIRST data row is always the engine/assembly rollup node itself
(AMOS tree-export convention — the parent node is emitted before its
children, the same shape `amos.py`'s OCCM sibling relies on for its own
row/REQUIREMENT pairing) and reads
``<engine model> / <esn> (ENGINE POWERPLANT <aircraft type>)`` with engine-
level TSN/CSN and no Togo value; every row after it is one life-limited
part: ``<part number> / <serial number> (<description>)`` plus that part's
own TSN, CSN, and "Togo" (cycles remaining to the next life limit, printed
as ``<cycles> / <limit-dimension-letter>`` — "C" for cycles on every row of
the known sample file; no other letter has been observed, so it is *not*
hardcoded as a closed enum, just validated as a single uppercase letter).
The rest of the page below the last real row is blank (pre-drawn) table
rows carrying no text at all — confirmed directly, these have to be
skipped rather than treated as short/malformed data rows.

Naive whole-page OCR (`pytesseract.image_to_string` over the full 300dpi
render) was tried first and produces exactly the kind of garbage this
project's other scanned-table modules warn about: gridlines, the row-tree
expand/collapse icons, and the alternating row-shading all bleed into a
single flattened text dump, silently concatenating what are actually 4
separate ruled columns into one run-on line per row (e.g. a genuine
"2996:28  2'092  17'908 / C" reads back with digits fused and swapped
across column boundaries, occasionally misread as spurious letters).
Fixed the same way `part_m_engine_disk_sheet.py` and
`kalstar_engine_llp_status.py` fix it: detect the ruled grid directly from
pixel darkness (this is vector-drawn, not photographed, so no rotational
skew correction is needed — a plain full-width/full-height darkness scan
is already clean) and OCR each cell's own crop independently, rather than
trust any single whole-row or whole-page text reconstruction.

Row/column detection specifics, confirmed directly against the real
sample file:

- Row lines: rows of near-continuous horizontal darkness across the full
  page width, collapsed to one y-position per printed rule. The table
  region is recovered as the longest run of consecutive row lines whose
  gaps all stay tight (mirrors `part_m_engine_disk_sheet.py`'s
  `_longest_dense_run()` — the sparser title-box rules above the table
  don't survive that filter). The first row inside that run is the
  "Description / TSN / CSN / Togo" column-header text row, not a data
  row — skipped, then every following pair of consecutive row lines is
  one table row (blank trailing rows included; they're filtered out later
  by having no parseable Description cell, not by row position).
- Column lines: full-height darkness scan restricted to that same table
  band. This turned up *more* than the real 4 data columns' worth of
  dividers on the real sample file — confirmed directly, two spurious
  extra lines sit just inside the left edge (the row-tree's own
  expand/collapse-box border, a real vertical rule but one that bounds a
  cosmetic icon gutter, not a data column) and one more sits just inside
  the right edge (a second, inner frame rule — this format double-draws
  its outer border, confirmed by direct pixel sampling: two separate
  ~4px-wide dark bands only ~30px apart at both the left and right page
  edges). Dropping the true outermost line on each side first (the page's
  own frame, always the min/max detected position) and then merging any
  *remaining* lines still within a small pixel distance of each other
  recovers exactly 5 boundaries -> 4 columns on the real sample file. This
  is the opposite bug from a plain "merge close lines by averaging"
  pass: averaging a real content-column boundary together with the
  discarded outer frame line shifted it inward or outward by ~15px,
  which was enough to leave a sliver of that second frame rule inside the
  rightmost (Togo) column's crop — read by Tesseract as a spurious
  trailing "|" appended to every row's Togo value until this was caught
  by comparing cropped-cell OCR output against the rendered image
  directly, row by row.
- Numeric-cell left-edge bleed: an early pass with only a few pixels of
  left padding on the TSN/CSN cell crops misread values with a spurious
  leading digit (e.g. a genuine "2996:28" came back as "12996:28") on
  every row — the left ruled line bleeding into the crop and being read
  as a "1". A small (~6px) left/right pad on every cell crop, confirmed
  directly against the real file to be enough margin without cutting into
  real digits, removes it entirely; this is the same class of fix
  `kalstar_engine_llp_status.py`'s `_tight_crop()` docstring describes for
  its own narrower numeric columns, just resolved here with a fixed pad
  rather than a glyph-bounding-box crop since this format's columns are
  wide enough not to need one.

Self-check performed, not blind trust: every one of the 18 data rows on
the real sample file was checked by hand against the rendered page after
the fixes above, and every PART_NUMBER/SERIAL_NUMBER/DESCRIPTION/TSN/CSN/
TOGO cell came back correct with no ambiguity left to fold into a
catch-all — unlike some of this project's harder scanned formats, this
one *is* a clean, fully-splittable ruled grid once the column-line
detection bug above was fixed, so nothing here needed a STATUS_TRAIL-style
catch-all column. Each row still carries a `_status` field ("OK" or a
description of what failed to parse) as a machine-checkable record of
that fact, rather than asserting it silently.

Header/report metadata (ESN, ENGINE_MODEL, REPORT_LABEL, REPORT_NUMBER,
REPORT_DATE, REPORT_TIME, and the engine-level ENGINE_TSN/ENGINE_CSN
pulled off that first rollup row) is parsed once per file and stamped on
every part row, the same convention this project's other header-plus-body
variants use (e.g. `esn_disc_sheet.py`). Values below are illustrative
placeholders only, not copied from any real file::

    ESN <esn> LLPs Status (<label>)          <report_no>   <report_date>
                                              <report_time> Page 1/1
    Description                                  TSN       CSN     Togo
    <engine_model> / <esn> (ENGINE POWERPLANT <ac_type>)  <tsn>  <csn>
      <part_number> / <serial_number> (<description>)     <tsn>  <csn>  <togo> / <dim>
"""
from __future__ import annotations

import re

import numpy as np

from sheet_types.llp_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text

NAME = "ESN LLPs Status"

# Text-layer signature list deliberately empty -- the known source file has
# a 0-char text layer (see module docstring); router.py's blank-text
# fallback reaches this module purely through ocr_detect() below. Kept here
# (rather than omitted) only for interface consistency with every other
# variant module, the same reasoning `kalstar_engine_llp_status.py` and
# `part_m_engine_disk_sheet.py` give for their own empty/inert SIGNATURES.
SIGNATURES: list[str] = []

CANONICAL_COLUMNS = [
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
    "TSN",
    "CSN",
    "TOGO",
    "TOGO_DIM",
    # Header/report metadata, stamped on every row.
    "ESN",
    "ENGINE_MODEL",
    "REPORT_LABEL",
    "REPORT_NUMBER",
    "REPORT_DATE",
    "REPORT_TIME",
    "ENGINE_TSN",
    "ENGINE_CSN",
]

_HHMM_RULE = {"pattern": r"^\d+:\d{2}$", "allow_empty": True}
_APOS_INT_RULE = {"pattern": r"^\d{1,3}(?:'\d{3})*$", "allow_empty": True}
_DATE_RULE = {"pattern": r"^\d{1,2}\.[A-Za-z]{3}\.\d{4}$", "allow_empty": True}
_OVERRIDES = {
    "PART_NUMBER": {"pattern": r"^[A-Z0-9\-]+$", "uppercase": True},
    "SERIAL_NUMBER": {"pattern": r"^[A-Z0-9]+$", "uppercase": True},
    "TSN": _HHMM_RULE,
    "CSN": _APOS_INT_RULE,
    "TOGO": _APOS_INT_RULE,
    "TOGO_DIM": {"pattern": r"^[A-Z]?$", "uppercase": True, "allow_empty": True},
    "ESN": {"pattern": r"^\d+$", "allow_empty": True},
    "ENGINE_MODEL": {"pattern": r"^[A-Z0-9\-]+$", "uppercase": True, "allow_empty": True},
    "REPORT_LABEL": {"allow_empty": True},
    "REPORT_NUMBER": {"pattern": r"^\d+$", "allow_empty": True},
    "REPORT_DATE": _DATE_RULE,
    "REPORT_TIME": {"pattern": r"^\d{1,2}:\d{2}$", "allow_empty": True},
    "ENGINE_TSN": _HHMM_RULE,
    "ENGINE_CSN": _APOS_INT_RULE,
}
RULES = merged_rules(_OVERRIDES)

_DPI = 300
_DARK_THRESH = 180
_ROW_FRAC = 0.5
_COL_FRAC = 0.5
_MAX_ROW_GAP = 150       # table's own row spacing is a tight, uniform run
_COL_MERGE_DIST = 150    # collapses the icon-gutter/double-frame artifacts
                          # described in the module docstring
_CELL_PAD_X = 6
_CELL_PAD_Y = 3
_N_TABLE_COLS = 4        # Description, TSN, CSN, Togo

_TITLE_RE = re.compile(r"ESN\s+(\d+)\s+LLPs?\s+Status\s*\(\s*([A-Za-z0-9./-]+)", re.I)
_REPORT_NO_RE = re.compile(r"\b(\d{5,})\b")
_REPORT_TIME_RE = re.compile(r"\b(\d{1,2}:\d{2})\b")
_REPORT_DATE_RE = re.compile(r"(\d{1,2})\s*\.?\s*([A-Za-z]{3})\s*\.\s*(\d{4})")
_DESC_RE = re.compile(r"([A-Z0-9\-]{4,})\s*/\s*([A-Z0-9]{4,})\s*\(([^)]+)\)", re.I)
_TOGO_RE = re.compile(r"^([\d']+)\s*/\s*([A-Za-z])$")


def _collapse_and_dedup(idx: np.ndarray, gap: int = 3) -> list[int]:
    """Collapse a run of adjacent dark rows/cols (a single printed rule is
    several pixels wide) into one representative position."""
    if len(idx) == 0:
        return []
    out, run = [], [int(idx[0])]
    for i in idx[1:]:
        if i - run[-1] <= gap:
            run.append(int(i))
        else:
            out.append(int(np.mean(run)))
            run = [int(i)]
    out.append(int(np.mean(run)))
    return out


def _merge_close(lines: list[int], dist: int) -> list[int]:
    """Merge lines still within `dist` px of each other, keeping the LAST
    (rightmost/bottommost) of each close pair -- not their average. See
    module docstring: this format's real column boundary in a close pair is
    always the one nearer the cell content, and which side that is differs
    between the left-edge icon-gutter line (content starts after it) and
    the right-edge double-frame line (content ends before the outer one,
    already dropped by the caller). Averaging instead of picking a side
    left a sliver of a discarded frame line inside the last real column's
    crop on the real sample file -- confirmed directly, read back as a
    spurious trailing "|" on every affected row."""
    if not lines:
        return []
    merged = [lines[0]]
    for x in lines[1:]:
        if x - merged[-1] <= dist:
            merged[-1] = x
        else:
            merged.append(x)
    return merged


def _longest_dense_run(lines: list[int], max_gap: int) -> list[int] | None:
    if len(lines) < 3:
        return None
    diffs = [b - a for a, b in zip(lines[:-1], lines[1:])]
    best_start, best_len, cur_start, cur_len = 0, 0, 0, 0
    for i, g in enumerate(diffs):
        if g < max_gap:
            if cur_len == 0:
                cur_start = i
            cur_len += 1
        else:
            if cur_len > best_len:
                best_start, best_len = cur_start, cur_len
            cur_len = 0
    if cur_len > best_len:
        best_start, best_len = cur_start, cur_len
    if best_len < 2:
        return None
    return lines[best_start:best_start + best_len + 1]


def _detect_grid(gray: np.ndarray) -> tuple[list[int], list[int]] | None:
    """Returns (row_lines, col_lines) -- row_lines[i]:row_lines[i+1] is one
    table row band (row 0 is the column-header text row, skipped by the
    caller); col_lines has _N_TABLE_COLS + 1 entries. None if the grid
    can't be confirmed."""
    dark = gray < _DARK_THRESH
    row_frac = dark.mean(axis=1)
    h_lines = _collapse_and_dedup(np.where(row_frac > _ROW_FRAC)[0])
    band = _longest_dense_run(h_lines, _MAX_ROW_GAP)
    if band is None or len(band) < 3:
        return None

    y0, y1 = band[0], band[-1]
    col_frac = dark[y0:y1, :].mean(axis=0)
    raw_cols = _collapse_and_dedup(np.where(col_frac > _COL_FRAC)[0])
    if len(raw_cols) < 2:
        return None
    inner = raw_cols[1:-1]  # drop the page's own outer frame border, each side
    col_lines = _merge_close(inner, _COL_MERGE_DIST)
    if len(col_lines) != _N_TABLE_COLS + 1:
        return None
    return band, col_lines


async def _cell_text(img, x0: int, x1: int, y0: int, y1: int, psm: int = 7) -> str:
    crop = img.crop((x0 + _CELL_PAD_X, y0 + _CELL_PAD_Y, x1 - _CELL_PAD_X, y1 - _CELL_PAD_Y))
    return (await ocr_text(crop, psm=psm)).strip()


async def _parse_title_block(img) -> dict:
    w = img.width
    meta: dict[str, str] = {}
    title_crop = img.crop((0, 0, int(w * 0.80), int(img.height * 0.10)))
    title_text = await ocr_text(title_crop, psm=7)
    m = _TITLE_RE.search(title_text)
    if m:
        meta["ESN"] = m.group(1)
        meta["REPORT_LABEL"] = m.group(2).strip()

    box_crop = img.crop((int(w * 0.78), 0, w, int(img.height * 0.10)))
    box_text = await ocr_text(box_crop, psm=6)
    m = _REPORT_NO_RE.search(box_text)
    if m:
        meta["REPORT_NUMBER"] = m.group(1)
    m = _REPORT_TIME_RE.search(box_text)
    if m:
        meta["REPORT_TIME"] = m.group(1)
    m = _REPORT_DATE_RE.search(box_text)
    if m:
        meta["REPORT_DATE"] = f"{int(m.group(1)):02d}.{m.group(2).capitalize()}.{m.group(3)}"

    # Deliberately no blanket `meta.setdefault(key, "")` pass here: the
    # engine-rollup row (extract()'s i == 0 case) still needs to be able to
    # fill ESN/REPORT_LABEL via `meta.setdefault(...)` if the title-block
    # OCR above missed them -- pre-seeding those keys with "" here would
    # make that later setdefault a no-op (a key already present, even with
    # an empty value, blocks setdefault). Every field still ends up
    # populated in each output record regardless: `extract()` builds each
    # row from `{col: "" for col in CANONICAL_COLUMNS}` before `rec.update
    # (meta)`, so a key missing from meta at that point still lands as "".
    return meta


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap header-only OCR check the router falls back to when a PDF has
    no usable text layer. Anchors on the title phrase's stable words alone
    ("LLPs Status") plus this producer's own footer branding -- both
    confirmed to read cleanly at 300dpi on the real sample file -- rather
    than the ESN digits or report label, which are per-file values."""
    try:
        img = await render_page(pdf_path, 0, dpi=_DPI)
        w, h = img.size
        title_text = (await ocr_text(img.crop((0, 0, int(w * 0.80), int(h * 0.10))), psm=7)).upper()
        if "LLPS STATUS" not in title_text.replace("LLP'S", "LLPS"):
            return False
        footer_text = (await ocr_text(img.crop((0, int(h * 0.95), w, h)), psm=7)).upper()
        return "AMOS" in footer_text or "SWISS-AS" in footer_text
    except Exception:
        return False


async def extract(pdf_path: str) -> list[dict]:
    img = await render_page(pdf_path, 0, dpi=_DPI)
    gray = np.array(img.convert("L"))
    grid = _detect_grid(gray)
    if grid is None:
        return []
    band, col_lines = grid
    row_lines = band[1:]  # band[0]:band[1] is the column-header text row

    meta = await _parse_title_block(img)

    records: list[dict] = []
    for i in range(len(row_lines) - 1):
        ry0, ry1 = row_lines[i], row_lines[i + 1]
        desc_raw = await _cell_text(img, col_lines[0], col_lines[1], ry0, ry1)
        m = _DESC_RE.search(desc_raw)
        if not m:
            continue  # blank pre-drawn row -- no part data to anchor on

        tok1, tok2, desc = m.group(1), m.group(2), m.group(3).strip()
        tsn_raw = await _cell_text(img, col_lines[1], col_lines[2], ry0, ry1)
        csn_raw = await _cell_text(img, col_lines[2], col_lines[3], ry0, ry1)

        if i == 0:
            # The table's first row is always the engine/assembly rollup
            # node, not a part row -- see module docstring. Its own ESN
            # should agree with the title block's; if OCR disagrees on one
            # of the two, keep the title block's value (cleaner crop, less
            # cluttered background) and don't silently overwrite it here.
            meta["ENGINE_MODEL"] = tok1
            meta.setdefault("ESN", tok2)
            meta["ENGINE_TSN"] = tsn_raw
            meta["ENGINE_CSN"] = csn_raw
            continue

        togo_raw = await _cell_text(img, col_lines[3], col_lines[4], ry0, ry1)
        rec = {col: "" for col in CANONICAL_COLUMNS}
        rec["PART_NUMBER"] = tok1
        rec["SERIAL_NUMBER"] = tok2
        rec["DESCRIPTION"] = desc
        rec["TSN"] = tsn_raw
        rec["CSN"] = csn_raw

        status = "OK"
        if not re.match(r"^\d+:\d{2}$", tsn_raw):
            status = f"UNPARSEABLE TSN: {tsn_raw!r} - verify against source PDF"
        if not re.match(r"^\d{1,3}(?:'\d{3})*$", csn_raw):
            status = f"UNPARSEABLE CSN: {csn_raw!r} - verify against source PDF"

        tm = _TOGO_RE.match(togo_raw.replace(" ", ""))
        if tm:
            rec["TOGO"] = tm.group(1)
            rec["TOGO_DIM"] = tm.group(2).upper()
        else:
            # Never guess a wrong split -- keep the raw cell text in TOGO
            # and flag it rather than force an unconfirmed value into
            # TOGO/TOGO_DIM.
            rec["TOGO"] = togo_raw
            status = f"UNPARSEABLE TOGO: {togo_raw!r} - verify against source PDF"

        rec["_status"] = status
        rec.update(meta)
        rec["_page"] = 1
        records.append(rec)

    return records
