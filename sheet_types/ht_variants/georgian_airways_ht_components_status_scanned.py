"""Georgian Airways "HARD TIME COMPONENTS STATUS" report — scanned copy,
OCR required.

Same underlying template and row shape as the born-digital
`georgian_airways_ht_components_status.py` sibling in this package (see its
docstring for the full header/column layout and the row-anchor design this
module reuses), but the files this module targets have no extractable text
layer at all (ScanSnap-style image scans), so that parser's plain-pdfplumber
signature match never fires. This module renders each page and OCRs it
directly instead, same pattern as `amos_scanned.py` in this package.

Row anchor is unchanged in spirit: the `NN-NNN-NN` task code at line start,
then DESCRIPTION / PART_NUMBER / SERIAL_NUMBER / POSITION, then a TASK
vocabulary word, then a STATUS_TRAIL catch-all for everything after (kept
as one string for the same reason the born-digital sibling gives: the
trailing MAINT/LIMIT/NEXT-DUE/REMAINING block is column-ragged and not
reliably splittable from whitespace tokens alone). Example, values
genericized::

    24-120-00 Main and APU Battery 024147-000 099766 Auxiliary 1-Aug-2017
        DeepCycle 55177 34365 8-Aug-2017 2000 57177 129

Everything below this point is OCR-specific tolerance layered on top of
that same design, worked out by inspecting real OCR'd text (tesseract
`--psm 6`) from files in this cluster:

  * **Line junk.** Ruled table borders and blank cells regularly OCR as
    stray punctuation glyphs (`_`, `~`, em/en dashes, smart quotes,
    brackets) glued onto the start of the task-code token or floating as
    their own token mid-row (e.g. a blank SERIAL_NUMBER cell reads as a
    bare `_`). These are stripped at the line level before tokenizing —
    same move `amos_scanned.py` makes for its own noisy grid — rather than
    guessing what character was actually under the smudge.

  * **INSTALL_DATE format.** Unlike the born-digital file's `DD.MM.YYYY`
    dates, OCR text from this cluster's scans shows `D-Mon-YYYY` dates
    (e.g. "6-Dec-2017") as the dominant form, with an occasional
    `DD.MM.YYYY` survivor. Both are accepted as the date anchor.

  * **TASK vocabulary.** OCR sometimes glues a two-word task ("Deep
    Cycle", "Hydro Test", "Weight Chk") into one token ("DeepCycle",
    "HydroTest", "WeightChe") — both the spaced and glued forms are
    matched, plus a couple of common misreads (e.g. "Che" for "Chk").

  * **Garbled/duplicate lines.** OCR on this grid frequently emits a
    second, badly mangled echo of a row immediately after (or before) the
    clean one — usually missing a digit group in the task code or reduced
    to noise elsewhere. Such lines simply fail the task-code anchor match
    and are dropped, same as any other unrecognised line; no attempt is
    made to merge or deduplicate against the clean copy, matching this
    parser family's general stance of not guessing a row split it isn't
    confident about.
"""
from __future__ import annotations
import re

from sheet_types.ht_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, page_count

NAME = "Georgian Airways HT Components Status (Scanned)"

# Deliberately empty -- see module docstring. Every known source file in
# this cluster has no usable text layer, so plain-pdfplumber SIGNATURES can
# never fire; detection happens structurally via ocr_detect() below, same
# pattern as amos_scanned.py / aircraft_rotables_ht_scanned.py.
SIGNATURES: list[str] = []

