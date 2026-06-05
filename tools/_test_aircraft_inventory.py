"""Smoke-test Aircraft Inventory Report (MM_504) parser."""
import sys, pathlib, csv
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import pandas as pd
from sheet_types import occm
from sheet_types.occm_variants import aircraft_inventory_report as air

with open("research/results/triage_occm.csv") as f:
    rows = [r for r in csv.DictReader(f) if r["variant"] == air.NAME]
print(f"Testing {len(rows)} files matched as {air.NAME!r}", flush=True)

total_rows, total_clean = 0, 0
for i, r in enumerate(rows):
    try:
        recs = air.extract(r["path"])
        cleaned = occm.normalize_and_validate(recs, variant_name=air.NAME)
        df = pd.DataFrame(cleaned)
        if df.empty:
            print(f"  [{i+1}/{len(rows)}] {r['filename'][:55]:55s}  rows=    0", flush=True)
            continue
        df = df[[c for c in air.CANONICAL_COLUMNS + ['_issues'] if c in df.columns]]
        clean = int((df['_issues'] == '').sum())
        total_rows += len(df)
        total_clean += clean
        print(f"  [{i+1}/{len(rows)}] {r['filename'][:55]:55s}  rows={len(df):5d}  clean={clean:5d}", flush=True)
    except Exception as e:
        print(f"  [{i+1}/{len(rows)}] {r['filename'][:55]:55s}  ERROR: {type(e).__name__}: {e}", flush=True)

print(f"\nSUMMARY: total_rows={total_rows}  total_clean={total_clean}", flush=True)
print("done", flush=True)
