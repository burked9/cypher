"""On Condition Components List -- T.T./T.C. header variant, scanned, no
text layer, OCR required throughout.

Confirmed on a real corpus sample file (multi-page, 0 extractable chars via
pdfplumber on every single page sampled -- a straight scan, no embedded text
layer at all anywhere in the document), so this module renders each page and
OCRs it directly via the async OCR bridge (`shared/ocr_bridge.py`), the same
approach as this package's other scanned-only OCCM variants (e.g.
`on_condition_cm_components_list.py`, `componentes_oc_cm.py`).

Title line (confirmed directly, OCRs cleanly at a plain whole-page pass)::

    ON CONDITION COMPONENTS LIST

This is deliberately a DIFFERENT title phrase from
`on_condition_cm_components_list.py`'s own known source file, which reads
"ON CONDITION, CONDITION MONITORING COMPONENTS LIST" (leading comma, extra
"CONDITION MONITORING" insert, checked directly against this module's own
sample -- neither phrase is a substring of the other). `detect_variant()`
was run against this module's own known sample file before it existed and
returned "Unknown" (no existing variant's SIGNATURES or ocr_detect() anchor
matched), confirming this is genuinely a new format rather than a
duplicate.

Header block, directly below the title (confirmed directly)::

    A/C <type> MSN <msn> REGISTER <reg>
    T.T. <n> T.C. <n>

("A/C" is confirmed to OCR consistently as "AIC" on the real sample file --
the forward slash misread as a capital I -- so the header regex tolerates
both spellings, same convention as `on_condition_cm_components_list.py`.)
Note this header uses "T.T." (total time) / "T.C." (total cycles) labels,
NOT "TSN"/"CSN" -- confirmed directly, distinct from
`on_condition_cm_components_list.py`'s own header block, which uses "TSN"/
"CSN" and an additional "DATE AS" report-date field this module's own
sample file does not carry anywhere on its header/title page. These four
fields (AIRCRAFT_TYPE, MSN, AIRCRAFT_REG, HEADER_TT, HEADER_TC) are parsed
once from whichever page they're first recovered from and stamped onto
every row, per this package's usual header-plus-body OCCM convention.

Column header row (confirmed directly against the real rendered page, badly
garbled at a plain whole-page OCR pass but resolvable via a narrow cropped +
2x-upscaled OCR pass over just that band)::

    ATA | DESCRIPTION | PART NUMBER | SERIAL NUMBER | POS | TSN | CSN |
    INSTALL DATE | REMARKS

Column order confirmed via that cropped pass reading the label fragments
"ATA DESCRIPTION PARTNUMBER | SERIALNUMBER | Pos | TSN CSN ... REMARKS" in
that left-to-right order. This is a 9-column layout with NO separate
item-number column and NO zone sub-field on POS -- confirmed directly
distinct from `on_condition_cm_components_list.py`'s own 10-column layout
(ATA | ITEM_NUMBER | DESCRIPTION | POS (ZONE) | PART NUMBER |
SERIAL NUMBER | INSTALLED DATE | TSN | CSN | REMARK), which additionally
carries an ITEM_NUMBER column and labels its own position column "POS
(ZONE)" rather than the bare "POS" confirmed here.

A data row's tokens, in column order (genericized, real corpus values
replaced with placeholders)::

    <ata> | <description text> | <part number> | <serial number> |
    <pos code> | <tsn figure> | <csn figure> | <dd-mon-yy> | SINCE DELIVERY

POS is confirmed to carry short alphanumeric codes on this file (a
recurring literal token that OCRs as roughly "ONT", alongside plain
3-digit numeric codes) -- kept as a loose alphanumeric pattern rather than
a constrained enum, same convention as `on_condition_cm_components_list.py`'s
own POS_ZONE column.

DESCRIPTION is confirmed to render as OCR-fused single words with no
internal space recoverable (e.g. a genuine "UNIDIRECTIONAL VALVE" two-word
description lands as one unbroken "UNIDIRECTIONALVALVE" word box) --
kept as free text, spaces re-joined from whatever word boxes land in the
column regardless, since no reliable space-recovery signal exists in the
raw OCR word boxes here.

PART_NUMBER is confirmed to sometimes split across two word boxes within
its own column (e.g. a short alpha prefix token immediately followed by
the main alphanumeric body, both still landing inside the PART_NUMBER
column's X-range) -- these are simply concatenated in column order along
with every other token that lands in that bucket, same general "bucket by
X-position, join whatever lands there" approach every other OCR-only OCCM
variant in this package uses; no attempt is made to guess which of several
word boxes is the "real" part number when more than one lands in the
bucket (per this package's "never guess a wrong split" convention -- see
`on_condition_cm_components_list.py`'s own docstring on the same point).

REMARK is confirmed to carry more than one distinct literal value across
the real sample file's rows (a delivery-basis marker, a certificate-basis
marker each with its own reference figure, a logbook marker, and a
service-tag marker) -- kept as free text rather than a constrained enum
for that reason, same convention as `on_condition_cm_components_list.py`.

OCR quality on this file's data grid is confirmed poor for the pure-numeric
cells specifically (TSN/CSN figures show frequent single/multi-digit
substitutions and dropped decimal points run to row, confirmed directly by
comparing the header block's own once-printed T.T./T.C. figures against
their per-row re-prints elsewhere on the page, which vary row to row) --
this is a genuinely hard scan for those columns, not a design shortcut, so
TSN/CSN/INSTALL_DATE/PART_NUMBER/SERIAL_NUMBER/POS are all kept fairly
permissive (`allow_empty`, loosely-shaped patterns) per this package's
soft-validation convention (see `shared/aviation_rules.py`). A meaningful
`_issues` flag rate on this variant's output is expected and acceptable
given the source scan quality.

A real person's name is confirmed printed once, in a signature block below
the final data row on the last page of the real sample file (a
"to the best of our knowledge..." attestation line followed by a
printed name and job title). This text sits well below every real data
row's Y-position and carries no ATA-column digit run at all, so it is
never picked up by the row-anchor logic below (anchored purely on the
ATA column's own digit runs -- see `_find_row_anchors`) and never lands in
any extracted field. Confirmed directly: this module's extract() only
ever emits rows anchored on a genuine ATA-column digit run, and the
signature block carries none.

Word-bucketing approach: each page's words are read via `ocr_words()`
(word-level bounding boxes, `min_conf=-1` since real cells here score under
Tesseract's default conf>30 filter on a meaningful fraction of rows),
bucketed into columns by X-position using column boundaries measured
directly from word positions on the real sample file's own data rows
(kept as fractions of page width, same convention as
`on_condition_cm_components_list.py`, so minor page-to-page scan-size
variation doesn't shift the buckets), then grouped into rows by anchoring
on the ATA column's own digit runs (confirmed to carry a clean 2-digit
run on very nearly every row) -- the same general row-anchoring technique
`on_condition_cm_components_list.py` uses for its own ATA+ITEM_NUMBER pair,
simplified here to a single anchor column since this file's own layout has
no second fused-digit column to disambiguate against.
"""
from __future__ import annotations
import re

