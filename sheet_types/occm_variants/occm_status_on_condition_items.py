"""On Condition Items (OCCM Status) -- scanned, no text layer, OCR required
throughout.

Confirmed on a real corpus sample file (real-corpus triage): every page is a
flat scanned image with no extractable text layer at all (confirmed via the
router's own pdfplumber head-text check returning "Unknown" -- fewer than 50
chars recovered on the first pages), so this module renders each page and
OCRs it directly via the async OCR bridge (`shared/ocr_bridge.py`), same
approach as this project's other scanned OCCM variants (e.g.
`aircraft_fitlist_occm.py`, `occm_list_func_loc_scanned.py`).

Header block (first page, repeats verbatim -- confirmed directly -- on every
following page)::

    ON CONDITION ITEMS
    <operator name>
    AIRCRAFT: <reg>
    SERIAL NUMBER: <msn>
    MODEL: <type>
    TSN: <n>
    CSN: <n>

The operator name printed in the header is intentionally NOT extracted into
a column here (out of scope for this module; the report's own aircraft
registration/MSN/model/TSN/CSN fields are already enough to identify a file,
and per this project's data-sensitivity policy operator names are never
worth stamping into extracted data anyway). Parsed once via a word-level OCR
pass over the header band (`ocr_words(..., psm=11)`, confirmed to separate
the label/value pairs far more reliably than a plain `ocr_text` pass on this
header, whose "<operator name>" line visually overlaps the "MODEL:" line and
badly confuses a line-mode OCR pass -- confirmed directly) and stamped on
every row as AIRCRAFT_REG / MSN / AC_MODEL / HEADER_TSN / HEADER_CSN, per
this project's convention for header-plus-body OCCM variants.

Column header row (confirmed directly against the real rendered page)::

    ATA | Partno | Serialno | Description | Pos | Inst-Date | CSN | TSN

Note the column order here: CSN comes BEFORE TSN, unlike some sibling OCCM
formats in this package where TSN precedes CSN -- confirmed directly against
the real rendered header row and multiple real data rows, not assumed from a
rough OCR pass. A data row's tokens, in column order: ATA, PART_NUMBER,
SERIAL_NUMBER, DESCRIPTION (free text), POSITION, INSTALL_DATE, CSN, TSN.

The report renders as a ruled ("pipe-bordered") table, but OCR of the ruling
lines is unreliable as a column delimiter (confirmed directly: the vertical
rule glyphs are inconsistently recognised as literal "|" characters, and
border-artifact glyphs -- stray "_", "=", em/en-dash runs -- routinely fuse
onto adjacent cell text, especially around the POSITION cell). Row parsing
therefore does NOT split on "|"; instead each OCR text line has border/rule
noise characters stripped, is tokenized on whitespace, and is parsed via
anchors from both ends:

    * ATA: the leading token, when it is a bare 1-2 digit chapter number.
      Confirmed directly that a meaningful fraction of real rows do NOT
      carry a leading ATA at all -- the chapter is only re-printed at the
      start of each new chapter's first row on this file's real pages, not
      forward-filled by the source report itself. Rather than drop those
      rows, ATA is left empty and PART_NUMBER/SERIAL_NUMBER/DESCRIPTION/
      POSITION are parsed starting from the row's first token instead; the
      router's own generic `forward_fill_ata` post-process (see
      `sheet_types/occm.py`, applied whenever "ATA" is a canonical column)
      then recovers the chapter from the most recently seen valid row.
    * INSTALL_DATE: the first token matching a loose day/month/year shape
      (`<d>[.-]<mon>[.-]<yyyy>`, tolerant of OCR separator-character noise,
      same loose approach as `aircraft_fitlist_occm.py`'s own date anchor).
      POSITION is taken as the token immediately before it; PART_NUMBER and
      SERIAL_NUMBER are the first two tokens after ATA; everything between
      SERIAL_NUMBER and POSITION is DESCRIPTION (may be empty on a badly
      garbled row -- kept as-is, not treated as a parse failure).
    * CSN and TSN: NOT read as separate whitespace tokens. Confirmed
      directly that this file's OCR occasionally inserts a stray space
      inside a single amount (e.g. digits, a colon, then a further stray
      space before the trailing minutes/sub-unit digits -- something like
      `<n>: <nn>` for what is almost certainly `<n>:<nn>`), which a plain
      whitespace split would wrongly turn into two tokens. Per this
      project's soft-validation convention, that kind of OCR noise is kept
      raw rather than "corrected" -- so CSN/TSN are instead recovered with a
      single regex run over the raw text *after* the located INSTALL_DATE
      token, matching a full amount shape (digits, optionally a colon with
      optional surrounding whitespace and trailing digits) as one unit; the
      first such match is CSN, the second is TSN, in that order. A row
      missing one of the two (confirmed to happen on this file, e.g. where
      the amount OCRs as a single fused run with no recoverable CSN/TSN
      split at all) simply yields an empty string for whichever one is
      missing, left for downstream validation to flag rather than guessed.

Known limitation, confirmed directly against the real sample file: OCR
quality degrades sharply on several pages, with rows visibly bleeding into
each other (a component's description or position spilling onto what should
be the next row's own line) -- those merged/split lines either fail the
INSTALL_DATE anchor entirely (silently dropped, same as header/footer noise)
or parse with a genuinely wrong PART_NUMBER/SERIAL_NUMBER/DESCRIPTION/
POSITION split; the latter is expected to surface as validation flags
downstream rather than being silently "corrected" here -- per this project's
soft-validation convention (see `shared/aviation_rules.py`), a suspicious
cell is flagged, never guessed or dropped.
"""
from __future__ import annotations
import re

