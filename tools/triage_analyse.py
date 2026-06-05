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
    args = ap.parse_args()

    rows: list[dict] = []
    with args.triage_csv.open() as f:
        rows = list(csv.DictReader(f))

    print(f"\nLoaded {len(rows)} rows from {args.triage_csv.name}\n")

    # ── 1. Bucket counts by (sheet_type, variant) ───────────────────────────
    bucket = Counter((r["sheet_type"], r["variant"]) for r in rows)
    print("=" * 60)
    print("Bucket counts — (sheet_type, variant)")
    print("=" * 60)
    for (st, v), n in bucket.most_common():
        print(f"  {st:8s}  {v:24s}  {n:4d}")

    # ── 2. Operator hint frequencies ────────────────────────────────────────
    hint_freq = Counter()
    for r in rows:
        if r["variant"] == "Unknown":
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
    unknowns = [r for r in rows if r["variant"] == "Unknown"]
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
