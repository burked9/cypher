"""OCCM List (Func.loc / A/C Hours & Cycles header) -- scanned, no text
layer, OCR required throughout.

Confirmed on one real corpus file (19 pages, 0 extractable chars on every
page via pdfplumber -- a straight scan). Header block repeats verbatim on
every page::

    <reg> OCCM LIST  A/C HOURS : <hours>  CYCLES : <cycles>
    (Date: <dd.mm.yyyy>  Time : <hh:mm:ss>)

...followed by a ruled data grid with the column-header row
``Func.loc | Equipment text | Part number | Serial number | Eq.Number |
Inst.date | TSN | CSN`` (that header row itself also reprints on every
page, directly under the two metadata lines above). A single non-component
row (``<reg>`` alone in the Func.loc cell, every other cell blank except
TSN/CSN carrying the aircraft-level totals already given in the header) sits
at the very top of the grid on the first page -- it duplicates the header's
own A/C HOURS/CYCLES figures and carries no part data, so it's deliberately
excluded from extracted rows (the row filter below requires a genuine
compound Func.loc shape, which this summary row never has).

Func.loc is a compound identifier, one per row, shaped::

    <reg>-<ata_chapter>-<ata_section>-<code>-<seq>

e.g. (genericized) ``<reg>-<cc>-<ss>-<code><seq>``. Confirmed directly
across every page of the real sample file: the two leading 2-digit groups
immediately after the registration are a genuine 2-part ATA chapter/section
code -- NOT the same value repeated (multiple distinct chapters were
observed, each pairing with several different sections across its own
rows, confirmed by reading every ATA chapter's full run of section values
directly, not assumed from a single example). Only the chapter is pulled
into its own ATA column (matching this package's other compound-F/L
variant, `fl_compound_code_occm.py`); the registration prefix is dropped
(it's a constant cross-reference back to the header, stamped separately as
AIRCRAFT_REG on every row) and everything from the chapter digit onward is
also kept verbatim as POSITION_CODE, since the section/code/sequence
segments don't follow one single fixed-width shape across every observed
row (a trailing alpha suffix is sometimes present, sometimes not; the
segment lengths vary) -- re-splitting further than chapter/rest risks a
wrong split more than it helps, same call as `fl_compound_code_occm.py`
makes for its own compound code.

OCR approach: `ocr_words()` (word-level bounding boxes, kept at
`min_conf=-1` since real Func.loc cells confirmed to score well under
Tesseract's default conf>30 filter on a meaningful fraction of rows despite
being legible) + geometric line-clustering by Y-coordinate (same technique
as `occm_report_scanned.py`/`aircraft_rotables_report_scanned.py`), then an
X-position column bucket per line. Column boundaries below are measured
directly from real data-row word positions across three widely-separated
pages of the real sample file (first, second, and last) -- header/footer
noise and the repeated column-header row are filtered out downstream by
requiring a genuine ATA-shaped Func.loc, not by position.

A number of narrow cells (Func.loc, Equipment text, Eq.Number) occasionally
split across two OCR word boxes with a small internal gap that isn't a real
space in the source (confirmed directly, e.g. a Func.loc's trailing
alpha-numeric suffix landing in its own box). Func.loc/Part number/Serial
number/Eq.Number/Inst.date are all single compact codes with no legitimate
internal space, so their column's words are joined with no separator;
Equipment text is genuine free-text and is joined with spaces instead.

TSN/CSN cells routinely pick up a fused vertical-rule border artifact
(confirmed directly, e.g. a leading dash/underscore/pipe run glued onto the
digits from the ruled cell border) -- the amount is recovered by taking the
last digit/comma/decimal run found in the bucket's joined text rather than
using it verbatim.
"""
from __future__ import annotations
import re

import pandas as pd

from sheet_types.occm_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, ocr_words, page_count

NAME = "OCCM List (Func.loc / A/C Hours Header, Scanned)"

# Deliberately empty -- the known source file has no text layer at all (see
# module docstring). Detection happens via ocr_detect() below.
SIGNATURES = []

CANONICAL_COLUMNS = [
    "ATA",
    "POSITION_CODE",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "EQ_NUMBER",
    "INSTALL_DATE",
    "TSN",
    "CSN",
    # Header metadata -- parsed once (first page it's recoverable on) and
    # stamped onto every row.
    "AIRCRAFT_REG",
    "AIRCRAFT_HOURS",
    "AIRCRAFT_CYCLES",
    "REPORT_DATE",
    "REPORT_TIME",
]

# Broad numeric shape shared by TSN/CSN/AIRCRAFT_HOURS/AIRCRAFT_CYCLES --
# covers both the header's plain (no thousands separator) figures and the
# data grid's comma-grouped ones, confirmed both forms are genuine on the
# real sample file (not an OCR artifact either way).
_AMOUNT_RULE = {"pattern": r"^\d+(?:,\d{3})*(?:\.\d+)?$", "allow_empty": True}

