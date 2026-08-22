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

    # Skip the two heavier optional passes (see below) for a fast first look
    python tools/triage.py --input /path/to/dir --skip-l2-check --skip-ocr-fallback

Output
------
    research/results/triage.csv
       path, filename, size_kb, pages, text_pages, scanned_pages,
       sheet_type, variant, operator_hint, text_source, first_500_chars,
       l2_kept_rows, l2_dropped_rows, l2_candidate

Two optional passes beyond the original fingerprint (both on by default):

  - L2-candidate check (l2_kept_rows / l2_dropped_rows / l2_candidate):
    re-runs pdfplumber's table extraction and, using the *exact* same
    `_is_data_row` gate `levels/L1_text/extract.py` uses, tallies rows that
    got kept vs. rows that got silently dropped despite holding real text.
    A dropped-but-non-trivial row is the fingerprint of a wrapped
    DESCRIPTION becoming its own orphan row -- L1 quietly loses that text
    today, with no error and no flag. `l2_candidate=True` means this file
    is losing description text right now. Caveat: this checks the *generic*
    L1 pattern (pdfplumber table grid + ATA/ZONE gate). Variants with
    bespoke extraction logic that doesn't go through this path won't be
    accurately represented by it -- treat a False here as "not flagged by
    this check," not "definitely has no row-splitting issue."
    Only runs for rows with a known sheet_type and a real text layer
    (meaningless for scanned/Unknown files) -- skip with --skip-l2-check.

  - Scanned-file OCR header fallback (text_source=ocr_header): without
    this, a scanned/no-text file gets an empty first_500_chars, and the
    trigram clustering in triage_analyse.py returns cosine=0 for any two
    empty bags -- meaning scanned files can *never* cluster with each
    other no matter how similar their letterheads actually are, silently
    defeating the whole point of clustering for that subset. This OCRs
    just the top 35% of page 1 (cheap, ~200dpi) to give scanned files a
    real clustering signal instead. Skip with --skip-ocr-fallback (faster,
    but scanned files will cluster poorly/not at all).
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
from levels.L1_text.extract import _is_data_row


# Per-file timeout: protects against OneDrive File Provider hangs on
# cloud-only PDFs that haven't hydrated. This is a *second* line of defense
# behind `_is_materialized()` below (which catches the common case -- a
# placeholder with zero allocated disk blocks -- near-instantly via stat(),
# no hang possible) for anything that looks materialized but still stalls
# (a mid-transfer file, a slow network mount, a genuinely pathological PDF).
# 30s is plenty for a normal document; anything longer gets logged + skipped
# so the run can continue.
PER_FILE_TIMEOUT_SECONDS = 30


class _FileTimeout(TimeoutError):
    pass


def _timeout_handler(signum, frame):
    raise _FileTimeout("file inspection exceeded timeout")


def _is_materialized(path: Path) -> bool:
    """OneDrive Files-On-Demand leaves cloud-only files with a real st_size
    but zero allocated disk blocks until something reads them and forces
    hydration -- reading one blind can hang for the duration of a real
    download. Checking st_blocks (same signal `ls -ls` shows) costs one
    stat() call and never touches file content, so it can't hang."""
    try:
        st = path.stat()
        return st.st_size == 0 or st.st_blocks > 0
    except OSError:
        return False


SHEET_TYPE_MODULES = {"OCCM": occm, "HT": ht, "LLP": llp}


# ---------------------------------------------------------------------------
# Per-PDF fingerprint
# ---------------------------------------------------------------------------
def _read_first_pages_text(path: str, n_pages: int = 3) -> tuple[str, int, int, int]:
    """Return (concatenated_text, total_pages, text_pages, scanned_pages).
    Threshold: a page is `text` if >1000 chars, `mixed` if >200, else scanned.

    In-process fitz.open. Fast (<100 ms typically) once the venv is outside
    OneDrive and the corpus is locally hydrated. Armed with a SIGALRM
    timeout (see PER_FILE_TIMEOUT_SECONDS) as a second line of defense
    behind the st_blocks pre-check -- for anything that looks materialized
    but still stalls on read. If you hit hangs even with both, the
    subprocess-per-file fallback lives in tools/_inspect_pdf.py."""
    text_parts: list[str] = []
    total = text_pages = scanned = 0
    old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(PER_FILE_TIMEOUT_SECONDS)
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
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)
    return "\n".join(text_parts), total, text_pages, scanned


# ---------------------------------------------------------------------------
# L2-candidate check — see module docstring for what this measures and why
# ---------------------------------------------------------------------------
def _count_row_drop(pdf_path: str) -> tuple[int, int]:
    """Returns (kept, dropped) using the exact `_is_data_row` gate
    `levels/L1_text/extract.py` uses. Returns (-1, -1) on any failure so
    callers can tell "couldn't check" apart from "checked, found 0"."""
    import pdfplumber
    kept = dropped = 0
    old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(PER_FILE_TIMEOUT_SECONDS)
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                for table in page.extract_tables() or []:
                    for row in table:
                        cells = [(c or "").strip() for c in row]
                        if _is_data_row(cells):
                            kept += 1
                        elif sum(len(c) for c in cells) >= 8:
                            dropped += 1
    except Exception:
        return -1, -1
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)
    return kept, dropped


