"""Component Inventory (HT / LLP) -- scanned, no text layer, OCR required
throughout.

Confirmed on one real corpus file (12 pages, 0 pdfplumber-extractable chars
on any page checked -- every page is a single embedded landscape scan
image, no text layer at all). Same underlying MIS report-generation tool
as `occm_variants/component_inventory_oc_cm_status_scanned.py` (identical
header layout, identical "COMPONENT INVENTORY - <bucket>" title style,
same sign-off stamp convention), just the HT/LLP-filtered bucket of that
tool's output rather than the OC/CM-filtered one -- the two column layouts
differ enough (see below) that this is its own module rather than a shared
one.

Header (repeats verbatim on every page, two lines)::

    ACFT: <reg>   S/N <msn>        COMPONENT INVENTORY - HT / LLP       STATUS DATE: <date>
    TSN <n>       CSN <n>                     <type>                    PAGE <n> OF <n>

...followed by a column-header row (no ruled grid -- a plain positional
table, like the OC/CM sibling) reading::

    KEYWORD          PARTNUMBER   -----INSTALLATION-----  TSN TSO OH_DTE  -INTERVAL-  -REMAINING-
    PPM  CPN         SERIAL       DATE   POSITION         CSN CSO         SVC HRS CYC DAY  HRS CYC DAY  FORECAST

Row grain: unlike the OC/CM sibling (one physical OCR line per record),
each component here spans a variable-height, THREE-PART block with no
ruled divider of its own (confirmed directly against the real sample
file, rendered and inspected page by page):

  1. One "identity" line carrying KEYWORD (free-text description),
     PART_NUMBER, INSTALL_DATE, POSITION, TSN and OH_DTE.
  2. A second "identity" line directly below it carrying the PPM flag
     (literally "HT" on every row of the sample -- "LLP" never actually
     observed there, but the report's own title implies it is the sibling
     bucket value the same tool can emit, so it is still accepted rather
     than hardcoding "HT" as the only valid reading), CPN (a
     component-type reference code, confirmed shaped
     `<ata>-<subchapter>-<seq>`), SERIAL_NUMBER and CSN/CSO (the CSN/CSO
     values share the same on-page column as TSN/CSO from line 1, stacked
     one value per line rather than side by side -- confirmed directly).
  3. ONE OR MORE "service" lines below that, each independently giving one
     life-limit basis for the SAME component: an unlabeled single-letter
     flag (confirmed "C" on the overwhelming majority of rows, "S" on a
     handful -- no column caption at all above this position, so kept as
     a literal, unlabeled flag column per this project's convention for
     an undocumented source field, see e.g. the OC/CM sibling's own
     D_FLAG), an SVC task code (O/H, CLN, RST, BET, PRC, HYT, U/L, WHG,
     INS confirmed on the real sample), INTERVAL_{HRS,CYC,DAY} and
     REMAINING_{HRS,CYC,DAY} (only the basis actually tracked for that
     particular limit is populated -- confirmed directly some components
     use HRS+DAY, others CYC+DAY, others HRS+CYC alone, others a single
     HRS-only "useful life" row -- never guessed/backfilled, left exactly
     as OCR'd per column position), and FORECAST (a date immediately
     followed by an unlabeled trailing letter, e.g. "H"/"D"/"C", and
     sometimes a trailing "*" -- neither the letter nor the asterisk has
     any column caption of its own in the source, so the whole FORECAST
     cell is kept as one verbatim string rather than force-splitting an
     undocumented suffix into invented fields, per this project's "never
     guess a wrong split" convention).

A component with no service line at all (rare, not confirmed on the real
sample but defensively handled) still emits exactly one record, with every
SVC_* / INTERVAL_* / REMAINING_* / FORECAST field blank, rather than being
silently dropped.

ATA is not printed as its own column -- it is derived from CPN's own
leading 2-digit chapter code (confirmed directly: every real CPN value on
the sample carries the same leading 2 digits as the shaded ATA-chapter
banner row printed just above that chapter's own first component block),
the same technique the OC/CM sibling uses against its own CONFIG_SLOT
column. The banner rows themselves are not parsed -- they carry no other
information and, since they match none of this module's three row shapes
(see below), are simply never classified as anything, no explicit
skip-logic required.

A handwritten signature/stamp sits in the bottom-right margin of most
pages. Its own diagonal text was confirmed directly to occasionally throw
stray 1-3 character OCR fragments well past the FORECAST column's own
real right-hand extent, at scattered Y positions spanning a wide vertical
range on at least one page -- not just clustered near the bottom-right
corner -- which is why words past `_JUNK_WORD_LEFT_FRAC` are dropped
before line-clustering (see `_group_lines_with_top`) rather than assumed
harmless. No signer name is written into this module regardless.

Row classification (no ruled grid to anchor on, so lines are told apart by
their own content shape, not by position in a fixed N-line cycle):

  - a line carrying a `D[D]/M[M]/YYYY`-shaped token in the DATE column
    band is the block's own identity line 1 (starts a new record group);
  - a line with the previous identity line still pending and no service-
    line content of its own is treated as identity line 2 (PPM/CPN/SERIAL/
    CSN/CSO) regardless of whether PPM literally reads "HT"/"LLP" -- OCR
    noise on that one flag token would otherwise silently drop a whole
    real row's SERIAL_NUMBER/CSN/CSO, which is worse than accepting a
    slightly garbled PPM_FLAG (RULES still flags an unrecognised value);
  - a line with the unlabeled flag column or SVC/interval/remaining/
    forecast columns populated is a service line -- emits one record per
    line, stamped with the most recently completed identity;
  - anything else (page title/header text, the repeated column-header
    row, an ATA-chapter banner row, a stray mark from the corner
    signature stamp) matches none of the above and is silently ignored.

OCR approach: `ocr_words()` (word-level bounding boxes, `min_conf=-1`,
same reasoning as the OC/CM sibling) + geometric line-clustering by Y,
then column assignment by X-fraction-of-page-width (not raw pixels, so a
page rendered at a size a few percent off from the sample -- confirmed
across the real sample's own 12 pages, whose rendered widths vary by
about 1% page to page -- still buckets correctly). Column boundaries
below were measured directly from a real per-word OCR pass across several
widely-separated pages of the sample file, placed at the midpoint of each
observed gap between neighbouring columns' own real content (not just
their header captions -- KEYWORD/CPN description text routinely runs
wider than the "KEYWORD"/"CPN" caption itself, POSITION values up to 8
characters routinely run wider than the "POSITION" caption, etc. -- every
boundary below was checked against the WIDEST real content seen on either
side of it, not just the header row).

`extract()` runs OCR over each page TWICE, not once, after confirming
directly that a single whole-page OCR pass silently drops a real service
line's own FLAG/SVC_CODE/interval/remaining tokens whenever a nearby
component happens to share the exact same task code and interval values
(a genuine Tesseract line-dedup quirk against near-identical nearby text,
the same family of issue this project's other per-column-strip OCR
variants call out, just triggered here by row *repetition* rather than
column repetition): a first, single whole-page pass locates only each
block's own identity-line-1 Y position (anchored on its own INSTALL_DATE
token, confirmed reliable under whole-page OCR even where the affected
service-line columns were not, since no two components share an install
date); a second pass then re-OCRs each block's own Y-band -- with
generous padding either side, not a tight crop (see `_CROP_PAD_PX`) --
in total isolation from every other block, which was confirmed directly
to recover the dropped tokens. `_process_block_lines()` still tolerates a
second (or third) row1-shaped line turning up inside one block's own
re-OCR pass -- confirmed directly necessary since the first pass's own
anchor-finding can occasionally miss one component's identity-line-1 the
same way, which would otherwise silently fold that whole extra
component's identity+service lines into the wrong record instead of
losing or misattributing them.

Before line-clustering, any single OCR "word" wider than ~12% of the
page's own width is dropped -- confirmed directly on the real sample file
that the thin horizontal rule printed under each component block is
occasionally misread by Tesseract as one absurdly wide "word" (a bogus
bounding box spanning most of the page, several thousand px, holding 1-2
garbage characters) rather than being ignored as a graphic; every genuine
single-word OCR box on this file, even a long PART_NUMBER/CPN code,
measures well under that width, so this filter only ever removes the rule-
line artifact.

Two-value column pairs (TSN/CSN, TSO/CSO) share one on-page X-band across
the pair's own two stacked physical lines (see row-grain discussion
above) -- read directly off whichever physical line (identity line 1 vs
2) is being parsed at the time, not by any further X-split within that
band.

SVC_CODE cleanup: every 3-letter code (BET, HYT, CLN, RST, PRC, WHG, INS)
was confirmed to OCR cleanly and verbatim across the real sample; the two
codes containing a "/" (O/H, U/L) are the only ones that reliably garble
(the slash itself is dropped/merged into the neighbouring letter --
confirmed directly, e.g. "O/H" reading back as "OM"/"OH"/"OF"/"OW" and
"U/L" reading back as "UN"/"UL"/"UF" across the real sample) -- these
specific, deterministically-observed misreadings are normalised back to
"O/H"/"U/L"; anything else is passed through verbatim rather than guessed
at, per this project's "never guess a wrong split" convention.

Sensitivity note: the sample file's own header carries a real operator
name/logo, tail number, MSN and dates -- none of that is written into
this module's code/comments (only the generic column-header/title phrases
the template itself prints, which are not document-specific). The
header's AIRCRAFT_REG/MSN/etc. fields ARE extracted into row data at
runtime (ordinary functional extraction, not a hardcoded value in source
code), same as the OC/CM sibling. The corner signature stamp is never
parsed into any field (see above); no signer name is written into this
module either way.
"""
from __future__ import annotations
import re