_OVERRIDES = {
    "POSITION_CODE": {"pattern": r"^\d{2}-\d{2}-.+$", "uppercase": True},
    "EQ_NUMBER": {"pattern": r"^\d+$", "allow_empty": True},
    "INSTALL_DATE": {"pattern": r"^\d{2}\.\d{2}\.\d{4}$", "allow_empty": True},
    "TSN": _AMOUNT_RULE,
    "CSN": _AMOUNT_RULE,
    "AIRCRAFT_REG": {"uppercase": True, "allow_empty": True},
    "AIRCRAFT_HOURS": _AMOUNT_RULE,
    "AIRCRAFT_CYCLES": _AMOUNT_RULE,
    "REPORT_DATE": {"pattern": r"^\d{2}\.\d{2}\.\d{4}$", "allow_empty": True},
    "REPORT_TIME": {"pattern": r"^\d{2}:\d{2}:\d{2}$", "allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Column X-boundaries (px @ 300dpi), measured directly from real data-row
# word LEFT (x0) positions across the first, second, and last pages of the
# real sample file -- consistent across all three (data column starts line
# up to within a few px on every page inspected). Bucketing on left (not a
# left+width/2 center) is deliberate: TSN/CSN amounts are wide enough that a
# center-based bucket pushes a long TSN value's center past the CSN
# boundary and a short leftover word-fragment (e.g. a P/N split across two
# OCR word boxes, its second box a couple of characters wide) short enough
# that its center falls back a whole column -- confirmed directly on real
# rows from the last page and from a mid-file P/N split, both fixed by
# switching to left-edge bucketing.
_COLUMNS = [
    (-1e9, 520, "FUNC_LOC"),
    (520, 1020, "DESCRIPTION"),
    (1020, 1300, "PART_NUMBER"),
    (1300, 1540, "SERIAL_NUMBER"),
    (1540, 1790, "EQ_NUMBER"),
    (1790, 1965, "INSTALL_DATE"),
    (1965, 2170, "TSN"),
    (2170, 1e9, "CSN"),
]
# These columns are single compact codes with no legitimate internal space
# (see module docstring) -- their word-boxes are joined with no separator.
# DESCRIPTION (free text) is the only column joined with spaces.
_JOIN_NOSPACE = {"FUNC_LOC", "PART_NUMBER", "SERIAL_NUMBER", "EQ_NUMBER", "INSTALL_DATE"}

# Row anchor: Func.loc must contain a genuine <chapter>-<section>- ATA shape
# (see module docstring) -- filters out the repeated column-header row, the
# aircraft-level summary row, and any stray page furniture in one step.
_FUNC_LOC_ATA_RE = re.compile(r"-(\d{2})-\d{2}-")

_HEADER1_RE = re.compile(
    r"(?P<reg>[A-Z0-9]+(?:-[A-Z0-9]+)*)\s+OCCM\s*LIST\s+A/?C\s*HOURS\s*[:;]?\s*"
    r"(?P<hours>[\d,]+\.?\d*)\s+CYCLES\s*[:;]?\s*(?P<cycles>[\d,]+)",
    re.IGNORECASE,
)
_HEADER2_RE = re.compile(
    r"DATE\s*[:;]?\s*(?P<date>\d{2}\.\d{2}\.\d{4})\s+TIME\s*[:;]?\s*"
    r"(?P<time>\d{2}:\d{2}:\d{2})",
    re.IGNORECASE,
)

# Strips border/rule artifacts that fuse onto TSN/CSN digits (see module
# docstring) before pulling out the trailing amount.
_BORDER_NOISE_RE = re.compile(r"[|\[\]_—–\-]+")
_AMOUNT_TOKEN_RE = re.compile(r"\d[\d,]*\.?\d*")


def _col_for_x(center: float) -> str | None:
    for lo, hi, name in _COLUMNS:
        if lo <= center < hi:
            return name
    return None


def _extract_amount(text: str) -> str:
    """Last digit/comma/decimal run in a bucket's joined text, after
    stripping ruled-border noise (see module docstring) -- the fused
    artifact, when present, always sits ahead of the real amount, not
    after it, in every row inspected."""
    cleaned = _BORDER_NOISE_RE.sub(" ", text)
    matches = _AMOUNT_TOKEN_RE.findall(cleaned)
    return matches[-1] if matches else ""


def _split_func_loc(func_loc: str) -> tuple[str, str]:
    """Return (ata_chapter, position_code) -- see module docstring for why
    only the chapter is split out and the rest is kept verbatim."""
    m = _FUNC_LOC_ATA_RE.search(func_loc)
    if not m:
        return "", ""
    return m.group(1), func_loc[m.start() + 1:]


def _words_to_df(words: list[dict]) -> pd.DataFrame:
    cols = ["left", "top", "width", "height", "conf", "text"]
    df = pd.DataFrame(words, columns=cols) if words else pd.DataFrame(columns=cols)
    if not df.empty:
        df = df.dropna(subset=["text"])
        df = df[df["text"].astype(str).str.strip() != ""]
    return df


def _group_lines(df: pd.DataFrame):
    """Cluster words into text-lines by Y coordinate -- ocr_words() carries
    no line/par/block index, so lines are recovered geometrically (same
    approach as occm_report_scanned.py / aircraft_rotables_report_scanned.py)."""
    if df.empty:
        return []
    df = df.sort_values(["top", "left"]).reset_index(drop=True)
    median_h = df["height"].median() or 20
    # A plain `> median_h * 0.5` split (the threshold used by this
    # package's other Y-clustered OCR variants) is too tight on this
    # format specifically: confirmed directly (by inspecting every
    # consecutive top-to-top gap on a real page, sorted) that this file's
    # own gaps cluster in two clearly separated bands -- up to ~15px
    # within a genuine row (Tesseract returns a visibly taller box,
    # spanning close to the full row pitch, for the left-hand columns on
    # many rows, and a normal-height box for the right-hand ones) and
    # ~25-35px between genuinely different rows -- with no gaps observed
    # in between. A 0.5x-height (~10px) threshold sits inside the first
    # band and incorrectly splits roughly a fifth of rows in half, silently
    # dropping their SERIAL_NUMBER/TSN/CSN into an orphan one-line group;
    # a too-generous threshold the other direction incorrectly merges
    # separate rows together instead (confirmed directly: 1.3x-height, at
    # ~27px, straddles the real inter-row band and merges real rows on this
    # file). A fixed 18px threshold sits in the gap between the two real
    # bands.
    df["row_id"] = (df["top"].diff().fillna(0).abs() > 18).cumsum()
    groups = []
    for _, g in df.groupby("row_id"):
        g = g.sort_values("left")
        words = list(zip(g["left"], g["width"], g["text"].astype(str)))
        groups.append((g["top"].mean(), words))
    groups.sort(key=lambda t: t[0])
    return [words for _, words in groups]


def _bucket_words(words: list[tuple[float, float, str]]) -> dict[str, list[str]]:
    buckets: dict[str, list[str]] = {name: [] for _, _, name in _COLUMNS}
    for left, _width, text in words:
        name = _col_for_x(left)
        if name:
            buckets[name].append(text)
    return buckets


def _parse_line(words: list[tuple[float, float, str]], page_num: int,
                 header_meta: dict) -> dict | None:
    buckets = _bucket_words(words)
    func_loc = "".join(buckets["FUNC_LOC"]).replace("|", "").strip()
    ata, position_code = _split_func_loc(func_loc)
    if not ata:
        # Not a genuine component row (repeated column-header row, the
        # aircraft-level summary row, or page furniture) -- see module
        # docstring.
        return None
    part_number = "".join(buckets["PART_NUMBER"])
    if not part_number:
        return None

    rec = {
        "ATA": ata,
        "POSITION_CODE": position_code,
        "DESCRIPTION": " ".join(buckets["DESCRIPTION"]),
        "PART_NUMBER": part_number,
        "SERIAL_NUMBER": "".join(buckets["SERIAL_NUMBER"]),
        "EQ_NUMBER": "".join(buckets["EQ_NUMBER"]),
        "INSTALL_DATE": "".join(buckets["INSTALL_DATE"]),
        "TSN": _extract_amount(" ".join(buckets["TSN"])),
        "CSN": _extract_amount(" ".join(buckets["CSN"])),
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

    Anchors on "OCCM LIST A/C HOURS", the report's own title-line phrase,
    which OCRs reliably even at this cheap pass. Checked directly (grep
    across every SIGNATURES list in sheet_types/{occm,ht,llp}.py and every
    existing occm_variants file): a bare "OCCM LIST" substring is shared by
    three other modules (occm_list_msn_dotdate.py, occm_list_as_at.py,
    occm_list_for_registration.py -- see occm_list_at_aircraft_fh.py's own
    docstring note on this), but none of those, nor any other module's own
    SIGNATURES/ocr_detect anchor, contain the fuller "A/C HOURS" phrase
    this title carries.
    """
    try:
        img = await render_page(pdf_path, 0, dpi=300)
        w, h = img.size
        crop = img.crop((0, 0, w, int(h * 0.12)))
        text = (await ocr_text(crop, psm=6)).upper()
        return "OCCM LIST A/C HOURS" in text
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
            crop = img.crop((0, 0, w, int(h * 0.12)))
            header_text = await ocr_text(crop, psm=6)
            _parse_header_text(header_text, header_meta)
        words = await ocr_words(img, psm=6, min_conf=-1)
        df = _words_to_df(words)
        for line_words in _group_lines(df):
            rec = _parse_line(line_words, page_index + 1, header_meta)
            if rec is not None:
                records.append(rec)
    return records
