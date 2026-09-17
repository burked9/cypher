"""AMOS "Aircraft-Reference-Equipment-List" — HT-side variant.

This is a distinct AMOS/Swiss-AS export template from the plain
`ht_variants/amos.py` "Aircraft Equipment List Report" — the title carries
an extra "Reference" segment, and the row layout differs enough (extra
"Main" flag column, doubled part-description column, per-requirement
continuation sub-rows) that it needs its own parser rather than reuse.

Extraction strategy — why this isn't plain `pdfplumber.extract_text()`
-----------------------------------------------------------------------
On this template, pdfplumber's line/word grouping is unreliable: whenever a
cell's text is wider than its column (a common occurrence here — ATA
section names, long part descriptions), the PDF's content stream still
positions the overflow characters at their natural (too-wide) x-coordinates,
which land on top of the *next* column's glyphs. `extract_text()`/
`extract_words()` re-sort characters purely by x-position, so an overflowing
run and the next column's run get shuffled together into one unreadable
blob (e.g. a part number merging with the tail of a section name).

The fix: `page.chars` preserves each character in PDF **content-stream**
order, not x-sorted order. Within that order, one field's characters are
drawn as one contiguous burst before the next field starts — even when the
two fields' x-ranges overlap once rendered. So per visual line (grouped by
`top`), we walk chars in original stream order and start a new "run"
whenever either (a) the x-gap to the next char is large (a normal
column/word boundary) or (b) the x-position jumps backward past the
running-max x1 (the overlap signature described above). Each resulting run
is a clean field value, in true column order, regardless of the visual
overlap. This was verified against the rendered page image: characters that
looked garbled in `extract_text()` decoded correctly once read in stream
order.

Row shape (per data line, ATA optional — carried forward within a
section):
    [ATA]  [SECTION_DESC — discarded]  PART_NUMBER  SERIAL_NUMBER
    DESCRIPTION  MAIN(Y/N)  [POS]  RELEASE_LABEL  INST_DATE  TSN  CSN

Per-requirement continuation sub-rows ("Requirement / Interval / TSR / To
go" and the data line under it) are intentionally NOT extracted here —
same design choice as `ht_variants/amos.py`'s docstring: the position
fingerprint (ATA + POS + PART_NUMBER + SERIAL_NUMBER + INST_DATE + TSN/CSN)
doesn't need them, and those sub-rows never carry a part/serial anchor of
their own.

Known source-data limitation (not a parser bug): some long part
descriptions and release labels are genuinely truncated mid-word in the
source PDF's own content stream — the missing characters were never drawn
at all (confirmed against the rendered page image), not merely hidden by
overlap. Those fields come through short; nothing to recover.

Occasionally a POS value overflows forward into the RELEASE_LABEL column
with no detectable boundary (a forward, not backward, overlap — the two
runs merge with no gap to split on). Rather than guess a split point, the
whole merged text is kept in RELEASE_LABEL and POS is left empty in that
case.
"""
from __future__ import annotations
import re

import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "AMOS HT (Aircraft-Reference-Equipment-List)"
SIGNATURES = [
    "Aircraft-Reference-Equipment-List",
    "Ref.-Tree HT NG",
]

CANONICAL_COLUMNS = [
    "ATA",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
    "MAIN",
    "POS",
    "RELEASE_LABEL",
    "INST_DATE",
    "TSN",
    "CSN",
]

_OVERRIDES = {
    "MAIN": {"pattern": r"^[YN]$", "uppercase": True, "allow_empty": True},
    "POS": {"allow_empty": True},
    "RELEASE_LABEL": {"allow_empty": True},
    "INST_DATE": {"pattern": r"^\d{1,2}\.[A-Za-z]{3}\.\d{4}$"},
    "TSN": {},
    "CSN": {},
}
RULES = merged_rules(_OVERRIDES)

_DATE_RE = re.compile(r"\d{1,2}\.[A-Za-z]{3}\.\d{4}")
_ATA_RE = re.compile(r"^\d{2}(?:-\d{2}){0,2}$")

