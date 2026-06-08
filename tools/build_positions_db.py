"""Build a SQLite `positions` database from the per-PDF OCCM extraction CSVs.

Reads:
    /tmp/triage_occm.csv  (or research/results/triage_occm.csv)  — filename→variant
    research/results/by_pdf/<stem>_<slug>.csv                    — per-file rows

Produces:
    research/results/positions.sqlite   (+ /tmp backup)

Grain of the base table `positions`: one row per component-instance per
source document. Everything is included — rows with validation issues are
kept, with `row_issues` carried verbatim so you can filter in SQL.

Three views sit on top:
    distinct_positions  — one row per (aircraft_key, position): the slot skeleton
    current_fit         — latest snapshot's part/serial per (aircraft_key, position)
    position_history    — full occupancy history per (aircraft_key, position, doc)

Design choices (confirmed with the user):
  * aircraft_key = MSN → registration → filename stem (fallback chain).
    aircraft_key_source records which one was used.
  * single normalised `position` column, tagged by `position_source`
    (FIN / POS / POSITION / LOCATION / POSN / FUNCTIONAL_LOCATION / AMM_FIN).
"""
from __future__ import annotations
import csv, re, sqlite3, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BY_PDF = ROOT / "research/results/by_pdf"

# variant NAME → (position_column, position_source_label, zone_column|None)
# (position_col, position_source_label, zone_col, kardex_col)
# kardex_col is the flat 6-digit ATA-derived code (e.g. 211501 for 21-15-01),
# captured separately from `position` because it's a useful stand-in slot
# identifier on the two variants whose FIN/POSITION fields are thin.
POSITION_MAP = {
    "Aeroflot":                            ("FIN", "FIN", "ZONE", None),
    "Aircraft Inventory Report (MM_504)":  ("POSITION", "POSITION", None, None),
    "Aircraft Rotables Report":            ("POSITION", "POSITION", None, None),
    "AMOS":                                ("POS", "POS", None, None),
    "Aircraft Spec File OCCM":             ("POS", "POS", None, None),
    "A330 Engineering Planning OCCM":      ("FIN", "FIN", "ZONE", None),
    "B777 Annex 8 OCCM":                   ("POSITION", "POSITION", None, None),
    # EL AL MSN 28132 records-package: no per-row position column, only ATA
    # and components. Rows land with empty position — filter by variant.
    "EL AL B767 MSN 28132":                (None, "NONE", None, None),
    "Georgian Airways B737":               ("POSITION", "POSITION", None, None),
    # HT-side variants — same layout as their OCCM siblings, so the OCCM
    # parser is reused with an HT-flavoured NAME. Position semantics match
    # the OCCM POS column.
    "AMOS HT (Aircraft Equipment List Report)": ("POS", "POS", None, None),
    # B777 Annex 7 is a master parts template — no per-row position data.
    # Rows land with empty position/serial; filter by variant to retrieve.
    "B777 Annex 7 OCCM":                   (None, "TEMPLATE", None, None),
    "CCA A340 OCCM":                       ("LOCATION", "LOCATION", None, None),
    "On Condition Monitoring OCCM":        ("POSITION", "POSITION", None, None),
    "Swiss A340 OCCM":                     ("POSITION", "POSITION", None, None),
    "A305 A340 OCCM":                      ("POSITION", "POSITION", None, None),
    "Avianca OCCM":                        ("POSITION", "POSITION", None, None),
    "Aegean ERJ OCCM":                     ("POSITION", "POSITION", None, None),
    "Cathay OCCM":                         ("LOCATION", "LOCATION", None, None),
    "CONFIG SLOT OCCM":                    ("POSITION", "POSITION", None, None),
    "Iberia Listado OCCM":                 ("LOCATION", "LOCATION", None, None),
    "OASES":                               ("POSITION", "POSITION", "ZONE", None),
    "OCCM List As At":                     ("POSN", "POSN", None, None),
    "OCCM Status List":                    ("FIN", "FIN", None, None),
    "MSN Components Status List":          ("FIN", "FIN", "ZONE", None),
    "SE-DOR B737 OCCM":                    ("POS", "POS", None, None),
    "On Condition Components Report":      ("POSITION", "POSITION", None, None),
    "Remaining Potentials":                ("AMM_FIN", "AMM_FIN", None, "KARDEX"),
    "Standard OCCM":                       ("FIN", "FIN", None, None),
    "TAP Compact OCCM":                    ("POSITION", "POSITION", None, None),
    "Technical Object Listing":            ("FUNCTIONAL_LOCATION", "FUNCTIONAL_LOCATION", None, "KARDEX"),
}

