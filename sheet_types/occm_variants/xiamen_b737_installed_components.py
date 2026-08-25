"""Xiamen Airlines B737-75C "List of Installed Components" OCCM — scanned,
no text layer, OCR required.

Confirmed on a small set of real files from a real-corpus triage pass, one
per airframe, each headed "<B-reg> List of Installed Components" / XIAMEN
AIRLINES / PREPARED BY / APPROVED BY / TITLE Quality Manager, with an
AIRFRAME + ENGINE L + ENGINE R + APU MAKE/MODEL-SER NO-TSN-CSN summary
block above the row table. A couple of the source files are literal
duplicates under different filenames (same content, different export
naming).

One sibling file covering the same airframe and repeating the same
AIRFRAME/ENGINE/APU numbers verbatim was deliberately NOT included here:
its title OCRs as "A/C List and Status of Time-controlled Components", not
"List of Installed Components", and its row shape is genuinely different —
an explicit ATA sub-code column and separate Hard Time / Total Time / Used
Time / REMAIN / Next Work Date columns, vs. this format's plain
DESCRIPTION + single TSN/CSN pair. That title phrase is also the one
flagged as the marker for a *separate* Xiamen HT-shaped cluster elsewhere
in the corpus — forcing that sibling file into this module would risk this
variant silently swallowing genuinely HT-shaped exports once that HT
variant exists.

Per pdfplumber, all known files have 0 extractable chars on every page
(confirmed), so ocr_detect()/extract() render every page and OCR it.

Row shape (index, description, part no., serial no., install date, TSN,
CSN, certificate) — no ATA code, no position column, confirmed by cross-
checking multiple clean rows across all known files, e.g.::

    5 | ACT-RAM AIR 541674-4 35-2969 2014-01-04 56613.09 40888 CAAC

Plain pytesseract at 300dpi (`--psm 6`, matching the other OCR variants in
this package) renders the ruled data grid as near-total noise on this
cluster specifically — stray border/gridline pixels OCR as runs of
"S"/"C"/"T"-shaped garbage swallowing whole rows (confirmed: the large
majority of rows unreadable). Upscaling to 400dpi, converting to grayscale,
and hard thresholding to pure black/white before OCR (removing the grid's
antialiased grey fringe, which is what plain psm 6 was choking on) plus
switching to `--psm 4` (single column of variable-sized text, vs psm 6's
uniform block) recovers roughly half the rows cleanly across all known
files. The remaining rows stay too corrupted to anchor on (numeric fields
fused with gridline noise into unrecognisable tokens) and are silently
skipped, the same trade-off `sriwijaya_b737_occm.py` and
`standard_occm.py`'s A305 sub-format make elsewhere in this package: a
wrong guess would be worse than a missing row for cross-operator
part-pricing use.
"""
from __future__ import annotations
import re

from sheet_types.occm_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, page_count

NAME = "Xiamen B737-75C List of Installed Components (Scanned)"

# Never actually fires through the router's normal text-signature match --
# every known source file has no text layer at all (see module docstring);
# kept for interface consistency, and in case a born-digital copy turns up.
# Deliberately NOT added to occm.py's top-level SIGNATURES by this change
# (out of scope here) -- real detection happens via ocr_detect() below.
# "LIST OF INSTALLED COMPONENTS" alone would also substring-match inside
# iberia_listado.py's "LIST OF INSTALLED COMPONENTS (AC or NHA)" header,
# but that variant's files have a real text layer and never reach this
# module's OCR-only detection path, so the two never actually compete.
SIGNATURES = [
    "List of Installed Components",
]

CANONICAL_COLUMNS = [
    "ITEM",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "INSTALL_DATE",
    "TSN",
    "CSN",
    "CERTIFICATE",
]

