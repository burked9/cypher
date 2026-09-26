"""Born-scanned "HT COMPONENTS STATUS REPORT" -- no extractable text layer
at all (confirmed directly: `page.get_text()` returns 0 characters on
every page of the sample), a wordmark/logo box top-left, title
"HT COMPONENTS STATUS REPORT", and a small aircraft-identity box
(registration / MSN / TAH / TAC / report date) to the right of the title,
repeating verbatim at the top of every page.

Distinct from this package's other "HT"/"HARD TIME" ... "STATUS"-titled
scanned variants (checked directly, grep, against every SIGNATURES/
ocr_detect anchor in occm.py/ht.py/llp.py and every occm_variants/
ht_variants/llp_variants module): this template's own bare title is
"HT COMPONENTS STATUS REPORT" -- not the "HARD TIME COMPONENTS STATUS
REPORT" phrase already used by `hard_time_day_fhr_cyc_matrix_scanned.py`
(that phrase begins "HARD TIME", this one begins with the bare "HT"
abbreviation, and neither is a substring of the other), and not the bare
"HT COMPONENTS STATUS" phrase already used by
`ht_components_status_ruled_grid.py` (that phrase has no "REPORT" suffix
and that module's own column layout -- SL NO/MPD REF/DESCRIPTION/... --
has no overlap with this one).

Column layout, unique to this template (9 ruled columns, confirmed
directly against every sibling module's own column set -- no overlap)::

    ATA | PART NO. | SERIAL NO. | DESCRIPTION | POS. |
    RELEASE NO. / LABEL NO. | INST-DATE | TSN | CSN

Structural quirk this module exists to handle -- each component prints
as A GROUP OF PHYSICAL ROWS, not one row per component (confirmed
directly against the rendered page, repeatedly, across several pages)::

    1. one "identity" row in the 9 columns above (ATA/PART NO./SERIAL
       NO./DESCRIPTION/POS./RELEASE NO. .../INST-DATE/TSN/CSN);
    2. exactly one static, unconditional LABEL row directly under it,
       printed in a near-black filled cell with barely-visible text
       reading (verbatim, always) "REQUIREMENT | TASKCARD | DIM | DUE AT
       | INTERVAL | TSR | EXPECTED | TO GO" -- this row carries no
       component-specific data at all, ever (confirmed directly: it
       reads identically, always, on every component block sampled
       across several pages) -- it is the table's own repeated
       sub-header, not a data row, and must never be emitted as (or
       merged into) a record;
    3. one or more "requirement" rows, each one maintenance requirement
       against that same component, REUSING the same 9 column x-positions
       but under the label row's field names instead: REQUIREMENT (at
       PART NO.'s x-position) | TASKCARD (at SERIAL NO.'s x-position) |
       DIM (at DESCRIPTION's x-position) | DUE AT (at POS.'s x-position) |
       INTERVAL (at RELEASE NO. .../LABEL NO.'s x-position) | TSR (at
       INST-DATE's x-position) | EXPECTED (at TSN's x-position) | TO GO
       (at CSN's x-position) -- confirmed directly, pixel-cropped, cell
       by cell, against several real rows on the sample file (e.g. a
       "RESTORE" requirement row whose own DUE AT/INTERVAL/TSR/EXPECTED/
       TO GO values crop cleanly out of the POS./RELEASE NO..../
       INST-DATE/TSN/CSN column boxes respectively) -- ATA's own
       x-position is unused/blank on a requirement row.

This module's own strategy, given the above, mirrors this package's other
whole-column-OCR + content-plausibility-gated scanned variants (e.g.
`hard_time_components_status_content_gated_scanned.py`) rather than
ruled-grid row-divider detection: row-divider detection (the technique
`hard_time_component_status_amp_interval_ruled_scanned.py` and
`hard_time_components_status_content_gated_scanned.py` both use) was
tried here first and DID NOT reproduce a usable row count when scanned
over a whole page's table height in one pass (confirmed directly: a grid
search across the full 9-column span, several (darkness, coverage-
fraction) combinations, found under half the true row count) -- this
template's own horizontal rules are apparently too faint/inconsistent
page-to-page-of-height for that global approach, even though the same
technique reproduces the correct row count when confined to a single
row's own narrow y-band (confirmed directly on several individual rows).
Rather than chase a per-row-band-only variant of that technique, this
module instead OCRs each of the 9 columns as ONE whole-column call (same
"more context per Tesseract call" reasoning as
`hard_time_components_status_content_gated_scanned.py`'s own docstring),
then reconstructs rows using the same PART NO.-column-as-row-anchor
technique `installed_rotables_since_delivery_scanned.py` already
validates for a sibling template in this package (see that module's own
docstring): the PART NO. column carries exactly one word on every real
content row -- a part number on an identity row, a requirement-type
keyword on a requirement row -- and nothing at all on the always-blank
LABEL row, so its own OCR'd word Y-positions directly give the Y-center
of every genuine row on the page with no separate row-divider detection
needed. Every other column's words are then assigned to whichever PART
NO.-anchor is vertically nearest (capped at `_ROW_GAP_PX`, comfortably
under this template's own real row pitch of ~40px at this module's DPI,
so a word is never pulled into the wrong row).

An earlier version of this module clustered words by sorting ALL
columns' words together by top and splitting wherever the gap to the
PREVIOUS WORD (of any column) exceeded a threshold. Confirmed directly
this silently merges two real, adjacent rows on a meaningful subset of
pages: a row's own words are not a single point but spread across most
of its own ~40px pitch (e.g. its own DUE AT/INTERVAL/TSR values sitting
30-40px below its own REQUIREMENT keyword), so the gap from that row's
OWN last word to the NEXT row's first word can end up smaller than the
gap threshold even though the two rows are genuinely distinct -- this
showed up as a requirement row's own REQUIREMENT-keyword cell silently
absorbing the following identity row's own PART NO. text into one merged
string (e.g. `"RESTORE 5A3307-7"`), corrupting the row-role
classification below. Anchoring on one column's own row-hits (each
occurring exactly once per row, not spread across the row) avoids this
entirely, which is exactly why `installed_rotables_since_delivery_scanned.py`
already established the same technique for its own sibling template. The
always-blank LABEL row is never explicitly detected or reconstructed at
all -- it simply contributes no PART NO.-column anchor (confirmed
directly: Tesseract does not recognize text against that row's own
near-black fill), so it disappears on its own rather than needing a
dedicated background-darkness classifier.

Row-role classification -- identity vs. requirement -- is a content-
plausibility check on the PART NO. column's OCR'd text for that row
(never a fixed row-index/parity assumption, which would silently break
the moment any one component's own requirement-row count differs from
another's, exactly the kind of assumption this package's own row-
detection modules warn against): every real part number sampled across
this file contains at least one digit (`182820-3`, `5A3307-7`,
`802300-14`, `DK120/90`, `1152890-1M419`, `453-5004(SERIAL)`, `A12SA`,
...), while every real requirement-type keyword sampled (`RESTORE`,
`DISCARD`, `REPLACEMENT`, `FUNCTIONAL CHECK`, `OPERATIONAL CHECK`,
`WEIGHT CHECK`, `DETAILED INSPECTION`, ...) is pure letters/spaces with
no digit at all -- so "does this row's own PART NO.-position cell
contain a digit" cleanly separates the two roles without needing a
closed vocabulary of every possible requirement-type keyword this
report might ever print. A row whose PART NO.-position cell is empty, or
whose text is a short/non-alphabetic fragment that matches neither shape
(most often a stray signature-block or footer artifact bleeding into the
column crop near the bottom of a page), is dropped rather than guessed
at -- the content-plausibility-gate convention used elsewhere in this
package.

A requirement row's identity fields (ATA/PART NO./SERIAL NO./
DESCRIPTION/POS./RELEASE NO. .../INST-DATE/TSN/CSN) are carried forward
from the most recently seen identity row (this module's own running
state during `extract()`, reset only at the start of a new file) --
never re-derived or guessed -- and joined onto that requirement's own
fields (REQUIREMENT/TASKCARD/DIM/DUE AT/INTERVAL/TSR/EXPECTED/TO GO) to
form one flattened record per requirement line. An identity row with no
requirement row ever following it (not observed anywhere in the sample
corpus -- every sampled component prints at least one requirement line)
would simply update the carried-forward state without ever itself
becoming a record; this is an accepted, deliberate trade-off given no
such case exists in the real file this module targets, not an oversight.

Sensitivity note: the sample file's own real registration/MSN/TAH/TAC/
date values are read at runtime as ordinary per-file data (same as this
project's other per-file header/body extraction elsewhere in this
package) but are NOT written into this module's source/comments anywhere
-- only the generic column-header/title phrases the template itself
prints (not document-specific) appear above.
"""
from __future__ import annotations
import re

