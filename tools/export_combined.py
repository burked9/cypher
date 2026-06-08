"""Local CLI combiner — Cypher OCCM+HT combined export.

Phase-1 implementation of the proposed Cypher OCCM+HT combined mode
(see docs/TODO.md). Reads from `research/results/positions.sqlite`
and emits a per-airframe artefact in three shapes:

  * **OCCM sheet**         — long-form OCCM rows for the airframe
                              (audit trail; one row per snapshot per
                              installed component)
  * **HT sheet**            — long-form HT rows
  * **Combined sheet**      — slot-joined wide view (one row per
                              `(aircraft_key, position)`, OCCM and HT
                              columns side-by-side). Sourced from the
                              `cross_sheet_slot` SQL view, so the slot
                              join already de-duplicates snapshots via
                              `current_fit` semantics.

Plus a sidecar CSV (`<key>_sextant_input.csv`) shaped exactly for
Sextant — slot + ATA + family + occm_part_number + occm_serial_number
+ ht_part_number + slot_coverage. No extra columns, no junk.

Usage
-----

    # Single airframe (DB lookup)
    python tools/export_combined.py --aircraft 2333

    # All cross-sheet airframes (45 in current corpus)
    python tools/export_combined.py --all-cross-sheet

    # Two-PDF input — pair the PDFs first, then export (Phase 2)
    python tools/export_combined.py \
        --occm-pdf path/to/occm.pdf \
        --ht-pdf   path/to/ht.pdf

    # Two-PDF input with caller-supplied aircraft_key (manual override)
    python tools/export_combined.py \
        --occm-pdf path/to/occm.pdf --ht-pdf path/to/ht.pdf \
        --aircraft-key MSN-12345

    # Specific output dir (default: research/results/combined/)
    python tools/export_combined.py --aircraft 223 --out /tmp/combined

The DB-lookup paths are read-only on positions.sqlite — no PDF reads.
The two-PDF mode delegates to `shared.pairing.link_pair()` to verify the
PDFs are for the same airframe before exporting.
"""
from __future__ import annotations
import argparse
import pathlib
import sqlite3
import sys
from typing import Optional

ROOT = pathlib.Path(__file__).resolve().parent.parent
# Make sibling packages (`shared`, `tools` itself) importable when invoked
# as `python tools/export_combined.py`.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

DB_PATH = ROOT / "research" / "results" / "positions.sqlite"
OUT_DIR = ROOT / "research" / "results" / "combined"


# Columns the user actually reads when reviewing — keep the long-form
# sheets tight. Hide derivation columns (`family_confidence`, etc.)
# in a sidecar if you need them; they're noise in the main artefact.
OCCM_COLS = [
    "ata", "position", "position_source", "part_number", "serial_number",
    "description", "report_date_iso", "variant", "source_file", "row_issues",
]
HT_COLS = OCCM_COLS   # same shape; row content differs

# Sextant input — the minimum surface area for the slot-level expected-
# PN advisory. Everything else can be looked up by foreign key.
SEXTANT_COLS = [
    "aircraft_key", "family", "ata", "position", "slot_coverage",
    "occm_part_number", "occm_serial_number", "occm_report_date",
    "ht_part_number", "ht_description", "ht_report_date",
]


