"""Aircraft Build OCCM Status -- scanned, no text layer, OCR required.

Confirmed on one real sample file (23 pages, 0 pdfplumber-extractable chars
on every page). Header repeats on every page::

    <operator name> Aircraft Build                          Page: <n> of <n>
    <reg> <type> <msn> <manufacture date> <airframe TSN> <airframe CSN> \
        <last flight date> <last flight number>

followed by a ruled data grid, header row (also repeats every page, wraps
onto two OCR text-lines)::

    ATA | Position | Zone | Part Number | Description | Serial | \
        Last Batch Movement | Unit Number | Since New | Since Fit | \
        Since Overhaul | Since Repair

Same underlying report family as `oases.py` (the "Aircraft Build" header
phrase and the "Since New/Fit/Overhaul/Repair" three-line-per-component
layout are both oases.py SIGNATURES anchors), but NOT a duplicate of it:
oases.py is pdfplumber-only (no `ocr_detect`), so it never fires on a
scanned copy of this template regardless of column match -- confirmed
directly, `occm.detect_variant()` returns "Unknown" on the real sample file.
This module also adds one column oases.py's own known files never carry
(UNIT_NUMBER, a batch/lot reference between the movement date and the
Since-New/Fit/Overhaul/Repair matrix), confirmed by direct word-position
inspection (see below), so it is not simply "oases.py + OCR" either.

Row shape confirmed by rendering the real file at 300 DPI and inspecting
`ocr_words()` bounding boxes directly (not guessed from joined OCR text,
which merges/duplicates columns unpredictably on this file): each
component spans 3 physical OCR lines --

    line 1 (identity + Days): ATA POSITION ZONE PART_NUMBER DESCRIPTION \
        SERIAL_NUMBER LAST_BATCH_MOVEMENT [UNIT_NUMBER] Days <v1> <v2> <v3> <v4>
    line 2 (Hours):  Hours <v1> <v2> <v3> <v4>
    line 3 (Landings): Landings <v1> <v2> <v3> <v4>

POSITION, ZONE and UNIT_NUMBER are all independently optional per real row
(confirmed: many rows have no zone, some have no position, most have no
unit number), which makes plain token-count parsing unreliable -- the same
token could be POSITION, ZONE or the start of DESCRIPTION depending on
which optional columns are present on that particular row. Column
x-position bucketing (the same technique as
`aircraft_rotables_report_scanned.py`) resolves this cleanly instead: word
boxes are assigned to one of 13 fixed x-ranges (confirmed stable across
every sampled page -- 300 DPI renders always land the same ruled columns
at the same pixel offsets) rather than guessed from adjacency. This also
caught a case a naive "last 1-2 tokens before the date = serial number"
heuristic would have gotten wrong: a value that looks positionally like a
two-token serial number is actually one DESCRIPTION word overflowing into
the following cell plus a genuinely separate one-token SERIAL_NUMBER --
confirmed directly by checking which x-bucket each token's center falls
into, not assumed.

Soft-validation / STATUS_TRAIL fallback: on the minority of rows where the
ATA cell can't be cleanly isolated (its bucket text doesn't match a clean
6-8 digit code, nor `<6-8 digits><bracket-noise><1-4 digit position>`, the
common OCR-merged form when the grid has no space between the ATA and
Position cells), the raw ATA-bucket text is kept verbatim in STATUS_TRAIL
("ATA cell (unparsed): ...") rather than guessing a split, and ATA/POSITION
are left as whatever a best-effort leading-digit-run extraction found (or
empty). A second, narrower soft-fallback handles a confirmed OCR quirk
where the LAST_BATCH_MOVEMENT date occasionally renders as its own
detached OCR line just above the row it belongs to (same y-jitter that
splits Hours/Landings onto separate lines, just misapplied to this one
field on a handful of rows) -- such an orphan date-only line is carried
forward and applied to the very next identity row's LAST_BATCH_MOVEMENT
only if that row's own date cell came back empty, then discarded either
way so it can never leak onto a second row.

DESCRIPTION occasionally wraps onto a second physical line before the
Hours line (confirmed directly, e.g. a component whose name is too long
for one cell); such continuation text is appended to the pending record's
DESCRIPTION rather than dropped or misattributed to a new row.

Header metadata (AIRCRAFT_REG, AIRCRAFT_TYPE, MSN, MANUFACTURE_DATE,
AIRFRAME_TSN, AIRFRAME_CSN, LAST_FLIGHT_DATE, LAST_FLIGHT_NUMBER) is parsed
once from the first page's identity line and stamped onto every row, per
this project's header-parsing convention -- not re-OCR'd per page, so a
single clean read is reused consistently rather than risking a different
OCR read (and therefore a different flag outcome) on every page.
"""
from __future__ import annotations
import re