import pandas as pd

from sheet_types.ht_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, ocr_words, page_count

NAME = "Component Inventory (HT / LLP, Scanned)"

# Deliberately empty -- the known source file has no text layer at all
# (confirmed: 0 pdfplumber-extractable chars on every page), so this
# module is only ever reached via ocr_detect()'s blank-text fallback below,
# never the router's normal pdfplumber-text SIGNATURES match.
SIGNATURES: list[str] = []

CANONICAL_COLUMNS = [
    "ATA",
    "KEYWORD",
    "PPM_FLAG",
    "CPN",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "INSTALL_DATE",
    "POSITION",
    "TSN",
    "CSN",
    "TSO",
    "CSO",
    "OH_DTE",
    "SVC_FLAG",
    "SVC_CODE",
    "INTERVAL_HRS",
    "INTERVAL_CYC",
    "INTERVAL_DAY",
    "REMAINING_HRS",
    "REMAINING_CYC",
    "REMAINING_DAY",
    "FORECAST",
    # Header metadata -- parsed once from page 1, stamped onto every row.
    "AIRCRAFT_REG",
    "MSN",
    "AIRCRAFT_TYPE",
    "TSN_TOTAL",
    "CSN_TOTAL",
    "STATUS_DATE",
]

_AMOUNT_RULE = {"pattern": r"^\d+$", "allow_empty": True}
_DATE_RULE = {"pattern": r"^\d{1,2}/\d{1,2}/\d{2,4}$", "allow_empty": True}

