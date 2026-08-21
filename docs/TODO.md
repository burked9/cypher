# Cypher — TODO

Open items in priority order. Each item has a category, a brief description, and a one-line "definition of done" so it's easy to pick up.

## Priority 0 — pre-publication checklist

### Local end-to-end smoke test in a real browser
- **Why**: Pyodide-only failures (top-level imports of stdlib modules
  Pyodide doesn't ship, side-effects at module load) only surface in a
  real browser, not in CLI tests. Already caught one: `sqlite3` was a
  top-level import in `tools/build_positions_db.py` which broke the
  in-browser pair flow. Lazy-imported it inside `build()` — fix landed,
  but a fresh test confirms no other landmines.
- **Done when**: `cd deploy && python3 -m http.server 8765`, open
  localhost, exercise both single-PDF and combined modes end-to-end with
  no console errors. (Pyodide first-load ~10–15 MB; cached after.) ✅ DONE
  2026-08-21 — single-PDF mode: a real 30-page text OCCM file extracted
  1155 rows correctly (1044 clean, 111 flagged); a real scanned file
  (`afl_test.pdf`) correctly showed the no-text-layer warning in seconds
  instead of hanging. No console errors beyond the two known/expected ones
  (`pn_master.bloom` 404, a pre-existing docstring `SyntaxWarning`).

### Verify in-browser combined-mode UI works with real PDFs
- **Why**: Phase 3 was smoke-tested via simulated Pyodide path (Python
  CLI invoking the deploy modules). The real browser execution path is
  slightly different (web worker, micropip-installed pdfplumber, file
  system mounted by Pyodide.FS).
- **Done when**: dropping an OCCM PDF + HT PDF for a known cross-sheet
  airframe (MSN 223 is the cleanest test case — 100% HT overlap) gives
  pair status, slot view, and three downloadable CSVs. ✅ DONE
  2026-08-21 — dropped the real MSN 223 OCCM+HT pair into the actual
  browser: `Pair: registration_match (high) · aircraft_key: CS-TOJ`,
  109 joined slots, 1131 OCCM-only rows, 1641 total source rows, all
  three CSVs (Combined/OCCM/HT) rendered correctly. A prior run with a
  different (renamed) pair had reported `no_match` — turned out to be
  those specific files genuinely having neither a readable MSN nor
  registration in their header text, not a renaming artifact as first
  guessed. See the filename-preservation finding below, found while
  chasing that.

### Combined-mode pairing can't fall back to filename (found 2026-08-21)
- **Why**: `shared/pairing.py`'s `link_pair()` reads `p.name` for its
  filename-derived aircraft_key fallback, but `deploy/main.py`'s
  `_save_temp()` always writes to `tempfile.mkstemp(suffix=".pdf")` --
  a randomly-generated name, discarding whatever the user's browser
  upload was actually called before pairing.py ever sees the path. The
  filename fallback the code clearly supports is currently unreachable
  in the live browser flow, for any file, regardless of what it's
  named. Didn't matter for tonight's MSN 223 test (registration-header
  matching covered it), but a future file with weak header text and a
  meaningful filename would silently lose that fallback too.
- **Fix sketch**: pass `occmFile.name` / `htFile.name` from `app.js`
  through to `main.run_combined()`, and have `_save_temp` (or a
  filename-aware variant) write into a fresh `tempfile.mkdtemp()`
  subdirectory using the real name instead of a random one.
- **Done when**: a combined-mode pair with deliberately weak header
  text but a meaningful original filename (e.g. containing `MSN1234`)
  still pairs via the filename fallback.

### Add the live link on the consultancy site
- **Superseded plan**: this item originally proposed mounting Cypher
  under a subdirectory of the consultancy site itself (e.g.
  `/dev/cypher/`), which is why the compatibility notes below were
  about CSS bleed from a shared parent page. The actual decision
  (2026-08-21): a plain, generic GitHub Pages site — discoverability
  minimization was the priority, and a separate github.io origin also
  makes the CSS-bleed concern moot entirely (different origin, nothing
  shared) rather than something to defend against.
- **Status**: Cypher is live at `https://burked9.github.io/cypher/` —
  pushed, deployed via `.github/workflows/pages.yml`, smoke-tested.
  Still outstanding: you add the actual `<a href>` on
  `https://churchbayconsulting.com/pages/cypher.html` — that's a plain
  action item on your side, not a code change.
- **Old compatibility notes** (kept for reference, apply only if a real
  subdirectory-mount is ever revisited instead): all paths inside
  `deploy/` are relative, so it *can* be hosted at any sub-path with no
  `<base href>` rewrite; Pyodide/pdf.js/Tesseract.js load from jsdelivr
  with no auth; CSS class names are generic (`.action`, `.panel`,
  `.results-section-title`) and could bleed under a shared-origin
  mount with broad resets — not a concern for the separate-origin
  approach actually shipped.
- **Done when**: the link is live on the consultancy page.

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

### L6 (proposed) — Docling-to-Markdown + LLM extraction, as a fallback tier
- **Why**: user idea (2026-08-21) — when the deterministic PDF→Excel path
  fails outright (no variant matches, or L1–L5 all produce unusable
  output), route through **docling** for its PDF→Markdown conversion
  specifically (not its TableFormer structured-cell output, which is
  what the existing L5 item above targets) and hand that markdown to an
  LLM to do the actual row/column extraction. Markdown is a much better
  LLM input than raw OCR word-soup or a raw PDF — it preserves reading
  order and table-ish structure as plain text, which an LLM can parse
  far more reliably than either extreme (fully unstructured text or a
  fully-parsed-but-wrong structured guess).
- **What already exists that this would plug into**: `docs/llm_extraction_rules.md`
  is already a purpose-built instruction set for exactly this — "reference
  for an LLM agent extracting component-list rows... apply them and the
  output will line up with the Cypher pipeline's existing schema and
  validation." It currently has no defined *input* format for the LLM to
  read from; docling's markdown output is a strong candidate for that role.
- **Relationship to L5 above**: same tool (docling), different output mode.
  L5 asks "can docling's own table-structure detection (TableFormer) recover
  rows well enough to skip an LLM entirely?" L6 asks "when that (or
  everything else) fails, can markdown + an LLM using the existing rules
  doc recover rows well enough to be worth the LLM cost/latency?" Worth
  running L5's recon conclusion first — if TableFormer output is already
  good, L6 may not be needed at all.
- **Not yet done**: no prototype yet. Untried questions: does docling's
  markdown conversion preserve enough table structure on a genuinely
  hard aviation layout to be usable; what's the cost/latency of routing
  every deterministic-pipeline failure through an LLM call; does the
  output need a machine-checkable schema (JSON) rather than free-form
  markdown-in/CSV-out to fit the pipeline's validation step cleanly.
- **Done when**: a recon test (mirroring L5's approach — one sample PDF,
  docling markdown → LLM extraction using the existing rules doc →
  compare against a hand-checked source) shows whether this recovers
  enough rows to be worth building into the pipeline as a real fallback.

---

## Done since the last revision

- ✅ **Published on GitHub Pages** — live at
  `https://burked9.github.io/cypher/`, repo public at
  `github.com/burked9/cypher`. Discoverability minimization followed:
  repo Topics blank, no releases tagged, no PyPI/npm registration,
  `noindex, nofollow` already in `deploy/index.html`. Deployed via
  `.github/workflows/pages.yml` (GitHub Actions source, not the
  branch-based option — GitHub Pages' basic mode only supports the repo
  root or a folder literally named `/docs`, neither fits this repo's
  layout). One deliberate deviation from the original minimization
  plan: the repo description is set (`"Cypher technical datasheet PDF
  conversion"`) — user reviewed and is fine leaving it.
- ✅ **Scanned-PDF browser hang, fixed.** `pdfplumber`/`pdfminer.six` under
  Pyodide could take 2.5+ minutes with zero feedback determining a
  genuinely scanned PDF has no text (confirmed on files down to 89KB/1
  page, ruling out size; root cause in pdfminer/WASM never identified).
  Fix: `hasTextLayer()` in `ocr_bridge.js` checks via `pdf.js` (a separate
  codebase, no such issue) BEFORE ever handing bytes to Pyodide — both
  known-hanging files now resolve in under 600ms. Wired into single-PDF
  and combined-mode paths in `app.js`; fails open to the old path if the
  check itself throws. Also fixed along the way: none of `app.js`'s
  fetches for the mounted Python modules had cache-busting, so a
  returning visitor could silently keep running stale Python code after
  a future deploy — every mounted-file fetch now carries a per-page-load
  cache-busting param.
- ⚠️ **CORRECTION to the item above, same evening**: the "2.5+ minute
  hang" was almost certainly never real. Root-caused it properly this
  time — loaded an isolated Pyodide instance under direct control (not
  the page's own, and not relying on watching the UI) and replicated the
  *exact* original pre-fix code (`git show 16b40cf:...`) byte-for-byte:
  `detect_sheet_type()`'s blind OCCM default → `occm.detect_variant()`'s
  blind Aeroflot default, on the same file that supposedly hung. It
  completed in **17 milliseconds**. Every sub-step (`pdfplumber.open()`,
  `.chars`, `.extract_text()`) individually timed in the low
  milliseconds too. The actual bug: `showStatus()` writes results to
  `#summary`, a *different* element than the `#status` "Detecting
  variant…" line being watched — which never updates on the
  warning/error path. The original test almost certainly finished in
  milliseconds; the observation kept checking a frozen piece of text for
  2.5 minutes and concluded the app was stuck. `hasTextLayer()` and the
  cache-busting fixes above are still worth keeping (fast, harmless,
  fail-open, genuinely fine engineering) — but they were not fixing a
  real pdfminer/Pyodide performance bug, because there wasn't one. No
  outstanding "unidentified WASM landmine" risk remains from this.
- ✅ **`deploy/_pymods/` is no longer gitignored.** It was excluded as a
  "build artifact," which is right instinct for a pipeline WITH a build
  step and silently wrong for this one (plain static GitHub Pages, no CI):
  the entire 66-file Python mirror `app.js` fetches at runtime, including
  `manifest.json`, would never have reached a real push. Verified directly
  against the committed tree (`git ls-tree -r HEAD deploy/`) rather than
  the working directory — 73 tracked files under `deploy/`, matching every
  file actually on disk. Run `python3 deploy/build.py` and commit the
  result before every push from now on; nothing enforces that yet (see the
  CI item below).
- ✅ **occm.py's blind blank-text fallback, fixed at its actual root.**
  Turned out to be two stacked defaults, not one: `sheet_types/router.py`
  was defaulting *any* no-text-layer PDF to `"OCCM"` before variant
  detection even ran, then `occm.py` defaulted that to `"Aeroflot"`.
  Together they mislabeled a scanned LLP engine sheet as "OCCM · Aeroflot"
  this session. Both now use a non-blind `ocr_detect(pdf_path) -> bool`
  per variant, tried only when the text layer is empty — each variant
  confirms its own template via a cheap header OCR pass rather than any
  one being a guessed default. `aeroflot.py` gained this check, tested
  against the real `afl_test.pdf` sample. `deploy/main.py`'s "needs OCR"
  messaging is generalized the same way for both single-PDF and
  combined-mode paths — any blank-text upload gets one honest "looks
  scanned, no in-browser OCR yet" message instead of a guess. This is what
  surfaced the CRITICAL scanned-PDF-hang finding above (the real-browser
  test this fix required was the first time that path had ever been
  exercised end-to-end).
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