# Columns common enough to pull directly when present.
PN_CANDIDATES   = ["PART_NUMBER", "PN", "P_N"]
SN_CANDIDATES   = ["SERIAL_NUMBER", "SERIAL", "S_N"]
DESC_CANDIDATES = ["DESCRIPTION", "EQUIPMENT_DESCRIPTION", "PART_NAME"]
ATA_CANDIDATES  = ["ATA"]

# MSN explicitly labelled in the filename. The `(?:^|[^A-Z0-9])` lead avoids
# matching `AMSN`/`xMSN`-style false positives, while accepting `_MSN_` and
# `-MSN-` (the literal `\b` would fail because `_` is a word character in
# regex, breaking on filenames like `OCCM_MSN_1119.pdf`).
_MSN_RE = re.compile(
    r"(?:^|[^A-Z0-9])MSN[ _\-]?(\d{3,5})(?=[^\d]|$)", re.I)
# Bare 3-5 digit MSN at the very start of the filename, before an `_` or ` ` —
# e.g. `0469_a305_occm...`, `0968_2016-09-08_...`. Reliable because filenames
# in this corpus use leading MSN as a sortable prefix.
_MSN_PREFIX_RE = re.compile(r"^(\d{3,5})[_ -]")
# Standalone 4-5 digit MSN anywhere (weaker — last resort, with year-filter).
_MSN_FALLBACK_RE = re.compile(r"(?:^|[^A-Z0-9])(\d{4,5})(?=[^\d]|$)", re.I)
# Tail-number / registration patterns. Same word-boundary issue as MSN —
# `_VP-BDV_` needs to match even though `_` is a word character. Replaced
# `\b` boundaries with explicit non-alphanumeric leads/trails. Broadened
# prefix list to cover more national registries.
_REG_RE = re.compile(
    r"(?:^|[^A-Z0-9])("
    r"VN-A\d{3,4}|VP-[A-Z]{3}|VQ-[A-Z]{3}|"
    r"EC-[A-Z]{3}|E[0-9]-[A-Z]{3}|"
    r"HZ-[A-Z]{3}|HL\d{4}|B-\d{3,4}|D-[A-Z]{4}|"
    # Digit-leading national prefixes: 4X-ABC (Israel), 5Y-XXX (Kenya), 9V-XXX
    # (Singapore), 9H-XXX (Malta), etc.
    r"[0-9][A-Z]-[A-Z0-9]{3,5}|"
    r"N\d{1,5}[A-Z]{0,2}|[A-Z]{1,2}-[A-Z0-9]{3,5}"
    r")(?=[^A-Z0-9]|$)", re.I)


def _looks_like_year(n: str) -> bool:
    """4-digit number in the year range 1990-2030 is almost certainly a date,
    not an MSN. Used to filter the MSN_FALLBACK pattern."""
    return len(n) == 4 and "1990" <= n <= "2030"


# Compressed registration heuristic — some filenames drop the standard dash
# (CSTQW.pdf vs CS-TQW.pdf). Restricted to known national prefixes to keep
# the heuristic safe (we don't want to misread random 5-char filenames).
_COMPRESSED_REG_RE = re.compile(
    r"^(CS|EI|OO|PH|OE|OY|LX|SE|LN|OH|SX|SP|OK|HA|YR|TC|9H|9A|EC)"
    r"([A-Z0-9]{3})(?=[_ .])", re.I)