# ---------------------------------------------------------------------------
# Scanned-file OCR header fallback — see module docstring for why
# ---------------------------------------------------------------------------
def _ocr_header_fallback(path: str, dpi: int = 200) -> str:
    """OCRs just the top 35% of page 1 -- cheap, and enough letterhead/title
    text for trigram clustering to have something real to work with. Not
    trying to hit a specific anchor phrase (unlike e.g. aeroflot.py's
    ocr_detect) -- just need *some* representative text per file."""
    try:
        import pytesseract
        from PIL import Image
        doc = fitz.open(path)
        page = doc[0]
        pix = page.get_pixmap(dpi=dpi)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        header = img.crop((0, 0, img.width, int(img.height * 0.35)))
        return pytesseract.image_to_string(header)[:500]
    except Exception:
        return ""


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
    ap.add_argument("--skip-l2-check", action="store_true",
                    help="skip the pdfplumber row-drop pass (faster, no l2_candidate signal)")
    ap.add_argument("--skip-ocr-fallback", action="store_true",
                    help="skip page-1 OCR for scanned files (faster, but they won't cluster)")
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
            "sheet_type", "variant", "operator_hint", "text_source", "first_500_chars",
            "l2_kept_rows", "l2_dropped_rows", "l2_candidate",
        ])

        total = not_downloaded = 0
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

                # Cheap, hang-proof pre-check -- OneDrive cloud-only files
                # get skipped instantly instead of attempted (see
                # _is_materialized's docstring). Re-run this tool later once
                # more of the download has landed to pick these up.
                if not _is_materialized(pdf):
                    writer.writerow([str(pdf), pdf.name, size_kb, 0, 0, 0,
                                     "NotDownloaded", "Unknown", "", "", "",
                                     "", "", ""])
                    total += 1
                    not_downloaded += 1
                    continue

                text, pages, tp, sp = _read_first_pages_text(str(pdf))
                if pages == 0 and not text:
                    print(f"  TIMEOUT/ERR: {pdf.name} — recording as 'Timeout'", flush=True)
                    writer.writerow([str(pdf), pdf.name, size_kb, 0, 0, 0,
                                     "Timeout", "Unknown", "", "", "",
                                     "", "", ""])
                    total += 1
                    continue

                sheet_type, variant = _detect(text, hint)
                op = _operator_hint(pdf.name, text)

                # Scanned files get an OCR'd header instead of empty text,
                # so clustering has something real to compare (see docstring).
                text_source = "real"
                display_text = text
                if tp == 0 and sp > 0 and not args.skip_ocr_fallback:
                    ocr_text = _ocr_header_fallback(str(pdf))
                    if ocr_text.strip():
                        display_text = ocr_text
                        text_source = "ocr_header"

                # L2-candidate check -- only meaningful for known sheet
                # types with a real text layer (see docstring). kept==0
                # alongside dropped>0 means the generic ATA/ZONE pattern
                # didn't match this file's rows *at all* -- almost always
                # because the variant has its own bespoke extractor that
                # doesn't go through this path (confirmed on the very first
                # smoke test: an AMOS file showed kept=0/dropped=1092, not
                # because it's losing text, but because AMOS's real
                # extraction logic isn't the generic pattern this checks).
                # That's noise, not an L2 finding -- only kept>0 AND
                # dropped>0 (most rows working, some genuinely lost) is a
                # real signal, so it gets its own "n/a" bucket instead of
                # being lumped in with either True or False.
                kept = dropped = candidate = ""
                if sheet_type != "Unknown" and tp > 0 and not args.skip_l2_check:
                    kept, dropped = _count_row_drop(str(pdf))
                    if kept == -1:
                        pass  # couldn't check -- leave blank
                    elif kept == 0 and dropped > 0:
                        candidate = "n/a"
                    else:
                        candidate = str(dropped > 0)

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
                    text_source,
                    (display_text[:500] or "").replace("\n", " ").replace("\r", " "),
                    kept,
                    dropped,
                    candidate,
                ])
                total += 1
                if (i + 1) % 100 == 0:
                    print(f"  ... {i+1}/{len(pdfs)}", flush=True)
            print(f"  done.")

        print(f"\nWrote {total} rows to {args.out.relative_to(ROOT) if args.out.is_relative_to(ROOT) else args.out}")
        if not_downloaded:
            print(f"  {not_downloaded} not yet downloaded (OneDrive cloud-only) — "
                  f"re-run once the sync catches up to pick these up.")


if __name__ == "__main__":
    main()
