"""COMPONENTES OC/CM — scanned, no text layer, OCR required throughout.

Confirmed on three real corpus files from the same document family (same
title/column layout, different aircraft) -- each a straight scan with 0
extractable chars on every page via pdfplumber, no embedded text layer at
all. Header block (bordered mini-table, repeats verbatim on every page)::

    <operator logo/name>                              COMPONENTES OC/CM
    AIRCRAFT | <reg> | DATE MANUFACTURER | <date> | DATE ENTERED SERVICES | <date>
    FLEET    | <family> | TOTAL HOURS | <n> | TOTAL CYCLES | <n>
    MSN      | <msn> | DT, MFL | <date>
    OWNER    | <operator> (<operator full name>)

...followed by a ruled data grid whose column-header row reads::

    CONFIG SLOT | PART NUMBER | SERIAL NUMBER | POSITION | DESCRIPTION |
    DATE INSTALL | TIME SINCE NEW | TIME SINCE INSTALLATION |
    CYCLE SINCE NEW | CYCLE SINCE INSTALLATION

Header metadata (AIRCRAFT_FAMILY, TOTAL_HOURS, TOTAL_CYCLES, MSN, MFG_DATE,
ENTERED_SERVICE_DATE, MFL_DATE) is parsed once -- from whichever page it
first OCRs cleanly on, matching this package's usual "keep trying while any
field is still missing" pattern -- and stamped onto every row. The
AIRCRAFT/OWNER row values themselves (registration, operator name) are
deliberately NOT captured into their own columns: this module's header spec
only calls for the seven fields above, and the operator/registration cells
would otherwise be free-text values with no validation anchor of their own.

The header block's absolute vertical position on the page is NOT constant
across files in this family (confirmed directly comparing the two real
files: an extra/missing sub-line above the column-header row shifts every
row below it by roughly one row's height) -- so the title/AIRCRAFT/FLEET/
MSN row crops are located per-page by their own label text
(`_locate_header_bands()`) rather than a single fixed set of page-fraction
constants, which only ever matched the first file seen. See that
function's docstring and `_HEADER_ROW_ANCHORS` below.

Whole-page `ocr_text()` on this file's data grid is confirmed unreliable
(digit/letter substitutions are severe enough that even a compound code's
own hyphens routinely disappear, e.g. a real "DD-DD-DD-DD-DDD" shaped
CONFIG SLOT was seen OCR'd with every hyphen dropped and several digits
misread as letters). The header mini-table OCRs far more cleanly than the
data grid, but even there a plain single whole-header OCR pass drops the
TOTAL CYCLES value outright on some pages (confirmed directly: the
Tesseract layout analyzer merges/misplaces that one cell often enough that
a single-block psm 4 pass over the full header silently omits it) -- so the
header is instead read one row-band at a time (`AIRCRAFT`/`FLEET`/`MSN` each
their own narrow horizontal crop), which recovers every field reliably on
the first page tested.

The data grid itself is read via `ocr_words()` (word-level bounding boxes,
`min_conf=-1` since real cells here score under Tesseract's default
conf>30 filter on a meaningful fraction of rows) + geometric line-clustering
by Y-coordinate (same technique as `occm_report_scanned.py` /
`occm_list_func_loc_scanned.py`), then an X-position column bucket per
line, using column boundaries measured directly from the real column-header
row's own ruled borders (detected as vertical runs of dark pixels, not
guessed from word positions) on the real sample file's first page, kept as
fractions of page width so minor page-to-page scan-size variation (seen
directly: page width varies by a few px from page to page in this same
file) doesn't shift the buckets.

CONFIG SLOT is a compound code, one per row, shaped::

    <ata>-<subchapter>-<code>-<seq>[-<suffix>]

e.g. (genericized) ``<ata>-<cc>-<code>-<seq>``. Confirmed directly across
several widely-separated pages of the real sample file: the leading 2-digit
group is a genuine ATA chapter, NOT a constant -- distinct values (each a
plausible ATA chapter number) were observed heading up rows on different
pages, each pairing with several different sub-codes across its own rows.
It is pulled into its own ATA column (matching this package's other
compound-code OCCM variants, `fl_compound_code_occm.py` and
`occm_list_func_loc_scanned.py`); unlike those two, nothing here is a
redundant cross-reference to the header (there is no tail/registration
prefix to drop), so CONFIG SLOT itself is kept verbatim as its own column
too, in addition to the derived ATA column, rather than being replaced by a
"rest of the code" remainder field.

Given the severity of the OCR quality issues described above, CONFIG SLOT,
POSITION, PART NUMBER and SERIAL NUMBER are all read with fairly permissive
(often unpatterned / `allow_empty`) validation rules -- this is a genuinely
hard scan, not a design shortcut, and a meaningful `_issues` flag rate on
this variant's output is expected. When ATA can't be recovered from a
row's own CONFIG SLOT text, it's left blank so
`occm.normalize_and_validate()`'s `forward_fill_ata()` post-process can
inherit it from the preceding row, the same safety net every other OCCM
variant in this package relies on for a missed chapter number.

Whole-page rotation, confirmed directly on the third real file in this
document family: unlike the first two real files (each already upright),
this one's entire scan is embedded rotated 90 degrees off true -- every
page checked (first, a middle, and the last) carries the same rotation,
consistent with a whole document fed through a scanner sideways rather
than a per-page artifact. The PDF's own page geometry (MediaBox) is
portrait on every page of all three real files regardless of the scanned
content's own true orientation, so the aspect-ratio check this package's
other rotation-handling OCCM variant uses (`occm_parts_compliance_status.py`
-- a landscape page rendering narrower-than-tall) can't tell a correctly
oriented file from a rotated one here; the embedded content itself has to
be read. `_detect_page_rotation()` below resolves this once per file, by
OCR-testing page 0's own title text (the same "COMPONENTES"/"OC/CM" anchor
`ocr_detect()` already relies on) across a small set of candidate
rotations and keeping whichever one the title is actually readable in;
that single per-file angle is then applied uniformly to every page's
render before any other OCR runs, rather than re-detected page by page
(confirmed consistent across the sampled pages above, and cheaper than a
full OCR-based check on every page of a scanned multi-page file).

TIME SINCE NEW / CYCLE SINCE NEW may read literally ``UNK`` in the source
(confirmed directly -- a real, printed value on rows where the "since new"
basis is not tracked for that unit, distinct from a blank/missing cell), so
that literal token is accepted as valid alongside the usual numeric shape
rather than flagged as corruption.
"""
from __future__ import annotations
import re

