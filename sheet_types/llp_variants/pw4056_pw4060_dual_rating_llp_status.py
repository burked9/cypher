"""Pratt & Whitney "Life Limited Parts Status" report for a dual-rated
PW4056/PW4060 engine — a single-page, flattened/rasterized scan (confirmed:
0-character text layer, and the page decomposes into dozens of tiled JPEG
images with zero vector drawings, i.e. a genuine scanned/rasterized
document, not a born-digital table with an embedded font). Because this
engine can be operated under either of two related type ratings, every part
row tracks its accumulated cycles/limit/remaining life TWICE — once per
rating (<rating_a> / <rating_b>) — side by side, rather than once.

Header block (illustrative placeholders only, no real file's values)::

    Manufacturer          <manufacturer>          Received <date>  Current   Date of report: <date>
    Engine P/N            <engine_pn>              TSN <received_tsn> <current_tsn>  TSO <tso>   Reason
    Engine S/N            <esn>                    CSN <received_csn> <current_csn>  CSO <cso>   <reason text>

Body is a single ruled table with 11 columns (confirmed directly by
numpy grid-line detection on the rendered page — the dense run of
closely-spaced horizontal rules that make up the table divides into
exactly 12 vertical rules, i.e. 11 columns, every time this format has been
inspected): Description, Part Number, Serial Number, TSN, CSN, Acc.Cycle
<rating_a>, Acc.Cycle <rating_b>, Time Limit <rating_a>, Time Limit
<rating_b>, Current Remaining <rating_a>, Current Remaining <rating_b>.

Two non-part row shapes share that same grid, both forward-filled onto the
part rows beneath them rather than emitted as their own output row (mirrors
how powerplant_maintenance_center_llp_status.py forward-fills its own
MODULE_NAME/CODE/TSN/CSN/TSO/CSO onto every row of a module section, and
egat_llp_on_log_list.py's MODULE_GROUP propagation):

  - A MODULE header, printed as a 2-row pair: row 1 carries the module's own
    short code (e.g. an illustrative "LPC"/"HPC"/"HPT"/"LPT"/"AGB"/"MGB"),
    the module assembly's own Part Number/Serial Number, its running TSN/CSN,
    the literal label "TSO" in the Acc.Cycle-<rating_a> column and the
    module's TSO figure in the Acc.Cycle-<rating_b> column (all four
    Time-Limit/Current-Remaining cells read "N/A" — a module assembly has no
    single life limit of its own); row 2 repeats that shape with "CSO" in
    place of "TSO". Detected structurally, not by hardcoding the 6 module
    codes: whichever row has a non-empty Description AND its Acc.Cycle-
    <rating_a> cell reads "TSO" is a module-header row, full stop — this
    generalises to a 7th/8th module code appearing in some other file of
    this family without code changes here.
  - A bare sub-header row, e.g. an illustrative "LPC/LPT Coupling" line with
    every other cell blank — forward-filled onto subsequent rows as GROUP,
    reset to "" at the start of each new MODULE_NAME.

Grid detection: full-width row darkness -> longest dense run of closely
spaced horizontal rules is the table band (same `_longest_dense_run`
strategy part_m_engine_disk_sheet.py uses to separate the table from the
sparser-ruled header info-box above it) -> vertical rules detected within
that band. The column-line merge distance needed tuning up from that
module's 15px default to 60px on this file: at 15px, one extra spurious
vertical rule (~45-70px inside the true Time-Limit-<rating_a> column,
confirmed by direct pixel inspection to be scan/compression noise, not a
real second rule) survives and the resulting 13-line grid fails the
required-column-count gate every time; 60px still keeps every pair of
genuinely distinct columns apart (the narrowest real gap between two
column rules on this file is ~135px) while merging that one noise line
away, and was confirmed to always yield exactly 12 rules (11 columns).

Two OCR reliability findings, confirmed directly against the rendered page
(not assumed):

  1. Whole-row OCR (one wide strip per row, column dividers painted out,
     words bucketed back to columns by x-position — the same technique
     part_m_engine_disk_sheet.py's `_ocr_row_bucketed` uses, and for the
     same reason: cropping each of the 11 columns separately starves
     Tesseract of the row context it needs) reads every genuine PART row on
     this file's sample cleanly. But a module header's *second* (CSO) row —
     five blank cells, then "CSO", then one number, then four "N/A"s — comes
     back as unrecoverable garbage on 3 of the 6 module sections' CSO rows
     every time, confirmed reproducible across repeated runs and several
     PSM values; the other 3 module sections' CSO rows read cleanly by the
     exact same method. No pattern was found in *which* 3 fail. Rather than
     trust a flaky whole-row read for a row shape we already know the exact
     structure of, the CSO/TSO-label cell and its numeric neighbour are
     re-cropped and OCR'd individually (2 small crops instead of trusting
     the wide-strip bucket for just this one row shape) — confirmed to read
     cleanly every time on every module section once done this way.
  2. The footnote-reference asterisk(s) some rows print just to the right
     of the table's own right border (outside the ruled grid entirely) are
     too small for Tesseract to recognise at all — every PSM tried returns
     either nothing or an unrelated 2-3 letter fragment on a crop that a
     direct pixel check confirms does contain ink. Detected by dark-pixel
     count in that margin strip instead: none -> no footnote; a low count
     (a single glyph's worth) -> "*"; roughly triple that (two glyphs) ->
     "**". The two thresholds were read directly off this file's own
     asterisk/double-asterisk rows, not guessed.

Digit/thousands-separator noise: some numeric cells OCR a comma thousands
separator as a period (e.g. a real "9,114" misread as "9.114" — confirmed
directly against several such cells on this file). No bespoke
comma-reconstruction is added for this here: shared/cleanup.py's
`_parse_thousands_int` (used by every `int_range` check via `clean_record`)
already tolerates comma, period, OR apostrophe thousands grouping
by design (see iai_dual_rating_engine_llp.py's docstring for the same
precedent) — this file's noise pattern falls squarely inside that existing
tolerance, so the raw OCR'd string is kept as printed (dot and all) and
validated through the shared parser rather than rewritten here. This is a
different noise pattern from powerplant_maintenance_center_llp_status.py's
(a thousands number split across two whitespace-tokens by pdfplumber) —
no token-merging is needed on this file since the grid gives each cell its
own crop; a stray-separator misread within one otherwise-intact cell is all
that's been observed.

Per this project's "never guess a wrong split" convention: every one of the
11 body columns is already given its own crop by the ruled grid, so there
is no free-text token count to guess at like several sibling variants face.
The one remaining defensive case — any cell in the 8 numeric-ish columns
that, after cleanup, is neither blank, "N/A", nor a plain thousands-grouped
number — is not force-fit into a named column; the whole raw 8-cell block
for that row is kept verbatim in STATUS_TRAIL instead and the 8 named
fields are left blank, mirroring the STATUS_TRAIL convention used by
cf34_life_limited_major_component.py and lan_engine_control_fleet_llp.py.
On the sample file this defensive path never actually triggers (every
PART row's 8-cell numeric block already parses cleanly), but it stays in
as a safety net rather than blind trust in the grid-based split holding on
every future file of this family.

A trailing "1st Limiter" summary line sits below the last module's CSO row,
only spanning the Time-Limit-<rating_b>/Current-Remaining-<rating_a>/
Current-Remaining-<rating_b> columns (its label cell reads "1st Limiter",
confirmed as a whole-document summary of whichever single part is closest
to its life limit under each rating, not a part row itself) — captured
once and stamped as FIRST_LIMITER_REMAINING_<rating_a>/<rating_b> metadata
on every row, the same way the rest of the header block is.
"""
from __future__ import annotations

