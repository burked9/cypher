"""Snapshot diff — compare two Cypher extractions of the same airframe.

Use case
--------
A monthly OCCM (or HT, or LLP) for the same aircraft arrives. You ran
Cypher on last month's PDF; you have a fresh CSV from this month's. What
changed?

This tool produces a diff showing:
    - rows ADDED in the new snapshot (newly installed components)
    - rows REMOVED from the old snapshot (removed / replaced components)
    - rows CHANGED (FH/CY/serial/date updated for the same logical part)
    - rows UNCHANGED (carried forward — usually the silent majority)

Identity strategy
-----------------
A "logical row" is identified by a configurable key. Defaults:
    OCCM  → (FIN, PART_NUMBER)
    HT    → (PART_NUMBER, SERIAL_NUMBER)
    LLP   → (NO,)
    other → (PART_NUMBER, SERIAL_NUMBER)

When a row's key changes (e.g. SN changes for the same FIN), it shows up
as a paired remove + add. When the key matches but content changes, it
shows up as CHANGED with a per-column delta.

Usage
-----
    python tools/snapshot_diff.py \\
        --old research/results/by_pdf/A350_MSN_2974_OCCM_OCCM_L1.csv \\
        --new path/to/next_month.csv \\
        --out research/results/diffs/A350_MSN_2974_2026-04_to_2026-05.csv

    # Or programmatically:
    from tools.snapshot_diff import diff_snapshots, summarize
    df = diff_snapshots(old_df, new_df, sheet_type="OCCM")
    print(summarize(df))
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path
from typing import Iterable

# Allow running from project root with `python tools/snapshot_diff.py`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


DEFAULT_KEYS = {
    "OCCM": ("FIN", "PART_NUMBER"),
    "HT":   ("PART_NUMBER", "SERIAL_NUMBER"),
    "LLP":  ("NO",),
}


def _detect_sheet_type(df) -> str:
    """Best-effort sheet-type detection from column names."""
    cols = set(df.columns)
    if {"FIN", "PART_NUMBER", "SERIAL_NUMBER"} <= cols:
        return "OCCM"
    if {"PART_NUMBER", "AIRCRAFT", "DEADLINE"} <= cols:
        return "HT"
    if {"NO", "TSN", "CSN", "REMAINING"} <= cols:
        return "LLP"
    return "OCCM"   # safe default


def _make_key(row, key_cols: tuple[str, ...]) -> tuple:
    return tuple(str(row.get(c, "") or "").strip().upper() for c in key_cols)


def diff_snapshots(old_df, new_df, sheet_type: str | None = None,
                   key_cols: Iterable[str] | None = None,
                   ignore_cols: Iterable[str] | None = None):
    """Return a DataFrame describing differences between old and new snapshots.

    Output columns:
        _change   : "added" | "removed" | "changed" | "unchanged"
        _key      : the identity tuple as a comma-joined string
        _changes  : when _change="changed", "col:old→new,col:old→new,…"
        ...all canonical columns from the union of inputs (new values)
    """
    import pandas as pd

    if sheet_type is None:
        sheet_type = _detect_sheet_type(new_df)
    if key_cols is None:
        key_cols = DEFAULT_KEYS.get(sheet_type, ("PART_NUMBER", "SERIAL_NUMBER"))
    key_cols = tuple(key_cols)

    if ignore_cols is None:
        ignore_cols = set()
    ignore_cols = set(ignore_cols) | {
        "_issues", "_page", "_source", "_trailer", "_ref_htll", "_pn_known",
    }

    # Index both frames by key, preserving last-wins on duplicates within a snapshot
    old_by_key = {_make_key(r, key_cols): r for _, r in old_df.fillna("").iterrows()}
    new_by_key = {_make_key(r, key_cols): r for _, r in new_df.fillna("").iterrows()}

    all_keys = set(old_by_key) | set(new_by_key)
    out_rows: list[dict] = []

    union_cols = list(dict.fromkeys(list(new_df.columns) + list(old_df.columns)))
    union_cols = [c for c in union_cols if c not in ignore_cols]

    for key in sorted(all_keys):
        in_old = key in old_by_key
        in_new = key in new_by_key
        key_str = ",".join(key)

        if in_new and not in_old:
            row = dict(new_by_key[key])
            out_rows.append({"_change": "added", "_key": key_str, "_changes": "",
                             **{c: row.get(c, "") for c in union_cols}})
        elif in_old and not in_new:
            row = dict(old_by_key[key])
            out_rows.append({"_change": "removed", "_key": key_str, "_changes": "",
                             **{c: row.get(c, "") for c in union_cols}})
        else:
            old_row = dict(old_by_key[key])
            new_row = dict(new_by_key[key])
            changes = []
            for c in union_cols:
                ov = str(old_row.get(c, "") or "").strip()
                nv = str(new_row.get(c, "") or "").strip()
                if ov != nv:
                    # Truncate display values for readability
                    ov_disp = ov if len(ov) <= 40 else ov[:37] + "…"
                    nv_disp = nv if len(nv) <= 40 else nv[:37] + "…"
                    changes.append(f"{c}:{ov_disp}→{nv_disp}")
            change_kind = "changed" if changes else "unchanged"
            out_rows.append({"_change": change_kind, "_key": key_str,
                             "_changes": "; ".join(changes),
                             **{c: new_row.get(c, "") for c in union_cols}})

    df_out = pd.DataFrame(out_rows)
    # Friendly ordering: changes first, then unchanged
    order = {"added": 0, "changed": 1, "removed": 2, "unchanged": 3}
    df_out["_order"] = df_out["_change"].map(order)
    df_out = df_out.sort_values(["_order", "_key"]).drop(columns="_order").reset_index(drop=True)
    return df_out


def summarize(diff_df) -> str:
    counts = diff_df["_change"].value_counts().to_dict()
    return (
        f"Added:     {counts.get('added', 0)}\n"
        f"Removed:   {counts.get('removed', 0)}\n"
        f"Changed:   {counts.get('changed', 0)}\n"
        f"Unchanged: {counts.get('unchanged', 0)}\n"
        f"Total:     {len(diff_df)}"
    )


def _read_table(path: Path):
    import pandas as pd
    if path.suffix.lower() == ".xlsx":
        return pd.read_excel(path, dtype=str).fillna("")
    return pd.read_csv(path, dtype=str, na_filter=False)


def main():
    ap = argparse.ArgumentParser(description="Diff two Cypher snapshots.")
    ap.add_argument("--old", type=Path, required=True, help="prior CSV/XLSX")
    ap.add_argument("--new", type=Path, required=True, help="latest CSV/XLSX")
    ap.add_argument("--out", type=Path, required=True, help="output diff CSV")
    ap.add_argument("--sheet-type", choices=["OCCM", "HT", "LLP"],
                    help="override auto-detected sheet type")
    ap.add_argument("--key", nargs="+", help="override identity key columns")
    args = ap.parse_args()

    old_df = _read_table(args.old)
    new_df = _read_table(args.new)
    diff = diff_snapshots(old_df, new_df,
                          sheet_type=args.sheet_type,
                          key_cols=args.key)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    diff.to_csv(args.out, index=False)
    diff.to_excel(args.out.with_suffix(".xlsx"), index=False)

    print(f"\nDiff written to {args.out} ({len(diff)} rows)")
    print(summarize(diff))


if __name__ == "__main__":
    main()
