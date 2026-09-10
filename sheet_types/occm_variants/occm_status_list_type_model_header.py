"""OCCM Status List (Type/Model Header) — mixed text-layer + scanned pages.

Confirmed on one real sample file (real-corpus triage): a multi-page OCCM
status export whose FIRST page (title/header page, which also carries the
opening block of data rows) and LAST page (closing data rows + a signature
footer) are flat scanned images with no text layer at all (confirmed via
pdfplumber: 0 chars on each), while every page in between has a genuine,
cleanly-extractable text layer (confirmed via pdfplumber: ~2.2-2.9k chars
per page, one data row per physical line, space-separated). This is the
same "mixed text-layer + scanned pages within one document" situation as
`occm_status_list.py`'s own docstring describes for its (differently
shaped) sibling format — just with the scanned pages at the two ends
instead of scattered throughout.

Because this must also run under Pyodide, all OCR here goes through
`shared/ocr_bridge.py`'s async `render_page()` / `ocr_text()` primitives
rather than raw fitz/pytesseract (see that module's own docstring) —
extract() and ocr_detect() are both `async def` accordingly, following the
same pattern as e.g. `aircraft_inventory_report_scanned.py` /
`aeroflot.py` in this same package.

Header block (rendered as part of the scanned title page, recovered via a
cropped OCR pass over the top ~20% of that page)::

    TYPE/MODEL:<type> DOM:<date>
    SERIAL NO:<msn> TSN:<n>
    REGISTRATION:<reg> CSN:<n>
    <report title line> OCCM STATUS LIST

`<type>` / `<date>` / `<msn>` / TSN / `<reg>` / CSN are parsed once from
this header via regex and stamped onto EVERY row as AIRCRAFT_TYPE / DOM /
MSN / HEADER_TSN / AIRCRAFT_REG / HEADER_CSN, per this project's
established header-metadata convention (see e.g. `component_fit_list.py`).
The report-title text itself (a MIS/tool name ahead of "OCCM STATUS LIST")
is deliberately NOT parsed/captured — it isn't needed for extraction and
OCRs too unreliably to trust as a stamped value anyway.

Column-header line (born-digital pages only; OCRs too unreliably on the
scanned title page to anchor on): "ATA PART NO SERIAL NO DESCRIPTION POS
INSTALL DATE STATUS/REMARKS" (or a close OCR variant of it) — confirmed
directly against the real sample's column-header row. Seven columns:

    ATA  PART_NUMBER  SERIAL_NUMBER  DESCRIPTION  POSITION  INSTALL_DATE  STATUS

Data rows on the born-digital pages are one clean physical line each,
space-separated, e.g. (values genericized; real sample uses real PN/SN
pairs and dates)::

    <ata> <pn> <sn> <description words...> <pos> <date> <status words...>

ATA / PART_NUMBER / SERIAL_NUMBER are always the first three whitespace
tokens on the line (confirmed on every sampled row). INSTALL_DATE renders
in one of two shapes mixed throughout the same document — `<D>-<Mon>-<YY>`
(e.g. one/two-digit day, 3-letter month abbreviation, 2-digit year) or
`<DD>.<MM>.<YYYY>` (dotted, 4-digit year) — both anchored by `_DATE_RE`; a
`<D>-<Mon>-<YY>`-shaped date whose day or year digit(s) got corrupted into
look-alike letters (e.g. a "5" rendering as "S") is a confirmed, if
occasional, real-file quirk (same class of character-substitution noise
documented on other variants in this package) — such rows are
deliberately left unparsed/dropped rather than guessed at, per this
project's "never guess a wrong split" convention.

DESCRIPTION and POSITION sit between SERIAL_NUMBER and INSTALL_DATE with no
fixed token count on either side (DESCRIPTION can run to several words;
POSITION is usually one token -- LH/RH/FWD/AFT/CTR/APU/UPR/LWR/U-R-style
abbreviations, a bare slot number, or a placeholder dash for "no position"
-- but is occasionally two tokens, e.g. a bay + a sub-slot code). Because
of that, the split can't be done by a fixed word-count rule; instead,
extract() uses each word's real x0 (pdfplumber `extract_words()`) and finds
the single largest horizontal gap among the "middle" words (the ones
between SERIAL_NUMBER and the recognized INSTALL_DATE token) -- confirmed
directly on the real sample: intra-DESCRIPTION and intra-POSITION word
gaps are consistently tight (a few points), while the DESCRIPTION/POSITION
column boundary itself is consistently the one clearly larger gap on the
line. Everything up to that gap is DESCRIPTION; everything from it is
POSITION. If there's no gap above the small-gap noise floor, the whole
middle run is DESCRIPTION and POSITION is left blank (a real, confirmed
case -- some rows genuinely carry no position value on this form). A
placeholder POSITION cell rendering as a single dash (or run of dashes) is
treated the same as blank, mirroring the placeholder-glyph handling in
`aircraft_inventory_report_scanned.py`.

STATUS is a phase-remaining / certification field, NOT a small closed
enum -- confirmed directly by tallying every distinct STATUS value across
the whole real sample. It mixes genuine sentinel phrases ("D.O.M" = date
of manufacture / since new, "< 3 YEARS", "OUT OF PHASE", and several
"A<n>[+C<n>][+...] CHECK"/"OUT OF PHASE" combinations) with certificate /
work-order reference codes that are effectively free text (bare
alphanumeric codes, "REF:<code>", "WO <code>", "FAA FORM // <code>", "SIN
<code>"). RULES below validates it as a loose free-text field rather than
against an enum for this reason -- forcing an enum here would misclassify
the (very common) certificate-code rows as invalid.

Some DESCRIPTION values embed a parenthetical cross-reference, e.g.
"VALVE,(STOCK # <pn>)" or "VALVE,APU AIR ISOLATION (<code>)QPA4" (confirmed
on the real sample). These are left as-is, part of DESCRIPTION -- they're
prose annotations inside the same column, not a separately-columned field,
and the surrounding text makes them unsafe to peel out generically without
risking mangling ordinary parenthetical text elsewhere in the same column.

The two scanned pages (first and last) are OCR'd via `render_page()` +
`ocr_text()` and parsed line-by-line rather than via word geometry -- OCR
word-level bounding boxes on these two pages were tested directly and
found too noisy/skewed for the same gap-based column split used on the
born-digital pages (row clustering by OCR word `top` either fragmented a
single printed row into pieces or merged several distinct rows together
depending on the tolerance used, confirmed directly at multiple tolerance
settings). The plain OCR text line -- after stripping table-border noise
characters ('|', '[', ']', '_', '~'), the same class of cleanup
`occm_status_list.py`'s own `_clean_ocr_text()` applies -- still yields
ATA/PART_NUMBER/SERIAL_NUMBER/INSTALL_DATE/STATUS reliably enough via the
same rank + date-anchor logic used for the born-digital pages; DESCRIPTION
and POSITION are NOT geometry-split on these two pages (no reliable x0 to
split on) and are instead left combined as DESCRIPTION, with POSITION left
blank, rather than guessing a wrong split. This means these two pages
recover a real but noticeably smaller fraction of their rows than the
born-digital pages do -- confirmed directly on the real sample -- which is
expected given the OCR quality on them, not a parsing bug.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text

NAME = "OCCM Status List (Type/Model Header, Scanned)"

# The known source file's title/header page has no text layer at all
# (confirmed via pdfplumber: 0 chars), so these can never be reached via
# the router's normal pdfplumber text-signature match -- real detection
# happens via ocr_detect() below. Declared anyway, per this file's
# convention, as a documented anchor / safety net for any future
# born-digital re-export. Checked directly (grep across every SIGNATURES
# list in sheet_types/{occm,ht,llp}.py and every existing occm_variants
# file): "OCCM STATUS LIST" is NOT a substring of (nor contains)
# occm_status_list.py's own "OCCM COMPONENTS STATUS LIST" / "COMPONENTS
# STATUS LIST" entries (the word "COMPONENTS" sits between "OCCM" and
# "STATUS" there but not here), so no collision risk with that sibling.
SIGNATURES = [
    "OCCM STATUS LIST",
]

CANONICAL_COLUMNS = [
    "ATA",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
    "POSITION",
    "INSTALL_DATE",
    "STATUS",
    # Header metadata -- parsed once from the scanned title page, stamped
    # onto every row.
    "AIRCRAFT_TYPE",
    "DOM",
    "MSN",
    "HEADER_TSN",
    "AIRCRAFT_REG",
    "HEADER_CSN",
]

_DATE_PATTERN = r"^\d{1,2}-[A-Za-z]{3}-[A-Za-z0-9]{2,4}$|^\d{1,2}\.\d{1,2}\.\d{4}$"
_OVERRIDES = {
    "POSITION": {
        "pattern": r"^[A-Z0-9][A-Z0-9 /#().\-]{0,24}$",
        "uppercase": True,
        "allow_empty": True,
    },
    "INSTALL_DATE": {"pattern": _DATE_PATTERN},
    # Free-text phase-remaining / certificate-code field -- NOT a closed
    # enum (see module docstring's tally of every distinct value observed
    # on the real sample). Validated loosely; allow_empty covers the rare
    # OCR-fallback row where the trailing text didn't resolve at all.
    # Leading "<" is a legitimate, common sentinel here ("< 3 YEARS" is the
    # single most frequent STATUS value on the real sample -- confirmed by
    # tallying every distinct value), not corruption -- included in the
    # allowed leading-character set rather than left to dominate the
    # flagged count.
    "STATUS": {
        "pattern": r"^[A-Z0-9<][A-Z0-9 +/#:.\-]{0,40}$",
        "uppercase": True,
        "allow_empty": True,
    },
    "AIRCRAFT_TYPE": {"pattern": r"^[A-Z0-9\-]{2,12}$", "uppercase": True, "allow_empty": True},
    "DOM": {"pattern": _DATE_PATTERN, "allow_empty": True},
    "MSN": {"pattern": r"^[A-Z0-9]{1,10}$", "uppercase": True, "allow_empty": True},
    "HEADER_TSN": {"pattern": r"^\d+$", "allow_empty": True},
    "AIRCRAFT_REG": {"pattern": r"^[A-Z0-9\-]{2,10}$", "uppercase": True, "allow_empty": True},
    "HEADER_CSN": {"pattern": r"^\d+$", "allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_ATA_RE = re.compile(r"^\d{2}$")
_DATE_RE = re.compile(_DATE_PATTERN)
# A lone leftover placeholder glyph where a real POSITION would be printed
# (same convention as aircraft_inventory_report_scanned.py's _PLACEHOLDER_RE).
_PLACEHOLDER_RE = re.compile(r"^[-_—–]+$")

_TYPE_DOM_RE = re.compile(
    r"TYPE\s*/\s*MODEL\s*:\s*(?P<type>\S+)\s+DOM\s*:\s*(?P<dom>\d{1,2}[-.][A-Za-z0-9]{2,4}[-.]\d{2,4})",
    re.IGNORECASE,
)
_MSN_TSN_RE = re.compile(
    r"SERIAL\s*NO\s*:\s*(?P<msn>\S+)\s+TSN\s*:\s*(?P<tsn>\d+)", re.IGNORECASE
)
_REG_CSN_RE = re.compile(
    r"REGISTRATION\s*:\s*(?P<reg>\S+)\s+CSN\s*:\s*(?P<csn>\d+)", re.IGNORECASE
)


def _parse_header(text: str) -> dict:
    meta: dict = {}
    m = _TYPE_DOM_RE.search(text)
    if m:
        meta["AIRCRAFT_TYPE"] = m.group("type")
        meta["DOM"] = m.group("dom")
    m = _MSN_TSN_RE.search(text)
    if m:
        meta["MSN"] = m.group("msn")
        meta["HEADER_TSN"] = m.group("tsn")
    m = _REG_CSN_RE.search(text)
    if m:
        meta["AIRCRAFT_REG"] = m.group("reg")
        meta["HEADER_CSN"] = m.group("csn")
    return meta


def _cluster_rows(words: list[dict], tol: float = 3.0) -> list[list[dict]]:
    """Group pdfplumber words into visual rows by their `top` coordinate."""
    if not words:
        return []
    words = sorted(words, key=lambda w: w["top"])
    rows: list[list[dict]] = []
    cur = [words[0]]
    for w in words[1:]:
        if w["top"] - cur[-1]["top"] <= tol:
            cur.append(w)
        else:
            rows.append(cur)
            cur = [w]
    rows.append(cur)
    return rows


def _split_description_position(middle: list[dict]) -> tuple[str, str]:
    """Split the words between SERIAL_NUMBER and INSTALL_DATE into
    (DESCRIPTION, POSITION) using the single largest horizontal gap among
    them -- see module docstring for why a fixed token count doesn't work
    here."""
    if not middle:
        return "", ""
    if len(middle) == 1:
        return middle[0]["text"], ""
    gaps = [middle[i]["x0"] - middle[i - 1]["x1"] for i in range(1, len(middle))]
    max_i = max(range(len(gaps)), key=lambda i: gaps[i])
    if gaps[max_i] <= 10:
        # No real column break -- everything is DESCRIPTION, no POSITION
        # printed on this row (confirmed real case, not a parsing gap).
        return " ".join(w["text"] for w in middle), ""
    split = max_i + 1
    desc = " ".join(w["text"] for w in middle[:split])
    pos = " ".join(w["text"] for w in middle[split:])
    if _PLACEHOLDER_RE.match(pos):
        pos = ""
    return desc, pos


def _parse_digital_row(row_words: list[dict]) -> dict | None:
    ws = sorted(row_words, key=lambda w: w["x0"])
    if len(ws) < 5:
        return None
    if not _ATA_RE.match(ws[0]["text"]):
        return None
    ata = ws[0]["text"]
    pn = ws[1]["text"]
    sn = ws[2]["text"]
    rest = ws[3:]
    date_idx = None
    for i, w in enumerate(rest):
        if _DATE_RE.match(w["text"]):
            date_idx = i
            break
    if date_idx is None:
        return None
    install_date = rest[date_idx]["text"]
    status = " ".join(w["text"] for w in rest[date_idx + 1:])
    description, position = _split_description_position(rest[:date_idx])
    return {
        "ATA": ata,
        "PART_NUMBER": pn,
        "SERIAL_NUMBER": sn,
        "DESCRIPTION": description,
        "POSITION": position,
        "INSTALL_DATE": install_date,
        "STATUS": status,
    }


def _clean_ocr_text(text: str) -> str:
    """Strip table-border noise characters Tesseract/Tesseract.js introduce
    on bordered tables -- same class of cleanup as
    occm_status_list.py's own `_clean_ocr_text()`."""
    for ch in "[]|_~":
        text = text.replace(ch, " ")
    return re.sub(r"[ \t]+", " ", text)


