"""Component Inventory List (Func.loc / A/C Hours Header, wide columns) --
scanned, no text layer, OCR required throughout.

Confirmed on one real corpus file (71 pages, 0 extractable chars on every
page via pdfplumber -- a straight scan, landscape orientation). Shares this
package's `occm_list_func_loc_scanned.py` header idiom almost verbatim::

    <reg> COMPONENT INVENTORY LIST  A/C HOURS : <hours>  CYCLES : <cycles>
    (Date: <dd.mm.yyyy>  Time : <hh:mm:ss>)

...and the same compound Func.loc row anchor (``<reg>-<ata_chapter>-
<ata_section>-<code>-<seq>``, see that module's own docstring for the
reasoning on why only the ATA chapter is split out of it). Confirmed
directly this is a genuinely different report template rather than the
same one re-exported, not merely a title-string variant of that other
module:

  * Title phrase differs ("COMPONENT INVENTORY LIST" vs "OCCM LIST") --
    confirmed by rendering page 1 of both the known source file of that
    other module and this module's own source file directly and comparing
    the two title lines side by side.
  * Page geometry differs: this file's pages render landscape (wider than
    tall at a fixed DPI); the other module's known source file renders
    portrait. Every X-coordinate boundary below is measured fresh against
    this file's own geometry and is not interchangeable with that module's.
  * Column order differs, not just column count: this file's grid header
    reads ``Func.loc | Part number | Equipment text | Serial number |
    Eq.Number | Inst.date | TSN | CSN | TSO | CSO | TSR | CSR`` -- Part
    number and Equipment text are swapped relative to the other module's
    ``Func.loc | Equipment text | Part number | Serial number | ...``, and
    four extra life-limit columns (TSO/CSO/TSR/CSR -- time/cycles since
    overhaul and since repair) are appended after TSN/CSN. Confirmed
    directly from the real header row's own OCR'd column captions plus
    cross-checking against unambiguous two-value and six-value data rows
    on three widely-separated pages (first, one in the middle third, and
    last).

Given both the swapped column order and the wider/landscape geometry, widening
the other module in place (conditional column order, an entirely disjoint
X-boundary table, four more optional numeric columns) was judged more
forced than building this as its own module -- same call this package
makes elsewhere for a sibling but distinct compound-Func.loc layout
(compare `fl_compound_code_occm.py` for the other example of that choice).

SERIAL_NUMBER and EQ_NUMBER cannot be told apart by fixed X-position alone
on this file: confirmed directly that many rows carry only ONE populated
value between the description and the install date (the other of the pair
being genuinely blank on that row -- e.g. a structural/airframe part with
no separate manufacturer serial recorded, or vice versa), and on those
rows the lone value's actual pixel position sits far enough right that a
naive fixed boundary would misfile it under the wrong header, or spill an
overrunning multi-word DESCRIPTION into it. Confirmed directly across many
rows of the real sample file: every EQ_NUMBER value observed is an
8-digit, all-numeric code beginning with the literal digits "20" (this
looks like an internal document/asset numbering convention, not aircraft-
specific data), and every SERIAL_NUMBER value observed either lacks that
shape or is genuinely absent; DESCRIPTION words, in contrast, always
contain at least one alphabetic character and never a bare digit run.
Given that, the wide zone between PART_NUMBER and INST_DATE is parsed by
content shape rather than fixed X-buckets alone (see `_split_wide_zone`):
leading no-digit word(s) become DESCRIPTION, and of what alphanumeric
code-like word(s) remain, an 8-digit ``20``-prefixed one is EQ_NUMBER and
anything else is SERIAL_NUMBER; with exactly two code-like words left the
first is SERIAL_NUMBER and the second EQ_NUMBER (matching the header's own
left-to-right order), and with only one, its own shape decides which
column it belongs to.

FUNC_LOC and PART_NUMBER are still bucketed by fixed X-position (as in
`occm_list_func_loc_scanned.py`): both are narrow, compact codes that
never overrun their column on any row inspected, unlike DESCRIPTION.

OCR approach: `ocr_words()` (word-level bounding boxes, `min_conf=-1` for
the same reason given in `occm_list_func_loc_scanned.py` -- real cells on
this file also confirmed to score under Tesseract's default conf>30 filter
on a meaningful fraction of rows) + geometric line-clustering by Y
(same technique as that module and `occm_report_scanned.py`); the real
sample file's own top-to-top gaps were inspected directly (sorted, one
full page) and cluster the same way that module's docstring describes --
a tight in-row band under ~16px and a separate inter-row band starting
around ~23px, with nothing observed in between -- so the same 18px-style
fixed threshold this package already uses elsewhere is reused unchanged.

TSN/CSN/TSO/CSO/TSR/CSR cells pick up the same fused ruled-border artifact
described in `occm_list_func_loc_scanned.py`'s own docstring (a leading
dash/underscore/pipe run glued onto the digits); the same "last
digit/comma/decimal run in the bucket" recovery is reused here for all six
trailing numeric columns, not just two.
"""
from __future__ import annotations
import re

