"""Aircraft OC/CM Components Status -- scanned, no text layer, OCR required.

Confirmed on one real sample file (29 pages, 0 pdfplumber-extractable chars
on any page checked). Header repeats identically on every page::

    AIRCRAFT OC/CM COMPONENTS STATUS
    <type>
    Actual FH <fh> MSN <msn>
    Actual FC <fc> Registration <reg>
    Date <date> Prod No: <prod_no>

followed by a two-line-wrapped column header row and a ruled data grid.
The header band also carries a faint diagonal watermark that OCRs as
scattered lowercase noise tokens (single letters, short nonsense words) --
harmless, but it means the header can't be parsed by joining the whole
band's text naively; anchor words are matched positionally instead (see
`_parse_header`).

Row shape confirmed by rendering the real file at 300 DPI and inspecting
`ocr_words()` bounding boxes directly across multiple pages (front,
middle, back) -- stable throughout, since every page renders the same
ruled grid at the same pixel offsets. Column x-position bucketing (same
technique as `aircraft_build_occm_status_scanned.py`) resolves each row
into 10 fixed x-ranges: ATA, PART_NUMBER, SERIAL_NUMBER, DESCRIPTION,
POSITION, INSTALL_DATE, then four trailing numeric cells.

Those four trailing numeric cells were NOT assumed from the rough header
OCR -- they were verified arithmetically against the real file. For a row
whose component was installed after the aircraft entered service, the
first pair reads as the aircraft's own hours/cycles *at the time of that
row's install* (i.e. non-zero, and less than the header's own Actual
FH/FC), while the second pair reads as hours/cycles *since that install*
-- confirmed directly: header Actual FH minus that row's own first-pair
hours value equals its own second-pair hours value to the reported
precision, and the same holds for cycles. For the (large majority of)
rows installed at/near aircraft manufacture, the first pair reads as
zero and the second pair equals the header's own Actual FH/FC exactly --
consistent with the same two pairs, just installed at time zero. So the
four columns are genuinely distinct (HOURS_AT_INSTALL, CYCLES_AT_INSTALL,
HOURS_SINCE_INSTALL, CYCLES_SINCE_INSTALL), not a header/OCR-pass
conflation of one pair into two.

ATA occasionally OCRs merged with the following PART_NUMBER cell into one
token (no visible gap between the two cells at that row's scan
resolution) -- confirmed directly, e.g. a two-digit chapter code glued to
the front of the part number with a single stray letter or bracket
between them. `_split_ata_part_number` recovers the leading two-digit
code via a narrow leading-digit-run pattern; when that pattern doesn't
match cleanly, the raw merged cell is kept verbatim in STATUS_TRAIL
("ATA/PN cell (unparsed): ...") and ATA/PART_NUMBER are left as
best-effort splits (or empty) rather than guessing a wrong split, per
this project's convention.

Header metadata (AIRCRAFT_TYPE, ACTUAL_FH, MSN, ACTUAL_FC, AIRCRAFT_REG,
REPORT_DATE, PROD_NO) is parsed once from page 1 and stamped onto every
row, per this project's header-parsing convention -- not re-OCR'd per
page, so a single clean read is reused consistently.
"""
from __future__ import annotations
import re

from sheet_types.occm_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_words, ocr_text, page_count

NAME = "Aircraft OC/CM Components Status (Scanned)"

# Deliberately empty -- the known source file has no text layer at all
# (confirmed: 0 pdfplumber-extractable chars on every page sampled), so
# this module is only ever reached via ocr_detect()'s blank-text fallback
# below, never the router's normal pdfplumber-text SIGNATURES match.
SIGNATURES = []

CANONICAL_COLUMNS = [
    "ATA",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
    "POSITION",
    "INSTALL_DATE",
    "HOURS_AT_INSTALL",
    "CYCLES_AT_INSTALL",
    "HOURS_SINCE_INSTALL",
    "CYCLES_SINCE_INSTALL",
    "STATUS_TRAIL",
    # Header metadata -- parsed once from page 1, stamped onto every row.
    "AIRCRAFT_TYPE",
    "ACTUAL_FH",
    "MSN",
    "ACTUAL_FC",
    "AIRCRAFT_REG",
    "REPORT_DATE",
    "PROD_NO",
]

