# `positions.sqlite` — Schema reference

Cypher's downstream output. Built by `tools/build_positions_db.py` from the
per-file CSVs under `research/results/by_pdf/`. Mirrored to both
`research/results/positions.sqlite` and `/tmp/positions.sqlite`.

This file is self-contained — a forked session can read it and know
exactly what every column, view, and join key means without re-deriving.

## `positions` — the base fact table

One row per component-instance per source document. Everything is included —
rows that fail soft validation stay in, with their issues visible in `row_issues`.

| Column | Type | What it is |
|---|---|---|
| `id` | INTEGER PK | autoincrement primary key |
| `source_file` | TEXT | original PDF filename — provenance, never modified |
| `variant` | TEXT | which OCCM parser produced this row (see README variant catalogue) |
| `aircraft_key` | TEXT | **join key for cross-snapshot queries** — see [`aircraft_key`](#aircraft_key-derivation) |
| `aircraft_key_source` | TEXT | how that key was derived (see table below) |
| `registration` | TEXT | tail/fin number from PDF header (`VN-A350`, `PK-CMJ`) — nullable |
| `msn` | TEXT | Manufacturer Serial Number from PDF header — nullable |
| `family` | TEXT | airframe family — see [families](#families) |
| `family_confidence` | TEXT | `high` / `medium` / `manual_review` / `manual` / `filename` / `ocr` / `none` |
| `model_raw` | TEXT | the model token literally matched (`A330`, `B737-800`, `321-231` …) |
| `report_date` | TEXT | raw report-date string from the PDF header (any format) |
| `report_date_iso` | TEXT | normalised `YYYY-MM-DD` form — blank if unparseable |
| `ata` | TEXT | ATA chapter (may be forward-filled — see `row_issues` for `_imputed:ATA`) |
| `position` | TEXT | **normalised slot identifier** — see [position normalisation](#position-normalisation) |
| `position_source` | TEXT | which source column this came from (`FIN`, `POS`, `LOCATION`, …) |
| `zone` | TEXT | airframe zone, where the variant has one |
| `kardex` | TEXT | flat 6-digit ATA-derived code from Remaining Potentials / Technical Object Listing |
| `description` | TEXT | component description |
| `part_number` | TEXT | |
| `serial_number` | TEXT | |
| `row_issues` | TEXT | comma-joined soft-validation flags (`empty`, `bad_format`, `out_of_range`, `over_review_band`, `_imputed:ATA`) |
| `page` | INTEGER | source page number |

### `aircraft_key` derivation

Preference order (`aircraft_key_source` records which won):

| Source | Strength | Notes |
|---|---|---|
| `manual_msn` / `manual_template` | **manual** | user-confirmed via override JSON |
| `header_msn` | **strong** | MSN parsed from PDF header text |
| `header_registration` | **strong** | tail/fin parsed from PDF header (labelled or unlabelled) |
| `msn` | **strong** | explicit `MSN <NNNN>` token in filename |
| `msn_prefix` | strong | leading numeric prefix in filename (`0469_a305_…`) |
| `registration` | strong | tail/fin token in filename |
| `registration_compressed` | strong | compressed reg like `CSTQW` → `CS-TQW` |
| `msn_guess` | weak | bare 4-5 digit number in filename (year-filtered) |
| `filename` | weak | last-resort filename stem |

For reliable cross-snapshot joining, filter:

```sql
WHERE aircraft_key_source IN
  ('manual_msn','manual_template','header_msn','header_registration',
   'msn','msn_prefix','registration','registration_compressed')
```

(That's 94% of the corpus.)

### `position` normalisation

The `position` column is a normalised identifier coming from one of **seven different
source columns** across the variants. `position_source` preserves which one.

| `position_source` | Looks like | Variants |
|---|---|---|
| `FIN` | `10HC`, `282HN`, `5319HL` | Standard OCCM, OCCM Status List, MSN Components Status List, A330 Engineering Planning |
| `POSITION` | `21`, `1002TW1`, `7SQ` (mixed shapes) | OASES, Avianca, On Condition Monitoring, B777 Annex 8, CONFIG SLOT, others |
| `POS` | `30HQ`, `4022HM` | AMOS, Aircraft Spec File OCCM |
| `LOCATION` | `E/E`, `CARGO`, `FRONT CARGO` (coarser) | Cathay OCCM, Iberia Listado, CCA A340 OCCM |
| `POSN` | mixed | OCCM List As At |
| `FUNCTIONAL_LOCATION` | SAP-style | Technical Object Listing |
| `AMM_FIN` | AMM-derived FIN (often `O/C` placeholder — use `kardex` instead) | Remaining Potentials |

**Critical:** `FIN '10HC'` and `LOCATION 'CARGO'` are NOT the same kind of identifier.
**Constrain set-comparisons to a single `position_source`** unless you specifically want a
loose union:

```sql
-- Clean A330-only positions, FIN-only
SELECT DISTINCT position FROM positions
WHERE family='A330' AND position<>'' AND position_source='FIN'
EXCEPT
SELECT DISTINCT position FROM positions
WHERE family='A340' AND position<>'' AND position_source='FIN';
```

### `kardex` vs `position`

For two variants (Remaining Potentials, Technical Object Listing), the **KARDEX** column
— a flat 6-digit ATA-derived code like `345101A` — is the real slot identifier, while
`position` is often a generic placeholder (`O/C` = "On Condition").

Currently **5,932 + 3,338 = 9,270 rows have a kardex value**.

When querying these variants, prefer `kardex` over `position`:

```sql
SELECT aircraft_key, kardex, part_number FROM positions
WHERE kardex <> '' AND family='A330';
```

### Families

Auto-derived in `tools/extract_file_metadata.py`. Possible values:

| Family | Notes |
|---|---|
| `A320 family` | A318/A319/A320/A321 — collapsed to one bucket because the user works them as one fleet |
| `A330` | |
| `A340` | |
| `A350` | (corpus has none — any A350 row is a bug, the user has confirmed this) |
| `A380` | |
| `B737` | |
| `B747` | (none in corpus) |
| `B757` | |
| `B767` | |
| `B777` | |
| `B787` | (none in corpus) |
| `Embraer` | E170 / E190 / ERJ190 etc. |
| `Bombardier CRJ` | CRJ-700 / CRJ-900 |
| `Unknown` | residual — see `family_confidence='none'` |

`family_confidence` values:

- `high` — model on an explicit MODEL/TYPE header line
- `medium` — model token found anywhere in the header (reg-masked)
- `manual_review` — applied via the user's review-CSV override
- `manual` — hardcoded MSN→family override in `_MANUAL_MSN_FAMILY`
- `filename` — fallback from Boeing model token in filename
- `ocr` — derived from OCR'd text (image-only PDFs)
- `none` — Unknown

## Views

### `distinct_positions`

```sql
CREATE VIEW distinct_positions AS
SELECT DISTINCT aircraft_key, family, position, position_source, variant
FROM positions WHERE position <> '';
```

One row per `(aircraft_key, position)` — the **slot skeleton** of each airframe.
This is the view that drives cross-airframe position-set comparisons.

### `current_fit`

```sql
-- Latest snapshot per (aircraft_key, position), real-date ordered.
-- Falls back to highest id for rows without a parseable date.
```

For each `(aircraft_key, position)`, returns the most recent row by
`report_date_iso DESC` with `id DESC` as tiebreaker.

**95.1% of rows have a parseable `report_date_iso`.** Rows with an empty
`report_date_iso` sort to the bottom — they only win when no dated alternative
exists.

### `position_history`

```sql
CREATE VIEW position_history AS
SELECT aircraft_key, position, source_file, part_number, serial_number,
       description, row_issues
FROM positions WHERE position <> ''
ORDER BY aircraft_key, position, source_file;
```

Full occupancy timeline per slot — useful for "what was at slot X over time."

## Soft-validation flags (`row_issues`)

Tag forms you'll see in the comma-joined `row_issues` column:

| Tag | Meaning |
|---|---|
| `<COL>:empty` | required column was empty |
| `<COL>:bad_format` | failed the regex pattern |
| `<COL>:not_a_number` | numeric field couldn't be parsed |
| `<COL>:out_of_range` | numeric out of the variant's hard bounds (e.g. cycles >55,000) |
| `<COL>:over_review_band` | numeric in the **soft review** band (e.g. cycles 30,001–55,000 on engine LLPs) |
| `_imputed:ATA` | ATA was forward-filled from the most recent section header |
| `_imputed:POSITION` | position was synthetically generated (reserved — not currently used) |
| `PART_NUMBER:unknown_pn` | (reserved) PN not in the master Bloom filter |

**No row is ever silently dropped.** Failed validation = flagged.

## Worked-example queries

```sql
-- Position skeleton for one airframe
SELECT DISTINCT position, description
FROM distinct_positions WHERE aircraft_key='2974'
ORDER BY position;

-- A330-only vs A340-only slots (FIN, like-for-like)
SELECT DISTINCT position FROM positions
WHERE family='A330' AND position_source='FIN' AND position<>''
EXCEPT
SELECT DISTINCT position FROM positions
WHERE family='A340' AND position_source='FIN' AND position<>'';

-- Current part fitted at every slot on MSN 2974
SELECT position, part_number, serial_number, report_date_iso
FROM current_fit
WHERE aircraft_key='2974' ORDER BY position;

-- All snapshots of a single slot
SELECT report_date_iso, part_number, serial_number, source_file
FROM positions
WHERE aircraft_key='2974' AND position='10HC'
ORDER BY report_date_iso DESC;

-- B737 fleet summary
SELECT aircraft_key, registration, msn,
       COUNT(*) AS rows,
       COUNT(DISTINCT position) AS slots
FROM positions WHERE family='B737'
GROUP BY aircraft_key ORDER BY rows DESC;

-- KARDEX-based query for Remaining Potentials / Technical Object Listing
SELECT aircraft_key, kardex, part_number, description
FROM positions WHERE kardex<>'' AND family='A330';
```

## Data quirks worth knowing

- **`A359`, `A350` in a filename ≠ A350 family.** They're tail/fin labels. Family
  is derived only from header MODEL tokens (or manual overrides).
- **The corpus has zero A350-family airframes.** User-confirmed.
- **`UNKNOWN` is a legitimate sentinel** for TSN/CSN in some variants (CCA A340,
  Avianca), not a parsing failure.
- **`ORIGINAL` is a legitimate sentinel** for LOCATION and INSTALL_DATE on CCA A340 —
  means "factory original, no slot recorded."
- **For multi-snapshot aircraft, filter by `aircraft_key_source IN ('header_msn',
  'header_registration','manual_msn','manual_template')`** to ensure clean joining.
  The 6 aircraft on `filename`-only keys don't cross-join reliably.
- **`B777 Annex 7 OCCM` variant rows are a parts template**, NOT operational OCCM.
  They have `position=''` and `serial_number=''`. Filter with `WHERE position<>''`
  to exclude template data from positions queries.
- **Sibling-cluster expansion** for some manual overrides: the 8 F-HBXK Component
  Fitted List files all carry `aircraft_key='17000008'`, even though their filenames
  are different — that's by design so they cross-snapshot-join as one airframe.
