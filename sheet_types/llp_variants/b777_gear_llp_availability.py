"""Boeing 777 gear LLP availability list -- "Available hours/cycles for
Component life limited parts at Airframe hours/cycles <TSN> / <CSN>". One
file per main-gear leg (confirmed on SYG's LH and RH MLG, MC0765P0366 /
MC0768P0367); the two share every header field and column, differing only
in position, serial numbers and the specific parts fitted.

No text layer (0 chars, 4 pages on both known files) but a clean
computer-rendered raster like sheet_types/llp_variants/kalstar_aviation_
llp_status.py's scans, not a photographed one -- plain psm 6 OCR reads
nearly every row correctly in one pass, no grid-cell cropping needed.

One row per part, single line::

    1 32 777M1H45 161W1163-4 AXLE CENTER WHM1157 86200* 65698 12022 74178
    2 32 RHMAIN 777M2000 161W1000-42 MAIN LANDING GEAR RH MC0768P0367 24739 5838 65835 12178 NA NA

    ITEM_NO ATA_CHAPTER [POSITION] IIN PART_NUMBER DESCRIPTION... SERIAL_NUMBER
    [TSO_HR_LIMIT] CSO_CYC_LIMIT TSN CSN [AVAILABLE_HOURS] AVAILABLE_CYCLES

PART_NUMBER anchors the row (Boeing's `\\d{3}[A-Z]\\d{3,4}-\\d{1,2}` shape,
the same one used in b737_gear_llp_inventory.py, coincidentally) rather
than ITEM_NO: the leading item number OCRs as outright garbage on a good
number of rows ("KP", "se", "e" for what the sequence shows must be
30/34/35) while PART_NUMBER never does, so ITEM_NO is read best-effort and
left blank rather than gating the row on it.

Most parts carry only a cycle limit -- TSO_HR_LIMIT and AVAILABLE_HOURS
both print blank, leaving 4 trailing values instead of 6. Matched at fixed
length (try 6, then 4), not an open-ended walk-back: at least one serial
number in this data is itself a bare digit string ("947") and would
otherwise be swallowed into the trail. A handful of rows lose just their
last (AVAILABLE_CYCLES) value to an isolated OCR misread ("74022" -> "i",
"74178" -> "7A178") despite the rest of the row reading cleanly -- for
those, the same 6-/4-length check is retried one position further in,
treating the actual last token as unreadable rather than dropping the
whole row over a single bad value.

The CSO_CYC_LIMIT figure carries a trailing hard/soft/revised-life-basis
marker per the page footnote (*, **, ***) which OCRs as anything from a
clean asterisk to a stray quote or degree sign -- stripped rather than
captured, since no marker in this data was ever legibly more than one
character and getting that character exactly right isn't load-bearing.
"""
from __future__ import annotations
import re

from sheet_types.llp_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, page_count

NAME = "B777 Gear LLP Availability"
SIGNATURES = [
    "Available hours/cycles for Component life limited parts",
    "TSLV/CSLV",
]

CANONICAL_COLUMNS = [
    "ITEM_NO",
    "ATA_CHAPTER",
    "POSITION",
    "IIN",
    "PART_NUMBER",
    "DESCRIPTION",
    "SERIAL_NUMBER",
    "TSO_HR_LIMIT",
    "CSO_CYC_LIMIT",
    "TSN",
    "CSN",
    "AVAILABLE_HOURS",
    "AVAILABLE_CYCLES",
    # File-level metadata -- same on every row (header repeats per page).
    "COMPONENT_DESCRIPTION",
    "TOP_PART_NUMBER",
    "TOP_SERIAL_NUMBER",
    "TOP_IIN",
    "AIRCRAFT_REG",
    "TOP_POSITION",
    "DATE_INSTALLED",
    "TOP_TSN",
    "TOP_CSN",
    "TOP_TSLV",
    "TOP_CSLV",
    "REMARKS",
    "AIRFRAME_HOURS",
    "AIRFRAME_CYCLES",
]

_CYCLE_RULE = {"pattern": r"^\d*$", "allow_empty": True,
               "int_range": (0, 90000), "int_range_review": (0, 55000)}
_HOUR_RULE = {"pattern": r"^\d*$", "allow_empty": True, "int_range": (0, 100000)}
_NA_CYCLE_RULE = {"pattern": r"^(NA|\d*)$", "allow_empty": True,
                   "int_range": (0, 90000), "int_range_review": (0, 55000)}