import re

import numpy as np
from PIL import ImageDraw

from sheet_types.llp_variants._base import merged_rules
from shared.ocr_bridge import render_page, ocr_text, ocr_words

NAME = "PW4056/PW4060 Dual-Rating LLP Status"

# The known source file has a genuinely empty (0-character) text layer, so
# this will never actually fire through the router's ordinary text-signature
# match -- present only for interface consistency with every other variant
# module (mirrors part_m_engine_disk_sheet.py's own comment on this point).
# Real detection happens via ocr_detect() below. Deliberately NOT added to
# sheet_types/llp.py's top-level SIGNATURES list: with no text layer at all
# (unlike iai_dual_rating_engine_llp.py's second known file, which carries a
# garbled-but-present embedded text layer), a text-substring entry there
# could never be reached anyway.
SIGNATURES = [
    "LIFE LIMITED PARTS STATUS",
]

CANONICAL_COLUMNS = [
    "MODULE_NAME",
    "GROUP",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "TSN",
    "CSN",
    "ACC_CYCLE_PW4056",
    "ACC_CYCLE_PW4060",
    "TIME_LIMIT_PW4056",
    "TIME_LIMIT_PW4060",
    "CURRENT_REMAINING_PW4056",
    "CURRENT_REMAINING_PW4060",
    "FOOTNOTE",
    "FOOTNOTE_TEXT",
    "STATUS_TRAIL",
    # Module-header (2-row-pair) metadata -- forward-filled per section.
    "MODULE_PART_NUMBER",
    "MODULE_SERIAL_NUMBER",
    "MODULE_TSN",
    "MODULE_CSN",
    "MODULE_TSO",
    "MODULE_CSO",
    # File-level metadata -- same on every row of a given file.
    "MANUFACTURER",
    "ENGINE_PART_NUMBER",
    "ENGINE_SERIAL_NUMBER",
    "RECEIVED_DATE",
    "REPORT_DATE",
    "ENGINE_TSN_RECEIVED",
    "ENGINE_TSN_CURRENT",
    "ENGINE_CSN_RECEIVED",
    "ENGINE_CSN_CURRENT",
    "ENGINE_TSO",
    "ENGINE_CSO",
    "REASON",
    "PREPARED_BY",
    "FIRST_LIMITER_REMAINING_PW4056",
    "FIRST_LIMITER_REMAINING_PW4060",
]

