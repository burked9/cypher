"""L3 — OCR fallback for scanned PDFs.

Pipeline:
  1. Render each page at OCR-quality DPI.
  2. Tesseract page-segmentation mode 6 (uniform block of text) for table layouts.
  3. Cluster words into rows by Y coordinate (adaptive threshold).
  4. Discover column anchors:
       - Right side: from header tokens VENDOR / PART / SERIAL when Tesseract finds them.
       - Left side: from gap clustering on the X-starts of words in candidate
         data rows (rows whose first token is a 2- or 3-digit ATA chapter).
  5. Project each row's words to columns by nearest-anchor.

Sheet-type-specific normalization happens in `sheet_types/<type>.py`.
"""
from __future__ import annotations
import re
from typing import Iterator, Optional
from pathlib import Path

import numpy as np
import pandas as pd

# fitz (PyMuPDF) and pytesseract are lazy-imported inside the two functions
# that actually use them (_ocr_page, extract_records), not at module level.
# Neither has a Pyodide-compatible wheel -- a top-level import here would
# crash the moment this module loads in the browser, even though
# extract_records_from_words() (the in-browser OCR entry point; see
# deploy/main.py's run_with_ocr()) never touches either.


DEFAULT_COLUMNS = ["ATA", "ZONE", "FIN", "DESCRIPTION", "VENDOR_CODE", "PART_NUMBER", "SERIAL_NUMBER"]


def _ocr_page(page, dpi: int = 300) -> pd.DataFrame:
    import pytesseract
    from PIL import Image
    pix = page.get_pixmap(dpi=dpi)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    df = pytesseract.image_to_data(img, output_type=pytesseract.Output.DATAFRAME, config="--psm 6")
    df = df.dropna(subset=["text"])
    df = df[df["text"].astype(str).str.strip() != ""]
    df = df[df["conf"].astype(float) > 30].copy()
    return df


def _cluster_rows(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["top", "left"]).reset_index(drop=True)
    median_h = df["height"].median() if len(df) else 20
    df["row_id"] = (df["top"].diff().fillna(0).abs() > median_h * 0.7).cumsum()
    return df


def _find_data_rows(df: pd.DataFrame):
    """A data row starts with a 2-digit ATA followed by a 2-3-digit ZONE.
    Requiring both filters out letterhead lines like '10 April 2017'."""
    rows = []
    for rid, g in df.groupby("row_id"):
        g = g.sort_values("left")
        words = g["text"].astype(str).tolist()
        if len(words) < 2:
            continue
        if re.match(r"^\d{2}$", words[0]) and re.match(r"^\d{2,3}$", words[1]):
            rows.append((rid, g))
    return rows


def _find_right_anchors(df: pd.DataFrame) -> dict:
    """Locate VENDOR / PART / SERIAL header tokens; return {col: x_left}."""
    anchors = {}
    for col, tok in (("VENDOR_CODE", "VENDOR"), ("PART_NUMBER", "PART"), ("SERIAL_NUMBER", "SERIAL")):
        hits = df[df["text"].astype(str).str.upper().str.strip(":") == tok]
        if not hits.empty:
            anchors[col] = int(hits["left"].iloc[0])
    return anchors


def _gap_cluster_left(xs: list[int], n_bins: int) -> list[int]:
    """Greedy gap-based 1-D clustering, returns cluster left edges."""
    if not xs:
        return []
    xs = sorted(xs)
    if len(xs) < n_bins:
        return xs
    gaps = np.diff(xs)
    if len(gaps) == 0:
        return [xs[0]]
    thr = sorted(gaps, reverse=True)[n_bins - 1] if len(gaps) >= n_bins - 1 else 0
    clusters, current = [], [xs[0]]
    for x, gap in zip(xs[1:], gaps):
        if gap >= thr and len(clusters) < n_bins - 1:
            clusters.append(current)
            current = [x]
        else:
            current.append(x)
    clusters.append(current)
    return [int(np.median(c)) for c in clusters]