_OVERRIDES = {
    "ATA": {"allow_empty": True},  # global rule's int_range(20,83) still applies
    "KEYWORD": {"allow_empty": True, "uppercase": True},
    "PPM_FLAG": {"pattern": r"^(HT|LLP)$", "uppercase": True, "allow_empty": True},
    # No established shape beyond "starts with the ATA chapter" (see module
    # docstring) -- loose, informational.
    "CPN": {"allow_empty": True, "uppercase": True},
    "PART_NUMBER": {"allow_empty": True},
    "SERIAL_NUMBER": {"allow_empty": True},
    "INSTALL_DATE": _DATE_RULE,
    "POSITION": {"pattern": r"^[A-Z0-9/]{0,20}$", "uppercase": True, "allow_empty": True},
    "TSN": _AMOUNT_RULE,
    "CSN": _AMOUNT_RULE,
    "TSO": _AMOUNT_RULE,
    "CSO": _AMOUNT_RULE,
    "OH_DTE": _DATE_RULE,
    # Unlabeled single-letter column (see module docstring) -- no fixed
    # shape to validate, informational only.
    "SVC_FLAG": {"pattern": r"^[A-Z]{0,2}$", "uppercase": True, "allow_empty": True},
    "SVC_CODE": {"allow_empty": True, "uppercase": True},
    "INTERVAL_HRS": _AMOUNT_RULE,
    "INTERVAL_CYC": _AMOUNT_RULE,
    "INTERVAL_DAY": _AMOUNT_RULE,
    "REMAINING_HRS": _AMOUNT_RULE,
    "REMAINING_CYC": _AMOUNT_RULE,
    "REMAINING_DAY": _AMOUNT_RULE,
    # Verbatim date + unlabeled trailing letter/asterisk (see module
    # docstring) -- no single fixed shape, kept as free text.
    "FORECAST": {"allow_empty": True},
    # Header metadata -- generic shape checks only (never tied to any one
    # real file's specific values), allow_empty since a header-parse miss
    # should never mass-flag every row over one shared stamped value.
    "AIRCRAFT_REG": {"pattern": r"^[A-Z0-9]{1,3}-[A-Z0-9]{2,6}$", "uppercase": True, "allow_empty": True},
    "MSN": {"pattern": r"^\d{3,6}$", "allow_empty": True},
    "AIRCRAFT_TYPE": {"pattern": r"^[A-Z][A-Z0-9]{2,5}$", "uppercase": True, "allow_empty": True},
    "TSN_TOTAL": _AMOUNT_RULE,
    "CSN_TOTAL": _AMOUNT_RULE,
    "STATUS_DATE": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Column X-boundaries, as a fraction of the rendered page's own width -- see
# module docstring for how these were derived. Ordered left to right;
# assignment is by nearest-enclosing (lo, hi) band, not by any fixed
# per-line column count, since which physical line (identity 1 / identity
# 2 / service) a given band's text belongs to is decided separately by row
# classification (see module docstring).
_COLUMNS = [
    (0.0451, 0.1844, "IDENT"),          # KEYWORD (identity 1) / PPM+CPN (identity 2)
    (0.1844, 0.2923, "PARTNUM"),        # PART_NUMBER (identity 1) / SERIAL_NUMBER (identity 2)
    (0.2923, 0.3756, "DATE"),           # INSTALL_DATE (identity 1 only)
    (0.3756, 0.4585, "POSITION"),       # POSITION (identity 1 only)
    (0.4585, 0.5103, "TSN_CSN"),        # TSN (identity 1) / CSN (identity 2)
    (0.5103, 0.5436, "TSO_CSO"),        # TSO (identity 1) / CSO (identity 2)
    (0.5436, 0.5972, "OH_DTE"),         # OH_DTE (identity 1 only)
    (0.5972, 0.6126, "FLAG"),           # unlabeled service-line flag
    (0.6126, 0.6407, "SVC_CODE"),
    (0.6407, 0.6647, "INTERVAL_HRS"),
    (0.6647, 0.6977, "INTERVAL_CYC"),
    (0.6977, 0.7332, "INTERVAL_DAY"),
    (0.7332, 0.7685, "REMAINING_HRS"),
    (0.7685, 0.8016, "REMAINING_CYC"),
    (0.8016, 0.8346, "REMAINING_DAY"),
    (0.8346, 1.00000, "FORECAST"),
]

# A single OCR "word" wider than this fraction of the page's own width is
# treated as a rule-line artifact and dropped before line-clustering (see
# module docstring) -- comfortably above the widest genuine single token
# observed on the real sample (a 15-character PART_NUMBER/CPN code, well
# under half this threshold) and comfortably below every observed artifact
# (which spanned most of the page width).
_JUNK_WORD_WIDTH_FRAC = 0.12

# A word whose own LEFT edge sits beyond this fraction of the page's own
# width is dropped as off-table noise before line-clustering -- confirmed
# directly on the real sample file that the corner signature stamp throws
# stray 1-3 character OCR fragments well past the FORECAST column's own
# real right-hand extent (a 10-character date plus a one-letter suffix and
# an asterisk, confirmed never extending past ~0.915 of the page width on
# any real row) at scattered Y positions spanning a wide vertical range on
# at least one page -- not just clustered near the bottom-right corner.
# Left uncaught, those scattered fragments bridge the gap between two
# genuinely different physical rows via `_LINE_CLUSTER_PX`'s own
# tolerance (each individual adjacent gap ends up under the threshold even
# though the two real rows either side of the noise are not actually
# adjacent), merging them into one bad cluster -- confirmed directly this
# is what was gluing a component's own identity-line-2 and service-line
# text onto its identity-line-1 text on at least one real block before
# this filter was added.
_JUNK_WORD_LEFT_FRAC = 0.92

# Y-clustering tolerance for grouping words into physical lines -- wider
# than this package's usual ~13-18px single-line tolerance because this
# file's own service-line numeric columns were confirmed directly to land
# up to ~18px off their own row's flag/SVC-code/FORECAST tokens (a
# Tesseract per-word Y-jitter quirk, same kind this package's OC/CM
# sibling also works around with its own widened tolerance), while the
# tightest confirmed real gap between two genuinely different physical
# rows (a component's own back-to-back service lines) is comfortably
# wider than that.
_LINE_CLUSTER_PX = 22

_DATE_TOKEN_RE = re.compile(r"\d{1,2}/\d{1,2}/\d{2,4}")
_PURE_PUNCT_RE = re.compile(r"^[|_=~—\-:;.,]+$")
_BORDER_RE = re.compile(r"[|\[\]{}<>=~()`*\"'«»‘’“”–—_]+")
_EDGE_STRIP = " _-|[]=~.\"':;"
_ATA_LEADING_RE = re.compile(r"^(\d{2})")

# The page/column-header block repeats verbatim on every page (see module
# docstring) -- these exact caption strings (this template's own fixed
# labels, not document-specific data) are dropped before line-clustering.
# Confirmed directly necessary: on at least one page of the real sample,
# the header block's own two stacked caption lines ("KEYWORD .../PPM CPN
# SERIAL...") sit close enough above the first real data row that simple
# sequential Y-diff clustering chains them into the same physical-line
# group as that first real row (each individual adjacent gap is under the
# clustering tolerance even though the header-to-data gap as a whole is
# not) -- stripping the caption tokens up front removes the bridge rather
# than trying to tighten the tolerance, which would risk re-splitting a
# genuine service line's own confirmed ~18px internal Y-jitter instead
# (see _LINE_CLUSTER_PX below).
_HEADER_LABELS = {
    "ACFT", "S", "N", "COMPONENT", "INVENTORY", "STATUS", "DATE", "PAGE",
    "OF", "TSN", "CSN", "TSO", "CSO", "KEYWORD", "PARTNUMBER", "SERIAL",
    "INSTALLATION", "POSITION", "OHDTE", "PPM", "CPN", "SVC", "HRS",
    "CYC", "DAY", "FORECAST", "INTERVAL", "REMAINING",
}


def _is_header_label(text: str) -> bool:
    cleaned = re.sub(r"[^A-Z]", "", text.upper())
    return cleaned in _HEADER_LABELS

# Deterministically-observed slash-drop misreadings (see module docstring)
# -- checked directly against the real sample file's own OCR output.
_OH_VARIANTS = {"OM", "OH", "OF", "OW"}
_UL_VARIANTS = {"UN", "UL", "UF"}


def _words_to_df(words: list[dict]) -> pd.DataFrame:
    cols = ["left", "top", "width", "height", "conf", "text"]
    df = pd.DataFrame(words, columns=cols) if words else pd.DataFrame(columns=cols)
    if not df.empty:
        df = df.dropna(subset=["text"])
        df = df[df["text"].astype(str).str.strip() != ""]
    return df


def _group_lines_with_top(df: pd.DataFrame, page_width: int) -> list[tuple[float, list[tuple[float, str]]]]:
    """Cluster words into text-lines by Y, dropping rule-line artifacts
    and repeated-caption noise first (see module docstring). Returns each
    line's own mean top alongside its (left, text) word list -- needed by
    `extract()`'s own anchor-finding pass (see `_group_lines` below for
    the plain word-list-only form most callers want)."""
    if df.empty:
        return []
    df = df[df["width"] <= _JUNK_WORD_WIDTH_FRAC * page_width]
    if df.empty:
        return []
    df = df[df["left"] <= _JUNK_WORD_LEFT_FRAC * page_width]
    if df.empty:
        return []
    df = df[~df["text"].astype(str).map(_is_header_label)]
    if df.empty:
        return []
    df = df.sort_values(["top", "left"]).reset_index(drop=True)
    df["row_id"] = (df["top"].diff().fillna(0).abs() > _LINE_CLUSTER_PX).cumsum()
    groups = []
    for _, g in df.groupby("row_id"):
        g = g.sort_values("left")
        words = list(zip(g["left"], g["text"].astype(str)))
        groups.append((g["top"].mean(), words))
    groups.sort(key=lambda t: t[0])
    return groups


def _group_lines(df: pd.DataFrame, page_width: int) -> list[list[tuple[float, str]]]:
    """Cluster words into text-lines by Y -- see `_group_lines_with_top`."""
    return [words for _, words in _group_lines_with_top(df, page_width)]


def _bucket_tokens(words: list[tuple[float, str]], page_width: int) -> dict[str, list[str]]:
    buckets: dict[str, list[str]] = {name: [] for _, _, name in _COLUMNS}
    for left, text in words:
        frac = left / page_width
        for lo, hi, name in _COLUMNS:
            if lo <= frac < hi:
                buckets[name].append(text)
                break
    return buckets


def _clean_join(tokens: list[str], sep: str = " ") -> str:
    kept = [t for t in tokens if not _PURE_PUNCT_RE.match(t)]
    text = sep.join(kept)
    text = _BORDER_RE.sub(" ", text)
    return " ".join(text.split()).strip(_EDGE_STRIP)


def _digits(tokens: list[str]) -> str:
    text = " ".join(tokens)
    found = re.findall(r"\d+", text)
    return found[0] if found else ""


def _extract_date(tokens: list[str]) -> str:
    text = " ".join(tokens)
    m = _DATE_TOKEN_RE.search(text)
    return m.group(0) if m else ""


def _clean_flag(tokens: list[str]) -> str:
    letters = re.sub(r"[^A-Za-z]", "", "".join(tokens)).upper()
    return letters[:1] if letters else ""


def _clean_svc_code(tokens: list[str]) -> str:
    raw = _clean_join(tokens, sep="")
    norm = re.sub(r"[^A-Z0-9]", "", raw.upper())
    if norm in _OH_VARIANTS:
        return "O/H"
    if norm in _UL_VARIANTS:
        return "U/L"
    return raw.upper()


def _ata_from_cpn(cpn: str) -> str:
    m = _ATA_LEADING_RE.match(cpn)
    return m.group(1) if m else ""


_EMPTY_IDENTITY = {
    "KEYWORD": "", "PART_NUMBER": "", "INSTALL_DATE": "", "POSITION": "",
    "TSN": "", "OH_DTE": "", "PPM_FLAG": "", "CPN": "", "SERIAL_NUMBER": "",
    "CSN": "", "TSO": "", "CSO": "",
}
_EMPTY_SVC = {
    "SVC_FLAG": "", "SVC_CODE": "",
    "INTERVAL_HRS": "", "INTERVAL_CYC": "", "INTERVAL_DAY": "",
    "REMAINING_HRS": "", "REMAINING_CYC": "", "REMAINING_DAY": "",
    "FORECAST": "",
}
# Columns whose OWN content, if a clean digit run, is trusted as a
# service-line signal (see `_looks_like_svc_line` below) -- FORECAST is
# deliberately excluded even though it often carries digits (a date),
# since the page-1 header block's own "STATUS DATE:"/"PAGE n OF n" text
# also lands in this X-range and would otherwise be misread as a service
# line (confirmed directly on the real sample before the header-label
# stoplist above was added).
_SVC_DIGIT_BUCKETS = (
    "INTERVAL_HRS", "INTERVAL_CYC", "INTERVAL_DAY",
    "REMAINING_HRS", "REMAINING_CYC", "REMAINING_DAY",
)
_DIGIT_TOKEN_RE = re.compile(r"^\d+$")


def _looks_like_svc_line(b: dict[str, list[str]]) -> bool:
    """A service line is trusted only via its own unlabeled flag reading
    "C"/"S" or a genuine digit-only token in one of the interval/
    remaining columns -- not merely "some text landed in the right-hand
    half of the page" (too permissive: confirmed directly on the real
    sample file that stray marks from the bottom-right corner signature
    stamp OCR into short garbage "words" whose X position falls inside
    this same column band on at least one page)."""
    if _clean_flag(b["FLAG"]) in ("C", "S"):
        return True
    return any(_DIGIT_TOKEN_RE.match(tok) for name in _SVC_DIGIT_BUCKETS for tok in b[name])


def _new_record(identity: dict[str, str], svc: dict[str, str], page_index: int,
                 header_meta: dict[str, str]) -> dict:
    rec = {c: "" for c in CANONICAL_COLUMNS}
    rec.update(identity)
    rec.update(svc)
    rec["ATA"] = _ata_from_cpn(identity["CPN"])
    rec["_page"] = page_index + 1
    rec.update(header_meta)
    return rec


# --- Header metadata parsing --------------------------------------------
_ACFT_RE = re.compile(r"ACFT\s*:?\s*([A-Z0-9\-]+)", re.IGNORECASE)
_MSN_RE = re.compile(r"S\s*/\s*N\s*[:\s]*\s*(\d{3,6})", re.IGNORECASE)
_STATUS_DATE_RE = re.compile(r"STATUS\s*DATE\s*:\s*(\S+)", re.IGNORECASE)
_TSN_TOTAL_RE = re.compile(r"\bTSN\s+([\d,]+)", re.IGNORECASE)
_CSN_TOTAL_RE = re.compile(r"\bCSN\s+([\d,]+)", re.IGNORECASE)
_TYPE_RE = re.compile(r"^[A-Z]\d{2,4}[A-Z0-9]*$")

_HEADER_FIELDS = ["AIRCRAFT_REG", "MSN", "AIRCRAFT_TYPE", "TSN_TOTAL", "CSN_TOTAL", "STATUS_DATE"]


async def _parse_header(pdf_path: str) -> dict:
    """Parsed once from page 1 and stamped onto every row -- the header
    block is confirmed identical (aside from PAGE n) on every page of the
    real sample file. Cropped to the top ~13% of the page -- above the
    table's own column-header row (which repeats "TSN"/"CSN" a second
    time as column captions; restricting the crop keeps those out of this
    regex pass)."""
    meta = {k: "" for k in _HEADER_FIELDS}
    try:
        img = await render_page(pdf_path, 0, dpi=300)
        w, h = img.size
        crop = img.crop((0, 0, w, int(h * 0.13)))
        text = await ocr_text(crop, psm=6)
    except Exception:
        return meta

    m = _ACFT_RE.search(text)
    if m:
        meta["AIRCRAFT_REG"] = m.group(1).strip(_EDGE_STRIP).upper()
    m = _MSN_RE.search(text)
    if m:
        meta["MSN"] = m.group(1)
    m = _STATUS_DATE_RE.search(text)
    if m:
        meta["STATUS_DATE"] = m.group(1).strip(_EDGE_STRIP)
    m = _TSN_TOTAL_RE.search(text)
    if m:
        meta["TSN_TOTAL"] = m.group(1).replace(",", "")
    m = _CSN_TOTAL_RE.search(text)
    if m:
        meta["CSN_TOTAL"] = m.group(1).replace(",", "")
    for line in text.splitlines():
        tok = line.strip().strip(_EDGE_STRIP).upper()
        if tok and _TYPE_RE.match(tok) and any(c.isdigit() for c in tok):
            meta["AIRCRAFT_TYPE"] = tok
            break
    return meta


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback.
    Anchors on "COMPONENT INVENTORY" combined with the "HT / LLP" title
    fragment (spaces around the slash tolerated). Checked directly (grep
    across every SIGNATURES list in sheet_types/{ht,occm,llp}.py and every
    existing ht_variants/occm_variants/llp_variants file): no other
    module's own SIGNATURES/ocr_detect anchor combines "COMPONENT
    INVENTORY" with an "HT / LLP" fragment -- in particular the OC/CM
    sibling's own anchor requires "OC / CM" instead, which this file's own
    sample does not carry anywhere on page 1."""
    try:
        img = await render_page(pdf_path, 0, dpi=300)
        w, h = img.size
        crop = img.crop((0, 0, w, int(h * 0.13)))
        text = (await ocr_text(crop, psm=6)).upper()
        return "COMPONENT INVENTORY" in text and bool(re.search(r"HT\s*/\s*LLP", text))
    except Exception:
        return False


def _start_identity(b0: dict[str, list[str]]) -> dict[str, str]:
    identity = dict(_EMPTY_IDENTITY)
    identity["KEYWORD"] = _clean_join(b0["IDENT"])
    identity["PART_NUMBER"] = _clean_join(b0["PARTNUM"], sep="")
    identity["INSTALL_DATE"] = _extract_date(b0["DATE"])
    identity["POSITION"] = _clean_join(b0["POSITION"], sep="")
    identity["TSN"] = _digits(b0["TSN_CSN"])
    identity["TSO"] = _digits(b0["TSO_CSO"])
    identity["OH_DTE"] = _extract_date(b0["OH_DTE"])
    return identity


def _svc_from_bucket(b: dict[str, list[str]]) -> dict[str, str]:
    svc = dict(_EMPTY_SVC)
    svc["SVC_FLAG"] = _clean_flag(b["FLAG"])
    svc["SVC_CODE"] = _clean_svc_code(b["SVC_CODE"])
    svc["INTERVAL_HRS"] = _digits(b["INTERVAL_HRS"])
    svc["INTERVAL_CYC"] = _digits(b["INTERVAL_CYC"])
    svc["INTERVAL_DAY"] = _digits(b["INTERVAL_DAY"])
    svc["REMAINING_HRS"] = _digits(b["REMAINING_HRS"])
    svc["REMAINING_CYC"] = _digits(b["REMAINING_CYC"])
    svc["REMAINING_DAY"] = _digits(b["REMAINING_DAY"])
    svc["FORECAST"] = _clean_join(b["FORECAST"])
    return svc


def _process_block_lines(buckets: list[dict[str, list[str]]], page_index: int,
                          header_meta: dict[str, str]) -> list[dict]:
    """Turn a block's own already-clustered/bucketed lines into output
    records. `buckets[0]` is expected to be the block's own identity line
    1 (that is what `extract()`'s anchor-finding pass looks for). A
    SECOND row1-shaped line is also tolerated mid-block and starts a
    second component within the same call -- confirmed directly necessary
    on the real sample file: `extract()`'s own anchor-finding pass (a
    single whole-page OCR call, see its own docstring) occasionally misses
    one component's own identity-line-1 the same way the per-block re-OCR
    pass recovers a dropped service line, which would otherwise silently
    fold that whole extra component's own identity+service lines into the
    PREVIOUS component's record instead of dropping or misattributing
    them."""
    out: list[dict] = []
    if not buckets:
        return out
    identity = _start_identity(buckets[0])
    svc_count = 0

    for b in buckets[1:]:
        if _DATE_TOKEN_RE.search(" ".join(b["DATE"])):
            if svc_count == 0:
                out.append(_new_record(identity, dict(_EMPTY_SVC), page_index, header_meta))
            identity = _start_identity(b)
            svc_count = 0
            continue
        if _looks_like_svc_line(b):
            out.append(_new_record(identity, _svc_from_bucket(b), page_index, header_meta))
            svc_count += 1
            continue
        # Identity line 2 (PPM/CPN/SERIAL/CSN/CSO) -- only merged once per
        # component; any further unmatched line (noise) is ignored.
        if not identity["PPM_FLAG"] and not identity["SERIAL_NUMBER"]:
            ident_tokens = b["IDENT"]
            if ident_tokens:
                identity["PPM_FLAG"] = ident_tokens[0].strip(_EDGE_STRIP).upper()
                identity["CPN"] = _clean_join(ident_tokens[1:], sep="")
            identity["SERIAL_NUMBER"] = _clean_join(b["PARTNUM"], sep="")
            identity["CSN"] = _digits(b["TSN_CSN"])
            identity["CSO"] = _digits(b["TSO_CSO"])

    if svc_count == 0:
        # No service line recognised at all for the last component in
        # this block (see module docstring) -- still emit exactly one
        # record rather than silently dropping it.
        out.append(_new_record(identity, dict(_EMPTY_SVC), page_index, header_meta))
    return out


# Extra padding (px @ 300 DPI), on top of and below the block's own true
# Y-range, added to the crop actually handed to Tesseract for its per-
# block re-OCR pass (see `extract()`). Generous on purpose -- confirmed
# directly that cropping a block *tightly* to its own true line range
# (no padding at all) sometimes drops its own last service line entirely,
# rather than just misreading it: with the real text sitting only a few
# px above the crop's own bottom edge, Tesseract's page-segmentation step
# apparently discards it as a truncated fragment. This padding gives
# Tesseract normal surrounding context/whitespace on every crop; which
# lines actually get attributed to which block is still decided
# separately, from each recognised line's own absolute Y position against
# the true (unpadded) anchor boundaries (see `_ASSIGN_MARGIN_PX`) -- so
# the generous padding can never cause one block's content to be
# mis-attributed to a neighbouring block.
_CROP_PAD_PX = 60

# Half-open [block_start - margin, next_block_start - margin) window used
# to decide which of a padded crop's own recognised lines belong to THIS
# block (see `_CROP_PAD_PX` above) -- small, just enough to tolerate the
# row-clustering tolerance's own vertical slack at a block's own top/
# bottom edge; confirmed directly narrower than every real gap between a
# block's own last line and the next block's first line on the sample.
_ASSIGN_MARGIN_PX = 10


async def extract(pdf_path: str) -> list[dict]:
    header_meta = await _parse_header(pdf_path)
    records: list[dict] = []
    n_pages = await page_count(pdf_path)

    for page_index in range(n_pages):
        img = await render_page(pdf_path, page_index, dpi=300)
        w, h = img.size

        # Pass 1: a single whole-page OCR call, used ONLY to locate each
        # block's own identity-line-1 Y position (anchored on its own
        # INSTALL_DATE token, which was confirmed reliable under whole-
        # page OCR even where other columns on the same file were not --
        # see below). row1 lines never repeat identical text page to page
        # (every component's own INSTALL_DATE/POSITION/TSN differs), so
        # this anchor-finding pass isn't exposed to the dedup quirk pass 2
        # exists to work around.
        anchor_words = await ocr_words(img, psm=6, min_conf=-1)
        anchor_df = _words_to_df(anchor_words)
        anchors: list[float] = []
        for top, line_words in _group_lines_with_top(anchor_df, w):
            b = _bucket_tokens(line_words, w)
            if _DATE_TOKEN_RE.search(" ".join(b["DATE"])):
                anchors.append(top)
        anchors.sort()

        # Pass 2: re-OCR each block's own Y-band, WITH generous padding
        # for Tesseract's own benefit, in isolation from every other block
        # (see module docstring / `_CROP_PAD_PX` above) -- confirmed
        # directly this recovers service-line tokens that a single whole-
        # page OCR pass silently drops when two components share the same
        # SVC task code and interval values (a real Tesseract line-dedup
        # quirk against near-identical nearby text, not just literally-
        # adjacent repeated lines).
        for i, top in enumerate(anchors):
            block_start = top
            block_end = anchors[i + 1] if i + 1 < len(anchors) else h
            y0 = max(0, int(block_start) - _CROP_PAD_PX)
            y1 = min(h, int(block_end) + _CROP_PAD_PX)
            crop = img.crop((0, y0, w, y1))
            block_words = await ocr_words(crop, psm=6, min_conf=-1)
            bdf = _words_to_df(block_words)
            # Words come back in crop-local coordinates -- shift back to
            # page-absolute before assigning to this block's own true
            # (unpadded) Y-range.
            if not bdf.empty:
                bdf = bdf.copy()
                bdf["top"] = bdf["top"] + y0
            lo = block_start - _ASSIGN_MARGIN_PX
            hi = block_end - _ASSIGN_MARGIN_PX
            lines = [
                lw for ltop, lw in _group_lines_with_top(bdf, w)
                if lo <= ltop < hi
            ]
            if not lines:
                continue
            buckets = [_bucket_tokens(lw, w) for lw in lines]
            # The block's own first assigned line is expected to be its
            # own identity line 1; if row1 landed a few px outside the
            # assignment window and some other noise sorted before it
            # (rare), drop leading lines until the first real row1 is
            # found.
            while buckets and not _DATE_TOKEN_RE.search(" ".join(buckets[0]["DATE"])):
                buckets.pop(0)
            if not buckets:
                continue
            records.extend(_process_block_lines(buckets, page_index, header_meta))

    return records