import pandas as pd

from sheet_types.occm_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, ocr_words, page_count

NAME = "COMPONENTES OC/CM"

# Deliberately empty -- the known source file has no text layer at all (see
# module docstring). Detection happens via ocr_detect() below.
SIGNATURES = []

CANONICAL_COLUMNS = [
    "ATA",
    "CONFIG_SLOT",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "POSITION",
    "DESCRIPTION",
    "INSTALL_DATE",
    "TIME_SINCE_NEW",
    "TIME_SINCE_INSTALL",
    "CYCLE_SINCE_NEW",
    "CYCLE_SINCE_INSTALL",
    # Header metadata -- parsed once (first page it's recoverable on) and
    # stamped onto every row.
    "AIRCRAFT_FAMILY",
    "TOTAL_HOURS",
    "TOTAL_CYCLES",
    "MSN",
    "MFG_DATE",
    "ENTERED_SERVICE_DATE",
    "MFL_DATE",
]

# Broad date shape shared by INSTALL_DATE and every header date field --
# dd-Mon-yy(yy), with the separators kept loose since OCR drops/garbles
# them inconsistently on this file (confirmed directly).
_DATE_PATTERN = r"^\d{1,2}[-/. ]?[A-Za-z]{3}[-/. ]?\d{2,4}$"
_DATE_RULE = {"pattern": _DATE_PATTERN, "allow_empty": True}

# Numeric-or-UNK shape shared by the four time/cycle columns -- see module
# docstring on the genuine "UNK" literal.
# NOTE: the leading run is `\d+` (not `\d{1,3}`) -- this file's own time/
# cycle figures are seen both comma-grouped (e.g. "<n>,<nnn>.<nn>") and,
# just as often, with the thousands separator dropped entirely by OCR (the
# same figure rendered as "<n><nnn>.<nn>" or "<n><nnn><nn>" with the decimal
# point lost too), confirmed directly across many rows -- a `\d{1,3}` cap
# would wrongly reject that second, equally genuine form as soon as its
# OCR'd digit run exceeds 3 characters ahead of any comma.
_AMOUNT_OR_UNK_RULE = {
    "pattern": r"^(?:\d+(?:,\d{3})*(?:\.\d+)?|UNK)$",
    "allow_empty": True,
}