def list_cross_sheet_airframes(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    """Return [(aircraft_key, family), ...] for every airframe that
    carries rows in BOTH the OCCM and HT sheets — the joinable set."""
    rows = conn.execute("""
        SELECT aircraft_key,
               MAX(family) AS family   -- single family expected per airframe
          FROM positions
         WHERE aircraft_key <> ''
         GROUP BY aircraft_key
         HAVING SUM(CASE WHEN sheet_type='OCCM' THEN 1 ELSE 0 END) > 0
            AND SUM(CASE WHEN sheet_type='HT'   THEN 1 ELSE 0 END) > 0
         ORDER BY family, aircraft_key
    """).fetchall()
    return [(ak, fam or "Unknown") for ak, fam in rows]


def export_airframe(conn: sqlite3.Connection, aircraft_key: str,
                    out_dir: pathlib.Path) -> dict:
    """Write the per-airframe 3-sheet xlsx + Sextant sidecar CSV.

    Returns a small stats dict so the caller can log per-airframe counts.
    """
    occm = pd.read_sql_query(
        f"""SELECT {', '.join(OCCM_COLS)}
              FROM positions
             WHERE aircraft_key = ? AND sheet_type='OCCM'
             ORDER BY ata, position, report_date_iso DESC""",
        conn, params=(aircraft_key,))
    ht = pd.read_sql_query(
        f"""SELECT {', '.join(HT_COLS)}
              FROM positions
             WHERE aircraft_key = ? AND sheet_type='HT'
             ORDER BY ata, position, report_date_iso DESC""",
        conn, params=(aircraft_key,))
    combined = pd.read_sql_query(
        """SELECT * FROM cross_sheet_slot
            WHERE aircraft_key = ?
            ORDER BY CAST(ata AS INTEGER), position""",
        conn, params=(aircraft_key,))
    sextant = combined[SEXTANT_COLS] if not combined.empty else pd.DataFrame(columns=SEXTANT_COLS)

    out_dir.mkdir(parents=True, exist_ok=True)
    # Filesystem-safe key (registrations carry `-`; preserve them, but
    # replace `/` if any sneak through).
    safe_key = aircraft_key.replace("/", "_")
    xlsx_path = out_dir / f"{safe_key}_combined.xlsx"
    csv_path  = out_dir / f"{safe_key}_sextant_input.csv"

    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as xw:
        # Sheet order matters — analysts open Combined first.
        if not combined.empty:
            combined.to_excel(xw, sheet_name="Combined", index=False)
        if not occm.empty:
            occm.to_excel(xw, sheet_name="OCCM", index=False)
        if not ht.empty:
            ht.to_excel(xw, sheet_name="HT", index=False)

    sextant.to_csv(csv_path, index=False)

    # Stats for the run summary
    both = int((combined["slot_coverage"] == "both").sum()) if not combined.empty else 0
    occm_only = int((combined["slot_coverage"] == "occm_only").sum()) if not combined.empty else 0
    ht_only = int((combined["slot_coverage"] == "ht_only").sum()) if not combined.empty else 0
    return {
        "aircraft_key": aircraft_key,
        "occm_rows": len(occm),
        "ht_rows": len(ht),
        "slot_rows": len(combined),
        "both": both,
        "occm_only": occm_only,
        "ht_only": ht_only,
        "xlsx": str(xlsx_path),
        "csv": str(csv_path),
    }


def _resolve_pair_mode(occm_pdf: str, ht_pdf: str,
                       manual_key: Optional[str]) -> Optional[str]:
    """Run link_pair() on the two PDFs; return the agreed aircraft_key
    (or None to abort). Prints a short summary so the analyst sees the
    pairing decision before the export runs."""
    from shared.pairing import link_pair  # local import to avoid cost at module load
    result = link_pair(occm_pdf, ht_pdf, manual_override=manual_key)
    print(f"[link_pair] status={result.status}  confidence={result.confidence}  "
          f"aircraft_key={result.aircraft_key or '(none)'}")
    if result.occm:
        print(f"  OCCM: {result.occm.filename}  "
              f"msn={result.occm.msn or '-'}  reg={result.occm.registration or '-'}")
    if result.ht:
        print(f"  HT  : {result.ht.filename}  "
              f"msn={result.ht.msn or '-'}  reg={result.ht.registration or '-'}")
    for w in result.warnings:
        print(f"  WARN: {w}")
    if result.is_hard_mismatch:
        print("\nABORTED: hard mismatch between the two PDFs. Override with "
              "--aircraft-key if you really want to force a pair.", file=sys.stderr)
        return None
    if result.needs_user_decision:
        print("\nWARNING: pairing is filename-only / unverified. The export will "
              "proceed, but treat the result as advisory.")
    return result.aircraft_key or None


def main() -> int:
    ap = argparse.ArgumentParser(description="Export combined OCCM+HT artefacts per airframe.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--aircraft", help="aircraft_key to export (DB lookup)")
    g.add_argument("--all-cross-sheet", action="store_true",
                   help="export every airframe that has both an OCCM and an HT list")
    g.add_argument("--occm-pdf",
                   help="path to one OCCM PDF — pair with --ht-pdf via link_pair()")
    ap.add_argument("--ht-pdf",
                    help="path to one HT PDF (required when --occm-pdf is given)")
    ap.add_argument("--aircraft-key",
                    help="manual aircraft_key override; forces the pair to use this key "
                         "(skips MSN/registration match)")
    ap.add_argument("--out", type=pathlib.Path, default=OUT_DIR,
                    help="output directory (default research/results/combined/)")
    args = ap.parse_args()

    if not DB_PATH.exists():
        print(f"ERROR: {DB_PATH} not found. Build it first via tools/build_positions_db.py",
              file=sys.stderr)
        return 1

    conn = sqlite3.connect(str(DB_PATH))
    if args.all_cross_sheet:
        airframes = list_cross_sheet_airframes(conn)
        print(f"Found {len(airframes)} cross-sheet airframes — exporting all")
    elif args.occm_pdf:
        if not args.ht_pdf:
            print("ERROR: --occm-pdf requires --ht-pdf", file=sys.stderr)
            return 2
        ak = _resolve_pair_mode(args.occm_pdf, args.ht_pdf, args.aircraft_key)
        if ak is None:
            return 3
        airframes = [(ak, "")]
    else:
        airframes = [(args.aircraft, "")]

    stats = []
    for ak, fam in airframes:
        s = export_airframe(conn, ak, args.out)
        if fam:
            s["family"] = fam
        stats.append(s)
        print(f"  [{ak:10s}] {s['both']:4d} joined / {s['occm_only']:5d} OCCM-only / "
              f"{s['ht_only']:4d} HT-only  ->  {pathlib.Path(s['xlsx']).name}")

    # Summary
    total_both = sum(s["both"] for s in stats)
    total_occm_only = sum(s["occm_only"] for s in stats)
    total_ht_only = sum(s["ht_only"] for s in stats)
    print()
    print(f"=== Wrote {len(stats)} airframe artefact(s) to {args.out} ===")
    print(f"  joined slots:     {total_both:6,}")
    print(f"  OCCM-only slots:  {total_occm_only:6,}")
    print(f"  HT-only slots:    {total_ht_only:6,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