_CYCLE_RULE = {"pattern": r"^(N/A|[\d,.']+)$", "int_range": (0, 100000),
                # PW4056/4060 power widebody airframes -- real engine-level
                # TSN on the one known source file legitimately exceeds
                # 60,000 hours, well above a typical regional-engine review
                # band; 60,000 (copied from a smaller-engine sibling module)
                # flagged essentially every row on this file for no reason.
                "int_range_review": (0, 90000), "allow_empty": True}
_NUMERIC_COLS = [
    "TSN", "CSN", "ACC_CYCLE_PW4056", "ACC_CYCLE_PW4060",
    "TIME_LIMIT_PW4056", "TIME_LIMIT_PW4060",
    "CURRENT_REMAINING_PW4056", "CURRENT_REMAINING_PW4060",
    "MODULE_TSN", "MODULE_CSN", "MODULE_TSO", "MODULE_CSO",
    "ENGINE_TSN_RECEIVED", "ENGINE_TSN_CURRENT",
    "ENGINE_CSN_RECEIVED", "ENGINE_CSN_CURRENT",
    "ENGINE_TSO", "ENGINE_CSO",
    "FIRST_LIMITER_REMAINING_PW4056", "FIRST_LIMITER_REMAINING_PW4060",
]
_OVERRIDES = {c: _CYCLE_RULE for c in _NUMERIC_COLS}
_OVERRIDES.update({
    "MODULE_NAME":    {"pattern": r"^[A-Z0-9/ ]*$", "uppercase": True, "allow_empty": True},
    "GROUP":          {"allow_empty": True},
    "FOOTNOTE":       {"pattern": r"^\*{0,2}$", "allow_empty": True},
    "FOOTNOTE_TEXT":  {"allow_empty": True},
    "STATUS_TRAIL":   {"allow_empty": True},
    "MODULE_PART_NUMBER":   {"allow_empty": True},
    "MODULE_SERIAL_NUMBER": {"allow_empty": True},
    "MANUFACTURER":         {"allow_empty": True},
    "ENGINE_PART_NUMBER":   {"pattern": r"^[A-Z0-9\-]*$", "uppercase": True, "allow_empty": True},
    "ENGINE_SERIAL_NUMBER": {"allow_empty": True},
    "RECEIVED_DATE":        {"allow_empty": True},
    "REPORT_DATE":          {"allow_empty": True},
    "REASON":               {"allow_empty": True},
    "PREPARED_BY":          {"allow_empty": True},
})
RULES = merged_rules(_OVERRIDES)

