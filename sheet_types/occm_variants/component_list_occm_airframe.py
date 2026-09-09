"""Component List OCCM- Airframe -- scanned, no text layer, OCR required
throughout.

Confirmed directly on a real corpus file (8 pages, 0 extractable chars on
every page via pdfplumber -- a straight scan, same triage step used by this
package's other scanned OCCM variants). Page 1 carries a header block, not
repeated in full on later pages (only the report's title line reprints on
every page)::

    <operator logo/name>              COMPONENT LIST OCCM- AIRFRAME

    AIRCRAFT REGISTER: <reg>      A/C SERIAL NUMBER: <msn>      REPORT DATE: <date>
    A/C MODEL: <type>              A/C LINE NUMBER: <n>          A/C TSN: <n>
    A/C MANUFACTURE DATE: <date>   A/C VARIABLE NUMBER: <code>   A/C CSN: <n>

Note: the real sample file's page 1 carries an operator logo/wordmark in
the top-left corner -- confirmed directly, NOT extracted into any column
here (out of scope for this module, and per this project's data-sensitivity
convention, no operator name is recorded anywhere below).

Column header row, confirmed directly against the real rendered page (not
assumed from any pre-cached OCR pass), and this row reprints on every page::

    ATA | PART NUMBER | SERIAL NUMBER | DESCRIPTION | POSITION | INSTALLATION DATE | TSN | CSN

A data row, tokens in column order: ATA, PART_NUMBER, SERIAL_NUMBER,
DESCRIPTION, POSITION, INSTALL_DATE, TSN, CSN. ATA is only printed on the
first row of each ATA-chapter run (blank on subsequent rows of the same
chapter, confirmed directly across multiple chapters on the real sample
file) -- left blank here and recovered downstream by occm.py's generic
forward-fill-ATA post-process, same convention as this package's other
column-per-chapter-run variants.

OCR approach: `ocr_words()` (word-level bounding boxes) + geometric
line-clustering by Y-coordinate, then an X-position column bucket per line
(same technique as `occm_list_func_loc_scanned.py`/`occm_report_scanned.py`/
`aircraft_rotables_report_scanned.py`). `psm=11` (sparse text, no layout
assumption) is used rather than this package's more common `psm=6`:
confirmed directly on the real sample file that `psm=6` recognizes only a
small fraction of the table's words on a full-page pass (its "assume a
single uniform block of text" layout model doesn't hold for a dense ruled
grid at this resolution), while `psm=11` recovers several times as many
word boxes on the same page -- verified directly by comparing word counts
returned for both modes on the real file. `min_conf=-1` is used (keep every
recognized word) since real cells on this file are legible but frequently
land at or below Tesseract's default conf>30 cutoff, same reasoning as
`occm_list_func_loc_scanned.py`.

Column X-boundaries (px @ 300dpi) below are measured directly from the
column-header row's own word positions plus a page-spanning check of
ruled-border vertical-line pixel columns (both confirmed to agree, and
confirmed stable across widely-separated pages of the real sample file --
first and second page checked directly).

Ruled-border artifacts (`|`, `_`, `[`, `]`, stray dashes) routinely land as
their own OCR word box, glued onto real column content with no separating
space in the source (confirmed directly) -- these are dropped before a
bucket's words are joined, rather than kept and risking a wrong downstream
pattern match.

Known limitation, confirmed directly against the real sample file: OCR
quality varies a lot row to row -- some rows have PART_NUMBER/
SERIAL_NUMBER/DESCRIPTION cells fused together or entirely misread (e.g. a
handful of glyphs substituted beyond recognition), and a genuine
multi-line wrapped DESCRIPTION cell occasionally splits into two separate
extracted rows sharing the same PART_NUMBER/SERIAL_NUMBER position, with
one of the two missing some trailing columns. Rows are extracted as read
rather than silently merged or discarded on a guess; a suspicious cell is
expected to surface as a validation flag downstream, per this project's
soft-validation convention (see `shared/aviation_rules.py`), not "corrected"
here.
"""
from __future__ import annotations
import re

