# Research notes

## Test corpus

Add representative PDFs to `test_pdfs/`. Aim for at least one of each sheet type:
- OCCM (On Condition – Condition Monitored)
- HT (Hard Time)
- LLP (Life Limited Parts)

## Scoreboard

`results/summary.csv` tracks per-(pdf × sheet_type × level) extraction quality. Re-run the notebook after adding new PDFs.

## Open questions

- Typical file size distribution? (text-PDF vs scanned)
- Are sheet types always on dedicated pages, or mixed?
- Column schemas — capture canonical column lists in `sheet_types/*.py` once we have ~5 examples of each.
