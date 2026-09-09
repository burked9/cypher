"""Component Fit List -- born-digital, full text layer, coordinate-bucketed
columns. Confirmed via a direct pdfplumber pass over every page of one real
sample file (no OCR needed; extract() is synchronous).

Header block (repeats verbatim at the top of every page)::

    AIRBUS <type> <reg> COMPONENT FIT LIST
    Updated <D-Mon-YY> MSN <msn> A/C DOM <D-Mon-YY>
    <scrambled fragment> <D-Mon-YY> MO SINCE NEW <n> APU TSN <n> <n>
    A/C TSN <n> <n> DAYS SINCE NEW <n> APU CSN <n> <n>
    A/C CSN <n>

`<type>`, `<reg>`, the "Updated" date and MSN and A/C DOM are parsed once
(via plain page.extract_text() -- these specific lines extract intact, see
below) and stamped onto every row as AIRCRAFT_TYPE / AIRCRAFT_REG /
UPDATED_DATE / MSN / AC_DOM. A/C TSN, A/C CSN, APU TSN, APU CSN and DAYS
SINCE NEW are also parsed and stamped (as AC_TSN / AC_CSN / APU_TSN /
APU_CSN / DAYS_SINCE_NEW) -- confirmed via the same clean text lines,
cross-checked below.

Why extract_text() is trustworthy for THIS header despite the module-level
warning below about the column-header line: on the real sample, the title
line, the "Updated .../MSN .../A/C DOM ..." line, the "A/C TSN ... DAYS
SINCE NEW ... APU CSN ..." line and the trailing "A/C CSN <n>" line each
extract as one clean, intact physical line via plain extract_text() --
confirmed directly, on every page. Only ONE header line is genuinely
scrambled: a short fragment overlapping the "Updated"/MSN block's own
sibling line (something like "<garbled letters> <D-Mon-YY> MO SINCE NEW <n>
APU TSN <n> <n>"). Its "APU TSN <n> <n>" tail is still a clean, unambiguous
substring of that line (regex-searched, not depended on for full-line
structure), so APU_TSN is captured with real confidence; the leading
scrambled fragment and the "MO SINCE NEW <n>" figure are NOT confidently
interpretable from word positions alone and are deliberately left
unparsed/uncaptured rather than guessed.

Column-header line (the ATA/FIN/Position/.../Date fitted/... line) IS the
severely scrambled one described by the task: it uses overlapping/rotated
text elements that defeat pdfplumber's default line-reconstruction, so it
is not used at all for parsing. Column meaning was instead derived from
(a) the individual header WORDS, still legible via extract_words() with
their real x0/top positions even though extract_text()'s line order for
that region is broken, and (b) the clean DATA ROWS beneath it. Two
independent lines of evidence confirm the six trailing numeric columns:

  1. Word positions: "A/C .. at fit" / "Unit .. since fit" labels recovered
     from extract_words(), each in its own distinct, non-overlapping x-band
     matching one data column's x0.
  2. Arithmetic cross-check: for every row sampled, AC_..._AT_FIT +
     UNIT_..._SINCE_FIT == the matching header total (AC_TSN / AC_CSN /
     DAYS_SINCE_NEW) for hours / landings / days respectively -- confirmed
     across multiple rows including a rare corrupted one (see below), never
     off by more than a same-day rounding difference.

Column geometry (x0 anchors, measured directly off real data-row words)::

    ATA(52) FIN(76) POSITION(100) ZONE(135) PART_NUMBER(164)
    DESCRIPTION(223) SERIAL_NUMBER(332) DATE_FITTED(392)
    DATE_REMOVED(426) PART_FITTED_TO(463) SERIAL_FITTED_TO(505)
    AC_DAYS_AT_FIT(542) AC_HOURS_AT_FIT(565) AC_LANDINGS_AT_FIT(591)
    UNIT_DAYS_SINCE_FIT(703) UNIT_HOURS_SINCE_FIT(732)
    UNIT_LANDINGS_SINCE_FIT(762)

POSITION and ZONE are populated on only a minority of rows (confirmed
sparse, not a parsing gap). DATE_REMOVED / PART_FITTED_TO /
SERIAL_FITTED_TO are populated on almost no rows in the real sample -- this
report lists currently-fitted components, so a removal-related value is
the rare exception rather than the norm; still captured verbatim (never
guessed) on the handful of rows that do carry one. AC_DAYS_AT_FIT is blank
on the majority of "fitted since new" rows rather than an explicit 0 --
left blank rather than assumed zero.

FIN sometimes prints on its own physical line, ~1pt below/above its row's
other columns (a font-baseline offset, confirmed on the real sample) --
row clustering below merges it back onto its row via a small top-tolerance
rather than treating it as a separate row or losing it.

DESCRIPTION occasionally wraps across up to three physical lines when it
is long (confirmed: a line consisting ONLY of words inside the DESCRIPTION
x-band, immediately above and/or below a real data row, with no ATA/PN/etc
words of its own). These pure-description continuation lines are merged
onto the adjacent row's DESCRIPTION (prefix if above, suffix if below)
rather than dropped or left as orphan fragments.

Confirmed real-file quirk -- doubled-character row corruption:
On most pages, exactly one row (varying position, not a fixed row number)
renders with every character interleaved/doubled -- e.g. a clean word like
"21" prints as "2211", "VALVE-TRIM" as "VVAALLVVEE-TTRRIIMM". This is
independent from the header-scrambling issue above: it affects a handful
of ordinary DATA rows, not the header, and always affects the row's own
distinct, real data (never a mere duplicate of an adjacent row -- checked
directly: the corrupted row's own part/serial/date never match a clean
row elsewhere on the same page). A deterministic, reversible de-interleave
(greedy left-to-right: two equal adjacent characters collapse to one;
an unpaired character, e.g. a shared hyphen glyph, passes through as-is)
recovers the original text exactly -- verified against every corrupted row
observed AND against the arithmetic cross-check above (recovered
AC_..._AT_FIT + UNIT_..._SINCE_FIT reproduces the header totals exactly on
every corrupted row tested). Applying this blindly to every row would be
unsafe (an ordinary un-corrupted token can coincidentally contain a
doubled letter, e.g. two adjacent zeros in a part number, and would be
wrongly collapsed), so it is gated strictly: only triggered when a row's
own ATA-band token fails the plain `^\d{2}$` shape AND the de-interleave of
that one token yields a valid 2-digit result. Only then is the
de-interleave applied to the rest of that row's words, and the
reconstructed row is still run through the same field validation as any
other row -- if a de-interleaved field still fails validation, the row's
raw (pre-collapse) text is captured into STATUS_TRAIL and the affected
named fields are left blank, per this project's "never guess a wrong
split" convention (see e.g. occm_variants/occm_component_data_install_current.py).

Row validity: a real component row always carries a valid 2-digit ATA and
at least one of PART_NUMBER / SERIAL_NUMBER (confirmed on the sample).
Rows with neither are the column-header line itself, the repeated page
title/footer block, or a signature/footer block -- none are real records
and are dropped rather than emitted as garbage rows.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "Component Fit List"
SIGNATURES = [
    "COMPONENT FIT LIST",
]

CANONICAL_COLUMNS = [
    "ATA",
    "FIN",
    "POSITION",
    "ZONE",
    "PART_NUMBER",
    "DESCRIPTION",
    "SERIAL_NUMBER",
    "DATE_FITTED",
    "DATE_REMOVED",
    "PART_FITTED_TO",
    "SERIAL_FITTED_TO",
    "AC_DAYS_AT_FIT",
    "AC_HOURS_AT_FIT",
    "AC_LANDINGS_AT_FIT",
    "UNIT_DAYS_SINCE_FIT",
    "UNIT_HOURS_SINCE_FIT",
    "UNIT_LANDINGS_SINCE_FIT",
    # Raw text for a row whose de-interleaved fields still failed
    # validation -- see module docstring's doubled-character section.
    "STATUS_TRAIL",
    # Header metadata -- parsed once, stamped onto every row.
    "AIRCRAFT_TYPE",
    "AIRCRAFT_REG",
    "UPDATED_DATE",
    "MSN",
    "AC_DOM",
    "AC_TSN",
    "AC_CSN",
    "APU_TSN",
    "APU_CSN",
    "DAYS_SINCE_NEW",
]

_DATE_RULE = {"pattern": r"^\d{1,2}-[A-Za-z]{3}-\d{2,4}$", "allow_empty": True}
_NUM_RULE = {"pattern": r"^\d+$", "int_range": (0, 400000), "allow_empty": True}
_OVERRIDES = {
    # FIN is genuinely blank on a real minority of rows in the sample
    # (confirmed directly -- no wrapped/offset FIN line nearby to recover),
    # same sparse-field situation as POSITION/ZONE below -- not a parsing
    # gap, so it must not be flagged as missing.
    "FIN": {"allow_empty": True},
    "ZONE": {"pattern": r"^\d{1,2}(\.\d{1,2})?$", "allow_empty": True},
    "POSITION": {
        "pattern": r"^[A-Z0-9][A-Z0-9#()./\-' ]{0,40}$",
        "uppercase": True,
        "allow_empty": True,
    },
    "DESCRIPTION": {"uppercase": True, "allow_empty": True},
    "DATE_FITTED": _DATE_RULE,
    "DATE_REMOVED": _DATE_RULE,
    "PART_FITTED_TO": {"pattern": r"^[A-Z0-9][A-Z0-9.\-]*$", "uppercase": True, "allow_empty": True},
    "SERIAL_FITTED_TO": {"pattern": r"^[A-Z0-9][A-Z0-9.\-/]*$", "uppercase": True, "allow_empty": True},
    "AC_DAYS_AT_FIT": _NUM_RULE,
    "AC_HOURS_AT_FIT": _NUM_RULE,
    "AC_LANDINGS_AT_FIT": _NUM_RULE,
    "UNIT_DAYS_SINCE_FIT": _NUM_RULE,
    "UNIT_HOURS_SINCE_FIT": _NUM_RULE,
    "UNIT_LANDINGS_SINCE_FIT": _NUM_RULE,
    "STATUS_TRAIL": {"allow_empty": True},
    "AIRCRAFT_TYPE": {"pattern": r"^[A-Z0-9\-]{2,12}$", "uppercase": True, "allow_empty": True},
    "AIRCRAFT_REG": {"pattern": r"^[A-Z0-9\-]{2,10}$", "uppercase": True, "allow_empty": True},
    "UPDATED_DATE": _DATE_RULE,
    "MSN": {"pattern": r"^\d{1,6}$", "allow_empty": True},
    "AC_DOM": _DATE_RULE,
    "AC_TSN": _NUM_RULE,
    "AC_CSN": _NUM_RULE,
    "APU_TSN": _NUM_RULE,
    "APU_CSN": _NUM_RULE,
    "DAYS_SINCE_NEW": _NUM_RULE,
}
RULES = merged_rules(_OVERRIDES)

# --- Column x-position anchors ---------------------------------------------
_NAMED_COLS = [
    ("ATA", 52.3),
    ("FIN", 76.0),
    ("POSITION", 100.0),
    ("ZONE", 135.0),
    ("PART_NUMBER", 163.7),
    ("DESCRIPTION", 223.4),
    ("SERIAL_NUMBER", 331.8),
    ("DATE_FITTED", 392.5),
    ("DATE_REMOVED", 425.5),
    ("PART_FITTED_TO", 462.7),
    ("SERIAL_FITTED_TO", 505.0),
    ("AC_DAYS_AT_FIT", 542.4),
    ("AC_HOURS_AT_FIT", 564.8),
    ("AC_LANDINGS_AT_FIT", 591.1),
    ("UNIT_DAYS_SINCE_FIT", 703.0),
    ("UNIT_HOURS_SINCE_FIT", 731.6),
    ("UNIT_LANDINGS_SINCE_FIT", 761.6),
]
_NUMERIC_COLS = [
    "AC_DAYS_AT_FIT", "AC_HOURS_AT_FIT", "AC_LANDINGS_AT_FIT",
    "UNIT_DAYS_SINCE_FIT", "UNIT_HOURS_SINCE_FIT", "UNIT_LANDINGS_SINCE_FIT",
]
_TEXT_COLS = ["FIN", "POSITION", "ZONE", "PART_NUMBER", "DESCRIPTION", "SERIAL_NUMBER"]

_COL_NAMES = [c[0] for c in _NAMED_COLS]
_COL_X0 = [c[1] for c in _NAMED_COLS]
_BOUNDARIES: list[tuple[float, float]] = []
for _i in range(len(_COL_X0)):
    _lo = float("-inf") if _i == 0 else (_COL_X0[_i - 1] + _COL_X0[_i]) / 2
    _hi = float("inf") if _i == len(_COL_X0) - 1 else (_COL_X0[_i] + _COL_X0[_i + 1]) / 2
    _BOUNDARIES.append((_lo, _hi))


def _bucket_for(x0: float) -> str:
    for name, (lo, hi) in zip(_COL_NAMES, _BOUNDARIES):
        if lo <= x0 < hi:
            return name
    return _COL_NAMES[-1]


_ATA_RE = re.compile(r"^\d{2}$")
_DATE_RE = re.compile(r"^\d{1,2}-[A-Za-z]{3}-\d{2,4}$")
_DIGIT_RE = re.compile(r"^\d+$")

_TITLE_RE = re.compile(
    r"AIRBUS\s+(?P<type>\S+)\s+(?P<reg>\S+)\s+COMPONENT FIT LIST"
)
_UPDATED_RE = re.compile(
    r"Updated\s+(?P<updated>\d{1,2}-[A-Za-z]{3}-\d{2,4})\s+MSN\s+(?P<msn>\d+)"
    r"\s+A/C\s+DOM\s+(?P<dom>\d{1,2}-[A-Za-z]{3}-\d{2,4})"
)
_AC_TSN_RE = re.compile(r"A/C\s+TSN\s+(?P<w1>\d+)\s+(?P<w2>\d+)")
_AC_CSN_RE = re.compile(r"A/C\s+CSN\s+(?P<v>\d+)")
_DAYS_SINCE_NEW_RE = re.compile(r"DAYS\s+SINCE\s+NEW\s+(?P<v>\d+)")
_APU_TSN_RE = re.compile(r"APU\s+TSN\s+(?P<w1>\d+)\s+(?P<w2>\d+)")
_APU_CSN_RE = re.compile(r"APU\s+CSN\s+(?P<w1>\d+)\s+(?P<w2>\d+)")


def _parse_header(text: str) -> dict:
    meta: dict = {}
    m = _TITLE_RE.search(text)
    if m:
        meta["AIRCRAFT_TYPE"] = m.group("type")
        meta["AIRCRAFT_REG"] = m.group("reg")
    m = _UPDATED_RE.search(text)
    if m:
        meta["UPDATED_DATE"] = m.group("updated")
        meta["MSN"] = m.group("msn")
        meta["AC_DOM"] = m.group("dom")
    m = _AC_TSN_RE.search(text)
    if m:
        meta["AC_TSN"] = m.group("w1") + m.group("w2")
    m = _AC_CSN_RE.search(text)
    if m:
        meta["AC_CSN"] = m.group("v")
    m = _DAYS_SINCE_NEW_RE.search(text)
    if m:
        meta["DAYS_SINCE_NEW"] = m.group("v")
    m = _APU_TSN_RE.search(text)
    if m:
        meta["APU_TSN"] = m.group("w1") + m.group("w2")
    m = _APU_CSN_RE.search(text)
    if m:
        meta["APU_CSN"] = m.group("w1") + m.group("w2")
    return meta


def _collapse_doubled(s: str) -> str:
    """Greedy left-to-right de-interleave: two equal adjacent characters
    collapse to one; an unpaired character passes through unchanged. See
    module docstring's doubled-character-row section."""
    out: list[str] = []
    i, n = 0, len(s)
    while i < n:
        if i + 1 < n and s[i] == s[i + 1]:
            out.append(s[i])
            i += 2
        else:
            out.append(s[i])
            i += 1
    return "".join(out)


