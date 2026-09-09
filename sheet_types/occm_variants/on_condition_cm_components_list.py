"""On Condition, Condition Monitoring Components List -- scanned, no text
layer, OCR required throughout.

Confirmed on a real corpus sample file (single page; 0 extractable chars via
pdfplumber -- a straight scan, no embedded text layer at all), so this
module renders the page(s) and OCRs them directly via the async OCR bridge
(`shared/ocr_bridge.py`), the same approach as this package's other
scanned-only OCCM variants (e.g. `componentes_oc_cm.py`,
`msn_occm_list_scanned.py`).

Title line (confirmed directly, OCRs cleanly at a plain whole-page pass)::

    ON CONDITION, CONDITION MONITORING COMPONENTS LIST

Header block, directly below the title (confirmed directly; OCRs reliably
once the header band is cropped and upscaled ~2x before OCR -- a whole-page
pass smears a small logo/decoration sitting to the right of this block into
the surrounding text, but the header line itself still resolves cleanly at
that narrower crop)::

    A/C <type> MSN <msn> REGISTER <reg>
    TSN <n> CSN <n>
    DATE AS <date>

("A/C" is confirmed to OCR consistently as "AIC" on the real sample file --
the forward slash misread as a capital I -- so the header regexes below
tolerate both spellings.) These six fields (AIRCRAFT_TYPE, MSN,
AIRCRAFT_REG, HEADER_TSN, HEADER_CSN, REPORT_DATE) are parsed once from
whichever page they're first recovered from and stamped onto every row, per
this package's usual header-plus-body OCCM convention.

Column header row (confirmed directly against the real rendered page, badly
garbled at every PSM tried but still resolvable via the position of its
recognisable fragments -- "DESCRIPTION", "POS (ZONE)", "PART NUMBER",
"SERIAL NUMBER", "TSN", "CSN" all land at X positions that line up with a
data row's own PART_NUMBER/SERIAL_NUMBER/TSN/CSN cells; two more label
fragments -- one over the ATA/item-number pair, one over the install-date
column, one over the trailing remark column -- OCR too corrupted to read as
words but still confirm a real column sits at that position). Column order,
left to right::

    ATA | ITEM NUMBER | DESCRIPTION | POS (ZONE) | PART NUMBER |
    SERIAL NUMBER | INSTALLED DATE | TSN | CSN | REMARK

A data row's tokens, in column order (genericized, real corpus values
replaced with placeholders)::

    <ata> | <item number> | <description text> | <pos/zone code> |
    <part number> | <serial number> | <dd-mon-yy> | <tsn figure> |
    <csn figure> | SINCE DELIVERY

ATA and ITEM NUMBER are confirmed printed as two separate cells that OCR
frequently fuses into one unbroken digit run with no visible gap (e.g. a
genuine "<ata><item number>" pairing renders as a single word box covering
both cells) -- confirmed directly across many rows of the real sample file.
ITEM NUMBER's own digit count is confirmed to be a stable 7 digits across
every row read; ATA a stable 2 digits. When the two land in the same word
box, the leading 2 digits are split off as ATA (only when they fall in the
plausible ATA-chapter range) and the remaining digits kept as ITEM_NUMBER,
matching the same fused-cell handling `componentes_oc_cm.py` uses for its
own compound CONFIG_SLOT column.

REMARK is confirmed to carry more than one distinct literal value across
the real sample file's rows (both a delivery-basis marker and a
certificate-basis marker, each followed by its own reference figure on the
certificate rows) -- kept as free text rather than a constrained enum for
that reason.

OCR quality on this file's data grid is confirmed poor for the pure-numeric
cells specifically (TSN/CSN/date figures show frequent single-digit
substitutions run to run, confirmed directly by comparing the same
aircraft-level TSN/CSN figures the header block prints once cleanly against
their per-row re-prints elsewhere on the page, which vary slightly OCR pass
to OCR pass) -- this is a genuinely hard scan for those columns, not a
design shortcut, so TSN/CSN/INSTALL_DATE/PART_NUMBER/SERIAL_NUMBER are all
kept fairly permissive (`allow_empty`, loosely-shaped patterns) per this
package's soft-validation convention (see `shared/aviation_rules.py`). A
meaningful `_issues` flag rate on this variant's output is expected and
acceptable given the source scan quality.

Word-bucketing approach: each page's words are read via `ocr_words()`
(word-level bounding boxes, `min_conf=-1` since real cells here score under
Tesseract's default conf>30 filter on a meaningful fraction of rows),
grouped into text-lines by Y-coordinate (same geometric-clustering
technique as `occm_report_scanned.py` / `componentes_oc_cm.py`), then
bucketed into columns by X-position using column boundaries measured
directly from word positions on the real sample file's own data rows (kept
as fractions of page width, the same convention `componentes_oc_cm.py`
uses, so minor page-to-page scan-size variation doesn't shift the
buckets).
"""
from __future__ import annotations
import re

