""""Time Controlled Component Status" -- scanned/OCR-only, task-block ruled
grid with variable-height, ZONE/POS sub-position rowspans.

Header (once per page)::

    Date as of : <date>                Issued from MPD <model family> Rev. <n> dated <date>
              TIME  CONTROLLED  COMPONENT  STATUS
                 <model>     MSN : <msn>
    AIRCRAFT TOTAL TIME : <n> FH     AIRCRAFT TOTAL CYCLES : <n> FC

    TASK ID | AI       | DESCRIPTION | ZONE | POS | LAST   | NEXT | P/N | S/N | REMARKS
    NUMBER  | INTERVAL |             |      |     | ACCOMP.| DUE  |     |     |

No extractable text layer at all on any page of the sample (confirmed
directly: `page.extract_text()` returns 0 characters on every page) --
`SIGNATURES` is deliberately empty, detection happens entirely through
`ocr_detect()`.

Structural shape (confirmed directly against a real, independently-counted
sample of this template's own pages): each ruled "row" in the printed table
is really a TASK, not a single physical table row. A task's own
TASK_ID_NUMBER/AI_INTERVAL/DESCRIPTION cells are drawn ONCE per task and can
visually span several physical sub-rows -- one task can cover several
ZONE/POS positions (e.g. one escape-slide task with four door positions,
each carrying its own LAST_ACCOMP/NEXT_DUE/P-N/S-N/REMARKS), and the task's
own TASK_ID_NUMBER text renders vertically CENTERED across the whole span
rather than pinned to its first sub-row. That centering is what makes a
naive "split halfway between two consecutive task-ID OCR boxes" boundary
unreliable: confirmed directly, it glues a following task's first
sub-position into the tail of a shorter preceding task's own record, purely
because the following task's own multi-position height pulls its OCR'd
center down past the true dividing rule.

This module never derives a task's own boundary from where its ID text
happens to sit. Instead:

1. `col_lines()` locates the 10 columns' 11 vertical rule x-positions from
   this template's own column-header row (a fixed, narrow relative-height
   band that reliably holds only that label row on every sampled page --
   confirmed directly, giving exactly 11 divider groups on every sampled
   page at one fixed (dark, coverage-fraction) cutoff).

2. `divider_candidates()` finds every real horizontal rule on the page --
   both task-boundary rules AND the finer ZONE/POS sub-position rules
   inside a single task's own span -- via a small (darkness, coverage-
   fraction) grid search restricted to the ZONE-through-REMARKS column
   span (`cl[3]:cl[-1]`), where EVERY row rule of either kind reaches
   close to full coverage. A page whose scan is generally lighter (this
   corpus's own real pages vary a lot in that regard -- some render every
   rule near-black, others render every rule closer to mid-gray) still
   gets its full divider set from this search, since the grid tries both
   several darkness cutoffs and several coverage-fraction cutoffs and
   keeps whichever combination surfaces the most candidates.

   `windowed_or_mean()` treats a pixel as "dark" if any pixel within a
   fixed vertical window at that x is dark, before averaging across x --
   plain per-row darkness (no window) badly undercounts a rule's own
   coverage on this file's own pages: confirmed directly, several sample
   pages render their ruled grid with a slight page skew, smearing a
   physically-horizontal rule across a handful of adjacent pixel rows
   rather than concentrating it on one, so a single fixed row's own raw
   darkness fraction can sit well under half even directly on top of a
   genuine full-width rule.

3. Each candidate divider is also scored by its OWN coverage across the
   TASK_ID_NUMBER/AI_INTERVAL/DESCRIPTION column span (`cl[0]:cl[3]`) --
   the columns that are only ever ruled at a genuine task boundary, never
   at a ZONE/POS sub-position divider (confirmed directly against this
   template's own real pages: a sub-position rule's own coverage across
   that left span never exceeds roughly a third, while a genuine task
   divider's coverage there is always well above that, even on a page
   whose task dividers otherwise render faintly overall).

4. `snap_boundary()` takes the naive midpoint between two consecutive
   task-ID OCR boxes' own centers (the same naive estimate that, used
   directly, produces the glued-record failure above) and snaps it to
   whichever nearby REAL divider from step 2 has the highest left-span
   score from step 3 -- not simply the closest candidate, and not a single
   fixed global score cutoff (confirmed directly neither is sufficient on
   its own: the closest candidate to a naive midpoint is sometimes a
   sub-position rule one row short of the true task boundary, and this
   file's own real task-boundary rules score anywhere from faint to
   fully solid depending on the page, so no one fixed cutoff cleanly
   separates "task boundary" from "sub-position divider" on every sampled
   page). Scoring picks the correct rule even when a weaker-but-genuine
   task boundary sits farther from the naive midpoint than a stronger
   sub-position rule does, and ties are broken toward the candidate
   closest to the naive midpoint.

Column cells are OCR'd as one crop per column per page (not per cell),
mirroring this package's other whole-column OCR variants (e.g.
`hard_time_components_status_content_gated_scanned.py`) -- each recognized
word is then assigned to whichever task's row-span contains the word's own
vertical center. A stacked multi-position cell (e.g. two Part Numbers
racked one above the other because a task covers two positions with no
further ZONE/POS split of their own) is preserved as newline-joined lines
in reading order rather than merged into one run-on string or arbitrarily
picked apart into separate fields -- this template offers no reliable way
to tell, from the ZONE/POS columns alone, which stacked P/N line pairs with
which stacked S/N line when a task's own ZONE/POS cell doesn't also split
into a matching number of sub-rows (confirmed directly: it sometimes
doesn't -- a task can show two stacked P/N-S/N pairs against a single,
unsplit POS value), so this module keeps that pairing implicit via shared
line order rather than guessing an explicit split.

Column x-positions and the header/footer band are freshly detected per
page (not hardcoded per page index): this file's own pages render at
slightly different pixel dimensions and left/top margins page to page
(confirmed directly), enough to shift the same template's column rules by
a double-digit pixel count from one page to the next.
"""
from __future__ import annotations
import re

