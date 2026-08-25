# Cypher

In-browser PDF table extractor for aviation maintenance documents (OCCM and adjacent inventory listings such as Aircraft Equipment List Reports and Avionic Inventory Listings).

PDFs are processed entirely client-side via [Pyodide](https://pyodide.org/) — nothing is uploaded to a server. The deployed page is a single static site suitable for GitHub Pages.

## Why

Aircraft maintenance teams routinely receive lengthy PDFs listing installed components, part numbers, serial numbers, dates, and flight-hour / flight-cycle figures. The structure varies between operators and MIS software. Cypher detects which variant a PDF is and applies a variant-specific parser, returning structured rows with per-cell soft validation against aviation-domain rules.

Adding a new variant is one new file under `sheet_types/<sheet>_variants/<name>.py`
exposing `NAME`, `SIGNATURES`, `CANONICAL_COLUMNS`, `RULES`, and `extract(pdf_path)`.

## Architecture (four-level extraction)

| Level | Strategy | Library | Status |
|-------|----------|---------|--------|
| L1 | Text-layer line parsing | [`pdfplumber`](https://github.com/jsvine/pdfplumber) | ✅ |
| L2 | Layout-aware (word coordinates) | `pdfplumber` word boxes | ⏳ reserved |
| L3 | OCR | [Tesseract](https://github.com/tesseract-ocr/tesseract) (locally) | ✅ local · 🚧 in-browser TODO |
| L4 | Alternative OCR | [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) `PP-Structure` | 🔬 Colab notebook |
| L5 | Layout-aware structured extraction | [docling](https://github.com/docling-project/docling) (TableFormer + layout-analysis ML) | 🔬 Colab notebook — recon in progress |

Per-cell validation comes from `shared/aviation_rules.py` (uppercase-alphanumeric codes, OCR character corrections, regex patterns) and `shared/cleanup.py` (multi-stage cleaning + ATA forward-fill).

## Repository layout

```
cypher/
├── README.md                  this file
├── LICENSE                    MIT
├── CONTRIBUTING.md            how to add a variant or rule
├── docs/
│   └── decisions.md           detailed design and decisions log
├── shared/                    rules, validation, journey tracking
├── sheet_types/
│   ├── occm.py                variant router
│   └── occm_variants/         one file per OCCM variant
├── levels/                    L1 / L2 / L3 / L4 extractors
├── research/
│   ├── workbook.ipynb         analyst notebook
│   ├── report_builder.py      generates the offline HTML report
│   ├── colab_L4_paddleocr.ipynb  fringe-case OCR fallback
│   ├── test_pdfs/             corpus (ignored by git)
│   └── results/               outputs + msn_journey.csv
└── deploy/                    static site for GitHub Pages
    ├── index.html
    ├── main.py                Pyodide entry
    ├── build.py               mirrors source modules into _pymods/
    └── assets/
```

## Local development

Create the venv **outside** any cloud-sync folder (OneDrive, Dropbox, iCloud Drive). macOS's File Provider can hang on `.so` reads inside synced folders and cause Python imports to wedge. A non-synced path like `~/.venvs/cypher` avoids the class entirely:

```bash
git clone <repo>
cd cypher
python3 -m venv ~/.venvs/cypher
~/.venvs/cypher/bin/pip install pdfplumber==0.9.0 pymupdf pytesseract Pillow \
    pandas openpyxl jupyter ipykernel
~/.venvs/cypher/bin/python -m ipykernel install --user --name cypher \
    --display-name "Python 3 (cypher)"
```

Then either activate the venv (`source ~/.venvs/cypher/bin/activate`) or invoke `~/.venvs/cypher/bin/python` directly.

Tesseract must be installed at the OS level for L3 (`brew install tesseract` on macOS).

### Process a PDF

```bash
.venv/bin/python -c "
import sys, pathlib, pandas as pd, fitz
sys.path.insert(0, str(pathlib.Path.cwd()))
from sheet_types import occm
from shared.journey import record_run

pdf = 'research/test_pdfs/your_file.pdf'
variant = occm.detect_variant(pdf)
result = occm.extract(pdf, variant_name=variant)
cleaned = occm.normalize_and_validate(result['records'], variant_name=variant)
df = pd.DataFrame(cleaned)
df.to_csv(f'research/results/by_pdf/{pathlib.Path(pdf).stem}_L1.csv', index=False)
df.to_excel(f'research/results/by_pdf/{pathlib.Path(pdf).stem}_L1.xlsx', index=False)
record_run(pdf, variant, df, len(fitz.open(pdf)))
print(f'{variant}: {len(df)} rows')
"
```

### Generate the offline report

```bash
.venv/bin/python research/report_builder.py
open research/report.html
```

### Test the deploy locally

```bash
cd deploy
python3 -m http.server 8765
# open http://localhost:8765
```

## Deploy to GitHub Pages

1. Push the repository to GitHub.
2. **Settings → Pages**: select the branch, set folder to `/deploy`.
3. The site is live at `https://<user>.github.io/<repo>/` within a minute.

The deploy uses Pyodide; first load installs `pdfplumber==0.9.0` (last release before `pypdfium2` became required — Pyodide can't resolve `pypdfium2`'s C extensions). All subsequent visits use the cached install.

## Variant catalogue

The OCCM router (`sheet_types/occm.py`) dispatches to one of a set of variant modules
under `sheet_types/occm_variants/`, one file per source-document layout. Order matters
for detection — more-specific signatures are listed first so they win over generic ones.
Each variant module's own docstring documents the layout it targets and the parsing
technique used (line-anchored, multi-line record, OCR grid, etc.) without naming the
specific operator, registration, or MSN it was built against.

`sheet_types/ht_variants/` and `sheet_types/llp_variants/` mirror the same pattern for
Hard-Time and Life-Limited-Parts sheets respectively.

Some variants are OCR-only (scanned PDFs, no extractable text layer) and need
`pytesseract` + the native Tesseract binary, neither of which exist under Pyodide;
`sheet_types/llp.py` imports these defensively, and they are never mirrored into
`deploy/`.

## Family classification & manual overrides

Beyond variant detection (which parser to run), Cypher derives a **family** — the airframe
type (A320 family, A330, B737, etc.). This drives cross-aircraft queries like "what
positions does an A330 have that an A340 doesn't?"

Family is derived in tiers by `tools/extract_file_metadata.py`:

1. **Tier 1 (high confidence):** explicit `MODEL/TYPE` header line + the airframe model token
2. **Tier 2 (medium):** `A330`/`A340` token anywhere in header (A-prefix required, registrations masked)
3. **Tier 2b (medium):** Boeing dash-suffix form (`737-700`, `767-300ER`)
4. **Tier 3 (filename):** explicit Boeing token in the filename
5. **Manual override:** user-provided MSN→family map in code or per-file JSON override

For files where automated classification can't tell, a **review-CSV workflow** captures
domain expert input:

```
research/results/family_review_msn_unknowns.csv    # write
tools/extract_file_metadata.py                     # picks up overrides
tools/build_positions_db.py                        # joins onto rows
```

Override JSONs at `/tmp/manual_family_overrides.json` (source_file → family) and
`/tmp/manual_aircraft_key_overrides.json` (source_file → aircraft_key) let you correct
individual airframes without touching code.

## Positions DB (`research/results/positions.sqlite`)

Cypher's downstream output is a SQLite database keyed on extracted rows:

- `positions` — base fact table (one row per component-instance per source file)
- `distinct_positions` view — `(aircraft_key, position)` deduplication; the "slot skeleton"
- `current_fit` view — latest snapshot per `(aircraft_key, position)` ordered by `report_date_iso DESC`
- `position_history` view — full occupancy timeline per slot

Schema is documented in `docs/positions_schema.md`.

## Adding a variant

1. Drop a representative PDF in `research/test_pdfs/`.
2. Add `sheet_types/occm_variants/<name>.py` exposing `NAME`, `SIGNATURES`, `CANONICAL_COLUMNS`, `RULES`, and `extract()`.
3. Register it in `sheet_types/occm.py:VARIANTS`.
4. Run the workbook to verify, then `python deploy/build.py` to mirror into the static deploy.

See `CONTRIBUTING.md` and `docs/decisions.md` for details.

## Privacy

Cypher does not upload, store, or transmit your PDFs. Pyodide runs Python in your browser via WebAssembly; the file you select is processed locally and never leaves the page. The L4 Colab notebook runs on Google's compute and is opt-in for fringe-quality scans where local extraction has failed.

## License

MIT — see [`LICENSE`](LICENSE). Cypher uses several third-party libraries; their licenses are listed in `docs/THIRD_PARTY.md`.
