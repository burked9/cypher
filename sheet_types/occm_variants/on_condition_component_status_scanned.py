"""On-Condition Component Status (Boeing 767 Specification Sheet) -- scanned,
no text layer, OCR required.

Confirmed on a real sample file (real-corpus triage): every page is a flat,
full-page scanned image produced by a physical photocopier/scanner (no PDF
text layer at all -- confirmed via pdfplumber, 0 extractable chars/words/
rects on every page). This module renders each page and OCRs it directly
via the async OCR bridge (`shared/ocr_bridge.py`), same approach as this
project's other scanned OCCM variants (e.g. `aircraft_fitlist_occm.py`,
`aircraft_inventory_report_scanned.py`).

Known limitation, confirmed directly against the real sample file: image
quality is noticeably worse than most other scanned variants in this
package -- consistent with a multi-generation photocopy rather than a
first-generation scan (heavy salt-and-pepper speckle, faint/broken
character strokes, table gridlines rendered as OCR noise tokens). DPI
300/400/600 and PSM 4/6/7/11/12 were all tried directly against the real
file; PSM 4 (assume a single uniform block of variable-sized text, no
column detection) at 400 DPI gave the cleanest, most consistent row
tokenisation across every page sampled and is used for the table body.
Given this, a meaningful fraction of rows fail to parse cleanly or parse
with a wrong token boundary -- expected and accepted, per this project's
convention, rather than forced into a falsely-precise shape.

A second, more severe known limitation, also confirmed directly: on
several of this file's twelve pages the degradation is bad enough that
Tesseract's own line segmentation collapses entirely -- a single real
table row's PART_NUMBER, DESCRIPTION, INSTALL_DATE and trailing numbers
each land on their OWN separate output line, in table-column reading
order across the whole page, rather than side-by-side on one line. No
per-line token-count or anchor regex can reassemble that back into rows,
so those pages yield zero records rather than a guessed, wrong
reassembly -- confirmed directly this affects a real minority of the
file's pages, not the majority.

Header block (first page only; parsed once and stamped on every row as
AC_REGISTRATION / MSN / MNFR_DATE / REPORT_DATE / HEADER_ACFH / HEADER_ACFC)::

    A/C Registration <reg>          Updated <date>
    MSN <msn>                       ACTT <n>
    Mnfr Date <date>                ACTC <n>

confirmed directly via word-position inspection of the real rendered page
1 header band (left-hand label/value pairs, right-hand label/value pairs
at a distinct x-offset on the same three text rows).

Column header row (confirmed directly, though heavily OCR-garbled on every
page sampled -- reconstructed from partial, higher-confidence word
fragments recovered across several pages, not assumed from a rough prior
pass)::

    ATA PN SN POS DESCRIPTION INST DATE INST A/C FH INST A/C FC TSN CSN TSINT CSINT

A data row, tokens in column order: ATA, PART_NUMBER, SERIAL_NUMBER (often
blank -- confirmed on real rows), POSITION (often blank, or a short code
such as a bare side letter, a compound side/zone code, or the literal "00"
placeholder meaning no side/zone applicable -- confirmed on real rows),
DESCRIPTION (free text, may itself contain commas), INSTALL_DATE, then two
decimal numbers (aircraft total time / total cycles at the time of that
install -- captured as ACFH/ACFC), then a trailing run of up to four
further numeric-or-"UNK" tokens.

Row extraction anchors on two positions rather than naive fixed-count
token splitting, since the SN/POS/DESCRIPTION zone between PART_NUMBER and
INSTALL_DATE is variable-width (confirmed directly: real rows range from
zero to two tokens present there before the description text starts).
First, the leading `<ata>` chapter is peeled off the front of the line with
a regex (OCR sometimes glues it directly onto the next token with no
space); second, INSTALL_DATE is located by shape (`<day>` + a
punctuation-separated middle chunk + a 2-or-4-digit year -- loose enough
to tolerate real OCR noise seen on this file) and used as the anchor for
PART_NUMBER (the token immediately after ATA) and for the trailing
ACFH/ACFC pair (the two decimal-shaped tokens immediately after
INSTALL_DATE). Working forward from PART_NUMBER, the token(s) before
INSTALL_DATE are resolved as: a leading token is SERIAL_NUMBER only if it
contains at least one digit (confirmed directly: every real SN token seen
does; genuine DESCRIPTION words never do); the following token is POSITION
only if it matches a short, closed shape (a bare side/zone code, or the
literal "00") -- confirmed directly against every distinct such token seen
across the sampled pages; anything left over is DESCRIPTION.

Everything after ACFH/ACFC (up to four further tokens -- normally the
component's own TSN/CSN and a since-interval TSN/CSN pair, per the column
header reconstructed above, though the exact identity of the third and
fourth trailing tokens on any given row cannot be reconstructed reliably
given this file's scan quality) is folded verbatim into STATUS_TRAIL
rather than force-split into four separately-named columns, per this
project's "never guess a wrong split" convention (see e.g.
`occm_variants/occm_component_ac_corrected_at_install.py`,
`occm_variants/multi_basis_accumulated_occm.py`). A suspicious or
malformed row surfaces as a validation flag downstream rather than being
silently "corrected" or dropped here, per this project's soft-validation
convention (see `shared/aviation_rules.py`) -- except rows that don't even
clear the ATA + PART_NUMBER + INSTALL_DATE anchor, which are silently
dropped as header/footer/noise, same as this package's other scanned
variants.

Illustrative example (placeholders only -- no real value from the actual
sample file appears anywhere in this module, per this project's data
sensitivity rules)::

    <ata> <pn> <sn> <position> <description...> <date> <acfh> <acfc> <trail...>
"""
from __future__ import annotations
import re

