"""AMASIS "Report KARDEX by Aircraft" -- OCR required despite a non-blank
pdfplumber text layer, because that text layer is unusable.

Confirmed directly on the real known source file: every page's
`extract_text()` returns thousands of non-blank characters, but the
recovered string is almost entirely pdfplumber's own "(cid:<n>)" placeholder
token -- the literal text pdfplumber emits for a glyph it cannot map through
the embedded font's (missing/broken) ToUnicode table. PyMuPDF's own
`get_text()` was checked directly against the same page too: it returns raw
control-byte garbage instead (no readable characters at all), confirming
this is a genuinely broken font encoding in the source file, not a
pdfplumber-specific quirk. Rendering the page to an image and reading it
visually, however, shows a clean, sharp, perfectly ordinary vector-text
table -- the PDF's rendering path (font glyph outlines) still works fine,
only the text-extraction path (character-code-to-Unicode mapping) is
broken. So this module is OCR-only end to end, same as this package's other
scanned variants, even though `pdfplumber.Page.extract_text()` never
returns an empty string for it -- see `sheet_types/occm.py`'s
`_is_cid_garbled()` for the router-level detection of this specific
failure mode (the existing "blank text" OCR-fallback checks alone do not
catch it, since the recovered text is never blank).

Header block (repeats identically on every page, confirmed directly)::

    AMASIS                    Report KARDEX by Aircraft          Page <n> sur <n>
    A/C : <reg>      Effectivity : <type>      Protocol : <protocol>
    A/B : <n>        B/B : <n>                 Cycle : <n>

    Position          Description
      Structure ID    AMM              F.I.N.  Zone  Maint. ETOPS Protocol  Phasing  Tolerance
                                                       level        Type
                       P/N description  P/N             S/N
                       Inspection BI    Other Inspection BI2   Overhaul BO   Life Limit MAX

Footer (repeats identically on every page): "<date>" / "<time>".

Body -- one record is a small block of table rows sharing one horizontal
rule above and below it. Confirmed directly across the whole real sample
file (front, several middle, and the last page), two record shapes occur:

    1. A genuine installed/trackable component (the common case), six
       printed lines:
           line 1: POSITION  DESCRIPTION
           line 2: [STRUCTURE_ID]  AMM  FIN  ZONE  [MAINT_LEVEL/ETOPS]
                    PROTOCOL_TYPE  [PHASING]  [TOLERANCE]
           line 3: PN_DESCRIPTION  PART_NUMBER  SERIAL_NUMBER
           line 4: "FH"    <Inspection BI> <Other Inspection BI2>
                           <Overhaul BO> <Life Limit MAX>
           line 5: "CY"    (same 4 sub-columns)
           line 6: "Month" (same 4 sub-columns)

    2. An ATA-subsystem heading row with no installed part at all (e.g. the
       real sample file's own "AIR CONDITIONING DISTRIBUTION" row), five
       printed lines -- line 3 (PN_DESCRIPTION/PART_NUMBER/SERIAL_NUMBER) is
       simply absent, and line 2 carries only a MAINT_LEVEL/ETOPS value and
       PROTOCOL_TYPE (AMM/FIN/ZONE blank):
           line 1: POSITION  DESCRIPTION
           line 2: [MAINT_LEVEL/ETOPS]  PROTOCOL_TYPE
           line 4-6: FH / CY / Month, as above

STRUCTURE_ID (confirmed directly on the real sample file's very last page,
the only real occurrence checked): when present, it prints on the SAME
physical line as the AMM/FIN/ZONE row (line 2), not its own line -- just
indented into the "Position" column's own sub-label position (~x=200 at
this module's own 300 DPI, vs. ~x=108 for the real POSITION value on line
1). Because of this, no separate "structure ID row" detection is needed or
implemented -- it is read straight off line 2's own left-hand strip,
exactly like every other line-2 field below.

MAINT_LEVEL vs. ETOPS -- confirmed directly NOT split into two separate
output columns, on purpose. Across every real occurrence checked (753
component/heading line-2 rows sampled across the whole real file, every
third page), the ETOPS field is blank on 100% of them -- the only value
ever seen in that stretch of line 2 is the single-character MAINT_LEVEL
value (almost always "N"), landing at an x-position (~1569 at 300 DPI)
noticeably closer to this report's own "ETOPS" column-header label
(~x=1568) than to its "Maint. level" column-header label (~x=1473),
because values render right-justified within their own cell while headers
render left-justified -- so a fixed x-boundary derived from the header
labels alone would misattribute that lone value to the wrong column on
every single row. No real occurrence of a second, distinct token anywhere
in this combined zone was found in that same sample (checked directly --
see the description above; the handful of x-range hits found there were
confirmed to be SERIAL_NUMBER values from an adjacent line-3 row bleeding
into the same coarse x-window, not real second line-2 values). Per this
project's "never guess a wrong split" convention, MAINT_LEVEL and ETOPS are
therefore read together into one MAINT_LEVEL_ETOPS field rather than risk
silently attributing a real value to the wrong one of the two.

Column x-boundaries below are pixel positions at this module's own fixed
300 DPI render (`render_page(..., dpi=300)` is always used, never a
different DPI, specifically so these fixed boundaries stay valid across
every page and every call site) -- derived directly from this report's own
column-header word positions (confirmed stable across the front, several
middle, and the last page of the real sample file) plus a safety margin,
not guessed or taken from a different report's layout.
"""
from __future__ import annotations
import re

