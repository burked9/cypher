"""Analyse the output of `tools/triage.py`.

Takes `triage_occm.csv` (or any triage CSV) and produces:

  1. Bucket counts by (sheet_type, variant) — what we already handle vs what's
     new.
  2. Operator-hint frequency table — surface registration prefixes / airline
     name signals.
  3. A character-trigram similarity cluster of the Unknown rows, so we can
     turn "200 unknowns" into "8 clusters of ~25 each, write 8 variants".
  4. Per-cluster representative files (1-3 PDFs with the smallest distance to
     the cluster centroid) — copy-paste paths to inspect manually.

Output: prints to stdout. Writes a small `triage_clusters.csv` companion
file alongside the input.

Usage
-----
    python tools/triage_analyse.py research/results/triage_occm.csv
"""
from __future__ import annotations
import argparse
import csv
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path


def _trigrams(s: str) -> Counter:
    """Character-trigram bag for cosine similarity."""
    s = re.sub(r"\s+", " ", s).strip().lower()
    return Counter(s[i:i + 3] for i in range(len(s) - 2))


def _cosine(a: Counter, b: Counter) -> float:
    """Cosine similarity between two trigram bags. 0 = orthogonal, 1 = identical."""
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    dot = sum(a[t] * b[t] for t in common)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


def _cluster(unknowns: list[dict], threshold: float = 0.55) -> list[list[dict]]:
    """Greedy single-link clustering: each row joins the first existing cluster
    whose centroid has cosine ≥ threshold; otherwise it seeds a new cluster.
    The centroid is the trigram bag of the first row added; cheap and
    effective for letterhead-dominated text where one operator's documents
    look highly similar to each other.
    """
    clusters: list[list[dict]] = []
    centroids: list[Counter] = []
    for row in unknowns:
        tg = _trigrams(row["first_500_chars"])
        placed = False
        for i, c in enumerate(centroids):
            if _cosine(tg, c) >= threshold:
                clusters[i].append(row)
                placed = True
                break
        if not placed:
            clusters.append([row])
            centroids.append(tg)
    # Sort biggest first
    order = sorted(range(len(clusters)), key=lambda i: -len(clusters[i]))
    return [clusters[i] for i in order]