import pandas as pd

from sheet_types.occm_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, ocr_words, page_count

NAME = "Component Inventory List (Func.loc / A/C Hours Header, Wide, Scanned)"

# Deliberately empty -- the known source file has no text layer at all (see
# module docstring). Detection happens via ocr_detect() below.
SIGNATURES = []

CANONICAL_COLUMNS = [
    "ATA",
    "POSITION_CODE",
    "PART_NUMBER",
    "DESCRIPTION",
    "SERIAL_NUMBER",
    "EQ_NUMBER",
    "INSTALL_DATE",
    "TSN",
    "CSN",
    "TSO",
    "CSO",
    "TSR",
    "CSR",
    # Header metadata -- parsed once (first page it's recoverable on) and
    # stamped onto every row.
    "AIRCRAFT_REG",
    "AIRCRAFT_HOURS",
    "AIRCRAFT_CYCLES",
    "REPORT_DATE",
    "REPORT_TIME",
]

# Broad numeric shape shared by every life-limit/hours-cycles column and the
# header's own A/C HOURS & CYCLES figures -- see
# occm_list_func_loc_scanned.py's own _AMOUNT_RULE docstring note (same
# reasoning, extended here to all six trailing numeric columns).
_AMOUNT_RULE = {"pattern": r"^\d+(?:,\d{3})*(?:\.\d+)?$", "allow_empty": True}