def _cluster_rows(words: list[dict]) -> list[list[dict]]:
    """Group words into visual rows by their `top` coordinate (2pt
    tolerance -- enough to merge the FIN-wrap baseline offset described in
    the module docstring without merging adjacent printed lines)."""
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
            row_groups.append(sorted(row_words, key=lambda w: w["x0"]))
    return row_groups


def _bucket_words(row_words: list[dict]) -> dict[str, list[dict]]:
    buckets: dict[str, list[dict]] = {}
    for w in row_words:
        buckets.setdefault(_bucket_for(w["x0"]), []).append(w)
    return buckets


def _description_continuation_text(buckets: dict[str, list[dict]]) -> str | None:
    """Return the joined text of a pure DESCRIPTION-wrap continuation line,
    or None if this line is not one.

    A long DESCRIPTION occasionally runs far enough right that its own
    trailing word's x0 lands past the DESCRIPTION/SERIAL_NUMBER boundary
    (confirmed on the real sample, e.g. a wrapped equipment-name label) --
    but only on a line that otherwise carries none of a real row's other
    fields. Genuine SERIAL_NUMBER values in this file always contain at
    least one digit (confirmed on every populated SN in the sample, "N/A"
    aside), so a SERIAL_NUMBER-bucket token with no digit at all on such a
    line is this same overflow, not a real serial number -- folded back
    into the description text rather than left to masquerade as an SN or
    to block the continuation-line merge below."""
    if "DESCRIPTION" not in buckets:
        return None
    sn_words = buckets.get("SERIAL_NUMBER", [])
    sn_is_overflow = bool(sn_words) and all(
        not any(ch.isdigit() for ch in w["text"]) for w in sn_words
    )
    if sn_words and not sn_is_overflow:
        return None
    other = [
        c for c in _COL_NAMES
        if c not in ("DESCRIPTION", "SERIAL_NUMBER") and buckets.get(c)
    ]
    if other:
        return None
    words = list(buckets["DESCRIPTION"]) + list(sn_words if sn_is_overflow else [])
    words.sort(key=lambda w: w["x0"])
    return " ".join(w["text"] for w in words)