import numpy as np

from sheet_types.ht_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, ocr_words, page_count

NAME = "Time Controlled Component Status (Task-Block Grid, Scanned)"
SIGNATURES: list[str] = []  # no extractable text layer -- see ocr_detect()

_COLUMN_ORDER = [
    "TASK_ID_NUMBER", "AI_INTERVAL", "DESCRIPTION", "ZONE", "POS",
    "LAST_ACCOMP", "NEXT_DUE", "PART_NUMBER", "SERIAL_NUMBER", "REMARKS",
]
_HEADER_FIELDS = [
    "MSN", "AIRCRAFT_MODEL", "REPORT_DATE",
    "AIRCRAFT_TOTAL_TIME", "AIRCRAFT_TOTAL_CYCLES",
]
CANONICAL_COLUMNS = _COLUMN_ORDER + _HEADER_FIELDS

_OVERRIDES = {c: {"allow_empty": True} for c in CANONICAL_COLUMNS}
# ZONE/PART_NUMBER/SERIAL_NUMBER inherit shared/aviation_rules.py's own
# pattern + OCR char-map/sequence-map rules (still allow_empty here, since
# many task blocks legitimately carry no ZONE, and a stacked multi-value
# cell -- see module docstring -- legitimately fails a single-value
# pattern and is meant to be flagged for a human to look at, not treated
# as clean). PART_NUMBER/SERIAL_NUMBER's own shared "no_spaces" rule is
# explicitly disabled here -- confirmed directly it collapses this
# module's own "\n" separator between two distinct stacked values into
# one run-on string with no separator at all (worse than the pattern
# mismatch flag it would otherwise get: a real, distinctly-separated
# multi-value cell would silently re-glue into exactly the kind of
# unbroken string this module's own OCR-side unglue step exists to avoid
# producing in the first place).
_OVERRIDES["PART_NUMBER"]["no_spaces"] = False
_OVERRIDES["SERIAL_NUMBER"]["no_spaces"] = False
RULES = merged_rules(_OVERRIDES)