import numpy as np

from sheet_types.ht_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_words, page_count

NAME = "Hard Time Components Status (Requirement-Grouped Rows, Scanned)"
SIGNATURES: list[str] = []  # no text layer at all -- see ocr_detect() below

_IDENTITY_COLS = ["ATA", "PART_NO", "SERIAL_NO", "DESCRIPTION", "POS",
                  "RELEASE_NO_LABEL_NO", "INST_DATE", "TSN", "CSN"]
_REQUIREMENT_COLS = ["REQUIREMENT", "TASKCARD", "DIM", "DUE_AT",
                      "INTERVAL", "TSR", "EXPECTED", "TO_GO"]
CANONICAL_COLUMNS = _IDENTITY_COLS + _REQUIREMENT_COLS

# A requirement row reuses the identity row's own 9 column x-positions,
# shifted one column right of ATA -- see module docstring for the
# pixel-cropped confirmation of this mapping.
_REQUIREMENT_SOURCE_COL = {
    "REQUIREMENT": "PART_NO",
    "TASKCARD": "SERIAL_NO",
    "DIM": "DESCRIPTION",
    "DUE_AT": "POS",
    "INTERVAL": "RELEASE_NO_LABEL_NO",
    "TSR": "INST_DATE",
    "EXPECTED": "TSN",
    "TO_GO": "CSN",
}

