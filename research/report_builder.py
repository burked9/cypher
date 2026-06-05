"""Build a self-contained offline HTML report covering the entire project state.

Sections:
  1. Scoreboard — cross-PDF headline numbers.
  2. Configuration & rules — every rule the analyst needs to know about,
     pulled directly from the source modules so docs and code can't drift.
  3. Issue frequency analysis — cross-corpus aggregates with bar charts.
  4. Per-PDF deep dive — metadata, raw text, full extracted table (filterable),
     issue counts, bbox debug overlays.
  5. Architecture flow — the routing logic from PDF in to records out.

Output: research/report.html, single file, all images base64-embedded, all
JS/CSS inline. Open in any browser, works offline.

Usage:
    python research/report_builder.py
"""
from __future__ import annotations
import base64
import html
import json
import re
import sys
from collections import Counter
from io import BytesIO
from pathlib import Path

import fitz  # pymupdf
import pdfplumber
import pandas as pd
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TEST_DIR = ROOT / "research" / "test_pdfs"
RESULTS_DIR = ROOT / "research" / "results" / "by_pdf"
REPORT_PATH = ROOT / "research" / "report.html"

# ---------------------------------------------------------------------------
# Pull live config from source modules
# ---------------------------------------------------------------------------
from shared import aviation_rules
from sheet_types import occm
from sheet_types.occm_variants import aeroflot, amos, china_eastern

VARIANTS = [aeroflot, amos, china_eastern]


# ---------------------------------------------------------------------------
# Per-PDF inspection helpers
# ---------------------------------------------------------------------------
def page_classifications(doc: fitz.Document) -> tuple[int, int, int]:
    text = mixed = scanned = 0
    for p in doc:
        n = len(p.get_text())
        if n > 1000: text += 1
        elif n > 200: mixed += 1
        else: scanned += 1
    return text, mixed, scanned


def page1_image_b64(doc: fitz.Document, dpi: int = 90) -> str:
    pix = doc[0].get_pixmap(dpi=dpi)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=70)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def first_text_page_dump(doc: fitz.Document, limit: int = 1500) -> tuple[int, str]:
    for i, p in enumerate(doc):
        t = p.get_text()
        if len(t) > 200:
            return i + 1, t[:limit]
    return 0, ""


def pdfplumber_first_table(pdf_path: Path):
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page in pdf.pages:
                tabs = page.extract_tables()
                if tabs:
                    return page.page_number, tabs[0][:8]
    except Exception as e:
        return -1, [["error", str(e)]]
    return 0, None


def extraction_summary(pdf_name: str) -> dict | None:
    stem = Path(pdf_name).stem
    for suffix, level in [("_L1.csv", "L1"), ("_L3.csv", "L3")]:
        csv_path = RESULTS_DIR / f"{stem}{suffix}"
        if csv_path.exists():
            df = pd.read_csv(csv_path).fillna("")
            issues = df["_issues"].astype(str) if "_issues" in df.columns else pd.Series([""] * len(df))
            clean = (issues == "").sum()
            imputed = issues.str.contains("_imputed:ATA", na=False).sum()
            return {"path": csv_path, "rows": len(df), "clean": int(clean),
                    "imputed_ata": int(imputed), "df": df, "level": level}
    return None


def debug_images_for(pdf_name: str) -> list[Path]:
    debug_dir = RESULTS_DIR / f"{Path(pdf_name).stem}_debug"
    if not debug_dir.exists():
        return []
    return sorted(debug_dir.glob("*.png"))


# ---------------------------------------------------------------------------
# HTML helpers
# ---------------------------------------------------------------------------
def variant_tag(name: str) -> str:
    cls = {"AMOS": "tag-amos", "Aeroflot": "tag-aero",
           "China Eastern": "tag-ce", "Vietnam Airlines": "tag-vie",
           "Unknown": "tag-unk"}.get(name, "tag-unk")
    return f'<span class="tag {cls}">{html.escape(name)}</span>'


def layer_tag(text_p: int, mixed_p: int, scan_p: int, total: int) -> str:
    if text_p >= total * 0.7:
        return '<span class="tag tag-text">text</span>'
    if text_p + mixed_p >= total * 0.5:
        return '<span class="tag tag-mixed">mixed</span>'
    return '<span class="tag tag-scan">scanned</span>'