_DPI = 300
_HEADER_BAND = (0.24, 0.278)   # relative page-height band holding ONLY the
                               # column-header labels (confirmed directly
                               # across every sampled page of this file)
_TABLE_TOP_FRAC = 0.283        # just below the column-header row's own
                               # bottom border
_INSET = 12                    # px inset from each column's ruled x-line,
                               # kept out of every column crop -- confirmed
                               # directly: including a column's own ruled
                               # divider line in its OCR crop corrupts
                               # psm-6 recognition of that whole column
_WIN = 40                      # vertical smear-tolerance window for
                               # windowed_or_mean() -- see module docstring
_DARKS = (150, 180, 200, 220, 240, 253)
_FRACS = (0.4, 0.5, 0.6, 0.75, 0.9)
_MIN_ROW_GAP = 60

_STOPWORDS = {"END OF STATUS", "END", "OF STATUS"}


def _col_lines(arr: np.ndarray, dark: int = 100, frac: float = 0.6, merge: int = 5) -> list[int]:
    h, w = arr.shape
    y0, y1 = int(h * _HEADER_BAND[0]), int(h * _HEADER_BAND[1])
    coverage = (arr[y0:y1, :] < dark).mean(axis=0)
    xs = np.where(coverage > frac)[0]
    groups: list[list[int]] = []
    for x in xs:
        if groups and x - groups[-1][-1] <= merge:
            groups[-1].append(x)
        else:
            groups.append([x])
    return [int(np.mean(g)) for g in groups]


def _windowed_or_mean(arr: np.ndarray, x0: int, x1: int, dark: int, win: int = _WIN) -> np.ndarray:
    sub = arr[:, x0:x1] < dark
    h, _ = sub.shape
    out = np.zeros_like(sub)
    half = win // 2
    for y in range(h):
        y0, y1 = max(0, y - half), min(h, y + half + 1)
        out[y] = sub[y0:y1].any(axis=0)
    return out.mean(axis=1)


def _peaks_from_cov(cov: np.ndarray, y_lo: int, y_hi: int, frac_thresh: float,
                     merge_px: int = 15) -> list[int]:
    ys = np.where(cov[y_lo:y_hi] > frac_thresh)[0] + y_lo
    groups: list[list[int]] = []
    for y in ys:
        if groups and y - groups[-1][-1] <= merge_px:
            groups[-1].append(y)
        else:
            groups.append([y])
    return [int(np.mean(g)) for g in groups]


def _table_bottom(arr: np.ndarray, cl: list[int], top: int) -> int:
    """Outer table border -- the last strong (near-full-coverage) rule on
    the page, searched for directly rather than assumed at a fixed
    fraction of page height (row count, and so table height, varies task
    block by task block and page by page)."""
    h, _ = arr.shape
    lx0, lx1 = cl[0], cl[3]
    best_last = None
    for dark in _DARKS:
        cov = _windowed_or_mean(arr, lx0, lx1, dark)
        peaks = _peaks_from_cov(cov, top + 150, int(h * 0.97), 0.75)
        if peaks:
            best_last = peaks[-1]
    return best_last if best_last is not None else int(h * 0.9)


_SKEW_REALIGN = 100  # px