def _discover_anchors(all_data_rows: list, columns: list[str]) -> list[Optional[int]]:
    """
    Strategy:
      - Right-side cols (VENDOR_CODE, PART_NUMBER, SERIAL_NUMBER) come from
        header anchors if available.
      - Left-side cols (ATA, ZONE, FIN, DESCRIPTION) come from gap-clustering
        the x-starts of words to the left of the rightmost left-side region.
    """
    right_cols = ["VENDOR_CODE", "PART_NUMBER", "SERIAL_NUMBER"]
    left_cols = [c for c in columns if c not in right_cols]

    # Aggregate header anchors across pages
    right_anchor_xs: dict[str, list[int]] = {c: [] for c in right_cols}
    for page_df, _drows in all_data_rows:
        anchors = _find_right_anchors(page_df)
        for c, x in anchors.items():
            right_anchor_xs[c].append(x)
    right_centers = {c: int(np.median(xs)) for c, xs in right_anchor_xs.items() if xs}

    # Left-side cutoff = leftmost right anchor minus a buffer
    cutoff = (min(right_centers.values()) - 50) if right_centers else 1300

    # Collect all word X-starts for data rows in the left region
    left_xs = []
    for _df, drows in all_data_rows:
        for _rid, g in drows:
            for x in g[g["left"] < cutoff]["left"].tolist():
                left_xs.append(int(x))

    left_centers_list = _gap_cluster_left(left_xs, len(left_cols))

    # Build the anchor list in column order
    anchors = []
    for c in columns:
        if c in right_cols:
            anchors.append(right_centers.get(c))
        else:
            # left_cols ordered same as columns; index by left position
            idx = left_cols.index(c)
            anchors.append(left_centers_list[idx] if idx < len(left_centers_list) else None)
    return anchors


FIN_PATTERN = re.compile(r"^[A-Za-z0-9]{2,8}$")


def _assign_positional(g: pd.DataFrame, columns: list[str], right_anchors: dict[str, int]) -> list[str]:
    """OCCM-aware row split.

    Left side is *positional*, not anchor-based:
      - 1st word -> ATA
      - 2nd word -> ZONE
      - 3rd word -> FIN if it looks like a FIN code, otherwise FIN stays empty
        and the word becomes part of DESCRIPTION.
      - DESCRIPTION absorbs all remaining words up to the leftmost right-side
        anchor (with a small buffer).

    Right side uses anchor-based bucketing for VENDOR_CODE / PART_NUMBER /
    SERIAL_NUMBER, since those are reliably column-aligned.
    """
    g = g.sort_values("left").reset_index(drop=True)
    words = g["text"].astype(str).tolist()
    lefts = g["left"].astype(int).tolist()
    centers = (g["left"] + g["width"] / 2).astype(int).tolist()

    out = {c: "" for c in columns}

    # Build fast lookup of right-side anchors and the leftmost cutoff
    right_cols = [c for c in ("VENDOR_CODE", "PART_NUMBER", "SERIAL_NUMBER") if c in columns]
    right_xs = {c: right_anchors[c] for c in right_cols if c in right_anchors}
    cutoff = min(right_xs.values()) - 50 if right_xs else 10**6

    # Split words into left-of-cutoff and right-of-cutoff
    left_idx = [i for i, x in enumerate(lefts) if x < cutoff]
    right_idx = [i for i, x in enumerate(lefts) if x >= cutoff]

    # Left side positional
    if "ATA" in columns and len(left_idx) >= 1:
        out["ATA"] = words[left_idx[0]]
    if "ZONE" in columns and len(left_idx) >= 2:
        out["ZONE"] = words[left_idx[1]]

    desc_start = 2  # default — assume FIN is 3rd word
    if "FIN" in columns and len(left_idx) >= 3:
        candidate = words[left_idx[2]]
        if FIN_PATTERN.match(candidate):
            out["FIN"] = candidate
            desc_start = 3
        else:
            # FIN missing — third word starts the description
            desc_start = 2

    if "DESCRIPTION" in columns:
        desc_words = [words[i] for i in left_idx[desc_start:]]
        out["DESCRIPTION"] = " ".join(desc_words)

    # Right side: nearest-anchor bucketing
    if right_xs:
        buckets: dict[str, list[str]] = {c: [] for c in right_cols}
        for i in right_idx:
            x = centers[i]
            best = min(right_xs.items(), key=lambda kv: abs(x - kv[1]))[0]
            buckets[best].append(words[i])
        for c, ws in buckets.items():
            out[c] = " ".join(ws).strip()

    return [out[c] for c in columns]


