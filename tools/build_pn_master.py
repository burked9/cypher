"""Build `shared/pn_master.bloom` from a CSV / XLSX of authoritative reference data.

Run once locally on the source data — the resulting binary is committed and
shipped with Cypher; the source CSV/XLSX is **never** published.

Usage
-----
    python tools/build_pn_master.py path/to/master.csv \
        --pn-col PartNumber                  \
        --mfr-col CAGECode                   \
        --ata-col ATA                        \
        --fp-rate 0.001                      \
        --out shared/pn_master.bloom

Either a single CSV/XLSX or multiple files can be passed; values are
deduplicated and uppercased before insertion.

Statistics on the resulting filter (size, expected FP rate) are printed so
you can confirm the trade-off before committing.
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

# Make `shared.pn_master` importable when running from the project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.pn_master import PNMaster   # noqa: E402


def _load_table(path: Path):
    """Return a pandas DataFrame from CSV / XLSX / TSV."""
    import pandas as pd
    suffix = path.suffix.lower()
    if suffix in (".csv", ".tsv", ".txt"):
        sep = "\t" if suffix == ".tsv" else ","
        return pd.read_csv(path, sep=sep, dtype=str, na_filter=False, low_memory=False)
    if suffix in (".xlsx", ".xlsm"):
        return pd.read_excel(path, dtype=str)
    raise ValueError(f"Unsupported file type: {path}")


def _column_values(df, col_name: str | None) -> list[str]:
    if col_name is None:
        return []
    if col_name not in df.columns:
        # Try case-insensitive match
        lower = {c.lower(): c for c in df.columns}
        if col_name.lower() in lower:
            col_name = lower[col_name.lower()]
        else:
            raise ValueError(f"Column {col_name!r} not in table. Available: {list(df.columns)[:30]}")
    series = df[col_name].astype(str).map(str.strip)
    series = series[(series != "") & (series.str.lower() != "nan")]
    return series.unique().tolist()


def main():
    ap = argparse.ArgumentParser(description="Build a Cypher PN master Bloom filter.")
    ap.add_argument("inputs", nargs="+", type=Path, help="CSV / XLSX file(s) with the master list")
    ap.add_argument("--pn-col",  default="PartNumber",  help="column name for part numbers (default: PartNumber)")
    ap.add_argument("--mfr-col", default=None,          help="column name for manufacturer/CAGE/vendor codes (optional)")
    ap.add_argument("--ata-col", default=None,          help="column name for ATA chapters (optional)")
    ap.add_argument("--fp-rate", type=float, default=0.001, help="target false-positive rate (default 0.001 = 0.1%%)")
    ap.add_argument("--out",     type=Path, default=Path("shared/pn_master.bloom"))
    args = ap.parse_args()

    # Aggregate values across all input files
    pns: list[str] = []
    mfrs: list[str] = []
    atas: list[str] = []
    for path in args.inputs:
        if not path.exists():
            ap.error(f"Input not found: {path}")
        df = _load_table(path)
        pns  += _column_values(df, args.pn_col)
        mfrs += _column_values(df, args.mfr_col)
        atas += _column_values(df, args.ata_col)
        print(f"  loaded {path.name}: rows={len(df)}  pn+={len(pns)} mfr+={len(mfrs)} ata+={len(atas)}")

    pns  = sorted(set(p.upper() for p in pns))
    mfrs = sorted(set(m.upper() for m in mfrs))
    atas = sorted(set(a.upper() for a in atas))
    print(f"\nUnique items: pn={len(pns)}  mfr={len(mfrs)}  ata={len(atas)}")

    namespaces: dict[str, list[str]] = {"pn": pns}
    if mfrs: namespaces["mfr"] = mfrs
    if atas: namespaces["ata"] = atas

    master = PNMaster.build(namespaces, fp_rate=args.fp_rate)
    blob = master.to_bytes()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(blob)
    print(f"\nWrote {args.out}  ({len(blob) / 1024:.1f} KB,  fp-rate target {args.fp_rate})")
    print("Namespaces:")
    for tag, vals in namespaces.items():
        print(f"  {tag:4s}  {len(vals):>9d} items")


if __name__ == "__main__":
    main()
