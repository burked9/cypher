# L3 — OCR fallback

Scanned PDFs with no text layer. Heavy in-browser; very large docs route to a Colab fallback linked from the deployed page.

**Deploy path**: Tesseract.js (JS/WASM) does the OCR; Python receives recognized text + bounding boxes and reconstructs tables.

**Research path**: pytesseract locally for offline benchmarking.