def _records_from_page_dfs(page_dfs: list[tuple[pd.DataFrame, int]], columns: list[str]) -> list[dict]:
    """Shared core, independent of where the word boxes came from. Each entry
    in `page_dfs` is (raw_word_df, page_num), where raw_word_df has columns
    left/top/width/height/conf/text -- the shape `pytesseract.image_to_data`'s
    DATAFRAME output has, and what the browser's Tesseract.js path (see
    `extract_records_from_words` below) is built to match exactly."""
    page_data = []
    for df, page_num in page_dfs:
        clustered = _cluster_rows(df)
        drows = _find_data_rows(clustered)
        page_data.append((clustered, drows, page_num))

    # Aggregate right-side header anchors across pages
    right_anchor_xs: dict[str, list[int]] = {c: [] for c in ("VENDOR_CODE", "PART_NUMBER", "SERIAL_NUMBER")}
    for df, _drows, _ in page_data:
        for c, x in _find_right_anchors(df).items():
            right_anchor_xs[c].append(x)
    right_anchors = {c: int(np.median(xs)) for c, xs in right_anchor_xs.items() if xs}

    records = []
    for _df, drows, page_num in page_data:
        for _rid, g in drows:
            cols = _assign_positional(g, columns, right_anchors)
            rec = dict(zip(columns, cols))
            rec["_page"] = page_num
            records.append(rec)
    return records


def extract_records(pdf_path: str, columns: list[str] = DEFAULT_COLUMNS) -> list[dict]:
    """End-to-end extraction from a local PDF via pytesseract. Returns a list
    of dicts keyed by `columns` plus `_page`."""
    import fitz
    doc = fitz.open(pdf_path)
    page_dfs = [(_ocr_page(page), i + 1) for i, page in enumerate(doc)]
    return _records_from_page_dfs(page_dfs, columns)


_WORD_COLS = ["left", "top", "width", "height", "conf", "text"]


def extract_records_from_words(pages_words: list[list[dict]],
                                columns: list[str] = DEFAULT_COLUMNS) -> list[dict]:
    """Same extraction as `extract_records`, but from word boxes OCR'd
    elsewhere (the browser's Tesseract.js, via `ocr_bridge.js`'s `ocrCanvas()`)
    instead of running pytesseract locally -- Pyodide has no `tesseract`
    binary for pytesseract to shell out to, so this is the in-browser path's
    only way to reach this module's column-projection logic.

    `pages_words[i]` is page i+1's word list: dicts with left/top/width/
    height/conf/text, already filtered to conf > 30 and non-empty text by
    the JS side (mirrored here too, defensively, in case a caller doesn't).
    """
    page_dfs = []
    for i, words in enumerate(pages_words):
        df = pd.DataFrame(words, columns=_WORD_COLS) if words else pd.DataFrame(columns=_WORD_COLS)
        if not df.empty:
            df = df.dropna(subset=["text"])
            df = df[df["text"].astype(str).str.strip() != ""]
            df = df[df["conf"].astype(float) > 30].copy()
        page_dfs.append((df, i + 1))
    return _records_from_page_dfs(page_dfs, columns)


def extract_tables(pdf_path: str, page_range: tuple[int, int] | None = None) -> Iterator[list[list[str]]]:
    """Generator interface matching the L1/L2 signature."""
    records = extract_records(pdf_path)
    yield [list(r.values()) for r in records]