_DPI = 300
_DARK_THRESHOLD = 180  # gray<128 (part_m_engine_disk_sheet.py's own threshold)
                       # missed real rules on this file's noisier scan/JPEG-
                       # tile compression; 180 was confirmed (by direct
                       # pixel inspection) to catch every real rule on this
                       # file without picking up stray anti-aliasing noise.


async def _render_page0(pdf_path: str, dpi: int = _DPI):
    return await render_page(pdf_path, 0, dpi=dpi)


def _collapse_and_dedup(idx: np.ndarray, merge_dist: int = 15) -> list[int]:
    """Collapse a run of adjacent dark rows/cols into one line position, then
    merge lines still within `merge_dist` px of each other. See
    part_m_engine_disk_sheet.py for the original version of this helper;
    unchanged here except for the tunable `merge_dist` (this file's own
    vertical-rule detection needs 60px -- see module docstring)."""
    if len(idx) == 0:
        return []
    out, run = [], [int(idx[0])]
    for i in idx[1:]:
        if i - run[-1] <= 3:
            run.append(int(i))
        else:
            out.append(int(np.mean(run)))
            run = [int(i)]
    out.append(int(np.mean(run)))
    merged = [out[0]]
    for x in out[1:]:
        if x - merged[-1] <= merge_dist:
            merged[-1] = int((merged[-1] + x) / 2)
        else:
            merged.append(x)
    return merged


def _longest_dense_run(lines: list[int], max_gap: int = 100, min_run: int = 10) -> tuple[int, int] | None:
    """Same strategy as part_m_engine_disk_sheet.py's helper of the same
    name: the data table is a dense run of closely-spaced ruled lines,
    distinguishable from the sparser rules in the header info-box above it
    by the size of the gaps between consecutive lines."""
    if len(lines) < min_run:
        return None
    gaps = [b - a for a, b in zip(lines[:-1], lines[1:])]
    best_start, best_len, cur_start, cur_len = 0, 0, 0, 0
    for i, g in enumerate(gaps):
        if g < max_gap:
            if cur_len == 0:
                cur_start = i
            cur_len += 1
        else:
            if cur_len > best_len:
                best_start, best_len = cur_start, cur_len
            cur_len = 0
    if cur_len > best_len:
        best_start, best_len = cur_start, cur_len
    if best_len < min_run:
        return None
    return lines[best_start], lines[best_start + best_len]


def _detect_table_grid(gray: np.ndarray) -> tuple[list[int], list[int]] | None:
    dark = gray < _DARK_THRESHOLD
    full_h_lines = _collapse_and_dedup(np.where(dark.mean(axis=1) > 0.4)[0])
    band = _longest_dense_run(full_h_lines)
    if band is None:
        return None
    y0, y1 = band
    v_lines = _collapse_and_dedup(np.where(dark[y0:y1, :].mean(axis=0) > 0.5)[0], merge_dist=60)
    if len(v_lines) != 12:
        # 11 data columns -> 12 dividing rules, always (confirmed on the
        # known source file). Anything else means grid detection latched
        # onto the wrong region or a spurious/missed rule slipped through,
        # and every downstream column boundary would be garbage.
        return None
    h_lines = _collapse_and_dedup(np.where(dark[:, v_lines[0]:v_lines[-1]].mean(axis=1) > 0.5)[0])
    h_lines = [y for y in h_lines if y0 - 5 <= y <= y1 + 5]
    return v_lines, h_lines


_LEAD_JUNK_RE = re.compile(r"^[^A-Za-z0-9]+")


def _clean_text(raw: str) -> str:
    """Post-OCR cleanup for a description/PN/SN cell: strip the leading
    stray symbol (a lone "/", "!", "|", "\\" etc.) that column-divider
    paint-out bleed regularly leaves on the first character of a row's
    Description cell (confirmed against this file: e.g. an OCR read of
    "Drum Rotor" coming back as "/Drum Rotor"), but keep interior
    punctuation ("Disk Stg. 1.6", "Rotor Drum 6 - 12" are legitimate)."""
    s = raw.replace("|", "").strip()
    s = _LEAD_JUNK_RE.sub("", s)
    return re.sub(r"\s+", " ", s).strip()


