"""Sample 10 LLP PDFs and run cypher's LLP pipeline. Save CSV/XLSX outputs
to research/results/llp_sample/."""
from __future__ import annotations
import sys, time, random, pathlib, traceback
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
from sheet_types import llp as llp_router

LLP_DIR = pathlib.Path("/Users/danielburke/Library/CloudStorage/OneDrive-Personal/work/KEEL_aviation_records/llp")
OUT = ROOT / "research/results/llp_sample"
OUT.mkdir(parents=True, exist_ok=True)

random.seed(20260520)
all_pdfs = sorted(LLP_DIR.glob("*.pdf"))
sample = random.sample(all_pdfs, 10)

print(f"Sampled 10 of {len(all_pdfs)} LLP PDFs:\n")
for i, p in enumerate(sample, 1):
    print(f"  [{i:2d}] {p.name}")
print()

summary = []
for i, p in enumerate(sample, 1):
    t0 = time.time()
    try:
        variant = llp_router.detect_variant(str(p))
        if variant == "Unknown":
            dt = time.time() - t0
            print(f"  [{i:2d}] {p.name[:65]:65s}  Unknown  ({dt:.1f}s)")
            summary.append({"file": p.name, "variant": "Unknown", "rows": 0, "secs": round(dt, 2)})
            continue
        result = llp_router.extract(str(p), variant_name=variant)
        records = result["records"]
        cleaned = llp_router.normalize_and_validate(records, variant_name=variant)
        dt = time.time() - t0
        df = pd.DataFrame(cleaned)
        rowcount = len(df)
        stem = p.stem.replace(" ", "_").replace("/", "_")[:80]
        slug = variant.lower().replace(" ", "_")
        out_csv = OUT / f"{stem}_{slug}.csv"
        clean = 0
        if rowcount > 0:
            keep = result["columns"] + ["_issues", "_page"]
            df = df[[c for c in keep if c in df.columns]]
            df.to_csv(out_csv, index=False)
            try:
                df.to_excel(out_csv.with_suffix(".xlsx"), index=False)
            except Exception:
                pass
            clean = int((df["_issues"].astype(str) == "").sum()) if "_issues" in df.columns else 0
        print(f"  [{i:2d}] {p.name[:65]:65s}  {variant[:20]:20s}  rows={rowcount:4d}  clean={clean:4d}  ({dt:.1f}s)")
        summary.append({"file": p.name, "variant": variant, "rows": rowcount, "clean": clean, "secs": round(dt, 2)})
    except Exception as e:
        dt = time.time() - t0
        print(f"  [{i:2d}] {p.name[:65]:65s}  ERROR {type(e).__name__}: {str(e)[:60]}  ({dt:.1f}s)")
        summary.append({"file": p.name, "variant": "ERROR", "rows": 0, "error": str(e)[:120], "secs": round(dt, 2)})

print("\n=== SUMMARY ===")
ok = sum(1 for s in summary if s.get("rows", 0) > 0)
total_rows = sum(s.get("rows", 0) for s in summary)
total_clean = sum(s.get("clean", 0) for s in summary)
print(f"  Detected + extracted: {ok}/10")
print(f"  Total rows: {total_rows}, clean: {total_clean}")
print(f"  Outputs: {OUT.relative_to(ROOT)}/")
