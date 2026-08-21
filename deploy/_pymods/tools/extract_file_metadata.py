"""Read each routed OCCM PDF's header (page 1, fallback page 2) and extract
aircraft identity: registration, MSN, model string, derived family, report
date. Produces a metadata table the positions DB joins on `source_file`.

Family is derived ONLY from the header MODEL string — never from the filename,
because filename tokens like "A350"/"A359" are tail/fin labels, not the
airframe family (confirmed: VN-A359's header model is `321-231`, an A321).

Output:
    research/results/file_metadata.csv   (+ /tmp backup)
    Files we can't confidently classify get family="Unknown" and a
    header_snippet so they can be reviewed/matched by hand.
"""
from __future__ import annotations
import csv, io, re, os, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
EVALSP = pathlib.Path("/Users/danielburke/Library/CloudStorage/OneDrive-Personal/work/KEEL_aviation_records/evalsp")

import pdfplumber

# ---- model → family --------------------------------------------------------
# Search the header text for a model token, then map to family. Patterns are
# ordered most-specific first. We accept optional leading "A"/"B" and the
# common "NNN-NNN" / "NNN-NNN-ER" suffixes.
# On a MODEL/TYPE line we accept the bare "3NN" form (e.g. "330-243").
_AIRBUS_RE = re.compile(r"\bA?3(18|19|20|21|30|40|50|80)\b")
# Anywhere in the header we only trust the A-prefixed form ("A330"), which is
# a real model token; a bare "350" could be a page range or part number, and
# "VN-A350" is a registration (masked before this runs).
_AIRBUS_APREFIX_RE = re.compile(r"\bA3(18|19|20|21|30|40|50|80)\b")
_BOEING_RE = re.compile(r"\bB?7(37|47|57|67|77|87)\b")
_EMBRAER_RE = re.compile(r"\b(ERJ\s?1[79]0|E1[79]0|EMB[- ]?1[79]\d)\b", re.I)

_FAMILY_FROM_AIRBUS = {
    "18": "A320 family", "19": "A320 family", "20": "A320 family", "21": "A320 family",
    "30": "A330", "40": "A340", "50": "A350", "80": "A380",
}

# Manual MSN → family overrides for files where the header carries no model
# token at all but the airframe is known to the user. Applied after automated
# extraction. Keep keys as strings, exactly as MSN appears in the header.
_MANUAL_MSN_FAMILY = {
    "30875": ("B777", "B777-200ER"),       # 9V-SQJ Singapore Airlines, user-confirmed
    "4174":  ("A320 family", "A320-232"),  # HA-LPZ Wizz Air, fixes B747 false positive
    "1541":  ("A320 family", "A319-112"),  # B-2215 China Eastern (D-AVWI delivery), user-confirmed
}

# Lines that plausibly carry the model. We look at these first to avoid
# matching a stray 3-digit number elsewhere on the page. Includes "A/C:",
# "AIRCRAFT" and "BOEING" because operators commonly carry the model after
# any of those (e.g. `OCCM AIRCRAFT 767-300ER`, `BOEING 737-73S`).
_MODEL_LINE_RE = re.compile(
    r"(MODEL|TYPE|M\s?O\s?D\s?E\s?L|A\s?/\s?C\s*:|\bAIRCRAFT\b|\bBOEING\b)", re.I)
# Boeing model in dash-suffix form (`737-700`, `767-200`, `B737-800`). Also
# accepts alphanumeric variant codes (`767-300ER`, `767-3Q8ER`, `737-73S`).
# Use a non-word lookahead instead of `\b` so the regex doesn't fail when the
# token continues with letters (`...300ER`).
# Real Boeing dash-suffix variants:
#   737-700 / 737-86N / 767-300ER / 767-3Q8ER / 747-400 / 777-300ER.
# A valid suffix is up to 3 digits, optionally followed by 1-4 letters/digits
# (variant code). This explicitly rules out 5+ digit codes like `747-06209`
# (a task-card reference that previously misclassified MSN 4174 as B747).
_BOEING_DASH_RE = re.compile(
    r"\bB?7(37|47|57|67|77|87)-[0-9]{1,3}(?![0-9])[0-9A-Z]{0,5}(?:[^A-Z0-9]|$)")