import pandas as pd

from sheet_types.occm_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, ocr_words, page_count

NAME = "On Condition Components List (T.T./T.C. Header)"

# Deliberately empty -- the known source file has no text layer at all (see
# module docstring). Detection happens via ocr_detect() below.
SIGNATURES = []

CANONICAL_COLUMNS = [
    "ATA",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "POS",
    "TSN",
    "CSN",
    "INSTALL_DATE",
    "REMARK",
    # Header metadata -- parsed once (first page it's recoverable on) and
    # stamped onto every row.
    "AIRCRAFT_TYPE",
    "MSN",
    "AIRCRAFT_REG",
    "HEADER_TT",
    "HEADER_TC",
]

# Broad date shape -- dd-Mon-yy(yy), separators kept loose and month token
# allowed 2-4 letters since OCR of the Spanish 3-letter month abbreviations
# seen on this file (e.g. the April/August/December abbreviations) is
# confirmed to sometimes drop/gain a letter.
_DATE_PATTERN = r"^\d{1,2}[-/. ]?[A-Za-z]{2,4}[-/. ]?\d{2,4}$"
_DATE_RULE = {"pattern": _DATE_PATTERN, "allow_empty": True}

# TSN figures -- decimal point confirmed to sometimes drop entirely on this
# file's per-row re-prints (a genuine "<n>.<nn>" figure OCR'd as one
# unbroken digit run), so the decimal suffix is optional rather than
# required.
_AMOUNT_RULE = {"pattern": r"^\d{3,8}(?:\.\d{1,2})?$", "allow_empty": True}
_COUNT_RULE = {"pattern": r"^\d{2,8}$", "allow_empty": True}

