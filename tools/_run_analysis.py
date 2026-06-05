"""Combined analysis: bucket counts + AMASIS parser smoke test on all detected files."""
import sys, pathlib, csv
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from collections import Counter

print("=== Triage bucket counts ===", flush=True)
with open("research/results/triage_occm.csv") as f:
    rows = list(csv.DictReader(f))
print(f"Total: {len(rows)}", flush=True)
b = Counter(r["variant"] for r in rows)
for v, n in b.most_common():
    print(f"  variant={v:24s} {n:4d}", flush=True)
print(flush=True)
bs = Counter(r["sheet_type"] for r in rows)
for v, n in bs.most_common():
    print(f"  sheet_type={v:18s} {n:4d}", flush=True)
print(flush=True)

print("=== AMASIS parser test ===", flush=True)
import pandas as pd
from sheet_types import occm
from sheet_types.occm_variants import amasis

amasis_rows = [r for r in rows if r["variant"] == "AMASIS"]
print(f"Detected AMASIS files: {len(amasis_rows)}", flush=True)

total_rows, total_clean = 0, 0
for i, r in enumerate(amasis_rows):
    try:
        recs = amasis.extract(r["path"])
        cleaned = occm.normalize_and_validate(recs, variant_name="AMASIS")
        df = pd.DataFrame(cleaned)
        if df.empty:
            print(f"  [{i+1}/{len(amasis_rows)}] {r['filename'][:60]:60s}  rows=    0", flush=True)
            continue
        df = df[[c for c in amasis.CANONICAL_COLUMNS + ['_issues'] if c in df.columns]]
        clean = int((df['_issues'] == '').sum())
        total_rows += len(df)
        total_clean += clean
        print(f"  [{i+1}/{len(amasis_rows)}] {r['filename'][:60]:60s}  rows={len(df):5d}  clean={clean:5d}", flush=True)
    except Exception as e:
        print(f"  [{i+1}/{len(amasis_rows)}] {r['filename'][:60]:60s}  ERROR: {type(e).__name__}: {e}", flush=True)

print(f"\nSUMMARY: total_rows={total_rows}  total_clean={total_clean}", flush=True)
print("done", flush=True)