def _row_top(row_words: list[dict]) -> float:
    return sum(w["top"] for w in row_words) / len(row_words)


def _build_record(buckets: dict[str, list[dict]]) -> dict:
    rec: dict = {c: "" for c in CANONICAL_COLUMNS}
    sn_words = list(buckets.get("SERIAL_NUMBER", []))
    sn_overflow: list[str] = []
    if len(sn_words) > 1:
        # A long DESCRIPTION's trailing word(s) occasionally land past the
        # DESCRIPTION/SERIAL_NUMBER boundary on the row's own line (same
        # confirmed real-file quirk as the pure-continuation-line case
        # above, e.g. "RETRACT MODULE LH - GREY <sn>" or "INDICATOR-RUDDER
        # TRIM <sn>"). The real SERIAL_NUMBER is always the LAST (rightmost)
        # word in the bucket -- confirmed on every such row in the sample,
        # including ones where the overflow word itself contains a digit
        # (so a digit/no-digit split can't be used here) -- everything
        # before it in this bucket is folded back onto DESCRIPTION rather
        # than glued onto the real SN.
        sn_overflow = [w["text"] for w in sn_words[:-1]]
        sn_words = sn_words[-1:]
    for name in _TEXT_COLS:
        if name == "SERIAL_NUMBER":
            rec[name] = " ".join(w["text"] for w in sn_words)
            continue
        toks = [w["text"] for w in buckets.get(name, [])]
        rec[name] = " ".join(toks)
    if sn_overflow:
        rec["DESCRIPTION"] = (rec["DESCRIPTION"] + " " + " ".join(sn_overflow)).strip()
    date_toks = [w["text"] for w in buckets.get("DATE_FITTED", [])]
    rec["DATE_FITTED"] = " ".join(date_toks)
    for name in ("DATE_REMOVED", "PART_FITTED_TO", "SERIAL_FITTED_TO"):
        toks = [w["text"] for w in buckets.get(name, [])]
        rec[name] = " ".join(toks)
    for name in _NUMERIC_COLS:
        toks = [w["text"] for w in buckets.get(name, [])]
        rec[name] = " ".join(toks)
    return rec


