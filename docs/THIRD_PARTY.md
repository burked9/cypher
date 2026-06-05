# Third-party dependencies

Cypher is MIT-licensed. The libraries it depends on are listed below with their respective licenses. None are bundled — they are installed at runtime via `pip` (locally) or `micropip` (Pyodide).

## Runtime — local pipeline

| Library | License | Notes |
|---------|---------|-------|
| [pdfplumber](https://github.com/jsvine/pdfplumber) | MIT | L1 text-layer parsing |
| [pdfminer.six](https://github.com/pdfminer/pdfminer.six) | MIT | Transitive (via pdfplumber) |
| [PyMuPDF](https://github.com/pymupdf/PyMuPDF) | AGPL-3.0 | Used locally for page rendering and text extraction. **The deploy does not bundle PyMuPDF**; we use `pdfplumber` (MIT) in-browser to keep the static site MIT-clean. |
| [Pillow](https://github.com/python-pillow/Pillow) | MIT-CMU | Image handling |
| [pytesseract](https://github.com/madmaze/pytesseract) | Apache-2.0 | Python wrapper for Tesseract |
| [Tesseract](https://github.com/tesseract-ocr/tesseract) | Apache-2.0 | OS-level OCR engine |
| [pandas](https://github.com/pandas-dev/pandas) | BSD-3-Clause | DataFrames |
| [openpyxl](https://foss.heptapod.net/openpyxl/openpyxl) | MIT | XLSX writing |
| [Jupyter](https://github.com/jupyter/jupyter) | BSD-3-Clause | Notebook |

### PyMuPDF AGPL note

PyMuPDF is AGPL-3.0 and is therefore used **only in local research tooling** (the L3 OCR extractor for Aeroflot, the bbox debug renderer, the report builder). It is intentionally excluded from `deploy/_pymods/` so the deployed static site contains no AGPL code and remains MIT-licensed end-to-end. If you fork Cypher and want to redistribute a binary or hosted version, either keep this separation or comply with AGPL terms.

## Runtime — in-browser deploy (Pyodide)

| Library | License | Notes |
|---------|---------|-------|
| [Pyodide](https://github.com/pyodide/pyodide) | MPL-2.0 | Python-in-WASM runtime |
| pdfplumber 0.9.0 | MIT | Pinned: 0.10+ requires `pypdfium2`, which has no Pyodide-compatible wheel |
| pdfminer.six | MIT | Transitive |
| Pillow | MIT-CMU | Bundled in Pyodide |

## L4 (Colab notebook) — optional

| Library | License | Notes |
|---------|---------|-------|
| [PaddlePaddle](https://github.com/PaddlePaddle/Paddle) | Apache-2.0 | ML framework PaddleOCR runs on |
| [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) | Apache-2.0 | PP-Structure table model |
| [pdf2image](https://github.com/Belval/pdf2image) | MIT | PDF → image rendering in the notebook |
| [poppler-utils](https://poppler.freedesktop.org/) | GPL-2.0/3.0 | Image conversion backend used by pdf2image. Apt-installed at notebook runtime; not bundled into Cypher. |

L4 runs entirely on Google Colab compute when invoked. No L4 dependency is shipped in this repository.

## EasyOCR (alternative L4 backend)

| Library | License | Notes |
|---------|---------|-------|
| [EasyOCR](https://github.com/JaidedAI/EasyOCR) | Apache-2.0 | Alternative OCR engine if PaddleOCR is unavailable |

## Attributions

- The variant detection / column-schema architecture takes inspiration from format-aware parsers commonly used in document-processing pipelines.
- The Pyodide deployment pattern follows [Pyodide's official examples](https://pyodide.org/en/stable/usage/quickstart.html) for in-browser Python.

If a license file or attribution is missing, please open an issue.