_OVERRIDES = {c: {"allow_empty": True} for c in CANONICAL_COLUMNS}
_OVERRIDES["ATA"] = {"pattern": r"^\d{2}$", "allow_empty": True}
RULES = merged_rules(_OVERRIDES)

_DPI = 300
# Real row pitch on the sample file is a stable ~40px at this DPI
# (confirmed directly, several pages) -- half that cleanly separates
# consecutive rows without ever splitting one row's own words apart.
_ROW_GAP_PX = 20
# A real requirement-type keyword is pure letters/spaces, no digit, and
# long enough not to be stray OCR noise (see module docstring).
_REQUIREMENT_TEXT_RE = re.compile(r"^[A-Za-z ]{4,}$")
_HAS_DIGIT_RE = re.compile(r"\d")

# ---------------------------------------------------------------------------
# Column x-position detection -- grid search over the header label band
# ("ATA | PART NO. | SERIAL NO. | ... | CSN"), expecting exactly 10
# dividers bracketing the 9 identity columns. Confirmed directly this
# reproduces the validated column set on every sampled page (small y-shift
# page to page, well within this search's own tolerance).
# ---------------------------------------------------------------------------
_COL_DARKS = (160, 180, 200, 220)
_COL_FRACS = (0.5, 0.6, 0.7)
_EXPECT_COL_DIVIDERS = len(_IDENTITY_COLS) + 1


def _find_col_lines(arr: np.ndarray, y0: int, y1: int, dark: int, thresh_frac: float,
                     merge_px: int = 5) -> list[int]:
    h, w = arr.shape
    if y1 <= y0:
        return []
    frac = (arr[y0:y1, :] < dark).mean(axis=0)
    xs = np.where(frac > thresh_frac)[0]
    groups: list[list[int]] = []
    for x in xs:
        if groups and x - groups[-1][-1] <= merge_px:
            groups[-1].append(x)
        else:
            groups.append([x])
    return [int(np.mean(g)) for g in groups]