# Bare `B777` / `B737` / `B767` etc. — reliable Boeing model token with the
# explicit B prefix, no dash required. Catches files like the 9V-SQJ Annex 8
# where rows say "4100945B B777 HS PBH: FAN…" (the 777 appears per-row).
_BOEING_BPREFIX_RE = re.compile(r"\bB7(37|47|57|67|77|87)\b")

# Registration: standard ICAO-ish tail forms.
_REG_RE = re.compile(
    r"\b(N\d{1,5}[A-Z]{0,2}|[A-Z]{1,2}-[A-Z]{2,5}|[A-Z]{2}-[A-Z0-9]{3,4})\b")
_REG_LABEL_RE = re.compile(
    r"(?:A\s*/?\s*C\s*)?REG(?:ISTRATION)?\s*[:.]?\s*", re.I)

# MSN / serial labels (tolerate letter-spacing like "S E R I A L #")
_MSN_LABEL_RE = re.compile(
    r"(?:MSN|SERIAL\s*(?:NUMBER|NO|#)?|S\s?/\s?N|S\s?E\s?R\s?I\s?A\s?L)\s*[:#.]?\s*", re.I)
_MSN_VAL_RE = re.compile(r"\b(\d{3,6})\b")

_DATE_RE = re.compile(
    r"\b("
    # Existing: D-Mon-YYYY, D/MM/YYYY, MonthName DD, YYYY
    r"\d{1,2}[-/][A-Za-z]{3,8}[-/.]?\d{2,4}"
    r"|\d{1,2}[-/]\d{1,2}[-/]\d{2,4}"
    r"|[A-Z][a-z]{2,8}\s+\d{1,2},?\s+\d{4}"
    # New: DD.Mon.YYYY (dotted, AMOS / Aircraft Rotables / Aegean ERJ)
    r"|\d{1,2}\.[A-Za-z]{3,4}\.\d{4}"
    # New: DDmonYYYY no-separator (OASES — also Portuguese/Spanish months)
    r"|\d{1,2}[A-Za-z]{3,4}\d{4}"
    # New: ISO YYYY-MM-DD (TAP Compact)
    r"|\d{4}-\d{2}-\d{2}"
    # New: DD.MM.YYYY pure numeric dotted (Aircraft Spec File)
    r"|\d{1,2}\.\d{1,2}\.\d{4}"
    # New: DD Mon YY space-separated (B777 Annex 8 "28 Mar 18")
    r"|\d{1,2}\s+[A-Za-z]{3}\s+\d{2,4}"
    r")\b")


def _collapse_spaced(text: str) -> str:
    """Collapse letter-spaced headers: 'M O D E L' -> 'MODEL' on a per-line
    basis where a run of single chars appears. Conservative: only joins runs
    of 1-char tokens."""
    out_lines = []
    for ln in text.splitlines():
        toks = ln.split()
        merged = []
        buf = []
        for t in toks:
            if len(t) == 1 and t.isalpha():
                buf.append(t)
            else:
                if len(buf) >= 3:
                    merged.append("".join(buf))
                else:
                    merged.extend(buf)
                buf = []
                merged.append(t)
        if len(buf) >= 3:
            merged.append("".join(buf))
        else:
            merged.extend(buf)
        out_lines.append(" ".join(merged))
    return "\n".join(out_lines)


def derive_family(text: str) -> tuple[str, str, str]:
    """Return (family, model_raw, confidence).

    PRECISION-FIRST. We only classify off an explicit MODEL/TYPE header line,
    and we mask out any registration token on that line first — otherwise a
    tail like `VN-A350` would be misread as an A350 airframe (it isn't), and
    body text like `pages 350-389` would generate spurious matches. Files
    without a clean model line are left Unknown for human review rather than
    guessed.
    """
    norm = _collapse_spaced(text)

    # Tier 1 — explicit MODEL/TYPE line (reg-masked). Highest trust; accepts
    # the bare "330-243" Boeing/Airbus form.
    model_lines = [ln for ln in norm.splitlines() if _MODEL_LINE_RE.search(ln)]
    for ln in model_lines:
        masked = _REG_RE.sub(" ", ln)
        m = _AIRBUS_RE.search(masked)
        if m:
            return _FAMILY_FROM_AIRBUS[m.group(1)], m.group(0), "high"
        m = _BOEING_RE.search(masked)
        if m:
            return f"B7{m.group(1)}", m.group(0), "high"
        m = _EMBRAER_RE.search(masked)
        if m:
            return "Embraer", m.group(0), "high"

    # Tier 2 — A-prefixed Airbus / Boeing-dash / Embraer token anywhere in the
    # header (reg-masked). "A330" and "737-700" are unambiguous model tokens;
    # recovers files whose header has no literal "MODEL" label (Cathay column
    # layout, OASES data row, etc.).
    masked_all = _REG_RE.sub(" ", norm)
    m = _AIRBUS_APREFIX_RE.search(masked_all)
    if m:
        return _FAMILY_FROM_AIRBUS[m.group(1)], "A3" + m.group(1), "medium"
    m = _BOEING_DASH_RE.search(masked_all)
    if m:
        return f"B7{m.group(1)}", m.group(0), "medium"
    m = _BOEING_BPREFIX_RE.search(masked_all)
    if m:
        return f"B7{m.group(1)}", "B7" + m.group(1), "medium"
    m = _EMBRAER_RE.search(masked_all)
    if m:
        return "Embraer", m.group(0), "medium"
    return "Unknown", "", "none"


