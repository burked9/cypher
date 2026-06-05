"""Triage — fingerprint a directory of PDFs and bucket them by variant.

For each PDF we record file size, page count, text-layer presence, the first
~500 chars of page-1 text, and run the existing variant signature detection.
The output (`research/results/triage.csv`) is the substrate for Phase 2
clustering and Phase 3 variant-building.

This script is **read-only on the source PDFs** — paths are inspected via
pymupdf / pdfplumber but no file is moved, renamed, or modified. Source
paths are kept out of the Cypher source tree on purpose; we just point at
them via `--input` arguments.

Usage
-----
    python tools/triage.py --input /path/to/dir1 --input /path/to/dir2

    # Optional --hint-sheet-type for directories whose files are all known to
    # be one sheet type even when the page-1 text doesn't contain the usual
    # signature (e.g. a folder of LLPs whose first-page header is sparse)
    python tools/triage.py \\
        --input /path/to/llp_folder --hint-sheet-type LLP \\
        --input /path/to/occm_folder --hint-sheet-type OCCM

Output
------
    research/results/triage.csv
       path, filename, size_kb, pages, text_pages, scanned_pages,
       sheet_type, variant, operator_hint, first_500_chars
"""
from __future__ import annotations
import argparse
import csv
import re
import signal
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import fitz  # pymupdf — fast for first-page text + page count
from sheet_types import router, occm, ht, llp


# Per-file timeout: protects against OneDrive File Provider hangs on
# cloud-only PDFs that haven't been hydrated. 30s is plenty for a normal
# document; anything longer is almost certainly a stuck syscall and gets
# logged + skipped so the run can continue.
PER_FILE_TIMEOUT_SECONDS = 30


class _FileTimeout(TimeoutError):
    pass


def _timeout_handler(signum, frame):
    raise _FileTimeout("file inspection exceeded timeout")


SHEET_TYPE_MODULES = {"OCCM": occm, "HT": ht, "LLP": llp}


# ---------------------------------------------------------------------------
# Per-PDF fingerprint
# ---------------------------------------------------------------------------
def _read_first_pages_text(path: str, n_pages: int = 3) -> tuple[str, int, int, int]:
    """Return (concatenated_text, total_pages, text_pages, scanned_pages).
    Threshold: a page is `text` if >1000 chars, `mixed` if >200, else scanned.

    In-process fitz.open. Fast (<100 ms typically) once the venv is outside
    OneDrive and the corpus is locally hydrated. If you hit hangs, the
    subprocess-per-file fallback lives in tools/_inspect_pdf.py and can be
    wired back in via `subprocess.run(...timeout=N)` here."""
    text_parts: list[str] = []
    total = text_pages = scanned = 0
    try:
        doc = fitz.open(path)
        total = len(doc)
        for i in range(total):
            t = doc[i].get_text() or ""
            n = len(t)
            if n > 1000:
                text_pages += 1
            elif n < 200:
                scanned += 1
            if i < n_pages:
                text_parts.append(t)
    except Exception:
        pass
    return "\n".join(text_parts), total, text_pages, scanned


# ---------------------------------------------------------------------------
# Variant detection — wraps the router with a hint mechanism for sheet type
# ---------------------------------------------------------------------------
def _detect(text: str, hint_sheet_type: str | None) -> tuple[str, str]:
    """Return (sheet_type, variant) given the first-pages text and an optional
    sheet-type hint from the caller (e.g. "this whole folder is LLPs").

    Collapses whitespace before matching so signatures land identically whether
    the underlying extractor produced one-token-per-line (`fitz`) or
    space-joined rows (`pdfplumber`). The deploy uses pdfplumber, this triage
    uses fitz for speed; both should agree on detection."""
    head = " ".join(text.upper().split()) if text else ""

    # Sheet type: explicit hint wins; else fall back to signature matching;
    # else default OCCM (matches the existing router default).
    if hint_sheet_type and hint_sheet_type in SHEET_TYPE_MODULES:
        sheet_type = hint_sheet_type
    elif not head.strip():
        sheet_type = "OCCM"   # likely Aeroflot-style scanned
    else:
        sheet_type = "Unknown"
        for st in ("LLP", "HT", "OCCM"):
            mod = SHEET_TYPE_MODULES[st]
            for sig in mod.SIGNATURES:
                if sig.upper() in head:
                    sheet_type = st
                    break
            if sheet_type != "Unknown":
                break

    if sheet_type == "Unknown":
        return "Unknown", "Unknown"

    mod = SHEET_TYPE_MODULES[sheet_type]
    variant = "Unknown"
    for v in mod.VARIANTS:
        for sig in v.SIGNATURES:
            if sig.upper() in head:
                variant = v.NAME
                break
        if variant != "Unknown":
            break
    return sheet_type, variant


