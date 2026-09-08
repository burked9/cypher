"""OCCM List variant with a Certificate/Remark column pair.

Confirmed directly via a pdfplumber pass over the whole real sample file:
a genuine, page-searchable text layer throughout (no OCR needed) -- this
module is synchronous, pdfplumber-only.

Header block (repeated verbatim on every page, first page used to stamp
REPORT_DATE onto every row per this project's usual convention)::

    OCCM List
    AS of Date: <date>

Column-header line (also this variant's SIGNATURES anchor)::

    No / Description Part No. Serial No. INST_DATE TSN CSN Certificate Remark

A data row, tokens in column order::

    <no> <description...> <pn> <sn> <install_date> <tsn> <csn> <certificate...> <remark...>

Table layout, confirmed directly against word x-positions on the rendered
page (position-anchored column bucketing, NOT `extract_text()`'s flattened
line order -- DESCRIPTION genuinely interleaves with the row above and/or
below it, see below). Column boundaries were derived from the real header's
own word x-positions and confirmed row-by-row against the real sample
file's data, including every edge case described below::

    NO            x <  100
    DESCRIPTION   100 <= x <  210
    PART_NUMBER   210 <= x <  300
    SERIAL_NUMBER 300 <= x <  400
    INSTALL_DATE  400 <= x <  490
    TSN           490 <= x <  545
    CSN           545 <= x <  600
    CERTIFICATE   600 <= x <  680
    REMARK        680 <= x

CERTIFICATE and REMARK are both bucketed by nearest header (not just a
naive per-word split): CERTIFICATE can be a single token (e.g. a
manufacturer-issued-certificate-style code, or a country/authority code) or
two tokens together (a code plus a following qualifier word observed
directly on real rows, e.g. "<code> OEI"); the qualifier word sits well
clear of REMARK's own boundary, confirmed directly on the real sample file.
REMARK is usually a short 2-digit code but is confirmed, directly on one
real row, to instead hold free text (multiple words) -- both shapes are
accepted rather than the free-text form being flagged as a parse failure.

Multi-line DESCRIPTION handling -- confirmed directly against the real
file, a genuine, deliberate layout behaviour, not a bug: when a
component's description needs more than one printed line, the renderer
keeps the row's OTHER columns (PN/SN/dates/etc.) on a single physical line
vertically centred within the description's own line-block, rather than
repeating them on every description line. A description that fits on one
line sits on the same physical line as the rest of that row's data (the
common case, e.g. a bare one- or two-word component name); one needing more
lines is centred among them, so a line straight above AND a line straight
below the anchor row can both belong to THIS SAME row's description --
and, confirmed directly on real rows with an especially long free-text
description (one that itself contains a parenthetical sub-note quoting a
kit-level part number distinct from the row's own real PART_NUMBER
column), the anchor row's own DESCRIPTION cell can ALSO be non-empty at
the same time as lines above and/or below it belong to the same
description; this module concatenates in vertical (top-to-bottom) print
order regardless of whether the anchor row's own cell is empty, rather
than assuming emptiness is required for wrapping to have occurred.

Each candidate continuation line between two anchors is assigned to
whichever of the two neighbouring anchor rows it sits vertically nearer to
(by printed line position) -- confirmed directly on the real file this
reproduces the correct split even when TWO description-only lines fall
between one pair of anchors (the first, nearer line belongs to the earlier
row's trailing continuation; the second, nearer line belongs to the later
row's leading continuation). A line that carries a word outside the
DESCRIPTION column's own x-range is never treated as a description
continuation -- per this project's "never guess a wrong split" convention,
such a line is folded verbatim into STATUS_TRAIL on its nearer anchor
instead, rather than risking misattributed data. No such fold was actually
needed on the real sample file once the column-header line's own vertical
position was accounted for per-page (see next paragraph) -- STATUS_TRAIL
exists here purely as a safety net for a file this module hasn't seen.

The column-header line's own vertical position is NOT fixed on this
format -- confirmed directly: it sits at one height on the file's earlier
pages but noticeably lower on its final, shorter page. A fixed cutoff
would leak that shifted header text into the first row's description on
such a page, so the header/body split is instead anchored per-page on the
header's own "Remark" word (unique to that line -- a real REMARK-column
value is a short code or short free-text phrase, never that literal word),
found fresh on every page rather than assumed constant.

Every value in this file's own real REMARK/CERTIFICATE columns -- including
ones that are themselves rendered as literal placeholder-shaped strings by
the source document (e.g. a country/authority-style code, or a
manufacturer-certificate-style code) -- is the document's own genuine
printed content, not something this module invents or genericizes further.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "OCCM List (Certificate/Remark)"

SIGNATURES = [
    "Part No. Serial No. INST_DATE TSN CSN Certificate Remark",
]

CANONICAL_COLUMNS = [
    "NO",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "INSTALL_DATE",
    "TSN",
    "CSN",
    "CERTIFICATE",
    "REMARK",
    # Header metadata, parsed once per file and stamped on every row.
    "REPORT_DATE",
    "STATUS_TRAIL",
]

_NUM_RE = r"^\d+(?:\.\d+)?$"

_OVERRIDES = {
    "NO": {"pattern": r"^\d+$"},
    "INSTALL_DATE": {"pattern": r"^\d{4}-\d{2}-\d{2}$"},
    "TSN": {"pattern": _NUM_RE},
    "CSN": {"pattern": _NUM_RE},
    # A code, or a code plus a trailing qualifier word -- see module
    # docstring. Placeholder-shaped codes with literal X's are genuine
    # printed values in this document, not something to flag.
    "CERTIFICATE": {"pattern": r"^[A-Z0-9](?:[A-Z0-9\- ]*[A-Z0-9])?$",
                     "uppercase": True, "allow_empty": True},
    # Usually a short numeric code, but confirmed to sometimes be free text
    # on a real row -- both accepted, see module docstring.
    "REMARK": {"pattern": r"^[A-Z0-9](?:[A-Z0-9\- ]*[A-Z0-9])?$",
               "uppercase": True, "allow_empty": True},
    "REPORT_DATE": {"pattern": r"^\d{1,2}-[A-Za-z]{3}-\d{4}$", "allow_empty": True},
    "STATUS_TRAIL": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Column x-boundaries (PDF points), derived from the real header's own word
# x-positions and confirmed row-by-row against the real sample file. See
# module docstring for the full derivation and edge cases.
_BOUNDS = [
    (-1e9, 100.0, "NO"),
    (100.0, 210.0, "DESCRIPTION"),
    (210.0, 300.0, "PART_NUMBER"),
    (300.0, 400.0, "SERIAL_NUMBER"),
    (400.0, 490.0, "INSTALL_DATE"),
    (490.0, 545.0, "TSN"),
    (545.0, 600.0, "CSN"),
    (600.0, 680.0, "CERTIFICATE"),
    (680.0, 1e9, "REMARK"),
]
_FIELDS = [b[2] for b in _BOUNDS]

_NO_ANCHOR_RE = re.compile(r"^\d+$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_REPORT_DATE_RE = re.compile(r"AS of Date:\s*(\S+)", re.IGNORECASE)

# Fallback only -- the real per-page cutoff is anchored on the header's own
# "Remark" word (see _header_bottom); this constant is used only if that
# word can't be found on a given page at all.
_BODY_TOP_MIN_FALLBACK = 130.0
# The real page footer (aircraft-lease-company name + "PAGE x of y") sits
# well below this on every page checked -- excluded outright so it can
# never leak into STATUS_TRAIL.
_BODY_TOP_MAX = 555.0
_ROW_TOL = 2.5


def _col_for_x(x: float) -> str:
    for lo, hi, name in _BOUNDS:
        if lo <= x < hi:
            return name
    return _FIELDS[-1]


def _group_lines(words: list[dict]) -> list[dict]:
    """Cluster words into visual table rows by `top` position. Words on the
    same printed row can differ by a fraction of a point due to font
    baseline/rendering, so a small tolerance is used rather than an exact
    match."""
    ws = sorted(words, key=lambda w: (w["top"], w["x0"]))
    lines: list[dict] = []
    for w in ws:
        if lines and abs(w["top"] - lines[-1]["top"]) <= _ROW_TOL:
            lines[-1]["words"].append(w)
            lines[-1]["top"] = (lines[-1]["top"] + w["top"]) / 2
        else:
            lines.append({"top": w["top"], "words": [w]})
    for line in lines:
        line["words"].sort(key=lambda w: w["x0"])
    return lines


def _bucket_line(line: dict) -> dict:
    row: dict[str, list[str]] = {f: [] for f in _FIELDS}
    for w in line["words"]:
        row[_col_for_x(w["x0"])].append(w["text"])
    return {k: " ".join(v) for k, v in row.items()}


def _is_anchor(bucketed: dict) -> bool:
    return (
        bool(_NO_ANCHOR_RE.match(bucketed["NO"]))
        and bool(_DATE_RE.match(bucketed["INSTALL_DATE"]))
        and bool(bucketed["PART_NUMBER"])
    )


def _header_bottom(all_words: list[dict]) -> float:
    """This format's column-header line does not sit at a fixed vertical
    position -- confirmed directly on the real sample file (its final,
    shorter page prints the whole header block noticeably lower than every
    earlier page). Anchoring on the header's own "Remark" word (unique to
    that line -- a real REMARK-column value is a short code or short
    free-text phrase, never that literal word) keeps the header/body split
    correct per-page instead of relying on one constant that only holds for
    most pages."""
    remark_tops = [w["top"] for w in all_words if w["text"] == "Remark"]
    if remark_tops:
        return min(remark_tops) + 15.0
    return _BODY_TOP_MIN_FALLBACK


def _extract_page(page) -> list[dict]:
    all_words = page.extract_words()
    if not all_words:
        return []
    body_min = _header_bottom(all_words)
    words = [w for w in all_words if body_min < w["top"] < _BODY_TOP_MAX]
    if not words:
        return []

    lines = _group_lines(words)
    bucketed_lines = [_bucket_line(l) for l in lines]
    anchor_idx = [i for i, b in enumerate(bucketed_lines) if _is_anchor(b)]
    if not anchor_idx:
        return []

    records: list[dict] = []
    for k, i in enumerate(anchor_idx):
        row = dict(bucketed_lines[i])
        this_top = lines[i]["top"]
        prev_top = lines[anchor_idx[k - 1]]["top"] if k > 0 else -1e9
        next_top = lines[anchor_idx[k + 1]]["top"] if k + 1 < len(anchor_idx) else 1e9

        lo = anchor_idx[k - 1] + 1 if k > 0 else 0
        hi = anchor_idx[k + 1] if k + 1 < len(anchor_idx) else len(lines)

        pre_words: list[str] = []
        post_words: list[str] = []
        trail: list[str] = []
        for j in range(lo, hi):
            if j == i:
                continue
            b = bucketed_lines[j]
            other_cols = [b[f] for f in _FIELDS if f != "DESCRIPTION" and b[f]]
            if other_cols:
                # A word landed outside the DESCRIPTION column's own
                # x-range on a non-anchor line -- not a description
                # continuation. Never guess: keep it verbatim, don't merge.
                trail.append(" ".join(other_cols))
                continue
            if not b["DESCRIPTION"]:
                continue
            gtop = lines[j]["top"]
            dist_prev = abs(gtop - prev_top)
            dist_next = abs(gtop - next_top)
            dist_this = abs(gtop - this_top)
            min_dist = min(dist_prev, dist_this, dist_next)
            this_is_nearest = abs(dist_this - min_dist) < 1e-6
            tie = this_is_nearest and (
                abs(dist_prev - min_dist) < 1e-6 or abs(dist_next - min_dist) < 1e-6
            )
            if tie:
                # Equidistant between this anchor and a neighbour --
                # genuinely ambiguous which row it belongs to. Fold
                # verbatim rather than guess (each tied anchor folds its
                # own copy independently; nothing is silently dropped).
                trail.append(b["DESCRIPTION"])
            elif this_is_nearest:
                if gtop < this_top:
                    pre_words.append(b["DESCRIPTION"])
                else:
                    post_words.append(b["DESCRIPTION"])
            # else: nearer a neighbouring anchor -- that anchor's own pass
            # over this same gap will claim it; skip silently here rather
            # than duplicating it onto this row's STATUS_TRAIL.

        if pre_words or post_words:
            row["DESCRIPTION"] = " ".join(
                pre_words + ([row["DESCRIPTION"]] if row["DESCRIPTION"] else []) + post_words
            ).strip()
        row["STATUS_TRAIL"] = " | ".join(t for t in trail if t)
        records.append(row)
    return records


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        if not pdf.pages:
            return records
        report_date = ""
        head_text = pdf.pages[0].extract_text() or ""
        m = _REPORT_DATE_RE.search(head_text)
        if m:
            report_date = m.group(1)
        for page_num, page in enumerate(pdf.pages, start=1):
            for row in _extract_page(page):
                row["REPORT_DATE"] = report_date
                row["_page"] = page_num
                records.append(row)
    return records
