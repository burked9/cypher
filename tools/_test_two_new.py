"""Smoke-test Cathay OCCM and CONFIG SLOT OCCM variants."""
import sys, pathlib, csv
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import pandas as pd
from sheet_types import occm
from sheet_types.occm_variants import cathay_occm, config_slot_occm

with open("research/results/triage_occm.csv") as f:
    rows = list(csv.DictReader(f))

for module in (cathay_occm, config_slot_occm):
    matches = [r for r in rows if r["variant"] == module.NAME]
    print(f"\n=== {module.NAME}: {len(matches)} files ===", flush=True)
    total_rows, total_clean = 0, 0
    for i, r in enumerate(matches):
        try:
            recs = module.extract(r["path"])
            cleaned = occm.normalize_and_validate(recs, variant_name=module.NAME)
            df = pd.DataFrame(cleaned)
            if df.empty:
                print(f"  [{i+1}/{len(matches)}] {r['filename'][:55]:55s}  rows=    0", flush=True)
                continue
            df = df[[c for c in module.CANONICAL_COLUMNS + ['_issues'] if c in df.columns]]
            clean = int((df['_issues'] == '').sum())
            total_rows += len(df); total_clean += clean
            print(f"  [{i+1}/{len(matches)}] {r['filename'][:55]:55s}  rows={len(df):5d}  clean={clean:5d}", flush=True)
        except Exception as e:
            print(f"  [{i+1}/{len(matches)}] {r['filename'][:55]:55s}  ERROR: {type(e).__name__}: {e}", flush=True)
    print(f"  SUMMARY {module.NAME}: total_rows={total_rows}  total_clean={total_clean}", flush=True)
print("\ndone", flush=True)
