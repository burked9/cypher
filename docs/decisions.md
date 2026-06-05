# Cypher — design & decisions log

A running log of architectural decisions, mappings, and trade-offs. Append a
dated section whenever a non-trivial choice is made or revised.

---

## Project scope and naming

Cypher is an in-browser tool for extracting tabular data from aviation
maintenance PDFs. Hosted as a static site on GitHub Pages, with Python running
client-side via Pyodide. PDFs never leave the browser.

The name is "Cypher" (with a Y, after the *Metal Gear Solid* character).
Repository folder: `work/cypher/`.

---

## Two orthogonal axes: resolution levels × document types

Cypher operates along two independent dimensions.

### Resolution levels — extraction strategies

Cypher uses a four-level extraction hierarchy. A document escalates per
page when a lower level fails to anchor:

| Level | Strategy | Library | Status | Best for |
|-------|----------|---------|--------|----------|
| L1 | Text-layer line parsing | `pdfplumber` | ✅ implemented | PDFs with text layer where rows anchor on date / ATA |
| L2 | Layout-aware extraction | `pdfplumber` word boxes / `pymupdf` | ⏳ reserved (implement when needed) | Text-layer PDFs where rows split across lines or pdfplumber's auto-detection fails |
| L3 | Tesseract OCR | `pytesseract` (PSM 12 + bbox clustering) | ✅ implemented locally; Tesseract.js TODO for browser | No text layer; or text layer is CID-encoded |
| L4 | Alternative OCR (heavier) | PaddleOCR `PP-Structure` (preferred) / EasyOCR | 🔬 Colab notebook only | Last resort: bordered tables, low-DPI scans, Asian-carrier sources where Tesseract garbles dates |

**L4 is intentionally Colab-first**: PaddleOCR pulls in PaddlePaddle and
~500 MB of model weights, which is too heavy for the static GitHub Pages
deploy. The deployed page links out to `research/colab_L4_paddleocr.ipynb`
where users run it on demand. Per-row provenance carries `_source: L4_paddle`
so analysts can filter / verify L4 output specifically.

The user-estimated split across their corpus is roughly L1 60% / L2 20% / L3 10%
(remainder needing manual review). The Pyodide deploy lets the user pick a
level explicitly per document; auto-escalation logic is deferred until ~20
benchmark documents have been processed.

### Document types (sheet types) — what the table means

| Type | Meaning | Status |
|------|---------|--------|
| OCCM | On Condition / Condition Monitored | **Primary focus** |
| HT | Hard Time | Stub — schema TBD |
| LLP | Life Limited Parts | Stub — schema TBD |

Only OCCMs are the primary scope. Adjacent inventory documents (Avionic
Inventory Listings, Aircraft Equipment List Reports) carry overlapping
information in less complete form — captured opportunistically as additional
variants under the OCCM umbrella, but explicitly *not* the priority.

---

## Document variants discovered so far

OCCM-class documents vary significantly between operators / MROs / airframe
manufacturers, because they're produced by different MIS (Maintenance
Information System) software. **A single hard-coded column schema will not
generalize.**

### Variant 1 — `Aeroflot` (Avionic Inventory Listing)

- File: `afl_test.pdf`
- Origin: Aeroflot Russian Airlines
- Document type: *not a true OCCM* — it's an "Inventory Listing of Avionic
  Installed Units" for one specific airframe (A320, MSN 003157)
- Storage: scanned PDF, no text layer (macOS Preview's Live Text creates
  the *appearance* of selectable text)
- Resolution required: **L3 (OCR)**
- Columns: `ATA / ZONE / FIN / DESCRIPTION / VENDOR_CODE / PART_NUMBER / SERIAL_NUMBER`
- Detection signature: header text contains "AEROFLOT" or
  "Avionic Installed Units"
- Validated baseline: 48/71 rows fully clean after rule application

### Variant 2 — `AMOS` (Aircraft Equipment List Report)

- File: `msn2517OCCM.pdf`
- Origin: AMOS / Swiss-AS MIS
- Document type: *not a true OCCM* — it's an "Aircraft Equipment List Report"
- Storage: full text layer on every page
- Resolution required: **L1 (text parsing)**
- Columns: `ATA / PART_NO / SERIAL_NO / DESCRIPTION / POS / RELEASE_NO_OR_LABEL_NO / INST_DATE / TSN / CSN`
- Note: `POS` is the FIN-equivalent; no separate ZONE or VENDOR_CODE columns
- Detection signature: text contains "AMOS", "swiss-as.com", or
  "produced by"

### Variant 3 — `China Eastern` (true OCCM)

