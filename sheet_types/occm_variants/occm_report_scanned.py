""""OCCM REPORT" component list — scanned, no text layer, OCR required.

Confirmed on one real file in the corpus (0 chars across every page via
`fitz`/pdfplumber text extraction, 1 embedded image per page) — a
photographed/scanned multi-page A-series-airframe component listing with a
simple 6-column ruled grid repeated on every page::

    <airframe> MSN <n>
    OCCM REPORT
    ATA | INSTALL DATE | POSITION | PN | SN | DESCRIPTION
    21  | 3-Sep-01      | 44WM1T   | 1263A0000-03 | 03103    | MACHINE, AIR CYCLES
    21  | 3-Sep-01      | 43MMT    | 1263A0000-03 | 03005002 | MACHINE, AIR CYCLE (HT)
    21  | 24-Jan-17     | 44WBLT   | 1303A0000-04 | 1303-03513 | VALVE-FLOW CONTROL (LHT)

Two other files initially grouped into this cluster by an automated
similarity pass turned out NOT to share this format on direct inspection:
one has a completely different header/column layout ("ON CONDITION
COMPONENT MONITORING STATUS", ATA/PART DESCRIPTION/PART NUMBER/SERIAL
NUMBER/POSITION/DATE INSTALLED/TSN/CSN) and a real text layer; the other
shares this module's exact column shape (ATA/INSTALL DATE/POSITION/PN/SN/
DESCRIPTION) but is a *born-digital* export of it with a full, clean text
layer — a plain pdfplumber-based sibling variant would be the right home
for that one, not this OCR module, since its text is already directly
extractable. Only the genuinely-scanned file drives this module.

The ruled table borders (vertical pipes between columns) OCR unpredictably:
sometimes as a lone stray token, sometimes fused into a run of border/text
noise that swallows a whole row into one garbled string (seen especially on
crowded sub-sections lower down some pages). Whole-page `ocr_text()` +
line-token splitting (the approach `sriwijaya_b737_occm.py` uses for a
similarly-shaped grid) does not hold up here: a border artifact can eat the
whitespace gap between two real columns, silently shifting every token
index for the rest of the row. This module instead OCRs the page once via
`ocr_words()` for word-level bounding boxes, clusters words into text-lines
by Y-coordinate (same technique as `aircraft_rotables_report_scanned.py`),
and buckets each line's words into the 6 columns by X-position — a border
artifact fused onto a neighbouring word still lands in the right column
bucket even when it can't be split into its own token.

Word-level OCR confidence runs low across the data grid on the one known
source file (session-median in the noisy grid area sits well under
Tesseract's default `conf > 30` filter — plain digits/letters against faint
ruled lines score in the 0-40 range even when legible on the rendered
page), so this module calls `ocr_words(min_conf=-1)` to keep every
recognized word rather than silently dropping whole cells (confirmed by
direct inspection: filtering at the default threshold blanks out PN/SN/
POSITION on a large fraction of otherwise-readable rows).

A genuine data row is accepted only when DESCRIPTION is non-empty and at
least one of PN/SN contains a 3+ digit run — this reliably separates real
component rows from the repeated column-header line ("ATA | INSTALL DATE |
..."), which reprints atop the grid on every page and would otherwise be
mistaken for a data row since its DESCRIPTION-column cell ("DESCRIPTION" /
"OCCM REPORT" depending on how the title block above it got OCR'd into the
same line cluster) is non-empty text with no digits.

ATA and INSTALL_DATE are both OCR'd too unreliably to trust the raw column
bucket outright (a leading border-artifact character routinely fuses onto
the leading digit, e.g. "21" -> "p21"/"21s"/"Patt"): both are recovered via
a permissive regex over the bucket text rather than used verbatim. When no
usable ATA digits are found, the field is left empty so
`occm.normalize_and_validate()`'s `forward_fill_ata()` post-process can
inherit it from the preceding row, the same safety net every other OCCM
variant in this package relies on for a missed chapter number.
"""
from __future__ import annotations
import re

import pandas as pd

from sheet_types.occm_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, ocr_words, page_count

NAME = "OCCM Report (Scanned)"

# Deliberately empty -- every known source file has no text layer at all
# (see module docstring). Detection happens via ocr_detect() below.
SIGNATURES = []

CANONICAL_COLUMNS = [
    "ATA",
    "INSTALL_DATE",
    "POSITION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
]