import pandas as pd

from sheet_types.occm_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, ocr_words, page_count

NAME = "Component List OCCM- Airframe"

# This module's known source file has no text layer at all (confirmed via
# pdfplumber -- 0 chars on every page), so these SIGNATURES can never fire
# through occm.py's normal pdfplumber head-text match; real detection
# happens via ocr_detect() below. Kept here anyway (per this project's
# convention) as a documented anchor and a safety net for any future
# born-digital re-export. The title phrase contains
# component_list_kardex.py's own (deliberately generic, placed near the end
# of occm.py's VARIANTS list) "COMPONENT LIST" phrase as a substring -- by
# design, per that module's own docstring note on why it's generic and
# placed late; this module's own phrase is the fuller, more specific title
# line. Checked for collisions against every SIGNATURES list in
# sheet_types/{occm,ht,llp}.py and every existing variant file: no other
# module's own SIGNATURES entry contains "AIRFRAME" combined with
# "COMPONENT LIST", and none of those files/entries is a substring of (nor
# contains) this fuller phrase.
SIGNATURES = [
    "COMPONENT LIST OCCM- AIRFRAME",
]

CANONICAL_COLUMNS = [
    "ATA",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
    "POSITION",
    "INSTALL_DATE",
    "TSN",
    "CSN",
    # Header metadata, parsed once (page 1) and stamped on every row.
    "AIRCRAFT_REG",
    "AC_MODEL",
    "MFG_DATE",
    "MSN",
    "LINE_NUMBER",
    "VARIABLE_NUMBER",
    "REPORT_DATE",
    "AC_TSN",
    "AC_CSN",
]