def _plausible_col_lines(cl: list[int], page_width: int) -> bool:
    """Rejects a same-count-by-coincidence match against the wrong band --
    confirmed directly this happens both against the title/aircraft-
    identity box above the real header (that box has its own decorative
    rules and, on some pages, happens to also yield exactly 9 narrow
    columns there) and, separately, against a spurious match hugging the
    page's own left edge. A genuine header match's own left/right edges
    sit within a narrow, confirmed-directly range on every sampled page
    (~11-12% / ~88-89% of page width respectively) with every real column
    comfortably wide (this template's own narrowest real column, at
    ~155px, is confirmed directly across every sampled page)."""
    if not (page_width * 0.08 <= cl[0] <= page_width * 0.18):
        return False
    if not (page_width * 0.85 <= cl[-1] <= page_width * 0.92):
        return False
    gaps = [b - a for a, b in zip(cl[:-1], cl[1:])]
    return min(gaps) >= 100


def _find_col_lines_adaptive(arr: np.ndarray, y0: int, y1: int) -> list[int] | None:
    page_width = arr.shape[1]
    for dark in _COL_DARKS:
        for frac in _COL_FRACS:
            cl = _find_col_lines(arr, y0, y1, dark, frac)
            if len(cl) == _EXPECT_COL_DIVIDERS and _plausible_col_lines(cl, page_width):
                return cl
    return None


# OCR-text anchoring on the column-header LABEL words ("ATA"/"SERIAL"/
# "DESCRIPTION"/...) was tried first here and is NOT reliable enough to
# gate table-top detection on: confirmed directly this whole-band OCR
# pass recognizes those label words cleanly on some pages but returns
# near-total noise for them on others (page-to-page scan-quality
# variance), which would silently lose an entire page's worth of records
# rather than degrading gracefully. A pure pixel grid search for the
# header row's own 10 column dividers -- the same technique
# `_find_col_lines_adaptive` already uses for the column x-positions
# themselves -- needs no legible text at all and is confirmed directly to
# succeed on every page of the sample that has a table on it (the one
# page that legitimately has no table, a signature/near-blank page, is
# expected and correct to fail this and contribute no records).
_HEADER_BAND_HEIGHT = 40
_HEADER_SWEEP_STEP = 3
# A small gap this many steps wide (or more) between two successful
# sweep hits marks the end of the header's own contiguous match run --
# see `_find_header_band`'s docstring.
_HEADER_SWEEP_GAP = 2 * _HEADER_SWEEP_STEP
# Margin below the header band's own last confirmed match before the
# first real data row is trusted to start (confirmed directly this
# clears the header label text's own real height with room to spare).
_TABLE_TOP_MARGIN = 15


def _find_header_band(arr: np.ndarray, y_lo: int = 300, y_hi: int = 700) -> int | None:
    """Y-position of the LAST y0 in the header row's own contiguous
    column-line match run (see docstring below) -- i.e. a window starting
    here, `_HEADER_BAND_HEIGHT` tall, still lands on the header's own
    ruled dividers, and the header's own real bottom edge is just below
    it. Returns None if no table is present on this page at all.

    A single successful column-line match is not enough to anchor on by
    itself: confirmed directly the same 40px sweep window keeps matching
    the header's own 9-column divider count across a WIDE, contiguous run
    of y0 values (~70px on the sample file) as the window slides down
    while still overlapping the header's own ruled lines -- not just at
    one exact y0. Anchoring on the FIRST y0 in that run (this function's
    first version) sits too close to the header text's own real top edge
    and, on some pages, leaves the header label words' own (occasionally
    over-tall, see this module's git history) OCR bounding boxes still
    inside the very first data row's own column-crop, corrupting it.
    Anchoring on the LAST y0 of that same contiguous run instead -- the
    point where the sweep stops matching, i.e. the header's own real
    bottom edge -- confirmed directly clears the header text safely on
    every sampled page. A later, unrelated match run (confirmed directly:
    an ordinary DATA row can also happen to satisfy the same 9-column
    divider check, since every row shares this template's own column
    geometry) is never reached -- this function returns as soon as the
    FIRST contiguous run ends, rather than continuing to sweep further
    down the page."""
    run_start = None
    last_hit = None
    for y0 in range(y_lo, y_hi, _HEADER_SWEEP_STEP):
        hit = _find_col_lines_adaptive(arr, y0, y0 + _HEADER_BAND_HEIGHT) is not None
        if hit:
            if run_start is None:
                run_start = y0
            last_hit = y0
        elif run_start is not None and y0 - last_hit >= _HEADER_SWEEP_GAP:
            return last_hit
    return last_hit