def extract_registration(text: str) -> str:
    """Extract a tail-number / registration from the header. Tries labelled
    forms first (`Registration: VN-A350`, `A/C: PK-CMJ`), then falls back to
    an UNlabelled scan when a registration pattern appears in the first few
    lines (covers AMOS/Aegean style `HZ-AEE (HZ-AEE EMBRAER-170)`)."""
    norm = _collapse_spaced(text)
    lines = norm.splitlines()[:12]
    # 1. Labelled lookup
    for ln in lines:
        m = _REG_LABEL_RE.search(ln)
        if m:
            rest = ln[m.end():]
            rm = _REG_RE.search(rest)
            if rm:
                return rm.group(1).upper()
    # 2. Fallback: any registration token in the first 12 lines. Filter out
    #    PN-like tokens by requiring a hyphenated form with a country prefix
    #    (the existing _REG_RE already enforces XX-YYY shape).
    for ln in lines:
        # Skip lines that look like column headers (Common false-positive source).
        if re.search(r"\b(PART|SERIAL|DESCRIPTION|ATA|REPORT)\b", ln, re.I):
            continue
        rm = _REG_RE.search(ln)
        if rm:
            return rm.group(1).upper()
    return ""


def extract_msn(text: str) -> str:
    norm = _collapse_spaced(text)
    for ln in norm.splitlines()[:12]:
        m = _MSN_LABEL_RE.search(ln)
        if m:
            rest = ln[m.end():]
            vm = _MSN_VAL_RE.search(rest)
            if vm:
                return vm.group(1)
    return ""


# Unicode dash variants that we normalise to ASCII before date matching.
# Some PDFs (A330 Engineering Planning, others) emit U+2010 instead of `-`.
_UNICODE_DASHES = str.maketrans({"‐":"-","‑":"-","–":"-",
                                 "—":"-","−":"-"})


def extract_report_date(text: str) -> str:
    """Scan a PDF's first ~3000 chars for a report date and return the raw
    matched string. Looks first on lines mentioning DATE/REPORT/AS OF, then
    falls back to a broader window. Normalises Unicode hyphens so they don't
    block the regex."""
    text = text.translate(_UNICODE_DASHES)
    # 1. Preferred: a line that says DATE/REPORT/AS OF and has a date on it.
    for ln in text.splitlines()[:20]:
        if re.search(r"\b(DATE|REPORT|AS\s+OF|VALID\s+AS\s+OF|REFERENCE|UPDATED|dd)\b",
                     ln, re.I):
            dm = _DATE_RE.search(ln)
            if dm:
                return dm.group(1)
    # 2. Fallback: any date in the first 3000 chars (widened from 600 —
    #    many headers carry the date deep in the title-page block).
    dm = _DATE_RE.search(text[:3000])
    return dm.group(1) if dm else ""


def read_header(path: str, max_pages: int = 2) -> str:
    parts = []
    try:
        with pdfplumber.open(path) as pdf:
            for p in pdf.pages[:max_pages]:
                parts.append(p.extract_text() or "")
                if sum(len(x) for x in parts) > 1500:
                    break
    except Exception:
        return ""
    return "\n".join(parts)


