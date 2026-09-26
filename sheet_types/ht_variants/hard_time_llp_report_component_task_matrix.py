"""Hard Time/LLP Report -- ATA-chapter-grouped component/task matrix.

Header (one block per page, repeated)::

    Aircraft: <TAIL>MSN: <MSN>
    Hard Time/LLP Report
    TSN:<total TSN> CSN:<total CSN>
    Status Date
    <DD-Mon-YYYY> INTERVAL REMAINING
    PN SN DESCRIPTION POS Inst Date TSN CSN TASK DESCRIPTION FH FC Days FH FC Days

Body rows are grouped under a bare ATA-chapter number printed alone on its
own line (e.g. a lone "21", then every component under that chapter, then a
lone "23", and so on) -- there is no repeated ATA cell on each component row
itself, so the running chapter number has to be tracked line-by-line.

Row example (single physical line, the common case)::

    VFT210B00 06312 SKIN AIR INLET VALVE ONLY-15HQ 21-Feb-14 2849416078VALVE-OVERHAUL 15000 3650 6735 2642

which is PN, SN, DESCRIPTION, POS, Inst Date, then TSN/CSN glued together
with no separating space (here "28494"+"16078"), then the TASK glued
straight onto CSN too, then up to 6 trailing numeric cells: INTERVAL
FH/FC/Days and REMAINING FH/FC/Days (most rows populate only 2-4 of the 6).

A component may carry more than one applicable task; every task after the
first prints as its own continuation line with no PN/SN/etc repeated, only
the TASK text and its own trailing numeric cells, e.g.::

    AD-2758 507429 MAIN BATTERY 1-2PB1 09-Sep-16 2061 1161 BATTERY-OVERHAUL 365 26
    BATTERY-PERIODICAL_CHECK 1000 456
    BATTERY-REGULAR_CHECK 2000 1456

Each such line becomes its own record, with the component's identity fields
copied onto it -- collapsing them into the anchor row would silently drop
whichever task lost the merge.

Column split strategy: pdfplumber's own word merging cannot be trusted for
this layout -- TSN and CSN are only ever separated by a couple of points of
whitespace when both are near their column's full width, and TASK almost
always sits flush against CSN with none at all, so `extract_words()` fuses
"<TSN><CSN><TASK>[<glued INTERVAL FH digits>]" into a single token on most
rows (e.g. "2849416078VALVE-OVERHAUL", or with a trailing interval glued on
too: "...FUNCTIONAL_CHECK9000"). Every column boundary up to and including
CSN's own right edge lands at an exact, fixed x0 (confirmed against the
header word positions on every page checked), so PN/SN/DESCRIPTION/POS/
INSTALL_DATE/TSN/CSN are all read directly off `page.chars` by x0 band
rather than off words at all -- this also transparently fixes the rarer case
of SN itself running into DESCRIPTION with no gap (e.g.
"0753C00ES006619PRIMARY" splits cleanly into SN "0753C00ES006619" and the
first DESCRIPTION word "PRIMARY").

TASK and the 6 trailing INTERVAL/REMAINING numeric cells are read off
`extract_words()` instead, since those columns are genuinely space-separated
almost everywhere and gap-based word splitting is what recovers multi-word
TASK text correctly (e.g. "LH M.L.G. SIDE STAY COMPLETE-(FIN : MLG-LH)
(OVERHAUL)"). The one place this needs a fallback: a handful of rows (all on
one page in the sample, all long "...-(FIN : ...)(OVERHAUL)"-style TASK
text) print with the leading INTERVAL-FH digits interleaved character-by-
character with the tail of the TASK text itself -- not merely touching, but
actually overlapping in x0/x1 (confirmed on real chars: a digit's x0 sits
*before* the previous letter's x1), which is a rendering artifact in the
source file, not a parsing choice. Plain word splitting can't recover either
string from that. The fix: detect a word whose own characters contain such
an overlap between a digit and a non-digit, and only then re-partition that
one word's characters into two interleaved-but-individually-monotonic
streams -- all digit characters in their own x0 order, all non-digit
characters in their own x0 order -- which cleanly recovers both the TASK
text tail and the glued numeric value (always the leftmost/INTERVAL_FH
cell, since gluing only ever happens against the column immediately right
of TASK; if that cell were blank there would be nothing there to overlap
with). A word with a single incidental digit in otherwise normal text (e.g.
a POS-style fragment such as "3FN)(CALIBRATIONS)" quoted inside a TASK
string) never exhibits this x-overlap, so it is left untouched.

The 6 trailing numeric cells, when they arrive as their own clean words, are
matched to INTERVAL_FH/FC/DAYS and REMAINING_FH/FC/DAYS by nearest right
edge (x1) against the 6 fixed target positions read off the header -- most
rows populate only 2-4 of the 6, never all six in the sample checked.

Corpus: a single real file confirmed so far, 5 pages, born-digital text
layer, this exact three-line title block ("Aircraft: ...MSN: ...", "Hard
Time/LLP Report", "TSN:...CSN:...") on every page.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.ht_variants._base import merged_rules

NAME = "Hard Time/LLP Report (Component Task Matrix)"
SIGNATURES = [
    "Hard Time/LLP Report",
    "PN SN DESCRIPTION POS Inst Date TSN CSN TASK DESCRIPTION",
]
CANONICAL_COLUMNS = [
    "ATA",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "DESCRIPTION",
    "POSITION",
    "INSTALLED_DATE",
    "TSN",
    "CSN",
    "TASK",
    "INTERVAL_FH",
    "INTERVAL_FC",
    "INTERVAL_DAYS",
    "REMAINING_FH",
    "REMAINING_FC",
    "REMAINING_DAYS",
]
_OVERRIDES = {
    "SERIAL_NUMBER":    {"allow_empty": True},
    "DESCRIPTION":      {"allow_empty": True},
    "POSITION":         {"allow_empty": True, "uppercase": True},
    "INSTALLED_DATE":   {"allow_empty": True},
    "TSN":              {"pattern": r"^\d*$", "allow_empty": True},
    "CSN":              {"pattern": r"^\d*$", "allow_empty": True},
    "TASK":             {"allow_empty": True},
    "INTERVAL_FH":      {"pattern": r"^\d*$", "allow_empty": True},
    "INTERVAL_FC":      {"pattern": r"^\d*$", "allow_empty": True},
    "INTERVAL_DAYS":    {"pattern": r"^\d*$", "allow_empty": True},
    "REMAINING_FH":      {"pattern": r"^\d*$", "allow_empty": True},
    "REMAINING_FC":      {"pattern": r"^\d*$", "allow_empty": True},
    "REMAINING_DAYS":    {"pattern": r"^\d*$", "allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Fixed x0 column bands for the left-hand identity fields, read directly off
# `page.chars` (NOT words -- see module docstring for why). Confirmed exact
# against the header word x0 positions on every page checked.
_PN_COL = (0, 89)
_SN_COL = (89, 150)
_DESC_COL = (150, 336)
_POS_COL = (336, 405)
_DATE_COL = (405, 442)
_TSN_COL = (442, 464)
_CSN_COL = (464, 486)
_TASK_ZONE_START = 486

# Header column line's own top on every page checked; real data never
# starts above this (also drops the repeated header line itself, whose own
# words would otherwise land inside these same bands).
_HEADER_BOTTOM = 120

# Nearest-right-edge (x1) targets for the 6 trailing INTERVAL/REMAINING
# numeric cells, read off the header word positions.
_NUMERIC_TARGETS = [
    ("INTERVAL_FH", 675),
    ("INTERVAL_FC", 697),
    ("INTERVAL_DAYS", 718),
    ("REMAINING_FH", 740),
    ("REMAINING_FC", 762),
    ("REMAINING_DAYS", 784),
]

_ATA_MARKER_RE = re.compile(r"^\d{1,3}$")
_FOOTER_RE = re.compile(r"^\d+\s+of\s+\d+$", re.IGNORECASE)


_GAP_THRESHOLD = 2.0  # points; comfortably above intra-word kerning (~0),
                       # comfortably below the smallest real inter-column
                       # gap seen in the sample (~4.4pt between adjacent
                       # populated numeric cells)


def _tokenize_chars(chars: list[dict]) -> list[list[dict]]:
    """Split a line's characters (already restricted to one x0 band, sorted
    by x0) into tokens. Used for the TASK + trailing-numeric zone instead of
    `extract_words()`, which would merge across the CSN/TASK column boundary
    (see module docstring) -- scoping tokenisation to chars already known to
    sit at x0 >= _TASK_ZONE_START sidesteps that merge entirely, since the
    CSN digits it would otherwise fuse with never enter this char list at
    all.

    A token boundary is either a real space character (real multi-word TASK
    text, e.g. "LH M.L.G. SIDE STAY ...") or a physical x-gap between
    consecutive characters with no space glyph at all (the normal case
    between TASK and the first numeric cell, and between adjacent numeric
    cells -- this source PDF places no space character in the content
    stream at those column boundaries, just a wide blank run). Intra-word
    kerning gaps (digits, hyphenated PNs, etc.) never come close to the
    threshold used here."""
    ordered = sorted(chars, key=lambda c: c["x0"])
    tokens: list[list[dict]] = []
    current: list[dict] = []
    prev_x1: float | None = None
    for c in ordered:
        if c["text"].isspace():
            if current:
                tokens.append(current)
                current = []
            prev_x1 = None
            continue
        if current and prev_x1 is not None and c["x0"] - prev_x1 > _GAP_THRESHOLD:
            tokens.append(current)
            current = []
        current.append(c)
        prev_x1 = c["x1"]
    if current:
        tokens.append(current)
    return tokens


def _group_lines_chars(chars: list[dict], y_tol: float = 2.0) -> list[list[dict]]:
    chars = sorted(chars, key=lambda c: (c["top"], c["x0"]))
    lines: list[list[dict]] = []
    for c in chars:
        if lines and abs(c["top"] - lines[-1][0]["top"]) <= y_tol:
            lines[-1].append(c)
        else:
            lines.append([c])
    return lines


def _band_text(chars: list[dict], band: tuple[float, float]) -> str:
    lo, hi = band
    picked = sorted((c for c in chars if lo <= c["x0"] < hi), key=lambda c: c["x0"])
    return "".join(c["text"] for c in picked)


_OVERLAP_MARGIN = 0.5  # points; comfortably above ordinary sub-point
                       # kerning/rounding noise between two adjacent glyphs
                       # (seen up to ~0.1pt on genuinely single-run text,
                       # e.g. a digit immediately followed by a letter in a
                       # legitimate token like "3FN)(CALIBRATIONS)"), and
                       # comfortably below the smallest genuine interleaved
                       # overlap seen in the sample (~1.3pt)


def _has_digit_overlap(ordered_chars: list[dict]) -> bool:
    """True if this token's own characters (already x0-sorted) contain a
    digit/non-digit pair whose x-ranges actually overlap by more than
    ordinary kerning noise (a later char's x0 sits well before an earlier
    char's x1) -- confirmed, on a real sample of this corpus, to be a
    source-PDF rendering artifact: a numeric cell's digits drawn
    interleaved with the tail of the TASK text, not merely touching it (see
    module docstring). Ordinary mixed alnum text (e.g. a POS fragment
    quoted inside a TASK string) never overlaps by this much."""
    for i in range(1, len(ordered_chars)):
        prev, cur = ordered_chars[i - 1], ordered_chars[i]
        if (cur["x0"] < prev["x1"] - _OVERLAP_MARGIN
                and prev["text"].isdigit() != cur["text"].isdigit()):
            return True
    return False


def _split_glued_token(ordered_chars: list[dict]) -> tuple[str, list[dict]]:
    """Split one token's x0-sorted characters into (task_text, digit_chars)
    -- the glued numeric value's own characters, kept (not just joined)
    so the caller can read their x1 for column matching.

    Two source shapes, both seen in the sample: characters that merely
    touch with no gap at all (e.g. "...FUNCTIONAL_CHECK2190", where a plain
    trailing digit run can just be sliced off the x0-sorted end), and
    characters that actually overlap in x -- interleaved digit-by-digit
    with the last word of the TASK text (e.g. "...(OVERHA2U0L0)00"). The
    first case is handled by peeling a plain trailing run of digit
    characters; the second needs `_has_digit_overlap` to detect it and a
    full class split (all digit characters in their own x0 order, all
    non-digit characters in their own x0 order) to recover both strings,
    since neither is a clean prefix/suffix of the raw character order."""
    if _has_digit_overlap(ordered_chars):
        digit_chars = [c for c in ordered_chars if c["text"].isdigit()]
        rest = "".join(c["text"] for c in ordered_chars if not c["text"].isdigit())
        return rest, digit_chars
    i = len(ordered_chars)
    while i > 0 and ordered_chars[i - 1]["text"].isdigit():
        i -= 1
    digit_chars = ordered_chars[i:]
    rest = "".join(c["text"] for c in ordered_chars[:i])
    return rest, digit_chars


def _nearest_target(x1: float) -> str:
    return min(_NUMERIC_TARGETS, key=lambda t: abs(t[1] - x1))[0]


def _parse_task_zone(tokens: list[list[dict]]) -> dict:
    """`tokens` are this line's TASK-zone tokens (chars with x0 >=
    _TASK_ZONE_START, split on real space characters -- see
    `_tokenize_chars`), in left-to-right order."""
    desc_parts: list[str] = []
    values: dict[str, str] = {}
    for tok_chars in tokens:
        ordered = sorted(tok_chars, key=lambda c: c["x0"])
        text = "".join(c["text"] for c in ordered)
        if text.replace(",", "").isdigit():
            values[_nearest_target(max(c["x1"] for c in ordered))] = text.replace(",", "")
            continue
        if any(ch.isdigit() for ch in text):
            rest, digit_chars = _split_glued_token(ordered)
            if digit_chars:
                if rest:
                    desc_parts.append(rest)
                digits = "".join(c["text"] for c in digit_chars)
                # Match by the digit characters' own x1, exactly like a
                # clean standalone numeric token -- which numeric column
                # this is depends on which cell is actually populated for
                # this task (some are FH+Days, some FC+Days, etc; see
                # module docstring), not on gluing having happened at all.
                digit_x1 = max(c["x1"] for c in digit_chars)
                values.setdefault(_nearest_target(digit_x1), digits)
                continue
            # Mixed alnum with no separable trailing/overlapping digit run
            # (e.g. a POS fragment quoted inside a TASK string) -- genuine
            # text, left untouched.
        desc_parts.append(text)
    return {
        "TASK": " ".join(p for p in desc_parts if p),
        **values,
    }


def _line_tokens(cline: list[dict], band: tuple[float, float]) -> list[list[dict]]:
    lo, hi = band
    return _tokenize_chars([c for c in cline if lo <= c["x0"] < hi])


def _parse_page(page, page_num: int, state: dict) -> list[dict]:
    """`state` carries `current_ata` / `current_identity` across pages --
    an ATA chapter's rows (and, in principle, a component's own task
    continuation lines) are not guaranteed to fit on one page, and neither
    the chapter marker nor the component's identity row repeats after a
    page break in the sample file."""
    all_chars = [c for c in page.chars if c["top"] >= _HEADER_BOTTOM]
    char_lines = _group_lines_chars(all_chars)

    records: list[dict] = []
    current_ata = state["current_ata"]
    current_identity = state["current_identity"]

    for cline in char_lines:
        pn_tokens = _line_tokens(cline, _PN_COL)
        task_tokens = _line_tokens(cline, (_TASK_ZONE_START, float("inf")))
        all_tokens = _tokenize_chars(cline)

        full_text = " ".join("".join(c["text"] for c in tok) for tok in all_tokens)
        if _FOOTER_RE.match(full_text.strip()):
            continue
        if len(all_tokens) == 1 and pn_tokens and _ATA_MARKER_RE.match(full_text.strip()):
            current_ata = full_text.strip()
            continue

        pn = "".join(c["text"] for tok in pn_tokens for c in tok)

        if pn:
            # Anchor row: a new component.
            sn = _band_text(cline, _SN_COL).strip()
            desc = _band_text(cline, _DESC_COL).strip()
            pos = _band_text(cline, _POS_COL).strip()
            inst_date = _band_text(cline, _DATE_COL).strip()
            tsn = _band_text(cline, _TSN_COL).strip()
            csn = _band_text(cline, _CSN_COL).strip()
            current_identity = {
                "ATA": current_ata,
                "PART_NUMBER": pn,
                "SERIAL_NUMBER": sn,
                "DESCRIPTION": desc,
                "POSITION": pos,
                "INSTALLED_DATE": inst_date,
                "TSN": tsn,
                "CSN": csn,
            }
            if not task_tokens:
                continue
        elif not task_tokens:
            continue
        elif current_identity is None:
            continue  # continuation task line with no anchor seen yet; nothing to attach it to

        task_fields = _parse_task_zone(task_tokens)
        record = {
            **current_identity,
            "TASK": task_fields.pop("TASK"),
            "INTERVAL_FH": "",
            "INTERVAL_FC": "",
            "INTERVAL_DAYS": "",
            "REMAINING_FH": "",
            "REMAINING_FC": "",
            "REMAINING_DAYS": "",
            **task_fields,
            "_page": page_num,
        }
        records.append(record)
    state["current_ata"] = current_ata
    state["current_identity"] = current_identity
    return records


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    state = {"current_ata": "", "current_identity": None}
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            records.extend(_parse_page(page, page_num, state))
    return records
