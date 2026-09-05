"""OC/CM Status Report — `OC/CM status <date>` header, position-anchored parse.

Header block (repeated on every page):
    OC/CM status <date>
    <reg> S/N: <msn> FH: <fh> FC: <fc>
    DESCRIPTION P/N S/N ATA POS DATE INSTALLED AIRCRAFT TIME TSI TSN

Confirmed via a direct pdfplumber pass over the real sample file: this PDF
has a genuine text layer (no OCR needed), and `page.extract_text()` renders
one data row per line for the *typical* case, e.g.:

    <desc> <pn> <sn> <ata> <pos> <date> <hrs-at-install> <tsi> <tsn>

But whitespace-splitting that line is NOT reliable, because several fields
are legitimately optional/variable-width in this format:
  - SERIAL_NUMBER can be blank for a row (some assemblies have no S/N).
  - POS can be blank for a row.
  - ATA can be blank entirely — a whole section (aftermarket/engine-vendor
    rows near the end of the real sample) carries no ATA chapter at all.
  - POS itself can be TWO whitespace-separated tokens for that same
    ATA-less section (e.g. an engine-position label made of a word and a
    number, rather than the short single-token position codes used
    elsewhere in the document).
  - DESCRIPTION can itself contain digits (e.g. a temperature-probe class
    designator embedded in the free-text description), which breaks any
    "first token with a digit is the P/N" heuristic.

None of that is expressible as a fixed token count or a left-to-right
regex without misattributing columns on a large fraction of rows. Instead,
this variant reads word-level bounding boxes (`page.extract_words()`) and
buckets each word into a column by its x0 position, using the column
header row's own word x-positions (read fresh per page) as anchors. Words
are first grouped into visual rows by y-position ("top") with a small
tolerance, since two words on the same printed line can differ by a
fraction of a point in reported baseline.

DESCRIPTION / PART_NUMBER / SERIAL_NUMBER are split purely by x-position:
those three column bands are wide and never collide in the real sample.
ATA / POS / DATE_INSTALLED / AIRCRAFT_TIME / TSI / TSN are NOT split by a
fixed x-boundary, because the ATA/POS boundary in particular is too tight
in practice -- a wide multi-token POS value (an alphanumeric position
label with a space in it, e.g. two words) can start printed far enough
left that its first word's x0 lands on the ATA side of any fixed
midpoint boundary, corrupting both fields. Instead, everything from the
S/N column onward is treated as one zone and split using the strongly
distinctive DATE_INSTALLED shape (`DD-Mon-YY`) as the anchor: the date
word is found by regex among that zone's words (sorted left to right),
the three words after it are AIRCRAFT_TIME / TSI / TSN, and within the
words before it, a leading exact 2-digit token is ATA (absent for the
ATA-less section) with everything else joined as POS. This is robust to
every optional-field combination observed in the real sample.

Header metadata (aircraft registration, MSN, report date, flight hours,
flight cycles) is parsed once per page from the two header text lines
above `page.extract_text()`, and the same values are stamped onto every
data row extracted from that page (falling back to the first page's
values for a page where the header line doesn't match, e.g. if page
count metadata ever drifts).

Illustrative-only example values below use placeholder tokens
(<reg>, <msn>, <pn>, <sn>, <ata>, <pos>, <date>, <fh>, <fc>) — never a
real value copied from a corpus file.
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants._base import merged_rules

NAME = "OC/CM Status Report"
SIGNATURES = [
    "OC/CM status",
]

CANONICAL_COLUMNS = [
    "DESCRIPTION",
    "PART_NUMBER",
    "SERIAL_NUMBER",
    "ATA",
    "POS",
    "DATE_INSTALLED",
    "AIRCRAFT_TIME",
    "TSI",
    "TSN",
    # Header metadata -- same on every row of a given file/page.
    "AIRCRAFT_REG",
    "MSN",
    "REPORT_DATE",
    "AIRCRAFT_FH",
    "AIRCRAFT_FC",
]

_HEADER_LABELS = ["DESCRIPTION", "P/N", "S/N", "ATA", "POS", "DATE", "AIRCRAFT", "TSI", "TSN"]

_OVERRIDES = {
    # A whole ATA-less section is legitimate in this format (see module
    # docstring) -- allow_empty keeps that from flagging every row in it.
    "ATA": {"allow_empty": True},
    # Some assemblies genuinely have no serial number recorded.
    "SERIAL_NUMBER": {"allow_empty": True},
    "DATE_INSTALLED": {"pattern": r"^\d{1,2}-[A-Za-z]{3}-\d{2}$"},
    # AIRCRAFT_TIME / TSI / TSN are either a plain integer or the literal
    # "UNKNOWN" (seen throughout the real sample for not-yet-computed
    # time-since-install values).
    "AIRCRAFT_TIME": {"pattern": r"^(?:\d+|UNKNOWN)$"},
    "TSI": {"pattern": r"^(?:\d+|UNKNOWN)$"},
    "TSN": {"pattern": r"^(?:\d+|UNKNOWN)$"},
    "AIRCRAFT_REG": {"pattern": r"^[A-Z0-9\-]+$", "uppercase": True},
    "MSN": {"pattern": r"^\d+$"},
    "REPORT_DATE": {"pattern": r"^\d{2}\.\d{2}\.\d{4}$"},
    "AIRCRAFT_FH": {"pattern": r"^\d+$"},
    "AIRCRAFT_FC": {"pattern": r"^\d+$"},
}
RULES = merged_rules(_OVERRIDES)

# "OC/CM status <date>" -- e.g. "OC/CM status <date>" with <date> in
# DD.MM.YYYY form.
_REPORT_DATE_RE = re.compile(r"OC/CM status\s+(\S+)", re.IGNORECASE)
# "<reg> S/N: <msn> FH: <fh> FC: <fc>"
_REGLINE_RE = re.compile(
    r"^(?P<reg>\S+)\s+S/N:\s*(?P<msn>\S+)\s+FH:\s*(?P<fh>\S+)\s+FC:\s*(?P<fc>\S+)",
    re.MULTILINE,
)
_FOOTER_RE = re.compile(r"^\d+\s+of\s+\d+$")
_DATE_TOKEN_RE = re.compile(r"^\d{1,2}-[A-Za-z]{3}-\d{2}$")
_ATA_TOKEN_RE = re.compile(r"^\d{2}$")


def _parse_header_metadata(text: str) -> dict:
    """Extract report date + reg/msn/fh/fc from a page's plain text.
    Returns only the keys it actually found (caller merges over defaults)."""
    out = {}
    m = _REPORT_DATE_RE.search(text)
    if m:
        out["REPORT_DATE"] = m.group(1)
    m = _REGLINE_RE.search(text)
    if m:
        out["AIRCRAFT_REG"] = m.group("reg")
        out["MSN"] = m.group("msn")
        out["AIRCRAFT_FH"] = m.group("fh")
        out["AIRCRAFT_FC"] = m.group("fc")
    return out


def _column_starts(words: list[dict]) -> dict[str, dict] | None:
    """Return {label: word} for the column-header row's words (so callers
    can read both x0 and x1), or None if the header row isn't present on
    this page (e.g. a truncated/odd page)."""
    starts: dict[str, dict] = {}
    for w in words:
        if w["text"] in _HEADER_LABELS and w["text"] not in starts:
            starts[w["text"]] = w
    if len(starts) < len(_HEADER_LABELS):
        return None
    return starts


def _cluster_rows(words: list[dict], y_tol: float = 3.0) -> list[list[dict]]:
    """Group words into visual rows by y-position ("top"), tolerant of the
    small per-glyph baseline jitter pdfplumber reports within one printed
    line."""
    words = sorted(words, key=lambda w: w["top"])
    rows: list[list[dict]] = []
    current: list[dict] = []
    ref_top: float | None = None
    for w in words:
        if ref_top is None or abs(w["top"] - ref_top) <= y_tol:
            current.append(w)
            if ref_top is None:
                ref_top = w["top"]
        else:
            rows.append(current)
            current = [w]
            ref_top = w["top"]
    if current:
        rows.append(current)
    return rows


def _extract_page_records(page, defaults: dict) -> tuple[list[dict], dict]:
    """Parse one page. Returns (records, updated_defaults) — `defaults` are
    the header-metadata values to stamp on rows and to carry forward to the
    next page if this page's own header line doesn't match."""
    text = page.extract_text() or ""
    found = _parse_header_metadata(text)
    metadata = dict(defaults)
    metadata.update(found)

    words = page.extract_words()
    starts = _column_starts(words)
    if starts is None:
        return [], metadata

    # x-position boundaries for the wide, never-colliding left-hand columns.
    # Everything at or past b3 (S/N's right edge midpointed with ATA's left
    # edge) is handled by the date-anchored logic below instead of a fixed
    # per-column boundary -- see module docstring for why.
    b1 = (starts["DESCRIPTION"]["x1"] + starts["P/N"]["x0"]) / 2
    b2 = (starts["P/N"]["x1"] + starts["S/N"]["x0"]) / 2
    b3 = (starts["S/N"]["x1"] + starts["ATA"]["x0"]) / 2

    header_top = starts["DESCRIPTION"]["top"]

    records: list[dict] = []
    for row in _cluster_rows(words):
        row = sorted(row, key=lambda w: w["x0"])
        row_top = row[0]["top"]
        if abs(row_top - header_top) <= 1:
            continue  # the column-header row itself
        joined = " ".join(w["text"] for w in row)
        if joined.upper().startswith("OC/CM STATUS"):
            continue
        if _FOOTER_RE.match(joined):
            continue
        if "S/N:" in joined and "FH:" in joined and "FC:" in joined:
            continue  # the reg/msn/fh/fc line

        desc, pn, sn, rest = [], [], [], []
        for w in row:
            if w["x0"] < b1:
                desc.append(w)
            elif w["x0"] < b2:
                pn.append(w)
            elif w["x0"] < b3:
                sn.append(w)
            else:
                rest.append(w)
        if not desc and not pn:
            continue

        date_idx = next((i for i, w in enumerate(rest) if _DATE_TOKEN_RE.match(w["text"])), None)
        if date_idx is None:
            # No recognisable install date on this line -- can't anchor the
            # tail fields reliably. Skip rather than guess; this hasn't been
            # observed on the real sample but protects against a stray
            # unmatched line (e.g. a page footnote) being misread as a row.
            continue
        pre = rest[:date_idx]
        date_word = rest[date_idx]
        post = rest[date_idx + 1:]

        ata = ""
        pos_words = pre
        if pre and _ATA_TOKEN_RE.match(pre[0]["text"]):
            ata = pre[0]["text"]
            pos_words = pre[1:]

        rec = {
            "DESCRIPTION": " ".join(w["text"] for w in desc),
            "PART_NUMBER": " ".join(w["text"] for w in pn),
            "SERIAL_NUMBER": " ".join(w["text"] for w in sn),
            "ATA": ata,
            "POS": " ".join(w["text"] for w in pos_words),
            "DATE_INSTALLED": date_word["text"],
            "AIRCRAFT_TIME": post[0]["text"] if len(post) > 0 else "",
            "TSI": post[1]["text"] if len(post) > 1 else "",
            "TSN": " ".join(w["text"] for w in post[2:]) if len(post) > 2 else "",
        }
        for k in ("AIRCRAFT_REG", "MSN", "REPORT_DATE", "AIRCRAFT_FH", "AIRCRAFT_FC"):
            rec[k] = metadata.get(k, "")
        records.append(rec)

    return records, metadata


def extract(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    defaults = {"AIRCRAFT_REG": "", "MSN": "", "REPORT_DATE": "",
                "AIRCRAFT_FH": "", "AIRCRAFT_FC": ""}
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_records, defaults = _extract_page_records(page, defaults)
            records.extend(page_records)
    return records