_OVERRIDES = {
    # The day-month and month-year separators are read as a dash, a dot, a
    # stray space, or dropped entirely often enough on this file's data grid
    # (a fused OCR artifact eats the whitespace column-internal gaps just as
    # readily as it eats a real hyphen) that all four are accepted rather
    # than only the canonical dashed form -- confirmed against the known
    # source file, where "3-Sep-01"/"3Sep-01"/"3Sep01"/"3.Sep-01" are all
    # OCR renderings of the exact same printed date.
    "INSTALL_DATE": {"pattern": r"^\d{1,2}[-/. ]?[A-Za-z]{3}[-/. ]?\d{2,4}$",
                      "allow_empty": True},
    "POSITION":      {"allow_empty": True},
    "PART_NUMBER":   {"allow_empty": True},
    "SERIAL_NUMBER": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Column X-boundaries (px @ 300dpi), derived from word bounding boxes on
# the one known source file's header + data rows -- consistent across every
# inspected page (data column starts/ends line up with the header cell
# edges to within ~20px on every sample). ATA | INSTALL_DATE | POSITION |
# PART_NUMBER | SERIAL_NUMBER | DESCRIPTION.
_BOUNDS = [0, 340, 600, 900, 1250, 1600, 10**6]

_BORDER_RE = re.compile(r"[|\[\]<>=~()`*\"'«»‘’“”–—]+")
_SEP_RUN_RE = re.compile(r"_{2,}|\.{3,}|-{3,}")
_EDGE_STRIP = " _-|[]=~.\"'"

# Real PN/SN values in this template are digit-heavy; the repeated header
# line's PN/SN cells ("PN"/"SN" or border-garbled variants of them) never
# contain a run this long, so this doubles as the header/data-row filter.
_DIGIT_RUN_RE = re.compile(r"\d{3,}")
# ATA chapters seen across this airframe's known rows; a 2-digit run
# outside this band is almost always a mis-split serial/part-number digit
# pair rather than a real chapter number.
_ATA_RANGE = (20, 83)
_DATE_RE = re.compile(r"\d{1,2}[-/. ]?[A-Za-z]{3}[-/. ]?\d{2,4}")


def _clean_bucket(text: str) -> str:
    s = _SEP_RUN_RE.sub(" ", _BORDER_RE.sub(" ", text))
    return " ".join(s.split()).strip(_EDGE_STRIP)


def _extract_ata(text: str) -> str:
    """Pull a plausible 2-digit ATA chapter out of a border-noise-prone
    bucket (see module docstring). Tries each digit run found in the text,
    in order, and each run's first/last 2 digits (a leading or trailing
    border artifact commonly fuses an extra digit onto the real chapter
    number) -- the first candidate inside the known chapter range wins.
    Returns "" when nothing plausible is found, so forward-fill can recover
    it from the preceding row instead of guessing.
    """
    for run in re.findall(r"\d+", text):
        candidates = [run] if len(run) == 2 else [run[:2], run[-2:]]
        for cand in candidates:
            if len(cand) == 2 and _ATA_RANGE[0] <= int(cand) <= _ATA_RANGE[1]:
                return cand
    return ""


def _extract_date(text: str) -> str:
    m = _DATE_RE.search(text)
    return m.group(0) if m else _clean_bucket(text)


def _bucket_words(words: list[tuple[float, float, str]]) -> list[str]:
    buckets: list[list[str]] = [[] for _ in range(len(_BOUNDS) - 1)]
    for left, width, text in words:
        center = left + width / 2
        for i in range(len(_BOUNDS) - 1):
            if _BOUNDS[i] <= center < _BOUNDS[i + 1]:
                buckets[i].append(text)
                break
    return [_clean_bucket(" ".join(b)) for b in buckets]


def _words_to_df(words: list[dict]) -> pd.DataFrame:
    cols = ["left", "top", "width", "height", "conf", "text"]
    df = pd.DataFrame(words, columns=cols) if words else pd.DataFrame(columns=cols)
    if not df.empty:
        df = df.dropna(subset=["text"])
        df = df[df["text"].astype(str).str.strip() != ""]
    return df


def _group_lines(df: pd.DataFrame):
    """Cluster words into text-lines by Y coordinate (adaptive threshold on
    median row height) -- ocr_words()'s output has no block/par/line_num
    fields, so lines are recovered geometrically instead (same approach as
    aircraft_rotables_report_scanned.py)."""
    if df.empty:
        return []
    df = df.sort_values(["top", "left"]).reset_index(drop=True)
    median_h = df["height"].median()
    df["row_id"] = (df["top"].diff().fillna(0).abs() > median_h * 0.5).cumsum()
    groups = []
    for _, g in df.groupby("row_id"):
        g = g.sort_values("left")
        words = list(zip(g["left"], g["width"], g["text"].astype(str)))
        groups.append((g["top"].mean(), words))
    groups.sort(key=lambda t: t[0])
    return [words for _, words in groups]


async def _parse_page(img, page_num: int) -> list[dict]:
    df = _words_to_df(await ocr_words(img, psm=6, min_conf=-1))
    lines = _group_lines(df)
    records = []
    for words in lines:
        cols = _bucket_words(words)
        ata_raw, date_raw, position, pn, sn, description = cols
        if not description:
            continue
        # Filters out the repeated column-header line and other non-data
        # noise (see module docstring) -- a real row's PN or SN always
        # carries a real digit run, the header cells never do.
        if not (_DIGIT_RUN_RE.search(pn) or _DIGIT_RUN_RE.search(sn)):
            continue
        records.append({
            "ATA": _extract_ata(ata_raw),
            "INSTALL_DATE": _extract_date(date_raw),
            "POSITION": position,
            "PART_NUMBER": pn,
            "SERIAL_NUMBER": sn,
            "DESCRIPTION": description,
            "_page": page_num,
        })
    return records


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback (see
    sheet_types/occm.py) -- this variant's SIGNATURES can never match
    through the normal pdfplumber text-extract path since the known source
    file has no text layer at all.

    Anchors on the "OCCM REPORT" title line, which OCRs cleanly on the
    known source file even though the data grid below it doesn't (see
    module docstring). Not shared by any other variant's ocr_detect anchor
    or top-level SIGNATURES list in this package (checked against
    sheet_types/{occm,ht,llp}.py and every OCR variant module at build
    time).
    """
    try:
        img = await render_page(pdf_path, 0, dpi=300)
        w, h = img.size
        crop = img.crop((0, 0, w, int(h * 0.20)))
        text = (await ocr_text(crop, psm=6)).upper()
        return "OCCM REPORT" in text
    except Exception:
        return False


async def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    n_pages = await page_count(pdf_path)
    for page_index in range(n_pages):
        img = await render_page(pdf_path, page_index, dpi=300)
        records.extend(await _parse_page(img, page_index + 1))
    return records
