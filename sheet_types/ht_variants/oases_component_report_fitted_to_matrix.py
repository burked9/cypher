"""OASES "Component Report" -- HT side, fitted-to/life-code matrix layout.

A different OASES export template from `oases_lifed_components.py`'s
"Lifed Component Report" (that one uses a slashed
`<ata-block>/<position>/<level>.<sublevel>` anchor token per record and has
no "Fitted to part"/"Fitted to serial" columns at all). This template's own
title line reads "Component Report" (not "Lifed Component Report" -- the two
phrases are never confused because this module's own anchor is the
column-header line below, never the bare title) and its column-header line is
unique to it::

    <PN> - <DESCRIPTION>
    Serial Fleet ATA Reference L Aircraft Reg Position Zone Fitted to part
        Fitted to serial Last Movement Life Code Since New Since Fit
        Since Overhaul Since Repair
    <SN> <FLEET> <ATA> <L> <REG> <POS> <ZONE> [<FITTED_PN>] [<FITTED_SN>]
        <LAST_MOVEMENT> Days <since-new> <since-fit> <since-overhaul>
        <since-repair>
    Hours <since-new> <since-fit> <since-overhaul> <since-repair>
    Landings <since-new> <since-fit> <since-overhaul> <since-repair>

Records are grouped under a `<PN> - <DESCRIPTION>` header line (applies to
every serial listed below it, until the next such header) and the
Serial/Fleet/.../Since-Repair column header repeats above every group. Each
logical record spans 3 physical text lines: the identity/Days line, then a
`Hours` continuation and a `Landings` continuation.

Column x-positions drift by a few points page to page (confirmed directly:
the "Life" header word sits at a different x0 on different pages of the same
sample file), so column boundaries are **not** hardcoded -- they are
re-derived from each page's own repeated header row via
`_find_column_bounds()`, using the header words themselves as anchors. This
avoids the off-by-one-column misread a fixed global bin would produce on
pages where the layout has shifted.

Some records (seen on engine-position rows in the sample corpus) carry extra
trailing lines after the Landings line -- additional life-limit breakdown
rows for alternate engine-model/category combinations (e.g. a line reading
just an engine-model code followed by 4 more numeric values). There is no
reliable, generically-named column set to force these into, so they are
never split -- they are preserved verbatim, one line per list entry, in the
`ADDITIONAL_LIFE_LIMITS` catch-all column instead (never guess a wrong
split).

Anchor for variant detection: the column-header line itself is used rather
than the report title, since it is the more structurally distinctive phrase
(checked directly for collisions against every SIGNATURES list in
sheet_types/{occm,ht,llp}.py and every occm_variants/ht_variants/llp_variants
module file -- no collision found).
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "OASES Component Report (Fitted-To Matrix)"
SIGNATURES = [
    "Fitted to part Fitted to serial",
]

CANONICAL_COLUMNS = [
    "PART_NUMBER",
    "DESCRIPTION",
    "SERIAL_NUMBER",
    "FLEET",
    "ATA",
    "L_CODE",
    "AIRCRAFT_REG",
    "POSITION",
    "ZONE",
    "FITTED_TO_PART",
    "FITTED_TO_SERIAL",
    "LAST_MOVEMENT",
    "DAYS_SINCE_NEW", "DAYS_SINCE_FIT", "DAYS_SINCE_OVERHAUL", "DAYS_SINCE_REPAIR",
    "HOURS_SINCE_NEW", "HOURS_SINCE_FIT", "HOURS_SINCE_OVERHAUL", "HOURS_SINCE_REPAIR",
    "LANDINGS_SINCE_NEW", "LANDINGS_SINCE_FIT", "LANDINGS_SINCE_OVERHAUL", "LANDINGS_SINCE_REPAIR",
    "ADDITIONAL_LIFE_LIMITS",
]

_OVERRIDES = {
    # 6-8 digit extended ATA codes (chapter + sub-codes), not the plain
    # 2-digit chapter the global default expects.
    "ATA":      {"pattern": r"^\d{6,8}$", "int_range": None},
    "ZONE":     {"pattern": r"^(?:\d+(?:\.\d+)?|[A-Z][A-Z0-9/\-]*)$",
                 "uppercase": True, "allow_empty": True},
    "L_CODE":   {"pattern": r"^[A-Z]{1,3}$", "uppercase": True, "allow_empty": True},
    "FLEET":    {"pattern": r"^[A-Z]{1,3}$", "uppercase": True, "allow_empty": True},
    "AIRCRAFT_REG": {"pattern": r"^[A-Z0-9\-]{2,10}$", "uppercase": True, "allow_empty": True},
    "POSITION": {"pattern": r"^[A-Z0-9/_.\-]{1,20}$", "uppercase": True, "allow_empty": True},
    # Parent assembly fields -- only populated on components fitted inside
    # another tracked assembly (e.g. engine sub-parts); blank is normal.
    "FITTED_TO_PART":   {"allow_empty": True},
    "FITTED_TO_SERIAL": {"allow_empty": True},
    "LAST_MOVEMENT": {"pattern": r"^\d{1,2}[a-z]{3}\d{4}$", "allow_empty": True},
    # Every "since" cell may be a numeric count, an `HH:MM` hours value, or
    # a literal `?` for "not recorded in source" -- no hard pattern; keep
    # the distinction between "missing" and "zero" rather than coercing.
    "DAYS_SINCE_NEW": {"allow_empty": True}, "DAYS_SINCE_FIT": {"allow_empty": True},
    "DAYS_SINCE_OVERHAUL": {"allow_empty": True}, "DAYS_SINCE_REPAIR": {"allow_empty": True},
    "HOURS_SINCE_NEW": {"allow_empty": True}, "HOURS_SINCE_FIT": {"allow_empty": True},
    "HOURS_SINCE_OVERHAUL": {"allow_empty": True}, "HOURS_SINCE_REPAIR": {"allow_empty": True},
    "LANDINGS_SINCE_NEW": {"allow_empty": True}, "LANDINGS_SINCE_FIT": {"allow_empty": True},
    "LANDINGS_SINCE_OVERHAUL": {"allow_empty": True}, "LANDINGS_SINCE_REPAIR": {"allow_empty": True},
    "ADDITIONAL_LIFE_LIMITS": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Column order after the header's repeating "Serial Fleet ATA Reference L
# Aircraft Reg Position Zone Fitted to part Fitted to serial Last Movement
# Life Code Since New Since Fit Since Overhaul Since Repair" line. Each
# entry's x0 anchor is re-derived per page from the header row itself (see
# _find_column_bounds); this is just the left-to-right column ordering.
_COLUMN_ORDER = [
    "SERIAL_NUMBER", "FLEET", "ATA", "L_CODE", "AIRCRAFT_REG", "POSITION",
    "ZONE", "FITTED_TO_PART", "FITTED_TO_SERIAL", "LAST_MOVEMENT",
    "LIFE_CODE", "SINCE_NEW", "SINCE_FIT", "SINCE_OVERHAUL", "SINCE_REPAIR",
]

_GROUP_HEADER_RE = re.compile(r"^([A-Z0-9][A-Z0-9\-]{2,})\s*-\s*(.+)$")
_SKIP_RE = re.compile(
    r"OASES MRO System|Component Report|Oases Option|^Aircraft \S+ Fleet|"
    r"^Serial\s+Fleet\s+ATA|^Continued\b|^Run Date", re.I)


def _find_column_bounds(words: list[dict]) -> list[tuple[str, float, float]] | None:
    """Locate this page's own header row and derive column x-bounds from it.

    Returns [(column_name, x0, x1), ...] in `_COLUMN_ORDER`, or None if no
    header row is present on this page (record rows are then binned using
    the most recently seen page's bounds, carried by the caller).
    """
    from collections import defaultdict
    by_top: dict[float, list[dict]] = defaultdict(list)
    for w in words:
        by_top[round(w["top"], 1)].append(w)
    for lw in by_top.values():
        lw = sorted(lw, key=lambda w: w["x0"])
        texts = [w["text"] for w in lw]
        if texts[:3] != ["Serial", "Fleet", "ATA"]:
            continue
        try:
            idx_l = texts.index("L", 4)
            idx_aircraft = texts.index("Aircraft", idx_l)
            idx_position = texts.index("Position", idx_aircraft)
            idx_zone = texts.index("Zone", idx_position)
            idx_fitted1 = texts.index("Fitted", idx_zone)
            idx_fitted2 = texts.index("Fitted", idx_fitted1 + 1)
            idx_last = texts.index("Last", idx_fitted2)
            idx_life = texts.index("Life", idx_last)
            idx_since1 = texts.index("Since", idx_life)
            idx_since2 = texts.index("Since", idx_since1 + 1)
            idx_since3 = texts.index("Since", idx_since2 + 1)
            idx_since4 = texts.index("Since", idx_since3 + 1)
        except ValueError:
            continue
        anchor_idxs = [0, 1, 2, idx_l, idx_aircraft, idx_position, idx_zone,
                       idx_fitted1, idx_fitted2, idx_last, idx_life,
                       idx_since1, idx_since2, idx_since3, idx_since4]
        anchors = [lw[i]["x0"] for i in anchor_idxs]
        bounds = []
        for i, name in enumerate(_COLUMN_ORDER):
            x0 = anchors[i] - 3
            x1 = anchors[i + 1] - 3 if i + 1 < len(anchors) else 9999.0
            bounds.append((name, x0, x1))
        return bounds
    return None


def _bin_words(words: list[dict], bounds: list[tuple[str, float, float]]) -> dict[str, str]:
    row: dict[str, list[str]] = {}
    for w in words:
        for name, x0, x1 in bounds:
            if x0 <= w["x0"] < x1:
                row.setdefault(name, []).append(w["text"])
                break
    return {k: " ".join(v) for k, v in row.items()}


def _empty_record(part_number: str, description: str) -> dict:
    rec = {c: "" for c in CANONICAL_COLUMNS}
    rec["PART_NUMBER"] = part_number
    rec["DESCRIPTION"] = description
    return rec


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    from collections import defaultdict

    with pdfplumber.open(pdf_path) as pdf:
        bounds: list[tuple[str, float, float]] | None = None
        for page_num, page in enumerate(pdf.pages, start=1):
            words = page.extract_words()
            if not words:
                continue
            new_bounds = _find_column_bounds(words)
            if new_bounds:
                bounds = new_bounds

            by_top: dict[float, list[dict]] = defaultdict(list)
            for w in words:
                by_top[round(w["top"], 1)].append(w)

            cur_pn = cur_desc = ""
            pending: dict | None = None       # record awaiting Hours/Landings
            current_record: dict | None = None  # most recent record (for EXTRA lines)

            for top in sorted(by_top.keys()):
                line_words = sorted(by_top[top], key=lambda w: w["x0"])
                text = " ".join(w["text"] for w in line_words)
                if _SKIP_RE.search(text):
                    continue
                first_tok = line_words[0]["text"]

                if first_tok == "Hours" and pending is not None:
                    vals = text.split()[1:5]
                    for col, v in zip(
                        ("HOURS_SINCE_NEW", "HOURS_SINCE_FIT",
                         "HOURS_SINCE_OVERHAUL", "HOURS_SINCE_REPAIR"), vals):
                        pending[col] = v
                    continue

                if first_tok == "Landings" and pending is not None:
                    vals = text.split()[1:5]
                    for col, v in zip(
                        ("LANDINGS_SINCE_NEW", "LANDINGS_SINCE_FIT",
                         "LANDINGS_SINCE_OVERHAUL", "LANDINGS_SINCE_REPAIR"), vals):
                        pending[col] = v
                    records.append(pending)
                    current_record = pending
                    pending = None
                    continue

                binned = _bin_words(line_words, bounds) if bounds else {}
                if binned.get("LIFE_CODE", "").strip() == "Days":
                    if pending is not None:
                        records.append(pending)
                    rec = _empty_record(cur_pn, cur_desc)
                    rec["SERIAL_NUMBER"] = binned.get("SERIAL_NUMBER", "")
                    rec["FLEET"] = binned.get("FLEET", "")
                    rec["ATA"] = binned.get("ATA", "")
                    rec["L_CODE"] = binned.get("L_CODE", "")
                    rec["AIRCRAFT_REG"] = binned.get("AIRCRAFT_REG", "")
                    rec["POSITION"] = binned.get("POSITION", "")
                    rec["ZONE"] = binned.get("ZONE", "")
                    rec["FITTED_TO_PART"] = binned.get("FITTED_TO_PART", "")
                    rec["FITTED_TO_SERIAL"] = binned.get("FITTED_TO_SERIAL", "")
                    rec["LAST_MOVEMENT"] = binned.get("LAST_MOVEMENT", "")
                    since_vals = text.split()[-4:]
                    for col, v in zip(
                        ("DAYS_SINCE_NEW", "DAYS_SINCE_FIT",
                         "DAYS_SINCE_OVERHAUL", "DAYS_SINCE_REPAIR"), since_vals):
                        rec[col] = v
                    rec["_page"] = page_num
                    pending = rec
                    current_record = rec
                    continue

                m = _GROUP_HEADER_RE.match(text)
                if m and line_words[0]["x0"] < 50:
                    cur_pn, cur_desc = m.group(1), m.group(2)
                    current_record = None
                    continue

                # Unrecognized continuation line (e.g. an extra engine-model
                # life-limit breakdown row) -- append verbatim to the most
                # recent record's catch-all rather than guessing a split.
                if current_record is not None:
                    prior = current_record.get("ADDITIONAL_LIFE_LIMITS", "")
                    current_record["ADDITIONAL_LIFE_LIMITS"] = (
                        f"{prior}; {text}" if prior else text)

            if pending is not None:
                records.append(pending)

    return records
