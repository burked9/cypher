"""Aircraft Fitlist (OCCM) -- scanned, no text layer, OCR required.

Confirmed on a real sample file (real-corpus triage): every page is a flat
scanned image with no extractable text layer at all (confirmed via
pdfplumber: near-zero chars on either page), so this module renders each
page and OCRs it directly via the async OCR bridge
(`shared/ocr_bridge.py`), same approach as this project's other scanned
OCCM variants (e.g. `aircraft_inventory_report_scanned.py`,
`aircraft_occm_list_scanned.py`).

Header block (first page only, repeats no metadata on later pages)::

    <operator name> / MSN <msn> AIRCRAFT FITLIST (OCCM) Date: <date> TSN - <n>
    CSN -<n>

parsed once and stamped on every row as MSN / REPORT_DATE / HEADER_TSN, per
this project's convention for header-plus-body OCCM variants. Only MSN,
REPORT_DATE and HEADER_TSN are captured -- the operator name printed in the
header is intentionally NOT extracted into a column here (out of scope for
this module; nothing in the header repeats onto later pages).

Column header row (confirmed directly against the real rendered page, not
assumed from a rough OCR pass)::

    ATA DESCRIPTION PART NUMBER SERIAL NUMBER POSITION INST-DATE TSN CSN

A data row, tokens in column order: ATA, DESCRIPTION (free text, may itself
contain spaces/hyphens/parentheses), PART_NUMBER, SERIAL_NUMBER, POSITION
(usually a single token like "U"/"RH"/"LH"/a bare digit, but confirmed on
real rows to sometimes be two tokens, e.g. a side code plus a sub-zone
modifier such as "<side> LWR"/"<side> TMV"), INSTALL_DATE, TSN, CSN.

Row extraction anchors on two positions rather than naive fixed-count
token splitting, since DESCRIPTION and POSITION are both variable-width:
first, the leading `<ata>` chapter is peeled off the front of the line with
a regex (OCR frequently glues it directly onto the next word with no
space, e.g. "<ata>/<description...>" -- confirmed directly on the real
file); second, the INSTALL_DATE token is located by shape (`<day>` + a
punctuation-separated middle chunk + a 4-digit year -- loose enough to
tolerate real OCR noise seen on this file, e.g. a digit substituted for a
letter inside the month abbreviation) and used as the anchor for the
trailing TSN/CSN pair (TSN may print as a genuine `Unknown`/`UNKNOWN`
sentinel when a component's prior life isn't tracked -- confirmed on real
rows -- kept as-is rather than treated as a parse failure). Working
backward from INSTALL_DATE, the token(s) immediately before it are taken as
POSITION -- two tokens only when the second-to-last one matches a small,
closed set of real sub-zone modifier codes seen on this file (side/end
qualifiers like forward/aft/inboard/outboard/upper/lower and cockpit valve
abbreviations); otherwise POSITION is the single token immediately before
the date. The two tokens before POSITION are SERIAL_NUMBER then
PART_NUMBER; everything remaining between ATA and PART_NUMBER is
DESCRIPTION.

Known limitation, confirmed directly against the real sample file: OCR
quality is markedly worse on the file's later page than its first --
several rows there have words fused together with no separating space
(e.g. a part-number/description boundary collapsing into one token), which
this whitespace-token heuristic cannot recover cleanly. Those rows either
fail the leading-ATA-chapter anchor entirely (silently dropped, same as
header/footer noise) or parse with a genuinely wrong PART_NUMBER/
SERIAL_NUMBER/POSITION split; the latter is expected to surface as
validation flags downstream rather than being silently "corrected" here --
per this project's soft-validation convention (see
`shared/aviation_rules.py`), a suspicious cell is flagged, never guessed or
dropped.
"""
from __future__ import annotations
import re

from sheet_types.occm_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, page_count

NAME = "Aircraft Fitlist (OCCM)"

# This module's known source file has no text layer at all (confirmed via
# pdfplumber -- near-zero chars on every page), so these SIGNATURES can
# never fire through occm.py's normal pdfplumber head-text match; real
# detection happens via ocr_detect() below. Kept here anyway (per this
# project's convention) as a documented anchor and a safety net for any
# future born-digital re-export of the same template. Checked for
# collisions against every SIGNATURES list in sheet_types/{occm,ht,llp}.py
# and every existing variant file first: neither phrase appears anywhere
# else, and neither is a substring of (nor contains) any other variant's
# own SIGNATURES entries.
SIGNATURES = [
    "AIRCRAFT FITLIST (OCCM)",
    "PART NUMBER SERIAL NUMBER POSITION INST-DATE",
]

CANONICAL_COLUMNS = [
    "ATA",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "POSITION",
    "INSTALL_DATE",
    "TSN",
    "CSN",
    # Header metadata, parsed once per file and stamped on every row.
    "MSN",
    "REPORT_DATE",
    "HEADER_TSN",
]