import pandas as pd

from sheet_types.occm_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, ocr_words, page_count

NAME = "On Condition, Condition Monitoring Components List"

# Deliberately empty -- the known source file has no text layer at all (see
# module docstring). Detection happens via ocr_detect() below.
SIGNATURES = []

CANONICAL_COLUMNS = [
    "ATA",
    "ITEM_NUMBER",
    "DESCRIPTION",
    "POS_ZONE",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "INSTALL_DATE",
    "TSN",
    "CSN",
    "REMARK",
    # Header metadata -- parsed once (first page it's recoverable on) and
    # stamped onto every row.
    "AIRCRAFT_TYPE",
    "MSN",
    "AIRCRAFT_REG",
    "HEADER_TSN",
    "HEADER_CSN",
    "REPORT_DATE",
]

# Broad date shape -- dd-Mon-yy(yy), separators kept loose and month token
# allowed 2-4 letters since OCR of the Spanish 3-letter month abbreviations
# seen on this file (e.g. the January abbreviation) is confirmed to
# sometimes drop/gain a letter.
_DATE_PATTERN = r"^\d{1,2}[-/. ]?[A-Za-z]{2,4}[-/. ]?\d{2,4}$"
_DATE_RULE = {"pattern": _DATE_PATTERN, "allow_empty": True}

# TSN/CSN figures -- decimal point confirmed to sometimes drop entirely on
# this file's per-row re-prints (a genuine "<n>.<nn>" figure OCR'd as one
# unbroken digit run), so the decimal suffix is optional rather than
# required.
_AMOUNT_RULE = {"pattern": r"^\d{3,8}(?:\.\d{1,2})?$", "allow_empty": True}
_COUNT_RULE = {"pattern": r"^\d{3,8}$", "allow_empty": True}

_OVERRIDES = {
    "ITEM_NUMBER": {"pattern": r"^\d{5,8}$", "allow_empty": True},
    "POS_ZONE": {"pattern": r"^[A-Z0-9]{1,6}$", "uppercase": True, "allow_empty": True},
    # Global PART_NUMBER/SERIAL_NUMBER rules already carry char_map/
    # sequence_map/pattern from shared/aviation_rules.py -- just relax to
    # allow_empty given this file's confirmed OCR quality on these cells.
    "PART_NUMBER": {"allow_empty": True},
    "SERIAL_NUMBER": {"allow_empty": True},
    "INSTALL_DATE": _DATE_RULE,
    "TSN": _AMOUNT_RULE,
    "CSN": _COUNT_RULE,
    "REMARK": {"uppercase": True, "allow_empty": True},
    # Header metadata -- each value is a single figure parsed once and
    # stamped identically on every row of the file, so a tight pattern here
    # would either flag every single row over one OCR misread in one
    # place, or none at all -- neither is a useful per-row signal (same
    # reasoning as this package's other header-plus-body OCCM variants,
    # e.g. `msn_occm_list_scanned.py`'s own header fields).
    "AIRCRAFT_TYPE": {"pattern": r"^[A-Z0-9]{2,4}-\d{2,4}$", "uppercase": True,
                       "allow_empty": True},
    "MSN": {"pattern": r"^\d{2,6}$", "allow_empty": True},
    "AIRCRAFT_REG": {"pattern": r"^[A-Z0-9]{4,8}$", "uppercase": True,
                      "allow_empty": True},
    "HEADER_TSN": _AMOUNT_RULE,
    "HEADER_CSN": _COUNT_RULE,
    "REPORT_DATE": _DATE_RULE,
}
RULES = merged_rules(_OVERRIDES)