_NUM_RULE = {"pattern": r"^\d+$", "allow_empty": True}
_OVERRIDES = {
    # No global default exists for POSITION -- usually a single code (a
    # bare side letter/digit or a short mnemonic like "UNC"/"APO"), but
    # confirmed on real rows to sometimes be two tokens (e.g. a side code
    # plus a sub-zone letter) or a parenthesised qualifier.
    "POSITION": {
        "pattern": r"^[A-Z0-9][A-Z0-9 /\-]{0,15}$",
        "uppercase": True,
        "allow_empty": True,
    },
    # Loose on purpose: real dates on this file are "<D[D]>.<Mon>.<YYYY>"
    # but OCR noise substitutes stray digits/symbols for letters inside the
    # month abbreviation (confirmed directly) -- flag genuinely malformed
    # dates rather than reject this whole, otherwise-valid shape.
    "INSTALL_DATE": {
        "pattern": r"^\d{1,2}\W?[A-Za-z0-9\W]{2,8}\W?\d{4}$",
        "allow_empty": True,
    },
    "TSN": _NUM_RULE,
    "CSN": _NUM_RULE,
    # Header metadata -- each value is a single figure parsed once and
    # stamped identically on every row of the file, so a tight pattern here
    # would either flag every single row over one OCR misread in one place,
    # or none at all -- neither is a useful per-row signal. Genuine per-row
    # corruption is still caught by the row-level rules above. Same
    # reasoning as occm_list_func_loc_scanned.py's HEADER_TSN /
    # aircraft_fitlist_occm.py's HEADER_TSN.
    "AIRCRAFT_REG": {"allow_empty": True},
    "AC_MODEL": {"allow_empty": True},
    "MFG_DATE": {"allow_empty": True},
    "MSN": {"allow_empty": True},
    "LINE_NUMBER": {"allow_empty": True},
    "VARIABLE_NUMBER": {"allow_empty": True},
    "REPORT_DATE": {"allow_empty": True},
    "AC_TSN": {"allow_empty": True},
    "AC_CSN": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Column X-boundaries (px @ 300dpi), measured directly from the real
# rendered page (see module docstring) -- confirmed stable across the
# first and second pages of the real sample file.
_COLUMNS = [
    (-1e9, 209, "ATA"),
    (209, 593, "PART_NUMBER"),
    (593, 848, "SERIAL_NUMBER"),
    (848, 1468, "DESCRIPTION"),
    (1468, 1617, "POSITION"),
    (1617, 1912, "INSTALL_DATE"),
    (1912, 2123, "TSN"),
    (2123, 1e9, "CSN"),
]

# Ruled-border artifacts routinely picked up as their own OCR word box (see
# module docstring) -- dropped before a bucket's words are joined.
_NOISE_TOKEN_RE = re.compile(r"^[|\[\]_\-—–]+$")

# Row-level anchor: skip the repeated column-header row, the page-1 title
# line, and the page-1 metadata block -- all identified by a literal label
# phrase that never appears as genuine cell content (real PART_NUMBER/
# SERIAL_NUMBER cells are compact codes, never the literal words "PART
# NUMBER"/"SERIAL NUMBER").
_JUNK_MARKERS = [
    "AIRCRAFT REGISTER", "A/C MODEL", "A/C MANUFACTURE", "A/C SERIAL NUMBER",
    "A/C LINE NUMBER", "A/C VARIABLE NUMBER", "REPORT DATE", "A/C TSN",
    "A/C CSN", "COMPONENT LIST", "PART NUMBER", "SERIAL NUMBER",
    "INSTALLATION DATE",
]

_REG_RE = re.compile(r"AIRCRAFT REGISTER:\s*([A-Z0-9\-]+)", re.IGNORECASE)
_MODEL_RE = re.compile(r"A/?C\s*MODEL:\s*(\S+)", re.IGNORECASE)
_MFG_DATE_RE = re.compile(r"A/?C\s*MANUFACTURE DATE:\s*(\S+)", re.IGNORECASE)
_MSN_RE = re.compile(r"A/?C\s*SERIAL NUMBER:\s*(\d+)", re.IGNORECASE)
_LINE_RE = re.compile(r"A/?C\s*LINE NUMBER:\s*(\d+)", re.IGNORECASE)
_VAR_RE = re.compile(r"A/?C\s*VARIABLE NUMBER:\s*(\S+)", re.IGNORECASE)
_REPORT_DATE_RE = re.compile(r"REPORT DATE:\s*(\S+)", re.IGNORECASE)
_AC_TSN_RE = re.compile(r"A/?C\s*TSN:\s*([\d.]+)", re.IGNORECASE)
_AC_CSN_RE = re.compile(r"A/?C\s*CSN:\s*([\d.]+)", re.IGNORECASE)

_HEADER_FIELDS = [
    "AIRCRAFT_REG", "AC_MODEL", "MFG_DATE", "MSN", "LINE_NUMBER",
    "VARIABLE_NUMBER", "REPORT_DATE", "AC_TSN", "AC_CSN",
]


def _col_for_x(x: float) -> str | None:
    for lo, hi, name in _COLUMNS:
        if lo <= x < hi:
            return name
    return None


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
    approach as occm_list_func_loc_scanned.py). A 15px threshold sits
    between this file's real within-row gaps and its real between-row gaps
    -- measured directly from consecutive top-to-top gaps on the real
    sample file's rendered pages."""
    if df.empty:
        return []
    df = df.sort_values(["top", "left"]).reset_index(drop=True)
    df["row_id"] = (df["top"].diff().fillna(0).abs() > 15).cumsum()
    groups = []
    for _, g in df.groupby("row_id"):
        g = g.sort_values("left")
        words = list(zip(g["left"], g["text"].astype(str)))
        groups.append((g["top"].mean(), words))
    groups.sort(key=lambda t: t[0])
    return [words for _, words in groups]


