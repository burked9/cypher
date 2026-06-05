# L1 — text-layer parsing

`pdfplumber.extract_tables()` against PDFs that already have a text layer. Cheap, fast, works for most well-structured exports.

**Falls back to L2** when: row count below threshold, expected columns missing, or text layer absent.