def _divider_candidates(arr: np.ndarray, cl: list[int], top: int, bottom: int
                         ) -> list[tuple[int, float]]:
    """Every real row divider on the page (task-boundary AND ZONE/POS
    sub-position dividers alike), each scored by its own coverage across
    the "always task-boundary-only" left column span. See module
    docstring for both the detection grid and the scoring rationale.

    A candidate's own y (found from the ZONE-through-REMARKS span, far to
    the right of the page) is only an approximate x-position-independent
    match for where the SAME physical rule crosses the left span, far to
    the left -- confirmed directly this file's own pages carry enough
    skew that one continuous rule's y can drift a few dozen pixels
    between the two spans, well past what `_windowed_or_mean`'s own
    smear window alone bridges. Scoring the left span's own local MAXIMUM
    within a small neighbourhood of the candidate's right-detected y
    (rather than the left span's coverage at that exact y) re-aligns for
    that drift -- confirmed directly this is what correctly separates a
    genuine task boundary from a merely nearby sub-position divider on a
    page where the naive same-y scoring scored the wrong one higher."""
    rx0, rx1 = cl[3], cl[-1]
    lx0, lx1 = cl[0], cl[3]
    best_divs: list[int] = []
    best_dark = _DARKS[0]
    for dark in _DARKS:
        cov = _windowed_or_mean(arr, rx0, rx1, dark)
        for frac in _FRACS:
            peaks = _peaks_from_cov(cov, top + 150, bottom - 1, frac)
            if len(peaks) > len(best_divs):
                best_divs, best_dark = peaks, dark
    h, _ = arr.shape
    lcov = _windowed_or_mean(arr, lx0, lx1, best_dark)
    out = []
    for y in best_divs:
        y0, y1 = max(0, y - _SKEW_REALIGN), min(h, y + _SKEW_REALIGN)
        out.append((y, float(lcov[y0:y1].max())))
    return out


def _snap_boundary(center_i: float, center_ip1: float, candidates: list[tuple[int, float]],
                    after: int) -> int:
    """The true boundary between task i and task i+1 always lies between
    the two tasks' own TASK_ID_NUMBER OCR centers -- each task's own ID
    text center sits somewhere within that task's own span (however far
    off-center a tall multi-position span pulls it), so the boundary
    (task i's own span end / task i+1's own span start) can never fall
    before task i's own center or after task i+1's own center. Searching
    only within [center_i, center_ip1] (never a fixed-radius window
    around the naive midpoint) is what keeps a strong-but-WRONG-context
    divider outside this gap entirely out of contention -- confirmed
    directly: a fixed +-450px window let a page whose real block pitch
    here runs closer to 200-300px reach clean past the correct (but
    weaker-scoring) divider for this specific gap and grab a stronger
    divider that actually belongs to a neighbouring gap instead.

    `after` (the previous, already-placed boundary) is a second, hard
    floor: two consecutive task boundaries snapping to the SAME real
    divider (also confirmed directly, on a page whose divider set near
    one naive midpoint is sparse) would squeeze the task between them
    down to nothing -- corrupting it further downstream, since a too-
    short column crop is what made Tesseract itself run separate stacked
    values together with no separator on a real sample page."""
    lo, hi = max(int(center_i), after), int(center_ip1)
    near = [(y, c) for (y, c) in candidates if lo <= y <= hi]
    if not near:
        return max(int((center_i + center_ip1) / 2), after + _MIN_ROW_GAP)
    best_score = max(c for _, c in near)
    tied = [(y, c) for (y, c) in near if c >= best_score - 0.05]
    naive = (center_i + center_ip1) / 2
    return min(tied, key=lambda t: abs(t[0] - naive))[0]


def _line_clusters(words: list[dict], gap: int = 22) -> list[tuple[float, float, str]]:
    ws = sorted(words, key=lambda w: w["top"])
    clusters: list[list[dict]] = []
    for w in ws:
        if clusters and w["top"] - clusters[-1][-1]["top"] <= gap:
            clusters[-1].append(w)
        else:
            clusters.append([w])
    out = []
    for c in clusters:
        top = min(x["top"] for x in c)
        bot = max(x["top"] + x["height"] for x in c)
        text = " ".join(x["text"] for x in sorted(c, key=lambda x: x["left"])).strip()
        out.append((top, bot, text))
    return out