def render_dataframe(df: pd.DataFrame, table_id: str, max_initial: int | None = None) -> str:
    """Render a pandas DataFrame as a filterable HTML table.

    The rendered table includes data attributes so the page-level JS can:
    - filter rows by 'flagged only' toggle
    - search rows by substring across all cells
    """
    if df.empty:
        return "<p><em>(empty)</em></p>"
    cols = list(df.columns)
    rows_html = []
    rows = df if max_initial is None else df.head(max_initial)
    for _, row in rows.iterrows():
        flagged = bool(str(row.get("_issues", "")))
        cls = "flagged" if flagged else ""
        cells = []
        for c in cols:
            v = row[c]
            v = "" if pd.isna(v) else str(v)
            css = "issues" if c == "_issues" else ""
            cells.append(f'<td class="{css}">{html.escape(v)}</td>')
        rows_html.append(f'<tr class="{cls}" data-flagged="{int(flagged)}">{"".join(cells)}</tr>')

    head = "".join(f"<th>{html.escape(c)}</th>" for c in cols)
    return (
        f'<div class="table-controls">'
        f'<input type="text" class="search-box" placeholder="Filter rows…" '
        f'oninput="filterTable(\'{table_id}\', this.value)">'
        f'<label><input type="checkbox" onchange="toggleFlagged(\'{table_id}\', this.checked)"> '
        f'Flagged only</label>'
        f'<span class="row-count" id="{table_id}-count">{len(rows)} rows shown</span>'
        f'</div>'
        f'<div class="table-scroll">'
        f'<table id="{table_id}" class="data"><thead><tr>{head}</tr></thead><tbody>{"".join(rows_html)}</tbody></table>'
        f'</div>'
    )


def render_bar_chart(items: list[tuple[str, int]], label: str = "count") -> str:
    """Inline horizontal bar chart using flexbox + CSS widths."""
    if not items:
        return "<p><em>(no data)</em></p>"
    top = max(v for _, v in items)
    rows = []
    for k, v in items:
        pct = int(100 * v / top) if top else 0
        rows.append(
            f'<div class="bar-row">'
            f'<span class="bar-label">{html.escape(str(k))}</span>'
            f'<span class="bar-track"><span class="bar-fill" style="width:{pct}%"></span></span>'
            f'<span class="bar-value">{v}</span>'
            f'</div>'
        )
    return f'<div class="bar-chart">{"".join(rows)}</div>'


def render_rules_table(rules: dict) -> str:
    """Render a per-column rules dict as an HTML table."""
    out = ['<table class="rules"><tr><th>column</th><th>rule</th></tr>']
    for col, r in rules.items():
        if not r:
            cell = '<em>(no rule)</em>'
        else:
            parts = []
            for k, v in r.items():
                if k == "char_map":
                    pieces = ", ".join(f"<code>{html.escape(repr(a))}→{html.escape(repr(b))}</code>"
                                       for a, b in v.items())
                    parts.append(f"char_map: {pieces}")
                else:
                    parts.append(f"<code>{html.escape(k)}</code>: <code>{html.escape(str(v))}</code>")
            cell = "<br>".join(parts)
        out.append(f'<tr><td><strong>{html.escape(col)}</strong></td><td>{cell}</td></tr>')
    out.append("</table>")
    return "".join(out)