_GAP_BREAK = 4.0     # forward gap (pt) beyond which we start a new run
_OVERLAP_BREAK = -1.5  # backward gap (pt) beyond which we start a new run
                       # (small negative kerning overlaps are normal and stay
                       # in the same run; this threshold is well inside the
                       # -20..-40pt overlaps actually seen from overflow)


def _line_runs(page) -> list[tuple[float, list[str]]]:
    """Group a page's chars by visual line (top), preserving PDF
    content-stream order within each line, and split into field "runs"."""
    lines: dict[float, list] = {}
    order: list[float] = []
    for c in page.chars:
        key = round(c["top"], 1)
        if key not in lines:
            lines[key] = []
            order.append(key)
        lines[key].append(c)

    results = []
    for key in order:
        cs = lines[key]
        runs = [[cs[0]]]
        for prev, c in zip(cs, cs[1:]):
            gap = c["x0"] - prev["x1"]
            if gap > _GAP_BREAK or gap < _OVERLAP_BREAK:
                runs.append([c])
            else:
                runs[-1].append(c)
        texts = ["".join(ch["text"] for ch in r).strip() for r in runs]
        results.append((key, [t for t in texts if t]))
    return results


def _parse_row(runs: list[str], current_ata: str) -> tuple[dict | None, str]:
    """Parse one line's runs as a main data row. Returns (record_or_None,
    updated_current_ata)."""
    if len(runs) < 7:
        return None, current_ata

    date_idx = None
    date_match = None
    for i, t in enumerate(runs):
        m = _DATE_RE.search(t)
        if m:
            date_idx = i
            date_match = m
            break
    if date_idx is None or date_idx + 2 >= len(runs):
        return None, current_ata

    tsn = runs[date_idx + 1]
    csn = runs[date_idx + 2]
    inst_date = date_match.group()
    release_prefix = runs[date_idx][: date_match.start()].strip()

    has_ata = (
        bool(_ATA_RE.match(runs[0])) and len(runs) >= 9 and date_idx >= 4
    )
    start = 2 if has_ata else 0
    new_ata = runs[0] if has_ata else current_ata

    if release_prefix:
        # RELEASE_LABEL and INST_DATE were merged into one run by overflow;
        # the run just before this one is NOT part of the release label.
        release_label = release_prefix
        pos_idx_candidate = date_idx - 1
    else:
        if date_idx - 1 < start + 2:
            return None, new_ata
        release_label = runs[date_idx - 1]
        pos_idx_candidate = date_idx - 2

    if pos_idx_candidate < start + 2:
        return None, new_ata

    pos = ""
    main = ""
    if runs[pos_idx_candidate] in ("Y", "N"):
        main = runs[pos_idx_candidate]
        desc_end = pos_idx_candidate
    else:
        pos = runs[pos_idx_candidate]
        main_idx = pos_idx_candidate - 1
        if main_idx >= start + 2 and runs[main_idx] in ("Y", "N"):
            main = runs[main_idx]
            desc_end = main_idx
        else:
            # No clean Y/N anchor found nearby -- never guess. Fold the
            # ambiguous token back into the description catch-all instead
            # of mis-assigning it to MAIN or dropping it.
            desc_end = pos_idx_candidate

    if desc_end < start + 2:
        return None, new_ata

    part_number = runs[start]
    serial_number = runs[start + 1]
    description = " ".join(runs[start + 2 : desc_end]).strip()

    record = {
        "ATA": new_ata,
        "PART_NUMBER": part_number,
        "SERIAL_NUMBER": serial_number,
        "DESCRIPTION": description,
        "MAIN": main,
        "POS": pos,
        "RELEASE_LABEL": release_label,
        "INST_DATE": inst_date,
        "TSN": tsn,
        "CSN": csn,
    }
    return record, new_ata


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    current_ata = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            for _, runs in _line_runs(page):
                rec, current_ata = _parse_row(runs, current_ata)
                if rec is not None:
                    rec["_page"] = page_num
                    records.append(rec)
    return records