from PIL import Image

from sheet_types.occm_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, ocr_words, page_count

NAME = "Aircraft KARDEX Status (AMASIS, Broken Font, Scanned)"

# This module's known source file DOES carry a non-blank pdfplumber text
# layer, but it is unusable "(cid:<n>)" placeholder noise throughout (see
# module docstring) -- so a normal SIGNATURES substring match against that
# recovered text can never reliably fire either way (it would either never
# match, or coincidentally garble-match something unrelated). Deliberately
# left empty, like this package's other purely-OCR variants; real detection
# happens via `ocr_detect()` below, reached through `sheet_types/occm.py`'s
# own `_is_cid_garbled()` fallback trigger (see that module for why the
# existing blank-text checks alone don't catch this file).
SIGNATURES = []

CANONICAL_COLUMNS = [
    "POSITION",
    "STRUCTURE_ID",
    "DESCRIPTION",
    "AMM",
    "FIN",
    "ZONE",
    "MAINT_LEVEL_ETOPS",
    "PROTOCOL_TYPE",
    "PHASING",
    "TOLERANCE",
    "PN_DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "FH_INSPECTION_BI",
    "FH_OTHER_INSPECTION_BI2",
    "FH_OVERHAUL_BO",
    "FH_LIFE_LIMIT_MAX",
    "CY_INSPECTION_BI",
    "CY_OTHER_INSPECTION_BI2",
    "CY_OVERHAUL_BO",
    "CY_LIFE_LIMIT_MAX",
    "MONTH_INSPECTION_BI",
    "MONTH_OTHER_INSPECTION_BI2",
    "MONTH_OVERHAUL_BO",
    "MONTH_LIFE_LIMIT_MAX",
    # Soft-validation catch-all: a line-2/line-3-shaped row this module's
    # own two-slots-per-record assumption (see module docstring) could not
    # place -- empty on every row of the real sample file, since every real
    # record checked fit cleanly into at most one line-2 + one line-3 row.
    "EXTRA_TEXT",
    # Header metadata -- parsed once (first data page) and stamped on every
    # row, same convention as this package's other header-plus-body OCCM
    # variants.
    "AIRCRAFT_REG",
    "EFFECTIVITY",
    "PROTOCOL",
    "CYCLE",
    "REPORT_DATE",
]

# Status-matrix cells (FH/CY/Month x 4 sub-columns) hold "O/C" on every real
# row checked, but the report's own column headers ("Inspection", "Overhaul",
# "Life Limit") describe genuine hour/cycle/date-limit fields too -- a
# number or a date is accepted here as well, never flagged just for not
# being "O/C" specifically. OCR misreads of the slash (e.g. "orc"/"Oc"/
# "o/c") are normalized to "O/C" at extraction time (see `_norm_oc()`)
# before this pattern is even checked, so this pattern only needs to accept
# the clean form plus numbers/dates.
_STATUS_CELL_RULE = {
    "pattern": r"^(?:O/C|\d+(?:\.\d+)?|\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})$",
    "allow_empty": True,
}