_NA_HOUR_RULE = {"pattern": r"^(NA|\d*)$", "allow_empty": True, "int_range": (0, 100000)}
_OVERRIDES = {
    "ITEM_NO":        {"pattern": r"^\d*$", "allow_empty": True},
    "ATA_CHAPTER":    {"pattern": r"^\d*$", "allow_empty": True},
    "TSO_HR_LIMIT":   _HOUR_RULE,
    "CSO_CYC_LIMIT":  _CYCLE_RULE,
    "TSN":            {"pattern": r"^\d*$", "allow_empty": True, "int_range": (0, 100000)},
    "CSN":            _CYCLE_RULE,
    "AVAILABLE_HOURS":  _NA_HOUR_RULE,
    "AVAILABLE_CYCLES": _NA_CYCLE_RULE,
    "AIRCRAFT_REG":   {"pattern": r"^[A-Z0-9\-]+$", "uppercase": True},
    "TOP_POSITION":   {"uppercase": True},
    "POSITION":       {"uppercase": True},
    "DATE_INSTALLED": {"pattern": r"^\d{1,2}-[A-Za-z]{3}-\d{4}$"},
}
RULES = merged_rules(_OVERRIDES)

_DPI = 300
# Letter fixed to "W" rather than [A-Z]: every real PN here is "161W...",
# and the E307/b737_gear_llp_inventory.py family's own PNs use the same
# \d{3}[A-Z]\d{3,4}-\d{1,2} shape but always with "A" ("162A1100-7",
# "161A1100-40") -- pinning the letter keeps this anchor from also lighting
# up on that unrelated format's real part numbers. Left otherwise loose on
# the leading digits: one row's PN OCRs as "461W1164-4" (should be
# "161W..."), and a mismatched leading digit there is still worth the row.
_PN_RE = re.compile(r"^\d{3}W\d{3,4}-\d{1,2}$")
_TRAIL_TOK_RE = re.compile(r'^(?:[\d,]+[*"\'°]*|NA)$', re.I)
_TRAIL_LENS = (6, 4)
_NOISE_TOK_RE = re.compile(r"^[.\-_;:,'\"]+$")
_GLUED_MARKER_RE = re.compile(r"(\d)\s+([*\"'°])")

_TITLE_RE = re.compile(
    r"Airframe hours/cycles\s*:?\s*(\d+)\s*/\s*(\d+)", re.I)
_COMPONENT_DESC_RE = re.compile(r"Component Description\s*:\s*(.+)", re.I)
_TOP_RE = re.compile(
    r"Part Number\s*[:>]\s*(\S+)\s+Serial [Nn]umber\s*:\s*(\S+)\s+I?[il1]?[iI]?N\s*[:>]\s*(\S+)", re.I)
_REG_RE = re.compile(r"Aircraft Reg\s*:\s*(\S+)", re.I)
_TOP_POSITION_RE = re.compile(r"\bPosition\s*:\s*(\S+)", re.I)
_DATE_INSTALLED_RE = re.compile(r"Date Install\w*\s*:\s*(\S+)", re.I)
_TSN_CSN_RE = re.compile(r"TSN\s*/\s*CSN\s*[:>]\s*(\S+)\s*/\s*(\S+)", re.I)
_TSLV_CSLV_RE = re.compile(r"TSLV\s*/\s*CSLV\s*:\s*(\S+)\s*/\s*(\S+)", re.I)
_REMARKS_RE = re.compile(r"Remarks\s*:\s*(.+)$", re.I | re.M)


async def _page_image(pdf_path: str, page_index: int, dpi: int = _DPI):
    return await render_page(pdf_path, page_index, dpi=dpi)


async def _ocr_all_pages(pdf_path: str) -> list[str]:
    n = await page_count(pdf_path)
    texts = []
    for i in range(n):
        img = await render_page(pdf_path, i, dpi=_DPI)
        texts.append(await ocr_text(img, psm=6))
    return texts


def _parse_meta(text: str) -> dict:
    meta: dict[str, str] = {}
    m = _TITLE_RE.search(text)
    if m:
        meta["AIRFRAME_HOURS"], meta["AIRFRAME_CYCLES"] = m.group(1), m.group(2)
    m = _COMPONENT_DESC_RE.search(text)
    if m:
        meta["COMPONENT_DESCRIPTION"] = m.group(1).strip()
    m = _TOP_RE.search(text)
    if m:
        meta["TOP_PART_NUMBER"], meta["TOP_SERIAL_NUMBER"], meta["TOP_IIN"] = m.groups()
    m = _REG_RE.search(text)
    if m:
        meta["AIRCRAFT_REG"] = m.group(1)
    m = _TOP_POSITION_RE.search(text)
    if m:
        meta["TOP_POSITION"] = m.group(1)
    m = _DATE_INSTALLED_RE.search(text)
    if m:
        meta["DATE_INSTALLED"] = m.group(1)
    m = _TSN_CSN_RE.search(text)
    if m:
        meta["TOP_TSN"], meta["TOP_CSN"] = m.groups()
    m = _TSLV_CSLV_RE.search(text)
    if m:
        meta["TOP_TSLV"], meta["TOP_CSLV"] = m.groups()
    m = _REMARKS_RE.search(text)
    if m:
        meta["REMARKS"] = m.group(1).strip()
    return meta