CANONICAL_COLUMNS = [
    "ATA",
    "TASK_CODE",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "POSITION",
    "INSTALL_DATE",
    "TASK",
    "STATUS_TRAIL",
]
_OVERRIDES = {
    "TASK_CODE":     {"pattern": r"^\d{2}-\d{3}-\d{2}$"},
    "PART_NUMBER":   {"allow_empty": True},
    "SERIAL_NUMBER": {"allow_empty": True},
    "POSITION":      {"allow_empty": True, "uppercase": True},
    "INSTALL_DATE":  {
        "pattern": r"^\d{1,2}-[A-Za-z]{3}-\d{4}$|^\d{2}\.\d{2}\.\d{4}$",
        "allow_empty": True,
    },
    "TASK":          {"allow_empty": True, "uppercase": True},
    "STATUS_TRAIL":  {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_CODE_RE = re.compile(r"^\d{2}-\d{3}-\d{2}$")
# D-Mon-YYYY (dominant in this OCR'd cluster) or the born-digital sibling's
# DD.MM.YYYY (an occasional survivor in the same corpus).
_DATE_RE = re.compile(r"^\d{1,2}-[A-Za-z]{3}-\d{4}$|^\d{2}\.\d{2}\.\d{4}$")
# Same PART_NUMBER shape test as the born-digital sibling: digits somewhere,
# punctuation/letters otherwise.
_PN_LIKE = re.compile(r"^(?=[A-Z0-9/-]*\d)[A-Z0-9/-]+$")
# Border/leader glyphs OCR emits for ruled table lines and blank cells --
# never real data. Stripped at the line level (not just token ends) so a
# stray glyph glued onto the task code or a bare-junk token mid-row both
# get cleaned the same way.
_BORDER_RE = re.compile(r"[|\[\]<>=~()`*\"'«»‘’“”–—_•·]+")

_TASK_1 = {
    "OPERATIONAL", "REPLACE", "OVERHAUL", "RESTORE", "DISCARD", "DISARD",
    "FUNCTIONAL", "FUNCT", "FNC", "TEST", "INSPECT", "INSPECTION",
    "RESTORARION",
    # OCR-glued two-word tasks (see docstring)
    "DEEPCYCLE", "HYDROTEST", "WEIGHTCHK", "WEIGHTCHE", "LIFELIMIT",
}
_TASK_2 = {
    ("DEEP", "CYCLE"), ("HYDRO", "TEST"), ("WEIGHT", "CHK"),
    ("WEIGHT", "CHE"), ("LIFE", "LIMIT"),
}


def _clean_line(line: str) -> str:
    s = _BORDER_RE.sub(" ", line)
    return " ".join(s.split())


def _find_task(rest: list[str]) -> tuple[int, int]:
    for i, tok in enumerate(rest):
        if i + 1 < len(rest) and (tok.upper(), rest[i + 1].upper()) in _TASK_2:
            return i, 2
        if tok.upper() in _TASK_1:
            return i, 1
    return -1, 0


def _parse_line(line: str, page_num: int) -> dict | None:
    line = _clean_line(line)
    toks = line.split()
    if not toks or not _CODE_RE.match(toks[0]):
        return None
    ata_int = int(toks[0][:2])
    if not (20 <= ata_int <= 83):
        return None
    rest = toks[1:]
    task_idx, task_len = _find_task(rest)
    if task_idx < 0:
        return None
    task = " ".join(rest[task_idx:task_idx + task_len])
    status_trail = " ".join(rest[task_idx + task_len:])
    head = rest[:task_idx]
    install_date = ""
    if head and _DATE_RE.match(head[-1]):
        install_date = head.pop()
    pn_idx = next((i for i, t in enumerate(head) if _PN_LIKE.match(t)), None)
    if pn_idx is None:
        description, pn, sn, position = " ".join(head), "", "", ""
    else:
        description = " ".join(head[:pn_idx])
        pn = head[pn_idx]
        after_pn = head[pn_idx + 1:]
        sn = after_pn[0] if after_pn else ""
        position = " ".join(after_pn[1:])
    return {
        "ATA": toks[0][:2],
        "TASK_CODE": toks[0],
        "DESCRIPTION": description,
        "PART_NUMBER": pn,
        "SERIAL_NUMBER": sn,
        "POSITION": position,
        "INSTALL_DATE": install_date,
        "TASK": task,
        "STATUS_TRAIL": status_trail,
        "_page": page_num,
    }


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback (see
    sheet_types/ht.py) -- this variant's SIGNATURES is deliberately empty
    (see module docstring).

    Anchors on the report title and operator name, both of which OCR
    cleanly near the top of page 1 even though the data grid below does
    not -- "GEORGIAN AIRWAYS" and "HARD TIME COMPONENTS STATUS" (the same
    two phrases the born-digital sibling's SIGNATURES entry is built from).
    """
    try:
        img = await render_page(pdf_path, 0, dpi=300)
        w, h = img.size
        crop = img.crop((0, 0, w, int(h * 0.25)))
        text = (await ocr_text(crop, psm=6)).upper()
        return "GEORGIAN AIRWAYS" in text and "HARD TIME COMPONENTS STATUS" in text
    except Exception:
        return False


async def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    n_pages = await page_count(pdf_path)
    for page_index in range(n_pages):
        img = await render_page(pdf_path, page_index, dpi=300)
        text = await ocr_text(img, psm=6)
        for raw in text.splitlines():
            rec = _parse_line(raw.strip(), page_index + 1)
            if rec is not None:
                records.append(rec)
    return records
