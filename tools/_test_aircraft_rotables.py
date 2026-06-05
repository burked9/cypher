"""Smoke-test Aircraft Rotables Report parser across detected files."""
import sys, pathlib, csv
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import pandas as pd
from sheet_types import occm
from sheet_types.occm_variants import aircraft_rotables_report as art

with open("research/results/triage_occm.csv") as f:
    rows = [r for r in csv.DictReader(f) if r["variant"] == "Aircraft Rotables Report"]
print(f"Testing {len(rows)} Aircraft Rotables Report files", flush=True)

total_rows, total_clean = 0, 0
for i, r in enumerate(rows):
    try:
        recs = art.extract(r["path"])
        cleaned = occm.normalize_and_validate(recs, variant_name="Aircraft Rotables Report")
        df = pd.DataFrame(cleaned)
        if df.empty:
            print(f"  [{i+1}/{len(rows)}] {r['filename'][:55]:55s}  rows=    0", flush=True)
            continue
        df = df[[c for c in art.CANONICAL_COLUMNS + ['_issues'] if c in df.columns]]
        clean = int((df['_issues'] == '').sum())
        total_rows += len(df)
        total_clean += clean
        print(f"  [{i+1}/{len(rows)}] {r['filename'][:55]:55s}  rows={len(df):5d}  clean={clean:5d}", flush=True)
    except Exception as e:
        print(f"  [{i+1}/{len(rows)}] {r['filename'][:55]:55s}  ERROR: {type(e).__name__}: {e}", flush=True)

print(f"\nSUMMARY: total_rows={total_rows}  total_clean={total_clean}", flush=True)
print("done", flush=True)