# ---------------------------------------------------------------------------
# CSS / JS / HEAD
# ---------------------------------------------------------------------------
HEAD_TEMPLATE = r"""<!doctype html>
<html><head><meta charset='utf-8'><title>Cypher research report</title>
<style>
:root {
  --fg: #1a1a1a; --muted: #666; --accent: #2c5282; --bg: #fafafa;
  --border: #ddd; --flag: #fff5e6; --code-bg: #f4f6fa;
}
* { box-sizing: border-box; }
body {
  font-family: system-ui, -apple-system, sans-serif;
  max-width: 1200px; margin: 1.5rem auto; padding: 0 1rem;
  color: var(--fg); background: var(--bg); line-height: 1.45;
}
h1 { margin: 0 0 0.5rem; font-size: 1.7rem; }
h2 { border-bottom: 2px solid var(--accent); padding-bottom: 0.25rem;
     margin-top: 2.5rem; padding-top: 1rem; }
h3 { color: var(--accent); margin-top: 1.4rem; }
h4 { color: #444; margin-top: 1rem; margin-bottom: 0.4rem; }
code { background: var(--code-bg); padding: 0 0.25rem; border-radius: 3px;
       font-size: 0.85em; }
pre { background: white; border: 1px solid var(--border); padding: 0.7rem;
      border-radius: 4px; overflow: auto; font-size: 0.78rem;
      white-space: pre-wrap; max-height: 320px; }
.tagline { color: var(--muted); margin: 0 0 1.5rem; font-size: 0.95rem; }

/* Table of contents */
nav.toc { background: white; border: 1px solid var(--border); padding: 0.75rem 1rem;
          border-radius: 6px; margin-bottom: 1.5rem; }
nav.toc ol { margin: 0.25rem 0 0 1.25rem; padding: 0; }
nav.toc a { color: var(--accent); text-decoration: none; }
nav.toc a:hover { text-decoration: underline; }

/* Scoreboard / generic tables */
table.scoreboard, table.rules, table.df {
  border-collapse: collapse; background: white; font-size: 0.88rem; width: 100%;
}
table.scoreboard th, table.scoreboard td,
table.rules th, table.rules td,
table.df th, table.df td {
  border: 1px solid var(--border); padding: 0.4rem 0.6rem; text-align: left;
  vertical-align: top;
}
table.scoreboard th, table.rules th, table.df th { background: #eef2f7; }

/* Data tables (per-PDF) — filterable, scrollable */
.table-controls { margin: 0.5rem 0; display: flex; gap: 1rem; align-items: center;
                  flex-wrap: wrap; }
.search-box { padding: 0.3rem 0.5rem; border: 1px solid var(--border);
              border-radius: 3px; min-width: 240px; }
.row-count { color: var(--muted); font-size: 0.85rem; }
.table-scroll { max-height: 600px; overflow: auto; border: 1px solid var(--border);
                background: white; }
table.data { border-collapse: collapse; font-size: 0.78rem; width: 100%; }
table.data th, table.data td {
  border: 1px solid var(--border); padding: 0.2rem 0.4rem; vertical-align: top;
}
table.data th { background: #eef2f7; position: sticky; top: 0; z-index: 1; }
table.data tr.flagged { background: var(--flag); }
table.data td.issues { color: #b45309; font-size: 0.74rem; max-width: 280px;
                       white-space: normal; }

/* Tags */
.tag { display: inline-block; padding: 0.1rem 0.5rem; border-radius: 3px;
       font-size: 0.78rem; font-weight: 600; }
.tag-text { background: #d4edda; color: #155724; }
.tag-mixed { background: #fff3cd; color: #856404; }
.tag-scan { background: #f8d7da; color: #721c24; }
.tag-amos { background: #cce5ff; color: #004085; }
.tag-aero { background: #e2d4f8; color: #491f7d; }
.tag-ce   { background: #ffd6d6; color: #7d1f1f; }
.tag-vie  { background: #fff3cd; color: #856404; }
.tag-unk  { background: #e9ecef; color: #495057; }
/* sheet-type tags */
.tag-st-occm { background: #e1ecf4; color: #1e4f88; }
.tag-st-ht   { background: #ffe8e8; color: #8a3939; }
.tag-st-llp  { background: #e6f4ea; color: #2c7a4d; }
.tag-st-unknown { background: #e9ecef; color: #495057; }

/* Bar charts */
.bar-chart { background: white; border: 1px solid var(--border);
             border-radius: 4px; padding: 0.6rem 0.8rem; }
.bar-row { display: flex; align-items: center; gap: 0.6rem; margin: 0.25rem 0; font-size: 0.85rem; }
.bar-label { flex: 0 0 280px; color: #333; word-break: break-word; }
.bar-track { flex: 1; height: 14px; background: #eef2f7; border-radius: 2px;
             overflow: hidden; }
.bar-fill { display: block; height: 100%; background: var(--accent); }
.bar-value { flex: 0 0 60px; text-align: right; color: var(--muted); font-variant-numeric: tabular-nums; }

/* Per-PDF metadata */
.meta { background: white; padding: 0.5rem 1rem; border: 1px solid var(--border);
        border-radius: 6px; margin-bottom: 0.75rem; font-size: 0.9rem; }
.meta dt { font-weight: 600; display: inline-block; width: 150px; }
.meta dd { display: inline; margin: 0; }
.meta dd::after { content: ""; display: block; }

/* Images */
img.preview { max-width: 240px; border: 1px solid var(--border);
              vertical-align: top; margin-bottom: 0.5rem; }
img.debug   { max-width: 100%; border: 1px solid var(--border); margin: 0.5rem 0; }

/* Architecture flow */
.flow { background: white; border: 1px solid var(--border); padding: 1rem;
        border-radius: 6px; font-family: ui-monospace, monospace; font-size: 0.85rem;
        white-space: pre; overflow-x: auto; }

/* Variant card */
.variant-card { background: white; border: 1px solid var(--border);
                border-left: 4px solid var(--accent); padding: 0.8rem 1rem;
                border-radius: 4px; margin-bottom: 1rem; }
.variant-card h4 { margin-top: 0; }

footer { margin-top: 2.5rem; padding-top: 1rem; border-top: 1px solid var(--border);
         color: var(--muted); font-size: 0.85rem; }
</style>
<script>
function filterTable(tableId, query) {
  const table = document.getElementById(tableId);
  if (!table) return;
  const rows = table.tBodies[0].rows;
  const q = query.toLowerCase();
  let shown = 0;
  for (const row of rows) {
    const flaggedOnly = table.dataset.flaggedOnly === "1";
    const flagged = row.dataset.flagged === "1";
    const text = row.textContent.toLowerCase();
    const matchesText = !q || text.includes(q);
    const matchesFlag = !flaggedOnly || flagged;
    const visible = matchesText && matchesFlag;
    row.style.display = visible ? "" : "none";
    if (visible) shown++;
  }
  const counter = document.getElementById(tableId + "-count");
  if (counter) counter.textContent = shown + " rows shown";
}
function toggleFlagged(tableId, on) {
  const table = document.getElementById(tableId);
  if (!table) return;
  table.dataset.flaggedOnly = on ? "1" : "0";
  const search = table.parentElement.parentElement.querySelector(".search-box");
  filterTable(tableId, search ? search.value : "");
}
</script>
</head><body>
"""


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------
def section_user_guide() -> str:
    return """
<h2 id='guide'>0. User guide</h2>

<div class='guide'>

<h3>What this report shows</h3>
<p>Every section below is auto-generated from the source code and the
test corpus in <code>research/test_pdfs/</code>. The rules, signatures,
detection logic, and extracted data are <strong>live</strong> — re-run the
build and the report reflects whatever's in the codebase right now.</p>

<h3>Stress-test workflow</h3>
<p>To process more OCCMs and watch the system handle each one:</p>
<ol>
  <li>Drop a new PDF into <code>research/test_pdfs/</code>.</li>
  <li>Run extraction — either in <code>research/workbook.ipynb</code>
      (Run All) or via a one-liner from the terminal:
      <pre style='font-size:0.78rem'>cd cypher
.venv/bin/python -c "
import sys, pathlib, pandas as pd, fitz
sys.path.insert(0, str(pathlib.Path.cwd()))
from sheet_types import occm
from shared.journey import record_run

pdf = 'research/test_pdfs/&lt;NEW_FILE&gt;.pdf'
variant = occm.detect_variant(pdf)
result = occm.extract(pdf, variant_name=variant)
cleaned = occm.normalize_and_validate(result['records'], variant_name=variant)
df = pd.DataFrame(cleaned)
df.to_csv(f'research/results/by_pdf/{pathlib.Path(pdf).stem}_L1.csv', index=False)
df.to_excel(f'research/results/by_pdf/{pathlib.Path(pdf).stem}_L1.xlsx', index=False)
record_run(pdf, variant, df, len(fitz.open(pdf)), notes='stress test')
print(f'{variant}: {len(df)} rows')
"</pre>
  </li>
  <li><code>msn_journey.csv</code> gets a new row automatically.</li>
  <li>Rebuild the dashboard:
      <pre style='font-size:0.78rem'>.venv/bin/python research/report_builder.py</pre></li>
  <li>Open this report &rarr; <a href='#journey'>MSN journey tracker</a>
      shows where each MSN went.</li>
  <li>For PDFs with missing-page lists: open
      <code>research/colab_L4_paddleocr.ipynb</code> in Colab, upload the
      PDF, run L4 only on the missing pages, drop the resulting CSV into
      <code>research/results/by_pdf/</code>, then re-run the report
      (step 4).</li>
</ol>

<h3>Things to try without adding more documents</h3>
<ul>
  <li><strong>Run the analyst notebook</strong>:
      <code>research/workbook.ipynb</code>. Same data as this report but
      in pandas, with live filtering, cross-corpus search, and an
      &ldquo;eyeball flagged rows&rdquo; cell. Pick the cypher
      <code>.venv</code> kernel.</li>
  <li><strong>Test the deploy locally</strong>:
      <code>cd cypher/deploy &amp;&amp; ../.venv/bin/python -m http.server
      8765</code>, then open <code>http://localhost:8765</code>. Drop in
      <code>msn2212OCCM.pdf</code> or <code>msn2517OCCM.pdf</code> &mdash;
      the page should auto-detect the variant and extract.</li>
  <li><strong>Open an XLSX in Excel</strong>:
      <code>research/results/by_pdf/&lt;file&gt;_L1.xlsx</code>. Sort by
      <code>_issues</code> to put flagged rows at the top; that's the
      analyst-eyeball list.</li>
  <li><strong>Try L4 on the 11 scanned pages of msn2212</strong>: open
      <code>research/colab_L4_paddleocr.ipynb</code> in Colab, set
      <code>PAGES=[1,4,5,6,10,12,13,14,16,20,21,22,23,24]</code>, and
      see what PaddleOCR recovers. Even partial success increases the
      msn2212 row count.</li>
  <li><strong>Inspect the bbox debug overlays</strong>: scroll to the
      <code>afl_test.pdf</code> section below — the colour-by-column
      images show exactly which words got assigned to which column.
      Useful when tuning OCR.</li>
  <li><strong>Read the rules</strong>: section 2 below renders every
      <code>aviation_rules.py</code> entry, every per-variant rule
      override, and the OCR character map with rationale.</li>
</ul>

<h3>Tips for using this report</h3>
<ul>
  <li>Per-PDF result tables have a <strong>filter box</strong> (substring
      search across all cells) and a <strong>&ldquo;Flagged only&rdquo;
      checkbox</strong>. Both update the row counter live.</li>
  <li>Column headers stay sticky as you scroll long tables.</li>
  <li>This report is <strong>fully self-contained</strong> &mdash;
      images are base64-embedded, JS/CSS inline. Email it, copy it, drop
      it on a USB stick. Works offline.</li>
</ul>
</div>
"""


