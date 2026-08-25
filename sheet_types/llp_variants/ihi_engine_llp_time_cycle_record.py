"""IHI Corporation "ENGINE/MODULE LIFE LIMITED PART TIME/CYCLE RECORD"
(FORM MU-006-2) -- V2500 engine LLP incoming/outgoing status, one row per
life-limited part, INCOMING STATUS and OUTGOING STATUS side by side.

Confirmed on 1 real file -- real embedded text layer (no OCR needed), but
the text itself reads as already OCR-derived somewhere upstream of this
PDF's creation, not a genuinely clean born-digital export: pervasive
digit/letter confusion (0/O, 1/I/l -- e.g. the engine serial number
extracts with a digit misread as a letter), stray border-glyph
punctuation (!, ', ~, `) glued onto real tokens, and a handful of rows
with a token outright missing or two tokens fused with no separating
space. Only 1 file of this exact format found in the corpus (searched
the whole LLP folder for "IHI Corporation"/"MU-006") -- built anyway per
explicit request, not cluster-mined like most other variants this
session.

Row shape (clean example, real file)::

    STG 3-8 DISK 6A8316 RRD3641 11434:00 20000 5033 14967 6B1404 RRD7535 NEW 0:00 20000 0 20000
    └─ DESCRIPTION ┘└PN┘└──SN──┘└─────── 4 nums ───────┘└PN2┘└──SN2──┘└NEW┘└─────── 4 nums ───────┘
       (incoming side)                                     (outgoing side -- part was replaced)

The 4 trailing numbers per side are (by position, per the header row) T.T
(time since new)/T.C-style running total, a life limit, cycles/hours
used, and cycles/hours remaining -- kept as one raw trailing string per
side rather than split into individually-named fields: OCR noise
(stray punctuation tokens, an occasional missing value) makes a
confident 1:1 positional mapping unreliable on more than a few rows, and
a wrong split would be worse than a readable combined field for
cross-operant part-pricing use, the same call several OCR-heavy siblings
in this package make for their own noisy trailing blocks (see e.g.
xiamen_time_controlled_components.py's STATUS_TRAIL). When a part wasn't
replaced, the source omits the second PN/SN pair entirely (both sides
share the one), which this variant reflects honestly by leaving the
OUTGOING fields empty rather than guessing they equal the incoming ones.
"""
from __future__ import annotations
import re

from sheet_types.llp_variants._base import merged_rules

NAME = "IHI Engine LLP Time/Cycle Record"

# "FORM MU-006" is this producer's own form-code footer, distinctive and
# checked against every existing SIGNATURES list in this package -- no
# collision found.
SIGNATURES = [
    "IHI Corporation",
    "FORM MU-006",
]

CANONICAL_COLUMNS = [
    "DESCRIPTION",
    "INCOMING_PART_NUMBER",
    "INCOMING_SERIAL_NUMBER",
    "INCOMING_STATUS",
    "OUTGOING_PART_NUMBER",
    "OUTGOING_SERIAL_NUMBER",
    "OUTGOING_STATUS",
    # File-level metadata -- same on every row.
    "ENGINE_TYPE",
    "ENGINE_SERIAL_NUMBER",
    "STATUS_DATE",
]

_OVERRIDES = {
    "INCOMING_STATUS": {"allow_empty": True},
    "OUTGOING_STATUS": {"allow_empty": True},
    "OUTGOING_PART_NUMBER": {"allow_empty": True},
    "OUTGOING_SERIAL_NUMBER": {"allow_empty": True},
    "STATUS_DATE": {"pattern": r"^\d{1,2}-[A-Za-z]{3}-\d{2,4}$", "allow_empty": True},
}
RULES = merged_rules(_OVERRIDES)

# Border-glyph noise this producer's scan/OCR step glues onto real tokens
# -- confirmed never legitimate mid-token content in this file's real
# part numbers, serial numbers, or numeric fields (which use only
# alnum/hyphen and digit/colon respectively). Removed from anywhere in a
# token, not just the ends -- some rows show it landing mid-token
# (e.g. "1!5A1757").
_NOISE_CHARS_RE = re.compile(r"[!'\"~`]")

# digit, 1-2 letters, 2-5 digits, optional trailing -alnum suffix --
# covers every real part number seen (5A1757, 6B1404, 2A3596, 5R0159,
# 5A1762) while staying specific enough not to match a serial number or
# a plain quantity/value token.
_PN_RE = re.compile(r"^\d[A-Z]{1,2}\d{2,5}[-A-Z0-9]*$")

_ENGINE_TYPE_RE = re.compile(r"\b([A-Z]{1,2}\d{3,4}-[A-Z]\d)\b")
_DATE_RE = re.compile(r"\b([lI1]-[A-Za-z]{3}-\d{2,4}|\d{1,2}-[A-Za-z]{3}-\d{2,4})\b")


def _clean_tok(tok: str) -> str:
    return _NOISE_CHARS_RE.sub("", tok)


def _parse_header(text: str) -> dict:
    meta: dict[str, str] = {}
    m = _ENGINE_TYPE_RE.search(text)
    if m:
        meta["ENGINE_TYPE"] = m.group(1)
        # The engine serial number is the token immediately following the
        # engine type on the same data line -- distinctive enough not to
        # need its own regex given how noisy the surrounding text is.
        after = text[m.end():].split()
        if after:
            meta["ENGINE_SERIAL_NUMBER"] = _clean_tok(after[0])
    m = _DATE_RE.search(text)
    if m:
        date = m.group(1)
        if date[0] in "lI":  # OCR confusing "1" for "l"/"I" at the start
            date = "1" + date[1:]
        meta["STATUS_DATE"] = date
    return meta


def _split_side(toks: list[str]) -> tuple[str, str, str]:
    if not toks:
        return "", "", ""
    pn = toks[0]
    sn = toks[1] if len(toks) > 1 else ""
    rest = " ".join(toks[2:])
    return pn, sn, rest


def _parse_line(line: str) -> dict | None:
    raw_toks = [_clean_tok(t) for t in line.split()]
    toks = [t for t in raw_toks if t]
    if len(toks) < 3:
        return None
    pn_idx = [i for i, t in enumerate(toks) if _PN_RE.match(t)]
    if not pn_idx:
        return None
    first = pn_idx[0]
    description = " ".join(toks[:first])
    if not description:
        return None
    if len(pn_idx) >= 2:
        second = pn_idx[1]
        incoming_toks = toks[first:second]
        outgoing_toks = toks[second:]
    else:
        incoming_toks = toks[first:]
        outgoing_toks = []
    in_pn, in_sn, in_rest = _split_side(incoming_toks)
    out_pn, out_sn, out_rest = _split_side(outgoing_toks)
    return {
        "DESCRIPTION": description,
        "INCOMING_PART_NUMBER": in_pn,
        "INCOMING_SERIAL_NUMBER": in_sn,
        "INCOMING_STATUS": in_rest,
        "OUTGOING_PART_NUMBER": out_pn,
        "OUTGOING_SERIAL_NUMBER": out_sn,
        "OUTGOING_STATUS": out_rest,
    }


def extract(pdf_path: str) -> list[dict]:
    import pdfplumber

    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            meta = _parse_header(text)
            for raw in text.splitlines():
                rec = _parse_line(raw.strip())
                if rec is None:
                    continue
                for k, v in meta.items():
                    rec[k] = v
                rec["_page"] = page_num
                records.append(rec)
    return records