async def _page_col_lines_and_top(img) -> tuple[list[int] | None, int | None]:
    arr = np.array(img.convert("L"))
    last_hit = _find_header_band(arr)
    if last_hit is None:
        return None, None
    col_lines = _find_col_lines_adaptive(arr, last_hit, last_hit + _HEADER_BAND_HEIGHT)
    if col_lines is None:
        return None, None
    table_top = last_hit + _HEADER_BAND_HEIGHT + _TABLE_TOP_MARGIN
    return col_lines, table_top


# ---------------------------------------------------------------------------
# Whole-column OCR + row clustering.
# ---------------------------------------------------------------------------

def _merge_words(words: list[tuple[float, float, str]]) -> str:
    """Space-joined, reading-order text -- sorted (top, left) so a row
    whose words Tesseract returned out of left-to-right order (confirmed
    directly this happens occasionally at psm 6 on a narrow column crop)
    still reassembles correctly."""
    return " ".join(t for _, _, t in sorted(words, key=lambda x: (x[0], x[1]))).strip()


async def _ocr_column(img, x0: int, x1: int, y0: int, y1: int) -> list[tuple[float, float, str]]:
    if x1 <= x0 or y1 <= y0:
        return []
    crop = img.crop((x0, y0, x1, y1))
    words = await ocr_words(crop, psm=6, min_conf=-1)
    out = []
    for w in words:
        text = str(w["text"]).strip()
        if not text:
            continue
        out.append((y0 + float(w["top"]), float(w.get("left", 0)), text))
    return out


def _cluster_anchor_words(words: list[tuple[float, float, str]]) -> list[tuple[float, str]]:
    """Groups the PART NO. column's own words into one row-anchor per real
    row -- a plain sequential top-gap split is safe HERE (unlike across
    all 9 columns at once, see module docstring) because this single
    column carries only one short value per row (never spread across the
    row's own ~40px pitch the way a full row's combined words are)."""
    ordered = sorted(words, key=lambda w: w[0])
    groups: list[list[tuple[float, float, str]]] = []
    for w in ordered:
        if groups and w[0] - groups[-1][-1][0] <= _ROW_GAP_PX:
            groups[-1].append(w)
        else:
            groups.append([w])
    return [(sum(w[0] for w in g) / len(g), _merge_words(g)) for g in groups]


