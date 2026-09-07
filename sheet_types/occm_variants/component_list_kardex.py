"""OCCM "COMPONENT LIST" variant with a Kardex-style column layout.

Title reads literally "COMPONENT LIST", preceded by a short header block and
followed by a wide landscape table headed "A/C ATA Kardex description Type
P/N S/N F/N Manufacture Date Install Date TSN CSN Time Since Inst Cycle
Since Inst". Confirmed directly against the real sample file: it DOES carry
a real, page-searchable text layer throughout (not scanned/blank), so this
module is synchronous, pdfplumber-only, no OCR -- but the text layer is
genuinely noisy: the same header/label text is spelled differently from
page to page in this file (e.g. the tail-registration label renders as
"A/C:", "AJC:", "AIC:", or "NC:" depending on the page, and column-header
words like "description"/"Kardex"/"Since" show one-off character drops or
substitutions per page too). This looks like a lossy re-render step
somewhere in this document's generation pipeline, not a scanned/OCR'd
source -- every page still yields a full, page-specific text layer, just an
inconsistent one. Every parsing decision below was checked directly against
the real file to confirm it degrades safely rather than mis-splitting data
when this noise is present.

Header block (first page only; some fields repeat, differently garbled, on
every page's own header band, but only the first page is used -- see
below)::

    <label>:<reg>
    MSN: <msn>
    COMPONENT LIST
    Airframe TAH: <n>
    Airframe TAC: <n>
    Date: <date>

The registration label's own text is one of the confirmed real variants
above, but the VALUE after the colon is spelled consistently everywhere it
occurs, so it's read generically as "whatever follows the first colon on
line 1" rather than by matching a specific label string. The word before
"TAH:"/"TAC:" is ALSO confirmed spelled two different ways on the very same
real header block (one reads "Airframe", the other has a dropped/duplicated
letter) -- so both value fields are anchored on the "TAH:"/"TAC:" label
text alone, which is spelled consistently everywhere checked, rather than
on the word before it. Confirmed directly that the TAH value ALSO differs
between pages for what should be a single unchanging report-level figure (a
page 2+ value seen during inspection had one digit different from page 1's)
-- this is more of the same per-page text-layer noise, not a real change in
the aircraft's total time. Because of this, header metadata is read from
page 1 ONLY and stamped on every row from every page, per this project's
usual header-plus-body convention -- never re-read per page, which would
otherwise let noise on a later page silently override a correct earlier
value.

Table layout, confirmed directly against word x-positions on the rendered
page (position-anchored column bucketing, the same principle this project's
other Kardex/word-grid OCCM variants use, NOT `extract_text()`'s flattened
line order -- description text genuinely interleaves with the row above and
below it, see below)::

    A/C ATA  Kardex description  Type  P/N  S/N  F/N  Manufacture Date  Install Date  TSN  CSN  Time Since Inst  Cycle Since Inst

A data row, tokens in column order::

    <ata> <description...> <type> <pn> <sn> <fn> <manufacture_date> <install_date> <tsn> <csn> <tsi> <csi>

The leading A/C column repeats the header's own tail registration on every
row (confirmed identical to the header value on every row checked) and is
used only to help anchor a row -- it is not carried into the output as its
own column, since AIRCRAFT_REG (header metadata, stamped once) already
covers it.

TYPE column values are one of "O/C", "0/C", or "OIC" depending on the page
(confirmed via direct character-level font inspection: these renders differ
in font between pages/rows but all occupy the exact same column position
and are the only values ever seen there) -- read as a single logical value
and accepted as equivalent by this module's TYPE pattern rather than
flagged as inconsistent, since this is the same kind of per-page text-layer
noise described above, confirmed directly rather than assumed.

Row anchoring: a row is accepted as a genuine data row only when it carries
BOTH the header's own tail registration (in the A/C column) AND a
recognisable TYPE-column token (matched loosely, case-insensitively, to
allow for the font-driven spelling noise above) -- ATA-column value and
numeric TSN/CSN were tried first and rejected as anchors, because a
confirmed real handful of rows print "UNK" in TSN/CSN (a legitimate
sentinel for unknown prior life, not a parse failure) rather than a number,
which would otherwise silently drop those rows from detection.

Multi-line description handling -- confirmed directly against the real
file, a genuine, deliberate layout behaviour, not a bug: when a component's
description needs more than one printed line, the renderer keeps the row's
OTHER columns (dates/TSN/CSN/etc.) on a single line vertically centred
within the description's own line-block, rather than repeating them on
every description line. A description that needs exactly one line sits on
the same physical line as the rest of that row's data (the common case);
one needing two lines is centred between them, so the row's other data ends
up on neither description line -- both a line straight above AND a line
straight below the anchor row can be part of THIS SAME row's description.
Confirmed directly, row by row, against the real file: whichever
neighbouring anchor's own on-row description cell came up empty is the one
that claims an adjacent description-only line; when exactly one
description-only line-group falls between two anchors, it always belongs
to whichever one of the two has an empty own-row description (the other
one's description was already complete on its own line) -- checked
directly, this was unambiguous on every one of the real occurrences in the
file (46 non-zero gaps checked directly: never both anchors empty with only
one line between them, and never both already non-empty with a stray line
between them). When exactly two description-only lines fall between two
anchors (both of whose own-row descriptions are empty, confirmed the only
way this occurs in the file), the first is the earlier anchor's trailing
continuation and the second is the later anchor's leading continuation --
also confirmed directly, on every real occurrence. Any other combination
(should it ever occur on a file this module hasn't seen) is NOT guessed at
-- per this project's soft-validation convention, it is folded into
STATUS_TRAIL on the nearer row instead of being silently attached to a
description that might already be complete and correct.

A single real one-off case was also confirmed directly: one row's TYPE cell
prints noticeably higher than the rest of that same row's data (its own
tiny vertical offset), which would otherwise put it in its own orphan
line-group with no other column filled in. Since a lone TYPE-column token
can never be a real row by itself (no registration, no ATA, no data), any
line-group consisting of exactly one word that lands in the TYPE column is
merged into the very next line-group before row-anchoring runs, rather than
either being discarded (which would silently blank that row's TYPE value)
or guessed at.

Known limitation, confirmed directly: this file's records are not
guaranteed to stay entirely on one page -- but checked directly against
every page boundary in the real file, no record's description wrap ever
needed to continue across a page break (the one page whose first anchor
needed a leading continuation line had it on the SAME page, above the
header cut-off; the one page with a stray leftover description word after
its last anchor belonged to a row whose own description was already
complete). Cross-page continuation is therefore not implemented -- it was
checked to not be needed here, not assumed to be safe in general.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "OCCM Component List (Kardex)"
SIGNATURES = [
    "COMPONENT LIST",
]

CANONICAL_COLUMNS = [
    "ATA",
    "DESCRIPTION",
    "TYPE",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "FIN",
    "MANUFACTURE_DATE",
    "INSTALL_DATE",
    "TSN",
    "CSN",
    "TSI",
    "CSI",
    # Soft-validation catch-all: only ever populated for a description-line
    # attribution this module could not confirm (see module docstring) --
    # empty on every row of the real sample file, since every real gap
    # resolved unambiguously.
    "STATUS_TRAIL",
    # Header metadata, parsed once from page 1 and stamped on every row.
    "AIRCRAFT_REG",
    "AIRCRAFT_MSN",
    "AIRCRAFT_HOURS",
    "AIRCRAFT_CYCLES",
    "REPORT_DATE",
]

# TSN/CSN/TSI/CSI cells are plain numbers (integer or decimal), but a
# confirmed real sentinel "UNK" (unknown prior life on a part with no
# tracked history) is a legitimate value too, not a parse failure.
_NUM_RULE = {"pattern": r"^(?:\d+(?:\.\d+)?|UNK)$", "allow_empty": True}
# Dates print as DD-MM-YY, but a confirmed real minority of rows use a
# doubled dash ("11--09-18") -- a genuine source formatting quirk, not an
# extraction artefact -- so 1 or 2 dashes are both accepted. MANUFACTURE_DATE
# additionally allows the "UNK" sentinel (confirmed on real rows for parts
# with no recorded manufacture date).
_INSTALL_DATE_RULE = {"pattern": r"^\d{1,2}-{1,2}\d{1,2}-{1,2}\d{2,4}$", "allow_empty": True}
_MANUFACTURE_DATE_RULE = {
    "pattern": r"^(?:\d{1,2}-{1,2}\d{1,2}-{1,2}\d{2,4}|UNK)$",
    "allow_empty": True,
}

_OVERRIDES = {
    # The global PART_NUMBER/SERIAL_NUMBER rules forbid embedded spaces, but
    # a confirmed real minority of this format's PN/SN cells carry one (a
    # manufacturer batch-code prefix separated from a numeric suffix) --
    # loosened here rather than flagging every such row.
    "PART_NUMBER": {
        "pattern": r"^[A-Z0-9](?:[A-Z0-9\-/ ]*[A-Z0-9])?$",
        "uppercase": True,
    },
    "SERIAL_NUMBER": {
        "pattern": r"^[A-Z0-9](?:[A-Z0-9\-/ ]*[A-Z0-9])?$",
        "uppercase": True,
    },
    # FIN's global rule forbids spaces and caps length at 8, but this
    # format's F/N cells occasionally carry an embedded space (confirmed on
    # real rows, e.g. a code plus a switch-position suffix) and can run
    # slightly longer -- loosened here rather than flagging every such row.
    # Genuinely blank on a confirmed real minority of rows too.
    "FIN": {
        "pattern": r"^[A-Z0-9](?:[A-Z0-9 ]{0,12}[A-Z0-9])?$",
        "uppercase": True,
        "allow_empty": True,
        "char_map": None,
        "sequence_map": None,
        "no_spaces": False,
    },
    # TYPE holds only "O/C" (or a same-meaning per-page rendering of it --
    # see module docstring) on every real row checked.
    "TYPE": {"pattern": r"^[Oo0][/I.,]?[Cc]$", "allow_empty": True},
    "MANUFACTURE_DATE": _MANUFACTURE_DATE_RULE,
    "INSTALL_DATE": _INSTALL_DATE_RULE,
    "TSN": _NUM_RULE,
    "CSN": _NUM_RULE,
    "TSI": _NUM_RULE,
    "CSI": _NUM_RULE,
    "STATUS_TRAIL": {"allow_empty": True},
    "AIRCRAFT_REG": {"uppercase": True, "allow_empty": True},
    "AIRCRAFT_MSN": {"allow_empty": True},
    "AIRCRAFT_HOURS": {"pattern": r"^\d+(?:\.\d+)?$", "allow_empty": True},
    "AIRCRAFT_CYCLES": {"pattern": r"^\d+$", "allow_empty": True},
    "REPORT_DATE": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Column boundaries as (x0_inclusive, x1_exclusive, name), derived from the
# real header row's own word x-positions (checked stable across every page
# of the real file, well within a few points of jitter) and confirmed
# row-by-row against real data, including the multi-line-description and
# blank-cell cases described in the module docstring.
_COLUMNS = [
    (-1e9, 102.0, "ACREG"),
    (102.0, 132.0, "ATA"),
    (132.0, 267.0, "DESCRIPTION"),
    (267.0, 296.0, "TYPE"),
    (296.0, 355.0, "PART_NUMBER"),
    (355.0, 420.0, "SERIAL_NUMBER"),
    (420.0, 470.0, "FIN"),
    (470.0, 530.0, "MANUFACTURE_DATE"),
    (530.0, 590.0, "INSTALL_DATE"),
    (590.0, 637.0, "TSN"),
    (637.0, 676.0, "CSN"),
    (676.0, 728.0, "TSI"),
    (728.0, 1e9, "CSI"),
]
# Header/body split: the column-header row itself sits around top=108-110 on
# every page checked; real data starts at top >= ~122. The footer page
# marker ("<n> of <n>") sits around top=562 on every page checked. Both
# bounds confirmed directly against the real file rather than guessed.
_BODY_TOP_MIN = 113.0
_BODY_TOP_MAX = 558.0
_ROW_CLUSTER_TOL = 2.5

_TYPE_RE = re.compile(r"^[Oo0][/I.,]?[Cc]$")

_MSN_RE = re.compile(r"MSN:\s*(\S+)")
# The "Airframe" word preceding these two labels is confirmed spelled two
# different ways on the very same real header block ("Aifframe TAH:" /
# "Airframe TAC:") -- more of the per-page text-layer noise described in
# the module docstring. TAH:/TAC:/Date: themselves are spelled consistently
# everywhere checked, so anchored on those alone rather than requiring a
# specific spelling of the word before them.
_TAH_RE = re.compile(r"\bTAH:\s*(\S+)")
_TAC_RE = re.compile(r"\bTAC:\s*(\S+)")
_DATE_RE = re.compile(r"\bDate:\s*(\S+)")


def _col_for_x(x: float) -> str | None:
    for lo, hi, name in _COLUMNS:
        if lo <= x < hi:
            return name
    return None


def _parse_header_meta(first_page_text: str) -> dict:
    meta = {
        "AIRCRAFT_REG": "", "AIRCRAFT_MSN": "", "AIRCRAFT_HOURS": "",
        "AIRCRAFT_CYCLES": "", "REPORT_DATE": "",
    }
    lines = first_page_text.split("\n")
    if lines:
        first_line = lines[0].strip()
        if ":" in first_line:
            meta["AIRCRAFT_REG"] = first_line.split(":", 1)[1].strip()
    m = _MSN_RE.search(first_page_text)
    if m:
        meta["AIRCRAFT_MSN"] = m.group(1)
    m = _TAH_RE.search(first_page_text)
    if m:
        meta["AIRCRAFT_HOURS"] = m.group(1)
    m = _TAC_RE.search(first_page_text)
    if m:
        meta["AIRCRAFT_CYCLES"] = m.group(1)
    m = _DATE_RE.search(first_page_text)
    if m:
        meta["REPORT_DATE"] = m.group(1)
    return meta


def _cluster_rows(words: list[dict]) -> list[list[dict]]:
    """Group words into visual table rows by `top` position. Words on the
    same printed row can differ by a fraction of a point due to font
    baseline/rendering, so a small tolerance is used rather than an exact
    match."""
    body = [w for w in words if _BODY_TOP_MIN < w["top"] < _BODY_TOP_MAX]
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


def _merge_lone_type_rows(rows: list[list[dict]]) -> list[list[dict]]:
    """A confirmed real one-off: one row's TYPE token prints slightly above
    the rest of that row's data, landing in its own single-word line-group.
    A lone TYPE-column word can never be a genuine row by itself, so it is
    merged into the next line-group (its own row) rather than silently
    dropped or mis-anchored."""
    out: list[list[dict]] = []
    i = 0
    while i < len(rows):
        r = rows[i]
        if len(r) == 1 and 267.0 <= r[0]["x0"] < 296.0 and i + 1 < len(rows):
            out.append(r + rows[i + 1])
            i += 2
        else:
            out.append(r)
            i += 1
    return out


def _desc_words(row: list[dict]) -> list[str]:
    return [w["text"] for w in row if 132.0 <= w["x0"] < 267.0]


def _is_anchor(row: list[dict], reg: str) -> bool:
    has_reg = any(
        w["x0"] < 95.0 and w["text"].upper().replace("-", "") == reg
        for w in row
    )
    has_type = any(
        270.0 <= w["x0"] < 300.0 and _TYPE_RE.match(w["text"])
        for w in row
    )
    return has_reg and has_type


def _row_to_record(row: list[dict]) -> dict:
    cols: dict[str, list[str]] = {}
    for w in row:
        cx = (w["x0"] + w["x1"]) / 2
        name = _col_for_x(cx)
        if name is None or name == "ACREG":
            continue
        cols.setdefault(name, []).append(w["text"])
    return {name: " ".join(cols.get(name, [])) for _, _, name in _COLUMNS if name != "ACREG"}


def _assemble_page_records(rows: list[list[dict]], reg: str) -> list[dict]:
    anchor_idx = [i for i, r in enumerate(rows) if _is_anchor(r, reg)]
    if not anchor_idx:
        return []
    recs = []
    own_desc = []
    for ai in anchor_idx:
        rec = _row_to_record(rows[ai])
        recs.append(rec)
        own_desc.append(" ".join(_desc_words(rows[ai])).strip())
    lead: list[list[str]] = [[] for _ in anchor_idx]
    trail: list[list[str]] = [[] for _ in anchor_idx]
    status_trail: list[list[str]] = [[] for _ in anchor_idx]

    # Gap before the very first anchor on this page (only relevant if its
    # own description cell was empty -- see module docstring).
    if own_desc[0] == "" and anchor_idx[0] > 0:
        texts = [" ".join(_desc_words(rows[k])).strip() for k in range(0, anchor_idx[0])]
        texts = [t for t in texts if t]
        lead[0] = texts

    # Gaps between each pair of consecutive anchors.
    for idx in range(len(anchor_idx) - 1):
        a_ai, b_ai = anchor_idx[idx], anchor_idx[idx + 1]
        between = list(range(a_ai + 1, b_ai))
        if not between:
            continue
        texts = [" ".join(_desc_words(rows[k])).strip() for k in between]
        texts = [t for t in texts if t]
        if not texts:
            continue
        prev_empty = own_desc[idx] == ""
        next_empty = own_desc[idx + 1] == ""
        if prev_empty and not next_empty:
            trail[idx].extend(texts)
        elif next_empty and not prev_empty:
            lead[idx + 1] = texts + lead[idx + 1]
        elif prev_empty and next_empty and len(texts) == 2:
            trail[idx].append(texts[0])
            lead[idx + 1] = [texts[1]] + lead[idx + 1]
        else:
            # Genuinely ambiguous (never observed on the real sample file --
            # see module docstring): don't guess which record this text
            # belongs to. Fold it onto the nearer (next) row's STATUS_TRAIL
            # instead of silently attaching it to either description.
            status_trail[idx + 1].extend(texts)

    for i, rec in enumerate(recs):
        parts = [p for p in lead[i] if p]
        if own_desc[i]:
            parts.append(own_desc[i])
        parts.extend(p for p in trail[i] if p)
        rec["DESCRIPTION"] = " ".join(parts)
        rec["STATUS_TRAIL"] = " | ".join(status_trail[i])
    return recs


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        if not pdf.pages:
            return records
        meta = _parse_header_meta(pdf.pages[0].extract_text() or "")
        reg = meta.get("AIRCRAFT_REG", "").upper().replace("-", "")
        for page_num, page in enumerate(pdf.pages, start=1):
            words = page.extract_words()
            if not words:
                continue
            rows = _cluster_rows(words)
            rows = _merge_lone_type_rows(rows)
            for rec in _assemble_page_records(rows, reg):
                rec.update(meta)
                rec["_page"] = page_num
                records.append(rec)
    return records