def section_scoreboard(per_pdf: list[dict]) -> str:
    out = ["<h2 id='scoreboard'>1. Scoreboard</h2>",
           "<table class='scoreboard'>",
           "<tr><th>File</th><th>Pages</th><th>Layer</th><th>Variant</th>",
           "<th>Level</th><th>Rows</th><th>Clean</th><th>Imputed ATA</th></tr>"]
    for d in per_pdf:
        ext = d["ext"]
        if ext:
            level = ext["level"]
            rows_n = ext["rows"]
            clean_pct = round(100 * ext["clean"] / ext["rows"], 1) if ext["rows"] else 0
            clean_str = f"{ext['clean']}/{ext['rows']} ({clean_pct}%)"
            imp = ext["imputed_ata"]
        else:
            level, rows_n, clean_str, imp = "—", "—", "—", "—"
        out.append(f"<tr><td>{html.escape(d['name'])}</td>"
                   f"<td>{d['pages']}</td>"
                   f"<td>{layer_tag(*d['layer_split'], total=d['pages'])}</td>"
                   f"<td>{variant_tag(d['variant'])}</td>"
                   f"<td>{level}</td><td>{rows_n}</td><td>{clean_str}</td><td>{imp}</td></tr>")
    out.append("</table>")
    return "".join(out)


