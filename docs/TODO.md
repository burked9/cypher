# Cypher — TODO

Open items in priority order. Each item has a category, a brief description, and a one-line "definition of done" so it's easy to pick up.

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

### L5 — non-OCR fallback layer
- **Why**: L3/L4 OCR has a documented ceiling (~0.4% recovery on the
  image-only HT corpus). A non-OCR alternative may close that gap for
  certain PDF classes. User to share specific approach.
- **Status**: placeholder — awaiting user notes on the proposed L5 strategy.
- **Done when**: at least one test PDF that L1–L4 cannot parse is parsed
  cleanly by L5, journey records `rows_l5`, and the report shows it
  alongside other levels.

## Priority 5 — distribution

### Publish on GitHub Pages
- **Status**: deferred until the corpus is broader (user preference).
- **When ready**: push the repo, **Settings → Pages → branch + folder `/deploy`**.
- **Discoverability minimization**: leave repo About / Topics / pinned-repos blank; do not tag releases; no PyPI / npm registration; `noindex, nofollow` already in deploy.

---

## Done since the last revision

- ✅ **Snapshot diffing tool** — `tools/snapshot_diff.py` and `diff_snapshots()` API. Smoke-tested on synthetic data (added / removed / changed / unchanged correctly partitioned, per-column deltas in the `_changes` cell).
- ✅ **Tesseract.js scaffold** — `deploy/assets/ocr_bridge.js`, index.html script tags, runtime-loaded Tesseract; full implementation deferred (see P2).
- ✅ **Open-source housekeeping** — `pyproject.toml` (with `Private :: Do Not Upload` safety classifier and ruff/mypy config), `SECURITY.md`, expanded `.gitignore` (test_pdfs, results, journey, report, bloom binary, dev artefacts).
- ✅ **`noindex, nofollow`** in `deploy/index.html`.
- ✅ **Marketing post** (`marketing/launch_post.md` + `launch_post_pelican.md`) — drop into Pelican site as `content/pages/cypher.md`.
- ✅ **Build automation cleanup** — `deploy/build.py` writes `deploy/_pymods/manifest.json`; `app.js` reads it. No more parallel-edit drift.
- ✅ **Bloom filter scaffold** — `shared/pn_master.py`, `tools/build_pn_master.py`, integration into `clean_record`. Soft-fails when no master is bundled.
- ✅ **Vietnam Airlines variants** for OCCM, HT, LLP — code paths exist and pass tests on 8 sample PDFs. Stress-testing across more VNA documents is corpus-dependent (see P1 "Test on more raw PDFs").

---

Last updated: 2026-05-08