def _clean_trail_val(tok: str) -> str:
    if tok.upper() == "NA":
        return "NA"
    return re.sub(r"\D", "", tok)


def _find_trail(toks: list[str]):
    for n in _TRAIL_LENS:
        if len(toks) >= n and all(_TRAIL_TOK_RE.match(t) for t in toks[-n:]):
            return [_clean_trail_val(t) for t in toks[-n:]], toks[:-n]
    # Retry one token further in: covers a lone unreadable AVAILABLE_CYCLES
    # value at the true end of the row (see module docstring).
    for n in _TRAIL_LENS:
        if len(toks) >= n + 1 and all(_TRAIL_TOK_RE.match(t) for t in toks[-(n + 1):-1]):
            return [_clean_trail_val(t) for t in toks[-(n + 1):-1]] + [""], toks[:-(n + 1)]
    return None, toks


def _parse_row(line: str) -> dict | None:
    line = _GLUED_MARKER_RE.sub(r"\1\2", line.strip())
    toks = [t for t in line.split() if t != "|" and not _NOISE_TOK_RE.match(t)]
    pn_idx = next((i for i, t in enumerate(toks) if _PN_RE.match(t)), None)
    if pn_idx is None or pn_idx < 3:
        return None

    trail, head_toks = _find_trail(toks)
    if trail is None:
        trail, sn_and_desc = [], toks[pn_idx + 1:]
    else:
        sn_and_desc = head_toks[pn_idx + 1:]
    if not sn_and_desc:
        return None
    serial_number = sn_and_desc[-1]
    description = " ".join(sn_and_desc[:-1])
    if not description:
        return None

    # ITEM_NO's own OCR is unreliable enough (garbled outright, or preceded
    # by a stray leading digit/letter from the row above's border) that
    # ITEM_NO/ATA_CHAPTER/POSITION can't just be read off toks[0]/toks[1] by
    # fixed position -- every row in this report is ATA 32 (it's a single
    # gear leg's own parts list), so that literal token is the one stable
    # anchor in the ITEM..IIN span; ITEM_NO and POSITION are read relative
    # to wherever it actually falls rather than assumed to sit at index 0/1.
    lead = toks[:pn_idx - 1]
    ata_idx = next((i for i, t in enumerate(lead) if t == "32"), None)
    if ata_idx is None:
        rec = {c: "" for c in CANONICAL_COLUMNS}
        rec["ITEM_NO"] = ""
        rec["ATA_CHAPTER"] = ""
        rec["POSITION"] = " ".join(t for t in lead if not _NOISE_TOK_RE.match(t))
    else:
        item_candidates = [t for t in lead[:ata_idx] if t.isdigit()]
        rec = {c: "" for c in CANONICAL_COLUMNS}
        rec["ITEM_NO"] = item_candidates[-1] if item_candidates else ""
        rec["ATA_CHAPTER"] = "32"
        rec["POSITION"] = " ".join(t for t in lead[ata_idx + 1:] if t not in ("=",))
    rec["IIN"] = toks[pn_idx - 1]
    rec["PART_NUMBER"] = toks[pn_idx]
    rec["DESCRIPTION"] = description
    rec["SERIAL_NUMBER"] = serial_number
    if len(trail) == 6:
        (rec["TSO_HR_LIMIT"], rec["CSO_CYC_LIMIT"], rec["TSN"], rec["CSN"],
         rec["AVAILABLE_HOURS"], rec["AVAILABLE_CYCLES"]) = trail
    elif len(trail) == 4:
        rec["CSO_CYC_LIMIT"], rec["TSN"], rec["CSN"], rec["AVAILABLE_CYCLES"] = trail
    return rec


async def ocr_detect(pdf_path: str) -> bool:
    try:
        img = await _page_image(pdf_path, 0, dpi=_DPI)
        crop = img.crop((0, 0, img.width, int(img.height * 0.15)))
        text = (await ocr_text(crop, psm=6)).upper()
        return "AVAILABLE HOURS" in text and "LIFE LIMITED PARTS" in text
    except Exception:
        return False


async def extract(pdf_path: str) -> list[dict]:
    pages = await _ocr_all_pages(pdf_path)
    meta = _parse_meta("\n".join(pages))

    records: list[dict] = []
    for page_num, text in enumerate(pages, start=1):
        for raw in text.splitlines():
            line = raw.strip()
            # The header block repeats on every page and re-prints the
            # assembly's own PN/SN/IIN on one line -- a real 161W-shaped
            # PN, so it otherwise passes the row anchor and duplicates row 2.
            if not line or "End Of Report" in line or "serial" in line.lower():
                continue
            rec = _parse_row(line)
            if rec is None:
                continue
            for k, v in meta.items():
                rec[k] = v
            rec["_page"] = page_num
            records.append(rec)
    return records