_OVERRIDES = {
    "POS": {"pattern": r"^[A-Z0-9]{1,6}$", "uppercase": True, "allow_empty": True},
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
    # e.g. `on_condition_cm_components_list.py`'s own header fields).
    "AIRCRAFT_TYPE": {"pattern": r"^[A-Z0-9]{2,4}-\d{2,4}$", "uppercase": True,
                       "allow_empty": True},
    "MSN": {"pattern": r"^\d{2,6}$", "allow_empty": True},
    # Loose overall shape (4-9 alnum/hyphen chars) rather than a fixed
    # prefix-length split either side of an optional hyphen -- real
    # registrations on this document class are confirmed to appear both
    # with a short hyphenated prefix and without one, so a fixed split
    # would reject the shorter, legitimate hyphenated form.
    "AIRCRAFT_REG": {"pattern": r"^[A-Z0-9-]{4,9}$",
                      "uppercase": True, "allow_empty": True},
    "HEADER_TT": _AMOUNT_RULE,
    "HEADER_TC": _COUNT_RULE,
}
RULES = merged_rules(_OVERRIDES)

# Column X-boundaries (as a fraction of page width), measured directly from
# word positions on the real sample file's own data rows at 300dpi (page
# width 3300px there) -- kept as fractions rather than absolute px per this
# package's usual convention (see `on_condition_cm_components_list.py`) so
# minor page-to-page scan-size variation doesn't shift the buckets.
_COLUMN_FRACS = [
    (0.000, 0.060, "ATA"),
    (0.060, 0.240, "DESCRIPTION"),
    (0.240, 0.460, "PART_NUMBER"),
    (0.460, 0.565, "SERIAL_NUMBER"),
    (0.565, 0.620, "POS"),
    (0.620, 0.685, "TSN"),
    (0.685, 0.750, "CSN"),
    (0.750, 0.835, "INSTALL_DATE"),
    (0.835, 1.000, "REMARK"),
]
# DESCRIPTION and REMARK are genuine free text and are joined with spaces;
# every other column is a compact code/value with no legitimate internal
# space (same convention as on_condition_cm_components_list.py).
_JOIN_WITH_SPACE = {"DESCRIPTION", "REMARK"}

_BORDER_RE = re.compile(r"[|\[\]<>=~()`*\"'«»‘’“”–—_]+")
_SEP_RUN_RE = re.compile(r"_{2,}|\.{3,}|-{3,}")
_EDGE_STRIP = " _-|[]=~.\"'"

# Real PART_NUMBER/SERIAL_NUMBER values on this file are digit-heavy; the
# repeated column-header row's own cells never carry a run this long --
# doubles as the header/data-row filter (same convention as
# on_condition_cm_components_list.py).
_DIGIT_RUN_RE = re.compile(r"\d{3,}")

# ATA chapters plausible for this document class (matches the global ATA
# rule's own int_range in shared/aviation_rules.py).
_ATA_RANGE = (20, 83)
_ATA_RE = re.compile(r"\b\d{2}\b")


def _clean_bucket(text: str) -> str:
    s = _SEP_RUN_RE.sub(" ", _BORDER_RE.sub(" ", text))
    return " ".join(s.split()).strip(_EDGE_STRIP)


