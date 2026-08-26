""""Aircraft OC/CM List" — mostly scanned/no text layer, OCR required for
most known pages, but see the per-page text-layer note below.

Confirmed on a small set of real files from a real-corpus triage pass, one
per airframe (plus at least one literal duplicate under a different
filename, same content). Header block reads roughly::

    Aircraft OC/CM List
    A/C Registration # : <tail>          A/C TSN : <total>   Last Update Date :
    MSN : <msn>                          A/C CSN : <total>   <yyyy-mm-dd>

followed by a ruled data grid with columns ATA / P/N / S/N / Install Date /
Description / Origin — no per-row TSN/CSN (those totals are aircraft-level,
in the header only) and no position (LH/RH/INBD/OUTBD) column, confirmed by
reading clean rows across every known file directly, e.g.::

    21 | 645405-1 | 109-3633 | 2011-01-24 | RECIRCULATING FAN | PREVIOUS OP'

ORIGIN is a closed set on every known file: TBC, ESR, or "PREVIOUS OP'"
(itself almost certainly a page-margin truncation of "PREVIOUS OPERATOR",
confirmed to never render more fully at any DPI tried) — canonicalised to
"PREVIOUS OPERATOR" below.

A sibling title, "<Operator name> OC/CM List", covering a same-shaped
aircraft-level header but a genuinely different row shape (an extra
LH/RH/INBD/OUTBD position column ahead of P/N, confirmed by direct
inspection) was deliberately NOT folded into this module: its rows OCR
dramatically worse than this cluster's at every DPI/PSM/threshold
combination tried (heavy horizontal-rule strikethrough-style artifacts
fusing adjacent columns into unrecoverable garbage on the large majority of
rows, vs. this cluster's grid which OCRs cleanly), and its title phrase is
distinguishable from this one (operator-prefixed vs. "Aircraft"-prefixed),
so it's left unhandled rather than risking either a low-quality forced
parse or misdetection of genuinely different rows through this module's
column mapping.

Per pdfplumber, most known source files have 0 extractable chars on every
page (confirmed) -- a straight scan, OCR needed throughout. One known file
is a mixed case, though (confirmed directly, not assumed): its cover page
and final (signed) page are image-only like the rest of its cluster, but
every page in between carries a genuine, cleanly-extractable text layer in
the exact same row shape -- almost certainly a "print to PDF" re-export
that got flattened back to an image only for the cover and the
wet-signature page. extract() checks each page's pdfplumber text first and
only falls back to OCR when that page itself has no usable text, so this
file gets fast, error-free extraction on its majority of pages and OCR
only where genuinely needed -- rather than degrading every page to OCR
quality just because *some* pages in the cluster require it.

Plain pytesseract at 300dpi `--psm 4` (single column of variable-sized
text) recovers this cluster's OCR-only pages cleanly -- confirmed the best
of several combinations tried directly against known files (`--psm 6`
recovers only the header block and stops dead at the first data row;
350dpi and a 400dpi-grayscale-hard-threshold pass -- the technique that
helps the noisy Xiamen B737 cluster elsewhere in this package -- both
recover measurably *fewer* clean rows here than plain 300dpi RGB, the
opposite trade-off). Signature-block and page-footer noise at the end of
the last page (free text, timestamps, page counters) never collides with
the row parser below since it requires the line's first token to be a bare
1-2 digit ATA chapter, which that noise never starts with.
"""
from __future__ import annotations
import re

import pdfplumber

from sheet_types.occm_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, page_count

NAME = "Aircraft OC/CM List (Scanned)"

# Most known source files have no text layer on any page and only ever
# reach this variant via ocr_detect()'s blank-text fallback below (see
# module docstring). One known file is a mixed case, though -- most of its
# pages DO carry a real text layer -- so this phrase is kept non-empty
# (unlike a purely-OCR sibling such as xiamen_b737_installed_components.py)
# so occm.py's normal pdfplumber-text signature match routes that file here
# directly too, rather than relying on it slipping through with <50 head
# chars (which it won't, since several of its pages have real text).
# Deliberately NOT added to occm.py's top-level SIGNATURES by this change
# (out of scope here).
SIGNATURES = [
    "Aircraft OC/CM List",
]

CANONICAL_COLUMNS = [
    "ATA",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "INSTALL_DATE",
    "DESCRIPTION",
    "ORIGIN",
]