def _parse_ocr_line(line: str) -> dict | None:
    """Parse one OCR'd text line on a scanned page. No word geometry is
    available here, so DESCRIPTION and POSITION are NOT split (see module
    docstring) -- POSITION is always left blank for OCR-path rows."""
    tokens = line.split()
    if len(tokens) < 5:
        return None
    if not _ATA_RE.match(tokens[0]):
        return None
    ata = tokens[0]
    pn = tokens[1]
    sn = tokens[2]
    rest = tokens[3:]
    date_idx = None
    for i, t in enumerate(rest):
        if _DATE_RE.match(t):
            date_idx = i
            break
    if date_idx is None:
        return None
    description = " ".join(rest[:date_idx])
    if not description:
        return None
    install_date = rest[date_idx]
    status = " ".join(rest[date_idx + 1:])
    return {
        "ATA": ata,
        "PART_NUMBER": pn,
        "SERIAL_NUMBER": sn,
        "DESCRIPTION": description,
        "POSITION": "",
        "INSTALL_DATE": install_date,
        "STATUS": status,
    }


async def _extract_ocr_page(pdf_path: str, page_index: int) -> list[dict]:
    img = await render_page(pdf_path, page_index, dpi=300)
    text = _clean_ocr_text(await ocr_text(img, psm=6))
    records = []
    for line in text.splitlines():
        rec = _parse_ocr_line(line.strip())
        if rec is not None:
            records.append(rec)
    return records


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback (see
    sheet_types/occm.py) -- this variant's own SIGNATURES can never match
    through the normal pdfplumber text-extract path since the known source
    file's title page has no text layer at all.

    Anchors on the full header fingerprint -- "TYPE/MODEL:" + "DOM:" +
    "SERIAL NO:" + "REGISTRATION:" + "TSN:" + "CSN:" all present in the
    top ~20% of the rendered page -- rather than the report-title text
    itself (which OCRs far less reliably on the real sample). Checked
    directly (grep across every SIGNATURES list in
    sheet_types/{occm,ht,llp}.py and every existing occm_variants file's
    own ocr_detect() anchors): no other module's own SIGNATURES/ocr_detect
    anchor combines all six of these labels the way this one does --
    other modules using a bare "TYPE/MODEL:" or "REGISTRATION:" fragment
    (e.g. maintenance_status_report_pr21.py, oc_component_status.py,
    standard_occm.py) are all born-digital (no ocr_detect of their own)
    and use a different surrounding phrase, so no collision risk.
    """
    try:
        img = await render_page(pdf_path, 0, dpi=300)
        w, h = img.size
        crop = img.crop((0, 0, w, int(h * 0.20)))
        text = (await ocr_text(crop, psm=4)).upper()
        return (
            "TYPE/MODEL:" in text.replace(" ", "")
            and "DOM:" in text
            and "SERIALNO:" in text.replace(" ", "")
            and "REGISTRATION:" in text
            and "TSN:" in text
            and "CSN:" in text
        )
    except Exception:
        return False


async def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    header_meta: dict = {
        "AIRCRAFT_TYPE": "", "DOM": "", "MSN": "",
        "HEADER_TSN": "", "AIRCRAFT_REG": "", "HEADER_CSN": "",
    }

    # Header lives only on the scanned title page (page 0), whose text
    # layer is empty -- OCR the top band once to recover it.
    try:
        img = await render_page(pdf_path, 0, dpi=300)
        w, h = img.size
        crop = img.crop((0, 0, w, int(h * 0.20)))
        header_text = await ocr_text(crop, psm=4)
        header_meta.update({k: v for k, v in _parse_header(header_text).items() if v})
    except Exception:
        pass

    with pdfplumber.open(pdf_path) as pdf:
        for page_index, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if len(text) >= 50:
                words = page.extract_words()
                page_records = []
                for row_words in _cluster_rows(words):
                    rec = _parse_digital_row(row_words)
                    if rec is not None:
                        page_records.append(rec)
            else:
                # No usable text layer on this page -- OCR it via the
                # bridge primitives (Pyodide-safe; see module docstring).
                page_records = await _extract_ocr_page(pdf_path, page_index)

            for rec in page_records:
                rec["_page"] = page_index + 1
                rec.update(header_meta)
                records.append(rec)

    return records
