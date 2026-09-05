"""Serialization List by ATA Chapter — landing-gear-focused parts
serialization/interchangeability list, born-digital (real text layer),
coordinate-bucketed columns.

Confirmed on one real corpus sample via a direct pdfplumber `extract_words()`
pass over every page. This is a genuinely different OCCM shape from the
usual TSN/CSN flight-hour-life tracking sheets: it tracks part
interchangeability/replaceability and physical-verification status, not
accumulated flight hours or cycles.

Header block, repeated on every page::

    <report_id> SERIALIZATION LIST by ATA CHAPTER

`<report_id>` is a short leading code (confirmed to look like it may embed
an aircraft tail/serial identifier on the known source file) -- treated as
opaque, parsed once from page 1 and stamped on every row as REPORT_ID,
never inspected or matched against for row logic. Do not assume any
particular shape for it beyond "whatever text precedes the literal title
phrase on this line".

Column-header line (repeated on every page, immediately above the body,
confirmed via direct word-position inspection)::

    ATA PART NUM DESCRIPTION <flag> MANUF DATE SERIAL INTRCHGE RPLCBLE S/N VERIFIED LOCATION ON AIRCRAFT ZONE

The `<flag>` column header word renders inconsistently across pages of the
same known source file -- confirmed directly via `page.chars` (same
Helvetica font every time, so this is not a custom-glyph-encoding quirk,
genuinely different literal text was typeset page to page): seen as
"UFED", "LJFED" and "LIFED" on different pages of one file. A footnote on
the known source file's last page ('Note 1: "T" in "LIFED" column
indicates components that are to be lifed temporarily...') confirms the
intended column is **LIFED**, so that is the canonical column name used
here; SIGNATURES below deliberately avoid this word since it isn't stable
across pages.

This module does NOT tokenize by whitespace-splitting the row text. Ten
columns can each independently be blank or filled per row (LIFED,
MANUF_DATE, SERIAL, INTRCHGE and RPLCBLE are NOT mutually exclusive or
sequential -- confirmed directly: some rows carry LIFED+MANUF_DATE+SERIAL+
INTRCHGE all populated and RPLCBLE blank, others carry only SERIAL+RPLCBLE
with the rest blank). Each page is read with `extract_words()`, words are
clustered into visual rows by `top`, and every word is assigned to a column
purely by which column's x-range its center falls in, in the same style as
this project's other coordinate-bucketed OCCM variants (e.g.
`occm_status_by_ata_chapter.py`). A blank cell contributes no word and
comes out as "" -- never guessed, never shifted into a neighbour.

Confirmed real per-column contents, each checked directly against the
known source file's own word coordinates (never assumed from the header
text alone):

  - LIFED: a marker column. Values seen: "X", "T" (temporarily lifed, per
    the footnote above), "CAL." (a calendar-life marker, distinct from
    cycle-life), and occasionally a bare footnote reference like
    "Note <n>" pointing at an explanatory footnote on the file's last page
    (e.g. one explains a battery-only replacement rule, another an
    externally-mandated hydrostatic test requirement). Never guessed
    further than "whatever token(s) landed in this column's x-range".

  - MANUF_DATE: despite the header text, this column's real content is
    NOT reliably a manufacture date. Confirmed directly: on rows where
    LIFED is populated, this column instead holds the literal text
    "Cycle Life" (i.e. it's telling you the tracking basis, not a date);
    on rows where LIFED is blank, it sometimes holds a genuine "Mfg <mon-
    yy>" / "Exp. <mon-yy>" date string (occasionally both, e.g.
    "Mfg <mon-yy> / Exp <mon-yy>"), and is often blank altogether. Kept as
    free text -- no date pattern is enforced since it isn't reliably a
    date.

  - SERIAL / INTRCHGE / RPLCBLE: independent "X"/blank marker columns.
    Confirmed real glitches: an occasional stray extra token (e.g. a
    side-of-aircraft letter that printed slightly further left than usual,
    landing in a marker column's x-range instead of the location column's)
    produces a marker cell that isn't a clean "X" -- rather than guess
    which of the two columns the stray token really belongs to, the whole
    raw cell text is folded into STATUS_TRAIL and the marker field is left
    blank. A bare lowercase "x" is treated as the same marker (case is
    normalized downstream, not a content difference).

  - S/N VERIFIED: an alphanumeric-ish code, but NOT reliably a bare
    part-serial-style token. Confirmed real values include compact
    alphanumeric codes, a code with an embedded parenthetical suffix, a
    code split across two words with an internal space, and free-text
    statuses -- most commonly the literal "not serialized" (component
    carries no serial number to verify) and occasionally "C-CHECK"
    (verified during a C-check rather than against a discrete code). Kept
    permissive; never split into sub-fields.

  - The column immediately right of S/N VERIFIED's own x-range and left of
    the location text carries an optional physical-verification-method
    marker, confirmed against an explanatory footnote block on the known
    source file's last page ("V = Physical Verification", "M = Menasco
    Verification", "MHI = MHI Verification", "Date = BOI Verification").
    The first three appear verbatim as a leading token; the fourth
    appears not as the literal word "Date" but as an actual date-shaped
    token (day/month, e.g. a "<d>/<d>" pattern) in that same leading
    position -- confirmed directly, this is the "BOI verification"
    (Bill-Of-Installation) case referred to by the footnote. Only these
    two shapes (a bare V/M/MHI code, or a "<d>/<d>"-shaped token) are
    split out into VERIFICATION_METHOD; every other leading token is
    ordinary location text and is left untouched in LOCATION_ON_AIRCRAFT
    -- this is a closed, footnote-confirmed vocabulary, not a guess.

  - LOCATION_ON_AIRCRAFT: free text, occasionally containing an internal
    comma (e.g. a two-part station/compartment description).

  - ZONE: usually a 3-digit code followed by one or two literal dots
    (e.g. as printed on the known source file), but confirmed real
    variants also end in one or two letters (a sub-zone suffix) or in a
    digit-code followed by a short word abbreviation. Kept permissive.

A row is accepted only when its ATA-column text starts with a digit and
both PART_NUMBER and DESCRIPTION are non-empty -- this is what lets the
repeated header line, the repeated title line, the per-page footer
("ENGINEERING" / "REV <letter>" / "Page <n> ISSUE <n>"), and the
explanatory footnote block on the file's last page (free-text lines with
no leading digit) fall out for free without special-casing them. One
confirmed real exception: a single row on the known source file has a
garbled ATA cell (an embedded stray character breaks the normal
`##-##-##` shape) -- this is a real row (part number and description both
present and legitimate) and is deliberately still accepted rather than
dropped; soft validation flags its malformed ATA value downstream instead
of silently guessing a corrected split, the same "never guess" principle
this project's other OCCM variants apply elsewhere.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "Serialization List by ATA Chapter"

SIGNATURES = [
    "SERIALIZATION LIST by ATA CHAPTER",
    # Column-header fragments that are stable across every page of the known
    # source file (the LIFED/UFED/LJFED header word is NOT used here since it
    # renders inconsistently across pages -- see module docstring). Checked
    # for collisions against every SIGNATURES list in
    # sheet_types/{occm,ht,llp}.py and every existing variant file; none
    # found.
    "PART NUM DESCRIPTION",
    "SERIAL INTRCHGE RPLCBLE",
]

CANONICAL_COLUMNS = [
    "ATA",
    "PART_NUMBER",
    "DESCRIPTION",
    "LIFED",
    "MANUF_DATE",
    "SERIAL",
    "INTRCHGE",
    "RPLCBLE",
    "SN_VERIFIED",
    "VERIFICATION_METHOD",
    "LOCATION_ON_AIRCRAFT",
    "ZONE",
    # Header metadata, parsed once per file and stamped on every row.
    "REPORT_ID",
    # Ambiguous / can't-confirm-the-split raw text, folded here rather than
    # guessed into a marker column -- see module docstring.
    "STATUS_TRAIL",
]

_OVERRIDES = {
    # This file's ATA cell is a full `##-##-##` chapter-section-subject code,
    # not the bare 2-digit chapter the global rule expects -- overridden
    # here, and the global rule's `int_range` is explicitly disabled (it
    # would otherwise misfire "not_a_number" on every row, since this shape
    # never parses as a plain int). One confirmed real row has a garbled
    # ATA cell (see module docstring) -- left as extracted and flagged by
    # this pattern rather than guessed into a corrected shape.
    "ATA": {
        "pattern": r"^\d{2}-\d{2}-\d{2}$",
        "int_range": None,
    },
    "ZONE": {
        "pattern": r"^\d{3}(?:\.{1,2}|[A-Z]{1,2})?(?:\s[A-Z]+)?$",
        "uppercase": True,
        "allow_empty": True,
    },
    # Marker column; real vocabulary confirmed wider than a bare "X" (see
    # module docstring): "T" (temporarily lifed), "CAL." (calendar-life
    # marker), or a bare footnote reference ("Note <n>").
    "LIFED": {
        "pattern": r"^(?:X|T|CAL\.?|NOTE\s*\d+)$",
        "uppercase": True,
        "allow_empty": True,
    },
    # Free text -- confirmed to hold either the literal "Cycle Life" marker
    # or a real Mfg/Exp date string, never reliably a bare date (see module
    # docstring). No pattern enforced; char_map/sequence_map disabled since
    # this is a real text layer, not OCR output.
    "MANUF_DATE": {
        "uppercase": True,
        "char_map": {},
        "sequence_map": [],
        "allow_empty": True,
    },
    # SERIAL/INTRCHGE/RPLCBLE: independent "X"/blank marker columns. A cell
    # that isn't a clean "X" after case-normalization is folded into
    # STATUS_TRAIL by extract() rather than kept here (see module
    # docstring) -- so by the time RULES validation runs, only "X" or ""
    # should ever reach these fields; the pattern below is a safety net,
    # not the primary defence.
    "SERIAL": {"pattern": r"^X?$", "uppercase": True, "allow_empty": True},
    "INTRCHGE": {"pattern": r"^X?$", "uppercase": True, "allow_empty": True},
    "RPLCBLE": {"pattern": r"^X?$", "uppercase": True, "allow_empty": True},
    # Permissive alphanumeric-ish free text -- confirmed real values include
    # a parenthetical suffix, an internal space, and free-text statuses like
    # "not serialized" / "C-CHECK" (see module docstring). char_map/
    # sequence_map disabled for the same real-text-layer reason as
    # MANUF_DATE above.
    "SN_VERIFIED": {
        "pattern": r"^[A-Z0-9()/\- ]+$",
        "uppercase": True,
        "char_map": {},
        "sequence_map": [],
        "allow_empty": True,
    },
    # Closed, footnote-confirmed vocabulary -- see module docstring.
    "VERIFICATION_METHOD": {
        "pattern": r"^(?:V|M|MHI|\d{1,2}/\d{1,2})$",
        "uppercase": True,
        "allow_empty": True,
    },
    "LOCATION_ON_AIRCRAFT": {
        "uppercase": True,
        "char_map": {},
        "sequence_map": [],
        "allow_empty": True,
    },
    "REPORT_ID": {"allow_empty": True},
    "STATUS_TRAIL": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Column x-boundaries (PDF points), derived from real data-row word
# coordinates on the known source file (data rows, not the header line
# itself -- the header's own word positions do not line up 1:1 with where
# the body text actually renders) and confirmed row-by-row, including every
# sparse-row / independent-marker-column case described in the module
# docstring.
_FIELDS = [
    "ATA", "PART_NUMBER", "DESCRIPTION", "LIFED", "MANUF_DATE", "SERIAL",
    "INTRCHGE", "RPLCBLE", "SN_VERIFIED", "LOCATION", "ZONE",
]
_BOUNDS = [0, 62, 130, 285, 316, 386, 421, 460, 499, 570, 700, 10**6]

_ROW_CLUSTER_TOL = 3.0
_FLAG_FIELDS = ("SERIAL", "INTRCHGE", "RPLCBLE")

_REPORT_ID_RE = re.compile(
    r"^(?P<report_id>.+?)\s+SERIALIZATION LIST\s+by\s+ATA CHAPTER", re.IGNORECASE
)
_VERIF_LEAD_RE = re.compile(r"^(V|M|MHI|\d{1,2}/\d{1,2})\b(.*)$")


def _bucket(x0: float) -> str:
    for i in range(len(_BOUNDS) - 1):
        if _BOUNDS[i] <= x0 < _BOUNDS[i + 1]:
            return _FIELDS[i]
    return _FIELDS[-1]


def _parse_report_id(first_page_text: str) -> str:
    for line in (first_page_text or "").splitlines():
        m = _REPORT_ID_RE.match(line.strip())
        if m:
            return m.group("report_id").strip()
    return ""


def _cluster_rows(words: list[dict]) -> list[list[dict]]:
    ws = sorted(words, key=lambda w: (w["top"], w["x0"]))
    rows: list[list[dict]] = []
    cur: list[dict] = []
    cur_top: float | None = None
    for w in ws:
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


def _bucket_row(row_words: list[dict]) -> dict:
    cols: dict[str, list[str]] = {f: [] for f in _FIELDS}
    for w in row_words:
        cx = (w["x0"] + w["x1"]) / 2
        cols[_bucket(cx)].append(w["text"])
    return {f: " ".join(toks).strip() for f, toks in cols.items()}


def _row_to_record(raw: dict) -> dict | None:
    ata = raw["ATA"]
    if not ata or not ata[0].isdigit():
        return None
    if not raw["PART_NUMBER"] or not raw["DESCRIPTION"]:
        return None

    trail: list[str] = []
    rec = {
        "ATA": ata,
        "PART_NUMBER": raw["PART_NUMBER"],
        "DESCRIPTION": raw["DESCRIPTION"],
        "LIFED": raw["LIFED"],
        "MANUF_DATE": raw["MANUF_DATE"],
        "ZONE": raw["ZONE"],
    }

    for field in _FLAG_FIELDS:
        val = raw[field]
        if val == "" or val.upper() == "X":
            rec[field] = val
        else:
            # Can't confirm this cell is really this marker column's own
            # value (e.g. a stray neighbouring token bled into its
            # x-range) -- fold the raw text into STATUS_TRAIL rather than
            # guess, per this module's "never guess a wrong split"
            # convention.
            rec[field] = ""
            trail.append(f"{field}:{val}")

    location_raw = raw["LOCATION"]
    m = _VERIF_LEAD_RE.match(location_raw)
    if m:
        rec["VERIFICATION_METHOD"] = m.group(1)
        rec["LOCATION_ON_AIRCRAFT"] = m.group(2).strip()
    else:
        rec["VERIFICATION_METHOD"] = ""
        rec["LOCATION_ON_AIRCRAFT"] = location_raw

    rec["SN_VERIFIED"] = raw["SN_VERIFIED"]
    rec["STATUS_TRAIL"] = "; ".join(trail)
    return rec


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        if not pdf.pages:
            return records
        report_id = _parse_report_id(pdf.pages[0].extract_text() or "")
        for page_num, page in enumerate(pdf.pages, start=1):
            words = page.extract_words()
            if not words:
                continue
            for row_words in _cluster_rows(words):
                raw = _bucket_row(row_words)
                rec = _row_to_record(raw)
                if rec is None:
                    continue
                rec["REPORT_ID"] = report_id
                rec["_page"] = page_num
                records.append(rec)
    return records
