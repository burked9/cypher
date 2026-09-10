"""Aircraft Build OCCM Status -- scanned, no text layer, page stored sideways.

Same underlying report template as `aircraft_build_occm_status_scanned.py`
(identical title, identity-line header, and ruled ATA/Position/Zone/Part
Number/Description/Serial/Last Movement/Batch Number/Unit/Since New-Fit-
Overhaul-Repair grid, confirmed directly by rendering a real sample file
and comparing side by side) -- but that module's known source file stores
each page already landscape (wide enough for the grid). This module's own
known source file instead stores every page portrait-shaped with the
report content drawn sideways inside it (confirmed directly: the page's
own `/Rotate` attribute reads 0 -- pdfplumber/pymupdf report no rotation
metadata at all -- yet the rendered pixels themselves are rotated 90
degrees; this is a scan/export artifact, not a `/Rotate` flag a renderer
would apply automatically, so it has to be detected and corrected here
before OCR). Confirmed directly across the first, a middle, and the last
page of a 30-page real sample file: every page uses the same sideways
orientation and the same rotation direction (rotating the rendered image
90 degrees clockwise -- `Image.rotate(-90, expand=True)` -- reproduces the
correct upright reading orientation each time; the other direction comes
out upside down).

Same detection approach as this package's other aspect-ratio-based
rotation handling (see `occm_parts_compliance_status.py`'s own docstring):
a rendered page whose pixel width is smaller than its height is sideways
relative to this report's own landscape-shaped grid, so it gets rotated
before anything else runs. Confirmed directly: once rotated, the ruled
grid's column pixel positions line up with
`aircraft_build_occm_status_scanned.py`'s own `_BOUNDS` table to within a
few pixels (both known source files render at the same 300 DPI and the
same physical page size once upright), so this module reuses that
module's column-bucketing and row-assembly logic directly rather than
duplicating it -- only the render-then-rotate step and the header/ata-line
OCR anchors (which must run against the corrected, upright crop) are
new here.

SIGNATURES is deliberately empty for the same reason as the sibling
module: known source file has 0 pdfplumber-extractable characters on
every page, so this is only ever reached via `ocr_detect()`'s blank-text
fallback in the router. Checked directly (grep across every SIGNATURES
list in sheet_types/{occm,ht,llp}.py and every existing occm_variants/
ht_variants/llp_variants file): no other module's own SIGNATURES entry is
the bare "AIRCRAFT BUILD" phrase this module's `ocr_detect()` anchors on
(same anchor as the sibling module -- see that module's own SIGNATURES
comment in `sheet_types/occm.py` for the full collision analysis against
`oases.py`). This module cannot collide with the sibling
`aircraft_build_occm_status_scanned.py` module either: that module's own
`ocr_detect()` OCRs the page as rendered, with no rotation step, and was
confirmed directly to return False on this module's own sideways-page
sample file (its header crop OCRs to noise, never "AIRCRAFT BUILD"); this
module's `ocr_detect()` only fires after confirming the page is
portrait-shaped (`width < height`), which the sibling's own known source
file is not (it is already landscape).
"""
from __future__ import annotations
import re

from sheet_types.occm_variants import aircraft_build_occm_status_scanned as _base
from shared.ocr_bridge import render_page, ocr_text, page_count

NAME = "Aircraft Build OCCM Status (Rotated Scan)"

# Deliberately empty -- see module docstring.
SIGNATURES = []

# Same column set as the sibling (upright) variant -- both parse the same
# underlying report template, just from a differently-stored page image.
CANONICAL_COLUMNS = _base.CANONICAL_COLUMNS

# Own copy of the sibling's RULES (not a shared reference -- mutating it in
# place would also change the sibling module's validation) with one
# override: ZONE. Confirmed directly against a real sample file that this
# report's ZONE cell prints as a two-part decimal code (one digit, a
# literal ".", then two digits, e.g. a zone/sub-zone pair) rather than the
# plain 1-4 digit code the sibling module's own RULES assumes -- reusing
# its ZONE rule unchanged would flag essentially every row over a pattern
# mismatch that has nothing to do with actual data quality. The plain
# digit-only shape is kept as a fallback alternative rather than dropped,
# in case a future real file from this same rotated-storage family prints
# ZONE without the decimal (matches the sibling module's own convention of
# not tightening a shared shape needlessly).
RULES = dict(_base.RULES)
RULES["ZONE"] = {**RULES.get("ZONE", {}), "pattern": r"^\d{1,2}\.\d{1,2}$|^\d{1,4}$"}