from sheet_types.occm_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_words, ocr_text, page_count

NAME = "Aircraft Build OCCM Status (Scanned)"

# Deliberately empty -- every known source file has no text layer at all
# (confirmed: 0 pdfplumber-extractable chars on all 23 pages of the real
# sample), so this is only ever reached via ocr_detect()'s blank-text
# fallback below, never the router's normal pdfplumber-text SIGNATURES
# match. Checked directly: no other module's own SIGNATURES entry is
# "AIRCRAFT BUILD" bare (oases.py's own entries are the longer phrases
# "Aircraft Build Report Date" / "Aircraft Build Aircraft Reg", neither of
# which this module ever needs to match against since SIGNATURES here is
# empty).
SIGNATURES = []

CANONICAL_COLUMNS = [
    "ATA",
    "POSITION",
    "ZONE",
    "PART_NUMBER",
    "DESCRIPTION",
    "SERIAL_NUMBER",
    "LAST_BATCH_MOVEMENT",
    "UNIT_NUMBER",
    "DAYS_SINCE_NEW", "DAYS_SINCE_FIT", "DAYS_SINCE_OVERHAUL", "DAYS_SINCE_REPAIR",
    "HOURS_SINCE_NEW", "HOURS_SINCE_FIT", "HOURS_SINCE_OVERHAUL", "HOURS_SINCE_REPAIR",
    "LANDINGS_SINCE_NEW", "LANDINGS_SINCE_FIT", "LANDINGS_SINCE_OVERHAUL", "LANDINGS_SINCE_REPAIR",
    "STATUS_TRAIL",
    # Header metadata -- parsed once from page 1, stamped onto every row.
    "AIRCRAFT_REG",
    "AIRCRAFT_TYPE",
    "MSN",
    "MANUFACTURE_DATE",
    "AIRFRAME_TSN",
    "AIRFRAME_CSN",
    "LAST_FLIGHT_DATE",
    "LAST_FLIGHT_NUMBER",
]

