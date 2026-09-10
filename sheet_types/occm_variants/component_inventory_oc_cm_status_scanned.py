"""Component Inventory (OC/CM Status) -- scanned, no text layer, OCR
required throughout.

Confirmed on one real corpus file (23 pages, 0 pdfplumber-extractable
chars on any page checked -- every page is a single embedded landscape
scan image, no text layer at all). Header (repeats verbatim on every
page, two lines)::

    ACFT: <reg>   S/N <msn>        COMPONENT INVENTORY - OC / CM       STATUS DATE: <date>
    TSN <n>       CSN <n>                     <type>

...followed by a ruled data grid whose column-header row reads::

    PPM  Config Slot   KEYWORD   PARTNUMBER   SERIAL   -----INSTALLATION-----   TSN CSN TSO CSO
                                                        DATE  POSITION

Per-row layout, all fixed-position columns on a single physical OCR line::

    <PPM> <Config Slot> [<KEYWORD>] [D] <PARTNUMBER> <SERIAL> <DATE> <POSITION> <TSN> <CSN> <TSO> <CSO>

Fields, confirmed directly against the real sample file:

  - PPM: literally "OC" or "CM" on every genuine data row -- this is the
    report's own row-type flag and doubles as this module's row anchor
    (see `_looks_like_row`), since section-banner rows (a lone ATA chapter
    digit, e.g. "21", rendered in the same left-hand column on a shaded
    banner row separating chapters) never carry this value.
  - CONFIG_SLOT: a compound code, confirmed shaped
    `<ata>-<subchapter>-<code>-<seq>` (occasionally a shorter/irregular
    tail, e.g. an engine-position row's own literal `<ata>-00-ENG`) --
    the leading 2-digit group is always the genuine ATA chapter, pulled
    into its own ATA column the same way this package's other
    compound-code OCCM variants do (see `fl_compound_code_occm.py`,
    `componentes_oc_cm.py`). CONFIG_SLOT itself is kept verbatim too.
  - KEYWORD: free-text part description. Confirmed genuinely blank on
    many rows -- a component installed in more than one position (e.g.
    two of the same recirculation fan, or left/right pairs) repeats its
    own CONFIG_SLOT on a second row directly below with an empty KEYWORD,
    since the description was already given on the row above. This is
    NOT a parse failure; RULES allows it empty.
  - The single-letter "D" column between KEYWORD and PARTNUMBER carries
    no column-header label of its own in the source (confirmed directly:
    the header row's own column captions -- "PPM Config Slot KEYWORD
    PARTNUMBER SERIAL ..." -- have no caption positioned above this
    narrow band), and only some rows populate it. Since its meaning isn't
    documented anywhere in the source and guessing would risk asserting
    something false, it's kept as a literal, unlabeled flag column
    (D_FLAG) rather than given an invented semantic name.
  - PARTNUMBER / SERIAL: as per the header order.
  - DATE (INSTALL_DATE): `D-Mon-YY` (single or double-digit day).
  - POSITION: free-form position/zone code (e.g. a side + numeric +
    suffix code), kept verbatim.
  - TSN / CSN / TSO / CSO: the four numeric life-basis columns under the
    "INSTALLATION" group header -- time/cycles since new, and time/cycles
    since overhaul, confirmed directly against the header row's own
    column captions.

Header metadata (AIRCRAFT_REG, MSN, AIRCRAFT_TYPE, ACTUAL_TSN, ACTUAL_CSN,
STATUS_DATE) is parsed once from page 1 and stamped onto every row, per
this package's usual convention -- not re-OCR'd per page, since a single
clean read is reused consistently and a misread here would otherwise flag
every row identically rather than surfacing genuine per-row corruption.
AIRCRAFT_REG is located by content shape (a short letter(s)-hyphen-code
token) rather than by anchoring on the "ACFT" label word itself, since
that label is confirmed to OCR unreliably (seen rendered as "*CFT",
"“CFD" and other garbled variants across pages of the real sample
file) while the registration token's own shape is distinctive and stable.

OCR approach: `ocr_words()` (word-level bounding boxes, `min_conf=-1`
since real cells on this file score under Tesseract's default conf>30
filter on a meaningful fraction of rows) + geometric line-clustering by
Y-coordinate (same technique as this package's other scanned OCCM
variants). The Y-clustering tolerance is widened to 30px here (row
spacing on this file is a stable ~66-70px) rather than the tighter ~13-18px
used elsewhere in this package: confirmed directly against the real
sample file that a small number of individual OCR word boxes (never a
whole row) land with their own `top` offset by as much as ~23px from the
rest of their own visual row -- e.g. one word of a two-word KEYWORD phrase,
or an entire PARTNUMBER token, rendering visibly on the very same printed
line as the rest of that row's cells when the page image itself is
inspected directly. A tighter tolerance would incorrectly split those
words into their own phantom line; the widened tolerance still comfortably
clears the real ~66-70px gap between genuine adjacent rows.

Column X-boundaries (px @ 300 DPI) were measured directly from real OCR
word `left`/`width` boxes across three widely-separated pages of the real
sample file (first, one in the middle third, last) -- stable throughout,
since every page renders the same ruled grid at the same offsets.
"""
from __future__ import annotations
import re