_OVERRIDES = {
    # ATA/PART_NUMBER/SERIAL_NUMBER/DESCRIPTION already have generic global
    # rules; loosen with allow_empty since a merged/garbled OCR cell should
    # be visible via STATUS_TRAIL rather than a hard failure with no value.
    "ATA": {"allow_empty": True},
    "PART_NUMBER": {"allow_empty": True},
    "SERIAL_NUMBER": {"allow_empty": True},
    "DESCRIPTION": {"allow_empty": True},
    "POSITION": {"pattern": r"^[A-Z0-9 /]{0,15}$", "uppercase": True, "allow_empty": True},
    # OCR renders the date inconsistently (a digit dropped/misread, e.g. a
    # leading "1" of "1999" lost) -- loose on purpose; a meaningful flag
    # rate here is expected given the source is a scan.
    "INSTALL_DATE": {"pattern": r"^\d{2,4}-\d{2}-\d{2}$", "allow_empty": True},
    "HOURS_AT_INSTALL": {"pattern": r"^[\d,]+(\.\d+)?$", "allow_empty": True},
    "CYCLES_AT_INSTALL": {"pattern": r"^[\d,]+(\.\d+)?$", "allow_empty": True},
    "HOURS_SINCE_INSTALL": {"pattern": r"^[\d,]+(\.\d+)?$", "allow_empty": True},
    "CYCLES_SINCE_INSTALL": {"pattern": r"^[\d,]+(\.\d+)?$", "allow_empty": True},
    "STATUS_TRAIL": {"allow_empty": True},
    # Header metadata -- generic shape checks only (never tied to any one
    # real file's specific values), allow_empty since a header-parse miss
    # should never mass-flag every row over one shared stamped value (see
    # module docstring: a single OCR misread here would otherwise flag
    # every row identically, a misleading near-100% rate for what is
    # genuinely just one stamped field, not per-row corruption).
    "AIRCRAFT_TYPE": {"pattern": r"^[A-Z0-9][A-Z0-9\-]{1,10}$", "uppercase": True, "allow_empty": True},
    "ACTUAL_FH": {"allow_empty": True},
    "MSN": {"pattern": r"^\d{3,6}$", "allow_empty": True},
    "ACTUAL_FC": {"allow_empty": True},
    "AIRCRAFT_REG": {"pattern": r"^[A-Z0-9]{1,3}-[A-Z0-9]{2,6}$", "uppercase": True, "allow_empty": True},
    "REPORT_DATE": {"allow_empty": True},
    "PROD_NO": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Fixed column x-ranges (pixels @ 300 DPI), confirmed by direct word-box
# inspection against the real sample across multiple pages (front, middle,
# back) -- stable throughout, since every page renders the same ruled grid
# at the same offsets. 10 buckets: ATA, PART_NUMBER, SERIAL_NUMBER,
# DESCRIPTION, POSITION, INSTALL_DATE, HOURS_AT_INSTALL,
# CYCLES_AT_INSTALL, HOURS_SINCE_INSTALL, CYCLES_SINCE_INSTALL.
_BOUNDS = [0, 330, 770, 1090, 1870, 2140, 2440, 2700, 2910, 3105, 10 ** 6]
_N_BUCKETS = len(_BOUNDS) - 1

_BORDER_RE = re.compile(r"[|\[\]{}<>=~()`*\"'«»‘’“”–—]+")
_SEP_RUN_RE = re.compile(r"_+|\.{3,}|-{3,}")
_ATA_RE = re.compile(r"^\d{2}$")
_ATA_MERGED_RE = re.compile(r"^[A-Za-z]{0,2}(\d{2})\s*(.*)$")
_NUMERIC_SPACE_RE = re.compile(r"(?<=\d)\s+(?=[\d,])")


def _clean_bucket(text: str) -> str:
    s = _SEP_RUN_RE.sub(" ", _BORDER_RE.sub(" ", text))
    return " ".join(s.split()).strip()


def _clean_numeric(text: str) -> str:
    # Numeric cells occasionally OCR with a stray internal space (a big
    # number split across two word boxes) -- close that gap, since it's
    # genuinely one value, not two.
    return _NUMERIC_SPACE_RE.sub("", _clean_bucket(text))


def _group_lines(words: list[dict], tol: float = 13.0) -> list[list[dict]]:
    """Cluster OCR words into physical lines by Y proximity. ocr_words()
    carries no block/line grouping of its own, so lines are recovered
    geometrically (same technique as the other scanned OCCM variants in
    this package)."""
    ws = sorted(words, key=lambda w: (w["top"], w["left"]))
    lines: list[dict] = []
    for w in ws:
        if lines and abs(w["top"] - lines[-1]["top"]) <= tol:
            lines[-1]["words"].append(w)
        else:
            lines.append({"top": w["top"], "words": [w]})
    for line in lines:
        line["words"].sort(key=lambda w: w["left"])
    return [line["words"] for line in lines]


def _bucket(words: list[dict]) -> list[str]:
    buckets: list[list[str]] = [[] for _ in range(_N_BUCKETS)]
    for w in words:
        center = w["left"] + w["width"] / 2
        for i in range(_N_BUCKETS):
            if _BOUNDS[i] <= center < _BOUNDS[i + 1]:
                buckets[i].append(w["text"])
                break
    return [" ".join(b) for b in buckets]


def _split_ata_part_number(ata_raw: str, pn_raw: str) -> tuple[str, str, str]:
    """Returns (ata, part_number, status_trail_note). Handles the confirmed
    OCR quirk where the ATA chapter code glues onto the front of the
    PART_NUMBER cell when the source grid has no visible gap between the
    two cells at that row (see module docstring)."""
    clean_ata = _clean_bucket(ata_raw)
    clean_pn = _clean_bucket(pn_raw)
    if _ATA_RE.match(clean_ata):
        return clean_ata, clean_pn, ""
    m = _ATA_MERGED_RE.match(clean_pn)
    if m and not clean_ata:
        return m.group(1), m.group(2), ""
    # Genuinely ambiguous -- keep both raw cells visible rather than guess.
    merged = " ".join(t for t in (clean_ata, clean_pn) if t)
    note = f"ATA/PN cell (unparsed): {merged}" if merged else ""
    return clean_ata, clean_pn, note


def _new_record(b: list[str]) -> dict:
    ata, part_number, note = _split_ata_part_number(b[0], b[1])
    rec = {c: "" for c in CANONICAL_COLUMNS}
    rec["ATA"] = ata
    rec["PART_NUMBER"] = part_number
    rec["SERIAL_NUMBER"] = _clean_bucket(b[2])
    rec["DESCRIPTION"] = _clean_bucket(b[3])
    rec["POSITION"] = _clean_bucket(b[4])
    rec["INSTALL_DATE"] = _clean_bucket(b[5])
    rec["HOURS_AT_INSTALL"] = _clean_numeric(b[6])
    rec["CYCLES_AT_INSTALL"] = _clean_numeric(b[7])
    rec["HOURS_SINCE_INSTALL"] = _clean_numeric(b[8])
    rec["CYCLES_SINCE_INSTALL"] = _clean_numeric(b[9])
    rec["STATUS_TRAIL"] = note
    return rec


def _looks_like_row(b: list[str]) -> bool:
    """A row is only opened once we can plausibly locate an ATA chapter
    code somewhere in the ATA or (merged) PART_NUMBER cell -- otherwise
    the line is header/footer/watermark noise, not a data row."""
    clean_ata = _clean_bucket(b[0])
    if _ATA_RE.match(clean_ata):
        return True
    return bool(_ATA_MERGED_RE.match(_clean_bucket(b[1])) and not clean_ata)


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback.
    Anchors on the bare "AIRCRAFT OC/CM COMPONENTS STATUS" title phrase --
    checked directly (grep across every SIGNATURES list in
    sheet_types/{occm,ht,llp}.py and every existing occm_variants file):
    no other module's own SIGNATURES/ocr_detect anchor is this phrase, nor
    a substring of it, nor does it contain any other module's own anchor
    (in particular occm_status_list.py's "OCCM COMPONENTS STATUS LIST" /
    "COMPONENTS STATUS LIST" both carry the word LIST, which this phrase
    never has, and aircraft_occm_list_scanned.py's own anchor "AIRCRAFT
    OC/CM LIST" is missing "COMPONENTS STATUS" entirely)."""
    try:
        img = await render_page(pdf_path, 0, dpi=300)
        w, h = img.size
        crop = img.crop((0, 0, w, int(h * 0.14)))
        text = (await ocr_text(crop, psm=6)).upper()
        return "AIRCRAFT" in text and "OC/CM" in text and "COMPONENTS" in text and "STATUS" in text
    except Exception:
        return False


def _norm(token: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", token.upper())


async def _parse_header(pdf_path: str) -> dict:
    """Parse the header metadata block once from page 1 and return it for
    stamping onto every row -- see module docstring. Matched positionally
    (anchor word -> very next word on the same OCR'd line) rather than by
    joining the band's text, since the watermark noise breaks up naive
    text-join parsing (see module docstring)."""
    meta = {
        "AIRCRAFT_TYPE": "", "ACTUAL_FH": "", "MSN": "", "ACTUAL_FC": "",
        "AIRCRAFT_REG": "", "REPORT_DATE": "", "PROD_NO": "",
    }
    try:
        img = await render_page(pdf_path, 0, dpi=300)
        w, h = img.size
        crop = img.crop((0, 0, w, int(h * 0.30)))
        words = await ocr_words(crop, psm=6, min_conf=-1)
    except Exception:
        return meta
    lines = _group_lines(words)

    title_seen = False
    type_line_words: list[dict] | None = None
    for line in lines:
        joined = " ".join(w["text"] for w in line).upper()
        if "AIRCRAFT" in joined and "STATUS" in joined and "OC" in joined:
            title_seen = True
            continue
        if title_seen and type_line_words is None and any(_norm(w["text"]) for w in line):
            # First line after the title that isn't itself an anchor line
            # (Actual FH / Actual FC / Date) is a candidate for the type
            # line -- confirmed real layout: type sits alone right under
            # the title, before the Actual FH line.
            normed = [_norm(w["text"]) for w in line]
            if "ACTUAL" in normed or "FH" in normed:
                pass  # already past the type line -- fall through below
            else:
                type_line_words = line
                continue

        toks = [w["text"] for w in line]
        normed = [_norm(t) for t in toks]
        for i, nt in enumerate(normed):
            if nt == "FH" and i + 1 < len(toks) and not meta["ACTUAL_FH"]:
                meta["ACTUAL_FH"] = toks[i + 1]
            elif nt == "MSN" and i + 1 < len(toks) and not meta["MSN"]:
                meta["MSN"] = toks[i + 1]
            elif nt == "FC" and i + 1 < len(toks) and not meta["ACTUAL_FC"]:
                meta["ACTUAL_FC"] = toks[i + 1]
            elif nt == "REGISTRATION" and i + 1 < len(toks) and not meta["AIRCRAFT_REG"]:
                meta["AIRCRAFT_REG"] = toks[i + 1]
            elif nt == "DATE" and i + 1 < len(toks) and not meta["REPORT_DATE"]:
                meta["REPORT_DATE"] = toks[i + 1]
            elif "PRODNO" in nt and i + 1 < len(toks) and not meta["PROD_NO"]:
                meta["PROD_NO"] = toks[i + 1]
            elif nt == "NO" and i + 1 < len(toks) and not meta["PROD_NO"]:
                meta["PROD_NO"] = toks[i + 1]

    if type_line_words:
        # Pick the token that looks like a real type designator (uppercase
        # alnum with at least one digit) rather than watermark noise
        # (which OCRs lowercase in the known real sample).
        for w in sorted(type_line_words, key=lambda w: w["left"]):
            tok = w["text"].strip(" .,:;\"'")
            if re.match(r"^[A-Z0-9][A-Z0-9\-]{1,9}$", tok) and any(c.isdigit() for c in tok):
                meta["AIRCRAFT_TYPE"] = tok
                break

    for key in ("ACTUAL_FH", "ACTUAL_FC"):
        meta[key] = _clean_bucket(meta[key])
    return meta


async def extract(pdf_path: str) -> list[dict]:
    header_meta = await _parse_header(pdf_path)
    records: list[dict] = []
    n_pages = await page_count(pdf_path)
    for page_index in range(n_pages):
        img = await render_page(pdf_path, page_index, dpi=300)
        words = await ocr_words(img, psm=6, min_conf=-1)
        for line_words in _group_lines(words):
            b = _bucket(line_words)
            if not _looks_like_row(b):
                continue
            rec = _new_record(b)
            rec["_page"] = page_index + 1
            rec.update(header_meta)
            records.append(rec)
    return records