_OVERRIDES = {
    # See module docstring -- OCR quality on this column is too poor to
    # enforce a strict shape; left unpatterned like occm_report_scanned.py
    # does for its own similarly-unreliable columns.
    "CONFIG_SLOT": {"allow_empty": True},
    "POSITION": {"allow_empty": True},
    "INSTALL_DATE": _DATE_RULE,
    "TIME_SINCE_NEW": _AMOUNT_OR_UNK_RULE,
    "TIME_SINCE_INSTALL": _AMOUNT_OR_UNK_RULE,
    "CYCLE_SINCE_NEW": _AMOUNT_OR_UNK_RULE,
    "CYCLE_SINCE_INSTALL": _AMOUNT_OR_UNK_RULE,
    "AIRCRAFT_FAMILY": {"pattern": r"^[A-Z0-9\-]{2,20}$", "uppercase": True,
                         "allow_empty": True},
    # Same comma-optional shape as _AMOUNT_OR_UNK_RULE above (this file's
    # own TOTAL HOURS/TOTAL CYCLES header cells are the same "sometimes
    # comma-grouped, sometimes not" figures, minus the "UNK" literal, which
    # is a per-row basis marker, not a valid aircraft-level total).
    "TOTAL_HOURS": {"pattern": r"^\d+(?:,\d{3})*(?:\.\d+)?$", "allow_empty": True},
    "TOTAL_CYCLES": {"pattern": r"^\d+(?:,\d{3})*$", "allow_empty": True},
    "MSN": {"pattern": r"^\d{2,6}$", "allow_empty": True},
    "MFG_DATE": _DATE_RULE,
    "ENTERED_SERVICE_DATE": _DATE_RULE,
    "MFL_DATE": _DATE_RULE,
}
RULES = merged_rules(_OVERRIDES)

# Column X-boundaries (as a fraction of page width), measured directly from
# the real column-header row's own ruled vertical borders (detected as
# columns of consistently-dark pixels across the header band, not guessed
# from word positions) on the real sample file's first page. Kept as
# fractions rather than absolute px since this same file's page width
# varies by a few px page to page (a scanning artifact, confirmed
# directly), and multiplied back out to px against each page's own
# rendered width below.
_COLUMN_FRACS = [
    (0.000, 0.099, "CONFIG_SLOT"),
    (0.099, 0.203, "PART_NUMBER"),
    (0.203, 0.310, "SERIAL_NUMBER"),
    (0.310, 0.416, "POSITION"),
    (0.416, 0.662, "DESCRIPTION"),
    (0.662, 0.723, "INSTALL_DATE"),
    (0.723, 0.779, "TIME_SINCE_NEW"),
    (0.779, 0.846, "TIME_SINCE_INSTALL"),
    (0.846, 0.909, "CYCLE_SINCE_NEW"),
    (0.909, 1.000, "CYCLE_SINCE_INSTALL"),
]
# DESCRIPTION is genuine free text and is joined with spaces; every other
# column is a compact code/value with no legitimate internal space (see
# occm_list_func_loc_scanned.py for the same convention).
_JOIN_WITH_SPACE = {"DESCRIPTION"}

_BORDER_RE = re.compile(r"[|\[\]<>=~()`*\"'«»‘’“”–—_]+")
_SEP_RUN_RE = re.compile(r"_{2,}|\.{3,}|-{3,}")
_EDGE_STRIP = " _-|[]=~.\"'"

# Real PART_NUMBER/SERIAL_NUMBER values on this file are digit-heavy; the
# repeated column-header row's own cells never carry a run this long --
# doubles as the header/data-row filter (same convention as
# occm_report_scanned.py).
_DIGIT_RUN_RE = re.compile(r"\d{3,}")
# ATA chapters plausible for this document class (matches the global ATA
# rule's own int_range in shared/aviation_rules.py).
_ATA_RANGE = (20, 83)
_AMOUNT_TOKEN_RE = re.compile(r"\d[\d,]*\.?\d*|UNK", re.IGNORECASE)


def _clean_bucket(text: str) -> str:
    s = _SEP_RUN_RE.sub(" ", _BORDER_RE.sub(" ", text))
    return " ".join(s.split()).strip(_EDGE_STRIP)


