# Cypher — TODO

Open items in priority order. Each item has a category, a brief description, and a one-line "definition of done" so it's easy to pick up.

## Priority 0 — pre-publication checklist

### CRITICAL: scanned PDFs may hang the browser tab for minutes (or longer)
- **Why**: found while finally running the smoke test below. Dropped
  `research/test_pdfs/afl_test.pdf` (530KB, 2-page scanned Aeroflot OCCM, no
  text layer) into the real deployed page in an actual browser. It never
  completed — stuck on "Detecting variant and extracting…" past 2.5 minutes
  with zero progress and no console error. Isolated the variable with a
  side-by-side test: a similarly-sized (408KB) **text-layer** PDF completed
  in ~5-10s in a separate, equally-cold tab, ruling out "first Pyodide call
  is slow to import everything" as the explanation. This is specific to
  scanned/image-heavy PDFs under Pyodide, most likely `pdfplumber`/
  `pdfminer.six` pathologically slow (or stuck) parsing this file's content
  stream in WASM — confirmed the exact same file processes fine natively
  (`router.extract()` returned 71 records quickly outside the browser).
  **Not caused by this session's router.py/occm.py/deploy/main.py changes**
  — the original code hit the identical `pdfplumber.open()` +
  `extract_text()` call via a different function (`router.py`'s
  `_read_head_text`), so this would have hung just as badly before those
  edits. It simply had never been tested end-to-end in a real browser
  before now, which is exactly what this checklist item was for.
  Given aviation maintenance PDFs are frequently scans/photocopies, this is
  a likely-common case for a real visitor, not an edge case.
- **Not yet done**: root-cause *why* pdfminer chokes on this file under
  Pyodide specifically (xref recovery fallback? something about how the
  embedded image stream is structured?), and whether it's this file
  specifically or scanned PDFs generally.
- **Approach ideas, untried**: a page-count/file-size pre-check with a
  timeout-and-abort around the detection call, so the UI fails fast with a
  message instead of hanging silently; testing a few more scanned PDFs to
  see if it's universal or file-specific; profiling the pdfplumber call
  under Pyodide directly (`pyodide.runPythonAsync` with `time.time()`
  around just the `pdfplumber.open()` call, isolated from everything else).
- **Done when**: dropping a scanned PDF into the real deployed page either
  completes in a reasonable time or fails fast with a clear message —
  never hangs with no feedback.