_NUM_NOISE_RE = re.compile(r"^[|=~`'\";:_\-() ]+|[|=~`'\";:_\-() ]+$")


def _clean_value(raw: str) -> str:
    """Post-OCR cleanup for a numeric/label cell (TSN/CSN/Acc.Cycle/Time
    Limit/Current Remaining, or the "TSO"/"CSO" row-shape label). Strips
    gridline-bleed punctuation from the edges only (confirmed noise like
    "~=15,000"/"= 15,000"/"2279 =|" on this file's real cells) and
    normalises the "N/A" cells' many OCR variants to one literal spelling.
    Deliberately does NOT touch a comma/period thousands separator inside
    an otherwise-clean number -- see module docstring."""
    s = raw.strip()
    s = _NUM_NOISE_RE.sub("", s)
    upper = s.upper().replace(" ", "")
    if upper in ("N/A", "NA", "N/", "NIA", "NYA"):
        return "N/A"
    if upper in ("TSO", "CSO"):
        return upper
    return re.sub(r"(?<=\d)\s+(?=\d)", "", s)


_VALID_VALUE_RE = re.compile(r"^(N/A|\d[\d,.']*)$")


def _looks_valid(s: str) -> bool:
    return s == "" or bool(_VALID_VALUE_RE.match(s))


async def _ocr_row_bucketed(img, v_lines: list[int], ry0: int, ry1: int,
                             pad: int = 2, psm: int = 7) -> list[str]:
    """OCR one full row as a single wide strip (column dividers painted
    white first) and bucket recognised words into columns by known
    x-position -- same technique and same rationale as
    part_m_engine_disk_sheet.py's `_ocr_row_bucketed` (per-cell crops starve
    Tesseract of row context on this kind of scan); see that module's own
    docstring for the full explanation, unchanged here."""
    strip = img.crop((v_lines[0], ry0 + pad, v_lines[-1], ry1 - pad)).copy()
    draw = ImageDraw.Draw(strip)
    for x in v_lines[1:-1]:
        bar = x - v_lines[0]
        draw.rectangle([bar - 3, 0, bar + 3, strip.height], fill=(255, 255, 255))
    words = await ocr_words(strip, psm=psm, min_conf=-1)
    n_cols = len(v_lines) - 1
    buckets: list[list[tuple[int, str]]] = [[] for _ in range(n_cols)]
    for word in words:
        x_center = v_lines[0] + word["left"] + word["width"] / 2
        for i in range(n_cols):
            if v_lines[i] <= x_center < v_lines[i + 1]:
                buckets[i].append((int(word["left"]), str(word["text"])))
                break
    cells = []
    for bucket in buckets:
        bucket.sort(key=lambda t: t[0])
        cells.append(re.sub(r"\s+", " ", " ".join(t[1] for t in bucket)).strip())
    return cells


async def _ocr_module_second_row(img, v_lines: list[int], ry0: int, ry1: int) -> tuple[str, str]:
    """A module header's 2nd (CSO) row only ever has 2 non-blank cells
    (the "CSO" label and its numeric value) -- whole-row bucketed OCR
    unreliably garbles this exact shape on 3 of every 6 module sections
    (confirmed reproducible on the known source file; see module
    docstring), so these 2 cells are cropped and OCR'd individually
    instead of trusting the wide-strip read for this one row shape."""
    cell_label = img.crop((v_lines[5] + 2, ry0 + 2, v_lines[6] - 2, ry1 - 2))
    cell_val = img.crop((v_lines[6] + 2, ry0 + 2, v_lines[7] - 2, ry1 - 2))
    label = _clean_value((await ocr_text(cell_label, psm=7)).strip())
    val = _clean_value((await ocr_text(cell_val, psm=7)).strip())
    return label, val