def _extract_ata(text: str) -> str:
    """Pull a plausible 2-digit ATA chapter out of a border/OCR-noise-prone
    CONFIG_SLOT bucket (see module docstring). Tries each digit run found,
    and each run's leading/trailing 2 digits (a fused border artifact or a
    misread hyphen commonly shifts an extra digit onto the real chapter
    number) -- the first candidate inside the plausible range wins. Returns
    "" when nothing plausible is found, so forward-fill can recover it from
    the preceding row instead of guessing."""
    for run in re.findall(r"\d+", text):
        candidates = [run] if len(run) == 2 else [run[:2], run[-2:]]
        for cand in candidates:
            if len(cand) == 2 and _ATA_RANGE[0] <= int(cand) <= _ATA_RANGE[1]:
                return cand
    return ""


def _extract_amount(text: str) -> str:
    """Last digit/comma/decimal run (or the literal "UNK") in a bucket's
    joined text -- mirrors occm_list_func_loc_scanned.py's own
    `_extract_amount`, extended to accept "UNK" (see module docstring)."""
    cleaned = _BORDER_RE.sub(" ", text)
    matches = _AMOUNT_TOKEN_RE.findall(cleaned)
    if not matches:
        return ""
    last = matches[-1]
    return "UNK" if last.upper() == "UNK" else last