from sheet_types.occm_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, ocr_words, page_count

NAME = "On Condition Items (OCCM Status)"

# This module's known source file has no text layer at all (confirmed via
# the router's own pdfplumber head-text check -- fewer than 50 chars
# recovered), so these SIGNATURES can never fire through occm.py's normal
# pdfplumber head-text match; real detection happens via ocr_detect() below.
# Kept here anyway (per this project's convention) as a documented anchor
# and a safety net for any future born-digital re-export of the same
# template. Checked for collisions against every SIGNATURES list in
# sheet_types/{occm,ht,llp}.py and every existing occm_variants/ht_variants/
# llp_variants file: neither phrase appears anywhere else, and neither is a
# substring of (nor contains) any other variant's own SIGNATURES entries.
SIGNATURES = [
    "ON CONDITION ITEMS",
    "Partno | Serialno | Description",
]

CANONICAL_COLUMNS = [
    "ATA",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
    "POSITION",
    "INSTALL_DATE",
    "CSN",
    "TSN",
    # Header metadata, parsed once per file and stamped on every row.
    "AIRCRAFT_REG",
    "MSN",
    "AC_MODEL",
    "HEADER_TSN",
    "HEADER_CSN",
]

# Broad numeric shape shared by row-level CSN/TSN: digits, optionally a
# colon (with tolerated stray whitespace around it per the module docstring)
# and further digits.
_AMOUNT_RULE = {"pattern": r"^\d{1,6}(?:\s?:\s?\d{1,3})?$", "allow_empty": True}