async def _detect_footnote(img, x_right: int, ry0: int, ry1: int) -> str:
    """The footnote-reference asterisk(s) some rows print just past the
    table's own right border are too small for Tesseract to read reliably
    at any PSM tried (confirmed: every attempt returns nothing or an
    unrelated fragment on crops a direct pixel check confirms do contain
    ink) -- detected by dark-pixel count in that margin strip instead.

    A first version of this check (plain dark-pixel count in the strip)
    produced false positives on rows next to a module-section boundary:
    those rows carry a faint 1px-tall smear the full height of the crop
    (confirmed by inspecting the per-row-of-pixels profile directly), which
    a flat pixel-count threshold can't tell apart from a real asterisk glyph
    at the same total ink. The fix: only count pixel-rows with >=2 dark
    pixels (a real glyph's stroke is several pixels wide at any given
    height; the boundary smear is never more than 1px wide) -- confirmed
    directly this drops the smear's contribution to exactly zero on every
    known false-positive row while leaving every real asterisk/double-
    asterisk row's count essentially unchanged. The single-vs-double
    threshold (50) was read directly off this file's own known rows: single
    asterisks summed to ~32-35, the one double-asterisk row to ~66."""
    gray = np.array(img.convert("L").crop((x_right + 2, ry0, x_right + 45, ry1)))
    row_dark_counts = (gray < 150).sum(axis=1)
    strong = row_dark_counts[row_dark_counts >= 2]
    if strong.size == 0:
        return ""
    return "**" if int(strong.sum()) >= 50 else "*"


_MANUFACTURER_RE = re.compile(r"Manufacturer\s+(.+?)\s*\|", re.I)
_RECEIVED_RE = re.compile(r"Received\s+([\d.]+\.\w+\.\d{4}|\S+)", re.I)
_REPORT_DATE_RE = re.compile(r"Date of report\s*:?\s*([\d/\-.]+)", re.I)
_ENGINE_PN_RE = re.compile(r"Engine\s*P\s*/?\s*N\S*\s+(\S+)", re.I)
_ENGINE_SN_RE = re.compile(r"Engine\s*S\s*/?\s*N\S*\s+(\S+)", re.I)
_TSN_LABELED_RE = re.compile(r"TSN\s+([\d,.']+)\s+([\d,.']+)", re.I)
_TSN_POSITIONAL_RE = re.compile(r"Engine\s*P\s*/?\s*N\S*\s+\S+\s+([\d,.']+)\s+([\d,.']+)", re.I)
_CSN_LABELED_RE = re.compile(r"CSN\s+([\d,.']+)\s+([\d,.']+)", re.I)
_CSN_POSITIONAL_RE = re.compile(r"Engine\s*S\s*/?\s*N\S*\s+\S+\s+([\d,.']+)\s+([\d,.']+)", re.I)
_TSO_RE = re.compile(r"TSO\.?\s+([\d,.']+)", re.I)
_CSO_RE = re.compile(r"CSO\s+([\d,.']+)", re.I)
_REASON_LABEL_RE = re.compile(r"Reason", re.I)
_PREPARED_BY_RE = re.compile(r"Prepared By\s+(\S+\s+\S+)", re.I)
_FOOTNOTE1_RE = re.compile(r"(?<!\*)\*\s+(.+?)(?:\n|$)")
_FOOTNOTE2_RE = re.compile(r"\*\*\s*(.+)")