from sheet_types.occm_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, page_count

NAME = "On-Condition Component Status (Boeing 767 Specification Sheet, Scanned)"

# This module's known source file has no text layer at all (confirmed via
# pdfplumber -- 0 chars on every page), so these SIGNATURES can never fire
# through occm.py's normal pdfplumber head-text match; real detection
# happens via ocr_detect() below. Kept here anyway (per this project's
# convention) as a documented anchor and a safety net for any future
# born-digital re-export of the same template. Checked directly (grep
# across every SIGNATURES list in sheet_types/{occm,ht,llp}.py and every
# existing occm_variants/ht_variants/llp_variants file): neither phrase
# appears anywhere else, and neither is a substring of (nor contains) any
# other variant's own SIGNATURES entries.
SIGNATURES = [
    "BOEING 767 SPECIFICATION SHEET",
    "On-Condition Component Status",
]

CANONICAL_COLUMNS = [
    "ATA",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "POSITION",
    "DESCRIPTION",
    "INSTALL_DATE",
    "ACFH",
    "ACFC",
    "STATUS_TRAIL",
    # Header metadata, parsed once per file and stamped on every row.
    "AC_REGISTRATION",
    "MSN",
    "MNFR_DATE",
    "REPORT_DATE",
    "HEADER_ACFH",
    "HEADER_ACFC",
]