def _unglue_exact_repeat(text: str) -> str:
    """A stacked cell whose two (or more) sub-position values happen to be
    IDENTICAL (e.g. the same Part Number reused across two positions of
    the same task -- confirmed a real, legitimate case on this file's own
    pages) sometimes gets read by Tesseract as a single fused token with
    no separating space or newline at all, since a whole-column OCR pass
    has no per-row crop boundary to force a break there (confirmed
    directly: e.g. a real "30900000M" appearing twice in one column,
    genuinely stacked one above the other, came back as one unbroken
    "30900000M30900000M" run). Only collapses an EXACT, whole-string
    self-repeat (`s+s` for some non-empty `s`) back into two separated
    lines -- this reconstructs a real, verified duplicate rather than
    guessing a split point in any other (non-repeating) glued string."""
    t = text.strip()
    n = len(t)
    if n < 8 or n % 2:
        return text
    half = n // 2
    if t[:half] == t[half:]:
        return t[:half] + "\n" + t[half:]
    return text


_ID_DIGIT_RE = re.compile(r"\d")


def _plausible_id(text: str) -> bool:
    """A real TASK ID NUMBER on this template is a hyphen-joined,
    digit-bearing code (e.g. "262141-02-1", "4922100-B1-1") -- long enough,
    with at least one digit and one hyphen. Screens out stray marks/rule
    fragments the ID-column OCR pass occasionally turns into a short
    "word" (confirmed directly against this file's own real pages)
    without ever depending on a specific digit count or prefix shape,
    since real IDs here vary in both across tasks."""
    t = text.strip()
    if len(t.replace(" ", "")) < 5:
        return False
    if "-" not in t:
        return False
    return bool(_ID_DIGIT_RE.search(t))


def _drop_stopwords(lines: list[str]) -> list[str]:
    """This template's own fixed "END OF STATUS" footer box sits close
    enough below the last task block's own bottom rule that it can enter
    the last block's own column crops on the last page -- confirmed
    directly. Dropped by exact (case-insensitive) phrase match only,
    never a partial/fuzzy match, so it can never remove real content."""
    return [ln for ln in lines if ln.strip().upper() not in _STOPWORDS]


_MSN_RE = re.compile(r"MSN\s*:?\s*([0-9A-Z\-]+)", re.I)
_MODEL_RE = re.compile(r"([A-Z0-9\-]{5,12})\s+MSN\s*:", re.I)
_DATE_RE = re.compile(r"Date\s+as\s+of\s*:?\s*([0-9A-Za-z\-]+)", re.I)
_TOTAL_TIME_RE = re.compile(r"TOTAL\s+TIME\s*:?\s*([\d.]+\s*FH)", re.I)
_TOTAL_CYCLES_RE = re.compile(r"TOTAL\s+CYCLES\s*:?\s*(\d+\s*FC)", re.I)


async def _parse_header(img) -> dict:
    meta = {k: "" for k in _HEADER_FIELDS}
    w, h = img.size
    # The left ~1/3 of the header band carries only a wordmark/logo that
    # otherwise garbles psm-6 recognition of the real header text sharing
    # its row -- confirmed directly cropping it out cleans up the read.
    crop = img.crop((int(w * 0.35), 0, w, int(h * _HEADER_BAND[1])))
    text = await ocr_text(crop, psm=6)
    for key, rx in (
        ("MSN", _MSN_RE), ("AIRCRAFT_MODEL", _MODEL_RE), ("REPORT_DATE", _DATE_RE),
        ("AIRCRAFT_TOTAL_TIME", _TOTAL_TIME_RE), ("AIRCRAFT_TOTAL_CYCLES", _TOTAL_CYCLES_RE),
    ):
        m = rx.search(text)
        if m:
            meta[key] = m.group(1).strip()
    return meta