def _bucket_words(words: list[tuple[float, str]]) -> dict[str, list[str]]:
    buckets: dict[str, list[str]] = {name: [] for _, _, name in _COLUMNS}
    for left, text in words:
        if _NOISE_TOKEN_RE.match(text):
            continue
        name = _col_for_x(left)
        if name:
            buckets[name].append(text)
    return buckets


def _join(tokens: list[str]) -> str:
    return " ".join(tokens).strip(" |[]_-—–")


def _parse_header_meta(text: str, meta: dict) -> None:
    for pat, key in (
        (_REG_RE, "AIRCRAFT_REG"), (_MODEL_RE, "AC_MODEL"),
        (_MFG_DATE_RE, "MFG_DATE"), (_MSN_RE, "MSN"),
        (_LINE_RE, "LINE_NUMBER"), (_VAR_RE, "VARIABLE_NUMBER"),
        (_REPORT_DATE_RE, "REPORT_DATE"), (_AC_TSN_RE, "AC_TSN"),
        (_AC_CSN_RE, "AC_CSN"),
    ):
        if meta.get(key):
            continue
        m = pat.search(text)
        if m:
            meta[key] = m.group(1).upper() if key == "AIRCRAFT_REG" else m.group(1)


def _parse_line(words: list[tuple[float, str]], page_num: int,
                 header_meta: dict) -> dict | None:
    buckets = _bucket_words(words)
    full_text = " ".join(" ".join(v) for v in buckets.values()).upper()
    if any(marker in full_text for marker in _JUNK_MARKERS):
        return None
    part_number = _join(buckets["PART_NUMBER"])
    serial_number = _join(buckets["SERIAL_NUMBER"])
    if not part_number and not serial_number:
        return None

    rec = {
        "ATA": _join(buckets["ATA"]),
        "PART_NUMBER": part_number,
        "SERIAL_NUMBER": serial_number,
        "DESCRIPTION": _join(buckets["DESCRIPTION"]),
        "POSITION": _join(buckets["POSITION"]),
        "INSTALL_DATE": _join(buckets["INSTALL_DATE"]),
        "TSN": _join(buckets["TSN"]),
        "CSN": _join(buckets["CSN"]),
        "_page": page_num,
    }
    rec.update(header_meta)
    return rec


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback (see
    sheet_types/occm.py) -- this variant's known source file has no text
    layer at all, so it can never be found through the normal pdfplumber
    head-text match.

    Anchors on the report's own title-line phrase, which OCRs reliably even
    at this cheap pass (confirmed directly on the real sample file).
    Checked directly (grep across every SIGNATURES list in
    sheet_types/{occm,ht,llp}.py and every existing occm_variants file):
    no other module's own SIGNATURES/ocr_detect anchor contains "AIRFRAME"
    combined with "COMPONENT LIST", nor is this phrase a substring of (nor
    does it contain) any of them.
    """
    try:
        img = await render_page(pdf_path, 0, dpi=300)
        w, h = img.size
        crop = img.crop((0, 0, w, int(h * 0.15)))
        text = (await ocr_text(crop, psm=6)).upper()
        return "COMPONENT LIST" in text and "OCCM" in text and "AIRFRAME" in text
    except Exception:
        return False


async def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    header_meta = {k: "" for k in _HEADER_FIELDS}
    n_pages = await page_count(pdf_path)
    for page_index in range(n_pages):
        img = await render_page(pdf_path, page_index, dpi=300)
        if not header_meta["MSN"]:
            w, h = img.size
            crop = img.crop((0, 0, w, int(h * 0.15)))
            header_text = await ocr_text(crop, psm=6)
            _parse_header_meta(header_text, header_meta)
        words = await ocr_words(img, psm=11, min_conf=-1)
        df = _words_to_df(words)
        for line_words in _group_lines(df):
            rec = _parse_line(line_words, page_index + 1, header_meta)
            if rec is not None:
                records.append(rec)
    return records
