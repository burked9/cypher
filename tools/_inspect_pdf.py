"""Per-PDF inspection helper — invoked as a subprocess from triage.py.

Reads first-3-pages text + page count, prints a single JSON line on stdout.
Lives in its own process so triage.py can hard-kill it on timeout when
OneDrive's File Provider hangs on `fz_open_document`.

Usage:
    python tools/_inspect_pdf.py <pdf_path>
"""
from __future__ import annotations
import json
import sys


def main():
    if len(sys.argv) != 2:
        print(json.dumps({"error": "usage"}))
        sys.exit(2)
    path = sys.argv[1]
    try:
        import fitz   # noqa: import inside function so the import cost is per-process
        doc = fitz.open(path)
        total = len(doc)
        parts = []
        tp = sc = 0
        for i in range(total):
            t = doc[i].get_text() or ""
            n = len(t)
            if n > 1000:
                tp += 1
            elif n < 200:
                sc += 1
            if i < 3:
                parts.append(t)
        print(json.dumps({
            "text": "\n".join(parts),
            "total_pages": total,
            "text_pages": tp,
            "scanned_pages": sc,
        }))
    except Exception as e:
        print(json.dumps({"error": f"{type(e).__name__}: {e}"}))
        sys.exit(3)


if __name__ == "__main__":
    main()