def _load_triage_rows():
    """Load both OCCM and HT triages, tagging each row with `sheet_type`.

    Each row carries an absolute `path` column from the triage step, so we
    don't need EVALSP/fn fallbacks any more — files from the HT folder are
    found via their triage row directly.
    """
    out = []
    for tag, candidates in (
        ("OCCM", ("/tmp/triage_occm.csv", "research/results/triage_occm.csv")),
        ("HT",   ("/tmp/triage_ht.csv",   "research/results/triage_ht.csv")),
    ):
        for p in candidates:
            path = pathlib.Path(p) if p.startswith("/") else ROOT / p
            if not path.exists():
                continue
            # Tolerant of triage CSVs that contain NULs (we've seen this on
            # some OneDrive copies).
            raw = path.read_bytes().replace(b"\x00", b"")
            for r in csv.DictReader(io.StringIO(raw.decode("utf-8", errors="ignore"))):
                r["sheet_type"] = tag
                out.append(r)
            break
    return out


def main():
    rows = _load_triage_rows()
    print(f"  loaded {len(rows)} triage rows (OCCM + HT)")

    out_rows = []
    n = 0
    for r in rows:
        v = (r.get("variant") or "").strip()
        fn = (r.get("filename") or "").strip()
        sheet_type = r.get("sheet_type", "OCCM")
        # Process Unknown-variant files too — they often carry a clear
        # model/family in the header even when no parser signature fires
        # (e.g. the 25+ Boeing-MSN Unknown files in this corpus). Skip only
        # files with no variant cell at all or a Timeout marker.
        if not v or v == "Timeout":
            continue
        # Prefer absolute path from triage (handles HT folder + OCCM folder);
        # fall back to EVALSP/fn for backwards-compatible behaviour.
        triage_path = (r.get("path") or "").strip()
        path = pathlib.Path(triage_path) if triage_path else EVALSP / fn
        if not path.exists():
            continue
        head = read_header(str(path))
        fam, model_raw, conf = derive_family(head)
        reg = extract_registration(head)
        msn = extract_msn(head)
        # Fall back to filename MSN parsing when the header didn't carry one
        # — many filenames embed it as `(MSN 30875)` or `MSN 30875`.
        if not msn:
            fn_m = re.search(r"\bMSN[ _-]?(\d{3,6})\b", fn, re.I)
            if fn_m:
                msn = fn_m.group(1)
        # Manual MSN-based override for airframes the user has confirmed by
        # hand but whose headers carry no model token at all.
        if fam == "Unknown" and msn in _MANUAL_MSN_FAMILY:
            fam, model_raw = _MANUAL_MSN_FAMILY[msn]
            conf = "manual"
        # Filename can carry explicit family ("Masterfile B757-200 MSN 26161")
        # when header is silent — try a last-resort filename scan.
        if fam == "Unknown":
            fn_search = _BOEING_DASH_RE.search(fn) or _BOEING_BPREFIX_RE.search(fn)
            if fn_search:
                fam = f"B7{fn_search.group(1)}"
                model_raw = fn_search.group(0)
                conf = "filename"
        date = extract_report_date(head)
        snippet = " ".join(head[:200].split())
        out_rows.append({
            "source_file": fn, "variant": v, "sheet_type": sheet_type,
            "registration": reg, "msn": msn,
            "model_raw": model_raw, "family": fam, "family_confidence": conf,
            "report_date": date, "header_snippet": snippet,
        })
        n += 1
        if n % 30 == 0:
            print(f"  [{n}] {fn[:40]:40s} fam={fam}", flush=True)

    cols = ["source_file", "variant", "sheet_type", "registration", "msn",
            "model_raw", "family", "family_confidence", "report_date",
            "header_snippet"]
    # /tmp backup always
    with open("/tmp/file_metadata.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(out_rows)
    try:
        dest = ROOT / "research/results/file_metadata.csv"
        with dest.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(out_rows)
        print(f"\nWrote {dest.relative_to(ROOT)} ({len(out_rows)} files)")
    except OSError as e:
        print(f"\n[!] OneDrive write failed ({type(e).__name__}); metadata at /tmp/file_metadata.csv")

    # Family distribution
    from collections import Counter
    fam_c = Counter(r["family"] for r in out_rows)
    print("\n=== family distribution ===")
    for fam, c in fam_c.most_common():
        print(f"  {fam:15s} {c}")


if __name__ == "__main__":
    main()
