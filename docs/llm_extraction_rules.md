# LLM extraction rules — aviation component lists (OCCM / HT)

**Purpose.** Reference for an LLM agent extracting component-list rows from
aircraft-maintenance PDFs (OCCM, HT, LLP). Read this **before** processing
any document. The rules below come from a hand-tuned corpus of 1000+
aviation-maintenance PDFs and capture every parsing failure pattern we've
seen — apply them and the output will line up with the Cypher pipeline's
existing schema and validation.

**Scope.** OCCM (On-Condition Component Monitoring) lists and HT
(Hard-Time / life-limited) lists. Same rules apply to both — the only
difference is the column set (HT has extra task / due-date / interval
columns).

**Cardinal rules.**
1. **Never drop a row silently.** If a value fails validation, emit the
   row with the bad value AND add a flag in `row_issues`.
2. **Normalise before validating.** Apply the cleanup rules (section 8)
   before checking the regex patterns.
3. **Forward-fill ATA** when a row inherits it from a section header.
4. **Preserve provenance.** Always emit `source_file` and `_page`.

---

## 1. Output schema — what the LLM must emit

One row per component-instance. Required columns; emit as JSON dict
or CSV row:

| Field            | Type   | Notes |
|------------------|--------|-------|
| `ATA`            | str    | 2-digit chapter, e.g. `"21"`. Forward-filled when needed. |
| `PART_NUMBER`    | str    | Cleaned per section 3. Empty allowed, flag `PART_NUMBER:empty`. |
| `SERIAL_NUMBER`  | str    | Cleaned per section 4. Empty allowed, flag `SERIAL_NUMBER:empty`. |
| `POSITION`       | str    | Cleaned per section 5. Empty allowed for some variants. |
| `DESCRIPTION`    | str    | Component description; may span multiple source-line fragments. |
| `INSTALL_DATE`   | str    | Normalised to ISO `YYYY-MM-DD` if possible, else preserve raw. |
| `TSN`            | str    | Total time since new (hours, integer). |
| `CSN`            | str    | Total cycles since new (integer). |
| `row_issues`     | str    | Comma-joined validation flags. Empty = clean. |
| `_page`          | int    | Source page number (1-based). |

HT-specific extra fields (emit when present):
`TASK`, `TASK_NUMBER`, `INTERVAL`, `LAST_DONE`, `NEXT_DUE`, `REMAINING`,
`ZONE`.

---

## 2. PART_NUMBER rules

**Valid PN regex:** `^[A-Z0-9](?:[A-Z0-9\-]*[A-Z0-9])?$`

A PN must:
- Start with `[A-Z0-9]` (letter or digit — **no** leading `.`, `,`, `-`)
- End with `[A-Z0-9]` (no trailing `-`)
- Contain only `[A-Z0-9-]` (uppercase letters, digits, internal hyphens)
- Have no spaces (collapse any whitespace before validating)

| Example | Verdict |
|---|---|
| `968A0000-03` | ✓ |
| `9024-15704-2` | ✓ |
| `113T2201-37G` | ✓ |
| `S9310B1720` | ✓ |
| `B-HL` | ✓ (single internal hyphen, alphanumeric ends) |
| `K` | ✓ (single char allowed) |
| `.968A0000-03` | ✗ leading dot — STRIP `.,;:•·*` from the start then re-validate |
| `,114193600` | ✗ leading comma — STRIP and re-validate |
| `968A0000-03 ` | ✗ trailing space — TRIM whitespace |
| `968A0000-` | ✗ trailing hyphen — STRIP trailing `-` then re-validate |
| `968A0000-03/04` | ✗ slash not allowed in PN (slashes belong to SN) |
| `968 A0000-03` | ✗ internal space — COLLAPSE spaces |
| `968A0000_03` | ✗ underscore — REPLACE `_` with `-` if it's clearly an OCR error |

**Cleanups to apply, in order, before validating:**
1. Strip leading punctuation: `s = s.lstrip(".,;:•·*")`
2. Trim whitespace: `s = s.strip()`
3. Strip trailing `-`: `s = s.rstrip("-")` (handles line-wrap artefacts)
4. Uppercase: `s = s.upper()`
5. Collapse internal whitespace: `s = re.sub(r"\s+", "", s)`
6. OCR character revert inside the leading letter prefix only:
   `I` → `1` becomes `S1C5059` → original was `SIC5059`. Only revert
   when the `I` sits BETWEEN two letters.

**Common OCR confusions** (apply judgement; the surrounding context
usually disambiguates):
- `O` ↔ `0` — PNs starting with letter `O` are rare; default to digit `0`
  for ambiguous chars BUT preserve clear `O` after letters