def section_config_and_rules() -> str:
    out = ["<h2 id='rules'>2. Configuration and rules</h2>"]

    # --- Resolution levels ---
    out.append("<h3>Resolution levels</h3>")
    out.append("<table class='rules'>"
               "<tr><th>Level</th><th>Strategy</th><th>Library</th><th>Status</th><th>When to use</th></tr>"
               "<tr><td><strong>L1</strong></td><td>Text-layer line parsing</td>"
               "<td><code>pdfplumber</code></td>"
               "<td>✅ implemented</td>"
               "<td>PDFs with a real text layer; rows anchor on date / ATA</td></tr>"
               "<tr><td><strong>L2</strong></td><td>Layout-aware extraction</td>"
               "<td><code>pdfplumber</code> word boxes / <code>pymupdf</code></td>"
               "<td>⏳ reserved</td>"
               "<td>Text-layer PDFs where rows split across lines or pdfplumber's auto-detection fails</td></tr>"
               "<tr><td><strong>L3</strong></td><td>OCR fallback</td>"
               "<td>Tesseract (PSM 12 + bbox clustering)</td>"
               "<td>✅ implemented (local) / Tesseract.js TODO (browser)</td>"
               "<td>No text layer; or text layer is CID-encoded / corrupt</td></tr>"
               "<tr><td><strong>L4</strong></td><td>Alternative OCR (heavier)</td>"
               "<td>PaddleOCR PP-Structure / EasyOCR</td>"
               "<td>🔬 Colab notebook (<code>research/colab_L4_paddleocr.ipynb</code>)</td>"
               "<td>Last resort: bordered tables, low-DPI scans, Asian-carrier sources where Tesseract garbles dates</td></tr>"
               "</table>")

    # --- OCR character map ---
    out.append("<h3>OCR character map</h3>")
    out.append("<p>Applied to fields with <code>char_map</code> in their rule "
               "(FIN, VENDOR_CODE, PART_NUMBER, SERIAL_NUMBER and any variant-specific code fields).</p>")
    out.append("<table class='rules'><tr><th>OCR sees</th><th>Map to</th><th>Reason</th></tr>")
    reasons = {
        "O": "PNs and codes never contain the letter O",
        "o": "Lowercase variant of O",
        "l": "PNs never contain lowercase l",
        "I": "PNs never contain capital I in PN context",
        "|": "Pipe characters are OCR border artifacts",
        "$": "PNs never contain $; OCR misreads S→$",
        "£": "OCR misreads E→£ in some fonts/scans",
        "€": "Same root cause as £",
    }
    for src, dst in aviation_rules.OCR_CHAR_MAP.items():
        out.append(f"<tr><td><code>{html.escape(repr(src))}</code></td>"
                   f"<td><code>{html.escape(repr(dst))}</code></td>"
                   f"<td>{reasons.get(src, '')}</td></tr>")
    out.append("</table>")
    out.append("<p><strong>Deferred:</strong> S/5 disambiguation. Empirically S "
               "tends to be the first character of a PN, while 5 occurs elsewhere. "
               "Encoding this requires a per-airframe PN reference list and is "
               "parked until an authoritative PN master list is wired in.</p>")

    # --- Global column rules ---
    out.append("<h3>Global per-column rules</h3>")
    out.append("<p>From <code>shared/aviation_rules.py:COLUMN_RULES</code>. "
               "These are the baseline aviation-domain conventions; per-variant "
               "overrides extend or replace them.</p>")
    out.append(render_rules_table(aviation_rules.COLUMN_RULES))

    # --- Variant-specific schemas ---
    out.append("<h3>Variant detection signatures and column schemas</h3>")
    out.append("<p>The OCCM router detects which variant a PDF is by looking for "
               "any of these substrings in the first 3 pages of text. When the PDF "
               "has no text layer at all, it falls back to <strong>Aeroflot</strong> "
               "(the only known no-text-layer variant).</p>")
    for v in VARIANTS:
        out.append(f"<div class='variant-card'>")
        out.append(f"<h4>{variant_tag(v.NAME)} <code>{v.__name__.split('.')[-1]}.py</code></h4>")
        out.append("<p><strong>Signatures:</strong> " + ", ".join(
            f"<code>{html.escape(s)}</code>" for s in v.SIGNATURES) + "</p>")
        out.append("<p><strong>Columns:</strong> " + " &middot; ".join(
            f"<code>{html.escape(c)}</code>" for c in v.CANONICAL_COLUMNS) + "</p>")
        # Show only rules that DIFFER from globals (i.e. variant-specific overrides)
        diff = {col: r for col, r in v.RULES.items()
                if col not in aviation_rules.COLUMN_RULES
                or r != aviation_rules.COLUMN_RULES.get(col)}
        if diff:
            out.append("<p><strong>Rule overrides / additions:</strong></p>")
            out.append(render_rules_table(diff))
        else:
            out.append("<p><em>No variant-specific overrides — uses global rules as-is.</em></p>")
        out.append("</div>")

    # --- ATA forward-fill ---
    out.append("<h3>Generic post-processing: ATA forward-fill</h3>")
    out.append("<p><code>shared/cleanup.py:forward_fill_ata</code> runs from "
               "<code>occm.normalize_and_validate</code> for any variant whose schema "
               "includes ATA. When ATA is empty on a row, it inherits the most recent "
               "<em>valid</em> value (a digit string in chapter range 20-83). "
               "Imputed rows are flagged with <code>_imputed:ATA</code> in <code>_issues</code> "
               "so analysts can distinguish source data from inferred data. "
               "Out-of-range or junk ATAs are not used as fill sources.</p>")

    return "".join(out)