def _extract_date(text: str) -> str:
    m = re.search(r"\d{1,2}[-/. ]?[A-Za-z]{3}[-/. ]?\d{2,4}", text)
    return m.group(0) if m else ""


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
    approach as occm_report_scanned.py / occm_list_func_loc_scanned.py). A
    fixed 18px threshold matches occm_list_func_loc_scanned.py's own
    finding for this document family (a bordered ruled grid rendered at
    300dpi): real inter-row gaps sit comfortably above it, intra-row gaps
    comfortably below."""
    if df.empty:
        return []
    df = df.sort_values(["top", "left"]).reset_index(drop=True)
    df["row_id"] = (df["top"].diff().fillna(0).abs() > 18).cumsum()
    groups = []
    for _, g in df.groupby("row_id"):
        g = g.sort_values("left")
        words = list(zip(g["left"], g["width"], g["text"].astype(str)))
        groups.append((g["top"].mean(), words))
    groups.sort(key=lambda t: t[0])
    return [words for _, words in groups]


def _bucket_words(words: list[tuple[float, float, str]], page_width: int) -> dict[str, list[str]]:
    bounds = [(lo * page_width, hi * page_width, name) for lo, hi, name in _COLUMN_FRACS]
    buckets: dict[str, list[str]] = {name: [] for _, _, name in _COLUMN_FRACS}
    for left, width, text in words:
        center = left + width / 2
        for lo, hi, name in bounds:
            if lo <= center < hi:
                buckets[name].append(text)
                break
    return buckets


def _parse_line(words: list[tuple[float, float, str]], page_width: int,
                 page_num: int, header_meta: dict) -> dict | None:
    raw_buckets = _bucket_words(words, page_width)
    buckets = {
        name: _clean_bucket(" ".join(vals) if name in _JOIN_WITH_SPACE else "".join(vals))
        for name, vals in raw_buckets.items()
    }

    part_number = buckets["PART_NUMBER"]
    serial_number = buckets["SERIAL_NUMBER"]
    description = buckets["DESCRIPTION"]
    if not description:
        return None
    # Filters out the repeated column-header row and other non-data noise
    # (same convention as occm_report_scanned.py): a real row's PN or SN
    # always carries a real digit run, the header cells never do.
    if not (_DIGIT_RUN_RE.search(part_number) or _DIGIT_RUN_RE.search(serial_number)):
        return None

    config_slot = buckets["CONFIG_SLOT"]
    # A fused OCR word occasionally spans the CONFIG_SLOT/PART_NUMBER rule
    # entirely (see module docstring), leaving CONFIG_SLOT's own bucket
    # empty and the compound code sitting at the front of PART_NUMBER's
    # bucket instead -- ATA is still recoverable from there in that case.
    ata_source = config_slot if config_slot else part_number
    rec = {
        "ATA": _extract_ata(ata_source),
        "CONFIG_SLOT": config_slot,
        "PART_NUMBER": part_number,
        "SERIAL_NUMBER": serial_number,
        "POSITION": buckets["POSITION"],
        "DESCRIPTION": description,
        "INSTALL_DATE": _extract_date(buckets["INSTALL_DATE"]),
        "TIME_SINCE_NEW": _extract_amount(buckets["TIME_SINCE_NEW"]),
        "TIME_SINCE_INSTALL": _extract_amount(buckets["TIME_SINCE_INSTALL"]),
        "CYCLE_SINCE_NEW": _extract_amount(buckets["CYCLE_SINCE_NEW"]),
        "CYCLE_SINCE_INSTALL": _extract_amount(buckets["CYCLE_SINCE_INSTALL"]),
        "_page": page_num,
    }
    rec.update(header_meta)
    return rec


# --- Header metadata parsing --------------------------------------------
# The header mini-table is read one row-band at a time (see module
# docstring on why a single whole-header OCR pass drops TOTAL_CYCLES).
# These are FALLBACK fractions of page height only, measured on the first
# real sample file seen for this variant -- confirmed directly against a
# second real file from the same document family (same title/column
# layout, different aircraft) that the header block's absolute vertical
# position is NOT constant across files: an extra/missing sub-line above
# the column-header row shifts every row below it by roughly one row's
# height. A fixed set of row-fraction bands tuned to one file therefore
# misses every row on another file in the same family (confirmed directly:
# each of these four bands landed on the WRONG row on that second file).
# `_locate_header_bands()` below finds each row by its own label text on
# whichever page is being read and falls back to these constants only if a
# label can't be located at all (e.g. a severely degraded scan).
_TITLE_BAND = (0.058, 0.075)
_AIRCRAFT_BAND = (0.108, 0.124)
_FLEET_BAND = (0.124, 0.138)
_MSN_BAND = (0.141, 0.156)

# (label token, top-margin, band height) -- as fractions of page height.
# The top-margin/height pair for each row was tuned so the resulting crop
# holds exactly that one row's text cleanly on both real files checked
# (label word's own top position varies file-to-file; these offsets from
# it do not).
_HEADER_ROW_ANCHORS = {
    "TITLE": ("COMPONENTES", -0.008, 0.022),
    "AIRCRAFT": ("AIRCRAFT", -0.003, 0.014),
    "FLEET": ("FLEET", -0.003, 0.014),
    "MSN": ("MSN", -0.003, 0.014),
}

_MFG_RE = re.compile(r"MANUFACTURER\D{0,10}(\d{1,2}[-/. ]?[A-Za-z]{3}[-/. ]?\d{2,4})", re.IGNORECASE)
_ENTERED_RE = re.compile(r"ENTERED\D{0,15}(\d{1,2}[-/. ]?[A-Za-z]{3}[-/. ]?\d{2,4})", re.IGNORECASE)
_FLEET_RE = re.compile(r"FLEET\D{0,5}([A-Z0-9][A-Z0-9\-]{1,15})", re.IGNORECASE)
_HOURS_RE = re.compile(r"HOURS\D{0,10}(\d[\d,]*(?:\.\d+)?)", re.IGNORECASE)
_CYCLES_RE = re.compile(r"CYCLES\D{0,10}(\d[\d,]*)", re.IGNORECASE)
_MSN_RE = re.compile(r"\bMSN\D{0,5}(\d{2,6})\b", re.IGNORECASE)
_ANY_DATE_RE = re.compile(r"\d{1,2}[-/. ]?[A-Za-z]{3}[-/. ]?\d{2,4}")


def _parse_header_meta(header_meta: dict, aircraft_text: str, fleet_text: str,
                        msn_text: str) -> None:
    if not header_meta["MFG_DATE"]:
        m = _MFG_RE.search(aircraft_text)
        if m:
            header_meta["MFG_DATE"] = m.group(1)
    if not header_meta["ENTERED_SERVICE_DATE"]:
        m = _ENTERED_RE.search(aircraft_text)
        if m:
            header_meta["ENTERED_SERVICE_DATE"] = m.group(1)
    if not header_meta["AIRCRAFT_FAMILY"]:
        m = _FLEET_RE.search(fleet_text)
        if m:
            header_meta["AIRCRAFT_FAMILY"] = m.group(1).upper()
    if not header_meta["TOTAL_HOURS"]:
        m = _HOURS_RE.search(fleet_text)
        if m:
            header_meta["TOTAL_HOURS"] = m.group(1)
    if not header_meta["TOTAL_CYCLES"]:
        m = _CYCLES_RE.search(fleet_text)
        if m:
            header_meta["TOTAL_CYCLES"] = m.group(1)
    if not header_meta["MSN"] or not header_meta["MFL_DATE"]:
        m = _MSN_RE.search(msn_text)
        if m:
            header_meta["MSN"] = m.group(1)
            tail = msn_text[m.end():]
            date_m = _ANY_DATE_RE.search(tail)
            if date_m:
                header_meta["MFL_DATE"] = date_m.group(0)


def _header_incomplete(header_meta: dict) -> bool:
    return not all(header_meta.values())


async def _ocr_band(img, band: tuple[float, float]) -> str:
    """OCR one tight header-row crop. Tries the default uniform-block
    layout mode (psm 6) first -- confirmed directly the right choice for
    AIRCRAFT/FLEET/MSN's own dense, left-aligned rows across all three
    real files -- and falls back to a sparse-text pass (psm 11) only when
    that comes back blank. Confirmed directly on the third real file's own
    TITLE row: a short phrase set off to the right, with wide blank
    margins on both sides and no other text on its row, is exactly the
    shape psm 6 drops outright (see `_locate_header_bands`'s docstring for
    the same failure mode there) but psm 11 reads cleanly and with high
    per-word confidence."""
    w, h = img.size
    crop = img.crop((0, int(h * band[0]), w, int(h * band[1])))
    crop = crop.resize((crop.width * 2, crop.height * 2))
    text = await ocr_text(crop, psm=6)
    if text.strip():
        return text
    return await ocr_text(crop, psm=11)


async def _locate_header_bands(img) -> dict[str, tuple[float, float]]:
    """Find this page's own TITLE/AIRCRAFT/FLEET/MSN row bands by their
    label text, instead of assuming the fixed fractions above (see the
    comment on _HEADER_ROW_ANCHORS/the fallback constants for why: this
    document family's header block shifts vertically file to file).

    A single cheap `ocr_words()` pass over the top quarter of the page,
    with Tesseract's default uniform-block layout mode (psm 6), locates
    AIRCRAFT/FLEET/MSN reliably -- confirmed directly across all three
    real files. The TITLE row is a different shape (an isolated short
    phrase set off to the right, above a horizontal rule, with a wide gap
    of blank space on both sides) that the same uniform-block pass
    confirmed directly, on the third real file, to drop entirely --
    Tesseract's psm 6 layout analysis merges/discards it rather than
    mis-reading it. A sparse-text pass (psm 11) over the same crop
    recovers it cleanly (confirmed directly, high per-word confidence) and
    is tried as a second pass, but only for whichever anchor(s) the first
    pass didn't find, since the cheaper uniform-block pass already covers
    the other rows correctly and psm 11 alone is not a reliable substitute
    for it (looser layout assumptions read stray table-grid fragments in
    that same crop as spurious words often enough to be worth avoiding
    except where actually needed).

    The caller still does its own clean, single-line `_ocr_band()` pass
    over the tight band returned here, same as before. A label missing
    from this dict (couldn't be located in either pass) should fall back
    to that row's fixed constant above.
    """
    w, h = img.size
    crop = img.crop((0, 0, w, int(h * 0.25)))
    crop = crop.resize((crop.width * 2, crop.height * 2))
    words = await ocr_words(crop, psm=6, min_conf=-1)

    def _search(word_list) -> dict[str, tuple[float, float]]:
        found: dict[str, tuple[float, float]] = {}
        for key, (token, lo_margin, height) in _HEADER_ROW_ANCHORS.items():
            for word in word_list:
                text = str(word.get("text", "")).strip().upper()
                if token in text:
                    top_frac = (word.get("top", 0) / 2) / h
                    lo = max(0.0, top_frac + lo_margin)
                    found[key] = (lo, lo + height)
                    break
        return found

    bands = _search(words)
    missing = [k for k in _HEADER_ROW_ANCHORS if k not in bands]
    if missing:
        sparse_words = await ocr_words(crop, psm=11, min_conf=-1)
        sparse_bands = _search(sparse_words)
        for key in missing:
            if key in sparse_bands:
                bands[key] = sparse_bands[key]
    return bands


# Whole-document rotation candidates, tried in this order (see module
# docstring on the third real file's whole-scan 90-degree rotation): 0
# first since the first two real files in this family were already
# upright, then the confirmed -90 correction, then the two remaining
# right-angle possibilities as an untested-but-plausible fallback for a
# future file rotated the other way. `Image.rotate()`'s positive direction
# is counter-clockwise, so -90 here means "rotate 90 degrees clockwise".
_ROTATION_CANDIDATES = (0, -90, 90, 180)


async def _detect_page_rotation(pdf_path: str, page_index: int = 0) -> int | None:
    """Resolve this file's whole-document rotation correction once, by
    OCR-testing page 0's own title text (the same "COMPONENTES"/"OC/CM"
    anchor `ocr_detect()` uses) across `_ROTATION_CANDIDATES` and keeping
    whichever angle actually makes the title readable. Returns None if the
    title can't be found in any candidate orientation (e.g. a severely
    degraded scan, or a file outside this variant entirely) -- callers
    treat that as "not this variant" / "assume upright" as appropriate.

    See module docstring: this document family's page geometry is
    portrait in the PDF's own MediaBox regardless of the scanned content's
    true orientation, so an aspect-ratio check alone can't tell a rotated
    file from an upright one here -- the content itself has to be read.
    """
    base_img = await render_page(pdf_path, page_index, dpi=300)
    for angle in _ROTATION_CANDIDATES:
        img = base_img if angle == 0 else base_img.rotate(angle, expand=True)
        band = (await _locate_header_bands(img)).get("TITLE", _TITLE_BAND)
        text = (await _ocr_band(img, band)).upper()
        if "COMPONENTES" in text and "OC/CM" in text:
            return angle
    return None


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback (see
    sheet_types/occm.py) -- this variant's SIGNATURES can never match
    through the normal pdfplumber text-extract path since the known source
    file has no text layer at all.

    Anchors on "COMPONENTES OC/CM", the report's own title-line phrase
    (Spanish for "OC/CM Components"), which OCRs reliably even at this
    cheap pass. Checked directly (grep across every SIGNATURES list in
    sheet_types/{occm,ht,llp}.py and every existing occm_variants/
    ht_variants/llp_variants file): the phrase appears nowhere else, and is
    not a substring of (nor contains) any other variant's own SIGNATURES
    entries -- in particular a305_a340_occm.py's own "Components >> OC/CM
    Components" phrase differs at the very first distinguishing letter
    ("Componentes" vs "Components") in both directions.

    The title's own crop is now located per-page via `_locate_header_bands`
    rather than a fixed fraction (see that function and the comment on
    _HEADER_ROW_ANCHORS): confirmed directly on a second real file in this
    same document family that the fixed `_TITLE_BAND` below misses the
    title line entirely once the header block sits even one row lower on
    the page. `_detect_page_rotation()` additionally tries the title in a
    small set of rotated orientations, covering the third real file's own
    whole-scan rotation (see module docstring).
    """
    try:
        return (await _detect_page_rotation(pdf_path, 0)) is not None
    except Exception:
        return False


