# Cypher — design notes

## Two orthogonal axes

- **Resolution level** (L1/L2/L3) — extraction strategy, escalating cost.
- **Sheet type** (OCCM/HT/LLP) — what the table means; drives column normalization and validation.

The benchmarking workbook tracks the (sheet_type × level) matrix. Aim: after ~20 examples, learn the distribution and decide whether automatic level escalation is worthwhile.

## Stability rules

- Process **one page at a time** — never load whole doc into memory.
- Page-range selector exposed in the UI.
- Progress indicator + cancel button.
- Hard memory ceiling estimated; above it, point user at the Colab fallback.

## Deploy

- Static GitHub Pages site.
- Pyodide loaded from jsdelivr CDN.
- L3 OCR uses Tesseract.js (not pytesseract via Pyodide) — too heavy otherwise.
- PDFs never leave the browser.