import pandas as pd

from sheet_types.occm_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, ocr_words, page_count

NAME = "Component Inventory (OC/CM Status, Scanned)"

# Deliberately empty -- the known source file has no text layer at all
# (confirmed: 0 pdfplumber-extractable chars on every page), so this
# module is only ever reached via ocr_detect()'s blank-text fallback
# below, never the router's normal pdfplumber-text SIGNATURES match.
SIGNATURES = []

CANONICAL_COLUMNS = [
    "PPM_FLAG",
    "CONFIG_SLOT",
    "ATA",
    "KEYWORD",
    "D_FLAG",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "INSTALL_DATE",
    "POSITION",
    "TSN",
    "CSN",
    "TSO",
    "CSO",
    # Header metadata -- parsed once from page 1, stamped onto every row.
    "AIRCRAFT_REG",
    "MSN",
    "AIRCRAFT_TYPE",
    "ACTUAL_TSN",
    "ACTUAL_CSN",
    "STATUS_DATE",
]

_AMOUNT_RULE = {"pattern": r"^[\d,]+$", "allow_empty": True}

_OVERRIDES = {
    "PPM_FLAG": {"pattern": r"^(OC|CM)$", "uppercase": True},
    # Compound code shape is fairly stable (see module docstring) but a
    # meaningful minority of rows garble it under OCR -- loose pattern,
    # allow_empty per this project's "never guess a wrong split" convention.
    "CONFIG_SLOT": {"pattern": r"^\d{2}-[A-Z0-9\-]*$", "uppercase": True, "allow_empty": True},
    # ATA already has a suitable global rule (pattern + int_range 20-83);
    # loosened with allow_empty since a row whose CONFIG_SLOT didn't OCR
    # cleanly enough to yield a leading chapter code should rely on
    # occm.normalize_and_validate()'s forward_fill_ata() rather than a hard
    # per-row failure.
    "ATA": {"allow_empty": True},
    "KEYWORD": {"allow_empty": True},
    # Unlabeled single-letter column (see module docstring) -- no fixed
    # shape to validate, informational only.
    "D_FLAG": {"pattern": r"^[A-Z]{0,2}$", "uppercase": True, "allow_empty": True},
    # PART_NUMBER / SERIAL_NUMBER already have suitable global rules keyed
    # by these exact column names; loosened with allow_empty since a
    # garbled OCR cell should surface as a visible bad_format/empty flag on
    # this scan, not a silent drop.
    "PART_NUMBER": {"allow_empty": True},
    "SERIAL_NUMBER": {"allow_empty": True},
    # D-Mon-YY(YY), single or double-digit day -- confirmed both seen on
    # the real sample file.
    "INSTALL_DATE": {"pattern": r"^\d{1,2}-[A-Za-z]{3}-\d{2,4}$", "allow_empty": True},
    "POSITION": {"pattern": r"^[A-Z0-9\-]{0,20}$", "uppercase": True, "allow_empty": True},
    "TSN": _AMOUNT_RULE,
    "CSN": _AMOUNT_RULE,
    "TSO": _AMOUNT_RULE,
    "CSO": _AMOUNT_RULE,
    # Header metadata -- generic shape checks only (never tied to any one
    # real file's specific values), allow_empty since a header-parse miss
    # should never mass-flag every row over one shared stamped value (see
    # module docstring).
    "AIRCRAFT_REG": {"pattern": r"^[A-Z0-9]{1,3}-[A-Z0-9]{2,6}$", "uppercase": True, "allow_empty": True},
    "MSN": {"pattern": r"^\d{3,6}$", "allow_empty": True},
    "AIRCRAFT_TYPE": {"pattern": r"^[A-Z][A-Z0-9]{2,5}$", "uppercase": True, "allow_empty": True},
    "ACTUAL_TSN": _AMOUNT_RULE,
    "ACTUAL_CSN": _AMOUNT_RULE,
    "STATUS_DATE": {"pattern": r"^\d{1,2}-[A-Za-z]{3}-\d{2,4}$", "allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Column X-boundaries (px @ 300 DPI) -- see module docstring. Boundaries
# sit in the wide gaps confirmed directly between each pair of adjacent
# columns' own observed word positions (start/end) across three
# widely-separated pages of the real sample file, not merely at one
# column's own edge, so ordinary page-to-page OCR jitter can't shift a
# genuine value across a boundary.
_COLUMNS = [
    (0, 140, "PPM_FLAG"),
    (140, 650, "CONFIG_SLOT"),
    (650, 1310, "KEYWORD"),
    (1310, 1370, "D_FLAG"),
    (1370, 1745, "PART_NUMBER"),
    (1745, 2105, "SERIAL_NUMBER"),
    (2105, 2310, "INSTALL_DATE"),
    (2310, 2700, "POSITION"),
    (2700, 2860, "TSN"),
    (2860, 3020, "CSN"),
    (3020, 3170, "TSO"),
    (3170, 10 ** 6, "CSO"),
]
_JOIN_WITH_SPACE = {"KEYWORD"}

_BORDER_RE = re.compile(r"[|\[\]{}<>=~()`*\"'«»‘’“”–—_]+")
_SEP_RUN_RE = re.compile(r"_{2,}|\.{3,}|-{3,}")
_EDGE_STRIP = " _-|[]=~.\"'"

_ATA_LEADING_RE = re.compile(r"^(\d{2})-")
_PPM_RE = re.compile(r"^(OC|CM)$")


def _clean_bucket(text: str) -> str:
    s = _SEP_RUN_RE.sub(" ", _BORDER_RE.sub(" ", text))
    return " ".join(s.split()).strip(_EDGE_STRIP)


def _words_to_df(words: list[dict]) -> pd.DataFrame:
    cols = ["left", "top", "width", "height", "conf", "text"]
    df = pd.DataFrame(words, columns=cols) if words else pd.DataFrame(columns=cols)
    if not df.empty:
        df = df.dropna(subset=["text"])
        df = df[df["text"].astype(str).str.strip() != ""]
    return df


def _group_lines(df: pd.DataFrame):
    """Cluster words into text-lines by Y coordinate -- 30px tolerance, not
    this package's more usual ~13-18px (see module docstring for why this
    file specifically needs the wider band)."""
    if df.empty:
        return []
    df = df.sort_values(["top", "left"]).reset_index(drop=True)
    df["row_id"] = (df["top"].diff().fillna(0).abs() > 30).cumsum()
    groups = []
    for _, g in df.groupby("row_id"):
        g = g.sort_values("left")
        words = list(zip(g["left"], g["text"].astype(str)))
        groups.append((g["top"].mean(), words))
    groups.sort(key=lambda t: t[0])
    return [words for _, words in groups]


def _bucket(words: list[tuple[float, str]]) -> dict[str, str]:
    buckets: dict[str, list[str]] = {name: [] for _, _, name in _COLUMNS}
    for left, text in words:
        for lo, hi, name in _COLUMNS:
            if lo <= left < hi:
                buckets[name].append(text)
                break
    return {
        name: _clean_bucket(" ".join(vals) if name in _JOIN_WITH_SPACE else "".join(vals))
        for name, vals in buckets.items()
    }


def _looks_like_row(b: dict[str, str]) -> bool:
    """A row is only opened once PPM_FLAG cleanly reads "OC" or "CM" --
    section-banner rows (a bare ATA chapter digit) and the repeated
    column-header row never satisfy this (see module docstring)."""
    return bool(_PPM_RE.match(b["PPM_FLAG"].strip().upper()))


def _new_record(b: dict[str, str]) -> dict:
    config_slot = b["CONFIG_SLOT"]
    m = _ATA_LEADING_RE.match(config_slot)
    ata = m.group(1) if m else ""
    rec = {c: "" for c in CANONICAL_COLUMNS}
    rec["PPM_FLAG"] = b["PPM_FLAG"].strip().upper()
    rec["CONFIG_SLOT"] = config_slot
    rec["ATA"] = ata
    rec["KEYWORD"] = b["KEYWORD"]
    rec["D_FLAG"] = b["D_FLAG"]
    rec["PART_NUMBER"] = b["PART_NUMBER"]
    rec["SERIAL_NUMBER"] = b["SERIAL_NUMBER"]
    rec["INSTALL_DATE"] = b["INSTALL_DATE"]
    rec["POSITION"] = b["POSITION"]
    rec["TSN"] = b["TSN"]
    rec["CSN"] = b["CSN"]
    rec["TSO"] = b["TSO"]
    rec["CSO"] = b["CSO"]
    return rec


# --- Header metadata parsing --------------------------------------------
# AIRCRAFT_REG is matched by content shape (see module docstring on why
# the "ACFT" label itself is unreliable): a short alnum-hyphen-alnum
# token, distinct from any other header token's own shape (dates carry a
# 3-letter month abbreviation; TSN/CSN/MSN are pure digit runs).
_REG_RE = re.compile(r"^[A-Z0-9]{1,3}-[A-Z0-9]{2,6}$")
_TYPE_RE = re.compile(r"^[A-Z][A-Z0-9]{2,5}$")
_DATE_RE = re.compile(r"^\d{1,2}-[A-Za-z]{3}-\d{2,4}$")


def _norm(token: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", token.upper())


async def _parse_header(pdf_path: str) -> dict:
    """Parse the header metadata block once from page 1 and return it for
    stamping onto every row -- see module docstring."""
    meta = {
        "AIRCRAFT_REG": "", "MSN": "", "AIRCRAFT_TYPE": "",
        "ACTUAL_TSN": "", "ACTUAL_CSN": "", "STATUS_DATE": "",
    }
    try:
        img = await render_page(pdf_path, 0, dpi=300)
        w, h = img.size
        crop = img.crop((0, 0, w, int(h * 0.18)))
        words = await ocr_words(crop, psm=6, min_conf=-1)
    except Exception:
        return meta

    df = _words_to_df(words)
    # Drop pure-symbol noise tokens (e.g. a stray "*" the operator logo's
    # own artwork OCRs as) before line-clustering -- confirmed directly on
    # the real sample file: one such token lands, by Y position alone,
    # almost exactly halfway between the ACFT/S-N title row and the
    # TSN/CSN row below it, close enough to each that the cumulative
    # Y-diff clustering below never sees a jump bigger than its own
    # threshold and merges both real rows (plus the title) into one,
    # scrambling every field's left-to-right token order. A real header
    # token always carries at least one letter or digit; this noise
    # token doesn't, so filtering on that is safe.
    if not df.empty:
        has_alnum = df["text"].astype(str).str.contains(r"[A-Za-z0-9]", regex=True)
        df = df[has_alnum]
    for line_words in _group_lines(df):
        toks = [t for _l, t in line_words]
        normed = [_norm(t) for t in toks]
        for i, tok in enumerate(toks):
            clean = tok.strip(" .,:;\"'")
            if not meta["AIRCRAFT_REG"] and _REG_RE.match(clean.upper()):
                meta["AIRCRAFT_REG"] = clean.upper()
                continue
            if not meta["MSN"] and normed[i] in ("SN", "SIN") and i + 1 < len(toks):
                cand = _norm(toks[i + 1])
                if cand.isdigit():
                    meta["MSN"] = cand
            if not meta["ACTUAL_TSN"] and normed[i] == "TSN" and i + 1 < len(toks):
                meta["ACTUAL_TSN"] = _norm(toks[i + 1])
            if not meta["ACTUAL_CSN"] and normed[i] == "CSN" and i + 1 < len(toks):
                meta["ACTUAL_CSN"] = _norm(toks[i + 1])
            if not meta["STATUS_DATE"] and _DATE_RE.match(clean):
                meta["STATUS_DATE"] = clean
            if not meta["AIRCRAFT_TYPE"] and _TYPE_RE.match(clean.upper()) \
                    and any(c.isdigit() for c in clean) and normed[i] not in ("SN", "SIN"):
                meta["AIRCRAFT_TYPE"] = clean.upper()
    return meta


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback.
    Anchors on "COMPONENT INVENTORY" combined with the "OC / CM" title
    fragment (spaces around the slash tolerated). Checked directly (grep
    across every SIGNATURES list in sheet_types/{occm,ht,llp}.py and every
    existing occm_variants file): no other module's own SIGNATURES/
    ocr_detect anchor combines "COMPONENT INVENTORY" with this "OC / CM"
    phrase -- in particular occm_component_inventory_list_scanned.py's own
    anchor ("COMPONENT INVENTORY LIST" + "A/C HOURS") has no "OC"/"CM"
    fragment at all, occm_component_inventory.py's own title
    ("OCCM COMPONENT INVENTORY") has no space-separated "OC / CM", and
    componentes_oc_cm.py's own anchor ("COMPONENTES" + "OC/CM") is the
    Spanish spelling ("COMPONENTES", not "COMPONENT INVENTORY") with no
    space around the slash.
    """
    try:
        img = await render_page(pdf_path, 0, dpi=300)
        w, h = img.size
        crop = img.crop((0, 0, w, int(h * 0.18)))
        text = (await ocr_text(crop, psm=6)).upper()
        return "COMPONENT INVENTORY" in text and bool(re.search(r"OC\s*/\s*CM", text))
    except Exception:
        return False


async def extract(pdf_path: str) -> list[dict]:
    header_meta = await _parse_header(pdf_path)
    records: list[dict] = []
    n_pages = await page_count(pdf_path)
    for page_index in range(n_pages):
        img = await render_page(pdf_path, page_index, dpi=300)
        words = await ocr_words(img, psm=6, min_conf=-1)
        df = _words_to_df(words)
        for line_words in _group_lines(df):
            b = _bucket(line_words)
            if not _looks_like_row(b):
                continue
            rec = _new_record(b)
            rec["_page"] = page_index + 1
            rec.update(header_meta)
            records.append(rec)
    return records
