"""Profile extraction performance across the corpus.

Runs the real router.extract() pipeline on every known (non-Unknown) file
from the latest triage CSV, timing each stage:
  - text extraction (read_head_text)
  - sheet-type detection
  - variant detection
  - extraction + validation

Outputs a CSV with per-file timings and a summary to stdout.

Usage
-----
    python tools/profile_extraction.py [--limit N] [--unknown]

    --limit N       Profile only the first N files (default: all known files)
    --unknown       Include Unknown files (skipped by default since they
                    short-circuit before extraction)
"""
from __future__ import annotations
import argparse
import asyncio
import csv
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from shared.text_layer import read_head_text
from shared.variant_detection import detect_sheet_type_from_text
from sheet_types import router, occm, ht, llp

SHEET_TYPES = {"OCCM": occm, "HT": ht, "LLP": llp}
DETECTION_ORDER = ["LLP", "HT", "OCCM"]

TRIAGE_CSV = ROOT / "research" / "results" / "triage.csv"
OUT_CSV = ROOT / "research" / "results" / "profile.csv"


async def profile_one(pdf_path: str) -> dict:
    """Profile a single file through the extraction pipeline."""
    result = {
        "path": pdf_path,
        "filename": Path(pdf_path).name,
        "t_text_extract": 0.0,
        "t_detect_type": 0.0,
        "t_detect_variant": 0.0,
        "t_extract": 0.0,
        "t_total": 0.0,
        "sheet_type": "Unknown",
        "variant": "Unknown",
        "rows": 0,
        "error": "",
    }

    t0 = time.perf_counter()

    try:
        t1 = time.perf_counter()
        head = read_head_text(pdf_path)
        result["t_text_extract"] = time.perf_counter() - t1

        t1 = time.perf_counter()
        head_upper = head.upper()
        sheet_type = detect_sheet_type_from_text(
            head_upper, SHEET_TYPES, DETECTION_ORDER)
        result["t_detect_type"] = time.perf_counter() - t1
        result["sheet_type"] = sheet_type

        if sheet_type == "Unknown":
            result["t_total"] = time.perf_counter() - t0
            return result

        mod = SHEET_TYPES[sheet_type]

        t1 = time.perf_counter()
        variant = await mod.detect_variant(pdf_path)
        result["t_detect_variant"] = time.perf_counter() - t1
        result["variant"] = variant or "Unknown"

        t1 = time.perf_counter()
        raw = await mod.extract(pdf_path, variant_name=variant)
        cleaned = mod.normalize_and_validate(
            raw["records"], variant_name=variant)
        result["t_extract"] = time.perf_counter() - t1
        result["variant"] = raw.get("variant", variant or "Unknown")
        result["rows"] = len(cleaned)

    except Exception as e:
        result["error"] = str(e)[:120]

    result["t_total"] = time.perf_counter() - t0
    return result