def _extract_ata(ata_text: str) -> str:
    digits = re.sub(r"\D", "", ata_text)
    if len(digits) >= 2:
        head = digits[:2]
        if _ATA_RANGE[0] <= int(head) <= _ATA_RANGE[1]:
            return head
    return digits[:2]


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
    membership is resolved afterwards via the ATA column's own digit-run
    anchor (see `_find_row_anchors`/`_assign_rows` below), not by a blind
    whole-row Y-clustering pass, same reasoning as
    `on_condition_cm_components_list.py`'s own bucketing function (see its
    own docstring for the confirmed failure mode of a blind Y-clustering
    pass on this class of scan)."""
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


# A real row's ATA cell always carries a clean 2-digit run (see module
# docstring); the column-header row's own garbled label fragments in this
# same X-range never do, so this doubles as the anchor discriminator.
_ANCHOR_DIGITS_RE = re.compile(r"\d{2,}")
# Row pitch on the real sample file is confirmed to run ~40-70px @ 300dpi
# (uneven -- varies with how many description/part-number words wrap);
# candidate anchor tops within 15px of each other are treated as the same
# row (same tolerance `on_condition_cm_components_list.py` uses for its own
# ATA/ITEM_NUMBER anchor).
_ANCHOR_MERGE_PX = 15
_ANCHOR_TOLERANCE_PX = 22


def _find_row_anchors(ata_words: list[tuple[float, float, str]]) -> list[float]:
    """One anchor top per real data row, built from the ATA column's own
    words (see module docstring)."""
    tops = sorted(
        top for top, _, text in ata_words
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
    # (same convention as on_condition_cm_components_list.py): a real row's
    # PN or SN always carries a real digit run, the header cells never do.
    if not (_DIGIT_RUN_RE.search(part_number) or _DIGIT_RUN_RE.search(serial_number)):
        return None

    ata = _extract_ata(buckets["ATA"])

    rec = {
        "ATA": ata,
        "DESCRIPTION": description,
        "PART_NUMBER": part_number,
        "SERIAL_NUMBER": serial_number,
        "POS": buckets["POS"],
        "TSN": buckets["TSN"],
        "CSN": buckets["CSN"],
        "INSTALL_DATE": buckets["INSTALL_DATE"],
        "REMARK": buckets["REMARK"],
        "_page": page_num,
    }
    rec.update(header_meta)
    return rec


# --- Header metadata parsing --------------------------------------------
# "A/C" is confirmed to OCR consistently as "AIC" on the real sample file
# (see module docstring), so this tolerates both spellings.
_TYPE_RE = re.compile(r"A[/I]?C\s+([A-Z0-9]{2,4}-\d{2,4})", re.IGNORECASE)
_MSN_RE = re.compile(r"\bMSN\s+(\d{2,6})\b", re.IGNORECASE)
_REG_RE = re.compile(r"REGISTER\s+([A-Z0-9-]{4,9})", re.IGNORECASE)
_TT_RE = re.compile(r"\bT\.?\s?T\.?\s+([\d.]{3,10})", re.IGNORECASE)
_TC_RE = re.compile(r"\bT\.?\s?C\.?\s+(\d{2,8})", re.IGNORECASE)

_HEADER_FIELDS = ["AIRCRAFT_TYPE", "MSN", "AIRCRAFT_REG", "HEADER_TT", "HEADER_TC"]


def _parse_header_text(text: str, meta: dict) -> None:
    for pat, key in (
        (_TYPE_RE, "AIRCRAFT_TYPE"),
        (_MSN_RE, "MSN"),
        (_REG_RE, "AIRCRAFT_REG"),
        (_TT_RE, "HEADER_TT"),
        (_TC_RE, "HEADER_TC"),
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

    Anchors on the report's own title-line phrase ("ON CONDITION COMPONENTS
    LIST"), which OCRs reliably even at this cheap pass. Checked directly
    (grep across every SIGNATURES list in sheet_types/{occm,ht,llp}.py and
    every existing occm_variants/ht_variants/llp_variants file): this exact
    phrase appears nowhere else -- in particular
    `on_condition_cm_components_list.py`'s own title phrase adds a leading
    "ON CONDITION," comma and an extra "CONDITION MONITORING" insert not
    present here, and `occm_component_status_dual_basis.py`'s own title
    phrase ends in "REPORT" rather than "LIST" -- both differ from this
    one in both directions, and this bare phrase is not a substring of
    (nor contains) any other module's own SIGNATURES/ocr_detect anchor.
    """
    try:
        img = await render_page(pdf_path, 0, dpi=300)
        w, h = img.size
        # Confirmed directly: the title line's own baseline sits around 8-9%
        # of page height down on the real sample file (a wide top margin
        # above it) -- a crop stopping any earlier than that cuts the title
        # off entirely and OCRs empty/garbage instead.
        crop = img.crop((0, 0, w, int(h * 0.10)))
        text = (await ocr_text(crop, psm=6)).upper()
        return "ON CONDITION COMPONENTS LIST" in text
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
            # Crop over the header block (title line included -- excluding
            # it was tried first but is confirmed directly to make Tesseract
            # drop the T.T./T.C. line entirely at psm 6, a block-segmentation
            # quirk of this exact crop height, not a resolution problem),
            # upscaled ~2x. psm 4 (single column of variable-size text) is
            # confirmed directly to read this header block -- title, A/C
            # line, and T.T./T.C. line -- more reliably in one pass than
            # psm 6 (which is confirmed to drop either the A/C line or the
            # T.T./T.C. line depending on the exact crop height chosen, no
            # single crop height recovering all three lines at psm 6).
            crop = img.crop((0, int(h * 0.03), w, int(h * 0.14)))
            crop = crop.resize((crop.width * 2, crop.height * 2))
            header_text = await ocr_text(crop, psm=4)
            _parse_header_text(header_text, header_meta)

        words = await ocr_words(img, psm=6, min_conf=-1)
        df = _words_to_df(words)
        column_words = _bucket_words_by_column(df, w)
        anchors = _find_row_anchors(column_words["ATA"])
        for row in _assign_rows(column_words, anchors):
            rec = _build_record(row, page_index + 1, header_meta)
            if rec is not None:
                records.append(rec)
    return records
