# Cypher — design notes

## Two orthogonal axes

- **Resolution level** (L1–L5) — extraction strategy, escalating cost:
  L1 text-layer, L2 layout-aware (reserved), L3 OCR (Tesseract/Tesseract.js),
  L4 PaddleOCR (Colab), L5 docling (Colab, recon stage).
- **Sheet type** (OCCM/HT/LLP) — what the table means; drives column normalization and validation.

## Stability rules

- Process **one page at a time** — never load whole doc into memory.
- Hard memory ceiling estimated; above it, point user at the Colab fallback.

## Deploy

- Static GitHub Pages site.
- Pyodide loaded from jsdelivr CDN.
- L3 OCR uses Tesseract.js (not pytesseract via Pyodide) — too heavy otherwise.
- PDFs never leave the browser.