async def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    header_meta = {
        "AIRCRAFT_FAMILY": "", "TOTAL_HOURS": "", "TOTAL_CYCLES": "",
        "MSN": "", "MFG_DATE": "", "ENTERED_SERVICE_DATE": "", "MFL_DATE": "",
    }
    n_pages = await page_count(pdf_path)
    # Resolved once from page 0 and applied uniformly to every page (see
    # module docstring / `_detect_page_rotation`) -- None (title not found
    # in any candidate orientation) falls back to upright rather than
    # raising, consistent with this package's soft-failure conventions;
    # downstream per-row parsing simply yields few/no rows in that case.
    rotation = await _detect_page_rotation(pdf_path, 0) or 0
    for page_index in range(n_pages):
        img = await render_page(pdf_path, page_index, dpi=300)
        if rotation:
            img = img.rotate(rotation, expand=True)
        if _header_incomplete(header_meta):
            row_bands = await _locate_header_bands(img)
            aircraft_text = await _ocr_band(img, row_bands.get("AIRCRAFT", _AIRCRAFT_BAND))
            fleet_text = await _ocr_band(img, row_bands.get("FLEET", _FLEET_BAND))
            msn_text = await _ocr_band(img, row_bands.get("MSN", _MSN_BAND))
            _parse_header_meta(header_meta, aircraft_text, fleet_text, msn_text)
        words = await ocr_words(img, psm=6, min_conf=-1)
        df = _words_to_df(words)
        page_width = img.size[0]
        for line_words in _group_lines(df):
            rec = _parse_line(line_words, page_width, page_index + 1, header_meta)
            if rec is not None:
                records.append(rec)
    return records
