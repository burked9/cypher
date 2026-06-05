"""Run extraction on every detected file in the triage CSV.

For each (variant, file):
  - Call variant.extract() → normalize_and_validate
  - Save full CSV/XLSX into research/results/by_pdf/<stem>_<variant>.csv
  - Record per-file stats (rows, clean, time)
  - Capture first N rows of one representative file per variant for HTML samples

Output:
  research/results/by_pdf/                      per-file CSV+XLSX
  research/results/extraction_samples.json      { variant: {files: [...], sample: {file, rows} } }
"""
from __future__ import annotations
import csv, json, sys, time, pathlib, traceback
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
from sheet_types import occm

SAMPLE_LIMIT = 8       # rows shown in HTML sample
NON_SAMPLE_COLS = {"_issues", "_page", "_source", "_trailer", "_ref_htll", "_pn_known"}


def main():
    # Prefer a local copy of the triage list if present (avoids OneDrive
    # de-hydration cancelling the read on the in-folder CSV). Falls back to
    # the canonical path.
    triage_local = pathlib.Path("/tmp/triage_occm.csv")
    triage = triage_local if triage_local.exists() else ROOT / "research/results/triage_occm.csv"
    out_dir = ROOT / "research/results/by_pdf"
    out_dir.mkdir(parents=True, exist_ok=True)

    with triage.open() as f:
        rows = list(csv.DictReader(f))

    # Group by variant; skip Unknown
    by_variant: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        v = r["variant"]
        if v and v != "Unknown" and v != "Timeout":
            by_variant[v].append(r)

    summary = {}

    for variant_name in sorted(by_variant):
        # Find the variant module
        variant_mod = next((v for v in occm.VARIANTS if v.NAME == variant_name), None)
        if variant_mod is None:
            print(f"  ! no module for variant {variant_name!r} — skipped", flush=True)
            continue

        per_file = []
        sample_payload = None
        print(f"\n=== {variant_name} ({len(by_variant[variant_name])} files) ===", flush=True)

        for r in by_variant[variant_name]:
            path = r["path"]
            stem = pathlib.Path(r["filename"]).stem.replace(" ", "_").replace("/", "_")[:100]
            slug = variant_name.lower().replace(" ", "_").replace("/", "").replace("(", "").replace(")", "")
            out_csv = out_dir / f"{stem}_{slug}.csv"

            t0 = time.time()
            try:
                recs = variant_mod.extract(path)
                cleaned = occm.normalize_and_validate(recs, variant_name=variant_name)
                dt = time.time() - t0
                df = pd.DataFrame(cleaned)
                rowcount = len(df)
                if rowcount == 0:
                    per_file.append({"file": r["filename"], "rows": 0, "clean": 0, "secs": round(dt, 2)})
                    print(f"  [.] {r['filename'][:55]:55s} rows=    0   ({dt:.1f}s)", flush=True)
                    continue
                keep = variant_mod.CANONICAL_COLUMNS + ["_issues", "_page"]
                df = df[[c for c in keep if c in df.columns]]
                clean = int((df["_issues"].astype(str) == "").sum())
                df.to_csv(out_csv, index=False)
                # Best-effort XLSX (won't crash if openpyxl/Pillow flake on a big file)
                try:
                    df.to_excel(out_csv.with_suffix(".xlsx"), index=False)
                except Exception as xe:
                    print(f"      (xlsx skipped: {type(xe).__name__})", flush=True)
                per_file.append({
                    "file": r["filename"],
                    "rows": rowcount, "clean": clean,
                    "pct": round(100 * clean / rowcount, 1),
                    "secs": round(dt, 2),
                    "out_csv": str(out_csv.relative_to(ROOT)),
                })
                print(f"  [✓] {r['filename'][:55]:55s} rows={rowcount:5d}  clean={clean:5d}  ({dt:.1f}s)", flush=True)

                # Capture the FIRST successful file's sample
                if sample_payload is None and clean > 0:
                    display_cols = [c for c in variant_mod.CANONICAL_COLUMNS if c not in NON_SAMPLE_COLS][:8]
                    sample_df = df[[c for c in display_cols if c in df.columns]].head(SAMPLE_LIMIT)
                    sample_payload = {
                        "filename": r["filename"],
                        "columns": list(sample_df.columns),
                        "rows": sample_df.astype(str).values.tolist(),
                    }
            except Exception as e:
                dt = time.time() - t0
                msg = f"{type(e).__name__}: {e}"
                per_file.append({"file": r["filename"], "error": msg, "secs": round(dt, 2)})
                print(f"  [x] {r['filename'][:55]:55s} ERROR {msg[:120]}", flush=True)

        # Aggregate
        total_rows = sum(x.get("rows", 0) for x in per_file)
        total_clean = sum(x.get("clean", 0) for x in per_file)
        files_ok = sum(1 for x in per_file if x.get("rows", 0) > 0)
        summary[variant_name] = {
            "files_total": len(by_variant[variant_name]),
            "files_ok": files_ok,
            "rows": total_rows,
            "clean": total_clean,
            "per_file": per_file,
            "sample": sample_payload,
        }

    payload = json.dumps(summary, indent=2, default=str)
    # Always keep a /tmp backup so an OneDrive write-cancel can't lose the
    # roll-up.
    pathlib.Path("/tmp/extraction_samples.json").write_text(payload)
    out_path = ROOT / "research/results/extraction_samples.json"
    try:
        out_path.write_text(payload)
        print(f"\nWrote {out_path.relative_to(ROOT)}", flush=True)
    except OSError as e:
        print(f"\n[!] OneDrive write failed ({type(e).__name__}); "
              f"roll-up saved to /tmp/extraction_samples.json", flush=True)
    print("done", flush=True)


if __name__ == "__main__":
    main()