- `I` ↔ `1` — letter `I` rare in PNs; default to digit `1`
- `l` (lowercase L) ↔ `1` — always digit `1` in PN context
- `S` ↔ `5`, `B` ↔ `8`, `Z` ↔ `2` — only correct if the surrounding
  characters make digits clearly wrong

---

## 3. SERIAL_NUMBER rules

**Valid SN regex:** `^[A-Z0-9/](?:[A-Z0-9\-/]*[A-Z0-9/])?$`

Differs from PN: **forward slashes ARE allowed** (real SNs frequently
contain `/`).

| Example | Verdict |
|---|---|
| `0319414` | ✓ |
| `9911984` | ✓ |
| `02-01-2686` | ✓ |
| `BNG25865` | ✓ |
| `0756A00ES006547` | ✓ |
| `7897/12613` | ✓ slash allowed |
| `09052000818BA` | ✓ |
| `.4427` | ✗ leading dot — STRIP and re-validate |
| `4427-` | ✗ trailing hyphen — STRIP and re-validate |
| `UNKNOWN` | ✓ sentinel — keep verbatim; do NOT flag |
| `N/A` | ✓ sentinel — keep verbatim |
| `ORIGINAL` | ✓ sentinel (CCA A340 variant) — keep verbatim |

**Cleanups:** same as PN sections 1-5 above. Do NOT apply the
`I` ↔ `1` letter-prefix revert to SN — SNs legitimately mix letters and
digits in any order.

---

## 4. POSITION rules

Aviation MIS systems use **seven different position-column conventions**.
Identify which one the source PDF uses from the column header, and emit
the value verbatim. Don't try to convert between them — they are not
interchangeable.

| Source column | Looks like | Operator examples |
|---|---|---|
| `FIN` (Functional Item Number) | `10HC`, `282HN`, `5319HL`, `316HL` | Standard OCCM, MSN Components Status List, A330 Engineering Planning |
| `POSITION` | `21`, `1002TW1`, `7SQ`, `521HH17`, `15HQ` | OASES, Avianca, B777 Annex 8, MM_510 HT, TAP HT |
| `POS` | `30HQ`, `4022HM`, `100HM` | AMOS, Aircraft Spec File OCCM |
| `LOCATION` | `E/E`, `CARGO`, `FRONT CARGO`, `COCKPIT` | Cathay OCCM, Iberia Listado, CCA A340 OCCM |
| `POSN` | mixed strings | OCCM List As At |
| `FUNCTIONAL_LOCATION` | SAP-style `<reg>/<ATA>/<seq>/<pos>` | Technical Object Listing, B777 Annex 8 |
| `AMM_FIN` | `O/C` placeholder mostly | Remaining Potentials (use `KARDEX` column instead) |

**Critical:** `FIN '10HC'` and `LOCATION 'CARGO'` are NOT comparable.
When the LLM is asked to cross-compare positions across aircraft, only
compare values that share the same source-column type.

**Cleanup:** uppercase, strip whitespace. Some positions legitimately
contain `/`, `-`, `#`, e.g. `R/H`, `1R`, `#2`, `FWD R/H` — preserve all
of these characters.

---

## 5. ATA chapter rules

- **Format:** 2 digits, zero-padded. `"21"`, `"05"`, `"34"`.
- **Valid range:** 20 ≤ ATA ≤ 83 (anything outside is a parse error).
- **Dotted variants** in source: `"21-31"`, `"21-26-0"`, `"21.31"` —
  extract the first 2 digits, emit `"21"`.
- **Forward-fill convention:** When a row has no leading ATA token,
  it inherits ATA from the most recent valid ATA-section header.
  Emit the inherited value AND add `_imputed:ATA` to `row_issues` so
  downstream consumers know it was filled, not read.

| Source token | Emit |
|---|---|
| `21` | `"21"` |
| `21-31-4` | `"21"` |
| `21.52` | `"21"` |
| `2100` | `"21"` (extract first 2 digits) |
| `5` (single digit) | `"05"` (zero-pad) |
| `00` | flag `ATA:out_of_range` — keep value but flag |
| `99` | flag `ATA:out_of_range` |
| (empty + previous row had `"21"`) | `"21"` + flag `_imputed:ATA` |

---

## 6. Date formats — variants seen in the corpus

Normalise to ISO `YYYY-MM-DD` when possible; preserve raw string when
you can't.

