# Contributing

Cypher is open source under the MIT license. Contributions are welcome — particularly new OCCM variants and rule refinements driven by real documents.

## How OCCMs vary

OCCMs are produced by different MIS software (AMOS, AMASIS, TRAX, in-house tools) and differ between operators and airframe manufacturers. A single hard-coded column schema does not generalize. Cypher's design treats each format as a **variant**, with one file per variant under `sheet_types/occm_variants/`.

## Adding a variant — quick recipe

1. Place a representative PDF in `research/test_pdfs/`.
2. Run the existing pipeline on it; the router will return `Unknown` if no signature matches.
3. Inspect what the text layer or OCR returns, then create a new module:

```python
# sheet_types/occm_variants/example.py
from sheet_types.occm_variants._base import merged_rules

NAME = "Example Operator"
SIGNATURES = ["EXAMPLE OPERATOR", "OCCM REPORT"]   # case-insensitive substrings
CANONICAL_COLUMNS = ["ATA", "DESCRIPTION", "FIN", "PART_NUMBER", "SERIAL_NUMBER"]
RULES = merged_rules({
    # Per-variant overrides — leave empty if globals are sufficient.
})

def extract(pdf_path: str) -> list[dict]:
    # Parse the PDF into list-of-dicts whose keys match CANONICAL_COLUMNS.
    # Add `_page` to each record. `_source` and `_trailer` are optional.
    ...
```

4. Register it in `sheet_types/occm.py:VARIANTS`.
5. Run `research/workbook.ipynb` to verify.
6. Run `python deploy/build.py` to mirror your new variant into the static deploy.

## Soft validation principle

Cypher never drops rows. Cells that fail rules are kept and tagged via the `_issues` column. New variants should follow this principle — your parser produces rows; `shared/cleanup.py` flags problems; the analyst eyeballs the `_issues` column.

## Adding a per-cell rule

`shared/aviation_rules.py` is the central rule file. Edit `OCR_CHAR_MAP`, `SEQUENCE_REPLACEMENTS`, or `COLUMN_RULES` — every consumer reads from this file at import time, so changes propagate everywhere.

When adding a rule, also update `docs/decisions.md` so the rationale is preserved alongside the code.

## Style

- Python ≥ 3.9.
- Type hints encouraged; `__future__ annotations` is fine.
- Docstrings explain the *why*, not the *what*.
- Unit-test rule changes via the test cases at the bottom of `shared/cleanup.py` style.

## License of contributed code

By contributing, you agree your contributions are licensed under the same MIT license as the project.