_OVERRIDES = {
    "DESCRIPTION": {"uppercase": True},
    "POSITION": {
        "pattern": r"^[A-Z0-9][A-Z0-9/\-]{0,8}$",
        "uppercase": True,
        "allow_empty": True,
    },
    # Loose on purpose: real dates on this file are "<D[D]-Mon-YY>" but OCR
    # noise on this heavily-degraded scan frequently substitutes stray
    # digits/symbols for letters inside the month abbreviation, or drops
    # the separating hyphens (confirmed directly) -- flag genuinely
    # malformed dates rather than reject this whole, otherwise-valid shape.
    "INSTALL_DATE": {
        "pattern": r"^\d{1,2}\W?[A-Za-z0-9\W]{2,6}\W?\d{2,4}$",
        "allow_empty": True,
    },
    "ACFH": {"pattern": r"^\d+(\.\d{1,2})?$", "allow_empty": True},
    "ACFC": {"pattern": r"^\d+(\.\d{1,2})?$", "allow_empty": True},
    # Free-form trailing counters (see module docstring) -- deliberately
    # unpatterned; a single stamped/derived text blob, not a validated
    # numeric field in its own right.
    "STATUS_TRAIL": {"allow_empty": True},
    "AC_REGISTRATION": {"allow_empty": True},
    "MSN": {"pattern": r"^\d{1,6}$", "allow_empty": True},
    "MNFR_DATE": {"allow_empty": True},
    "REPORT_DATE": {"allow_empty": True},
    # Relaxed rather than pattern-enforced: these are single stamped
    # header values repeated identically on every row of the file, so a
    # tight pattern here would either flag every single row over one OCR
    # misread in one place, or none at all -- neither is a useful signal
    # at row granularity. Genuine per-row corruption is still caught by
    # the row-level ACFH/ACFC rules above.
    "HEADER_ACFH": {"allow_empty": True},
    "HEADER_ACFC": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Leading ATA chapter, often glued directly onto the next word by OCR with
# no separating space (confirmed directly on the real file).
_LEAD_RE = re.compile(r"^\s*[|\[({_.]*\s*(\d{2})\s*[/|)\].]*\s*(.*)$")

# A date token's shape: 1-2 digit day, a literal separator, a short
# alphabetic month abbreviation (2-6 letters, tolerating OCR noise that
# drops/substitutes one letter), a literal separator, a 2-or-4-digit year.
# Real separators on this file are "-" or "." (confirmed directly) --
# requiring an actual separator character on both sides (rather than the
# optional `\W?` this project's other scanned variants use for cleaner
# sources) is deliberately stricter here: without it, plain digit-heavy
# tokens shaped like a part-number suffix (e.g. "<n><letter><n>-<n>") were
# confirmed directly, on a real row of the sample file, to false-positive-
# match as a date and corrupt the anchor.
_DATE_RE = re.compile(r"^\d{1,2}[-.][A-Za-z]{2,6}[-.]\d{2,4}$")

# Matches a stray space inserted between the day digits and the rest of a
# date token (see `_parse_line`'s one caller for why).
_SPLIT_DATE_RE = re.compile(r"(\d{1,2})\s+(-[A-Za-z]{2,6}-\d{2,4})")

# A decimal-number token (ACFH/ACFC shape): digits, optional 1-2 decimal
# places.
_DEC_RE = re.compile(r"^\d+(?:\.\d{1,2})?$")

# A serial-number-shaped token: contains at least one digit (confirmed
# directly: every real SN token seen does; genuine DESCRIPTION words --
# which this token would otherwise be confused with -- never do).
_SN_RE = re.compile(r"^[A-Z0-9][A-Z0-9\-]{0,11}$")
_HAS_DIGIT_RE = re.compile(r"\d")

# Closed set of real POSITION token shapes confirmed directly on the
# sampled pages: a bare side letter/code, a compound side+zone code, or
# the literal "00" placeholder meaning no side/zone applicable.
_POS_RE = re.compile(
    r"^(?:LH|RH|LH\d[A-Z]{0,3}|RH\d[A-Z]{0,3}|FWD|AFT|CTR|EQ|UP|LWR|ONLY|U|00)$",
    re.IGNORECASE,
)

_AC_REG_RE = re.compile(r"A[/I]?C\s+Registration\s+(\S+)", re.IGNORECASE)
_MSN_RE = re.compile(r"\bMSN\s+(\d{1,6})\b", re.IGNORECASE)
# "Mn<...>Date" -- confirmed directly, OCR renders the "Mnfr" label with
# an extra inserted vowel on some passes (e.g. "Mnofr") and sometimes fuses
# it directly onto "Date" with no separating space, so both are tolerated.
_MNFR_DATE_RE = re.compile(r"Mn\w{0,4}\s*Date\s*[:.]?\s*(\S+)", re.IGNORECASE)
_UPDATED_RE = re.compile(r"Updated\s+(\S+)", re.IGNORECASE)
_ACTT_RE = re.compile(r"\bACTT\s+([\d.]+)", re.IGNORECASE)
_ACTC_RE = re.compile(r"\bACTC\s+([\d.]+)", re.IGNORECASE)


def _parse_header_meta(text: str) -> dict:
    meta = {
        "AC_REGISTRATION": "",
        "MSN": "",
        "MNFR_DATE": "",
        "REPORT_DATE": "",
        "HEADER_ACFH": "",
        "HEADER_ACFC": "",
    }
    m = _AC_REG_RE.search(text)
    if m:
        meta["AC_REGISTRATION"] = m.group(1)
    m = _MSN_RE.search(text)
    if m:
        meta["MSN"] = m.group(1)
    m = _MNFR_DATE_RE.search(text)
    if m:
        meta["MNFR_DATE"] = m.group(1)
    m = _UPDATED_RE.search(text)
    if m:
        meta["REPORT_DATE"] = m.group(1)
    m = _ACTT_RE.search(text)
    if m:
        meta["HEADER_ACFH"] = m.group(1)
    m = _ACTC_RE.search(text)
    if m:
        meta["HEADER_ACFC"] = m.group(1)
    return meta


def _parse_line(line: str, page_num: int) -> dict | None:
    m = _LEAD_RE.match(line)
    if not m:
        return None
    ata = m.group(1)
    # OCR on this file's more heavily degraded pages sometimes splits the
    # date token in two, inserting a stray space between the leading day
    # digits and the rest (e.g. "<dd> -<Mon>-<yy>") -- confirmed directly
    # on real rows of the sample file, this otherwise silently fails the
    # date anchor below, dropping an otherwise-parseable row. Reunited
    # before tokenizing.
    body = _SPLIT_DATE_RE.sub(r"\1\2", m.group(2))
    toks = [t.strip("|[]") for t in body.split() if t.strip("|[]")]
    if len(toks) < 3:
        return None

    pn = toks[0]
    rest = toks[1:]

    date_idx = None
    for i, tok in enumerate(rest):
        if _DATE_RE.match(tok):
            date_idx = i
            break
    if date_idx is None:
        return None

    middle = rest[:date_idx]
    sn = ""
    pos = ""
    if middle and _HAS_DIGIT_RE.search(middle[0]) and _SN_RE.match(middle[0]):
        sn = middle[0]
        middle = middle[1:]
    if middle and _POS_RE.match(middle[0]):
        pos = middle[0].upper()
        middle = middle[1:]
    description = " ".join(middle)

    after = rest[date_idx + 1:]
    acfh = ""
    acfc = ""
    trail_start = 0
    if after and _DEC_RE.match(after[0]):
        acfh = after[0]
        trail_start = 1
        if len(after) > 1 and _DEC_RE.match(after[1]):
            acfc = after[1]
            trail_start = 2
    status_trail = " ".join(after[trail_start:])

    return {
        "ATA": ata,
        "PART_NUMBER": pn,
        "SERIAL_NUMBER": sn,
        "POSITION": pos,
        "DESCRIPTION": description,
        "INSTALL_DATE": rest[date_idx],
        "ACFH": acfh,
        "ACFC": acfc,
        "STATUS_TRAIL": status_trail,
        "_page": page_num,
    }


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback (see
    sheet_types/occm.py) -- this variant's known source file has no text
    layer at all, so it can never be found through the normal pdfplumber
    head-text match.

    Requires both the aircraft-model title line and the report subtitle in
    the same top-of-page crop, so a different scanned OCCM report that
    merely shares generic wording doesn't get claimed here by mistake.
    "COMPONENT STAT" (a prefix of "COMPONENT STATUS") is used rather than
    the full word -- confirmed directly on the real sample file, this
    heavily-degraded scan's own header OCRs the trailing "US" of "STATUS"
    as a different, unreliable glyph run (e.g. "STATIS") on at least one
    render pass, so anchoring on the full word would risk a false negative
    on this module's own known source file.
    """
    try:
        img = await render_page(pdf_path, 0, dpi=400)
        w, h = img.size
        crop = img.crop((0, 0, w, int(h * 0.18)))
        text = (await ocr_text(crop, psm=6)).upper()
        return "SPECIFICATION SHEET" in text and "COMPONENT STAT" in text
    except Exception:
        return False


async def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    n_pages = await page_count(pdf_path)
    meta = {
        "AC_REGISTRATION": "",
        "MSN": "",
        "MNFR_DATE": "",
        "REPORT_DATE": "",
        "HEADER_ACFH": "",
        "HEADER_ACFC": "",
    }
    for page_index in range(n_pages):
        img = await render_page(pdf_path, page_index, dpi=400)
        text = await ocr_text(img, psm=4)
        if page_index == 0:
            # The header info block (A/C Registration / MSN / Mnfr Date /
            # Updated / ACTT / ACTC) needs its own, separate OCR pass at
            # psm=6 (line-oriented) rather than the psm=4 pass used for the
            # table body -- confirmed directly: psm=4 drops most of these
            # labels outright on this file's own real header band (e.g.
            # "A/C Registration" OCRs as a fragment with no recognizable
            # label text at all), while psm=6 recovers them intact.
            # The crop is deliberately restricted to the info-block band
            # alone (excluding the title/subtitle lines above it) --
            # confirmed directly that including the title in the same
            # psm=6 pass breaks Tesseract's column segmentation and drops
            # the right-hand label/value pairs (Updated/ACTT/ACTC)
            # entirely, even though they OCR fine once isolated.
            w, h = img.size
            header_crop = img.crop((0, int(h * 0.15), w, int(h * 0.29)))
            header_text = await ocr_text(header_crop, psm=6)
            meta = _parse_header_meta(header_text)
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
