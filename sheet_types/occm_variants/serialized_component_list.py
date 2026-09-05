"""Serialized Component List OCCM — Airbus header block, real text layer.

Confirmed on a real-corpus sample file via a direct pdfplumber pass over
every page (a *rendered-word* pass, not just the flattened text -- see the
row-parsing note below). Has a genuine text layer throughout; this module
is synchronous, pdfplumber-only, no OCR.

Header block (6 lines, repeated verbatim on every page)::

    AIRCRAFT
    AIRBUS <type> HOURS <n>
    Serialized Component List
    MSN <msn> CYCLES <n>
    REG <reg> DATE <date>
    DOM <date>

parsed once from page 1 and stamped on every row, same convention this
project's other header-plus-body OCCM variants use. <type> is the bare
Airbus model designator (e.g. a family/variant string shaped like
`A3nn-2nn`); DOM is the aircraft's date of manufacture, distinct from the
report DATE.

Column-header line (repeated on every page, immediately above the body)::

    L/I ATA Material Description P/N S/N Install Date TSN CSN FIN NOTE

L/I (a running line-item counter, 1..N across the whole document, not
per-page) is parsed only as a row anchor and is not carried into the
output -- it has no analytical value once the real columns are captured.

Row parsing deliberately does NOT use whitespace/`.split()` tokenizing.
Confirmed real edge cases break that approach:
  - DESCRIPTION is a variable number of words, occasionally including an
    embedded comma (e.g. a fragment like `<part name>, <qualifier>`).
  - Several middle columns (P/N, S/N, Install Date, TSN, CSN) are blank
    together on some rows -- e.g. a component the file marks not-yet-
    tracked/pending shows only ATA, DESCRIPTION, FIN and a literal `TBD` in
    NOTE with every other cell empty; other rows are blank in the middle
    (Install Date present, TSN/CSN blank) while FIN/NOTE further right are
    still populated. A fixed-count positional split would silently shift
    every later field on these rows.
  - NOTE is free text, sometimes two words (e.g. an internal cross-
    reference note naming the donor aircraft's own MSN, or a maintenance-
    organisation-approval code together with a second word).
  - FIN (the installed-position code) is not always a plain alnum token --
    real values include an embedded `/` (side-of-aircraft prefix), a `.`
    (e.g. a `NO.<n>` suffix), a space (two-token position labels), and a
    leading `#` (e.g. an engine-station prefix).

Instead each page is read with `extract_words()` (word-level boxes), words
are clustered into visual rows by `top` position, and each word is
assigned to its column purely by which column's x-range its center falls
in -- confirmed against the real header's own word positions and checked
row-by-row against the real sample file, including every sparse-row case
above. A blank cell simply contributes no word to its column and comes out
as "" -- never guessed, never shifted into a neighbour -- the same "never
guess a wrong split" principle this project's other variants apply to
ambiguous free text, enforced geometrically here instead.

A row is accepted only when its L/I-column word is a bare digit sequence
AND its ATA-column word is a bare 2-digit number; this is what lets the
repeated header line, blank-page noise, and a signature/approval block on
the real sample's final page (free-text lines with no digit L/I at all)
fall out for free without special-casing them.

Known limitation, confirmed directly against the real sample file: a
handful of rows have every optional field but FIN and NOTE blank (no P/N,
S/N, Install Date, TSN or CSN at all) -- these are recovered as rows with
those fields empty rather than dropped, consistent with the "blank cell,
not a guess" principle above.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "Serialized Component List"
SIGNATURES = [
    "Serialized Component List",
    "L/I ATA Material Description P/N S/N Install Date TSN CSN FIN NOTE",
]

CANONICAL_COLUMNS = [
    "ATA",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "INSTALL_DATE",
    "TSN",
    "CSN",
    "FIN",
    "NOTE",
    # Header metadata, parsed once per file and stamped on every row.
    "AIRCRAFT_TYPE",
    "AIRCRAFT_MSN",
    "AIRCRAFT_HOURS",
    "AIRCRAFT_REG",
    "AIRCRAFT_CYCLES",
    "REPORT_DATE",
    "DOM",
]

# Time/cycle cells use thousands-comma integers; both are blank together on
# rows whose Install Date is also blank (see module docstring).
_NUM_RULE = {"pattern": r"^\d{1,3}(?:,\d{3})*$", "allow_empty": True}
_DATE_RULE = {"pattern": r"^\d{4}-\d{2}-\d{2}$", "allow_empty": True}

_OVERRIDES = {
    # PART_NUMBER/SERIAL_NUMBER use the global patterns but are blank on
    # some real rows (see module docstring) -- allow_empty added.
    "PART_NUMBER": {"allow_empty": True},
    "SERIAL_NUMBER": {"allow_empty": True},
    "INSTALL_DATE": _DATE_RULE,
    "TSN": _NUM_RULE,
    "CSN": _NUM_RULE,
    # FIN on this format carries more punctuation than the global 2-8-char
    # alnum rule allows -- confirmed real values include an embedded "/"
    # (side-of-aircraft prefix), "." (a "NO.<n>" suffix), a space (two-token
    # position labels) and a leading "#" (engine-station prefix). char_map/
    # sequence_map are explicitly disabled here (overriding the global FIN
    # rule's OCR-oriented defaults): this is a real text layer, not OCR
    # output, and real values here legitimately contain letters the global
    # OCR_CHAR_MAP would silently rewrite (e.g. "O"->"0" would corrupt a
    # genuine "NO1LH"-style position code into "N01LH").
    "FIN": {
        "pattern": r"^[A-Z0-9#][A-Z0-9./#\- ]{0,14}$",
        "uppercase": True,
        "no_spaces": False,
        "char_map": {},
        "sequence_map": [],
        "allow_empty": True,
    },
    # NOTE is free text: a certifying-authority code, a cross-reference to
    # a donor aircraft's own MSN, a placeholder like "TBD", or a two-word
    # combination of these -- no fixed vocabulary, so only loosely shaped.
    # char_map/sequence_map disabled for the same real-text-layer reason as
    # FIN above (e.g. a real authority code containing "O"/"I"/"L" would
    # otherwise be silently rewritten by the OCR-oriented global map).
    "NOTE": {
        "pattern": r"^[A-Z0-9_./#\- ]+$",
        "uppercase": True,
        "char_map": {},
        "sequence_map": [],
        "allow_empty": True,
    },
    "AIRCRAFT_TYPE": {"allow_empty": True},
    "AIRCRAFT_MSN": {"allow_empty": True},
    "AIRCRAFT_HOURS": {"pattern": r"^\d{1,3}(?:,\d{3})*$", "allow_empty": True},
    "AIRCRAFT_REG": {"uppercase": True, "allow_empty": True},
    "AIRCRAFT_CYCLES": {"pattern": r"^\d{1,3}(?:,\d{3})*$", "allow_empty": True},
    "REPORT_DATE": {"allow_empty": True},
    "DOM": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Column boundaries as (x0_inclusive, x1_exclusive, name), derived from the
# real header's own word x-positions (midpoints between adjacent column
# starts) and confirmed row-by-row against the real sample file, including
# every sparse-row case in the module docstring. "LI" is parsed only to
# anchor rows -- ATA is the second anchor -- and is not carried into output.
_COLUMNS = [
    (-1e9, 60.0, "LI"),
    (60.0, 92.0, "ATA"),
    (92.0, 297.0, "DESCRIPTION"),
    (297.0, 388.0, "PART_NUMBER"),
    (388.0, 483.0, "SERIAL_NUMBER"),
    (483.0, 558.0, "INSTALL_DATE"),
    (558.0, 615.0, "TSN"),
    (615.0, 682.0, "CSN"),
    (682.0, 745.0, "FIN"),
    (745.0, 1e9, "NOTE"),
]
# Header/body split: the real header block (title + aircraft metadata + the
# column-header line itself) ends well above this -- confirmed directly
# against the real sample file's header word positions -- so restricting to
# words below it also drops the header's own repeated text on every page.
_BODY_TOP_MIN = 118.0
_ROW_CLUSTER_TOL = 3.5

_ATA_RE = re.compile(r"^\d{2}$")
_LI_RE = re.compile(r"^\d+$")

_TYPE_RE = re.compile(r"AIRBUS\s+(\S+)\s+HOURS\s+([\d,]+)")
_MSN_RE = re.compile(r"MSN\s+(\S+)\s+CYCLES\s+([\d,]+)")
_REG_RE = re.compile(r"REG\s+(\S+)\s+DATE\s+(\S+)")
_DOM_RE = re.compile(r"\bDOM\s+(\S+)")


def _col_for_x(x: float) -> str | None:
    for lo, hi, name in _COLUMNS:
        if lo <= x < hi:
            return name
    return None


def _parse_header_meta(first_page_text: str) -> dict:
    meta = {
        "AIRCRAFT_TYPE": "", "AIRCRAFT_HOURS": "",
        "AIRCRAFT_MSN": "", "AIRCRAFT_CYCLES": "",
        "AIRCRAFT_REG": "", "REPORT_DATE": "",
        "DOM": "",
    }
    m = _TYPE_RE.search(first_page_text)
    if m:
        meta["AIRCRAFT_TYPE"] = m.group(1)
        meta["AIRCRAFT_HOURS"] = m.group(2)
    m = _MSN_RE.search(first_page_text)
    if m:
        meta["AIRCRAFT_MSN"] = m.group(1)
        meta["AIRCRAFT_CYCLES"] = m.group(2)
    m = _REG_RE.search(first_page_text)
    if m:
        meta["AIRCRAFT_REG"] = m.group(1)
        meta["REPORT_DATE"] = m.group(2)
    m = _DOM_RE.search(first_page_text)
    if m:
        meta["DOM"] = m.group(1)
    return meta


def _cluster_rows(words: list[dict]) -> list[list[dict]]:
    """Group words into visual table rows by `top` position. Words on the
    same printed row can differ by a fraction of a point due to font
    baseline/rendering, so a small tolerance is used rather than an exact
    match."""
    body = [w for w in words if w["top"] > _BODY_TOP_MIN]
    body.sort(key=lambda w: (w["top"], w["x0"]))
    rows: list[list[dict]] = []
    cur: list[dict] = []
    cur_top: float | None = None
    for w in body:
        if cur_top is None or abs(w["top"] - cur_top) <= _ROW_CLUSTER_TOL:
            cur.append(w)
            if cur_top is None:
                cur_top = w["top"]
        else:
            rows.append(cur)
            cur = [w]
            cur_top = w["top"]
    if cur:
        rows.append(cur)
    return rows


def _row_to_record(row_words: list[dict]) -> dict | None:
    cols: dict[str, list[str]] = {}
    for w in row_words:
        cx = (w["x0"] + w["x1"]) / 2
        name = _col_for_x(cx)
        if name is None:
            continue
        cols.setdefault(name, []).append(w["text"])
    li_toks = cols.get("LI")
    ata_toks = cols.get("ATA")
    if not li_toks or not _LI_RE.match(li_toks[0]):
        return None
    if not ata_toks or not _ATA_RE.match(ata_toks[0]):
        return None
    return {name: " ".join(cols.get(name, [])) for _, _, name in _COLUMNS if name != "LI"}


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        if not pdf.pages:
            return records
        meta = _parse_header_meta(pdf.pages[0].extract_text() or "")
        for page_num, page in enumerate(pdf.pages, start=1):
            words = page.extract_words()
            if not words:
                continue
            for row_words in _cluster_rows(words):
                rec = _row_to_record(row_words)
                if rec is None:
                    continue
                rec.update(meta)
                rec["_page"] = page_num
                records.append(rec)
    return records