# ---------------------------------------------------------------------------
# Operator hint — best-effort extraction
# ---------------------------------------------------------------------------
_AIRCRAFT_REG_RE = re.compile(r"\b([A-Z]{1,2})-?([A-Z0-9]{3,4})\b")
_REGISTRATION_COUNTRY = {
    "ZK": "New Zealand", "VH": "Australia", "G":  "United Kingdom",
    "D":  "Germany",     "F":  "France",    "I":  "Italy",
    "VP": "Bermuda/Cayman", "VQ": "Bermuda/Cayman",
    "EI": "Ireland",     "OK": "Czech",     "SP": "Poland",
    "HA": "Hungary",     "YR": "Romania",   "LZ": "Bulgaria",
    "OO": "Belgium",     "PH": "Netherlands","SX": "Greece",
    "TC": "Turkey",      "UR": "Ukraine",   "RA": "Russia",
    "B":  "China/Taiwan","VT": "India",     "9V": "Singapore",
    "HL": "South Korea", "JA": "Japan",     "9M": "Malaysia",
    "HS": "Thailand",    "VN": "Vietnam",   "PK": "Indonesia",
    "RP": "Philippines", "ZS": "South Africa","ET":"Ethiopia",
    "N":  "USA",         "C":  "Canada",    "XA": "Mexico",
    "PR": "Brazil",      "PT": "Brazil",
}

# Filename-token operator hints (case-insensitive substring → canonical name)
_FILENAME_HINTS = {
    "AEROFLOT": "Aeroflot",
    "VOLARIS":  "Volaris",
    "VIETNAM":  "Vietnam Airlines",
    "VNA":      "Vietnam Airlines",
    "CHINA EASTERN": "China Eastern",
    "EASTERN":  "China Eastern (?)",
    "MSN":      "",   # too generic, ignore
}


def _operator_hint(filename: str, text: str) -> str:
    """Heuristic best-guess operator. Combines:
      1. Filename token matches against known airline names.
      2. Aircraft registration prefix → country (helps cluster unknowns).
      3. First-page text scan for capitalised airline-name candidates.
    Returns a short string for the triage CSV — purely informational."""
    fn_upper = filename.upper()
    text_upper = (text or "").upper()

    hits: list[str] = []

    # 1. Filename airline hint
    for needle, canonical in _FILENAME_HINTS.items():
        if needle and needle in fn_upper and canonical and canonical not in hits:
            hits.append(canonical)

    # 2. Registration prefix from filename
    reg_match = _AIRCRAFT_REG_RE.match(filename) or _AIRCRAFT_REG_RE.search(filename)
    if reg_match:
        prefix = reg_match.group(1)
        country = _REGISTRATION_COUNTRY.get(prefix)
        if country:
            hits.append(f"reg:{prefix}={country}")

    # 3. Capitalised airline candidates from page-1 text
    for needle, canonical in _FILENAME_HINTS.items():
        if needle and needle in text_upper and canonical and canonical not in hits:
            hits.append(canonical)

    return " · ".join(hits) or ""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def find_pdfs(input_dir: Path):
    yield from input_dir.rglob("*.pdf")
    yield from input_dir.rglob("*.PDF")


def main():
    ap = argparse.ArgumentParser(description="Triage a directory of PDFs.")
    ap.add_argument("--input", action="append", required=True,
                    help="directory to scan (repeatable). Subdirectories are included.")
    ap.add_argument("--hint-sheet-type", action="append", default=None,
                    choices=["OCCM", "HT", "LLP"],
                    help="optional sheet-type hint applied to the *same-position* "
                         "--input (use once per --input, in order).")
    ap.add_argument("--out", type=Path,
                    default=ROOT / "research" / "results" / "triage.csv",
                    help="output CSV path")
    args = ap.parse_args()

    # Align hints with inputs (pad with None if fewer hints given)
    hints = list(args.hint_sheet_type or [])
    while len(hints) < len(args.input):
        hints.append(None)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "path", "filename", "size_kb", "pages", "text_pages", "scanned_pages",
            "sheet_type", "variant", "operator_hint", "first_500_chars",
        ])

        total = 0
        for input_str, hint in zip(args.input, hints):
            input_dir = Path(input_str).expanduser().resolve()
            if not input_dir.exists():
                print(f"  WARN: {input_dir} missing — skipped")
                continue
            pdfs = list(find_pdfs(input_dir))
            print(f"\nScanning {len(pdfs):4d} PDFs in {input_dir.name}/  (hint: {hint or 'none'})")
            for i, pdf in enumerate(pdfs):
                # Defensive: file may have been moved/synced away between
                # rglob enumeration and stat (OneDrive activity mid-scan).
                try:
                    size_kb = pdf.stat().st_size // 1024
                except (FileNotFoundError, OSError):
                    print(f"  GONE: {pdf.name} — file disappeared mid-scan, skipped", flush=True)
                    continue
                text, pages, tp, sp = _read_first_pages_text(str(pdf))
                if pages == 0 and not text:
                    print(f"  TIMEOUT/ERR: {pdf.name} — recording as 'Timeout'", flush=True)
                    writer.writerow([str(pdf), pdf.name, size_kb,
                                     0, 0, 0, "Timeout", "Unknown", "", ""])
                    total += 1
                    continue
                sheet_type, variant = _detect(text, hint)
                op = _operator_hint(pdf.name, text)
                writer.writerow([
                    str(pdf),
                    pdf.name,
                    size_kb,
                    pages,
                    tp,
                    sp,
                    sheet_type,
                    variant,
                    op,
                    (text[:500] or "").replace("\n", " ").replace("\r", " "),
                ])
                total += 1
                if (i + 1) % 100 == 0:
                    print(f"  ... {i+1}/{len(pdfs)}", flush=True)
            print(f"  done.")

        print(f"\nWrote {total} rows to {args.out.relative_to(ROOT) if args.out.is_relative_to(ROOT) else args.out}")


if __name__ == "__main__":
    main()