_OVERRIDES = {
    # POSITION is a compact alnum code on every real row inspected (e.g. a
    # side/zone letter combo, or a bare digit run) -- global default column
    # rules have no entry for POSITION at all, so this is defined fresh here
    # rather than overridden (same approach as aircraft_fitlist_occm.py).
    "POSITION": {
        "pattern": r"^[A-Z0-9][A-Z0-9 /\-]{0,20}$",
        "uppercase": True,
        "allow_empty": True,
    },
    # Loose on purpose: real dates on this file are "<d>.<Mon>.<yyyy>" but
    # confirmed to sometimes render with a hyphen separator instead of a dot,
    # or with an OCR-substituted character inside the month abbreviation --
    # flag genuinely malformed dates rather than reject this whole,
    # otherwise-valid shape.
    "INSTALL_DATE": {
        "pattern": r"^\d{1,2}\W?[A-Za-z0-9\W]{2,6}\W?\d{4}$",
        "allow_empty": True,
    },
    "CSN": _AMOUNT_RULE,
    "TSN": _AMOUNT_RULE,
    "AIRCRAFT_REG": {
        "pattern": r"^[A-Z0-9\-]{3,10}$",
        "uppercase": True,
        "allow_empty": True,
    },
    "MSN": {"pattern": r"^\d{1,8}$", "allow_empty": True},
    "AC_MODEL": {
        "pattern": r"^[A-Z0-9\-]{2,20}$",
        "uppercase": True,
        "allow_empty": True,
    },
    # Relaxed rather than pattern-enforced: these are single stamped header
    # values repeated identically on every row of the file, so a tight
    # pattern here would either flag every single row over one shared OCR
    # misread, or none at all -- neither is a useful signal at row
    # granularity (same reasoning as aircraft_fitlist_occm.py's own
    # HEADER_TSN override). Genuine per-row corruption is still caught by
    # the row-level CSN/TSN rules above.
    "HEADER_TSN": {"allow_empty": True},
    "HEADER_CSN": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Border/rule-artifact characters that fuse onto real cell text (see module
# docstring) -- stripped to spaces before tokenizing. Ordinary ASCII hyphens
# are deliberately NOT included here: they're needed verbatim inside real
# part numbers and hyphenated description words.
_NOISE_CHARS_RE = re.compile(r"[|_=–—\[\]{}()]+")

# Leading ATA chapter: a bare 1-2 digit token. Confirmed directly that a
# meaningful fraction of real rows have no leading ATA at all (see module
# docstring) -- those are handled by leaving ATA empty rather than requiring
# this to match.
_ATA_RE = re.compile(r"^\d{1,2}$")

# A date token's loose shape: 1-2 digit day, a short separator-tolerant
# middle chunk (the month abbreviation, tolerating OCR noise), a 4-digit
# year. Same looseness as aircraft_fitlist_occm.py's own date anchor.
_DATE_RE = re.compile(r"^\d{1,2}\W?[A-Za-z0-9\W]{2,6}\W?\d{4}$")

# A full CSN/TSN amount, matched against the raw text (not whitespace
# tokens) so a stray internal space isn't lost (see module docstring).
_AMOUNT_RE = re.compile(r"\d{1,6}(?:\s?:\s?\d{1,3})?")

_HDR_LABELS = {"AIRCRAFT", "SERIAL", "NUMBER", "MODEL", "TSN", "CSN"}


def _clean_token(text: str) -> str:
    return re.sub(r"^[^A-Za-z0-9]+|[^A-Za-z0-9:.\-]+$", "", text.strip())


def _cluster_header_lines(words: list[dict]) -> list[list[dict]]:
    """Group header-band OCR words into visual lines by Y-coordinate, then
    sort each line left-to-right. Needed because two label/value pairs on
    the same printed line (e.g. "TSN" and its value) can still differ by a
    few OCR bounding-box pixels in `top`, which would otherwise put the
    value token ahead of its own label under a naive single top-sort
    (confirmed directly on this file's real header crop)."""
    if not words:
        return []
    ws = sorted(words, key=lambda w: w["top"])
    lines = [[ws[0]]]
    for w in ws[1:]:
        if abs(w["top"] - lines[-1][-1]["top"]) <= 20:
            lines[-1].append(w)
        else:
            lines.append([w])
    return [sorted(line, key=lambda w: w["left"]) for line in lines]


def _parse_header_words(words: list[dict]) -> dict:
    meta = {"AIRCRAFT_REG": "", "MSN": "", "AC_MODEL": "", "HEADER_TSN": "", "HEADER_CSN": ""}
    for line in _cluster_header_lines(words):
        toks = [w["text"] for w in line]
        i = 0
        while i < len(toks):
            up = toks[i].strip().upper()
            if up.startswith("AIRCRAFT") and not meta["AIRCRAFT_REG"] and i + 1 < len(toks):
                meta["AIRCRAFT_REG"] = _clean_token(toks[i + 1]).upper()
                i += 2
                continue
            if up.startswith("SERIAL") and not meta["MSN"]:
                j = i + 1
                if j < len(toks) and toks[j].strip().upper().startswith("NUMBER"):
                    j += 1
                if j < len(toks):
                    meta["MSN"] = _clean_token(toks[j])
                i = j + 1
                continue
            if up.startswith("MODEL") and not meta["AC_MODEL"]:
                rest = [t for t in toks[i + 1:] if t.strip().upper() not in _HDR_LABELS]
                meta["AC_MODEL"] = _clean_token("".join(rest)).upper()
                i = len(toks)
                continue
            if up.startswith("TSN") and not meta["HEADER_TSN"] and i + 1 < len(toks):
                meta["HEADER_TSN"] = _clean_token(toks[i + 1])
                i += 2
                continue
            if up.startswith("CSN") and not meta["HEADER_CSN"] and i + 1 < len(toks):
                meta["HEADER_CSN"] = _clean_token(toks[i + 1])
                i += 2
                continue
            i += 1
    return meta


def _parse_line(line: str, page_num: int) -> dict | None:
    cleaned = _NOISE_CHARS_RE.sub(" ", line)
    tokens = cleaned.split()
    if not tokens:
        return None

    if _ATA_RE.match(tokens[0]):
        ata = tokens[0]
        start = 1
    else:
        ata = ""
        start = 0

    date_idx = None
    for i in range(start, len(tokens)):
        if _DATE_RE.match(tokens[i]):
            date_idx = i
            break
    # Need at least PART_NUMBER, SERIAL_NUMBER and POSITION tokens ahead of
    # the date anchor (description may legitimately be empty).
    if date_idx is None or date_idx < start + 3:
        return None

    part_number = tokens[start]
    serial_number = tokens[start + 1]
    position = tokens[date_idx - 1]
    description = " ".join(tokens[start + 2:date_idx - 1])
    install_date = tokens[date_idx]

    idx = cleaned.find(install_date)
    remainder = cleaned[idx + len(install_date):] if idx != -1 else ""
    amounts = _AMOUNT_RE.findall(remainder)
    csn = amounts[0] if len(amounts) > 0 else ""
    tsn = amounts[1] if len(amounts) > 1 else ""

    return {
        "ATA": ata,
        "PART_NUMBER": part_number,
        "SERIAL_NUMBER": serial_number,
        "DESCRIPTION": description,
        "POSITION": position,
        "INSTALL_DATE": install_date,
        "CSN": csn,
        "TSN": tsn,
        "_page": page_num,
    }


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback (see
    sheet_types/occm.py) -- this variant's known source file has no text
    layer at all, so it can never be found through the normal pdfplumber
    head-text match.

    Requires BOTH the report title ("ON CONDITION ITEMS") and a distinctive
    fragment of the column-header row ("SERIALNO" / "INST-DATE", tolerant of
    either surviving OCR spacing) in the same header-band crop, so a
    different scanned report that merely shares generic title wording
    doesn't get claimed here by mistake.
    """
    try:
        img = await render_page(pdf_path, 0, dpi=300)
        w, h = img.size
        crop = img.crop((0, 0, w, int(h * 0.25)))
        text = (await ocr_text(crop, psm=6)).upper()
        has_title = "ON CONDITION ITEMS" in text
        has_col_hdr = "INST-DATE" in text or "INST DATE" in text
        return has_title and has_col_hdr
    except Exception:
        return False


async def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    meta = {"AIRCRAFT_REG": "", "MSN": "", "AC_MODEL": "", "HEADER_TSN": "", "HEADER_CSN": ""}
    n_pages = await page_count(pdf_path)
    for page_index in range(n_pages):
        img = await render_page(pdf_path, page_index, dpi=300)
        if not all(meta.values()):
            w, h = img.size
            crop = img.crop((0, 0, w, int(h * 0.16)))
            words = await ocr_words(crop, psm=11, min_conf=-1)
            found = _parse_header_words(words)
            for k, v in found.items():
                if v and not meta[k]:
                    meta[k] = v
        text = await ocr_text(img, psm=4)
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            rec = _parse_line(line, page_index + 1)
            if rec is None:
                continue
            rec.update(meta)
            records.append(rec)
    return records