- File: `msn2212OCCM.pdf`
- Origin: China Eastern Airlines
- Document type: **true OCCM** ("OCCM Components Status List")
- Storage: mixed — pages 2-3 have text layer, later pages may be scanned;
  letterhead has CID-encoded Chinese characters that don't decode cleanly
- Resolution required: **L1 with L3 fallback per page**
- Columns: `ATA / DESCRIPTION / FIN / PART_NUMBER / SERIAL_NUMBER / DATE / FH / FC`
- Detection signature: text contains "CHINA EASTERN" or
  "OCCM COMPONENTS STATUS LIST"

---

## Architecture: variant routing under sheet_types

Decision (2026-05-06): introduce a per-variant module structure.

```
sheet_types/
  __init__.py
  occm.py                      # ROUTER: detects variant, dispatches
  occm_variants/
    __init__.py
    _base.py                   # shared schema helpers
    aeroflot.py                # Aeroflot Avionic Inventory Listing
    amos.py                    # AMOS Aircraft Equipment List Report
    china_eastern.py           # China Eastern true OCCM
  ht.py                        # stub
  llp.py                       # stub
```

`occm.py` exposes a `detect_variant(pdf_path) -> str` function that reads
text from the first 2-3 pages and matches against per-variant signature
strings. The router then calls the chosen variant's `extract(pdf_path)`,
which handles both schema and (in some cases) layer choice (e.g. China
Eastern's mixed-page handling).

If detection fails, `_fallback_aeroflot_l3` is tried as a generic last resort.

### Why per-variant modules instead of a config file

Each variant has its own:
- column count, order, and names
- extraction strategy (line-chunking vs. column-projection vs. table-extraction)
- per-cell validation rules (some have dates, FH, CSN; others don't)
- letterhead/footer skip logic

Encoding all that as data would be more complex than just having one
focused Python file per variant. A future refactor could promote the *shared*
fields (validation rules, char maps) into config and keep the parsers in code.

---

## ATA forward-fill (generic post-processing)

OCCMs commonly print the ATA chapter once at the top of each section and
leave it implicit for subsequent rows in the same chapter. Each variant
parser handles this inline (e.g. AMOS's `current_ata` carry-forward), but
`shared/cleanup.py:forward_fill_ata` provides a generic safety-net post-step
that runs in `occm.normalize_and_validate` for any variant whose schema
includes ATA.

The fill rule: walk records in document order; whenever ATA is empty, copy
the most recently seen valid ATA value (one in the configured chapter range,
default 20-83). Rows whose ATA was filled this way receive an
`_imputed:ATA` flag in `_issues`, so the analyst can distinguish source data
from inferred data. Out-of-range ATAs keep their original `bad_format` flag
and are *not* used as the fill source.

Why both inline parser tracking *and* a post-step: when a parser misses an
ATA header (e.g. a future variant we haven't characterized yet, or a
corrupted source page), the post-step still imputes correctly. Defense in
depth.

---

## Soft validation principle

All cell validation is **soft**. Bad cells produce flags in an `_issues`
column and are still kept in the output. We never drop rows.

Rationale: when a new manufacturer's OCCM appears, we want the analyst to see
*everything* the extractor found — flagged where suspicious — rather than
silently dropping unrecognized rows. This is the right trade for an
analyst-facing tool whose users will eyeball the output anyway.

---

## OCR cleaning pipeline (extended)

Cells with `char_map` rules pass through this pipeline in order:

1. **`SEQUENCE_REPLACEMENTS`** — multi-character OCR fixes applied first so
   they aren't shadowed by single-char rules. Order matters; longer / more
   specific sequences come first.
2. **`OCR_CHAR_MAP`** — single-character substitutions.
3. **Strip pipes** — always (table-border artifacts).
4. **`no_spaces`** — collapse internal whitespace where forbidden.
5. **`uppercase`** — when configured.
6. **Field-specific reverts** — e.g. `revert_I_in_pn_prefix` on
   `PART_NUMBER`.
7. **Pattern validation** — regex check (soft; flags rather than rejects).
8. **Range check** — `int_range` on numeric fields.

### Sequence replacements

| Sequence | Maps to | Reason |
|----------|---------|--------|
| `-'` | `7` | OCR misread of "7" |
| `'-` | `7` | Reverse-order variant of the above |
| `°1` | `7` | Another "7" misread |
| `1°` | `7` | Reverse-order variant |
| `~~` | `-` | Doubled tilde collapses to single dash |
| `··` | `-` | Doubled interpunct collapses to single dash |

### Field-specific revert: `revert_I_in_pn_prefix`

PNs typically start with up to 3 capital letters followed by digits (e.g.
`SIC5059-13-10`, `B372BAM0511`). After the global char map runs, any `1`
sandwiched between letters in the first 4 characters is reverted to `I`.

This catches: `S1C5059` → `SIC5059`. It does *not* affect: `B372BAM0511`
(no letter neighbour after `B`), or `1209-100` (does not start with a
letter at all).

### `PART_NUMBER` pattern: no leading or trailing dash

`^[A-Z0-9](?:[A-Z0-9\-]*[A-Z0-9])?$` — must start AND end with an
alphanumeric character. Internal hyphens fine. Single-char PNs allowed.

### `SERIAL_NUMBER` pattern: slashes allowed

`^[A-Z0-9/](?:[A-Z0-9\-/]*[A-Z0-9/])?$` — SNs in the wild may contain
`/`, so it's part of the allowed character set.

---

## OCR character map (`shared/aviation_rules.py`)

For uppercase-alphanumeric fields (`FIN`, `VENDOR_CODE`, `PART_NUMBER`,
`SERIAL_NUMBER`), the following character substitutions are applied before
validation:

| OCR sees | Map to | Reason |
|----------|--------|--------|
| `O`, `o` | `0` | PNs and codes never contain the letter O |
| `l`, `I` | `1` | PNs and codes never contain lowercase l or capital I in PN context |
| `\|` | `""` | Pipe characters are OCR border artifacts |
| `$` | `S` | PNs never contain `$`; OCR misreads S→$ |
| `£` | `E` | OCR misreads E→£ in some fonts/scans |
| `€` | `E` | Same root cause as £ |

**Deferred — S/5 disambiguation**: empirically `S` tends to be the first
character of a PN, while `5` occurs elsewhere. Both are roughly equally
common overall. Encoding this requires a per-airframe PN reference list
and is parked until an authoritative PN master list is wired in (see below).

**Known side effect**: aggressive char-mapping on FIN can convert genuine OCR
"AIR" reads to "A1R" if Tesseract guessed wrong on a real FIN. Accepted
as the right trade — the cell is wrong either way and PN correctness is
the higher-stakes case.

---

## Per-column rules (`COLUMN_RULES` in `aviation_rules.py`)

The current rules are baseline aviation-domain conventions:

| Column | Pattern | Notes |
|--------|---------|-------|
| ATA | `^\d{2}$` | Range 20–83 enforced separately |
| ZONE | `^\d{2,3}$` | |
| FIN | `^[A-Z0-9]{2,8}$` | uppercase, no spaces |
| DESCRIPTION | (none) | uppercase only |
| VENDOR_CODE | `^[A-Z0-9]{4,5}$` | uppercase, no spaces |
| PART_NUMBER | `^[A-Z0-9\-]+$` | uppercase, no spaces |
| SERIAL_NUMBER | `^[A-Z0-9\-]+$` | uppercase, no spaces |

Per-variant overrides will live in the variant module (e.g. AMOS adds
`INST_DATE`, `TSN`, `CSN` rules). Rules are merged with the global
`COLUMN_RULES` at import time.

---

## Output formats

For every extraction:

1. `research/results/by_pdf/<pdf_stem>_L<n>.csv` — primary structured output
2. `research/results/by_pdf/<pdf_stem>_L<n>.xlsx` — same data as Excel
3. `research/results/by_pdf/<pdf_stem>_debug/page_*_debug.png` — bbox overlays
   for L3 runs (one PNG per page, words colored by assigned column)
4. `research/results/summary.csv` — append-only scoreboard across all runs
5. `research/report.html` — self-contained offline dashboard (regenerable)

The deployed app offers both CSV and XLSX downloads from a results panel.

---

## Stability rules (deploy)

For Pyodide-based deployment:

- Process **one page at a time** — never load whole doc into memory
- Page-range selector exposed in UI
- Progress indicator + cancel button
- L3 OCR uses Tesseract.js (JS/WASM), not pytesseract via Pyodide — too heavy
- Very large scanned PDFs (>50MB or >50 pages OCR) route to a Colab fallback
  link from the deployed page

---

## PN master cross-check (deferred)

Once a variant produces stable structured output, an additional validation
step will load an authoritative PN master list (any CSV/XLSX with a column of
known-good part numbers) and mark each `PART_NUMBER` as
`_pn_known: True/False`. Implementation parked until a master list is
provided and the schema is confirmed.

The integration is read-only and one-shot — the master list ships as a
static asset alongside the deployed site, not a live link.

---

## Date-keyed change log

### 2026-05-06

- Project initialized at `work/cypher/`
- Folder structure created: `research/`, `levels/{L1,L2,L3}/`, `sheet_types/`,
  `shared/`, `deploy/`, `docs/`
- L3 OCR pipeline implemented end-to-end against `afl_test.pdf` (Aeroflot
  variant); 48/71 rows clean after rule application
- L1 implemented for text-layer PDFs (`levels/L1_text/extract.py`)
- Per-cell soft validation with `_issues` column added
- OCR character map populated with O→0, l/I→1, |→"", $→S, £/€→E
- Bbox debug visualizer (`shared/debug_render.py`) — overlays colored boxes
  per assigned column
- Pyodide deploy scaffolded: `index.html`, `app.js`, `main.py`, `build.py`
  for mirroring Python modules into `deploy/_pymods/`
- Three OCCM variants identified (Aeroflot, AMOS, China Eastern) — variant
  router architecture chosen
- Self-contained HTML research report (`research/report.html`) generator
  written
- Variant router and three variant modules implemented:
  `aeroflot.py`, `amos.py`, `china_eastern.py` under `sheet_types/occm_variants/`
- China Eastern (`msn2212OCCM.pdf`) parser: 413/429 rows clean (96%) on first run
- AMOS (`msn2517OCCM.pdf`) parser: 1026/1265 rows clean (81%) after POS-anchor
  fix; ATA section-prefix stripping and date-anchor row reconstruction
- Generic ATA forward-fill helper added in `shared/cleanup.py`; runs from
  `normalize_and_validate` for any variant whose schema includes ATA
- Pyodide deploy completed end-to-end for L1 variants:
  - `deploy/main.py` calls `occm.detect_variant` and dispatches via the router
  - `deploy/build.py` mirrors 15 Python source files into `deploy/_pymods/`
  - `deploy/assets/app.js` loads Pyodide, installs pdfplumber via micropip,
    mounts modules, renders a filterable results table with CSV download
  - `occm._read_head_text` switched from pymupdf to pdfplumber to keep the
    in-browser dependency surface to a single PDF library
  - Aeroflot variant currently surfaces a warning in-browser because L3 OCR
    requires Tesseract.js (next step)
- Comprehensive HTML report generator (`research/report_builder.py`) rebuilt:
  TOC, scoreboard, live rules and per-variant cards, cross-corpus issue
  bar charts, full filterable per-PDF tables, architecture flow diagram,
  bbox debug overlays — all auto-generated from source so it can't drift
- OCR rule expansion based on real-world feedback:
  - Multi-character sequence replacements: `-'`/`'-`/`°1` → `7`,
    `~~`/`··` → `-`
  - Single-char additions: `~` → `-`, `·` → `-`, `°` → `-`, `'`/`` ` `` → ""
  - `PART_NUMBER` pattern updated: no leading or trailing `-`
  - `SERIAL_NUMBER` pattern updated: forward slashes allowed
  - `revert_I_in_pn_prefix` field rule: catches `S1C5059` → `SIC5059`
- China Eastern parser gained per-page L3 OCR fallback so mixed-source
  PDFs (text-layered + scanned pages in one document) extract from every
  page in a single pass; rows extracted via OCR are tagged `_source: ocr`
- Empirical finding on `msn2212OCCM.pdf`: 13 of 24 pages have a usable
  text layer and yield **423/429 rows clean (99%)**; the remaining 11
  pages are scanned at a quality where Tesseract (any PSM mode tested:
  4, 6, 11, 12, with bbox clustering and ATA-digit merging) cannot
  reliably reconstruct the 8-column row structure — date and PN fields
  are typically too garbled to anchor against. The OCR fallback
  infrastructure is in place but produces 0 reliable rows on this PDF's
  scanned pages. Future paths: rescan source at higher DPI, or run L4
  (PaddleOCR PP-Structure) via the Colab notebook for these specific pages.
- L4 (PaddleOCR) added as a Colab-first level for fringe-quality scans:
  - `levels/L4_alt_ocr/extract.py` stub maintains a uniform variant-parser
    interface; returns empty when paddleocr isn't installed locally.
  - `research/colab_L4_paddleocr.ipynb` is a runnable notebook: pip-installs
    paddleocr, accepts an uploaded PDF, runs PP-Structure on each page,
    emits a CSV/XLSX tagged `_source: L4_paddle` and `_page: N` for clean
    merging back into local results.
- MSN journey tracker (`shared/journey.py`) records per-PDF, per-level
  provenance into `research/results/msn_journey.csv`. Append-only so trends
  over time are preserved when stress-testing 50+ documents. The HTML report
  has a dedicated "MSN journey tracker" section showing latest run per PDF
  plus full history. Captures: total pages, pages with rows, per-level row
  counts, clean count and percentage, missing-page list, free-text notes.