def section_issue_analysis(per_pdf: list[dict]) -> str:
    out = ["<h2 id='issues'>3. Issue frequency analysis (cross-corpus)</h2>"]

    # Aggregate issue tuples (column, reason)
    by_col_reason = Counter()
    by_variant_col_reason = Counter()
    total_rows = 0
    total_flagged = 0
    for d in per_pdf:
        if not d["ext"]:
            continue
        df = d["ext"]["df"]
        if df.empty or "_issues" not in df.columns:
            continue
        total_rows += len(df)
        for s in df["_issues"].fillna("").astype(str):
            if not s:
                continue
            total_flagged += 1
            for bit in s.split(","):
                if not bit:
                    continue
                col, _, reason = bit.partition(":")
                by_col_reason[(col, reason)] += 1
                by_variant_col_reason[(d["variant"], col, reason)] += 1

    out.append(f"<p>Across <strong>{total_rows}</strong> total rows, "
               f"<strong>{total_flagged}</strong> are flagged "
               f"(<strong>{round(100*total_flagged/total_rows,1) if total_rows else 0}%</strong>).</p>")

    out.append("<h3>By (column, reason) — all variants combined</h3>")
    items = sorted(by_col_reason.items(), key=lambda kv: -kv[1])
    out.append(render_bar_chart([(f"{c}:{r}", n) for (c, r), n in items]))

    out.append("<h3>By variant — top issues per variant</h3>")
    by_variant = {}
    for (v, c, r), n in by_variant_col_reason.items():
        by_variant.setdefault(v, []).append((f"{c}:{r}", n))
    for v in sorted(by_variant.keys()):
        items = sorted(by_variant[v], key=lambda kv: -kv[1])
        out.append(f"<h4>{variant_tag(v)}</h4>")
        out.append(render_bar_chart(items))

    return "".join(out)