async def _extract_page(img, page_index: int, identity_state: dict) -> list[dict]:
    col_lines, table_top = await _page_col_lines_and_top(img)
    if col_lines is None:
        return []
    h = img.height
    y_bottom = int(h * 0.97)  # keep clear of footer/signature-block artifacts
    if y_bottom <= table_top:
        return []

    col_bounds = list(zip(col_lines[:-1], col_lines[1:]))
    col_words: dict[str, list[tuple[float, float, str]]] = {}
    for name, (x0, x1) in zip(_IDENTITY_COLS, col_bounds):
        col_words[name] = await _ocr_column(img, x0, x1, table_top, y_bottom)

    anchors = _cluster_anchor_words(col_words["PART_NO"])
    if not anchors:
        return []
    anchor_tops = [a[0] for a in anchors]

    def nearest_anchor(top: float) -> int | None:
        best_i, best_d = None, None
        for i, at in enumerate(anchor_tops):
            d = abs(top - at)
            if best_d is None or d < best_d:
                best_i, best_d = i, d
        return best_i if best_d is not None and best_d <= _ROW_GAP_PX else None

    rows: list[dict[str, list[tuple[float, float, str]]]] = [
        {n: [] for n in _IDENTITY_COLS} for _ in anchors
    ]
    for name, words in col_words.items():
        for top, left, text in words:
            i = nearest_anchor(top)
            if i is not None:
                rows[i][name].append((top, left, text))

    records: list[dict] = []
    for by_col in rows:
        cell = {n: _merge_words(by_col[n]) for n in _IDENTITY_COLS}
        part_no_text = cell["PART_NO"]

        if _HAS_DIGIT_RE.search(part_no_text):
            # Identity row -- update carried-forward state, no record yet.
            identity_state.update(cell)
            identity_state["_page"] = page_index + 1
            continue

        if not _REQUIREMENT_TEXT_RE.match(part_no_text):
            # Neither a plausible part number nor a plausible requirement
            # keyword -- drop rather than guess (content-plausibility gate;
            # most often a stray footer/signature artifact).
            continue

        req = {name: cell[src] for name, src in _REQUIREMENT_SOURCE_COL.items()}
        if not any(req[f] for f in ("TASKCARD", "DUE_AT", "INTERVAL", "TSR", "EXPECTED", "TO_GO")):
            # A bare requirement-looking keyword with every other field
            # blank carries no real evidence of a genuine row -- drop it.
            continue
        if not identity_state.get("PART_NO"):
            # A requirement row with no identity row ever seen yet on this
            # file has nothing real to attach it to -- drop rather than
            # emit a record with fabricated/blank identity fields.
            continue

        rec = {k: identity_state.get(k, "") for k in _IDENTITY_COLS}
        rec.update(req)
        rec["_page"] = page_index + 1
        records.append(rec)

    return records


# ---------------------------------------------------------------------------
# Detection.
# ---------------------------------------------------------------------------
_TITLE_RE = re.compile(r"HT\s+COMPONENTS\s+STATUS\s+REPORT", re.IGNORECASE)
# Plain substring check (not a \b-bounded word regex) -- a whole-band OCR
# pass across every column at once (no per-column separation at detection
# time) reliably glues adjacent header cells together with no intervening
# space (confirmed directly, e.g. "RELEASE NO. / LABEL NO." and "INST-DATE"
# come back as one run like "RELEASENG,/WABELNG,~|NST:DATE" -- the "LABEL"
# neighbour is even too OCR-mangled itself, "L" misread as "W", to use as
# its own anchor), so only "RELEASE" (which does OCR cleanly here,
# confirmed directly) is required, on top of the title match above.
_COL_HEADER_SUBSTRINGS = ("RELEASE",)


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback (see
    sheet_types/ht.py) -- SIGNATURES is deliberately empty (no text layer
    at all, see module docstring). Requires both the bare title phrase
    AND this template's own distinctive "RELEASE ..." column-header
    fragment -- checked directly (grep) against every SIGNATURES/
    ocr_detect anchor in this package; no collision found."""
    try:
        img = await render_page(pdf_path, 0, dpi=_DPI)
        w, h = img.size
        title_crop = img.crop((0, 0, w, int(h * 0.16)))
        title_words = await ocr_words(title_crop, psm=6, min_conf=-1)
        title_text = " ".join(str(x["text"]) for x in title_words)
        if not _TITLE_RE.search(re.sub(r"\s+", " ", title_text)):
            return False
        header_crop = img.crop((0, int(h * 0.1), w, int(h * 0.22)))
        header_words = await ocr_words(header_crop, psm=6, min_conf=-1)
        header_text = "".join(str(x["text"]) for x in header_words).upper()
        return all(s in header_text for s in _COL_HEADER_SUBSTRINGS)
    except Exception:
        return False


async def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    identity_state: dict = {k: "" for k in _IDENTITY_COLS}
    n_pages = await page_count(pdf_path)
    for page_index in range(n_pages):
        img = await render_page(pdf_path, page_index, dpi=_DPI)
        records.extend(await _extract_page(img, page_index, identity_state))
    return records