# Manual filename-to-aircraft-key overrides for files that resist both the
# regex patterns and the compressed-reg heuristic. Add entries here when the
# user identifies an airframe whose key can't be inferred from text.
_MANUAL_FILENAME_KEY = {
    "TQW_OCCM.PDF": ("CS-TQW", "registration"),   # sibling of CSTQW_OCCM_30OCT2019
}


# Month name → 2-digit string for ISO normalisation.
# Includes English abbreviations + full names, plus Portuguese (`out` =
# October, `dez` = December) and French (`sept`/`septembre`, `déc`, `aoû`,
# `août`) abbreviations we've seen in the corpus.
_MONTHS = {m: f"{i+1:02d}" for i, m in enumerate(
    ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"])}
_MONTHS.update({m: f"{i+1:02d}" for i, m in enumerate(
    ["JANUARY","FEBRUARY","MARCH","APRIL","MAY","JUNE","JULY","AUGUST",
     "SEPTEMBER","OCTOBER","NOVEMBER","DECEMBER"])})
# Portuguese (OASES files)
_MONTHS.update({"FEV":"02","ABR":"04","AGO":"08","SET":"09","OUT":"10","DEZ":"12"})
# French (A330 Engineering Planning) — strip trailing `.` before lookup
_MONTHS.update({"JANV":"01","FÉVR":"02","FEVR":"02","MARS":"03","AVR":"04",
                "JUIN":"06","JUIL":"07","AOÛ":"08","AOU":"08","AOÛT":"08",
                "AOUT":"08","SEPT":"09","DÉC":"12"})


def _yy_to_yyyy(yy: str) -> str:
    """2-digit → 4-digit year. <50 → 20xx, else 19xx (aviation OCCM dating
    convention; older airframes were built in the 90s)."""
    n = int(yy)
    return f"20{n:02d}" if n < 50 else f"19{n:02d}"


_RE_DMonY = re.compile(r"^(\d{1,2})[-/]([A-Za-z]{3,9}\.?)[-/.]?(\d{2,4})$")
_RE_DMY   = re.compile(r"^(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})$")
_RE_MonDY = re.compile(r"^([A-Za-z]{3,9})\s+(\d{1,2}),?\s+(\d{4})$")
# New formats observed this session:
_RE_DMonY_dotted = re.compile(r"^(\d{1,2})\.([A-Za-z]{3,4})\.(\d{4})$")    # 22.Aug.2016
_RE_DMonY_nosep  = re.compile(r"^(\d{1,2})([A-Za-z]{3,4})(\d{4})$")        # 25Aug2011
_RE_ISO          = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")                 # 2018-03-01
_RE_DMY_dotted   = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$")          # 06.04.2018
_RE_DMonY_spaced = re.compile(r"^(\d{1,2})\s+([A-Za-z]{3})\s+(\d{2,4})$")  # 28 Mar 18


def parse_report_date_iso(raw: str) -> str:
    """Normalise an arbitrary report-date string to ISO `YYYY-MM-DD`.
    Returns empty string when the input doesn't look like a real date
    (filters out ATA-chapter false positives like `21-23-50`).
    """
    s = (raw or "").strip().rstrip(".")
    if not s:
        return ""

    # ISO first — unambiguous YYYY-MM-DD
    m = _RE_ISO.match(s)
    if m:
        yyyy, mo, d = m.groups()
        di, moi = int(d), int(mo)
        if 1 <= di <= 31 and 1 <= moi <= 12:
            return f"{yyyy}-{moi:02d}-{di:02d}"
        return ""

    # Month-name forms (D-Mon-YY / DD.Mon.YYYY / DDMonYYYY / DD Mon YY)
    for pat in (_RE_DMonY, _RE_DMonY_dotted, _RE_DMonY_nosep, _RE_DMonY_spaced):
        m = pat.match(s)
        if m:
            day, mon, yy = m.groups()
            mm = _MONTHS.get(mon.upper().rstrip("."))
            if not mm:
                return ""
            yyyy = yy if len(yy) == 4 else _yy_to_yyyy(yy)
            return f"{yyyy}-{mm}-{int(day):02d}"

    # Pure-numeric DD-MM-YYYY / DD.MM.YYYY (European order)
    for pat in (_RE_DMY, _RE_DMY_dotted):
        m = pat.match(s)
        if m:
            d, mo, yy = m.groups()
            di, moi = int(d), int(mo)
            if not (1 <= di <= 31 and 1 <= moi <= 12):
                continue
            yyyy = yy if len(yy) == 4 else _yy_to_yyyy(yy)
            return f"{yyyy}-{moi:02d}-{di:02d}"

    # `Month DD, YYYY`
    m = _RE_MonDY.match(s)
    if m:
        mon, day, yyyy = m.groups()
        mm = _MONTHS.get(mon.upper())
        if not mm:
            return ""
        return f"{yyyy}-{mm}-{int(day):02d}"
    return ""


def _slug(variant_name: str) -> str:
    return (variant_name.lower().replace(" ", "_").replace("/", "")
            .replace("(", "").replace(")", ""))


def _stem(filename: str) -> str:
    return pathlib.Path(filename).stem.replace(" ", "_").replace("/", "_")[:100]


def derive_aircraft_key(filename: str) -> tuple[str, str]:
    """Return (aircraft_key, source) from the filename.

    Preference order:
      1. Manual override table (`_MANUAL_FILENAME_KEY`)
      2. Explicit `MSN <NNN>` label  →  source="msn"
      3. Leading numeric prefix `NNNN_…` (sortable MSN convention) → "msn_prefix"
      4. Registration token (XX-YYY / Nxxxx / etc.)  →  "registration"
      5. Compressed-form registration at filename start (CSTQW → CS-TQW)
         → "registration_compressed"
      6. Bare 4-5 digit number (last resort, with year-filter) → "msn_guess"
    """
    # Manual overrides win first.
    if filename in _MANUAL_FILENAME_KEY:
        return _MANUAL_FILENAME_KEY[filename]
    m = _MSN_RE.search(filename)
    if m:
        return m.group(1), "msn"
    # Leading-prefix MSN like "0469_a305_occm..." — reliable in this corpus.
    m = _MSN_PREFIX_RE.match(filename)
    if m and not _looks_like_year(m.group(1)):
        return m.group(1), "msn_prefix"
    m = _REG_RE.search(filename)
    if m:
        return m.group(1).upper(), "registration"
    # Compressed registration: filename starts with a known national prefix
    # plus 3 chars, no dash. Reconstruct as `XX-XXX`.
    m = _COMPRESSED_REG_RE.match(filename)
    if m:
        return f"{m.group(1).upper()}-{m.group(2).upper()}", "registration_compressed"
    # Bare 4-5 digit number anywhere — reject year-shaped digits and
    # all-zero / all-same-digit sequence markers (`0000`, `9999`) which are
    # almost always sequence padding, not real MSNs.
    for m in _MSN_FALLBACK_RE.finditer(filename):
        n = m.group(1)
        if _looks_like_year(n):
            continue
        if len(set(n)) == 1:   # all same digit → reject
            continue
        return n, "msn_guess"
    return pathlib.Path(filename).stem, "filename"


def _first_present(row: dict, candidates: list[str]) -> str:
    for c in candidates:
        if c in row and (row[c] or "").strip():
            return row[c].strip()
    return ""


def load_triage() -> list[dict]:
    """Load OCCM + HT triages concatenated; each row carries `sheet_type`.

    Triage CSVs occasionally contain stray NUL bytes from interrupted
    writes — strip them before parsing.
    """
    import io
    rows: list[dict] = []
    for tag, candidates in (
        ("OCCM", ("/tmp/triage_occm.csv", "research/results/triage_occm.csv")),
        ("HT",   ("/tmp/triage_ht.csv",   "research/results/triage_ht.csv")),
    ):
        for p in candidates:
            path = pathlib.Path(p) if p.startswith("/") else ROOT / p
            if not path.exists():
                continue
            raw = path.read_bytes().replace(b"\x00", b"")
            for r in csv.DictReader(io.StringIO(raw.decode("utf-8", errors="ignore"))):
                r["sheet_type"] = tag
                rows.append(r)
            break
    return rows


def load_metadata() -> dict[str, dict]:
    """source_file -> {registration, msn, family, report_date, ...}.
    Prefers the /tmp copy (avoids OneDrive read cancels)."""
    for cand in (pathlib.Path("/tmp/file_metadata.csv"),
                 ROOT / "research/results/file_metadata.csv"):
        if cand.exists():
            with cand.open() as f:
                return {r["source_file"]: r for r in csv.DictReader(f)}
    return {}


def load_family_overrides() -> dict[str, tuple[str, str]]:
    """Optional file: source_file -> (family, model). Populated from the
    user's review CSV. Applied after auto-classification when the auto
    result was Unknown."""
    import json
    cand = pathlib.Path("/tmp/manual_family_overrides.json")
    if not cand.exists():
        return {}
    raw = json.loads(cand.read_text())
    return {fn: tuple(v) for fn, v in raw.items()}


def load_aircraft_key_overrides() -> dict[str, tuple[str, str]]:
    """Optional file: source_file -> (aircraft_key, source_label).
    Used for sibling-cluster files where the user has confirmed the airframe
    by hand but the header carries no MSN/registration label."""
    import json
    cand = pathlib.Path("/tmp/manual_aircraft_key_overrides.json")
    if not cand.exists():
        return {}
    raw = json.loads(cand.read_text())
    return {fn: tuple(v) for fn, v in raw.items()}


def build():
    triage = load_triage()
    db_tmp = pathlib.Path("/tmp/positions.sqlite")
    if db_tmp.exists():
        db_tmp.unlink()
    conn = sqlite3.connect(db_tmp)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_file        TEXT,
            sheet_type         TEXT,
            variant            TEXT,
            aircraft_key       TEXT,
            aircraft_key_source TEXT,
            registration       TEXT,
            msn                TEXT,
            family             TEXT,
            family_confidence  TEXT,
            model_raw          TEXT,
            report_date        TEXT,
            report_date_iso    TEXT,
            ata                TEXT,
            position           TEXT,
            position_source    TEXT,
            zone               TEXT,
            kardex             TEXT,
            description        TEXT,
            part_number        TEXT,
            serial_number      TEXT,
            row_issues         TEXT,
            page               INTEGER
        )
    """)
    meta = load_metadata()
    family_overrides = load_family_overrides()
    aircraft_key_overrides = load_aircraft_key_overrides()
    if family_overrides:
        print(f"  (applying user family overrides on {len(family_overrides)} files)")
    if aircraft_key_overrides:
        print(f"  (applying aircraft_key overrides on {len(aircraft_key_overrides)} files)")

    n_files = n_rows = n_missing_csv = 0
    for r in triage:
        variant = (r.get("variant") or "").strip()
        filename = (r.get("filename") or "").strip()
        sheet_type = (r.get("sheet_type") or "OCCM").strip()
        if not variant or variant in ("Unknown", "Timeout"):
            continue
        posmap = POSITION_MAP.get(variant)
        if posmap is None:
            continue
        pos_col, pos_src, zone_col, kardex_col = posmap
        csv_path = BY_PDF / f"{_stem(filename)}_{_slug(variant)}.csv"
        if not csv_path.exists():
            n_missing_csv += 1
            continue

        # Aircraft identity: prefer header-derived MSN → registration, then
        # fall back to filename scrape only if the header gave us nothing.
        md = meta.get(filename, {})
        reg = (md.get("registration") or "").strip()
        msn = (md.get("msn") or "").strip()
        family = (md.get("family") or "Unknown").strip()
        fam_conf = (md.get("family_confidence") or "none").strip()
        model_raw = (md.get("model_raw") or "").strip()
        report_date = (md.get("report_date") or "").strip()
        report_date_iso = parse_report_date_iso(report_date)
        # User family-override (applies when auto-classification was Unknown
        # or when the user explicitly knows the airframe via the review CSV).
        if filename in family_overrides:
            fam_o, model_o = family_overrides[filename]
            if family in ("", "Unknown") or fam_conf in ("none", "low"):
                family = fam_o
                fam_conf = "manual_review"
                model_raw = model_o or model_raw
        # Manual aircraft_key override wins over everything — user has
        # confirmed the airframe for these sibling-cluster files.
        if filename in aircraft_key_overrides:
            ak_o, ak_src_o = aircraft_key_overrides[filename]
            ak, aksrc = ak_o, f"manual_{ak_src_o}"
        elif msn:
            ak, aksrc = msn, "header_msn"
        elif reg:
            ak, aksrc = reg, "header_registration"
        else:
            ak, aksrc = derive_aircraft_key(filename)
        try:
            with csv_path.open() as f:
                reader = csv.DictReader(f)
                batch = []
                for row in reader:
                    batch.append((
                        filename, sheet_type, variant, ak, aksrc,
                        reg, msn, family, fam_conf, model_raw,
                        report_date, report_date_iso,
                        _first_present(row, ATA_CANDIDATES),
                        (row.get(pos_col) or "").strip(),
                        pos_src,
                        (row.get(zone_col) or "").strip() if zone_col else "",
                        (row.get(kardex_col) or "").strip() if kardex_col else "",
                        _first_present(row, DESC_CANDIDATES),
                        _first_present(row, PN_CANDIDATES),
                        _first_present(row, SN_CANDIDATES),
                        (row.get("_issues") or "").strip(),
                        int(row["_page"]) if (row.get("_page") or "").strip().isdigit() else None,
                    ))
                cur.executemany(
                    "INSERT INTO positions (source_file,sheet_type,variant,"
                    "aircraft_key,aircraft_key_source,registration,msn,family,"
                    "family_confidence,model_raw,report_date,report_date_iso,"
                    "ata,position,position_source,zone,kardex,description,"
                    "part_number,serial_number,row_issues,page) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", batch)
                n_rows += len(batch)
                n_files += 1
        except OSError as e:
            print(f"  [!] read failed: {csv_path.name} ({type(e).__name__})", flush=True)

    # HT family inheritance: for any HT row whose family is Unknown but
    # whose aircraft_key matches an OCCM row with a known family, copy that
    # family over. This is the cheapest way to flow OCCM-side classification
    # to HT files for the same airframe (AMOS HT headers don't carry a model
    # token, so the standalone classifier returns Unknown even when the OCCM
    # twin clearly identifies the family).
    cur.execute("""
        UPDATE positions
           SET family = (
               SELECT o.family FROM positions o
                WHERE o.sheet_type='OCCM' AND o.aircraft_key=positions.aircraft_key
                  AND o.family NOT IN ('','Unknown')
                LIMIT 1),
               family_confidence = 'occm_sibling'
         WHERE sheet_type='HT'
           AND family IN ('','Unknown')
           AND aircraft_key IN (
               SELECT DISTINCT aircraft_key FROM positions
                WHERE sheet_type='OCCM' AND family NOT IN ('','Unknown'))
    """)
    print(f"  HT family-inheritance: {cur.rowcount} rows updated from OCCM siblings")

    # Indexes
    cur.execute("CREATE INDEX idx_sheet ON positions(sheet_type)")
    cur.execute("CREATE INDEX idx_ak ON positions(aircraft_key)")
    cur.execute("CREATE INDEX idx_pos ON positions(aircraft_key, position)")
    cur.execute("CREATE INDEX idx_pn ON positions(part_number)")
    cur.execute("CREATE INDEX idx_family ON positions(family)")

    # Views
    cur.execute("""
        CREATE VIEW distinct_positions AS
        SELECT DISTINCT aircraft_key, family, position, position_source, variant
        FROM positions
        WHERE position <> ''
    """)
    # current_fit: latest snapshot per (aircraft_key, position), ordered by
    # `report_date_iso` DESC (real date), id DESC as tiebreaker. Rows with
    # no parseable date are still represented — they sort *after* any dated
    # row, so they only win when no dated alternative exists.
    cur.execute("""
        CREATE VIEW current_fit AS
        SELECT p.* FROM positions p
        JOIN (
            SELECT aircraft_key, position,
                   -- Sort key: empty dates push to the bottom, then most-recent first.
                   (SELECT id FROM positions q
                    WHERE q.aircraft_key = positions.aircraft_key
                      AND q.position = positions.position
                      AND q.position <> ''
                    ORDER BY (q.report_date_iso = '') ASC,
                             q.report_date_iso DESC,
                             q.id DESC
                    LIMIT 1) AS best_id
            FROM positions
            WHERE position <> ''
            GROUP BY aircraft_key, position
        ) m ON p.id = m.best_id
    """)
    cur.execute("""
        CREATE VIEW position_history AS
        SELECT aircraft_key, position, source_file, part_number,
               serial_number, description, row_issues
        FROM positions
        WHERE position <> ''
        ORDER BY aircraft_key, position, source_file
    """)

    conn.commit()

    # Quick stats
    def q(sql):
        return cur.execute(sql).fetchone()[0]
    total = q("SELECT COUNT(*) FROM positions")
    with_pos = q("SELECT COUNT(*) FROM positions WHERE position <> ''")
    clean_pos = q("SELECT COUNT(*) FROM positions WHERE position <> '' AND row_issues = ''")
    distinct_ac = q("SELECT COUNT(DISTINCT aircraft_key) FROM positions")
    distinct_slots = q("SELECT COUNT(*) FROM distinct_positions")

    print(f"\n=== positions DB built ===")
    print(f"Files loaded:            {n_files}")
    print(f"Missing CSVs (skipped):  {n_missing_csv}")
    print(f"Total rows:              {total:,}")
    print(f"Rows with a position:    {with_pos:,}  ({100*with_pos/max(total,1):.1f}%)")
    print(f"  of those, issue-free:  {clean_pos:,}  ({100*clean_pos/max(with_pos,1):.1f}%)")
    print(f"Distinct aircraft keys:  {distinct_ac}")
    print(f"Distinct (ac,position):  {distinct_slots:,}")

    print(f"\n=== rows by family ===")
    for fam, n, files in cur.execute(
        "SELECT family, COUNT(*), COUNT(DISTINCT source_file) "
        "FROM positions GROUP BY family ORDER BY 2 DESC"):
        print(f"  {fam:15s} {n:7,} rows  ({files} files)")

    print(f"\n=== aircraft_key source ===")
    for s, n in cur.execute(
        "SELECT aircraft_key_source, COUNT(DISTINCT aircraft_key) "
        "FROM positions GROUP BY 1 ORDER BY 2 DESC"):
        print(f"  {s:20s} {n} aircraft")
    conn.close()

    # Copy to OneDrive (best effort)
    import shutil
    print(f"\nWrote /tmp/positions.sqlite")
    try:
        dest = ROOT / "research/results/positions.sqlite"
        shutil.copyfile(db_tmp, dest)
        print(f"Copied to {dest.relative_to(ROOT)}")
    except OSError as e:
        print(f"[!] OneDrive copy failed ({type(e).__name__}); DB is at /tmp/positions.sqlite")


if __name__ == "__main__":
    build()