_OVERRIDES = {
    "POSITION": {"pattern": r"^\d{5,9}$"},
    "STRUCTURE_ID": {"pattern": r"^[A-Z0-9]{3,10}$", "allow_empty": True},
    # AMM references print as "<ata>-<subj>-<seq>-<var>" (e.g.
    # "21-21-54-401"), confirmed uniform in shape across the real sample
    # file wherever present; blank on the real sample's own heading rows
    # (see module docstring).
    "AMM": {"pattern": r"^\d{2}-\d{2}-\d{2}-\d{3}$", "allow_empty": True},
    "FIN": {"allow_empty": True},
    "ZONE": {"allow_empty": True},
    # See module docstring for why MAINT_LEVEL and ETOPS are read as one
    # combined field rather than force-split.
    "MAINT_LEVEL_ETOPS": {
        "pattern": r"^[A-Z0-9 /]{1,10}$",
        "uppercase": True,
        "allow_empty": True,
    },
    "PROTOCOL_TYPE": {
        "pattern": r"^O/C$",
        "uppercase": True,
        "allow_empty": True,
    },
    # Never populated on the real sample file checked, but the report's own
    # column headers are real ("Phasing", "Tolerance") -- no pattern is
    # asserted since no real value has ever been seen to derive one from.
    "PHASING": {"allow_empty": True},
    "TOLERANCE": {"allow_empty": True},
    "PN_DESCRIPTION": {"uppercase": True, "allow_empty": True},
    "PART_NUMBER": {"allow_empty": True},
    "SERIAL_NUMBER": {"allow_empty": True},
    "FH_INSPECTION_BI": _STATUS_CELL_RULE,
    "FH_OTHER_INSPECTION_BI2": _STATUS_CELL_RULE,
    "FH_OVERHAUL_BO": _STATUS_CELL_RULE,
    "FH_LIFE_LIMIT_MAX": _STATUS_CELL_RULE,
    "CY_INSPECTION_BI": _STATUS_CELL_RULE,
    "CY_OTHER_INSPECTION_BI2": _STATUS_CELL_RULE,
    "CY_OVERHAUL_BO": _STATUS_CELL_RULE,
    "CY_LIFE_LIMIT_MAX": _STATUS_CELL_RULE,
    "MONTH_INSPECTION_BI": _STATUS_CELL_RULE,
    "MONTH_OTHER_INSPECTION_BI2": _STATUS_CELL_RULE,
    "MONTH_OVERHAUL_BO": _STATUS_CELL_RULE,
    "MONTH_LIFE_LIMIT_MAX": _STATUS_CELL_RULE,
    "EXTRA_TEXT": {"allow_empty": True},
    "AIRCRAFT_REG": {"uppercase": True, "allow_empty": True},
    "EFFECTIVITY": {"uppercase": True, "allow_empty": True},
    "PROTOCOL": {"uppercase": True, "allow_empty": True},
    "CYCLE": {"allow_empty": True},
    "REPORT_DATE": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# --- Geometry (300 DPI, derived from this report's own column headers) ----
_BODY_TOP_MIN = 500
_BODY_TOP_MAX = 3460
# Words on the same printed row were confirmed directly to differ in `top`
# by up to ~12px in the common case (font-rendering/baseline jitter), but
# a real outlier was also confirmed directly: one status-matrix value cell
# (a low-confidence OCR read) landed 24px from its own row's "Month"
# label -- well past a tolerance that would still safely separate two
# real DIFFERENT rows (confirmed directly: the closest real gap between
# two different rows, CY to Month, can be as little as ~30px, so a single
# tolerance wide enough to always catch a 24px outlier in one pass would
# risk merging genuinely different rows elsewhere). 14 catches the common
# case; `_merge_orphan_rows()` below catches the rest with a narrower,
# content-shape-restricted rule instead of just widening this tolerance.
_ROW_CLUSTER_TOL = 14
# Merge cap for `_merge_orphan_rows()` -- generous enough to catch the
# confirmed 24px real outlier above with margin, only ever applied to a
# row already confirmed content-only (see that function).
_ORPHAN_MERGE_MAX_DIST = 35

_X_POSITION_MAX = 150       # real POSITION values render here (~108)
_X_LEFT_MAX = 480           # DESCRIPTION / AMM / PN_DESCRIPTION column start
_X_FIN_MAX = 950
_X_ZONE_MAX = 1300
_X_ZONE_END = 1460
_X_MAINT_ETOPS_END = 1750
_X_PROTOCOL_END = 2000
_X_PHASING_END = 2160

_X_PN_DESC_MAX = 480
_X_PART_NUMBER_END = 1500

_X_STATUS_1_MAX = 950
_X_STATUS_1_END = 1300
_X_STATUS_2_END = 1700
_X_STATUS_3_END = 2050

_ANCHOR_RE = re.compile(r"^\d{5,9}$")
_FH_RE = re.compile(r"^FH$", re.I)
_CY_RE = re.compile(r"^C[YV]$", re.I)   # "CY" -- "V" covers a confirmed misread
_MONTH_RE = re.compile(r"^MONTH$", re.I)
_OC_RE = re.compile(r"^O[/RLI.,]?C$", re.I)


def _norm_oc(text: str) -> str:
    """Normalize OCR misreads of "O/C" (e.g. "orc", "Oc", "o/c") to the
    canonical form -- confirmed directly, the slash is the one character
    Tesseract sometimes drops or misreads as a similar-shaped letter at
    this column's small font size; the surrounding "O"/"C" were confirmed
    to always read correctly on the real sample file."""
    t = text.strip().replace(" ", "")
    if _OC_RE.match(t):
        return "O/C"
    return text.strip()


def _merge_orphan_rows(rows: list[list[dict]]) -> list[list[dict]]:
    """A row is only ever "content-only" (every word at x>=950, the first
    real status-matrix sub-column -- see module docstring) when it is the
    tail end of a genuine FH/CY/Month row whose own label word (and
    possibly its earlier value cells) landed in the PREVIOUS cluster due
    to baseline jitter beyond `_ROW_CLUSTER_TOL` (confirmed directly --
    see that constant's own comment). A genuine label/anchor row, an AMM
    row, or a PN-description row always has a word further left than
    that. So any content-only row is merged into whichever OTHER row's
    own top is nearest (by absolute distance, capped at
    `_ORPHAN_MERGE_MAX_DIST`) rather than kept as its own (mis-shaped)
    row -- `.extend()` mutates the target row's own list in place, so this
    is safe regardless of whether the target has already been emitted
    into the caller's output list."""
    is_orphan = [all(w["left"] >= _X_FIN_MAX for w in r) for r in rows]
    tops = [min(w["top"] for w in r) for r in rows]
    for i, orphan in enumerate(is_orphan):
        if not orphan:
            continue
        best_j, best_d = None, float("inf")
        for j in range(len(rows)):
            if j == i or is_orphan[j]:
                continue
            d = abs(tops[i] - tops[j])
            if d < best_d:
                best_j, best_d = j, d
        if best_j is not None and best_d <= _ORPHAN_MERGE_MAX_DIST:
            rows[best_j].extend(rows[i])
            rows[i] = []
    return [r for r in rows if r]


_NOISE_TOKEN_RE = re.compile(r"^[-_~=|.,`'\"*]+$")


def _cluster_rows(words: list[dict]) -> list[list[dict]]:
    body = [w for w in words if _BODY_TOP_MIN < w["top"] < _BODY_TOP_MAX]
    # Drop punctuation-only tokens before clustering -- confirmed directly
    # on a real occurrence (a bare "-" OCR'd from a stray rule/border
    # remnant, landing on its own row between the POSITION/DESCRIPTION
    # anchor and the real AMM row): left in, a token like this forms its
    # own spurious row and shifts every later row-2/row-3 assignment in
    # `_assemble_record()` off by one for that whole record. No real
    # AMM/PN_DESCRIPTION/PART_NUMBER/SERIAL_NUMBER cell is ever legitimately
    # punctuation-only on this report (a genuinely absent value is simply
    # blank -- confirmed directly, e.g. the real sample file's own heading
    # rows never print a placeholder dash for a blank AMM), so this is safe
    # to drop outright rather than risk it derailing row assignment.
    body = [w for w in body if not _NOISE_TOKEN_RE.match(w["text"].strip())]
    body.sort(key=lambda w: (w["top"], w["left"]))
    rows: list[list[dict]] = []
    cur: list[dict] = []
    cur_top: float | None = None
    for w in body:
        if cur_top is None or abs(w["top"] - cur_top) <= _ROW_CLUSTER_TOL:
            cur.append(w)
            cur_top = w["top"] if cur_top is None else cur_top
        else:
            rows.append(cur)
            cur = [w]
            cur_top = w["top"]
    if cur:
        rows.append(cur)
    return _merge_orphan_rows(rows)


def _row_label(row: list[dict]) -> str | None:
    row_sorted = sorted(row, key=lambda w: w["left"])
    first = row_sorted[0]
    if first["left"] >= _X_POSITION_MAX:
        return None
    text = first["text"].strip()
    if _FH_RE.match(text):
        return "FH"
    if _CY_RE.match(text):
        return "CY"
    if _MONTH_RE.match(text):
        return "MONTH"
    return None


def _is_anchor(row: list[dict]) -> bool:
    row_sorted = sorted(row, key=lambda w: w["left"])
    first = row_sorted[0]
    if first["left"] >= _X_POSITION_MAX:
        return False
    if not _ANCHOR_RE.match(first["text"].strip()):
        return False
    # A genuine anchor row also carries description text to its right --
    # distinguishes it from a bare FH/CY/Month label (never numeric) and
    # from a line-2 row whose own STRUCTURE_ID token happens to be a bare
    # digit run too but sits further right (~x=200, still < _X_LEFT_MAX;
    # a line-2 row always also carries real line-2 content further right,
    # same shape check either way).
    return any(w["left"] >= _X_LEFT_MAX for w in row_sorted[1:])


def _bucket(row: list[dict], bounds: list[tuple[float, float, str]]) -> dict[str, str]:
    """Bucket a row's words by x-position into named columns. A bound
    named "_IGNORE" (used for a row's own leading label cell, e.g. the
    "FH"/"CY"/"Month" word itself, or a row-3 zone with no real column)
    is deliberately dropped from the returned dict -- it exists only to
    consume those words so they don't spill into a real neighbouring
    column, never as an output field."""
    out: dict[str, list[str]] = {}
    for w in sorted(row, key=lambda w: w["left"]):
        for lo, hi, name in bounds:
            if lo <= w["left"] < hi:
                out.setdefault(name, []).append(w["text"])
                break
    return {
        name: " ".join(out.get(name, [])).strip()
        for _, _, name in bounds
        if name != "_IGNORE"
    }


_ROW1_BOUNDS = [
    (-1e9, _X_POSITION_MAX, "POSITION"),
    (_X_POSITION_MAX, 1e9, "DESCRIPTION"),
]
_ROW2_BOUNDS = [
    (-1e9, _X_LEFT_MAX, "STRUCTURE_ID"),
    (_X_LEFT_MAX, _X_FIN_MAX, "AMM"),
    (_X_FIN_MAX, _X_ZONE_MAX, "FIN"),
    (_X_ZONE_MAX, _X_ZONE_END, "ZONE"),
    (_X_ZONE_END, _X_MAINT_ETOPS_END, "MAINT_LEVEL_ETOPS"),
    (_X_MAINT_ETOPS_END, _X_PROTOCOL_END, "PROTOCOL_TYPE"),
    (_X_PROTOCOL_END, _X_PHASING_END, "PHASING"),
    (_X_PHASING_END, 1e9, "TOLERANCE"),
]
_ROW3_BOUNDS = [
    (-1e9, _X_PN_DESC_MAX, "_IGNORE"),
    (_X_PN_DESC_MAX, _X_FIN_MAX, "PN_DESCRIPTION"),
    (_X_FIN_MAX, _X_PART_NUMBER_END, "PART_NUMBER"),
    (_X_PART_NUMBER_END, 1e9, "SERIAL_NUMBER"),
]


def _status_bounds(prefix: str) -> list[tuple[float, float, str]]:
    return [
        (-1e9, _X_STATUS_1_MAX, "_IGNORE"),
        (_X_STATUS_1_MAX, _X_STATUS_1_END, f"{prefix}_INSPECTION_BI"),
        (_X_STATUS_1_END, _X_STATUS_2_END, f"{prefix}_OTHER_INSPECTION_BI2"),
        (_X_STATUS_2_END, _X_STATUS_3_END, f"{prefix}_OVERHAUL_BO"),
        (_X_STATUS_3_END, 1e9, f"{prefix}_LIFE_LIMIT_MAX"),
    ]


def _row_text(row: list[dict]) -> str:
    return " ".join(w["text"] for w in sorted(row, key=lambda w: w["left"])).strip()


def _assemble_record(anchor: list[dict], body_rows: list[list[dict]]) -> dict:
    rec = {col: "" for col in CANONICAL_COLUMNS}
    r1 = _bucket(anchor, _ROW1_BOUNDS)
    rec["POSITION"] = r1["POSITION"]
    rec["DESCRIPTION"] = r1["DESCRIPTION"]

    labeled = {"FH": None, "CY": None, "MONTH": None}
    plain_rows: list[list[dict]] = []
    for row in body_rows:
        label = _row_label(row)
        if label is not None:
            labeled[label] = row
        else:
            plain_rows.append(row)

    if len(plain_rows) >= 1:
        r2 = _bucket(plain_rows[0], _ROW2_BOUNDS)
        for k in ("STRUCTURE_ID", "AMM", "FIN", "ZONE", "MAINT_LEVEL_ETOPS", "PHASING", "TOLERANCE"):
            rec[k] = r2[k]
        rec["PROTOCOL_TYPE"] = _norm_oc(r2["PROTOCOL_TYPE"])
    if len(plain_rows) >= 2:
        r3 = _bucket(plain_rows[1], _ROW3_BOUNDS)
        rec["PN_DESCRIPTION"] = r3["PN_DESCRIPTION"]
        rec["PART_NUMBER"] = r3["PART_NUMBER"]
        rec["SERIAL_NUMBER"] = r3["SERIAL_NUMBER"]
    if len(plain_rows) > 2:
        # Never observed on the real sample file (see module docstring) --
        # folded into the catch-all rather than silently dropped or
        # guessed into an existing field.
        rec["EXTRA_TEXT"] = " | ".join(_row_text(r) for r in plain_rows[2:])

    for label, prefix in (("FH", "FH"), ("CY", "CY"), ("MONTH", "MONTH")):
        row = labeled[label]
        if row is None:
            continue
        vals = _bucket(row, _status_bounds(prefix))
        for k, v in vals.items():
            rec[k] = _norm_oc(v)
    return rec


def _split_blocks(rows: list[list[dict]]) -> list[tuple[list[dict], list[list[dict]]]]:
    anchors_idx = [i for i, r in enumerate(rows) if _is_anchor(r)]
    blocks = []
    for n, ai in enumerate(anchors_idx):
        end = anchors_idx[n + 1] if n + 1 < len(anchors_idx) else len(rows)
        blocks.append((rows[ai], rows[ai + 1:end]))
    return blocks


_HEADER_FIELDS = ("AIRCRAFT_REG", "EFFECTIVITY", "PROTOCOL", "CYCLE", "REPORT_DATE")

_AC_RE = re.compile(r"A[/I.]?[CG]\s*:\s*([A-Z0-9\-]+)", re.I)
_EFF_RE = re.compile(r"Effectivity\s*:?\s*([A-Z0-9]+)", re.I)
_PROTO_RE = re.compile(r"Protocol\s*:?\s*([A-Z0-9]+)", re.I)
_CYCLE_RE = re.compile(r"Cycle\s*:?\s*([\d ]{1,3}\s?\d{0,3})", re.I)
_DATE_RE = re.compile(r"(\d{1,2}\s+\S+\s+\d{4})")


async def _parse_header_meta(img: Image.Image) -> dict:
    """Header info band (A/C / Effectivity / Protocol / A/B / B/B / Cycle) --
    OCR'd from a single top-of-page crop and picked apart with per-label
    regexes (rather than a fixed column split) since the labels themselves
    are confirmed to render at slightly different x-positions from row to
    row (see module docstring's own note on OCR label-spelling noise in
    this package's sibling AMASIS module, `component_list_kardex.py`)."""
    meta = {k: "" for k in _HEADER_FIELDS}
    w, h = img.size
    crop = img.crop((0, int(h * 0.045), w, int(h * 0.075)))
    text = await ocr_text(crop, psm=6)
    m = _AC_RE.search(text)
    if m:
        meta["AIRCRAFT_REG"] = m.group(1)
    m = _EFF_RE.search(text)
    if m:
        meta["EFFECTIVITY"] = m.group(1)
    m = _PROTO_RE.search(text)
    if m:
        meta["PROTOCOL"] = m.group(1)
    m = _CYCLE_RE.search(text)
    if m:
        meta["CYCLE"] = m.group(1).strip()
    footer_crop = img.crop((0, int(h * 0.975), int(w * 0.4), h))
    footer_text = await ocr_text(footer_crop, psm=6)
    m = _DATE_RE.search(footer_text)
    if m:
        meta["REPORT_DATE"] = m.group(1)
    return meta


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's OCR-fallback loop (see
    `sheet_types/occm.py`'s `_is_cid_garbled()` -- this module's known
    source file has a non-blank but entirely unusable text layer, reached
    only through that fallback, never through a normal SIGNATURES match).

    Requires BOTH the report's own brand text ("AMASIS") and its own title
    line ("Report KARDEX by Aircraft") together, in the same top-of-page
    crop. Checked directly (grep across every SIGNATURES list in
    sheet_types/{occm,ht,llp}.py and every existing occm_variants/
    ht_variants/llp_variants module, plus every module's own ocr_detect()
    anchor text): "AMASIS" is not used as an actual matching string
    anywhere else in this package (only ever mentioned in prose comments
    speculating about the MIS tool behind a couple of unrelated modules),
    and "REPORT KARDEX BY AIRCRAFT" is a materially different phrase from
    the bare "KARDEX" SIGNATURES entries used by
    `remaining_potentials.py`/`technical_object_listing.py` (those two
    modules are both reached only through the router's normal pdfplumber
    SIGNATURES match, which requires real extracted text -- something this
    module's own known source file never has, so the two paths cannot
    collide on the same file either way) and from
    `component_list_kardex.py`'s own SIGNATURES entry ("COMPONENT LIST",
    no "KARDEX" substring at all). No other module's own SIGNATURES/
    ocr_detect anchor requires the combination checked here.
    """
    try:
        img = await render_page(pdf_path, 0, dpi=300)
        w, h = img.size
        # 0.06 (not a tighter crop): confirmed directly, a shorter crop
        # (0.04) clips the bottom of the title band's own glyphs just
        # enough to misread it entirely ("Report KARDEX by Aircraft" OCRs
        # as "Ranart KARDEY hv Aircraft" at that height) -- 0.05 was the
        # first height confirmed to read cleanly, 0.06 used for margin.
        crop = img.crop((0, 0, w, int(h * 0.06)))
        text = (await ocr_text(crop, psm=6)).upper()
        normed = " ".join(text.split())
        return "AMASIS" in normed and "REPORT KARDEX BY AIRCRAFT" in normed
    except Exception:
        return False


async def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    header_meta = {k: "" for k in _HEADER_FIELDS}
    n_pages = await page_count(pdf_path)
    for page_index in range(n_pages):
        # 300 DPI: confirmed directly, side by side against this same page
        # at 400 DPI, to already OCR this report's own body text cleanly
        # (a whole-page `ocr_words()` pass, not per-column-strip -- see
        # module docstring's own note on why per-column-strip wasn't
        # needed here) -- see this module's own docstring "Column
        # x-boundaries" note for why this fixed DPI matters beyond just
        # image quality.
        img = await render_page(pdf_path, page_index, dpi=300)
        if page_index == 1:
            # Page 1 (index 0) is a title/parameters cover sheet, not a
            # data page -- confirmed directly, it carries no table at all.
            # The header info band repeats identically on every real data
            # page, so it's read once from the first real data page
            # (index 1) and stamped on every record, same convention as
            # this package's other header-plus-body OCCM variants.
            header_meta = await _parse_header_meta(img)
        words = await ocr_words(img, psm=6)
        rows = _cluster_rows(words)
        for anchor, body_rows in _split_blocks(rows):
            rec = _assemble_record(anchor, body_rows)
            rec.update(header_meta)
            rec["_page"] = page_index + 1
            records.append(rec)
    return records