_OVERRIDES = {
    "INSTALL_DATE": {"pattern": r"^\d{4}-\d{2}-\d{2}$"},
    # Closed set on every known file (TBC / ESR / PREVIOUS OPERATOR), but
    # kept loose here rather than pattern-enforced -- a genuinely new code
    # on a future export of this template should flag for review, not be
    # silently rejected as invalid.
    "ORIGIN": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_BORDER_RE = re.compile(r"[|\[\]<>=~()`*\"'«»‘’“”–—]+")
_SEP_RUN_RE = re.compile(r"_+|\.{3,}|-{3,}")
_ATA_RE = re.compile(r"^\d{1,2}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _parse_line(line: str, page_num: int) -> dict | None:
    s = _SEP_RUN_RE.sub(" ", _BORDER_RE.sub(" ", line))
    toks = s.split()
    if len(toks) < 4:
        return None
    if not _ATA_RE.match(toks[0]):
        return None
    date_idx = next((i for i, t in enumerate(toks) if _DATE_RE.match(t)), None)
    if date_idx is None or date_idx < 2:
        return None

    mid = toks[1:date_idx]
    if len(mid) == 2:
        pn, sn = mid[0], mid[1]
    elif len(mid) == 1:
        pn, sn = mid[0], ""
    else:
        # More than 2 tokens ahead of the date -- an OCR-split P/N or S/N
        # containing a stray space. Keep the first token as P/N and rejoin
        # the rest into S/N rather than guessing which internal space is
        # real; flag-worthy but not worth dropping the row over.
        pn = mid[0]
        sn = " ".join(mid[1:])

    tail = toks[date_idx + 1:]
    if not tail:
        return None

    if len(tail) >= 2 and tail[-2].upper() == "PREVIOUS" and tail[-1].upper() == "OP":
        origin = "PREVIOUS OPERATOR"
        description = " ".join(tail[:-2])
    elif tail[-1].upper() in ("TBC", "ESR"):
        origin = tail[-1].upper()
        description = " ".join(tail[:-1])
    else:
        # Unrecognised origin code -- keep the whole tail as description
        # rather than guessing which trailing token is the code.
        origin = ""
        description = " ".join(tail)

    if not description:
        return None

    return {
        "ATA": toks[0],
        "PART_NUMBER": pn,
        "SERIAL_NUMBER": sn,
        "INSTALL_DATE": toks[date_idx],
        "DESCRIPTION": description,
        "ORIGIN": origin,
        "_page": page_num,
    }


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback -- for
    the known files that have no text layer at all, SIGNATURES can never
    match through the normal pdfplumber text-extract path (occm.py only
    reads pdf.pages[:3], which is all-image on those files), so this is
    the only way they get detected. Files where pdfplumber DOES find text
    (see module docstring on the one known mixed-mode file) are already
    caught by the SIGNATURES match above and never reach this function.

    Anchors on the full "AIRCRAFT OC/CM LIST" title phrase (not just
    "OC/CM LIST" alone), which OCRs reliably even at this cheap 300dpi/
    psm-6 pass and specifically excludes the operator-prefixed sibling
    title covering a different row shape (see module docstring) -- that
    title OCRs as "<OPERATOR> OC/CM LIST", never "AIRCRAFT OC/CM LIST".
    """
    try:
        img = await render_page(pdf_path, 0, dpi=300)
        w, h = img.size
        crop = img.crop((0, 0, w, int(h * 0.15)))
        text = (await ocr_text(crop, psm=6)).upper()
        return "AIRCRAFT OC/CM LIST" in text
    except Exception:
        return False


def _page_text_layer(pdf_path: str, page_index: int) -> str | None:
    """A page's real pdfplumber text, or None if it's too short to be a
    usable text layer (image-only page -- see module docstring on the one
    known mixed-mode file)."""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            if page_index >= len(pdf.pages):
                return None
            text = pdf.pages[page_index].extract_text() or ""
    except Exception:
        return None
    return text if len(text.strip()) >= 20 else None


async def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    n_pages = await page_count(pdf_path)
    for page_index in range(n_pages):
        text = _page_text_layer(pdf_path, page_index)
        if text is None:
            # No usable text layer on this page -- render + OCR it.
            img = await render_page(pdf_path, page_index, dpi=300)
            text = await ocr_text(img, psm=4)
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            rec = _parse_line(line, page_index + 1)
            if rec is not None:
                records.append(rec)
    return records