def _parse_row(row_words: list[dict]) -> dict | None:
    buckets = _bucket_words(row_words)
    if _description_continuation_text(buckets) is not None:
        return None  # handled as a continuation merge by the caller

    ata_words = buckets.get("ATA", [])
    if not ata_words:
        return None
    ata_raw = ata_words[0]["text"]

    if _ATA_RE.match(ata_raw):
        rec = _build_record(buckets)
        rec["ATA"] = ata_raw
        rec["STATUS_TRAIL"] = ""
    else:
        collapsed_ata = _collapse_doubled(ata_raw)
        if not _ATA_RE.match(collapsed_ata):
            # Neither a plain nor a doubled-then-collapsed ATA -- not a
            # real data row (header/footer noise landing in this band).
            return None
        # Confirmed doubled-character row (see module docstring): collapse
        # every word, then validate as usual before trusting it.
        collapsed_buckets: dict[str, list[dict]] = {}
        for col, words in buckets.items():
            collapsed_buckets[col] = [
                {**w, "text": _collapse_doubled(w["text"])} for w in words
            ]
        rec = _build_record(collapsed_buckets)
        rec["ATA"] = collapsed_ata

        ok = bool(rec["PART_NUMBER"]) and bool(rec["DATE_FITTED"])
        if ok and rec["DATE_FITTED"] and not _DATE_RE.match(rec["DATE_FITTED"]):
            ok = False
        if ok:
            for name in _NUMERIC_COLS:
                if rec[name] and not _DIGIT_RE.match(rec[name]):
                    ok = False
                    break
        if not ok:
            # De-interleave didn't cleanly validate -- don't guess. Capture
            # the raw (pre-collapse) row text and leave named fields blank.
            raw = _build_record(buckets)
            rec = {c: "" for c in CANONICAL_COLUMNS}
            rec["STATUS_TRAIL"] = " ".join(w["text"] for w in row_words)
            return rec
        rec["STATUS_TRAIL"] = ""

    if not rec["PART_NUMBER"] and not rec["SERIAL_NUMBER"]:
        return None
    return rec


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    header_meta: dict = {
        "AIRCRAFT_TYPE": "", "AIRCRAFT_REG": "", "UPDATED_DATE": "",
        "MSN": "", "AC_DOM": "", "AC_TSN": "", "AC_CSN": "",
        "APU_TSN": "", "APU_CSN": "", "DAYS_SINCE_NEW": "",
    }
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            page_meta = _parse_header(text)
            # Header repeats identically on every page; keep the last
            # successfully-parsed value rather than overwriting with blanks
            # if a later page's header fails to match for any reason.
            for k, v in page_meta.items():
                if v:
                    header_meta[k] = v

            words = page.extract_words()
            if not words:
                continue
            row_groups = _cluster_rows(words)

            page_records: list[dict] = []
            page_tops: list[float] = []
            pending_desc: dict[int, list[str]] = {}
            for row_words in row_groups:
                buckets = _bucket_words(row_words)
                text_frag = _description_continuation_text(buckets)
                if text_frag is not None:
                    top = _row_top(row_words)
                    # Attach to the nearest already-parsed row on this page
                    # within a small vertical gap (see module docstring's
                    # DESCRIPTION-wrap section) -- prefer the row directly
                    # above (this fragment is its continuation), else the
                    # next row parsed (this fragment precedes it).
                    attached = False
                    for idx in range(len(page_records) - 1, -1, -1):
                        if top - page_tops[idx] <= 6.0 and top - page_tops[idx] >= -1.0:
                            page_records[idx]["DESCRIPTION"] = (
                                page_records[idx]["DESCRIPTION"] + " " + text_frag
                            ).strip()
                            attached = True
                            break
                    if not attached:
                        pending_desc.setdefault(len(page_records), []).append(text_frag)
                    continue

                rec = _parse_row(row_words)
                if rec is None:
                    continue
                rec.update(header_meta)
                idx = len(page_records)
                page_records.append(rec)
                page_tops.append(_row_top(row_words))
                if idx in pending_desc:
                    rec["DESCRIPTION"] = (
                        " ".join(pending_desc[idx]) + " " + rec["DESCRIPTION"]
                    ).strip()

            records.extend(page_records)
    return records
