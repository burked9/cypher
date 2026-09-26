"""Hard Time Component Status — two-tier ATA-chapter header, born-digital.

Header block (repeats verbatim at the top of every page)::

    HARD TIME COMPONENT STATUS
    MODEL: <model/msn> MFG DATE: <date> LINE No <n> VRV No: <n>
    TOTAL HOURS: <n> TOTAL CYCLES: <n> DATE: <date>
    ATA LAST DATE INSTALLED DATE LAST TIME TIME SINCE INSTALL ALOW TIME INTERVAL REMAIN FOR OH
    DESCRIPTION POSN P/N S/N DUE DATE REMARKS
    chapter OF FORM1 HRS CYC DATE SINCE OH HRS CYC DAYS HRS CYC DAYS HRS CYC DAYS

This is a genuine 3-physical-line column header (the three lines above,
each its own row in `page.extract_text()`) whose words do NOT line up
word-for-word across the three lines — pdfplumber's line-based extraction
just emits each physical text line in y-order, and a merged header cell
that spans two or three of those lines contributes its own words to
whichever line its own baseline happens to fall on. The real column
groupings were recovered from the DATA rows instead of the header text:
`extract_words()` x0 values were histogrammed across every row of the
6-page sample (outside the header band), which produces a clean run of
20 tight x0 clusters separated by consistent double-digit-pixel gaps
(confirmed directly — see column bounds below, one bin per cluster, bin
edges at the midpoint of each gap). The bins are then cross-checked
against the header's own words for a plausible label (e.g. the header's
own "OF FORM1" / "DATE SINCE OH" phrases land inside the
LAST_DATE_INSTALLED / DATE_SINCE_OH bins respectively), but the bin
*boundaries* themselves come from the data, not the header.

Row example (single physical line — the common case)::

    23 BATTERY - ACOUSTIC BEACON CVR DK120 SD35601 18.02.14 2190 1785 18-Feb-20 Battery Repl.MPD Item 23-070-00

Column semantics (best-effort, from the tier-1/tier-3 header words nearest
each bin, cross-checked against real values, e.g. `DUE_DATE` minus
`TOTAL_HOURS`-implied report date roughly equalling `INTERVAL_DAYS` on
several rows): ATA / DESCRIPTION / POSN / PART_NUMBER / SERIAL_NUMBER,
then LAST_DATE_INSTALLED (+ LAST_TIME_HRS/CYC accumulated at that
install), DATE_SINCE_OH (last overhaul date), a
TIME_SINCE_INSTALL_{HRS,CYC,DAYS} triplet, an ALOW_TIME_{HRS,CYC,DAYS}
triplet (the allowable/life-limit basis), an INTERVAL_{HRS,CYC,DAYS}
triplet, then DUE_DATE and REMARKS. Most rows populate only ONE unit
(HRS *or* CYC *or* DAYS) per triplet — the other two cells in that
triplet are genuinely blank in the source, not a parsing miss (confirmed
directly across the whole sample: e.g. a calendar-only battery item
populates only the DAYS cell of a triplet, an hours-tracked hydraulic
fuse only the HRS cell).

Multi-line component groups: a single physical "unit" in this report
sometimes spans several text lines that each become their own record —
e.g. a fire-bottle's pressure-switch check and its hydrostatic test are
two separate lines with their own DUE_DATE/REMARKS but no repeated
PART_NUMBER/SERIAL_NUMBER on the second line (confirmed directly, e.g.
the "№1 ENGINE FIRE BOTTLE LH" block on the sample's page 1). This
parser treats every physical line carrying ANY non-ATA content as its
own record rather than trying to merge these into one row — merging
would require guessing which fields "belong together" across lines with
no reliable anchor, which risks exactly the row-window/value-glue
failure this project's other variants are written to avoid. The
trade-off is that a fraction of records legitimately have blank
DESCRIPTION/PART_NUMBER/SERIAL_NUMBER (a continuation line for the
previous named component) — this is left blank rather than
back-filled/copied from the prior row, since copying would fabricate a
value the source PDF doesn't actually repeat there.

ATA-chapter assignment: the ATA cell is a single grid cell vertically
centered across however many physical lines its own component group
spans, so its own y-position in the text stream can land ABOVE, BELOW,
or in between those lines' own text (confirmed directly, e.g. the sample
page 1 "EMERGENCY LOCATOR TRANSMITTER" line has no ATA of its own; the
literal "25" appears on the NEXT line down instead, i.e. after — not
before — the row it belongs to). Because of this, a simple forward-fill
(this project's usual `shared.cleanup.forward_fill_ata`, e.g. as used by
`occm.py`) is a real risk here: it can leave a record silently attributed
to the PREVIOUS chapter every time this happens (`sheet_types/ht.py`'s
own `normalize_and_validate()` does not call `forward_fill_ata` at all
either — see `hard_time_day_fhr_cyc_matrix_scanned.py`'s own docstring
for that same, separate, precedent). This module instead collects every
line that DOES carry its own ATA value (whether alone on its own line or
leading a full record line) as an "anchor", and assigns every other
record the NEAREST anchor by line-count distance in EITHER direction —
confirmed directly this resolves the ELT case above correctly (the "25"
anchor one line below is closer than the "24" anchor several lines
above). A record exactly equidistant between two differing anchors
still resolves to *a* value (ties favour the earlier/above anchor) —
this is a real, confirmed limitation on ATA specifically (not on any
core identity field): a small number of ATA values may be one chapter
off on a tied boundary row. No other field is affected.

Page footer: every page ends with a bare "Page N of M" line, which is
explicitly skipped (checked directly — without this, `page.extract_text()`
puts it in-stream just like any other line, and it would otherwise read
as a phantom record with a stray value in the DATE_SINCE_OH bin, since
its own x0 happens to land in that bin's range).
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.ht_variants._base import merged_rules

NAME = "Hard Time Component Status (Two-Tier ATA Header)"
SIGNATURES = [
    "ATA LAST DATE INSTALLED DATE LAST TIME TIME SINCE INSTALL ALOW TIME INTERVAL REMAIN FOR OH",
]

_COLUMN_ORDER = [
    "ATA",
    "DESCRIPTION",
    "POSN",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "LAST_DATE_INSTALLED",
    "LAST_TIME_HRS",
    "LAST_TIME_CYC",
    "DATE_SINCE_OH",
    "TIME_SINCE_INSTALL_HRS",
    "TIME_SINCE_INSTALL_CYC",
    "TIME_SINCE_INSTALL_DAYS",
    "ALOW_TIME_HRS",
    "ALOW_TIME_CYC",
    "ALOW_TIME_DAYS",
    "INTERVAL_HRS",
    "INTERVAL_CYC",
    "INTERVAL_DAYS",
    "DUE_DATE",
    "REMARKS",
]
_HEADER_FIELDS = [
    "MODEL", "LINE_NO", "VRV_NO", "TOTAL_HOURS", "TOTAL_CYCLES", "REPORT_DATE",
]
CANONICAL_COLUMNS = _COLUMN_ORDER + _HEADER_FIELDS

# Column x0 bin boundaries — derived from a histogram of every data-row
# word's own x0 across all 6 pages of the sample file (see module
# docstring). `(lo, hi)` is a half-open interval `[lo, hi)`.
_BOUNDS: list[tuple[str, float, float]] = [
    ("ATA", 0, 40),
    ("DESCRIPTION", 40, 155),
    ("POSN", 155, 198),
    ("PART_NUMBER", 198, 237),
    ("SERIAL_NUMBER", 237, 288),
    ("LAST_DATE_INSTALLED", 288, 324),
    ("LAST_TIME_HRS", 324, 353),
    ("LAST_TIME_CYC", 353, 376),
    ("DATE_SINCE_OH", 376, 444),
    ("TIME_SINCE_INSTALL_HRS", 444, 463),
    ("TIME_SINCE_INSTALL_CYC", 463, 486),
    ("TIME_SINCE_INSTALL_DAYS", 486, 508),
    ("ALOW_TIME_HRS", 508, 528),
    ("ALOW_TIME_CYC", 528, 548),
    ("ALOW_TIME_DAYS", 548, 569),
    ("INTERVAL_HRS", 569, 591),
    ("INTERVAL_CYC", 591, 612),
    ("INTERVAL_DAYS", 612, 639),
    ("DUE_DATE", 639, 669),
    ("REMARKS", 669, float("inf")),
]

_DATE_DOT_RE = r"^\d{1,2}\.\d{1,2}\.\d{2,4}$"
_DATE_DASH_RE = r"^\d{1,2}-[A-Za-z]{3}-\d{2,4}$"
_NUM_RE = r"^-?\d+$"

_OVERRIDES = {
    "ATA": {"allow_empty": True},
    "DESCRIPTION": {"allow_empty": True},
    "POSN": {"allow_empty": True, "uppercase": True},
    "PART_NUMBER": {"allow_empty": True},
    "SERIAL_NUMBER": {"allow_empty": True},
    "LAST_DATE_INSTALLED": {"pattern": _DATE_DOT_RE, "allow_empty": True},
    "LAST_TIME_HRS": {"pattern": _NUM_RE, "allow_empty": True},
    "LAST_TIME_CYC": {"pattern": _NUM_RE, "allow_empty": True},
    "DATE_SINCE_OH": {"pattern": _DATE_DOT_RE, "allow_empty": True},
    "TIME_SINCE_INSTALL_HRS": {"pattern": _NUM_RE, "allow_empty": True},
    "TIME_SINCE_INSTALL_CYC": {"pattern": _NUM_RE, "allow_empty": True},
    "TIME_SINCE_INSTALL_DAYS": {"pattern": _NUM_RE, "allow_empty": True},
    "ALOW_TIME_HRS": {"pattern": _NUM_RE, "allow_empty": True},
    "ALOW_TIME_CYC": {"pattern": _NUM_RE, "allow_empty": True},
    "ALOW_TIME_DAYS": {"pattern": _NUM_RE, "allow_empty": True},
    "INTERVAL_HRS": {"pattern": _NUM_RE, "allow_empty": True},
    "INTERVAL_CYC": {"pattern": _NUM_RE, "allow_empty": True},
    "INTERVAL_DAYS": {"pattern": _NUM_RE, "allow_empty": True},
    "DUE_DATE": {"pattern": _DATE_DASH_RE, "allow_empty": True},
    "REMARKS": {"allow_empty": True},
    # Header metadata — a single misread here shouldn't flag every row of
    # the file, same reasoning this package's other header-plus-body
    # variants use.
    "MODEL": {"allow_empty": True},
    "LINE_NO": {"allow_empty": True},
    "VRV_NO": {"allow_empty": True},
    "TOTAL_HOURS": {"pattern": _NUM_RE, "allow_empty": True},
    "TOTAL_CYCLES": {"pattern": _NUM_RE, "allow_empty": True},
    "REPORT_DATE": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_ATA_TOKEN_RE = re.compile(r"^\d{1,3}$")
_FOOTER_RE = re.compile(r"^Page\s+\d+\s+of\s+\d+$", re.IGNORECASE)
_Y_TOL = 3.0

_MODEL_RE = re.compile(r"MODEL:\s*(.+?)\s*MFG\s*DATE:", re.IGNORECASE)
_MFG_DATE_RE = re.compile(r"MFG\s*DATE:\s*(\S+)", re.IGNORECASE)
_LINE_NO_RE = re.compile(r"LINE\s*(?:№|No\.?)\s*(\S+)", re.IGNORECASE)
_VRV_NO_RE = re.compile(r"VRV\s*(?:№|No\.?):?\s*(\S+)", re.IGNORECASE)
_TOTAL_HOURS_RE = re.compile(r"TOTAL\s+HOURS:\s*(\S+)", re.IGNORECASE)
_TOTAL_CYCLES_RE = re.compile(r"TOTAL\s+CYCLES:\s*(\S+)", re.IGNORECASE)
_REPORT_DATE_RE = re.compile(r"TOTAL\s+CYCLES:\s*\S+\s*DATE:\s*(\S+)", re.IGNORECASE)


def _bucket(x0: float) -> str:
    for name, lo, hi in _BOUNDS:
        if lo <= x0 < hi:
            return name
    return "REMARKS"


def _group_lines(words: list[dict], y_tol: float = _Y_TOL) -> list[list[dict]]:
    lines: list[list[dict]] = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        placed = False
        for ln in lines:
            if abs(ln[0]["top"] - w["top"]) <= y_tol:
                ln.append(w)
                placed = True
                break
        if not placed:
            lines.append([w])
    lines.sort(key=lambda ln: min(w["top"] for w in ln))
    return lines


def _parse_header_meta(head_text: str) -> dict:
    meta = {k: "" for k in _HEADER_FIELDS}
    m = _MODEL_RE.search(head_text)
    if m:
        meta["MODEL"] = m.group(1).strip()
    m = _LINE_NO_RE.search(head_text)
    if m:
        meta["LINE_NO"] = m.group(1).strip()
    m = _VRV_NO_RE.search(head_text)
    if m:
        meta["VRV_NO"] = m.group(1).strip()
    m = _TOTAL_HOURS_RE.search(head_text)
    if m:
        meta["TOTAL_HOURS"] = m.group(1).strip()
    m = _TOTAL_CYCLES_RE.search(head_text)
    if m:
        meta["TOTAL_CYCLES"] = m.group(1).strip()
    m = _REPORT_DATE_RE.search(head_text)
    if m:
        meta["REPORT_DATE"] = m.group(1).strip()
    return meta


def _parse_page(words: list[dict], page_num: int) -> list[dict]:
    lines = _group_lines(words)

    # Header ends at the 3rd (bottom) tier of the column header, the only
    # line to carry the literal word "chapter" (this template's own tier-3
    # label for the ATA column — see module docstring). Data starts right
    # after it. Falls back to keeping every line if that marker isn't
    # found (defensive; not expected on this template).
    header_end = None
    for i, ln in enumerate(lines):
        if any(w["text"] == "chapter" for w in ln):
            header_end = i
            break
    data_lines = lines[header_end + 1:] if header_end is not None else lines

    rows: list[dict[str, str]] = []
    for ln in data_lines:
        full_text = " ".join(w["text"] for w in sorted(ln, key=lambda w: w["x0"]))
        if _FOOTER_RE.match(full_text.strip()):
            continue
        buckets: dict[str, list[str]] = {c: [] for c in _COLUMN_ORDER}
        for w in sorted(ln, key=lambda w: w["x0"]):
            buckets[_bucket(w["x0"])].append(w["text"])
        row = {c: " ".join(v).strip() for c, v in buckets.items()}
        rows.append(row)

    # ATA anchor resolution (see module docstring for why nearest-by-
    # line-distance is used instead of a plain forward-fill).
    anchors = [(i, r["ATA"]) for i, r in enumerate(rows)
               if r["ATA"] and _ATA_TOKEN_RE.match(r["ATA"])]

    def _nearest_ata(i: int) -> str:
        if not anchors:
            return ""
        return min(anchors, key=lambda a: abs(a[0] - i))[1]

    records: list[dict] = []
    for i, row in enumerate(rows):
        own_ata = row["ATA"]
        has_other = any(row[c] for c in _COLUMN_ORDER if c != "ATA")
        if not has_other:
            continue  # bare ATA-only line, or fully blank line
        rec = dict(row)
        if not own_ata:
            rec["ATA"] = _nearest_ata(i)
        rec["_page"] = page_num
        records.append(rec)
    return records


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    header_meta = {k: "" for k in _HEADER_FIELDS}
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            if not all(header_meta.values()):
                head_text = page.extract_text() or ""
                page_meta = _parse_header_meta(head_text)
                for k, v in page_meta.items():
                    if v and not header_meta[k]:
                        header_meta[k] = v
            page_records = _parse_page(page.extract_words(), page_num)
            for rec in page_records:
                rec.update(header_meta)
            records.extend(page_records)
    return records