def fmt_ms(seconds: float) -> str:
    return f"{seconds * 1000:.0f}ms"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0,
                    help="max files to profile (0 = all)")
    ap.add_argument("--unknown", action="store_true",
                    help="include Unknown files")
    args = ap.parse_args()

    if not TRIAGE_CSV.exists():
        print(f"No triage CSV at {TRIAGE_CSV} — run triage first.")
        sys.exit(1)

    with TRIAGE_CSV.open() as f:
        rows = list(csv.DictReader(f))

    if not args.unknown:
        rows = [r for r in rows if r["variant"] != "Unknown"]

    if args.limit:
        rows = rows[:args.limit]

    sys.stdout.reconfigure(line_buffering=True)
    print(f"Profiling {len(rows)} files through router.extract()...")
    print()

    PER_FILE_TIMEOUT = 60

    async def profile_with_timeout(path):
        try:
            return await asyncio.wait_for(profile_one(path), PER_FILE_TIMEOUT)
        except asyncio.TimeoutError:
            return {
                "path": path, "filename": Path(path).name,
                "t_text_extract": 0.0, "t_detect_type": 0.0,
                "t_detect_variant": 0.0, "t_extract": 0.0,
                "t_total": PER_FILE_TIMEOUT,
                "sheet_type": "Timeout", "variant": "Timeout",
                "rows": 0, "error": f"exceeded {PER_FILE_TIMEOUT}s timeout",
            }

    results = []
    for i, row in enumerate(rows):
        path = row["path"]
        if not Path(path).exists():
            continue
        r = asyncio.run(profile_with_timeout(path))
        results.append(r)
        print(f"  [{i+1:3d}/{len(rows)}] {fmt_ms(r['t_total']):>7s}  "
              f"{r['rows']:>5d} rows  {r['variant'][:30]:30s}  "
              f"{r['filename'][:40]}", flush=True)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "filename", "sheet_type", "variant", "rows",
            "t_text_extract", "t_detect_type", "t_detect_variant",
            "t_extract", "t_total", "error",
        ])
        writer.writeheader()
        for r in results:
            writer.writerow({k: r[k] for k in writer.fieldnames})

    # Summary
    completed = [r for r in results if not r["error"]]
    errored = [r for r in results if r["error"]]
    extracted = [r for r in completed if r["rows"] > 0]

    print(f"\n{'=' * 60}")
    print(f"PROFILE SUMMARY — {len(results)} files")
    print(f"{'=' * 60}")
    print(f"  Completed:  {len(completed)}")
    print(f"  Extracted:  {len(extracted)} ({sum(r['rows'] for r in extracted)} total rows)")
    print(f"  Errored:    {len(errored)}")

    if completed:
        totals = [r["t_total"] for r in completed]
        print(f"\n  Total time per file:")
        print(f"    median  {fmt_ms(statistics.median(totals))}")
        print(f"    mean    {fmt_ms(statistics.mean(totals))}")
        print(f"    p95     {fmt_ms(sorted(totals)[int(len(totals)*0.95)])}")
        print(f"    max     {fmt_ms(max(totals))}")
        print(f"    sum     {sum(totals):.1f}s")

    if extracted:
        print(f"\n  By stage (extracted files only):")
        for stage in ["t_text_extract", "t_detect_type",
                       "t_detect_variant", "t_extract"]:
            vals = [r[stage] for r in extracted]
            label = stage.replace("t_", "").replace("_", " ")
            print(f"    {label:20s}  "
                  f"median={fmt_ms(statistics.median(vals)):>6s}  "
                  f"mean={fmt_ms(statistics.mean(vals)):>6s}  "
                  f"p95={fmt_ms(sorted(vals)[int(len(vals)*0.95)]):>6s}  "
                  f"max={fmt_ms(max(vals)):>6s}")

    # Top 10 slowest
    by_total = sorted(completed, key=lambda r: r["t_total"], reverse=True)
    print(f"\n  Top 10 slowest files:")
    for r in by_total[:10]:
        print(f"    {fmt_ms(r['t_total']):>7s}  {r['rows']:>5d} rows  "
              f"{r['variant'][:35]:35s}  {r['filename'][:40]}")

    # By sheet type
    from collections import defaultdict
    by_type = defaultdict(list)
    for r in extracted:
        by_type[r["sheet_type"]].append(r)

    print(f"\n  By sheet type:")
    for st in ["OCCM", "HT", "LLP"]:
        group = by_type.get(st, [])
        if group:
            times = [r["t_total"] for r in group]
            total_rows = sum(r["rows"] for r in group)
            print(f"    {st:5s}  {len(group):>4d} files  "
                  f"{total_rows:>6d} rows  "
                  f"median={fmt_ms(statistics.median(times)):>6s}  "
                  f"mean={fmt_ms(statistics.mean(times)):>6s}")

    print(f"\n  Wrote per-file timings to {OUT_CSV.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