| Source format | Example | ISO |
|---|---|---|
| `DD.Mmm.YYYY` | `01.Sep.2014` | `2014-09-01` |
| `DD Mmm YYYY` | `12 Jun 2014` | `2014-06-12` |
| `DDMmmYYYY` (compact) | `20NOV2019`, `27JUN2016` | `2019-11-20` |
| `DD-Mon-YY` (Sun Express MM_510) | `04-OCT-13` | `2013-10-04` |
| `DD-MM-YYYY` (MM_510 Atlas Global) | `28-02-2014` | `2014-02-28` |
| `DD/MM/YYYY` (Iberia bilingual) | `15/03/2005` | `2005-03-15` |
| `MM/DD/YYYY` (STARS / Trax US) | `08/24/2017` | `2017-08-24` |
| `YYYY-MM-DD` | `2020-01-18` | `2020-01-18` |
| `DD.MM.YYYY` (Georgian Airways) | `04.07.2016` | `2016-07-04` |
| Portuguese month abbreviations | `OUT`, `FEV`, `AGO`, `SET`, `DEZ` | translate to month number |
| French month abbreviations | `JANV`, `JUIN`, `SEPT`, `DÉC`, `AOÛ`, `FÉVR` | translate to month number |

**Ambiguous DD/MM vs MM/DD:** If both fields ≤ 12 the day/month order
is ambiguous. Use operator hint: US carriers (Sunwing, Allegiant) use
`MM/DD`; everyone else uses `DD/MM`. If unsure, keep raw and add flag
`INSTALL_DATE:ambiguous`.

---

## 7. OCR artefacts to clean before output

These are real, repeated, observed patterns in the corpus.

### 7.1 Leading-punctuation indentation
**Pattern:** TAP, Swiss A340, EL AL B767 use a leading `.`, `,`, or `..`
on PN/SN tokens to denote sub-component indentation in the source PDF.

**Examples:**
- `.968A0000-03` → strip → `968A0000-03` ✓
- `,114193600` → strip → `114193600` ✓
- `..OO-200-1462` → strip the dots → `OO-200-1462` ✓

**Rule:** `value = value.lstrip(".,;:•·*")` before validating.

### 7.2 Doubled-character headers
**Pattern:** Some PDFs (Aegean ERJ, Alitalia AMOS, OASES Lifed) emit
column headers in a doubled-character font: `AATTAA DDeessccrriippttiioonn`
where each character is repeated.

**Rule:** When detected, treat as half the characters — `AATTAA` →
`ATA`. Detect by checking for `(.)\1` repeat ratio > 50% on a line.

### 7.3 Glued tokens
**Pattern:** PDF text extraction occasionally fuses neighbouring tokens.

**Examples:**
- `10.Mar.l998` — letter `l` for digit `1` inside the year. Fix.
- `12*178` or `12'178` — `*` / `'` as thousands separator. Replace with `,`.
- `7574018 12*178` — sometimes the whole tail collapses to `757401812178`
  — needs intelligent splitting (typically 7-digit TSN + remainder).
- `28-02-2014CLEANING` — date glued to task name. Split on the date pattern.
- `32748FH` — integer glued to its unit (FH/CY). Strip trailing unit
  before validating the integer.

### 7.4 Character confusion
Apply **inside known field types** only — never wholesale on free text:

| In PN/SN | Substitute with |
|---|---|
| `O` between digits | `0` |
| `I` between digits | `1` |
| `l` (lowercase L) | `1` (PN context) |
| `S` next to digits and clearly wrong | `5` |
| `B` next to digits and clearly wrong | `8` |

**Always preserve** in DESCRIPTION fields — descriptions legitimately
mix letters and digits and don't need OCR correction.

### 7.5 Table-border characters
Pipes `|`, dashes used as separators `─`, box-drawing chars — strip
from all fields.

---

## 8. Family classification — derive airframe type from headers

After extracting rows, derive a single **family** for the airframe:
`A320 family | A330 | A340 | A350 | A380 | B737 | B747 | B757 | B767 | B777 | B787 | Embraer | Bombardier CRJ | Unknown`

**Detection ladder (high → low confidence):**

1. **`MODEL/TYPE:`** explicit line in PDF header.
   - `Model: A321-231` → `A320 family`
   - `Type/Series: 737-NG` → `B737`
2. **Airbus prefix anywhere in header**, registration tokens masked first:
   - `A330`, `A340`, `A380` direct match. Mask `VN-A350` (registration) before scanning.
3. **Boeing dash-suffix form** (must end with ≤3 digits + ≤5 letters,
   to reject task-card refs like `747-06209`):
   - `737-700`, `767-300ER`, `777-300ER` → `B737` / `B767` / `B777`.
   - **REJECT** `747-06209` (5 digits after dash — task card, not model).
4. **Boeing B-prefix**:
   - `B777`, `B737-86N` → corresponding family.
