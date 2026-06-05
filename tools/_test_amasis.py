"""One-off — test AMASIS parser across all detected AMASIS files.

Per-file logging *before* extract() so we can spot any pdfplumber hang.
"""
import sys, pathlib, csv, time, signal
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import pandas as pd
from sheet_types import occm
from sheet_types.occm_variants import amasis


def _timeout_handler(signum, frame):
    raise TimeoutError("file took too long")


with open("research/results/triage_occm.csv") as f:
    rows = [r for r in csv.DictReader(f) if r["variant"] == "AMASIS"]
print(f"Testing {len(rows)} AMASIS files", flush=True)

total_rows = 0
total_clean = 0

for i, r in enumerate(rows):
    name = r["filename"][:55]
    print(f"  [{i+1}/{len(rows)}] opening {name} ...", end="", flush=True)
    signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(60)   # 60s per file
    t0 = time.time()
    try:
        recs = amasis.extract(r["path"])
        cleaned = occm.normalize_and_validate(recs, variant_name="AMASIS")
        df = pd.DataFrame(cleaned)
        signal.alarm(0)
        dt = time.time() - t0
        if df.empty:
            print(f"  rows=    0  ({dt:.1f}s)", flush=True)
            continue
        df = df[[c for c in amasis.CANONICAL_COLUMNS + ['_issues'] if c in df.columns]]
        clean = int((df['_issues'] == '').sum())
        total_rows += len(df)
        total_clean += clean
        print(f"  rows={len(df):5d}  clean={clean:5d}  ({dt:.1f}s)", flush=True)
    except TimeoutError:
        signal.alarm(0)
        print(f"  TIMED OUT (>60s) — skipping", flush=True)
    except Exception as e:
        signal.alarm(0)
        print(f"  ERROR: {type(e).__name__}: {e}", flush=True)

print(f"\nSUMMARY: total_rows={total_rows}  total_clean={total_clean}", flush=True)
print("done", flush=True)