_OVERRIDES = {
    "POSITION_CODE": {"pattern": r"^\d{2}-\d{2}-.+$", "uppercase": True},
    "EQ_NUMBER": {"pattern": r"^\d+$", "allow_empty": True},
    "INSTALL_DATE": {"pattern": r"^\d{2}\.\d{2}\.\d{4}$", "allow_empty": True},
    "TSN": _AMOUNT_RULE,
    "CSN": _AMOUNT_RULE,
    "TSO": _AMOUNT_RULE,
    "CSO": _AMOUNT_RULE,
    "TSR": _AMOUNT_RULE,
    "CSR": _AMOUNT_RULE,
    "AIRCRAFT_REG": {"uppercase": True, "allow_empty": True},
    "AIRCRAFT_HOURS": _AMOUNT_RULE,
    "AIRCRAFT_CYCLES": _AMOUNT_RULE,
    "REPORT_DATE": {"pattern": r"^\d{2}\.\d{2}\.\d{4}$", "allow_empty": True},
    "REPORT_TIME": {"pattern": r"^\d{2}:\d{2}:\d{2}$", "allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Column X-boundaries (px @ 300dpi) for the two narrow, never-overrunning
# leading columns only -- measured directly from real data-row word LEFT
# (x0) positions across the first, one middle, and the last page of the
# real sample file. Everything from PART_NUMBER's right edge onward is
# parsed by content shape instead (see module docstring / _split_wide_zone),
# not by a fixed bucket, because DESCRIPTION's width varies too much
# (single short word vs. several wrapped words) to give SERIAL_NUMBER/
# EQ_NUMBER/INST_DATE stable boundaries on every row.
_FUNC_LOC_MAX_X = 520
_PART_NUMBER_MAX_X = 790

# Trailing six numeric columns -- boundaries measured the same way as
# occm_list_func_loc_scanned.py's own _COLUMNS table (left-edge bucketing,
# same rationale: a wide amount's center can drift past its own column's
# boundary on this file too).
_TAIL_COLUMNS = [
    (2160, 2350, "TSN"),
    (2350, 2520, "CSN"),
    (2520, 2730, "TSO"),
    (2730, 2880, "CSO"),
    (2880, 3050, "TSR"),
    (3050, 1e9, "CSR"),
]

# Row anchor: the FUNC_LOC bucket's own reg prefix is always letters-only
# (the registration itself never contains a digit), so the first digit
# character in the joined bucket text marks the start of the ATA-shaped
# remainder. Confirmed directly this file's own compound Func.loc separator
# dashes OCR far less reliably than occm_list_func_loc_scanned.py's known
# source file -- across three widely-separated pages, the same genuine
# Func.loc value was seen missing a dash entirely, with a dash swapped for
# a period, and with digit groups glued straight together with no
# separator survivor at all -- so, unlike that module, this one does not
# require a literal "-DD-DD-" shape, only a run of at least 6 digits
# following the first digit found (short enough to tolerate 1-2 dropped
# digits, long enough that page furniture/footer text with a single stray
# digit -- confirmed directly on real non-data lines -- never qualifies).
_FUNC_LOC_FIRST_DIGIT_RE = re.compile(r"\d")
_MIN_ATA_DIGITS = 6

# Strips leading whitespace plus a ruled-border-artifact run (see
# `_split_func_loc_part_number` docstring) off PART_NUMBER once it's been
# identified -- real part numbers never start with any of these
# characters (the whitespace comes from the OCR word's own text, e.g. a
# leading space glued in front of a fused bracket artifact).
_BORDER_PREFIX_RE = re.compile(r"^[\s|\[\]_—–]+")

# Ruled-grid-line artifacts (see module docstring) also turn up fused
# mid-string or trailing on this file, not just as a leading run -- unlike
# `_BORDER_PREFIX_RE` this strips them anywhere in PART_NUMBER/
# SERIAL_NUMBER/EQ_NUMBER/DESCRIPTION, all of which are confirmed never to
# contain a bracket, underscore, or em/en-dash as genuine content (real
# hyphens in these fields are always the plain ASCII "-", never these).
_NOISE_ANYWHERE_RE = re.compile(r"[\[\]_—–]")


def _strip_noise(text: str) -> str:
    return _NOISE_ANYWHERE_RE.sub("", text).strip()

# EQ_NUMBER's own confirmed shape (see module docstring): 8 digits, always
# beginning with the literal "20".
_EQ_NUMBER_RE = re.compile(r"^20\d{6}$")
# A "code-like" wide-zone word: contains at least one digit (DESCRIPTION
# words never do, per module docstring).
_HAS_DIGIT_RE = re.compile(r"\d")
_DATE_RE = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")

_HEADER1_RE = re.compile(
    r"(?P<reg>[A-Z0-9]+(?:-[A-Z0-9]+)*)\s+COMPONENT\s*INVENTORY\s*LIST\s+"
    r"A/?C\s*HOURS\s*[:;]?\s*(?P<hours>[\d,]+\.?\d*)\s+CYCLES\s*[:;]?\s*"
    r"(?P<cycles>[\d,]+)",
    re.IGNORECASE,
)
_HEADER2_RE = re.compile(
    r"DATE\s*[:;]?\s*(?P<date>\d{2}\.\d{2}\.\d{4})\s+TIME\s*[:;]?\s*"
    r"(?P<time>\d{2}:\d{2}:\d{2})",
    re.IGNORECASE,
)

# Strips border/rule artifacts that fuse onto the six trailing numeric
# columns' digits (see module docstring) before pulling out the trailing
# amount.
_BORDER_NOISE_RE = re.compile(r"[|\[\]_—–\-]+")
_AMOUNT_TOKEN_RE = re.compile(r"\d[\d,]*\.?\d*")


def _extract_amount(text: str) -> str:
    """Last digit/comma/decimal run in a bucket's joined text, after
    stripping ruled-border noise -- see module docstring."""
    cleaned = _BORDER_NOISE_RE.sub(" ", text)
    matches = _AMOUNT_TOKEN_RE.findall(cleaned)
    return matches[-1] if matches else ""


def _split_func_loc(func_loc: str) -> tuple[str, str]:
    """Return (ata_chapter, position_code) -- see module docstring / the
    row-anchor comment above `_FUNC_LOC_FIRST_DIGIT_RE` for why this looks
    for the first digit rather than a literal "-DD-DD-" shape."""
    m = _FUNC_LOC_FIRST_DIGIT_RE.search(func_loc)
    if not m:
        return "", ""
    suffix = func_loc[m.start():]
    if sum(ch.isdigit() for ch in suffix) < _MIN_ATA_DIGITS:
        return "", ""
    ata = suffix[:2]
    if not ata.isdigit():
        return "", ""
    return ata, suffix


def _split_wide_zone(words: list[tuple[float, str]]) -> tuple[str, str, str, str]:
    """Split the words lying to the right of PART_NUMBER (left position,
    text pairs, already sorted by left) into (description, serial_number,
    eq_number, install_date) -- see module docstring for the content-shape
    reasoning."""
    install_date = ""
    rest: list[str] = []
    for _left, text in words:
        if not install_date and _DATE_RE.match(text):
            install_date = text
            continue
        if text not in ("|", "[", "]", "_", "-"):
            rest.append(text)

    description_words: list[str] = []
    code_words: list[str] = []
    i = 0
    while i < len(rest) and not _HAS_DIGIT_RE.search(rest[i]):
        description_words.append(rest[i])
        i += 1
    code_words = rest[i:]

    serial_number = ""
    eq_number = ""
    if len(code_words) >= 2:
        serial_number = code_words[0]
        eq_number = code_words[1]
    elif len(code_words) == 1:
        if _EQ_NUMBER_RE.match(code_words[0]):
            eq_number = code_words[0]
        else:
            serial_number = code_words[0]

    description = _strip_noise(" ".join(description_words))
    return description, _strip_noise(serial_number), _strip_noise(eq_number), install_date


def _words_to_df(words: list[dict]) -> pd.DataFrame:
    cols = ["left", "top", "width", "height", "conf", "text"]
    df = pd.DataFrame(words, columns=cols) if words else pd.DataFrame(columns=cols)
    if not df.empty:
        df = df.dropna(subset=["text"])
        df = df[df["text"].astype(str).str.strip() != ""]
    return df


def _group_lines(df: pd.DataFrame):
    """Cluster words into text-lines by Y coordinate -- see module
    docstring; same technique and threshold as
    occm_list_func_loc_scanned.py's own `_group_lines`."""
    if df.empty:
        return []
    df = df.sort_values(["top", "left"]).reset_index(drop=True)
    df["row_id"] = (df["top"].diff().fillna(0).abs() > 18).cumsum()
    groups = []
    for _, g in df.groupby("row_id"):
        g = g.sort_values("left")
        words = list(zip(g["left"], g["text"].astype(str)))
        groups.append((g["top"].mean(), words))
    groups.sort(key=lambda t: t[0])
    return [words for _, words in groups]


def _split_func_loc_part_number(lead_words: list[tuple[float, str]]) -> tuple[list, list]:
    """Split the words left of PART_NUMBER's nominal right edge into
    (func_loc_words, part_number_words) -- see module docstring's note on
    why a single fixed X-boundary between these two columns isn't reliable
    on this file. Confirmed directly: PART_NUMBER's own OCR word box
    routinely starts to the left of `_FUNC_LOC_MAX_X` (measured as low as
    485px on real rows against a nominal ~520-526px boundary), but it is
    reliably still its own separate OCR word, and -- on every leaked case
    inspected -- that word carries a leading ruled-border-artifact
    character (a pipe, bracket, underscore, or em/en-dash glued on from
    the grid line, same fused-artifact phenomenon documented in
    occm_list_func_loc_scanned.py's own docstring) that the genuine
    Func.loc continuation words never do. The first non-leading word
    (i > 0) that starts with one of those characters is treated as the
    real start of PART_NUMBER regardless of its measured X position;
    falls back to the fixed boundary if no such marker word is found."""
    for i, (left, text) in enumerate(lead_words):
        if i == 0:
            continue
        if re.match(r"^[|\[\]_—–]", text.strip()):
            return lead_words[:i], lead_words[i:]
    fallback = [(l, t) for l, t in lead_words if l < _FUNC_LOC_MAX_X]
    rest = [(l, t) for l, t in lead_words if l >= _FUNC_LOC_MAX_X]
    return fallback, rest


def _parse_line(words: list[tuple[float, str]], page_num: int,
                 header_meta: dict) -> dict | None:
    lead_words = [(l, t) for l, t in words if l < _PART_NUMBER_MAX_X]
    func_loc_pairs, part_number_pairs = _split_func_loc_part_number(lead_words)
    func_loc_words = [t for _l, t in func_loc_pairs]
    part_number_words = [t for _l, t in part_number_pairs]
    wide_words = [(l, t) for l, t in words if _PART_NUMBER_MAX_X <= l < _TAIL_COLUMNS[0][0] - 200]

    func_loc = "".join(func_loc_words).replace("|", "").strip()
    ata, position_code = _split_func_loc(func_loc)
    if not ata:
        # Not a genuine component row (repeated column-header row or page
        # furniture) -- see module docstring.
        return None
    part_number = _strip_noise(_BORDER_PREFIX_RE.sub("", "".join(part_number_words)))
    if not part_number:
        return None

    description, serial_number, eq_number, install_date = _split_wide_zone(wide_words)

    tail_buckets: dict[str, list[str]] = {name: [] for _, _, name in _TAIL_COLUMNS}
    for l, t in words:
        if l < _TAIL_COLUMNS[0][0] - 200:
            continue
        for lo, hi, name in _TAIL_COLUMNS:
            if lo <= l < hi:
                tail_buckets[name].append(t)
                break

    rec = {
        "ATA": ata,
        "POSITION_CODE": position_code,
        "PART_NUMBER": part_number,
        "DESCRIPTION": description,
        "SERIAL_NUMBER": serial_number,
        "EQ_NUMBER": eq_number,
        "INSTALL_DATE": install_date,
        "TSN": _extract_amount(" ".join(tail_buckets["TSN"])),
        "CSN": _extract_amount(" ".join(tail_buckets["CSN"])),
        "TSO": _extract_amount(" ".join(tail_buckets["TSO"])),
        "CSO": _extract_amount(" ".join(tail_buckets["CSO"])),
        "TSR": _extract_amount(" ".join(tail_buckets["TSR"])),
        "CSR": _extract_amount(" ".join(tail_buckets["CSR"])),
        "_page": page_num,
    }
    rec.update(header_meta)
    return rec


def _parse_header_text(text: str, header_meta: dict) -> None:
    if not header_meta["AIRCRAFT_REG"]:
        m1 = _HEADER1_RE.search(text)
        if m1:
            header_meta["AIRCRAFT_REG"] = m1.group("reg").upper()
            header_meta["AIRCRAFT_HOURS"] = m1.group("hours")
            header_meta["AIRCRAFT_CYCLES"] = m1.group("cycles")
    if not header_meta["REPORT_DATE"]:
        m2 = _HEADER2_RE.search(text)
        if m2:
            header_meta["REPORT_DATE"] = m2.group("date")
            header_meta["REPORT_TIME"] = m2.group("time")


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback (see
    sheet_types/occm.py) -- this variant's SIGNATURES can never match
    through the normal pdfplumber text-extract path since the known source
    file has no text layer at all.

    Anchors on "COMPONENT INVENTORY LIST A/C HOURS", this report's own
    title-line phrase. Checked directly (grep across every SIGNATURES list
    in sheet_types/{occm,ht,llp}.py and every existing occm_variants file,
    occm_list_func_loc_scanned.py and occm_component_inventory.py
    included): this fuller phrase appears nowhere else, and it is not a
    substring of (nor contains) any other module's own SIGNATURES/
    ocr_detect anchor -- in particular it does not collide with
    occm_list_func_loc_scanned.py's own "OCCM LIST A/C HOURS" anchor since
    the title words themselves differ ("COMPONENT INVENTORY" vs "OCCM").

    Crops the top 18% of the page height, not the 12% that module's own
    ocr_detect() uses -- confirmed directly this file's title/header block
    sits lower as a fraction of page height on account of its landscape
    orientation (see module docstring); a 12% crop clips mid-line and
    garbles the OCR pass on every page tried.
    """
    try:
        img = await render_page(pdf_path, 0, dpi=300)
        w, h = img.size
        crop = img.crop((0, 0, w, int(h * 0.18)))
        text = (await ocr_text(crop, psm=6)).upper()
        return "COMPONENT INVENTORY LIST" in text and "A/C HOURS" in text
    except Exception:
        return False


async def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    header_meta = {
        "AIRCRAFT_REG": "", "AIRCRAFT_HOURS": "", "AIRCRAFT_CYCLES": "",
        "REPORT_DATE": "", "REPORT_TIME": "",
    }
    n_pages = await page_count(pdf_path)
    for page_index in range(n_pages):
        img = await render_page(pdf_path, page_index, dpi=300)
        if not header_meta["AIRCRAFT_REG"] or not header_meta["REPORT_DATE"]:
            w, h = img.size
            # 18%, not 12% -- see ocr_detect()'s own docstring note above.
            crop = img.crop((0, 0, w, int(h * 0.18)))
            header_text = await ocr_text(crop, psm=6)
            _parse_header_text(header_text, header_meta)
        words = await ocr_words(img, psm=6, min_conf=-1)
        df = _words_to_df(words)
        for line_words in _group_lines(df):
            rec = _parse_line(line_words, page_index + 1, header_meta)
            if rec is not None:
                records.append(rec)
    return records