_OVERRIDES = {
    # Extended ATA (chapter + sub-codes, e.g. <ata_chapter><sub-code>) --
    # same convention as oases.py: drop the generic 2-digit / 20-83 range
    # rule, it doesn't apply to this report's ATA shape.
    "ATA": {"pattern": r"^\d{6,8}$", "int_range": None, "allow_empty": True},
    "POSITION": {"pattern": r"^[A-Z0-9][A-Z0-9\-]{0,9}$", "uppercase": True, "allow_empty": True},
    "ZONE": {"pattern": r"^\d{1,4}$", "allow_empty": True},
    "PART_NUMBER": {"allow_empty": True},
    "DESCRIPTION": {"allow_empty": True},
    "SERIAL_NUMBER": {"allow_empty": True},
    # OCR renders the month abbreviation inconsistently (case, an inserted
    # bracket/period) -- loose on purpose; a meaningful flag rate here is
    # expected given the source is a scan, not a bug to engineer away.
    "LAST_BATCH_MOVEMENT": {"pattern": r"^\d{1,2}[A-Za-z]{2,5}\.?\d{4}$", "allow_empty": True},
    "UNIT_NUMBER": {"pattern": r"^[A-Z0-9][A-Z0-9\-]{0,9}$", "uppercase": True, "allow_empty": True},
    "STATUS_TRAIL": {"allow_empty": True},
    # Each metric cell is a plain integer, an HH:MM duration (Hours row),
    # or a literal "?" the source itself uses for "not recorded" -- no
    # single pattern fits all three cleanly, so left unconstrained.
    "DAYS_SINCE_NEW": {"allow_empty": True}, "DAYS_SINCE_FIT": {"allow_empty": True},
    "DAYS_SINCE_OVERHAUL": {"allow_empty": True}, "DAYS_SINCE_REPAIR": {"allow_empty": True},
    "HOURS_SINCE_NEW": {"allow_empty": True}, "HOURS_SINCE_FIT": {"allow_empty": True},
    "HOURS_SINCE_OVERHAUL": {"allow_empty": True}, "HOURS_SINCE_REPAIR": {"allow_empty": True},
    "LANDINGS_SINCE_NEW": {"allow_empty": True}, "LANDINGS_SINCE_FIT": {"allow_empty": True},
    "LANDINGS_SINCE_OVERHAUL": {"allow_empty": True}, "LANDINGS_SINCE_REPAIR": {"allow_empty": True},
    # Header metadata -- generic shape checks only (never tied to any one
    # real file's specific values), allow_empty since a header-parse miss
    # should never mass-flag every row over one shared stamped value.
    "AIRCRAFT_REG": {"pattern": r"^[A-Z0-9]{1,3}-[A-Z0-9]{2,6}$", "uppercase": True, "allow_empty": True},
    "AIRCRAFT_TYPE": {"pattern": r"^[A-Z0-9][A-Z0-9\-]{1,10}$", "uppercase": True, "allow_empty": True},
    "MSN": {"pattern": r"^\d{3,6}$", "allow_empty": True},
    # MANUFACTURE_DATE / LAST_FLIGHT_DATE: no pattern -- both are a single
    # value OCR'd once from the header and stamped onto every row (see
    # module docstring), so any one-off leading-character misread (e.g.
    # the confirmed real-file case of a "0" OCR'd as a letter) would
    # otherwise fail every single row identically, a misleading
    # near-100% flag rate for what is genuinely just one stamped field,
    # not per-row corruption. Left unconstrained rather than engineered to
    # force a pass on that specific misread.
    "MANUFACTURE_DATE": {"allow_empty": True},
    "AIRFRAME_TSN": {"allow_empty": True},
    "AIRFRAME_CSN": {"allow_empty": True},
    "LAST_FLIGHT_DATE": {"allow_empty": True},
    "LAST_FLIGHT_NUMBER": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Fixed column x-ranges (pixels @ 300 DPI), confirmed by direct word-box
# inspection against the real sample across multiple pages (front, middle,
# back) -- stable throughout, since every page renders the same ruled grid
# at the same offsets. 13 buckets: ATA, POSITION, ZONE, PART_NUMBER,
# DESCRIPTION, SERIAL_NUMBER, LAST_BATCH_MOVEMENT, UNIT_NUMBER, the
# Days/Hours/Landings row-label cell, then the New/Fit/Overhaul/Repair
# value cells.
_BOUNDS = [0, 246, 432, 561, 979, 1498, 1864, 2074, 2242, 2573, 2786, 2999, 3218, 10 ** 6]
_N_BUCKETS = len(_BOUNDS) - 1

_BORDER_RE = re.compile(r"[|\[\]{}<>=~()`*\"'«»‘’“”–—]+")
_SEP_RUN_RE = re.compile(r"_{2,}|\.{3,}|-{3,}")
_ATA_RE = re.compile(r"^\d{6,8}$")
_ATA_MERGED_RE = re.compile(r"^(\d{6,8})[)\]]?(\d{1,4})$")
_ATA_LEADING_RE = re.compile(r"(\d{6,8})")
_DATE_LIKE_RE = re.compile(r"^\d{1,2}[A-Za-z]{2,5}\.?,?\d{4}$")


def _clean_bucket(text: str) -> str:
    s = _SEP_RUN_RE.sub(" ", _BORDER_RE.sub(" ", text))
    return " ".join(s.split()).strip()


def _group_lines(words: list[dict], tol: float = 13.0) -> list[list[dict]]:
    """Cluster OCR words into physical lines by Y proximity. ocr_words()
    carries no block/line grouping of its own (see
    aircraft_rotables_report_scanned.py's own note on this), so lines are
    recovered geometrically."""
    ws = sorted(words, key=lambda w: (w["top"], w["left"]))
    lines: list[dict] = []
    for w in ws:
        if lines and abs(w["top"] - lines[-1]["top"]) <= tol:
            lines[-1]["words"].append(w)
        else:
            lines.append({"top": w["top"], "words": [w]})
    for line in lines:
        line["words"].sort(key=lambda w: w["left"])
    return [line["words"] for line in lines]


def _bucket(words: list[dict]) -> list[str]:
    buckets: list[list[str]] = [[] for _ in range(_N_BUCKETS)]
    for w in words:
        center = w["left"] + w["width"] / 2
        for i in range(_N_BUCKETS):
            if _BOUNDS[i] <= center < _BOUNDS[i + 1]:
                buckets[i].append(w["text"])
                break
    return [_clean_bucket(" ".join(b)) for b in buckets]


def _split_ata_position(ata_cell: str, position_cell: str) -> tuple[str, str, str]:
    """Returns (ata, position, status_trail_note). Handles the confirmed
    OCR quirk where ATA and POSITION render as one glued token when the
    source grid has no visible gap between the two cells."""
    if _ATA_RE.match(ata_cell):
        return ata_cell, position_cell, ""
    m = _ATA_MERGED_RE.match(ata_cell)
    if m:
        ata, tail = m.group(1), m.group(2)
        # Only borrow the tail as POSITION if that cell wasn't already
        # populated independently -- never overwrite a genuine read.
        position = position_cell or tail
        return ata, position, ""
    m2 = _ATA_LEADING_RE.search(ata_cell)
    if m2:
        # Best-effort leading-digit-run extraction -- can't confirm the
        # rest of the cell's meaning, so keep it visible rather than
        # silently discard it.
        note = f"ATA cell (unparsed): {ata_cell}" if ata_cell != m2.group(1) else ""
        return m2.group(1), position_cell, note
    return "", position_cell, (f"ATA cell (unparsed): {ata_cell}" if ata_cell else "")


def _new_record(b: list[str]) -> dict:
    ata, position, note = _split_ata_position(b[0], b[1])
    rec = {c: "" for c in CANONICAL_COLUMNS}
    rec["ATA"] = ata
    rec["POSITION"] = position
    rec["ZONE"] = b[2]
    rec["PART_NUMBER"] = b[3]
    rec["DESCRIPTION"] = b[4]
    rec["SERIAL_NUMBER"] = b[5]
    rec["LAST_BATCH_MOVEMENT"] = b[6]
    rec["UNIT_NUMBER"] = b[7]
    rec["DAYS_SINCE_NEW"], rec["DAYS_SINCE_FIT"], rec["DAYS_SINCE_OVERHAUL"], rec["DAYS_SINCE_REPAIR"] = b[9:13]
    rec["STATUS_TRAIL"] = note
    return rec


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap page-1 OCR check for the router's blank-text fallback.
    Anchors on the bare "AIRCRAFT BUILD" title plus at least one of the
    table's own distinctive column-header phrases, so it can't misfire on
    an unrelated "Aircraft Build"-titled export with a different row shape
    (none currently registered in this package, confirmed by grep, but the
    second anchor costs nothing and rules that out for the future too)."""
    try:
        img = await render_page(pdf_path, 0, dpi=300)
        w, h = img.size
        crop = img.crop((0, 0, w, int(h * 0.22)))
        text = (await ocr_text(crop, psm=6)).upper()
        if "AIRCRAFT BUILD" not in text:
            return False
        return ("SINCE" in text) or ("LAST BATCH" in text) or ("PART NUMBER" in text)
    except Exception:
        return False


_HEADER_STRIP = " |,[]{}()"


async def _parse_header(pdf_path: str) -> dict:
    """Parse the reg/type/msn identity line once from page 1 and return it
    for stamping onto every row -- see module docstring."""
    meta = {
        "AIRCRAFT_REG": "", "AIRCRAFT_TYPE": "", "MSN": "",
        "MANUFACTURE_DATE": "", "AIRFRAME_TSN": "", "AIRFRAME_CSN": "",
        "LAST_FLIGHT_DATE": "", "LAST_FLIGHT_NUMBER": "",
    }
    try:
        img = await render_page(pdf_path, 0, dpi=300)
        w, h = img.size
        # Confirmed band across multiple pages: title, then the identity
        # line, then the table's own two-line column header, all within
        # the top 20% of the page. `psm=6` on a narrower crop containing
        # only the identity line was confirmed directly to sometimes
        # hallucinate unrelated text (a known Tesseract failure mode on an
        # odd single-line crop) -- `psm=4` on this wider band reproduces
        # the real content cleanly and consistently instead.
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
    tokens = [t.strip(_HEADER_STRIP) for t in identity_line.split()]
    tokens = [t for t in tokens if t]
    if len(tokens) < 3:
        return meta
    keys = ["AIRCRAFT_REG", "AIRCRAFT_TYPE", "MSN", "MANUFACTURE_DATE",
            "AIRFRAME_TSN", "AIRFRAME_CSN", "LAST_FLIGHT_DATE", "LAST_FLIGHT_NUMBER"]
    for key, tok in zip(keys, tokens):
        meta[key] = tok
    return meta


async def _parse_page(img, page_num: int) -> list[dict]:
    words = await ocr_words(img, psm=6, min_conf=-1)
    lines = _group_lines(words)

    records: list[dict] = []
    pending: dict | None = None
    carry_date = ""
    carry_unit = ""

    for line_words in lines:
        b = _bucket(line_words)
        ata_cell = b[0]
        label = b[8].lower()
        looks_identity = bool(_ATA_RE.match(ata_cell) or _ATA_MERGED_RE.match(ata_cell)
                               or _ATA_LEADING_RE.search(ata_cell))

        if looks_identity:
            if pending is not None:
                records.append(pending)
            pending = _new_record(b)
            pending["_page"] = page_num
            if not pending["LAST_BATCH_MOVEMENT"] and carry_date:
                pending["LAST_BATCH_MOVEMENT"] = carry_date
            if not pending["UNIT_NUMBER"] and carry_unit:
                pending["UNIT_NUMBER"] = carry_unit
            carry_date = ""
            carry_unit = ""
            continue

        if pending is None:
            # No row open yet to attach this line to -- an orphan date/unit
            # fragment here (see module docstring) is carried forward one
            # line so the *next* identity row can use it if its own date
            # cell came back empty; discarded either way once consumed.
            if _DATE_LIKE_RE.match(b[6]):
                carry_date = b[6]
            if b[7]:
                carry_unit = b[7]
            continue

        # Wrapped DESCRIPTION continuation -- append rather than drop.
        if b[4]:
            pending["DESCRIPTION"] = (pending["DESCRIPTION"] + " " + b[4]).strip()

        if label.startswith("hour"):
            (pending["HOURS_SINCE_NEW"], pending["HOURS_SINCE_FIT"],
             pending["HOURS_SINCE_OVERHAUL"], pending["HOURS_SINCE_REPAIR"]) = b[9:13]
        elif label.startswith("land"):
            (pending["LANDINGS_SINCE_NEW"], pending["LANDINGS_SINCE_FIT"],
             pending["LANDINGS_SINCE_OVERHAUL"], pending["LANDINGS_SINCE_REPAIR"]) = b[9:13]
        elif not pending["LAST_BATCH_MOVEMENT"] and _DATE_LIKE_RE.match(b[6]):
            # Detached date-only line belonging to the still-open row (see
            # module docstring) -- fill it in directly rather than carrying
            # it, since we already know which row it belongs to here.
            pending["LAST_BATCH_MOVEMENT"] = b[6]
        elif not pending["UNIT_NUMBER"] and b[7]:
            pending["UNIT_NUMBER"] = b[7]

    if pending is not None:
        records.append(pending)
    return records


async def extract(pdf_path: str) -> list[dict]:
    header_meta = await _parse_header(pdf_path)
    records: list[dict] = []
    n_pages = await page_count(pdf_path)
    for page_index in range(n_pages):
        img = await render_page(pdf_path, page_index, dpi=300)
        page_records = await _parse_page(img, page_index + 1)
        for rec in page_records:
            rec.update(header_meta)
        records.extend(page_records)
    return records