# Column X-boundaries (as a fraction of page width), measured directly from
# word positions on the real sample file's own data rows at 300dpi (page
# width 3312px there) -- kept as fractions rather than absolute px per this
# package's usual convention (see `componentes_oc_cm.py`) so minor
# page-to-page scan-size variation doesn't shift the buckets.
_COLUMN_FRACS = [
    (0.000, 0.0483, "ATA"),
    (0.0483, 0.1359, "ITEM_NUMBER"),
    (0.1359, 0.3170, "DESCRIPTION"),
    (0.3170, 0.3774, "POS_ZONE"),
    (0.3774, 0.4891, "PART_NUMBER"),
    (0.4891, 0.5978, "SERIAL_NUMBER"),
    (0.5978, 0.6642, "INSTALL_DATE"),
    (0.6642, 0.7276, "TSN"),
    (0.7276, 0.8002, "CSN"),
    (0.8002, 1.000, "REMARK"),
]
# DESCRIPTION and REMARK are genuine free text and are joined with spaces;
# every other column is a compact code/value with no legitimate internal
# space (same convention as componentes_oc_cm.py / occm_list_func_loc_scanned.py).
_JOIN_WITH_SPACE = {"DESCRIPTION", "REMARK"}

_BORDER_RE = re.compile(r"[|\[\]<>=~()`*\"'«»‘’“”–—_]+")
_SEP_RUN_RE = re.compile(r"_{2,}|\.{3,}|-{3,}")
_EDGE_STRIP = " _-|[]=~.\"'"

# Real PART_NUMBER/SERIAL_NUMBER values on this file are digit-heavy; the
# repeated column-header row's own cells never carry a run this long --
# doubles as the header/data-row filter (same convention as
# occm_report_scanned.py / componentes_oc_cm.py).
_DIGIT_RUN_RE = re.compile(r"\d{3,}")

# ATA chapters plausible for this document class (matches the global ATA
# rule's own int_range in shared/aviation_rules.py).
_ATA_RANGE = (20, 83)


def _clean_bucket(text: str) -> str:
    s = _SEP_RUN_RE.sub(" ", _BORDER_RE.sub(" ", text))
    return " ".join(s.split()).strip(_EDGE_STRIP)


def _split_ata_item_number(ata_text: str, item_text: str) -> tuple[str, str]:
    """Recover ATA / ITEM_NUMBER from their own buckets, handling the fused
    single-word-box case (see module docstring) where the whole
    "<ata><item number>" run lands entirely in one bucket."""
    ata_digits = re.sub(r"\D", "", ata_text)
    item_digits = re.sub(r"\D", "", item_text)

    if len(ata_digits) == 2 and _ATA_RANGE[0] <= int(ata_digits) <= _ATA_RANGE[1]:
        return ata_digits, item_digits

    # Fused: the leading 2 digits of whichever bucket carries the longer
    # digit run are the ATA chapter, the rest is the item number.
    combined = ata_digits + item_digits if ata_digits else item_digits
    if len(combined) >= 2:
        head = combined[:2]
        if _ATA_RANGE[0] <= int(head) <= _ATA_RANGE[1]:
            return head, combined[2:]
    return ata_digits[:2], item_digits or combined


def _words_to_df(words: list[dict]) -> pd.DataFrame:
    cols = ["left", "top", "width", "height", "conf", "text"]
    df = pd.DataFrame(words, columns=cols) if words else pd.DataFrame(columns=cols)
    if not df.empty:
        df = df.dropna(subset=["text"])
        df = df[df["text"].astype(str).str.strip() != ""]
    return df


def _bucket_words_by_column(df: pd.DataFrame, page_width: int) -> dict[str, list[tuple[float, float, str]]]:
    """Bucket every word into its column by X-center, keeping each word's
    own (top, left, text) rather than collapsing to text only -- row
    membership is resolved afterwards via the ATA/ITEM_NUMBER anchors (see
    `_find_row_anchors`/`_assign_rows` below), not by a blind whole-row
    Y-clustering pass. A first attempt at this module used a single
    Y-clustering threshold across every word on the page (same technique
    `componentes_oc_cm.py` uses), but is confirmed directly to
    mis-merge several real rows together once row spacing gets tight/
    uneven further down the real sample file's page (rows with overlapping
    per-word Y ranges -- caused by a handful of oversized/duplicated OCR
    word boxes -- landed in the same cluster despite being genuinely
    different rows, producing a handful of records with two or three rows'
    worth of digits concatenated together). Anchoring on ATA/ITEM_NUMBER
    instead (confirmed to carry a clean digit run on very nearly every row)
    is the same general row-anchoring technique `msn_occm_list_scanned.py`
    uses (there anchored on its own file's ATA column alone) to sidestep
    an unreliable whole-row Y-clustering pass, though that module's own
    root cause is confirmed different from this one (a wide/thin crop
    aspect ratio issue, per its own docstring) -- both land on the same
    fix for the same class of symptom."""
    bounds = [(lo * page_width, hi * page_width, name) for lo, hi, name in _COLUMN_FRACS]
    buckets: dict[str, list[tuple[float, float, str]]] = {name: [] for _, _, name in _COLUMN_FRACS}
    for _, r in df.iterrows():
        center = r["left"] + r["width"] / 2
        text = str(r["text"])
        for lo, hi, name in bounds:
            if lo <= center < hi:
                buckets[name].append((r["top"], r["left"], text))
                break
    for name in buckets:
        buckets[name].sort(key=lambda t: t[0])
    return buckets