5. **Filename fallback**:
   - `MSN 30875` + manual override map → `B777`.
6. **Default**: `Unknown`. Flag for review, never guess.

**Important:** A350 family does not exist in the corpus. Any string
matching `A35[0-9]` in a registration (e.g. `VN-A350`) is a TAIL, not
a model. Mask registrations before family detection.

**A320 family** rolls up: A318, A319, A320, A321.

---

## 9. Decision rules — fix / flag / leave blank

| Situation | Action |
|---|---|
| PN with leading punctuation | FIX silently (strip the punctuation) |
| PN with trailing hyphen (line-wrap artefact) | FIX silently (strip the hyphen) |
| Empty PN | LEAVE BLANK + flag `PART_NUMBER:empty` |
| Empty SN | LEAVE BLANK + flag `SERIAL_NUMBER:empty` |
| SN = `UNKNOWN` / `N/A` / `ORIGINAL` | KEEP VERBATIM (legitimate sentinel) — do not flag |
| ATA out of valid range | KEEP value + flag `ATA:out_of_range` |
| ATA inherited from section header | EMIT inherited value + flag `_imputed:ATA` |
| TSN/CSN out of plausible range (e.g. cycles > 55,000) | KEEP + flag `CSN:out_of_range` |
| Date parse failed | KEEP raw + flag `INSTALL_DATE:bad_format` |
| Ambiguous DD/MM vs MM/DD | KEEP raw + flag `INSTALL_DATE:ambiguous` |
| Whole row looks corrupt | KEEP the row + flag everything wrong with it — **never drop** |

---

## 10. Common parsing mistakes to avoid (lessons from the corpus)

These are mistakes a naive LLM extractor would make. Don't repeat them.

1. **Treating `.968A0000-03` as the PN.** The leading dot is PDF
   indentation, not part of the PN. Cleanup section 7.1.
2. **Joining `RTA-44D 064-50000-0110` into one PN.** Two tokens —
   first is the model marker, second is the PN. Use the column header
   to disambiguate.
3. **Reading the doubled-character header literally.** `AATTAA` is
   `ATA`. Same for `DDeessccrriippttiioonn`.
4. **Splitting `VALVE-AIR MIXING` after the dash.** Description fields
   freely contain hyphens. Don't tokenise descriptions on `-`.
5. **Misclassifying `747-06209` as a B747.** Suffix is too long to be
   a model variant — it's a task-card reference. Family classifier must
   require ≤3 digits after the dash.
6. **Returning `aircraft_key` from a registration when MSN is present.**
   Always prefer the strongest available identifier (MSN > registration
   > filename-derived).
7. **Dropping rows that fail validation.** Every row must survive into
   the output with its flags attached. Downstream consumers depend on
   the complete row set, not the "clean" subset.
8. **Forgetting to forward-fill ATA across section headers.** Rows
   appearing under "Chapter 21" without their own ATA token belong to
   ATA 21 — emit `"21"` + flag `_imputed:ATA`.
9. **Joining glued FH tokens incorrectly.** `32748FH` → strip the
   `FH` suffix, the integer is `32748`. Don't try to parse the full
   string as a number.
10. **Treating engineering drawings, AFM letters, ferry-flight forms,
    and weight & balance reports as component lists.** They're in the
    same source folders but contain no row data. Detect by header — if
    no recognised column header appears, return zero rows + emit a
    `sheet_type: NOT_COMPONENT_LIST` indicator.

---

## 11. Quick-reference cheat sheet

```
PN  valid:  ^[A-Z0-9][A-Z0-9\-]*[A-Z0-9]$         (no leading/trailing -, .)
SN  valid:  ^[A-Z0-9/][A-Z0-9\-/]*[A-Z0-9/]$     (slashes allowed)
ATA valid:  ^\d{2}$  AND  20 <= value <= 83
DATE: parse → YYYY-MM-DD if possible, else keep raw + flag

CLEANUP ORDER on PN/SN:
  1. lstrip(".,;:•·*")
  2. strip()
  3. rstrip("-")
  4. upper()
  5. collapse internal whitespace
  6. (PN only) revert I→1 in leading letter prefix

NEVER:
  - drop a row
  - strip slashes from SN
  - apply OCR correction to DESCRIPTION
  - tokenise DESCRIPTION on hyphens
  - guess family when no model token is present
```

---

**Last updated**: 2026-06-10. Generated from the Cypher project's
hand-tuned corpus of 1000+ aviation maintenance PDFs spanning 28 OCCM
variants, 7 HT variants, and 7 LLP variants. Aligned with the
validation rules in `shared/aviation_rules.py` and the cleanup pipeline
in `shared/cleanup.py`.
