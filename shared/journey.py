"""MSN journey tracker — records the per-PDF, per-level extraction history.

For each PDF processed, we append one row to `research/results/msn_journey.csv`
capturing:
  - which variant was detected,
  - how many pages had a usable text layer vs were scanned,
  - how many rows came out of L1, L2, L3, L4,
  - clean-row count and percentage,
  - which pages produced no rows at all,
  - a free-text notes field for ad-hoc context.

The journey CSV is **append-only** so progress over time is preserved. Re-runs
of the same PDF show as multiple rows; the report shows the latest by default
but the full history is available for trend analysis when stress-testing
with 50+ documents.

Usage:
    from shared.journey import record_run
    record_run(pdf_path, variant, df, total_pages, notes="initial run")
"""
from __future__ import annotations
import csv
import datetime as dt
from pathlib import Path

import pandas as pd

JOURNEY_CSV = Path(__file__).resolve().parent.parent / "research" / "results" / "msn_journey.csv"

COLUMNS = [
    "timestamp",
    "pdf",
    "sheet_type",
    "variant",
    "total_pages",
    "pages_with_rows",
    "pages_missing",
    "rows_l1",
    "rows_l2",
    "rows_l3",
    "rows_l4",
    "rows_total",
    "rows_clean",
    "clean_pct",
    "notes",
]


def _ensure_header():
    JOURNEY_CSV.parent.mkdir(parents=True, exist_ok=True)
    if not JOURNEY_CSV.exists():
        with JOURNEY_CSV.open("w", newline="") as f:
            csv.writer(f).writerow(COLUMNS)


def record_run(pdf_path: str, variant: str, df: pd.DataFrame,
               total_pages: int, notes: str = "", sheet_type: str = "OCCM") -> dict:
    """Append a journey row. `df` is the cleaned extraction dataframe with
    `_page`, `_issues`, and (optionally) `_source` columns."""
    _ensure_header()

    if df is None or df.empty:
        rows_l1 = rows_l3 = rows_l4 = 0
        clean = 0
        pages_seen = []
    else:
        sources = df.get("_source", pd.Series([""] * len(df))).astype(str)
        rows_l1 = int((sources == "").sum())
        rows_l3 = int(sources.isin(["ocr", "L3", "L3_tess"]).sum())
        rows_l4 = int(sources.str.startswith("L4").sum())
        clean = int((df["_issues"].astype(str) == "").sum()) if "_issues" in df.columns else 0
        pages_seen = sorted(int(p) for p in df["_page"].dropna().unique()) if "_page" in df.columns else []

    rows_l2 = 0  # L2 not implemented yet
    rows_total = rows_l1 + rows_l2 + rows_l3 + rows_l4
    pages_missing = sorted(set(range(1, total_pages + 1)) - set(pages_seen))
    clean_pct = round(100 * clean / rows_total, 1) if rows_total else 0.0

    row = {
        "timestamp": dt.datetime.now().replace(microsecond=0).isoformat(),
        "pdf": Path(pdf_path).name,
        "sheet_type": sheet_type,
        "variant": variant,
        "total_pages": total_pages,
        "pages_with_rows": len(pages_seen),
        "pages_missing": ",".join(str(p) for p in pages_missing),
        "rows_l1": rows_l1,
        "rows_l2": rows_l2,
        "rows_l3": rows_l3,
        "rows_l4": rows_l4,
        "rows_total": rows_total,
        "rows_clean": clean,
        "clean_pct": clean_pct,
        "notes": notes,
    }
    with JOURNEY_CSV.open("a", newline="") as f:
        csv.DictWriter(f, fieldnames=COLUMNS).writerow(row)
    return row


def latest_per_pdf() -> pd.DataFrame:
    """Return the most recent journey row per PDF. Empty DataFrame if no
    history yet."""
    if not JOURNEY_CSV.exists():
        return pd.DataFrame(columns=COLUMNS)
    df = pd.read_csv(JOURNEY_CSV)
    if df.empty:
        return df
    df = df.sort_values("timestamp")
    return df.drop_duplicates(subset=["pdf"], keep="last").reset_index(drop=True)


def history(pdf_name: str | None = None) -> pd.DataFrame:
    """Return the full history (or for one PDF when `pdf_name` is given)."""
    if not JOURNEY_CSV.exists():
        return pd.DataFrame(columns=COLUMNS)
    df = pd.read_csv(JOURNEY_CSV)
    if pdf_name:
        df = df[df["pdf"] == pdf_name]
    return df.reset_index(drop=True)
