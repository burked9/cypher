"""STARS/Trax MIS OCCM export — two page-header styles from the same source
system that produces `ht_variants/stars_trax.py`'s Hard-Time report (that
module names the same known airframe as one of its confirmed files). That
sibling only pulls rows carrying a literal `HT` Mnt/Ctl marker; everything
else in these documents — TSN/TSO/TSI/LL/OHI/HYS/BTS/... — is On Condition
/ Condition Monitored data with nowhere else to go, since neither style
ever carries the HT sheet type's own top-level signature ("PLAN OF
AIRCRAFT COMPONENT REPLACEMENT" — confirmed absent from every page of the
largest file in this cluster). So there's no double-routing risk: these
files reach OCCM or nothing.

Real-corpus triage clustered several files here; most turned out to be one
large multi-hundred-page document split into page-range chunks covering
its pages verbatim, plus the master file itself -- one format, not many.

Style 1 -- "A/C Detail Items Print" header (a known airframe, A319-132).
ATA has no spaces around its dashes and is stated only on a component's
first line; PN and SN repeat on every line unlike ATA. Category/Position/
Mnt-Ctl are three ragged label slots and most rows populate only the
first::

    29-12-0 1554A9900-01 1554A99LI001953 TSN 2WD1 30683:23 15118 3039
    MANIFOLD HP
    1554A9900-01 1554A99LI001953 TSO 2WD1 18668:57 8606 1847
    MANIFOLD HP

Style 2 -- "A/C Status Audit Print" header (seen on two other known
airframes). ATA is spaced
("21 - 00 - 00") and repeats on every line; DESCRIPTION/SERIAL_NO instead
repeat only on a component's first category row, and POSITION/PART_NUMBER
live on a following line and likewise appear once per component::

    21 - 00 - 00 TRIM AIR CHECK VALVE 02009 TSI 35605:48 03/03/2016 10355:09 5526
    19HM 1298A0000-01 O/C 13053 Accum At Install: 1471 776
    21 - 00 - 00 TRIM AIR CHECK VALVE TSN 0:00 03/03/2016 8884:09 4750 1162
    O/C 0 Accum At Install: 0

Both styles are column-ragged the way georgian_airways_ht_components_
status.py and aircraft_components_list.py already documented for sibling
reports: which of the Scheduled/Actuals/Remaining Hours-Cycles-Days
triples is populated varies per row with no whitespace-only way to tell
them apart, so the numeric tail (plus any label token -- a lone `HT` or
`O/C` flag -- that didn't fit CATEGORY/POSITION) is kept as one raw
STATUS_TRAIL string rather than guessed into named sub-columns.

Row/description pairing (style 1) and the trailing position/part-number
line (style 2) are both per-page, matching `stars_trax.py`'s own choice to
reset forward-fill state at each page break rather than stitch across
pages.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules
from shared.cleanup import normalize_dashes

NAME = "STARS Trax OCCM"
SIGNATURES = [
    "A/C Detail Items Print",
    "A/C Status Audit Print",
]

CANONICAL_COLUMNS = [
    "ATA",
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "CATEGORY",
    "POSITION",
    "STATUS_TRAIL",
]

# Chapter-section[-subsection] ATA, e.g. "21-61-0" or "74-20" -- not the
# plain 2-digit chapter the global rule expects, and "00-00-00" (general/
# airframe-level items in style 2) falls outside its 20-83 int_range too.
_OVERRIDES = {
    "ATA": {"pattern": r"^\d{1,3}-\d{1,3}(-\d{1,3})?$", "int_range": None},
    "PART_NUMBER": {"allow_empty": True},
    "SERIAL_NUMBER": {"allow_empty": True},
    "CATEGORY": {"pattern": r"^[A-Z]{1,6}$", "allow_empty": True},
    "POSITION": {"allow_empty": True},
    "STATUS_TRAIL": {"allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# ---------------------------------------------------------------- style 1

_ATA_A_RE = re.compile(r"^\d{1,3}-\d{1,3}(-\d{1,3})?$")
_HAS_DIGIT = re.compile(r"\d")
# Closed-vocabulary-free by design: real category codes (TSN, TSO, TSI, HT,
# LL, OHI, HYS, BTS, ALS, RST, ...) are too numerous to enumerate, but every
# description word in this corpus's ALL-CAPS text can *also* match a bare
# "2-6 uppercase letters" shape ("FUEL", "DOOR", "ASSY", ...). The PN/SN
# digit-gate below is what actually keeps description lines out; this
# shape check only needs to reject the header/footer boilerplate.
_CATEGORY_A_RE = re.compile(r"^[A-Z]{2,6}$")
_NUM_A_RE = re.compile(r"^\d+(:\d{1,2})?$")
_HEADER_SKIP_A = re.compile(
    r"Print Date:|A/C Detail Items Print|^Page:|^A/C:\s|Scheduled\s+Actuals|^ATA\s+P",
    re.I)


def _match_detail_row(toks: list[str], cur_ata: str) -> tuple[dict | None, str]:
    if toks and _ATA_A_RE.match(toks[0]):
        cur_ata = toks[0]
        toks = toks[1:]
    if len(toks) < 3:
        return None, cur_ata
    pn, sn, category = toks[0], toks[1], toks[2]
    # Real PN/SN always carry a digit; this is what actually distinguishes
    # a data row from a plain uppercase description line (see note above).
    if not (_HAS_DIGIT.search(pn) and _HAS_DIGIT.search(sn)):
        return None, cur_ata
    if not _CATEGORY_A_RE.match(category):
        return None, cur_ata
    rest = toks[3:]
    k = 0
    while k < len(rest) and not _NUM_A_RE.match(rest[k]):
        k += 1
    rec = {
        "ATA": cur_ata,
        "PART_NUMBER": pn,
        "SERIAL_NUMBER": sn,
        "CATEGORY": category,
        "POSITION": " ".join(rest[:k]),
        "STATUS_TRAIL": " ".join(rest[k:]),
    }
    return rec, cur_ata


def _extract_detail_items(pages_text: list[str]) -> list[dict]:
    records: list[dict] = []
    for page_num, text in enumerate(pages_text, start=1):
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        cur_ata = ""
        i = 0
        while i < len(lines):
            if _HEADER_SKIP_A.search(lines[i]):
                i += 1
                continue
            rec, cur_ata = _match_detail_row(lines[i].split(), cur_ata)
            if rec is None:
                i += 1
                continue
            # Description always sits on the physical line right after the
            # data row (confirmed on every sampled page) -- but only steal
            # it when that line isn't itself the next data row or header.
            desc = ""
            if i + 1 < len(lines):
                nxt = lines[i + 1]
                nxt_rec, _ = _match_detail_row(nxt.split(), cur_ata)
                if nxt_rec is None and not _HEADER_SKIP_A.search(nxt):
                    desc = nxt
                    i += 1
            rec["DESCRIPTION"] = desc
            rec["_page"] = page_num
            records.append(rec)
            i += 1
    return records


# ---------------------------------------------------------------- style 2

_ATA_B_SEG = re.compile(r"^\d{1,2}$")
_DATE_B_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")
# Shared shape for both SERIAL_NUMBER and PART_NUMBER in this style: must
# carry a digit somewhere, letters/digits/hyphens only. Excludes punctuation
# that turns up in DESCRIPTION's last word instead (e.g. `MONITOR-8.4"`),
# which would otherwise get mistaken for the (dropped, forward-filled) SN.
_ALNUM_ID_RE = re.compile(r"^[A-Z0-9][A-Z0-9-]*\d[A-Z0-9-]*$")
_CATEGORY_B_RE = re.compile(r"^[A-Z]{1,6}$")
_POSITION_B_RE = re.compile(r"^(\d{1,3}[A-Z]{1,4}\d{0,2}|\d{1,3}-\d{1,3}-\d{1,3})$")
_HEADER_SKIP_B = re.compile(
    r"Print Date:|A/C Status Audit Print|^Page:|^A/C:\s|Sorted By:|"
    r"^ATA\s+DESCRIPTION|^POS\s+PART",
    re.I)


def _consume_ata_b(toks: list[str]) -> tuple[str | None, list[str]]:
    if (len(toks) >= 5 and _ATA_B_SEG.match(toks[0]) and toks[1] == "-"
            and _ATA_B_SEG.match(toks[2]) and toks[3] == "-" and _ATA_B_SEG.match(toks[4])):
        return f"{toks[0]}-{toks[2]}-{toks[4]}", toks[5:]
    return None, toks


def _parse_audit_line1(line: str) -> dict | None:
    ata, toks = _consume_ata_b(line.split())
    if ata is None:
        return None
    # The Ent/Inst Date is the one column this style never seems to leave
    # blank (even long-since-superseded rows carry a placeholder date), so
    # it anchors the row far more reliably than guessing at CATEGORY's
    # large, open-ended vocabulary (TSN/TSO/TSI/TSV/SCR/HST/TSLV/WTC/...).
    date_idx = next((i for i, t in enumerate(toks) if _DATE_B_RE.match(t)), None)
    if date_idx is None or date_idx < 2:
        return None
    category = toks[date_idx - 2]
    if not _CATEGORY_B_RE.match(category):
        return None
    head = toks[:date_idx - 2]
    sn = ""
    if head and _ALNUM_ID_RE.match(head[-1]):
        sn = head[-1]
        head = head[:-1]
    return {
        "ATA": ata,
        "DESCRIPTION": " ".join(head),
        "SERIAL_NUMBER": sn,
        "CATEGORY": category,
        "_trail1": " ".join(toks[date_idx - 1:]),
    }


def _extract_status_audit(pages_text: list[str]) -> list[dict]:
    records: list[dict] = []
    for page_num, text in enumerate(pages_text, start=1):
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        cur_ata = cur_desc = cur_sn = cur_pos = cur_pn = ""
        i = 0
        while i < len(lines):
            if _HEADER_SKIP_B.search(lines[i]):
                i += 1
                continue
            row = _parse_audit_line1(lines[i])
            if row is None:
                i += 1
                continue
            cur_ata = row["ATA"]
            if row["DESCRIPTION"]:
                cur_desc = row["DESCRIPTION"]
            if row["SERIAL_NUMBER"]:
                cur_sn = row["SERIAL_NUMBER"]
            i += 1
            # POSITION/PART_NUMBER (when present at all) sit on the line(s)
            # right after -- one extra line normally, two when the source
            # also echoes an ATA-shaped position placeholder ("00-00-00")
            # on its own line first (seen on one of the known airframes).
            trailer: list[str] = []
            while i < len(lines):
                ata_here, _ = _consume_ata_b(lines[i].split())
                if ata_here is not None or _HEADER_SKIP_B.search(lines[i]):
                    break
                trailer.extend(lines[i].split())
                i += 1
            if trailer and _POSITION_B_RE.match(trailer[0]):
                cur_pos = trailer[0]
                trailer = trailer[1:]
                if trailer and _ALNUM_ID_RE.match(trailer[0]):
                    cur_pn = trailer[0]
                    trailer = trailer[1:]
            trail = row["_trail1"]
            if trailer:
                trail = f"{trail} | {' '.join(trailer)}"
            records.append({
                "ATA": cur_ata,
                "DESCRIPTION": cur_desc,
                "PART_NUMBER": cur_pn,
                "SERIAL_NUMBER": cur_sn,
                "CATEGORY": row["CATEGORY"],
                "POSITION": cur_pos,
                "STATUS_TRAIL": trail,
                "_page": page_num,
            })
    return records


def extract(pdf_path: str) -> list[dict]:
    with pdfplumber.open(pdf_path) as pdf:
        pages_text = [normalize_dashes(p.extract_text() or "") for p in pdf.pages]
    if any("A/C Status Audit Print" in t for t in pages_text):
        return _extract_status_audit(pages_text)
    return _extract_detail_items(pages_text)
