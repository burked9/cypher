"""AMASIS "Remaining potentials report" — HT-side variant.

Reuses the existing OCCM "Remaining Potentials" parser verbatim. The same
AMASIS MIS template (2MORO's tool, per the sibling OCCM module's own
docstring) can be run with different `Protocol Type` filters -- an export
filtered to Hard-Time-only positions carries `Protocol Type H/T` on its
header line, e.g.:

    From Position 2100000 To 9999999 Protocol Type H/T Part level * ...

whereas the previously-known OCCM-side files use a different/broader
Protocol Type filter. The row/record shape (six lines per component,
KARDEX + PN/SN + time-matrix rows) is identical either way, so this module
just re-exports the OCCM sibling's `extract`, `CANONICAL_COLUMNS`, and
`RULES` rather than duplicating them.

Detection-order note: the generic header phrases ("Remaining potentials
report", "Aircraft Remaining Potentials", "BI SI Remain Deadline",
"Effectivity :") are deliberately NOT added to `ht.py`'s sheet-type-level
SIGNATURES -- router.py's DETECTION_ORDER checks HT before OCCM, so a
generic phrase there would silently steal every OCCM-flavored Remaining
Potentials file too (the same class of problem flagged in llp.py's
mm510_llp.py comment). Instead `ht.py` gates on the specific, mutually
exclusive `Protocol Type H/T` phrase, which only ever appears on the
HT-flavored export. This variant's own SIGNATURES list (checked only once
already inside the HT router) can safely reuse the OCCM sibling's broader
phrases for variant-level matching.
"""
from __future__ import annotations

from sheet_types.occm_variants import remaining_potentials as _remaining_potentials_occm

NAME = "Remaining Potentials (HT)"
SIGNATURES = list(_remaining_potentials_occm.SIGNATURES) + [
    "Protocol Type H/T",
]

CANONICAL_COLUMNS = _remaining_potentials_occm.CANONICAL_COLUMNS
RULES = _remaining_potentials_occm.RULES


def extract(pdf_path: str):
    return _remaining_potentials_occm.extract(pdf_path)