# A real row's ATA+ITEM_NUMBER cell(s) always carry at least a 2-digit run
# (see module docstring); the column-header row's own garbled label
# fragments in this same X-range never do, so this doubles as the anchor
# discriminator.
_ANCHOR_DIGITS_RE = re.compile(r"\d{2,}")
# Row pitch on the real sample file is confirmed to run ~40-70px @ 300dpi
# (uneven -- varies with how many description words wrap); candidate
# anchor tops within 15px of each other are the same row's own ATA/
# ITEM_NUMBER pair (split across two word boxes) rather than two distinct
# rows.
_ANCHOR_MERGE_PX = 15
# Half the smallest real row pitch seen -- wide enough that a genuine
# ATA/ITEM_NUMBER pair (or a wrapped second line of the same row) still
# lands within tolerance of its own row's anchor, narrow enough that it
# never bleeds into a neighboring row.
_ANCHOR_TOLERANCE_PX = 22


def _find_row_anchors(ata_words: list[tuple[float, float, str]],
                       item_words: list[tuple[float, float, str]]) -> list[float]:
    """One anchor top per real data row, built from the ATA/ITEM_NUMBER
    column's own words (see module docstring)."""
    tops = sorted(
        top for top, _, text in ata_words + item_words
        if _ANCHOR_DIGITS_RE.search(text)
    )
    anchors: list[float] = []
    group: list[float] = []
    for top in tops:
        if group and top - group[-1] > _ANCHOR_MERGE_PX:
            anchors.append(sum(group) / len(group))
            group = []
        group.append(top)
    if group:
        anchors.append(sum(group) / len(group))
    return anchors


def _nearest_anchor_idx(top: float, anchors: list[float]) -> int | None:
    best_idx, best_dist = None, None
    for i, a in enumerate(anchors):
        d = abs(top - a)
        if best_dist is None or d < best_dist:
            best_idx, best_dist = i, d
    if best_idx is not None and best_dist <= _ANCHOR_TOLERANCE_PX:
        return best_idx
    return None


def _assign_rows(column_words: dict[str, list[tuple[float, float, str]]],
                  anchors: list[float]) -> list[dict[str, list[tuple[float, str]]]]:
    rows: list[dict[str, list[tuple[float, str]]]] = [
        {name: [] for name in column_words} for _ in anchors
    ]
    for name, words in column_words.items():
        for top, left, text in words:
            idx = _nearest_anchor_idx(top, anchors)
            if idx is not None:
                rows[idx][name].append((left, text))
    for row in rows:
        for name in row:
            row[name].sort(key=lambda t: t[0])
    return rows


def _build_record(row: dict[str, list[tuple[float, str]]], page_num: int,
                   header_meta: dict) -> dict | None:
    buckets = {}
    for name, toks in row.items():
        texts = [t for _, t in toks]
        joined = " ".join(texts) if name in _JOIN_WITH_SPACE else "".join(texts)
        buckets[name] = _clean_bucket(joined)

    part_number = buckets["PART_NUMBER"]
    serial_number = buckets["SERIAL_NUMBER"]
    description = buckets["DESCRIPTION"]
    if not description:
        return None
    # Filters out the repeated column-header row and other non-data noise
    # (same convention as occm_report_scanned.py / componentes_oc_cm.py): a
    # real row's PN or SN always carries a real digit run, the header
    # cells never do.
    if not (_DIGIT_RUN_RE.search(part_number) or _DIGIT_RUN_RE.search(serial_number)):
        return None

    ata, item_number = _split_ata_item_number(buckets["ATA"], buckets["ITEM_NUMBER"])

    rec = {
        "ATA": ata,
        "ITEM_NUMBER": item_number,
        "DESCRIPTION": description,
        "POS_ZONE": buckets["POS_ZONE"],
        "PART_NUMBER": part_number,
        "SERIAL_NUMBER": serial_number,
        "INSTALL_DATE": buckets["INSTALL_DATE"],
        "TSN": buckets["TSN"],
        "CSN": buckets["CSN"],
        "REMARK": buckets["REMARK"],
        "_page": page_num,
    }
    rec.update(header_meta)
    return rec