async def _extract_page(img, page_index: int) -> list[dict]:
    arr = np.array(img.convert("L"))
    h, _ = arr.shape
    cl = _col_lines(arr)
    if len(cl) != 11:
        return []
    top = int(h * _TABLE_TOP_FRAC)
    bottom = _table_bottom(arr, cl, top)
    if bottom <= top:
        return []

    id_words_raw = await ocr_words(img.crop((cl[0] + _INSET, top, cl[1] - _INSET, bottom)),
                                    psm=6, min_conf=-1)
    id_words = [{"text": str(w["text"]), "top": top + float(w["top"]),
                 "height": float(w["height"]), "left": float(w["left"])}
                for w in id_words_raw]
    clusters = _line_clusters(id_words)
    anchors = [(t, b, txt) for (t, b, txt) in clusters if _plausible_id(txt)]
    if not anchors:
        return []

    centers = [(t + b) / 2 for (t, b, _) in anchors]
    candidates = _divider_candidates(arr, cl, top, bottom)
    bounds = [top]
    for i in range(len(centers) - 1):
        bounds.append(_snap_boundary(centers[i], centers[i + 1], candidates, after=bounds[-1]))
    bounds.append(max(bottom, bounds[-1] + _MIN_ROW_GAP))
    # Guard against a degenerate (near-zero-height) span from a snap that
    # landed on (or before) the previous boundary -- keeps records ordered
    # and non-overlapping even on a page whose divider detection under-
    # performs.
    fixed = [bounds[0]]
    for y in bounds[1:]:
        fixed.append(y if y - fixed[-1] >= _MIN_ROW_GAP else fixed[-1] + _MIN_ROW_GAP)
    bounds = fixed

    col_words: dict[str, list[dict]] = {}
    for name, x0, x1 in zip(_COLUMN_ORDER[1:], cl[1:-1], cl[2:]):
        ws_raw = await ocr_words(img.crop((x0 + _INSET, top, x1 - _INSET, bottom)),
                                  psm=6, min_conf=-1)
        col_words[name] = [{"text": str(w["text"]), "top": top + float(w["top"]),
                             "height": float(w["height"]), "left": float(w["left"])}
                            for w in ws_raw]

    span_ids: dict[int, list[str]] = {}
    for i, (t, b, txt) in enumerate(anchors):
        c = (t + b) / 2
        idx = len(bounds) - 2
        for j in range(len(bounds) - 1):
            if bounds[j] <= c < bounds[j + 1]:
                idx = j
                break
        span_ids.setdefault(idx, []).append(txt)

    records = []
    for idx in sorted(span_ids):
        y0, y1 = bounds[idx], bounds[idx + 1]
        rec = {"TASK_ID_NUMBER": "\n".join(_drop_stopwords(span_ids[idx])), "_page": page_index + 1}
        for name in _COLUMN_ORDER[1:]:
            ws = [w for w in col_words[name] if y0 <= (w["top"] + w["height"] / 2) < y1]
            lines = [_unglue_exact_repeat(txt) for (_, _, txt) in _line_clusters(ws) if txt]
            rec[name] = "\n".join(_drop_stopwords(lines))
        _fold_not_applicable(rec)
        records.append(rec)
    return records


_NOT_APPLICABLE_COLS = ("LAST_ACCOMP", "NEXT_DUE", "PART_NUMBER", "SERIAL_NUMBER")
_NOT_APPLICABLE_RE = re.compile(r"NOT\s+AP", re.I)


