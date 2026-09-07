"""Assembly Configuration / Status Report -- born-digital OCCM export, real
text layer confirmed via a direct pdfplumber pass on the real sample (no OCR
needed; extract() is synchronous).

Header block (repeats verbatim at the top of every page, parsed once from
page 1 and stamped on every row -- some later pages in the sample show a
truncated/garbled header line, e.g. a missing FHRS/CYCS pair, so re-parsing
per page would silently blank out otherwise-good metadata)::

    DATE: <date> <operator name> RPT CODE: <code>
    TIME: <time> ASSEMBLY CONFIGURATION / STATUS REPORT PAGE NO.: <n>
    TAIL NO.: <tail>
    A/C Type: <type> Manufacturer's Name: <mfr> Registration Number: <reg> Manufacturer's Serial Number: <msn>
    Current A/C Times > FHRS: <n> CYCS: <n> Date: <date> Dates > Manufacture: <date> Aquisition: <date>
    Report Based On The Following Utilization Rates >> Flight Hours / Day: <n> Flight Cycles / Day: <n> (Forecast)

Data-row geometry -- this is the genuinely unusual part. The column header
prints as two stacked lines::

    RCN / <alt-code> # / DESC  CON  INSTALLATION DATA  SAFE LIFE CONTROLS  OVERHAUL CONTROLS  SHOP VISIT CONTROLS  DUE DATA FOR
    # SERIAL NO. / POSITION  TRL  A/C DATA  TSI  LIMIT  TSN  RMNG  LIMIT  TSO  RMNG  LIMIT  TSV  RMNG  FIRST  DUE

but a single component's real data is NOT one row -- it is exactly FOUR
physical printed lines, confirmed directly via `extract_words()` x0
positions across the whole sample (895 components observed, 100% of them
this exact 4-line shape, zero exceptions)::

    <rcn> <part_number>   FHR  <...12 status/value tokens for the FHR basis...>
    <alt_part_number>     CYC  <...same, for the CYC basis...>
    <description...>      CAL  <...same, for the CAL basis...>
    <serial> POS: <pos> GRN No.> <grn> [extra trailing status tokens]

The leftmost cell (`CON`) is a hard, unmoving x0 anchor (139.0pt in the
sample, confirmed on every single data row) holding one of three literal
tokens -- FHR (flight-hours basis), CYC (flight-cycles basis), CAL
(calendar/date basis) -- and tells you which basis's numeric trail that one
physical line is populating; the header's own "CON"/"TRL" cell is simply a
two-line label sitting at that same anchor. Identifying the CON token by
x0-proximity to that anchor (not by string search across the row) matters:
those same literal strings "FHR"/"CYC" also legitimately appear much further
right, as the value of the DUE-DATA-FOR sub-column on some rows (e.g. a row
whose SAFE LIFE control is the binding limit prints "... 18,536 FHR" at the
end of its CYC-basis line) -- a plain substring/token-membership check over
the whole row would misfire on those.

The fourth line has no CON token at all -- it is a trailing continuation
that was NOT anticipated by the column-header's first row (whose 3-part
label only names RCN/<alt-code>#/DESC), but IS explicitly named by the
header's own second row ("# SERIAL NO. / POSITION"), and matches this
project's convention of trusting the source's own labels over a guessed
reading. It carries the component's real SERIAL_NUMBER, POSITION and an
internal cross-reference number (labelled "GRN No.>" in the source, kept
verbatim as GRN_NUMBER -- meaning not confirmed, not guessed at). A small
number of these lines (5 out of 895 in the sample) either omit the literal
"POS:" label entirely (position value simply follows the serial with
nothing marking it) or have "POS:" glued directly onto the previous token
with zero gap at the PDF text-stream level (confirmed directly via
`extract_words()`: one single word object, e.g. serial + "POS:" fused, no
space). The former is left with POSITION blank rather than guessed at; the
latter is fixed with a narrow regex that only inserts a space immediately
before a "POS:" that has a non-space character touching it, before token
splitting -- not a general reflow of the line.

Soft-validation / STATUS_TRAIL, and the 3-rows-vs-1-row modeling decision:
The 12-13 raw tokens following each basis's CON token do NOT reliably
decompose into the header's own 14 named sub-columns (TRL/A/C DATA/TSI/
LIMIT/TSN/RMNG/LIMIT/TSO/RMNG/LIMIT/TSV/RMNG/FIRST/DUE) -- confirmed
directly: some are a single wide date, some are a single "NO LIMITS" phrase,
some are a duration value that itself splits across two whitespace tokens
("1Y 4M28D"), and the trailing FIRST/DUE pair sometimes holds a real date
on the FHR line, sometimes the literal basis code ("FHR") on the CYC line,
sometimes a "FOR: <code>" status phrase on the CAL line -- there is no
single fixed token-count-to-column mapping that holds across the sample.
Rather than force an unreliable per-subcolumn split (this project's "never
guess a wrong split" convention -- see e.g. multi_basis_accumulated_occm.py
in this same package), the entire raw trailing region for a given basis
line is kept verbatim in one STATUS_TRAIL column.

That, in turn, is why this variant models each component as THREE rows
(one per BASIS: FHR/CYC/CAL) rather than one row with three parallel sets of
numeric columns: since the numeric trail per basis is being kept as one
opaque legible string rather than decomposed, three parallel STATUS_TRAIL_
FHR/STATUS_TRAIL_CYC/STATUS_TRAIL_CAL columns on one row would just be the
same data under a wider, harder-to-scan shape. Three rows sharing every
identifying field (RCN, PART_NUMBER, PART_NUMBER_ALT, DESCRIPTION,
SERIAL_NUMBER, POSITION, GRN_NUMBER) plus a BASIS column keeps each basis's
own trail on its own line, closest to how the source itself prints it.

Two distinct "part number"-shaped fields, not one:
The header's first line names both "RCN" and an alternate per-operator part
code (rendered as "<alt-code> #" in the header -- the sample's own header
literally names this after the specific airline that generated the file,
which is a real-world detail this project's variant code and docs must
never repeat verbatim; here it is written generically) directly above
"DESC". The FHR-basis physical line holds an RCN integer plus one PN-shaped
code (e.g. format like <chapter>-<section>-<suffix>); the CYC-basis line's
own value is a *different* code, usually itself PN-shaped (e.g.
<mfr-code>-<suffix>) but occasionally serial-shaped instead (confirmed only
on the sample's very first, airframe-level pseudo-component). Since the
sample doesn't confirm which one of the two is "the" manufacturer part
number in the strict sense, both are kept, under distinct names
(PART_NUMBER for the FHR-line code, PART_NUMBER_ALT for the CYC-line code)
rather than asserting a single shared PART_NUMBER is definitely right and
silently dropping the other.

No OCR is used: a direct pdfplumber pass over the sample confirmed a full,
clean text layer on every page (extract() is synchronous).
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "Assembly Configuration / Status Report"
SIGNATURES = [
    "ASSEMBLY CONFIGURATION / STATUS REPORT",
    "SERIAL NO. / POSITION",
]

CANONICAL_COLUMNS = [
    "RCN",
    "PART_NUMBER",
    "PART_NUMBER_ALT",
    "DESCRIPTION",
    "BASIS",
    "STATUS_TRAIL",
    "SERIAL_NUMBER",
    "POSITION",
    "GRN_NUMBER",
    "NOTES",
    # Header metadata -- same on every row of a given file.
    "REPORT_DATE",
    "RPT_CODE",
    "TAIL_NO",
    "AC_TYPE",
    "MANUFACTURER_NAME",
    "AIRCRAFT_REG",
    "AIRCRAFT_MSN",
    "CURRENT_FHRS",
    "CURRENT_CYCS",
    "MANUFACTURE_DATE",
    "ACQUISITION_DATE",
    "UTILIZATION_HOURS_PER_DAY",
    "UTILIZATION_CYCLES_PER_DAY",
]

_OVERRIDES = {
    "RCN":              {"pattern": r"^\d{1,3}$", "allow_empty": True},
    "PART_NUMBER_ALT":  {"pattern": r"^[A-Z0-9](?:[A-Z0-9\-/]*[A-Z0-9])?$", "uppercase": True, "allow_empty": True},
    "BASIS":            {"pattern": r"^(FHR|CYC|CAL)$", "uppercase": True},
    "STATUS_TRAIL":     {"allow_empty": True},
    "POSITION":         {"pattern": r"^[A-Z0-9\-]{1,10}$", "uppercase": True, "allow_empty": True},
    "GRN_NUMBER":       {"pattern": r"^\d+$", "allow_empty": True},
    "NOTES":            {"allow_empty": True},
    "REPORT_DATE":            {"pattern": r"^\d{2}/\d{2}/\d{4}$", "allow_empty": True},
    "RPT_CODE":               {"pattern": r"^[A-Z0-9.]{1,10}$", "uppercase": True, "allow_empty": True},
    "TAIL_NO":                {"pattern": r"^[A-Z0-9\-]{1,10}$", "uppercase": True, "allow_empty": True},
    "AC_TYPE":                {"pattern": r"^[A-Z0-9\-]{1,10}$", "uppercase": True, "allow_empty": True},
    "MANUFACTURER_NAME":      {"uppercase": True, "allow_empty": True},
    "AIRCRAFT_REG":           {"pattern": r"^[A-Z0-9\-]{1,10}$", "uppercase": True, "allow_empty": True},
    "AIRCRAFT_MSN":           {"pattern": r"^[A-Z0-9]{1,10}$", "uppercase": True, "allow_empty": True},
    "CURRENT_FHRS":           {"pattern": r"^[\d,]+:\d{2}$", "allow_empty": True},
    "CURRENT_CYCS":           {"pattern": r"^[\d,]+\.\d{2}$", "allow_empty": True},
    "MANUFACTURE_DATE":       {"pattern": r"^\d{2}/\d{2}/\d{4}$", "allow_empty": True},
    "ACQUISITION_DATE":       {"pattern": r"^\d{2}/\d{2}/\d{4}$", "allow_empty": True},
    "UTILIZATION_HOURS_PER_DAY":  {"pattern": r"^\d+(\.\d+)?$", "allow_empty": True},
    "UTILIZATION_CYCLES_PER_DAY": {"pattern": r"^\d+(\.\d+)?$", "allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# --- Row/column geometry ------------------------------------------------
# The CON token's x0 is a hard, unmoving anchor confirmed on every data row
# in the sample (139.0pt); a small tolerance absorbs sub-pixel jitter. This
# is deliberately an x-position check, not a text search over the whole
# row -- the literal strings "FHR"/"CYC" also legitimately appear far to the
# right as a DUE-DATA-FOR status value on some rows (see module docstring).
_CON_ANCHOR = 139.0
_CON_TOLERANCE = 3.0
_CON_TOKENS = {"FHR", "CYC", "CAL"}

_HEADER_OR_META_MARKERS = (
    "DATE:", "TIME:", "TAIL NO.:", "A/C Type:", "Current A/C Times",
    "Report Based On", "RCN /", "# SERIAL", "END OF REPORT",
)

_POS_RE = re.compile(r"POS:\s*(\S+)")
_GRN_RE = re.compile(r"GRN No\.>\s*(\S+)")
# Narrow fix for the rare case where the PDF's own text stream has zero gap
# between a serial number and the following "POS:" label (confirmed via
# extract_words(): the two are literally one merged word object on 5 of the
# sample's 895 trailing lines) -- insert a space only in that exact spot,
# not a general reflow of the line.
_GLUED_POS_RE = re.compile(r"(?<=\S)POS:")

_META_RE_TYPE = re.compile(
    r"A/C Type:\s*(\S+).*?Name:\s*(\S+).*?Registration Number:\s*(\S+).*?Serial Number:\s*(\S+)"
)
_META_RE_TAIL = re.compile(r"TAIL NO\.:\s*(\S+)")
_META_RE_DATE_RPT = re.compile(r"DATE:\s*(\S+).*?RPT CODE:\s*(\S+)")
_META_RE_TIMES = re.compile(
    r"FHRS:\s*(\S+)\s+CYCS:\s*(\S+).*?Manufacture:\s*(\S+)\s+Aquisition:\s*(\S+)"
)
_META_RE_UTIL = re.compile(
    r"Flight Hours\s*/\s*Day:\s*(\S+)\s+Flight Cycles\s*/\s*Day:\s*(\S+)"
)


def _parse_meta(text: str) -> dict:
    meta: dict[str, str] = {}
    m = _META_RE_DATE_RPT.search(text)
    if m:
        meta["REPORT_DATE"] = m.group(1)
        meta["RPT_CODE"] = m.group(2)
    m = _META_RE_TAIL.search(text)
    if m:
        meta["TAIL_NO"] = m.group(1)
    m = _META_RE_TYPE.search(text)
    if m:
        meta["AC_TYPE"] = m.group(1)
        meta["MANUFACTURER_NAME"] = m.group(2)
        meta["AIRCRAFT_REG"] = m.group(3)
        meta["AIRCRAFT_MSN"] = m.group(4)
    m = _META_RE_TIMES.search(text)
    if m:
        meta["CURRENT_FHRS"] = m.group(1)
        meta["CURRENT_CYCS"] = m.group(2)
        meta["MANUFACTURE_DATE"] = m.group(3)
        meta["ACQUISITION_DATE"] = m.group(4)
    m = _META_RE_UTIL.search(text)
    if m:
        meta["UTILIZATION_HOURS_PER_DAY"] = m.group(1)
        meta["UTILIZATION_CYCLES_PER_DAY"] = m.group(2)
    return meta


def _cluster_rows(words: list[dict]) -> list[list[dict]]:
    """Group words into visual rows by their `top` coordinate. Row pitch in
    the sample is a consistent ~7.2pt; a 2pt tolerance clusters words on the
    same printed line without merging adjacent lines."""
    if not words:
        return []
    tops = sorted(set(round(w["top"], 1) for w in words))
    clusters: list[list[float]] = []
    cur = [tops[0]]
    for t in tops[1:]:
        if t - cur[-1] <= 2.0:
            cur.append(t)
        else:
            clusters.append(cur)
            cur = [t]
    clusters.append(cur)

    row_groups = []
    for cl in clusters:
        lo, hi = min(cl) - 0.5, max(cl) + 0.5
        row_words = [w for w in words if lo <= w["top"] <= hi]
        if row_words:
            row_groups.append(row_words)
    return row_groups


def _find_con_word(row_words: list[dict]) -> dict | None:
    for w in row_words:
        if w["text"] in _CON_TOKENS and abs(w["x0"] - _CON_ANCHOR) <= _CON_TOLERANCE:
            return w
    return None


def _new_pending(page_num: int) -> dict:
    return {
        "RCN": "", "PART_NUMBER": "", "PART_NUMBER_ALT": "", "DESCRIPTION": "",
        "_trails": {}, "_page": page_num,
    }


def _finish_component(pending: dict) -> list[dict]:
    """Parse the trailing serial/position/GRN line's info (already stashed
    onto `pending` by the caller) and expand into one row per basis."""
    rows = []
    for basis in ("FHR", "CYC", "CAL"):
        rec = {c: "" for c in CANONICAL_COLUMNS}
        rec["RCN"] = pending["RCN"]
        rec["PART_NUMBER"] = pending["PART_NUMBER"]
        rec["PART_NUMBER_ALT"] = pending["PART_NUMBER_ALT"]
        rec["DESCRIPTION"] = pending["DESCRIPTION"]
        rec["BASIS"] = basis
        rec["STATUS_TRAIL"] = pending["_trails"].get(basis, "")
        rec["SERIAL_NUMBER"] = pending.get("SERIAL_NUMBER", "")
        rec["POSITION"] = pending.get("POSITION", "")
        rec["GRN_NUMBER"] = pending.get("GRN_NUMBER", "")
        rec["NOTES"] = pending.get("NOTES", "")
        # Header metadata, stamped by the caller onto `pending` before this
        # runs -- copy across anything matching a canonical column name.
        for col in CANONICAL_COLUMNS:
            if col in pending and rec.get(col, "") == "":
                rec[col] = pending[col]
        rec["_page"] = pending["_page"]
        rows.append(rec)
    return rows


def _parse_trailer(pending: dict, joined: str) -> None:
    """Parse the 4th (non-CON) physical line of a component: SERIAL_NUMBER,
    POSITION, GRN_NUMBER, with anything left over kept verbatim in NOTES
    rather than guessed at."""
    fixed = _GLUED_POS_RE.sub(" POS:", joined)
    toks = fixed.split()
    serial = toks[0] if toks else ""
    m_pos = _POS_RE.search(fixed)
    m_grn = _GRN_RE.search(fixed)
    pending["SERIAL_NUMBER"] = serial
    pending["POSITION"] = m_pos.group(1) if m_pos else ""
    pending["GRN_NUMBER"] = m_grn.group(1) if m_grn else ""

    remainder = fixed
    if m_pos:
        remainder = remainder.replace(m_pos.group(0), "", 1)
    if m_grn:
        remainder = remainder.replace(m_grn.group(0), "", 1)
    if toks:
        remainder = remainder.replace(serial, "", 1)
    pending["NOTES"] = " ".join(remainder.split())


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    meta: dict[str, str] = {}
    pending: dict | None = None

    with pdfplumber.open(pdf_path) as pdf:
        if pdf.pages:
            meta = _parse_meta(pdf.pages[0].extract_text() or "")

        for page_num, page in enumerate(pdf.pages, start=1):
            words = page.extract_words()
            if not words:
                continue
            for row_words in _cluster_rows(words):
                row_words = sorted(row_words, key=lambda w: w["x0"])
                joined = " ".join(w["text"] for w in row_words)
                if not joined.strip():
                    continue
                if any(marker in joined for marker in _HEADER_OR_META_MARKERS):
                    continue

                con_word = _find_con_word(row_words)
                if con_word is not None:
                    left = [w["text"] for w in row_words if w["x0"] < con_word["x0"]]
                    trail = [w["text"] for w in row_words if w["x0"] > con_word["x0"]]
                    basis = con_word["text"]
                    if pending is None:
                        pending = _new_pending(page_num)
                    if basis == "FHR":
                        pending["RCN"] = left[0] if left else ""
                        pending["PART_NUMBER"] = " ".join(left[1:])
                    elif basis == "CYC":
                        pending["PART_NUMBER_ALT"] = " ".join(left)
                    elif basis == "CAL":
                        pending["DESCRIPTION"] = " ".join(left)
                    pending["_trails"][basis] = " ".join(trail)
                    continue

                # Not a CON line: the trailing serial/position/GRN line for
                # the component just accumulated, but only once all three
                # basis lines have actually been seen (guards against a
                # stray/unexpected line being misread as the trailer).
                if pending is not None and set(pending["_trails"]) >= _CON_TOKENS:
                    _parse_trailer(pending, joined)
                    for k, v in meta.items():
                        pending[k] = v
                    records.extend(_finish_component(pending))
                    pending = None
                # else: unrecognized stray line -- skip rather than guess.

    # A component with no trailing line (should not happen per the sample,
    # but guards against a truncated final page) still gets its 3 basis
    # rows emitted rather than silently dropped.
    if pending is not None and set(pending["_trails"]) >= _CON_TOKENS:
        for k, v in meta.items():
            pending[k] = v
        records.extend(_finish_component(pending))

    return records