### Local end-to-end smoke test in a real browser
- **Why**: Pyodide-only failures (top-level imports of stdlib modules
  Pyodide doesn't ship, side-effects at module load) only surface in a
  real browser, not in CLI tests. Already caught one: `sqlite3` was a
  top-level import in `tools/build_positions_db.py` which broke the
  in-browser pair flow. Lazy-imported it inside `build()` — fix landed,
  but a fresh test confirms no other landmines.
- **Done when**: `cd deploy && python3 -m http.server 8765`, open
  localhost, exercise both single-PDF and combined modes end-to-end with
  no console errors. (Pyodide first-load ~10–15 MB; cached after.)

### Verify in-browser combined-mode UI works with real PDFs
- **Why**: Phase 3 was smoke-tested via simulated Pyodide path (Python
  CLI invoking the deploy modules). The real browser execution path is
  slightly different (web worker, micropip-installed pdfplumber, file
  system mounted by Pyodide.FS).
- **Done when**: dropping an OCCM PDF + HT PDF for a known cross-sheet
  airframe (MSN 223 is the cleanest test case — 100% HT overlap) gives
  pair status, slot view, and three downloadable CSVs.

### GitHub Pages integration into existing consultancy site
- **Why**: User has an existing static GitHub Pages consultancy site
  and wants Cypher mounted under a subdirectory (e.g. `/dev/cypher/`).
- **Compatibility notes** (verified):
  * All paths inside `deploy/` are relative — Cypher can be hosted at
    any sub-path. No `<base href>` rewrite needed.
  * Pyodide + pdf.js + Tesseract.js load from jsdelivr CDN — no auth,
    no API key.
  * `noindex, nofollow` already in `deploy/index.html` head.
  * `deploy/` is self-contained — drop the whole folder under the
    target subdirectory.
  * **CSS class names are generic** (`.action`, `.panel`,
    `.results-section-title`). If the parent consultancy site uses
    broad CSS resets that bleed into the Cypher subdirectory, scope
    drift is possible. Fix is either (a) keep Cypher's `index.html`
    as the standalone page served from its own subdirectory, or (b)
    namespace Cypher's CSS under `.cypher-app { ... }` and wrap the
    `<body>` content in `<div class="cypher-app">`. Defer until we
    see actual drift.
- **Done when**: Cypher is reachable under the consultancy-site
  domain, both modes work, no styling drift from the parent site.

## Priority 1 — near-term, high impact

### Bloom-filter PN master cross-check
- **Why**: Quality-check `PART_NUMBER` against an authoritative master list without ever shipping the master list itself. Tunable false-positive rate; one-way encoding means publishing the filter is safe.
- **Status**: code scaffold in place (`tools/build_pn_master.py`, `shared/pn_master.py`, hook in `clean_record`). Awaiting the master CSV/XLSX.
- **Done when**: master CSV provided → `python tools/build_pn_master.py <csv>` produces `shared/pn_master.bloom` → every extracted row gains a `_pn_known` flag → analyst can filter in the report and on the deployed page.

### Test on more raw PDFs (corpus growth)
- **Why**: Stress-test variant detection and parsers across operators not yet seen.
- **Done when**: each new PDF is in `research/test_pdfs/`, journey-CSV has a row, and either ≥95% clean or there's a documented reason with a follow-up rule/variant entry below.

### Aircraft-type sub-variant axis
- **Why**: Some operators emit different formats per airframe family. Today the axis is `(sheet_type × operator)`; this proposes `(sheet_type × operator × airframe)`.
- **Done when**: at least one operator has two airframe-specific sub-variants and the router picks correctly.

## Priority 2 — quality and depth

### Improve Part M Engine Disk Sheet OCR accuracy
- **Why**: `sheet_types/llp_variants/part_m_engine_disk_sheet.py` (new — see
  "Done" below) is the first scanned/no-text-layer LLP variant. Confirmed
  against two real files (MSN29924 ESN888813 / ESN890419): row/column
  structure is 100% reliable (grid detection + `_cycles_sum_check`
  self-validation), but individual numeric cells still need spot-checking —
  common failure modes are a lone "0" cell misreading as junk, and
  occasional cross-column digit bleed on tightly-packed cells. The
  cycles-sum self-check catches nearly all of these (rows fail the check
  rather than silently passing), but that currently means *most* rows on
  both known files get flagged, not a minority.
- **Approach ideas, untried**: per-cell confidence scores from
  `pytesseract.image_to_data` to target retries only at low-confidence
  tokens; a second OCR pass with different preprocessing (e.g. adaptive
  threshold) voted against the first; widening the corpus past 2 files
  before tuning further, since it's easy to overfit thresholds to just these
  two.
- **Done when**: `_cycles_sum_check` reports "OK" on a clear majority of
  rows across a handful of different source files, not just structural
  correctness on the two known ones.

### Fix occm.py's blank-text fallback (found while building the above)
- **Why**: `sheet_types/occm.py:92-97` defaults `detect_variant()` to
  `"Aeroflot"` for *any* PDF with no text layer, with a comment noting this
  "will need revisiting when we encounter another scanned-only OCCM." We hit
  exactly that this session, except worse than anticipated: the blank-text
  PDF wasn't OCCM at all (it was an engine LLP sheet), so the tool
  confidently mislabeled it as "OCCM · Aeroflot" instead of saying
  "Unknown." `sheet_types/llp.py` now has a non-blind alternative — an
  optional `ocr_detect(pdf_path) -> bool` per variant, tried only when the
  text layer is empty, each variant confirming its own template via a cheap
  header OCR rather than any variant being a default guess.
- **Done when**: `occm.py` uses the same opt-in `ocr_detect` pattern (or
  equivalent) instead of a blind default, checked against how
  `deploy/main.py`/`app.js` trigger "needs OCR" messaging so the UX doesn't
  regress for genuine Aeroflot scans.

### Tesseract.js for in-browser L3
- **Status**: scaffold in place. `deploy/assets/ocr_bridge.js` wires up Tesseract.js + pdf.js; index.html loads them. Top-level entry `runOcrPipeline()` returns a clear "not finished" error so failures are visible, not silent.
- **Remaining work**: a Python entry-point `main.run_with_ocr(pages, sheet_type, variant)` that accepts pre-OCR'd word lists from JS, plus a small extractor refactor in `levels/L3_ocr/extract.py` so the column-projection logic can run on browser-supplied word boxes instead of always calling pytesseract locally. Roughly half a day's work.
- **Done when**: dropping `afl_test.pdf` into the deploy returns a populated table.

### More OCCM / HT / LLP variants as documents arrive
- **Why**: Each new operator typically needs one new module; that's how the system grows.
- **Approach**: per-operator follows the existing pattern in `sheet_types/<class>_variants/<operator>.py`.

### L2 (layout-aware) implementation
- **Why**: Reserved slot. Implement when we hit a text-layer PDF where rows split across lines and L1's regex can't anchor.

## Priority 3 — adjacent ingestion

### ARL / AIR / Excel sources (lowest priority)
- **Why**: Original manufacturer documents (Airworthiness Review List, Airworthiness Inspection Report) usually arrive as Excel rather than PDF.
- **Approach**: a separate `levels/L0_excel/` ingester. Variant modules can declare an Excel reader alongside the PDF parser. Soft-validation pipeline applies as-is.
- **Done when**: at least one ARL or AIR Excel file is parsed end-to-end, journey records `rows_l0`, and the report shows it alongside PDF results.

### Trend analysis across monthly snapshots
- **Why**: Once you have multiple monthly snapshots, plot how clean rates evolve, track LLP remaining-life burn-down per engine, etc.
- **Approach**: append-only journey already gives us the longitudinal substrate. Notebook cells for plotting.

## Priority 4 — engineering hygiene

### Lint + typecheck CI
- **Why**: Open-source project; small barrier-to-entry for contributors.
- **Approach**: a tiny GitHub Action — ruff + mypy on a small public function surface.
- **Status**: ruff/mypy configured in `pyproject.toml`; CI workflow not yet committed.

### ~~Move `.venv/` outside OneDrive~~ ✅ DONE
- Migrated to `~/.venvs/cypher`. Triage runs end-to-end in 3 min with zero timeouts. Old in-OneDrive `.venv/` deleted.

### Performance profile for 50+ docs
- **Why**: When the corpus grows we'll want to know where time is going.
- **Approach**: `python -m cProfile` over a 50-doc run; surface in `docs/`.

## Priority 1.5 — Cypher OCCM+HT (new combined mode)

### Combined OCCM + HT extraction mode
- **Why**: Sextant (the follow-up project — slot-level expected-PN advisory)
  consumes OCCM **and** HT data combined per airframe. Pre-joining the two
  sheets in Cypher means Sextant has one input contract instead of two, and
  every downstream consumer benefits from the same slot-level merge.
- **Shape**: same Cypher engine, new UI mode alongside OCCM / HT:
    `[ OCCM ]   [ HT ]   [ OCCM + HT (combined) ]`
  Combined mode takes two drop zones, auto-pairs on MSN → registration →
  user override, and produces three views:
    * long-form union (existing `positions.sqlite` shape)
    * slot-joined wide (one row per `(aircraft_key, position)`, OCCM + HT
      columns side-by-side)
    * Sextant ground-truth feed (slot + expected PN + actual PN + HT tasks)
- **Status**: unified `positions.sqlite` (sheet_type column, 45 cross-sheet
  airframes joinable today, `cross_sheet_slot` SQL view in place) plus
  Phase-1 local combiner shipped. Remaining work:
    * ✅ **Phase 0** — HT parser coverage (~110 files / 7 variants /
      ~27k rows across 4 waves; singletons + OCR deferred).
    * ✅ **Phase 1** — `tools/export_combined.py --aircraft <key>`
      writes a 3-sheet xlsx (Combined / OCCM / HT) plus a Sextant-
      shaped CSV sidecar. `--all-cross-sheet` emits all 45 airframes
      in one run.
    * **Phase 2** — `link_pair()` for the in-browser case (two PDFs in,
      one airframe out): MSN > registration > user override. 1 day.
    * **Phase 3** — in-browser combined-mode UI (dual drop zone, pairing
      confirmation, three-view download). 2–3 days.
    * **Phase 4** — Sextant integration spec + sample export.
      Sidecar CSV shape already defined in `tools/export_combined.py`'s
      `SEXTANT_COLS` — first concrete contract.
- **Position-semantic gotcha**: HT often uses coarser positions than OCCM
  (one HT task covers "all 4 brakes", OCCM lists 4 separate slots). Default
  to repeat-and-tag (each OCCM slot shows applicable HT obligations) with a
  `applies_to_all_in_ATA: <n>` flag for transparency.
- **Done when**: an analyst drops one OCCM PDF and one HT PDF, Cypher
  auto-pairs them, and the download contains the three views with the slot
  join behaving correctly across all 30 currently-joinable airframes.

### L5 — layout-aware document understanding (docling)
- **Why**: L3 Tesseract / L4 PaddleOCR have a documented ceiling on the
  ~133 image-only HT PDFs (~0.4% recovery). They give a flat OCR string;
  the per-variant line parsers can't recover row structure from that.
  **docling** (IBM Research, LF AI & Data, MIT) ships layout-analysis +
  TableFormer + integrated OCR — output is a `DoclingDocument` with
  per-table cells indexed by row/col with bounding boxes, exactly the
  structured intermediate Cypher's per-variant adapters need.
- **Architecture decision (user preference)**: main pipeline stays on
  Python 3.9 / Pyodide-friendly stack. L5 lives in a Colab notebook
  (cloud burst), mirroring the existing L4 PaddleOCR pattern. Heavy
  dependencies (PyTorch, transformers, layout models, TableFormer) all
  stay off the local install and the deploy.
- **Status**: Colab notebook landed at `research/colab_L5_docling.ipynb`.
  Recon experiment ready — point at one of the recommended image-only
  HT PDFs, run sections 1–6, and the notebook tells you whether
  docling's TableItem output is recoverable enough to power a generic
  L5 adapter.
- **Decision point after recon**:
  * **If recovery looks good** → wire L5 into `sheet_types/router.py`
    as a fallback when L1 returns 0 rows on an image-only PDF. Adapter
    module at `levels/L5_docling/extract.py` (local-only); deploy keeps
    its current "needs local L5" friendly stub for these cases.
  * **If recovery is poor on aviation layouts** → stop. Note the
    finding in docs/TODO.md and revisit when newer layout models ship.
- **Done when**: the recon notebook produces a `<stem>_l5_docling.csv`
  that, after a quick visual cross-check against the source PDF,
  contains ≥80% of the visible component rows for at least one of the
  five recommended sample files. (Reuse the notebook on more files if
  the first sample is borderline.)

## Priority 5 — distribution

### Publish on GitHub Pages
- **Status**: deferred until the corpus is broader (user preference).
- **When ready**: push the repo, **Settings → Pages → branch + folder `/deploy`**.
- **Discoverability minimization**: leave repo About / Topics / pinned-repos blank; do not tag releases; no PyPI / npm registration; `noindex, nofollow` already in deploy.

---

## Done since the last revision

- ✅ **`part_m_engine_disk_sheet.py`** — first scanned/no-text-layer LLP
  variant (Part M Aviation Ireland's engine LLP status sheet). Grid-detects
  the ruled table directly, OCRs full rows (not per-cell — per-cell crops
  of this layout were confirmed unreliable) and bucket-assigns words to
  columns by known x-position. Every row is self-checked
  (`CYCLES_R1..R4` sums to `TOTAL_CYCLES`) and flagged via
  `_cycles_sum_check` rather than trusted blind. See the new P2 item above
  for known accuracy gaps — this is a working v1, not a finished pipeline.
  Local-only (needs `pytesseract` + native Tesseract; `sheet_types/llp.py`
  imports it defensively so the Pyodide deploy is unaffected).
- ✅ **Manually-verified reference data** for both known Part M source files
  (`research/results/by_pdf/MSN29924_ESN{888813,890419}_llp_verified.csv`)
  — hand-transcribed and pixel-checked against the source scans, used as
  ground truth to build and test the variant above. Confirmed finding: the
  "-5C4" rating's REMAINING figure is never derivable from LIMIT−TOTAL on
  this sheet (checked on nearly every row with a numeric -5C4 limiter, both
  files) — Part M evidently tracks it against a different basis not shown
  here. Not a parse error; never re-derive it.
- ✅ **Snapshot diffing tool** — `tools/snapshot_diff.py` and `diff_snapshots()` API. Smoke-tested on synthetic data (added / removed / changed / unchanged correctly partitioned, per-column deltas in the `_changes` cell).
- ✅ **Tesseract.js scaffold** — `deploy/assets/ocr_bridge.js`, index.html script tags, runtime-loaded Tesseract; full implementation deferred (see P2).
- ✅ **Open-source housekeeping** — `pyproject.toml` (with `Private :: Do Not Upload` safety classifier and ruff/mypy config), `SECURITY.md`, expanded `.gitignore` (test_pdfs, results, journey, report, bloom binary, dev artefacts).
- ✅ **`noindex, nofollow`** in `deploy/index.html`.
- ✅ **Marketing post** (`marketing/launch_post.md` + `launch_post_pelican.md`) — drop into Pelican site as `content/pages/cypher.md`.
- ✅ **Build automation cleanup** — `deploy/build.py` writes `deploy/_pymods/manifest.json`; `app.js` reads it. No more parallel-edit drift.
- ✅ **Bloom filter scaffold** — `shared/pn_master.py`, `tools/build_pn_master.py`, integration into `clean_record`. Soft-fails when no master is bundled.
- ✅ **Vietnam Airlines variants** for OCCM, HT, LLP — code paths exist and pass tests on 8 sample PDFs. Stress-testing across more VNA documents is corpus-dependent (see P1 "Test on more raw PDFs").

---

Last updated: 2026-08-21