async def _parse_header_metadata(img) -> dict:
    """The Manufacturer/Engine-P-N/Engine-S-N/TSN/CSN/TSO/CSO/Received
    block is OCR'd as one wide crop and regex-parsed (labels sometimes drop
    out of the OCR entirely on this file -- e.g. "TSN"/"CSN" occasionally
    go missing while the numbers around them stay readable -- hence the
    positional fallback regexes alongside the labeled ones). The Date-of-
    report/Reason value sits far enough to the right, and close enough to
    an unrelated letterhead logo, that pulling it from the SAME wide crop
    regularly interleaves logo-OCR noise into the captured Reason text
    (confirmed directly); a second, narrower crop isolating just that
    right-hand block reads cleanly instead."""
    w, h = img.size
    meta: dict[str, str] = {}

    crop = img.crop((0, int(h * 0.03), w, int(h * 0.20)))
    text = await ocr_text(crop, psm=6)

    m = _MANUFACTURER_RE.search(text)
    if m:
        meta["MANUFACTURER"] = m.group(1).strip()
    m = _RECEIVED_RE.search(text)
    if m:
        meta["RECEIVED_DATE"] = m.group(1).strip()
    m = _ENGINE_PN_RE.search(text)
    if m:
        meta["ENGINE_PART_NUMBER"] = m.group(1).strip()
    m = _ENGINE_SN_RE.search(text)
    if m:
        meta["ENGINE_SERIAL_NUMBER"] = m.group(1).strip()
    m = _TSN_LABELED_RE.search(text) or _TSN_POSITIONAL_RE.search(text)
    if m:
        meta["ENGINE_TSN_RECEIVED"], meta["ENGINE_TSN_CURRENT"] = m.group(1), m.group(2)
    m = _CSN_LABELED_RE.search(text) or _CSN_POSITIONAL_RE.search(text)
    if m:
        meta["ENGINE_CSN_RECEIVED"], meta["ENGINE_CSN_CURRENT"] = m.group(1), m.group(2)
    m = _TSO_RE.search(text)
    if m:
        meta["ENGINE_TSO"] = m.group(1)
    m = _CSO_RE.search(text)
    if m:
        meta["ENGINE_CSO"] = m.group(1)

    # Narrower crop isolating "Date of report:"/"Reason" from the
    # letterhead logo sitting just to their left -- coordinates measured
    # against the rendered page (0.80-1.0 width, 0.105-0.143 height held
    # this block cleanly on the known source file), not guessed.
    reason_crop = img.crop((int(w * 0.80), int(h * 0.105), w, int(h * 0.143)))
    reason_text = await ocr_text(reason_crop, psm=6)
    m = _REPORT_DATE_RE.search(reason_text)
    if m:
        meta["REPORT_DATE"] = m.group(1).strip()
    rm = _REASON_LABEL_RE.search(reason_text)
    if rm:
        rest = reason_text[rm.end():].strip()
        if rest:
            meta["REASON"] = rest.splitlines()[0].strip()

    return meta


async def _parse_footnotes(img) -> dict:
    """Footnote reference text ("* <note>" / "** <note>") sits in the
    Prepared-By block at the foot of the page -- read once per file and
    matched back to each row's FOOTNOTE marker."""
    w, h = img.size
    crop = img.crop((0, int(h * 0.855), w, int(h * 0.95)))
    text = await ocr_text(crop, psm=6)
    out: dict[str, str] = {}
    m = _FOOTNOTE2_RE.search(text)
    if m:
        out["**"] = m.group(1).strip()
    m = _FOOTNOTE1_RE.search(text)
    if m:
        out["*"] = re.split(r"\*\*", m.group(1).strip())[0].strip()
    m = _PREPARED_BY_RE.search(text)
    if m:
        out["_prepared_by"] = m.group(1).strip()
    return out


async def _parse_first_limiter(img, v_lines: list[int], ry0: int) -> tuple[str, str]:
    """The trailing "1st Limiter" summary line has no bottom rule of its
    own across the columns it doesn't use (confirmed: it's why grid
    detection's row band ends at the line above it, not below) -- so its
    row height is assumed equal to a normal data row rather than detected,
    and only the 2 value cells this line actually carries are read."""
    ry1 = ry0 + 48
    c9 = img.crop((v_lines[9] + 2, ry0 + 2, v_lines[10] - 2, ry1 - 2))
    c10 = img.crop((v_lines[10] + 2, ry0 + 2, v_lines[11] - 2, ry1 - 2))
    v9 = _clean_value((await ocr_text(c9, psm=7)).strip())
    v10 = _clean_value((await ocr_text(c10, psm=7)).strip())
    return v9, v10


async def ocr_detect(pdf_path: str) -> bool:
    """Cheap header-only OCR check the router falls back to when a PDF has
    no usable text layer. Requires the report title AND both rating labels
    together, narrowing the match to this dual-rating template specifically
    rather than any single-rating sibling that might share the bare title
    phrase."""
    try:
        img = await _render_page0(pdf_path, dpi=_DPI)
        w, h = img.size
        crop = img.crop((0, int(h * 0.03), w, int(h * 0.20)))
        text = (await ocr_text(crop, psm=6)).upper()
        return "LIFE LIMITED PARTS STATUS" in text and "PW4056" in text and "PW4060" in text
    except Exception:
        return False