_NUM_RULE = {"pattern": r"^(?:UNKNOWN|[\d:]+)$", "allow_empty": True}
_OVERRIDES = {
    "DESCRIPTION": {"uppercase": True},
    # POSITION is usually a single code (a bare side letter or digit), but
    # confirmed on real rows to sometimes be two space-separated tokens
    # (see module docstring) -- the global default column rules have no
    # entry for POSITION at all, so this is defined fresh here rather than
    # overridden.
    "POSITION": {
        "pattern": r"^[A-Z0-9][A-Z0-9 /\-]{0,20}$",
        "uppercase": True,
        "allow_empty": True,
    },
    # Loose on purpose: real dates on this file are "<D[D]>.<Mon>.<YYYY>"
    # but OCR noise substitutes stray digits/symbols for letters inside the
    # month abbreviation (confirmed directly, e.g. a "c" misread as a
    # non-letter glyph) -- flag genuinely malformed dates rather than
    # reject this whole, otherwise-valid shape.
    "INSTALL_DATE": {
        "pattern": r"^\d{1,2}\W?[A-Za-z0-9\W]{2,6}\W?\d{4}$",
        "allow_empty": True,
    },
    "TSN": _NUM_RULE,
    "CSN": _NUM_RULE,
    "MSN": {"pattern": r"^\d{1,6}$", "allow_empty": True},
    "REPORT_DATE": {"allow_empty": True},
    # Relaxed rather than pattern-enforced: this is a single stamped
    # header value repeated identically on every row of the file, so a
    # tight pattern here would either flag every single row over one OCR
    # misread in one place, or none at all -- neither is a useful signal
    # at row granularity. Genuine per-row corruption is still caught by
    # the row-level TSN rule above.
    "HEADER_TSN": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Leading ATA chapter, often glued directly onto the next word by OCR with
# no separating space (confirmed directly on the real file, e.g. a stray
# "/" or "|" border-line artifact between the chapter and the first
# description word) -- peeled off with a regex rather than a plain
# whitespace split.
_LEAD_RE = re.compile(r"^\s*[|\[({]*\s*(\d{1,2})\s*[/|)\].]*\s*(.*)$")

# A date token's shape: 1-2 digit day, a short punctuation-delimited middle
# chunk (the month abbreviation, tolerating OCR noise), a 4-digit year.
_DATE_RE = re.compile(r"^\d{1,2}\W?\S{2,6}\W?\d{4}$")

# Closed set of real sub-zone/side modifier codes confirmed on this file's
# rows, used only to decide whether POSITION is one or two tokens wide.
_MODIFIER_RE = re.compile(
    r"^(?:FWD|AFT|INBD|OUTBD|OTBD|UPR|LWR|CKPT|TMV|TCV)$", re.IGNORECASE
)

_MSN_RE = re.compile(r"\bMSN\s+(\d+)")
_DATE_HDR_RE = re.compile(r"\bDate:\s*(\S+)")
_TSN_HDR_RE = re.compile(r"\bTSN\s*-?\s*([\d:]+)")


def _parse_header_meta(text: str) -> dict:
    meta = {"MSN": "", "REPORT_DATE": "", "HEADER_TSN": ""}
    m = _MSN_RE.search(text)
    if m:
        meta["MSN"] = m.group(1)
    m = _DATE_HDR_RE.search(text)
    if m:
        meta["REPORT_DATE"] = m.group(1)
    m = _TSN_HDR_RE.search(text)
    if m:
        meta["HEADER_TSN"] = m.group(1)
    return meta


def _parse_line(line: str, page_num: int) -> dict | None:
    m = _LEAD_RE.match(line)
    if not m:
        return None
    ata = m.group(1)
    toks = [t.strip("|[]") for t in m.group(2).split()]
    if len(toks) < 5:
        return None

    date_idx = None
    for i in range(len(toks) - 1, -1, -1):
        if _DATE_RE.match(toks[i]):
            date_idx = i
            break
    if date_idx is None or date_idx < 3:
        return None

    after = toks[date_idx + 1:]
    tsn = after[0] if len(after) > 0 else ""
    csn = after[1] if len(after) > 1 else ""

    head = toks[:date_idx]
    pos_tokens = [head[-1]]
    rest = head[:-1]
    if rest and (_MODIFIER_RE.match(head[-1]) or _MODIFIER_RE.match(rest[-1])):
        pos_tokens.insert(0, rest[-1])
        rest = rest[:-1]
    if len(rest) < 2:
        return None
    sn = rest[-1]
    pn = rest[-2]
    description = " ".join(rest[:-2])
    if not description:
        return None

    return {
        "ATA": ata,
        "DESCRIPTION": description,
        "PART_NUMBER": pn,
        "SERIAL_NUMBER": sn,
        "POSITION": " ".join(pos_tokens),
        "INSTALL_DATE": toks[date_idx],
        "TSN": tsn,
        "CSN": csn,
        "_page": page_num,
    }


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback (see
    sheet_types/occm.py) -- this variant's known source file has no text
    layer at all, so it can never be found through the normal pdfplumber
    head-text match.

    Requires BOTH the report title ("AIRCRAFT FITLIST (OCCM)") and a
    distinctive fragment of the column-header row ("INST-DATE") in the
    same header-band crop, so a different scanned OCCM report that merely
    shares generic title wording doesn't get claimed here by mistake.
    """
    try:
        img = await render_page(pdf_path, 0, dpi=300)
        w, h = img.size
        crop = img.crop((0, 0, w, int(h * 0.2)))
        text = (await ocr_text(crop, psm=6)).upper()
        return "AIRCRAFT FITLIST" in text and "OCCM" in text and "INST-DATE" in text
    except Exception:
        return False


async def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    n_pages = await page_count(pdf_path)
    meta = {"MSN": "", "REPORT_DATE": "", "HEADER_TSN": ""}
    for page_index in range(n_pages):
        img = await render_page(pdf_path, page_index, dpi=300)
        text = await ocr_text(img, psm=4)
        if page_index == 0:
            meta = _parse_header_meta(text)
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