# --- Header metadata parsing --------------------------------------------
# "A/C" is confirmed to OCR consistently as "AIC" on the real sample file
# (see module docstring), so these tolerate both spellings.
_TYPE_RE = re.compile(r"A[/I]?C\s+([A-Z0-9]{2,4}-\d{2,4})", re.IGNORECASE)
_MSN_RE = re.compile(r"\bMSN\s+(\d{2,6})\b", re.IGNORECASE)
_REG_RE = re.compile(r"REGISTER\s+([A-Z0-9]{4,8})", re.IGNORECASE)
_TSN_RE = re.compile(r"\bTSN\s+([\d.]{3,10})", re.IGNORECASE)
_CSN_RE = re.compile(r"\bCSN\s+(\d{3,8})", re.IGNORECASE)
_DATE_AS_RE = re.compile(r"DATE\s+AS\s+(\d{1,2}[-/. ]?[A-Za-z]{2,4}[-/. ]?\d{2,4})",
                          re.IGNORECASE)

_HEADER_FIELDS = ["AIRCRAFT_TYPE", "MSN", "AIRCRAFT_REG", "HEADER_TSN",
                  "HEADER_CSN", "REPORT_DATE"]


def _parse_header_text(text: str, meta: dict) -> None:
    for pat, key in (
        (_TYPE_RE, "AIRCRAFT_TYPE"),
        (_MSN_RE, "MSN"),
        (_REG_RE, "AIRCRAFT_REG"),
        (_TSN_RE, "HEADER_TSN"),
        (_CSN_RE, "HEADER_CSN"),
        (_DATE_AS_RE, "REPORT_DATE"),
    ):
        if meta.get(key):
            continue
        m = pat.search(text)
        if m:
            meta[key] = m.group(1).upper()


def _header_incomplete(header_meta: dict) -> bool:
    return not all(header_meta.values())


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback (see
    sheet_types/occm.py) -- this variant's SIGNATURES can never match
    through the normal pdfplumber text-extract path since the known source
    file has no text layer at all.

    Anchors on the report's own title-line phrase ("ON CONDITION," followed
    by "CONDITION MONITORING COMPONENTS" and ending in "LIST"), which OCRs
    reliably even at this cheap pass. Checked directly (grep across every
    SIGNATURES list in sheet_types/{occm,ht,llp}.py and every existing
    occm_variants/ht_variants/llp_variants file, this batch's siblings
    included): this exact phrase, with the leading "ON CONDITION," comma
    and the trailing "LIST" (not "STATUS"), appears nowhere else -- in
    particular on_condition_monitoring_components.py's own title phrase
    ("ON CONDITION MONITORING COMPONENTS", no leading comma, no trailing
    "LIST") and condition_monitoring_components_status.py's own title
    phrase ("CONDITION MONITORING COMPONENTS STATUS", no leading "ON",
    trailing "STATUS" not "LIST") both differ from this one in both
    directions.
    """
    try:
        img = await render_page(pdf_path, 0, dpi=300)
        w, h = img.size
        crop = img.crop((0, 0, w, int(h * 0.05)))
        text = (await ocr_text(crop, psm=6)).upper()
        return ("ON CONDITION," in text and "CONDITION MONITORING COMPONENTS" in text
                and "LIST" in text)
    except Exception:
        return False


async def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    header_meta = {k: "" for k in _HEADER_FIELDS}
    n_pages = await page_count(pdf_path)
    for page_index in range(n_pages):
        img = await render_page(pdf_path, page_index, dpi=300)
        w, h = img.size
        if _header_incomplete(header_meta):
            # Narrow crop over the header block (title line excluded),
            # upscaled ~2x -- see module docstring on why a whole-page pass
            # smears the small logo/decoration next to this block into the
            # surrounding text. Confirmed directly: including even a
            # sliver of the title line's own pixels in this crop is enough
            # to flip a single MSN digit (Tesseract's block segmentation
            # shifting slightly), while starting the crop just below the
            # title reads that digit correctly and consistently.
            crop = img.crop((0, int(h * 0.03), w, int(h * 0.085)))
            crop = crop.resize((crop.width * 2, crop.height * 2))
            header_text = await ocr_text(crop, psm=6)
            _parse_header_text(header_text, header_meta)

        words = await ocr_words(img, psm=6, min_conf=-1)
        df = _words_to_df(words)
        column_words = _bucket_words_by_column(df, w)
        anchors = _find_row_anchors(column_words["ATA"], column_words["ITEM_NUMBER"])
        for row in _assign_rows(column_words, anchors):
            rec = _build_record(row, page_index + 1, header_meta)
            if rec is not None:
                records.append(rec)
    return records