def _centroid_representative(cluster: list[dict], k: int = 3) -> list[dict]:
    """Pick the k rows with the highest mean similarity to the rest of the cluster."""
    if len(cluster) <= k:
        return cluster
    bags = [_trigrams(r["first_500_chars"]) for r in cluster]
    scores = []
    for i, bi in enumerate(bags):
        s = sum(_cosine(bi, bj) for j, bj in enumerate(bags) if i != j)
        scores.append((s / (len(bags) - 1), i))
    top = [cluster[i] for _, i in sorted(scores, reverse=True)[:k]]
    return top


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("triage_csv", type=Path)
    ap.add_argument("--threshold", type=float, default=0.55,
                    help="cosine threshold for cluster membership (default 0.55)")
    ap.add_argument("--compare-thresholds", action="store_true",
                    help="run clustering at several thresholds and print a "
                         "comparison table instead of clustering once — use "
                         "this to actually decide whether 'resolution' "
                         "(the cosine threshold) should move, instead of "
                         "guessing. Higher threshold = stricter match = "
                         "more, smaller clusters ('finer resolution'). Lower "
                         "= looser match = fewer, bigger clusters ('coarser').")
    args = ap.parse_args()

    # Some source PDFs have unusual/corrupted font encodings that make
    # pdfplumber extract raw control bytes instead of text (seen on the
    # "-SHT#" engineering-document family, not a real HT/OCCM/LLP sheet
    # to begin with) -- those NUL bytes land in first_500_chars and crash
    # Python's csv reader outright. Strip them per-line rather than
    # letting one garbled file take down analysis of the whole corpus.
    rows: list[dict] = []
    with args.triage_csv.open(newline="") as f:
        rows = list(csv.DictReader(line.replace("\0", "") for line in f))

    print(f"\nLoaded {len(rows)} rows from {args.triage_csv.name}\n")

    # ── 1. Bucket counts by (sheet_type, variant) ───────────────────────────
    bucket = Counter((r["sheet_type"], r["variant"]) for r in rows)
    print("=" * 60)
    print("Bucket counts — (sheet_type, variant)")
    print("=" * 60)
    for (st, v), n in bucket.most_common():
        print(f"  {st:8s}  {v:24s}  {n:4d}")

    # ── 1b. L2 candidates — files where L1 is silently dropping row text ───
    # See tools/triage.py's docstring for exactly what this checks and its
    # caveat (only the generic pdfplumber-table + ATA/ZONE-gate pattern).
    l2_checked = [r for r in rows if r.get("l2_kept_rows") not in (None, "", "-1")]
    l2_na = [r for r in l2_checked if r.get("l2_candidate") == "n/a"]
    l2_meaningful = [r for r in l2_checked if r.get("l2_candidate") in ("True", "False")]
    l2_flagged = [r for r in l2_meaningful if r.get("l2_candidate") == "True"]
    if l2_checked:
        print("\n" + "=" * 60)
        print(f"L2 candidates — {len(l2_flagged)} of {len(l2_meaningful)} files the "
              f"generic pattern actually applies to are dropping row text")
        print("=" * 60)
        if l2_na:
            print(f"  ({len(l2_na)} more had kept=0 — the generic ATA/ZONE pattern "
                  f"didn't match their rows at all, almost always a bespoke-variant "
                  f"file, not an L2 finding either way — excluded above)")
        if l2_flagged:
            by_variant = Counter((r["sheet_type"], r["variant"]) for r in l2_flagged)
            for (st, v), n in by_variant.most_common():
                print(f"  {st:8s}  {v:24s}  {n:4d} file(s) flagged")
            print("\n  Worst offenders (by dropped-row count):")
            worst = sorted(l2_flagged, key=lambda r: -int(r["l2_dropped_rows"]))[:10]
            for r in worst:
                print(f"    {r['l2_dropped_rows']:>4s} dropped / {r['l2_kept_rows']:>4s} kept  "
                      f"— {r['sheet_type']}/{r['variant']}  {r['filename']}")
        else:
            print("  None flagged — no evidence yet that L2 is needed on this corpus.")

    # "Unknown" variant alone isn't enough to mean "a real file we couldn't
    # match" -- NotDownloaded/Timeout placeholder rows also carry
    # variant=Unknown (for consistency with how they're written), but they
    # were never actually opened and have no content to hint at or cluster
    # on. Filtering sheet_type too keeps those out of both the hint
    # frequency table and the clustering pool below.
    real_unknown = lambda r: r["variant"] == "Unknown" and r["sheet_type"] not in ("NotDownloaded", "Timeout")

    # ── 2. Operator hint frequencies ────────────────────────────────────────
    hint_freq = Counter()
    for r in rows:
        if real_unknown(r):
            for piece in (r["operator_hint"] or "").split(" · "):
                p = piece.strip()
                if p:
                    hint_freq[p] += 1
    if hint_freq:
        print("\n" + "=" * 60)
        print("Operator hints — Unknown rows only (top 20)")
        print("=" * 60)
        for hint, n in hint_freq.most_common(20):
            print(f"  {n:4d}  {hint}")

    # ── 3. Cluster the Unknowns ─────────────────────────────────────────────
    unknowns = [r for r in rows if real_unknown(r)]

    if unknowns and args.compare_thresholds:
        print(f"\n{'=' * 60}")
        print(f"Threshold comparison — {len(unknowns)} Unknown rows")
        print("=" * 60)
        print("  higher threshold → stricter match → more, smaller clusters (finer)")
        print("  lower threshold  → looser match   → fewer, bigger clusters (coarser)\n")
        print(f"  {'threshold':>9s}  {'clusters':>8s}  {'singletons':>10s}  {'largest':>7s}  {'median':>6s}")
        for t in (0.35, 0.45, 0.55, 0.65, 0.75, 0.85):
            clusters = _cluster(unknowns, threshold=t)
            sizes = sorted((len(c) for c in clusters), reverse=True)
            singles = sum(1 for s in sizes if s == 1)
            median = sizes[len(sizes) // 2] if sizes else 0
            marker = "  <- default" if abs(t - 0.55) < 1e-9 else ""
            print(f"  {t:9.2f}  {len(clusters):8d}  {singles:10d}  {sizes[0]:7d}  {median:6d}{marker}")
        print("\n  A good threshold: cluster count << unknown count (real grouping "
              "happening), and singleton count isn't most of the clusters (else "
              "it's barely different from no clustering at all). Too low a "
              "threshold shows up as one giant cluster swallowing everything — "
              "watch the 'largest' column for that.")
        return

    if unknowns:
        print(f"\n{'=' * 60}")
        print(f"Clustering {len(unknowns)} Unknown rows (threshold {args.threshold})")
        print("=" * 60)
        clusters = _cluster(unknowns, threshold=args.threshold)
        print(f"  → {len(clusters)} clusters\n")

        cluster_out_path = args.triage_csv.with_name(
            args.triage_csv.stem.replace("triage_", "clusters_") + ".csv"
        )
        with cluster_out_path.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["cluster_id", "size", "rep_filename", "rep_path",
                        "operator_hint", "first_120"])
            for ci, cluster in enumerate(clusters):
                reps = _centroid_representative(cluster, k=3)
                size = len(cluster)
                # Print a summary block per cluster
                rep = reps[0]
                head = (rep["first_500_chars"] or "")[:120]
                hint = rep["operator_hint"] or "—"
                print(f"  cluster {ci:2d}  ·  {size:3d} files  ·  hint: {hint}")
                print(f"    rep: {rep['filename']}")
                print(f"    head: {head}")
                if size > 1:
                    other_reps = [r["filename"] for r in reps[1:]]
                    if other_reps:
                        print(f"    also-central: {' / '.join(other_reps)}")
                print()
                for r in reps:
                    w.writerow([
                        ci, size, r["filename"], r["path"],
                        r["operator_hint"], (r["first_500_chars"] or "")[:120],
                    ])
        print(f"Wrote {cluster_out_path}")


if __name__ == "__main__":
    main()