async def extract(pdf_path: str) -> list[dict]:
    img = await _render_page0(pdf_path, dpi=_DPI)
    gray = np.array(img.convert("L"))
    grid = _detect_table_grid(gray)
    if grid is None:
        return []
    v_lines, h_lines = grid

    meta = await _parse_header_metadata(img)
    footnotes = await _parse_footnotes(img)
    if "_prepared_by" in footnotes:
        meta["PREPARED_BY"] = footnotes["_prepared_by"]

    records: list[dict] = []
    current_module: dict[str, str] = {}
    current_group = ""
    i = 0
    n_rows = len(h_lines) - 1
    while i < n_rows:
        ry0, ry1 = h_lines[i], h_lines[i + 1]
        cells = await _ocr_row_bucketed(img, v_lines, ry0, ry1)
        desc = _clean_text(cells[0])
        col5 = _clean_value(cells[5])

        if desc and col5 == "TSO":
            # Module-header first (TSO) row -- look ahead one row for its
            # CSO partner (see module docstring for why that row is read
            # via targeted per-cell OCR rather than the usual bucketed read).
            module_cso = ""
            if i + 1 < n_rows:
                ry0b, ry1b = h_lines[i + 1], h_lines[i + 2]
                label2, val2 = await _ocr_module_second_row(img, v_lines, ry0b, ry1b)
                if label2 == "CSO":
                    module_cso = val2
                i += 1
            current_module = {
                "MODULE_NAME": desc,
                "MODULE_PART_NUMBER": _clean_text(cells[1]),
                "MODULE_SERIAL_NUMBER": _clean_text(cells[2]),
                "MODULE_TSN": _clean_value(cells[3]),
                "MODULE_CSN": _clean_value(cells[4]),
                "MODULE_TSO": _clean_value(cells[6]),
                "MODULE_CSO": module_cso,
            }
            current_group = ""
            i += 1
            continue

        if desc and all(not _clean_text(c) for c in cells[1:]):
            # Bare sub-header row (e.g. an illustrative "<module>/<module>
            # Coupling" line) -- forward-filled as GROUP, no data of its own.
            current_group = desc
            i += 1
            continue

        if not desc:
            i += 1
            continue

        vals = [_clean_value(c) for c in cells[3:11]]
        footnote = await _detect_footnote(img, v_lines[-1], ry0, ry1)

        rec = {c: "" for c in CANONICAL_COLUMNS}
        rec.update(current_module)
        rec["GROUP"] = current_group
        rec["DESCRIPTION"] = desc
        rec["PART_NUMBER"] = _clean_text(cells[1])
        rec["SERIAL_NUMBER"] = _clean_text(cells[2])

        numeric_names = [
            "TSN", "CSN", "ACC_CYCLE_PW4056", "ACC_CYCLE_PW4060",
            "TIME_LIMIT_PW4056", "TIME_LIMIT_PW4060",
            "CURRENT_REMAINING_PW4056", "CURRENT_REMAINING_PW4060",
        ]
        bad = [v for v in vals if not _looks_valid(v)]
        if bad:
            # Never guess a wrong split: fold the whole raw block into the
            # catch-all instead of force-fitting a garbled cell into a
            # named field.
            rec["STATUS_TRAIL"] = " | ".join(cells[3:11])
        else:
            for name, val in zip(numeric_names, vals):
                rec[name] = val

        rec["FOOTNOTE"] = footnote
        rec["FOOTNOTE_TEXT"] = footnotes.get(footnote, "") if footnote else ""
        for k, v in meta.items():
            rec[k] = v

        records.append(rec)
        i += 1

    if records:
        fl_pw4056, fl_pw4060 = await _parse_first_limiter(img, v_lines, h_lines[-1])
        for rec in records:
            rec["FIRST_LIMITER_REMAINING_PW4056"] = fl_pw4056
            rec["FIRST_LIMITER_REMAINING_PW4060"] = fl_pw4060

    return records
