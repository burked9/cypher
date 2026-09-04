"""AAR Landing Gear Services -- "Serialized List" (Exchange & Overhaul).

Source format: a landing-gear teardown parts breakdown from an overhaul
shop, headed "Exchange & Overhaul" with a "TRACKING#: <n> Serialized List"
line repeated on every page. The header block also carries the top
assembly's P/N, S/N, work order and the aircraft it came off, but that
metadata is deliberately NOT captured here -- see the commercially
sensitive data note below.

Row format (single line, space-separated):

    <tracking#> <part name...> <part number> <serial number> <work order> \
<last operator...> <a/c reg> <life limit> <csn>

    <tracking#> LH MLG INSTALLATION <pn> <sn> <wo> <operator> \
<reg> 50,000 SEE LIST
    NN LH BUILDUP ASSY <pn> <sn> <wo> <operator> <reg> \
50,000 SEE LIST
    <tracking#> BRAKE ATTACH PIN <pn> <sn> <wo> <operator> <reg> \
UNLIMITED N/A

TRACKING_NUMBER is a 6-7 digit id, or the literal "NN" (no tracking number
assigned to that sub-part). It occasionally lands split across a stray
space from the source PDF (e.g. two digit groups split by a stray space
that reassemble into one tracking number) -- both digit tokens
are rejoined when neither carries a letter.

WORK_ORDER is normally a bare number, but a handful of rows (repair/
fabrication line items) show "PO <n>" instead.

LAST_OPERATOR is a free-text airline/operator name (1-2 words, occasionally
with periods, e.g. an abbreviated carrier name) followed by an A/C_REG
token (a registration, or "N/A" on repair-order rows that were never
installed on an aircraft).

LIFE_LIMIT is a thousands-comma cycle count, or "UNLIMITED" -- the source
renders this with a garbled trailing character on several rows ("UNLIMITEO",
"UNLIMITE'J", "UNLIMITEP", etc.), normalized here to a clean "UNLIMITED".
CSN is a thousands-comma cycle count, the literal "SEE LIST" (assembly-level
rows -- see the sub-parts instead), "N/A" (its OCR-ish misread "NIA" is
normalized to "N/A"), or "-0-" (seen on freshly fabricated/repaired parts
with no accumulated cycles).

The text layer also carries a handful of junk tokens with no data content:
a vertical rule/watermark on the source page bleeds into the extracted text
as stray single-character tokens (stray "I"/"i"/"j"/"!"/"'" etc., sometimes
several run together into one word like "iI'") at essentially arbitrary
positions in a row. These match no real field (every real field here is
multi-character) and are dropped before the row is split into columns.

One row per file (out of ~60) shows a garbled LIFE_LIMIT value bleeding in
from an unrelated overlapping mark on the page -- it fails the numeric/
UNLIMITED pattern and is flagged rather than guessed at.

A separate "MODIFICATIONS / PRE P/N / SUBMITTALS / REMARKS" mini-block
appears inline after a handful of rows for parts that were sent out
unserviceable ("U/S") and repaired under a purchase order -- e.g.:

    <p/n> us <s/n> PO <n> <repair facility> N/A <life limit> <csn>
    MODIFICATIONS  PRE P/N  SUBMITTALS  REMARKS
    N/A  <p/n> U/S  N/A  N/A

The first line is a normal (if slightly irregular) data row -- its "us"
token is folded into PART_NUMBER as a " U/S" suffix. The follow-on
MODIFICATIONS/PRE-P/N/SUBMITTALS/REMARKS block is a restatement, not a new
part; its lines don't match the row shape (no tracking number / part
number pair at the front) and are simply skipped.

CRITICAL -- commercially sensitive data: do not add the sample file's real
tracking numbers, work order numbers, serial numbers, aircraft
registration, or operator/customer names to this file. Every example value
above is genericized.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.llp_variants._base import merged_rules

NAME = "AAR Landing Gear Serialized List"
SIGNATURES = [
    "Serialized List",
    "LANDING GEAR SERVICES",
]

CANONICAL_COLUMNS = [
    "TRACKING_NUMBER",
    "PART_NAME",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "WORK_ORDER",
    "LAST_OPERATOR",
    "AC_REG",
    "LIFE_LIMIT",
    "CSN",
]

_CYCLE_RULE = {"pattern": r"^[\d,]+$", "int_range": (0, 60000)}
_OVERRIDES = {
    "TRACKING_NUMBER": {"pattern": r"^(NN|\d+)$", "uppercase": True},
    "PART_NAME":       {"uppercase": True},
    "PART_NUMBER":      # base already has char_map/uppercase/etc.; only the
                        # pattern + no_spaces need loosening for the " U/S"
                        # suffix and the "/" some PNs carry (e.g. "...-1/8").
        {"pattern": r"^[A-Z0-9][A-Z0-9\-/]*(?: U/S)?$", "no_spaces": False},
    "WORK_ORDER":      {"pattern": r"^(PO \d+|\d+)$", "uppercase": True},
    "LAST_OPERATOR":   {"pattern": r"^[A-Z0-9.\- ]+$", "uppercase": True},
    "AC_REG":          {"pattern": r"^(N/A|[A-Z0-9\-]+)$", "uppercase": True},
    "LIFE_LIMIT":      {"pattern": r"^(UNLIMITED|[\d,]+)$", "uppercase": True},
    "CSN":             {"pattern": r"^(SEE LIST|N/A|-0-|[\d,]+)$",
                         "uppercase": True},
}
RULES = merged_rules(_OVERRIDES)

# Part number: leading alnum, then alnum/-//, e.g. "161X0000-123",
# "161X1214-4-1/8". Requires a dash so ordinary PART_NAME words never match.
_PN_RE = re.compile(r"^\d[\dA-Za-z]*-[\w/-]+$")
_US_RE = re.compile(r"^u/?s$", re.I)
_UNLIMITED_RE = re.compile(r"^UNLIMITE\S*$", re.I)
_NIA_RE = re.compile(r"^N/?A$|^NIA$", re.I)

# Stray tokens from a vertical rule/watermark bleeding into the text layer.
# No real field in this row shape is ever a single character, so any
# 1-character token is junk; longer junk runs are made up only of these
# characters (occasionally merged into one word, e.g. "iI'").
_JUNK_CHARS_RE = re.compile(r"^[iIjlt!'\[\]:;.,`\"]+$")


def _is_junk(tok: str) -> bool:
    return len(tok) == 1 or bool(_JUNK_CHARS_RE.match(tok))


def _normalize_life_limit(v: str) -> str:
    if _UNLIMITED_RE.match(v):
        return "UNLIMITED"
    return v


def _normalize_csn(v: str) -> str:
    if _NIA_RE.match(v) and v.upper() != "N/A":
        return "N/A"
    return v


def _parse_row(line: str) -> dict | None:
    toks = [t for t in line.strip().split() if not _is_junk(t)]
    if len(toks) < 8:
        return None

    if toks[0].upper() == "NN":
        tracking = "NN"
        i = 1
    elif toks[0].isdigit() and len(toks) > 1 and toks[1].isdigit() and len(toks[1]) >= 4:
        tracking = toks[0] + toks[1]
        i = 2
    elif toks[0].isdigit():
        tracking = toks[0]
        i = 1
    else:
        return None
    if len(toks) - i < 6:
        return None

    # CSN is "SEE LIST" (2 tokens) on assembly-level rows, otherwise a
    # single token -- everything else is anchored from the right of that.
    if len(toks) >= 2 and toks[-2].upper() == "SEE" and toks[-1].upper() == "LIST":
        csn = "SEE LIST"
        life_limit = toks[-3]
        ac_reg = toks[-4]
        rest = toks[i:-4]
    else:
        csn = _normalize_csn(toks[-1])
        life_limit = toks[-2]
        ac_reg = toks[-3]
        rest = toks[i:-3]

    pn_idx = next((j for j, t in enumerate(rest) if _PN_RE.match(t)), None)
    if pn_idx is None:
        return None
    part_name = " ".join(rest[:pn_idx])
    part_number = rest[pn_idx]
    j = pn_idx + 1
    if j < len(rest) and _US_RE.match(rest[j]):
        part_number += " U/S"
        j += 1
    if j >= len(rest):
        return None
    serial = rest[j]
    j += 1
    remainder = rest[j:]
    if not remainder:
        return None
    if remainder[0].upper() == "PO" and len(remainder) >= 2:
        work_order = "PO " + remainder[1]
        operator_toks = remainder[2:]
    else:
        work_order = remainder[0]
        operator_toks = remainder[1:]
    if not operator_toks:
        return None
    operator = " ".join(operator_toks)

    return {
        "TRACKING_NUMBER": tracking,
        "PART_NAME": part_name,
        "PART_NUMBER": part_number,
        "SERIAL_NUMBER": serial,
        "WORK_ORDER": work_order,
        "LAST_OPERATOR": operator,
        "AC_REG": ac_reg,
        "LIFE_LIMIT": _normalize_life_limit(life_limit),
        "CSN": csn,
    }


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if len(text) < 50:
                continue
            for raw in text.splitlines():
                rec = _parse_row(raw)
                if rec is None:
                    continue
                rec["_page"] = page_num
                records.append(rec)
    return records