_OVERRIDES = {
    "ITEM":          {"pattern": r"^\d{1,3}$"},
    "INSTALL_DATE":  {"pattern": r"^\d{4}-\d{2}-\d{2}$"},
    "TSN":           {"pattern": r"^[\d.,]+$", "allow_empty": True},
    "CSN":           {"pattern": r"^[\d.,]+$", "allow_empty": True},
    "CERTIFICATE":   {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_BORDER_RE = re.compile(r"[|\[\]<>=~()`*\"'«»‘’“”–—]+")
_SEP_RUN_RE = re.compile(r"[_]{2,}|\.{3,}|-{3,}")
_ITEM_RE = re.compile(r"^\d{1,3}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# Tolerant of a stray leading/trailing non-digit character (border-glyph
# misread) and of a comma thousands separator, matching the OCR failure
# modes actually observed on this cluster's numeric columns.
_NUM_RE = re.compile(r"^[\d.,]+$")


def _looks_numeric(tok: str) -> bool:
    return bool(tok) and bool(_NUM_RE.match(tok))


_HEADER_NOISE_RE = re.compile(
    r"QUALITY MANAGER|PREPARED BY|APPROVED BY|AS OF DATE", re.IGNORECASE
)


def _parse_line(line: str, page_num: int) -> dict | None:
    # The header block's APU row ("131-9B | P-5104 | 39507:21 | 38935 |
    # TITLE Quality Manager AS OF DATE 2017-01-18") OCRs its leading
    # "131-9B" as plausible digits (e.g. "398") often enough to pass the
    # ITEM anchor below, and always carries the report-generation date --
    # which matches the INSTALL_DATE anchor too. Confirmed false-positive
    # on one source file ("398 | P5104 | ... | TITLE Quality Manager AS OF
    # DATE <report-date>"). Reject outright rather than let it masquerade
    # as a data row.
    if _HEADER_NOISE_RE.search(line):
        return None
    s = _SEP_RUN_RE.sub(" ", _BORDER_RE.sub(" ", line))
    toks = s.split()
    if len(toks) < 4:
        return None
    if not _ITEM_RE.match(toks[0]):
        return None
    date_idx = next((i for i, t in enumerate(toks) if _DATE_RE.match(t)), None)
    if date_idx is None or date_idx < 2:
        return None

    mid = toks[1:date_idx]
    if len(mid) >= 3:
        pn, sn = mid[-2], mid[-1]
        description = " ".join(mid[:-2])
    elif len(mid) == 2:
        pn, sn = mid[0], mid[1]
        description = ""
    else:
        pn, sn, description = mid[0], "", ""
    # A row with no recovered description text is too degraded to be worth
    # keeping -- likely a gridline-noise false match on the ITEM/DATE
    # anchors rather than a real row.
    if not description:
        return None

    tail = toks[date_idx + 1:]
    tsn = csn = ""
    i = 0
    if i < len(tail) and _looks_numeric(tail[i]):
        tsn = tail[i]
        i += 1
    if i < len(tail) and _looks_numeric(tail[i]):
        csn = tail[i]
        i += 1
    certificate = " ".join(tail[i:])

    return {
        "ITEM": toks[0],
        "DESCRIPTION": description,
        "PART_NUMBER": pn,
        "SERIAL_NUMBER": sn,
        "INSTALL_DATE": toks[date_idx],
        "TSN": tsn,
        "CSN": csn,
        "CERTIFICATE": certificate,
        "_page": page_num,
    }


def _to_bw(img):
    """400dpi + grayscale + hard threshold -- see module docstring for why
    plain 300dpi RGB (the other OCR variants' default) OCRs this cluster's
    ruled grid as near-total noise."""
    gray = img.convert("L")
    return gray.point(lambda x: 0 if x < 150 else 255, "1")


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback -- this
    variant's SIGNATURES can never match through the normal pdfplumber
    text-extract path since every known source file has no text layer.

    Anchors on the title phrase, which OCRs reliably even at the cheaper
    300dpi/psm-6 pass this uses (unlike the data grid below it -- see
    module docstring), deliberately excluding the "Time-controlled
    Components" title of the sibling scan-quality cluster covering the
    same airframe (see module docstring).
    """
    try:
        img = await render_page(pdf_path, 0, dpi=300)
        w, h = img.size
        crop = img.crop((0, 0, w, int(h * 0.15)))
        text = (await ocr_text(crop, psm=6)).upper()
        return "LIST OF INSTALLED COMPONENTS" in text and "XIAMEN" in text
    except Exception:
        return False


async def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    n_pages = await page_count(pdf_path)
    for page_index in range(n_pages):
        img = await render_page(pdf_path, page_index, dpi=400)
        bw = _to_bw(img)
        text = await ocr_text(bw, psm=4)
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            rec = _parse_line(line, page_index + 1)
            if rec is not None:
                records.append(rec)
    return records