def section_per_pdf(per_pdf: list[dict]) -> str:
    out = ["<h2 id='per-pdf'>4. Per-PDF deep dive</h2>"]
    for d in per_pdf:
        anchor = re.sub(r"\W+", "_", d["name"]).lower()
        out.append(f"<h3 id='{anchor}'>{html.escape(d['name'])}</h3>")
        out.append("<dl class='meta'>")
        out.append(f"<dt>Size</dt><dd>{d['size_kb']:.1f} KB</dd>")
        out.append(f"<dt>Pages</dt><dd>{d['pages']}</dd>")
        tp, mp, sp = d["layer_split"]
        out.append(f"<dt>Page layer mix</dt><dd>{tp} text · {mp} mixed · {sp} scanned</dd>")
        out.append(f"<dt>Detected variant</dt><dd>{variant_tag(d['variant'])}</dd>")
        if d["ext"]:
            ext = d["ext"]
            out.append(f"<dt>Extraction</dt><dd>{ext['level']} · "
                       f"<strong>{ext['rows']}</strong> rows · "
                       f"<strong>{ext['clean']}</strong> clean · "
                       f"<strong>{ext['imputed_ata']}</strong> imputed ATA</dd>")
        out.append("</dl>")

        # Page 1 thumbnail
        try:
            b64 = page1_image_b64(d["doc"])
            out.append(f"<img class='preview' src='data:image/jpeg;base64,{b64}' alt='page 1 preview'>")
        except Exception as e:
            out.append(f"<p>Preview failed: {html.escape(str(e))}</p>")

        # Raw text dump
        page_n, dump = first_text_page_dump(d["doc"])
        if dump:
            out.append(f"<h4>Raw text-layer dump (page {page_n}, first 1500 chars)</h4>")
            out.append(f"<pre>{html.escape(dump)}</pre>")
        else:
            out.append("<h4>Raw text-layer dump</h4>"
                       "<p><em>No text layer detected — L3 OCR was required.</em></p>")

        # pdfplumber raw
        page_n, table = pdfplumber_first_table(Path(TEST_DIR) / d["name"])
        if table:
            out.append(f"<h4>pdfplumber baseline (page {page_n}, first 8 rows)</h4>")
            out.append("<table class='df'>")
            for r in table:
                out.append("<tr>" + "".join(
                    f"<td>{html.escape(((c or '')[:300]))}</td>" for c in r) + "</tr>")
            out.append("</table>")

        # Cypher extraction (full table, filterable)
        if d["ext"]:
            ext = d["ext"]
            csv_rel = ext["path"].relative_to(ROOT)
            xlsx_rel = csv_rel.with_suffix(".xlsx")
            out.append(f"<h4>Cypher extraction — full results ({d['variant']} variant, {ext['level']})</h4>")
            out.append(f"<p>CSV: <code>{html.escape(str(csv_rel))}</code> &middot; "
                       f"XLSX: <code>{html.escape(str(xlsx_rel))}</code></p>")
            table_id = f"tbl-{anchor}"
            out.append(render_dataframe(ext["df"], table_id=table_id))
        else:
            out.append("<h4>Cypher extraction</h4>"
                       "<p><em>No output — extractor returned 0 rows.</em></p>")

        # Per-PDF issue chart
        if d["ext"] and "_issues" in d["ext"]["df"].columns:
            cnt = Counter()
            for s in d["ext"]["df"]["_issues"].fillna("").astype(str):
                for bit in s.split(","):
                    if bit:
                        cnt[bit] += 1
            if cnt:
                out.append(f"<h4>Issue counts for this file</h4>")
                out.append(render_bar_chart(sorted(cnt.items(), key=lambda kv: -kv[1])))

        # Bbox debug overlays
        dbg = debug_images_for(d["name"])
        if dbg:
            out.append("<h4>Bounding-box debug overlays</h4>")
            out.append("<p>Each word coloured by which column the extractor assigned it to. "
                       "Look for misaligned colours at column boundaries — that's where to tune.</p>")
            for p in dbg:
                b64 = base64.b64encode(p.read_bytes()).decode("ascii")
                out.append(f'<img class="debug" src="data:image/png;base64,{b64}" alt="{p.name}">')

    return "".join(out)


def section_journey() -> str:
    """MSN journey table — read from research/results/msn_journey.csv."""
    from shared.journey import latest_per_pdf, history
    latest = latest_per_pdf()
    out = ["<h2 id='journey'>5. MSN journey tracker</h2>"]
    out.append("<p>For each PDF processed, where did its rows come from? "
               "L1 = text-layer parsing, L2 = layout-aware (reserved), "
               "L3 = Tesseract OCR, L4 = PaddleOCR (Colab fallback). "
               "Missing pages list pages where no row was extracted.</p>")
    if latest.empty:
        out.append("<p><em>No journey data yet — run the extraction pipeline to populate.</em></p>")
        return "".join(out)
    out.append("<table class='scoreboard'><tr>"
               "<th>PDF</th><th>Sheet type</th><th>Variant</th><th>Pages</th>"
               "<th>L1</th><th>L2</th><th>L3</th><th>L4</th>"
               "<th>Total</th><th>Clean</th><th>Pages w/ rows</th>"
               "<th>Missing pages</th><th>When</th><th>Notes</th></tr>")
    for _, r in latest.iterrows():
        miss = str(r["pages_missing"]) if pd.notna(r["pages_missing"]) else ""
        sheet_type = str(r.get("sheet_type", "")) if pd.notna(r.get("sheet_type", "")) else ""
        sheet_html = (f"<span class='tag tag-st-{sheet_type.lower()}'>{html.escape(sheet_type)}</span>"
                      if sheet_type else "")
        out.append(f"<tr>"
                   f"<td>{html.escape(str(r['pdf']))}</td>"
                   f"<td>{sheet_html}</td>"
                   f"<td>{variant_tag(str(r['variant']))}</td>"
                   f"<td>{r['total_pages']}</td>"
                   f"<td>{r['rows_l1']}</td>"
                   f"<td>{r['rows_l2']}</td>"
                   f"<td>{r['rows_l3']}</td>"
                   f"<td>{r['rows_l4']}</td>"
                   f"<td><strong>{r['rows_total']}</strong></td>"
                   f"<td>{r['rows_clean']} ({r['clean_pct']}%)</td>"
                   f"<td>{r['pages_with_rows']}/{r['total_pages']}</td>"
                   f"<td><code style='font-size:0.78rem'>{html.escape(miss[:80])}{'…' if len(miss)>80 else ''}</code></td>"
                   f"<td style='font-size:0.78rem'>{html.escape(str(r['timestamp']))}</td>"
                   f"<td>{html.escape(str(r['notes']) if pd.notna(r['notes']) else '')}</td>"
                   f"</tr>")
    out.append("</table>")

    # Full history if there's more than 1 row per pdf
    full = history()
    if len(full) > len(latest):
        out.append("<h3>Full history</h3>")
        out.append(f"<p>{len(full)} runs recorded across {len(latest)} PDFs.</p>")
        full_table_id = "journey-history"
        out.append(render_dataframe(full, table_id=full_table_id))
    return "".join(out)