# Confirmed directly (rendering the real sample file and inspecting
# `ocr_words()` bounding boxes, same technique as the sibling module's own
# `_BOUNDS` derivation): the ZONE and PART_NUMBER cells sit close enough
# together on this file's rendered grid that Tesseract occasionally reads
# them as a single connected word (no OCR-visible space between them,
# apparently because the ruled cell border renders as a touching glyph),
# e.g. a single OCR token "1.17]7121-19971-01AC". Bucketing is done per
# *word*, not per character, so such a glued token lands entirely in
# whichever bucket its center falls into (here, PART_NUMBER, since the
# merged token is wider than the ZONE column alone) -- leaving ZONE empty
# and PART_NUMBER corrupted with a leading zone code. This is corrected
# here rather than by re-tuning `_BOUNDS` (confirmed the merge happens
# regardless of exactly where the boundary is drawn, since it is a single
# OCR token, not two tokens split across it) by recognizing the
# confirmed-distinctive ZONE shape (a single digit, ".", two digits) as a
# safe, unambiguous prefix to peel off: no real PART_NUMBER value in the
# sampled data begins with that exact shape (this report's part numbers
# use hyphens, not a lone leading decimal), so this is not a guess at an
# ambiguous split -- it only fires when ZONE is empty AND PART_NUMBER
# starts with the confirmed shape, and never overwrites a ZONE value that
# was already read correctly on its own.
_ZONE_PREFIX_RE = re.compile(r"^(\d\.\d{2})[\]\}\)\|.,;:]*(.+)$")


def _split_zone_partnumber(rec: dict) -> None:
    if rec.get("ZONE"):
        return
    pn = rec.get("PART_NUMBER", "")
    m = _ZONE_PREFIX_RE.match(pn)
    if not m:
        return
    zone, remainder = m.group(1), m.group(2).strip()
    if not remainder:
        # Nothing left to be a real part number -- leave as-is rather than
        # guess (see module docstring's "never guess a wrong split" rule).
        return
    rec["ZONE"] = zone
    rec["PART_NUMBER"] = remainder


async def _rotate_upright(pdf_path: str, page_index: int):
    """Render one page at 300 DPI and correct the sideways-storage
    artifact described in the module docstring. Only rotates when the
    render itself is portrait-shaped (`width < height`) -- the confirmed
    signature of this report's known sideways-stored files, as opposed to
    the sibling module's own already-landscape source -- so this never
    double-rotates a page that didn't need it."""
    img = await render_page(pdf_path, page_index, dpi=300)
    w, h = img.size
    if w < h:
        img = img.rotate(-90, expand=True)
    return img


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback. Same
    anchor phrases as the sibling (upright) module, run against the
    rotation-corrected crop -- see module docstring for why the two
    modules cannot collide."""
    try:
        img = await render_page(pdf_path, 0, dpi=300)
        w, h = img.size
        if w >= h:
            # Not portrait-shaped -- not this module's known sideways
            # layout (the sibling module's own already-landscape source
            # falls here instead).
            return False
        img = img.rotate(-90, expand=True)
        w2, h2 = img.size
        crop = img.crop((0, 0, w2, int(h2 * 0.22)))
        text = (await ocr_text(crop, psm=6)).upper()
        if "AIRCRAFT BUILD" not in text:
            return False
        return ("SINCE" in text) or ("LAST BATCH" in text) or ("PART NUMBER" in text)
    except Exception:
        return False


async def _parse_header(pdf_path: str) -> dict:
    """Same identity-line parse as the sibling module's own
    `_parse_header`, run against the rotation-corrected page-1 render."""
    meta = {
        "AIRCRAFT_REG": "", "AIRCRAFT_TYPE": "", "MSN": "",
        "MANUFACTURE_DATE": "", "AIRFRAME_TSN": "", "AIRFRAME_CSN": "",
        "LAST_FLIGHT_DATE": "", "LAST_FLIGHT_NUMBER": "",
    }
    try:
        img = await _rotate_upright(pdf_path, 0)
        w, h = img.size
        crop = img.crop((0, 0, w, int(h * 0.20)))
        text = await ocr_text(crop, psm=4)
    except Exception:
        return meta
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    identity_line = ""
    seen_title = False
    for ln in lines:
        if not seen_title:
            if "AIRCRAFT BUILD" in ln.upper():
                seen_title = True
            continue
        identity_line = ln
        break
    if not identity_line:
        return meta
    tokens = [t.strip(_base._HEADER_STRIP) for t in identity_line.split()]
    tokens = [t for t in tokens if t]
    if len(tokens) < 3:
        return meta
    keys = ["AIRCRAFT_REG", "AIRCRAFT_TYPE", "MSN", "MANUFACTURE_DATE",
            "AIRFRAME_TSN", "AIRFRAME_CSN", "LAST_FLIGHT_DATE", "LAST_FLIGHT_NUMBER"]
    for key, tok in zip(keys, tokens):
        meta[key] = tok
    return meta


async def extract(pdf_path: str) -> list[dict]:
    header_meta = await _parse_header(pdf_path)
    records: list[dict] = []
    n_pages = await page_count(pdf_path)
    for page_index in range(n_pages):
        img = await _rotate_upright(pdf_path, page_index)
        # Reuse the sibling module's own row-assembly/bucketing logic
        # directly -- confirmed to line up correctly against the same
        # `_BOUNDS` table once the page is upright (see module docstring).
        page_records = await _base._parse_page(img, page_index + 1)
        for rec in page_records:
            _split_zone_partnumber(rec)
            rec.update(header_meta)
        records.extend(page_records)
    return records
