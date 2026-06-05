"""Debug visualizer — renders a PDF page with colored bounding boxes around each
OCR'd word, colored by which column it was assigned to. Lets an analyst see at
a glance where the extractor is making mistakes.

Usage from the notebook:
    from shared.debug_render import render_debug_pages
    render_debug_pages("research/test_pdfs/afl_test.pdf",
                      out_dir="research/results/by_pdf/afl_test_debug")
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional

import fitz  # pymupdf
import pytesseract
from PIL import Image, ImageDraw, ImageFont

from levels.L3_ocr.extract import (
    _ocr_page, _cluster_rows, _find_data_rows, _find_right_anchors,
    FIN_PATTERN, DEFAULT_COLUMNS,
)

# One distinct colour per column
COL_COLORS = {
    "ATA":           (220,  20,  60),  # crimson
    "ZONE":          (255, 140,   0),  # dark orange
    "FIN":           (255, 215,   0),  # gold
    "DESCRIPTION":   ( 30, 144, 255),  # dodger blue
    "VENDOR_CODE":   ( 50, 205,  50),  # lime green
    "PART_NUMBER":   (138,  43, 226),  # blue violet
    "SERIAL_NUMBER": (255,   0, 255),  # magenta
    "_skip":         (128, 128, 128),  # grey for non-data words
}


def _classify_word(idx: int, total_left: int, lefts: list[int],
                   words: list[str], cutoff: int,
                   right_xs: dict[str, int]) -> str:
    """Mirror the assignment logic in extract.py to label one word."""
    if lefts[idx] >= cutoff:
        # right-side: nearest anchor
        center = lefts[idx]  # close enough
        return min(right_xs.items(), key=lambda kv: abs(center - kv[1]))[0]
    # left-side positional
    left_indices = [i for i, x in enumerate(lefts) if x < cutoff]
    pos = left_indices.index(idx)
    if pos == 0:
        return "ATA"
    if pos == 1:
        return "ZONE"
    if pos == 2 and FIN_PATTERN.match(words[idx]):
        return "FIN"
    return "DESCRIPTION"


def render_debug_pages(pdf_path: str, out_dir: str, dpi: int = 200) -> list[Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(pdf_path)

    # Discover right-side anchors across all pages (same logic as extractor)
    right_anchor_xs: dict[str, list[int]] = {c: [] for c in ("VENDOR_CODE", "PART_NUMBER", "SERIAL_NUMBER")}
    for page in doc:
        df = _ocr_page(page)
        for c, x in _find_right_anchors(df).items():
            right_anchor_xs[c].append(x)
    right_anchors = {c: int(sum(xs) / len(xs)) for c, xs in right_anchor_xs.items() if xs}
    cutoff = (min(right_anchors.values()) - 50) if right_anchors else 10**6

    saved = []
    for i, page in enumerate(doc):
        # Render page (lower DPI for the debug image is fine — output is for eyeballing)
        pix = page.get_pixmap(dpi=dpi)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples).convert("RGBA")
        draw = ImageDraw.Draw(img, "RGBA")

        # OCR at the same DPI used by the extractor (300) to match coords, then scale
        ocr_pix = page.get_pixmap(dpi=300)
        ocr_img = Image.frombytes("RGB", (ocr_pix.width, ocr_pix.height), ocr_pix.samples)
        df = pytesseract.image_to_data(ocr_img, output_type=pytesseract.Output.DATAFRAME, config="--psm 6")
        df = df.dropna(subset=["text"])
        df = df[df["text"].astype(str).str.strip() != ""]
        df = df[df["conf"].astype(float) > 30].copy()

        scale = dpi / 300.0
        df_clustered = _cluster_rows(df.copy())
        data_rids = {rid for rid, _g in _find_data_rows(df_clustered)}

        # Build a lookup: rid -> sorted indices into df
        rows_by_rid: dict = {}
        for rid, g in df_clustered.groupby("row_id"):
            rows_by_rid[rid] = g.sort_values("left")

        for rid, g in rows_by_rid.items():
            words = g["text"].astype(str).tolist()
            lefts = g["left"].astype(int).tolist()
            tops = g["top"].astype(int).tolist()
            widths = g["width"].astype(int).tolist()
            heights = g["height"].astype(int).tolist()

            for idx in range(len(words)):
                if rid in data_rids:
                    label = _classify_word(idx, len(words), lefts, words, cutoff, right_anchors)
                else:
                    label = "_skip"
                color = COL_COLORS.get(label, COL_COLORS["_skip"])
                x0 = int(lefts[idx] * scale)
                y0 = int(tops[idx] * scale)
                x1 = int((lefts[idx] + widths[idx]) * scale)
                y1 = int((tops[idx] + heights[idx]) * scale)
                draw.rectangle([x0, y0, x1, y1], outline=color + (255,), width=2)
                draw.rectangle([x0, y0, x1, y1], fill=color + (40,))

        # Legend in top-left
        ly = 10
        for col, color in COL_COLORS.items():
            draw.rectangle([10, ly, 30, ly + 14], fill=color + (255,))
            draw.text((36, ly), col, fill=(0, 0, 0))
            ly += 18

        out_path = out / f"page_{i+1}_debug.png"
        img.convert("RGB").save(out_path)
        saved.append(out_path)
    return saved
