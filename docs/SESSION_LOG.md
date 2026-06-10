# Session log — Cypher OCCM+HT major version

One-page recap of what landed in the multi-day session that took Cypher
from "OCCM extraction only" to "OCCM + HT combined-mode with in-browser
UI and an L5 escalation path." Self-contained — a forked session or a
collaborator picking this up cold can read this and know exactly where
things stand.

## State on session start

* 26 OCCM variants, 1 HT variant (Vietnam Airlines only)
* `positions.sqlite` covered OCCM rows only
* No combined-mode tooling; downstream Sextant project had no defined
  input contract from Cypher

## State on session end

* **28 OCCM + 7 HT + 7 LLP variants** implemented
* Unified `positions.sqlite` (159k OCCM + 27k HT rows = 186k total)
  with a `sheet_type` column and the `cross_sheet_slot` SQL view
* **45 airframes have both OCCM and HT data joinable on `aircraft_key`**
* OCCM+HT combined-mode shipped Phase 0–3:
  - Phase 0 (HT parser coverage) — 4 waves, 110 HT files / 7 variants
  - Phase 1 — local CLI combiner (`tools/export_combined.py`)
  - Phase 2 — `shared.pairing.link_pair()` + two-PDF CLI mode
  - Phase 3 — in-browser combined-mode UI
* Global PN/SN leading-punctuation cleanup (651 → 0 affected rows)
* L5 escalation path scaffolded — `research/colab_L5_docling.ipynb`
  ready for recon on the 133 image-only HT PDFs

## Commits in chronological order

| Commit | What |
|---|---|
| `9e9702b` | Initial commit: Cypher in-browser PDF table extractor |
| `8153ba8` | Unify OCCM + HT into single positions.sqlite |
| `d3efa96` | MM_510 HT parser (Sun Express cluster, +18 files) |
| `b218246` | TODO: add Cypher OCCM+HT combined mode + L5 non-OCR placeholder |
| `9787a1c` | Wave 1 HT parser cluster expansion (+18 files) |
| `93d3086` | Wave 2 HT parser expansion: TAP sub-format fix + OASES Lifed Component Report |
| `d574d45` | Strip leading punctuation from PN/SN globally + STARS/Trax HT parser |
| `735821c` | Wave 4 HT parsers — Aircraft Rotables HT + EI-FFM signature widening |
| `9e8ab0c` | README + positions_schema.md refresh post-Wave-4 |
| `27b658b` | cross_sheet_slot SQL view + combined-mode preflight findings |
| `226f994` | Phase 1 — local CLI combiner (tools/export_combined.py) |
| `d9158e6` | Phase 2 — link_pair() pairing module + two-PDF CLI mode |
| `4e74d46` | Refresh partner HTML report + Phase 3 in-browser combined-mode UI |
| `bf88faf` | Fix in-browser Pairing failure: lazy-import sqlite3 + TODO updates |
| `03c18de` | L5 docling Colab notebook — recon scaffold for image-only PDFs |

## How the pieces fit

```
research/test_pdfs/      # corpus (gitignored)
sheet_types/             # per-variant parsers (OCCM/HT/LLP routers)
shared/                  # cleanup, rules, pairing (link_pair)
levels/                  # L1..L5 extraction strategies
tools/
  triage.py              # variant detection across a directory
  extract_file_metadata.py # header parse → MSN, reg, family
  build_positions_db.py  # merges by_pdf CSVs into positions.sqlite
  export_combined.py     # per-airframe OCCM+HT artefact (Phase 1)
deploy/                  # in-browser UI (Pyodide); index.html + main.py
research/results/
  positions.sqlite       # the unified DB
  combined/              # per-airframe combined artefacts (Phase 1 outputs)
  occm_index.html        # searchable index across 322 files
research/
  colab_L5_docling.ipynb # L5 escalation notebook
  session_summary.html   # partner-facing snapshot
```

## What's open

See `docs/TODO.md` for the full list. The headline open items:

1. **Local-browser smoke test** of the deploy after `bf88faf` (the
   sqlite3 fix and the top-level OCCM signature widening tonight).
2. **L5 docling recon** — run the Colab notebook on at least one of the
   five recommended image-only HT PDFs. Decision criteria are in the
   notebook itself.
3. **GitHub Pages integration** into the existing consultancy site
   (subdirectory mount, CSS-namespacing if drift appears).
4. **PN master cross-check** (long-pending — waiting on the PN file).

## Reproducibility

Every tool in this session is deterministic:

```bash
# Full rebuild from PDFs to DB
~/.venvs/cypher/bin/python tools/triage.py \
   --input /Users/danielburke/Library/CloudStorage/OneDrive-Personal/work/KEEL_aviation_records/evalsp \
   --hint-sheet-type OCCM
~/.venvs/cypher/bin/python tools/triage.py \
   --input /Users/danielburke/Library/CloudStorage/OneDrive-Personal/work/KEEL_aviation_records/ht \
   --hint-sheet-type HT \
   --out research/results/triage_ht.csv
~/.venvs/cypher/bin/python tools/extract_file_metadata.py
~/.venvs/cypher/bin/python tools/build_positions_db.py

# Export the 45 cross-sheet airframes
~/.venvs/cypher/bin/python tools/export_combined.py --all-cross-sheet

# Refresh the deploy mirror
~/.venvs/cypher/bin/python deploy/build.py

# Test deploy locally
cd deploy && python3 -m http.server 8765
```
