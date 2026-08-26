"""Air France "CCINV" (Aircraft Reglementary Inventory) HT export.

Header, values genericized below but the shape is real::

    ** CCINV ** A I R F R A N C E <date>
    ALL MOTHER SHOPS AIRCRAFT REGLEMENTARY INVENTORY : <tail> M.E.: AF-A31/32 PAGE: 1
    DATE: <date> HOURS: <n> CYCLES: <n>
    LVL RCN T ACTUAL MANUFACT. PART INSTALL TATI A C C U M U L A T E D C S P E C S . V A L U E S EP ID
    CDN A.RCN POS NOUN L SERIAL SERIAL DATE CATI HOURS CYCLE DAYOP DAYCA S HOURS CYCLE DAYOP DAYCA STATUS
    ---- ------- --- -------- - ------ --------------- ------- ------ ---- ------ ----- ----- ----- - ------ ----- ----- ----- -------
    1 0322424 00 SAIV 3 003072 VFT210A2 18JAN18 42059 NEW 62201 44200 9661 10856 R
    Y 0322424 371 27889 OHAU 62201 44200 9661 10856
    REPA 6889 4180 1174 1201
    BENC 6889 4180 1174 1201
    INST 6889 4180 1174 1174
    ATA: 21 26 52 MARK NUMBER: 15HQ M.E ITEM: 212652-51-1AFR01/01
    SOFT TIME ON CHECKS: UR = OHAU
    = REPA 10000
    = BENC
    ----------------------------------------------------------------------------------------------------------------------------------

Cover pages: the first few pages of a file in this corpus are typically a
large ASCII-art title-block logo page, then a short "<title> (ERROR
REPORT)" summary page (may say "**** END OF DATA ****" if there's nothing
to report), then the logo again -- the real component table can start
several pages in. Row-anchor detection below only fires on lines with the
component-row shape, so these cover pages naturally yield zero rows
without special-casing; the sheet-type signature is still found on them
since "(ERROR REPORT)" is just a suffix appended to the same title phrase.

Each physical component is a repeating multi-line block, terminated by a
solid dashed separator line (a long unbroken run of `-`, distinct from the
column-header's dashed rule which has spaces between dash groups):

  1. a "core" data line: LVL, RCN, POS (T), NOUN (description, sometimes
     multiple words), a constant single-digit "L" token (always seen as
     `3` in this corpus), ACTUAL_SERIAL, PART_SERIAL (manufacturer
     serial/part), INSTALL_DATE (`DDMMMYY`), then TATI/CATI/4 accumulated
     values (HOURS/CYCLE/DAYOP/DAYCA)/an optional trailing STATUS letter
     (e.g. `R`) -- anchored from the right by the first `DDMMMYY`-shaped
     token, since NOUN's word count varies.
     A slot can also have no unit fitted at all, printed as
     `<LVL> <RCN> <POS> <NOUN...> <L> << NO UNIT INSTALLED >>` with no
     date/accumulated block; handled as its own case.
  2. an optional "Y" secondary line (a linked/replaced-component
     reference -- starts with `Y`, not present for every component).
  3. zero or more category detail lines, a 4-letter code (`REPA`, `BENC`,
     `INST` -- the only three seen across the sample) each followed by
     numeric values.
  4. an `ATA: <chapter> [<n> [<n>]] [(RCN ATA)] [MARK NUMBER: <code>]
     [M.E ITEM: <code> [<code2> ...]]` line -- the most information-dense
     line: ATA chapter (+ optional sub-codes), a FIN-like position code
     ("MARK NUMBER", sometimes blank), and one or more M.E. task item
     codes (sometimes absent, e.g. on "(RCN ATA)" summary rows for unslotted
     positions).
  5. zero or more `SOFT TIME ON CHECKS: ...` lines and `= <code> <n>`
     continuation lines, and occasional `** ... **` annotations (e.g.
     "ABOVE UNIT IS OVERDUE", "NOT FOUND ON AIRCRAFT", "UNFILLED POSITION
     ON WHICH A SPEC MAY EXIST").
  6. the dashed separator line marking the end of this component's block.

A component's lines can straddle a page break -- the core/Y/REPA lines can
end one page and the ATA line + trailing annotations + separator can open
the next, with no core line re-printed -- so this parser walks the whole
document as one continuous line stream (state carried across pages)
instead of resetting per page like most sibling HT parsers do.

Row grain: one row per component (matches this project's convention for
similarly-shaped repeating blocks -- see `hard_time_report_config_slot.py`
and `time_controlled_components_status.py`). The Y-line, REPA/BENC/INST
category breakdown, SOFT TIME/`=` continuation lines, `**` annotations,
and any trailing numeric tokens past the STATUS letter on the core line
are low per-field value and column-ragged (not every component carries
all of them), so they're folded into one `STATUS_TRAIL` catch-all string,
same call the two modules above make for their own trailing blocks.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.ht_variants._base import merged_rules

NAME = "Air France CCINV Aircraft Inventory"
SIGNATURES = [
    "AIRCRAFT REGLEMENTARY INVENTORY",
]

CANONICAL_COLUMNS = [
    "LVL",
    "RCN",
    "POS",
    "NOUN",
    "ACTUAL_SERIAL",
    "PART_SERIAL",
    "INSTALL_DATE",
    "HOURS",
    "CYCLES",
    "DAYS_OP",
    "DAYS_CA",
    "STATUS",
    "ATA",
    "MARK_NUMBER",
    "ME_ITEM",
    "STATUS_TRAIL",
]

_OVERRIDES = {
    "RCN":           {"pattern": r"^\d{6,7}$"},
    "POS":           {"pattern": r"^[A-Z0-9]{1,4}$", "uppercase": True,
                       "allow_empty": True},
    "NOUN":          {"uppercase": True, "allow_empty": True},
    "ACTUAL_SERIAL": {"pattern": r"^[A-Z0-9][A-Z0-9\-/]*$", "uppercase": True,
                       "allow_empty": True},
    "PART_SERIAL":   {"pattern": r"^[A-Z0-9][A-Z0-9\-/]*$", "uppercase": True,
                       "allow_empty": True},
    "INSTALL_DATE":  {"pattern": r"^\d{2}[A-Z]{3}\d{2}$", "allow_empty": True},
    "HOURS":         {"pattern": r"^\d+$", "allow_empty": True},
    "CYCLES":        {"pattern": r"^\d+$", "allow_empty": True},
    "DAYS_OP":       {"pattern": r"^\d+$", "allow_empty": True},
    "DAYS_CA":       {"pattern": r"^\d+$", "allow_empty": True},
    "STATUS":        {"pattern": r"^[A-Z]$", "uppercase": True, "allow_empty": True},
    "ATA":           {"allow_empty": True},
    "MARK_NUMBER":   {"pattern": r"^[A-Z0-9]{1,10}$", "uppercase": True,
                       "allow_empty": True},
    "ME_ITEM":       {"allow_empty": True},
    "STATUS_TRAIL":  {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

_CORE_RE = re.compile(r"^\d+\s+\d{6,7}\s")
_DATE_RE = re.compile(r"^\d{2}[A-Z]{3}\d{2}$")
_SEPARATOR_RE = re.compile(r"^-{20,}$")
_ATA_LINE_RE = re.compile(r"^ATA:\s*")
_SKIP_PREFIXES = (
    "** CCINV **",
    "ALL MOTHER SHOPS",
    "DATE:",
    "LVL RCN T ACTUAL",
    "CDN A.RCN POS NOUN",
    "**** END OF DATA ****",
    "RCN SERIAL",
)


def _is_header_rule_line(line: str) -> bool:
    # The column-header's own dashed rule ("---- ------- --- ...") is made
    # of dash-groups separated by spaces -- distinct from a component's
    # solid dashed end-of-block separator, which has no spaces at all.
    return bool(line) and set(line) <= {"-", " "} and " " in line


def _is_skip_line(line: str) -> bool:
    if not line:
        return True
    if line.startswith(_SKIP_PREFIXES):
        return True
    if _is_header_rule_line(line):
        return True
    return False


def _parse_ata_line(line: str) -> tuple[str, str, str, str]:
    """Split an `ATA: ...` line into (ata_chapter, ata_full, mark_number, me_item).

    Handled with plain string ops rather than one regex: MARK NUMBER and
    M.E ITEM are each optional and MARK NUMBER can be present-but-blank
    (`MARK NUMBER: M.E ITEM: ...`), which a single greedy/lazy regex
    struggled to express cleanly across every combination seen in the
    sample.

    `ata_full` keeps every digit-group printed on the line (e.g.
    `21 26 52`); `ata_chapter` is just the leading 2-digit ATA chapter, to
    match this project's global `ATA` column convention (`^\\d{2}$`,
    validated against the 20-83 aircraft-systems range) shared by every
    other sheet-type variant.
    """
    body = _ATA_LINE_RE.sub("", line).replace("(RCN ATA)", "").strip()
    mark_number = ""
    me_item = ""
    if "MARK NUMBER:" in body:
        before, _, after = body.partition("MARK NUMBER:")
        ata_full = before.strip()
        if "M.E ITEM:" in after:
            mark_part, _, item_part = after.partition("M.E ITEM:")
            mark_number = mark_part.strip()
            me_item = item_part.strip()
        else:
            mark_number = after.strip()
    elif "M.E ITEM:" in body:
        before, _, after = body.partition("M.E ITEM:")
        ata_full = before.strip()
        me_item = after.strip()
    else:
        ata_full = body.strip()
    ata_chapter = ata_full.split()[0] if ata_full.split() else ""
    return ata_chapter, ata_full, mark_number, me_item


def _parse_core_line(line: str) -> dict | None:
    toks = line.split()
    if len(toks) < 5:
        return None
    lvl, rcn, pos = toks[0], toks[1], toks[2]
    if not lvl.isdigit():
        return None
    if not re.match(r"^\d{6,7}$", rcn):
        return None

    if "NO UNIT INSTALLED" in line:
        # `<LVL> <RCN> <POS> <NOUN...> <L> << NO UNIT INSTALLED >>`
        try:
            marker_idx = toks.index("<<")
        except ValueError:
            marker_idx = len(toks)
        # toks[marker_idx - 1] is the constant single-digit "L" token.
        noun_end = max(marker_idx - 1, 3)
        noun = " ".join(toks[3:noun_end])
        return {
            "LVL": lvl, "RCN": rcn, "POS": pos, "NOUN": noun,
            "ACTUAL_SERIAL": "", "PART_SERIAL": "", "INSTALL_DATE": "",
            "HOURS": "", "CYCLES": "", "DAYS_OP": "", "DAYS_CA": "",
            "STATUS": "",
            "_trail_extra": "NO UNIT INSTALLED",
        }

    date_idx = next((i for i in range(3, len(toks)) if _DATE_RE.match(toks[i])), None)
    if date_idx is None or date_idx - 3 < 0:
        return None
    # toks[date_idx - 3] is the constant single-digit "L" token, toks[date_idx-2]
    # is ACTUAL_SERIAL, toks[date_idx-1] is PART_SERIAL/MANUFACT. SERIAL.
    noun = " ".join(toks[3:date_idx - 3])
    actual_serial = toks[date_idx - 2]
    part_serial = toks[date_idx - 1]
    install_date = toks[date_idx]

    rest = toks[date_idx + 1:]
    if len(rest) < 6:
        return None
    # rest[0] = TATI code, rest[1] = CATI status word (e.g. "NEW") -- both
    # low individual value, folded into the trail below rather than given
    # their own columns.
    tati, cati = rest[0], rest[1]
    hours, cycles, days_op, days_ca = rest[2:6]
    status = ""
    extra: list[str] = []
    if len(rest) > 6:
        if re.match(r"^[A-Za-z]+$", rest[6]):
            status = rest[6]
            extra = rest[7:]
        else:
            extra = rest[6:]

    trail_bits = [f"TATI:{tati}", f"CATI:{cati}"]
    if extra:
        trail_bits.append("EXTRA:" + " ".join(extra))

    return {
        "LVL": lvl, "RCN": rcn, "POS": pos, "NOUN": noun,
        "ACTUAL_SERIAL": actual_serial, "PART_SERIAL": part_serial,
        "INSTALL_DATE": install_date,
        "HOURS": hours, "CYCLES": cycles, "DAYS_OP": days_op, "DAYS_CA": days_ca,
        "STATUS": status,
        "_trail_extra": " ".join(trail_bits),
    }


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    current: dict | None = None
    trail: list[str] = []

    def _flush():
        if current is not None:
            rec = dict(current)
            rec.pop("_trail_extra", None)
            rec["STATUS_TRAIL"] = " | ".join(t for t in trail if t)
            rec.setdefault("ATA", "")
            rec.setdefault("MARK_NUMBER", "")
            rec.setdefault("ME_ITEM", "")
            rec["_page"] = current["_page"]
            records.append(rec)

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if len(text) < 50:
                continue
            for raw in text.splitlines():
                line = raw.strip()
                if _is_skip_line(line):
                    continue

                if _SEPARATOR_RE.match(line):
                    _flush()
                    current = None
                    trail = []
                    continue

                if _CORE_RE.match(line):
                    comp = _parse_core_line(line)
                    if comp is not None:
                        _flush()
                        extra = comp.pop("_trail_extra", "")
                        comp["_page"] = page_num
                        current = comp
                        trail = [extra] if extra else []
                        continue
                    # Fall through: didn't parse as a component core line
                    # (e.g. malformed row) -- treat as a trail continuation
                    # of whatever component is currently open, same as any
                    # other unrecognized line below.

                if _ATA_LINE_RE.match(line):
                    ata_chapter, ata_full, mark_number, me_item = _parse_ata_line(line)
                    if current is not None:
                        current["ATA"] = ata_chapter
                        current["MARK_NUMBER"] = mark_number
                        current["ME_ITEM"] = me_item
                        if ata_full != ata_chapter:
                            trail.append(f"ATA_FULL:{ata_full}")
                    continue

                # Y-line / REPA-BENC-INST category lines / SOFT TIME lines /
                # "=" continuation lines / "**" annotations / anything else
                # belonging to the currently open component.
                if current is not None:
                    trail.append(line)
        _flush()
    return records