def section_architecture() -> str:
    flow = """  PDF in
   │
   ▼
  occm.detect_variant(pdf_path)
   ├── reads first 3 pages of text via pdfplumber
   ├── matches variant SIGNATURES
   │     ├── "AEROFLOT", "Avionic Installed Units"     → Aeroflot
   │     ├── "AMOS", "swiss-as.com"                    → AMOS
   │     └── "CHINA EASTERN", "OCCM COMPONENTS …"      → China Eastern
   └── if no text layer at all                         → Aeroflot (default)
       │
       ▼
  variant.extract(pdf_path)   ─── per-page level escalation:
       │
       ├── L1  pdfplumber text-layer line parsing      ✓ implemented
       │       (regex-anchored on DATE / ATA / FH-FC)
       │
       ├── L2  pdfplumber word-coordinate clustering   ⏳ reserved
       │       (use when L1 mis-splits multi-line cells)
       │
       ├── L3  Tesseract OCR + bbox row clustering     ✓ implemented
       │       (PSM 12 + ATA-digit merging on bordered tables)
       │
       └── L4  PaddleOCR PP-Structure                  🔬 Colab notebook
               (research/colab_L4_paddleocr.ipynb;
                fringe-quality scans only)
       │
       ▼
  occm.normalize_and_validate(records, variant_name)
   ├── shared.cleanup.clean_record   sequence_map → char_map →
   │                                 strip pipes → no_spaces →
   │                                 uppercase → revert_I_in_pn_prefix →
   │                                 pattern check → range check
   └── shared.cleanup.forward_fill_ata    safety-net ATA imputation
       │
       ▼
  shared.journey.record_run    ─── append journey row per PDF
       │
       ▼
  records → CSV / XLSX / report HTML / Pyodide browser table"""
    return ("<h2 id='arch'>6. Architecture flow</h2>"
            "<p>How a PDF flows from input to validated records:</p>"
            f"<div class='flow'>{html.escape(flow)}</div>")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def build():
    pdfs = sorted(TEST_DIR.glob("*.pdf"))
    per_pdf = []
    for pdf in pdfs:
        doc = fitz.open(str(pdf))
        full_text = "".join(p.get_text() for p in doc[:3])
        variant = occm.detect_variant(str(pdf))
        tp, mp, sp = page_classifications(doc)
        ext = extraction_summary(pdf.name)
        per_pdf.append({
            "name": pdf.name,
            "size_kb": pdf.stat().st_size / 1024,
            "pages": len(doc),
            "layer_split": (tp, mp, sp),
            "variant": variant,
            "doc": doc,
            "ext": ext,
        })

    out = [HEAD_TEMPLATE,
           "<h1>Cypher research report</h1>",
           "<p class='tagline'>In-browser PDF table extractor for aviation maintenance documents. "
           "This report is auto-generated from the source code and the test corpus — "
           "every rule, signature, and result you see here is live.</p>"]

    pdf_links = []
    for d in per_pdf:
        anchor = re.sub(r"\W+", "_", d["name"]).lower()
        pdf_links.append(f"<li><a href='#{anchor}'>{html.escape(d['name'])}</a></li>")
    out.append("<nav class='toc'><strong>Contents</strong>"
               "<ol>"
               "<li><a href='#guide'>User guide</a></li>"
               "<li><a href='#scoreboard'>Scoreboard</a></li>"
               "<li><a href='#rules'>Configuration &amp; rules</a></li>"
               "<li><a href='#issues'>Issue frequency analysis</a></li>"
               "<li><a href='#per-pdf'>Per-PDF deep dive</a><ul>"
               + "".join(pdf_links)
               + "</ul></li>"
               "<li><a href='#journey'>MSN journey tracker</a></li>"
               "<li><a href='#arch'>Architecture flow</a></li>"
               "</ol></nav>")
    out.append(section_user_guide())

    out.append(section_scoreboard(per_pdf))
    out.append(section_config_and_rules())
    out.append(section_issue_analysis(per_pdf))
    out.append(section_per_pdf(per_pdf))
    out.append(section_journey())
    out.append(section_architecture())

    out.append(f"<footer>Generated by <code>research/report_builder.py</code>. "
               f"Self-contained: images embedded as base64, JS/CSS inline, no external dependencies. "
               f"Re-run after extraction changes to refresh.</footer>")
    out.append("</body></html>")

    REPORT_PATH.write_text("".join(out), encoding="utf-8")
    size_mb = REPORT_PATH.stat().st_size / 1024 / 1024
    print(f"Wrote {REPORT_PATH.relative_to(ROOT)}  ({size_mb:.2f} MB)")


if __name__ == "__main__":
    build()