def _fold_not_applicable(rec: dict) -> None:
    """This template merges LAST_ACCOMP/NEXT_DUE/PART_NUMBER/SERIAL_NUMBER
    into ONE wide "NOT APPLICABLE" cell (plus a generic explanatory line,
    e.g. an airframe-model/configuration note) whenever a task doesn't
    apply to this aircraft's own configuration -- confirmed directly
    against this file's own real pages. Column-cropped OCR still splits
    that single wide cell
    at each column's own x-line regardless, so each of the 4 columns'
    "own" text is really just an arbitrary fragment of the same merged
    sentence -- e.g. a PART_NUMBER fragment that happens to read as a
    plausible-shaped code purely by accident of where the crop line fell
    (confirmed directly: this let a real garbled fragment PASS this
    module's own PART_NUMBER pattern check unflagged before this fix).
    Detected whenever any of the 4 columns' own OCR text contains "NOT
    APPL..." (tolerant of a trailing "ICABLE" OCR misread): the merged
    sentence is reassembled (its fragments recombined in column order,
    since that is also left-to-right reading order for this merged cell)
    into NEXT_DUE alone, and the other 3 columns -- which never carry
    independent content of their own on a row like this -- are cleared
    rather than left holding a meaningless split fragment each."""
    combined = " ".join(rec[c] for c in _NOT_APPLICABLE_COLS if rec[c]).strip()
    if not _NOT_APPLICABLE_RE.search(combined):
        return
    rec["LAST_ACCOMP"] = ""
    rec["NEXT_DUE"] = combined
    rec["PART_NUMBER"] = ""
    rec["SERIAL_NUMBER"] = ""


_TITLE_RE = re.compile(r"TIME\s+CONTROLLED\s+COMPONENT\s+STATUS", re.I)
# Just "TASK" + "ID" (from the "TASK ID NUMBER" column header) -- a plain
# psm-6 read of the FULL header row (all 10 columns at once) reliably
# recognizes these two leftmost words but garbles or drops the further-
# right column labels entirely (confirmed directly: a real sample read of
# this exact band came back "TASK ID Al LAST NEXT ." -- no "ZONE"/"POS"/
# "DESCRIPTION" survived that joint multi-column read at all, even though
# per-column cropped OCR reads every one of them cleanly elsewhere in this
# module). Checked directly (grep) against every SIGNATURES list and
# ocr_detect anchor in occm.py/ht.py/llp.py and every occm_variants/
# ht_variants/llp_variants module -- combined with the title check above,
# no collision found.
_COLHDR_WORDS_RE = [re.compile(r"\bTASK\b", re.I), re.compile(r"\bID\b", re.I)]


async def ocr_detect(pdf_path: str) -> bool:
    """Page-1 title + column-header check for the router's blank-text
    fallback (see sheet_types/ht.py) -- SIGNATURES is deliberately empty
    (see module docstring). "TIME CONTROLLED COMPONENT STATUS" (singular
    COMPONENT) is this template's own bare title line, verbatim; checked
    directly (grep) against every SIGNATURES list in occm.py/ht.py/llp.py
    and every occm_variants/ht_variants/llp_variants module's own
    SIGNATURES/ocr_detect anchor text -- no collision found (the closest
    look-alike, time_controlled_components_status.py's own "TIME
    CONTROLLED COMPONENTS STATUS", uses the plural COMPONENTS)."""
    try:
        img = await render_page(pdf_path, 0, dpi=_DPI)
        w, h = img.size
        title_crop = img.crop((0, 0, w, int(h * 0.20)))
        title_text = await ocr_text(title_crop, psm=6)
        if not _TITLE_RE.search(re.sub(r"\s+", " ", title_text)):
            return False
        arr = np.array(img.convert("L"))
        cl = _col_lines(arr)
        if len(cl) != 11:
            return False
        y0, y1 = int(h * _HEADER_BAND[0]), int(h * _HEADER_BAND[1] + 0.02 * h)
        header_text = await ocr_text(img.crop((0, y0, w, y1)), psm=6)
        return all(rx.search(header_text) for rx in _COLHDR_WORDS_RE)
    except Exception:
        return False


async def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    n_pages = await page_count(pdf_path)
    header_meta = {k: "" for k in _HEADER_FIELDS}
    for page_index in range(n_pages):
        img = await render_page(pdf_path, page_index, dpi=_DPI)
        if not all(header_meta.values()):
            page_meta = await _parse_header(img)
            for k, v in page_meta.items():
                if v and not header_meta[k]:
                    header_meta[k] = v
        page_records = await _extract_page(img, page_index)
        for rec in page_records:
            rec.update(header_meta)
        records.extend(page_records)
    return records
