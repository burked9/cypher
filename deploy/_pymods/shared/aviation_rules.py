"""Aviation-domain hyperparameter file.

Edit this when a new edge case appears. Validation is *soft* — cells that
fail patterns are flagged in the `_issues` column, never dropped. This
protects us from breaking when we hit an OCCM from an unfamiliar airframe
manufacturer.

Cleaning order applied to fields with `char_map`:
    1. SEQUENCE_REPLACEMENTS  (multi-char OCR fixes — done first to avoid
       sub-pattern collisions; longest sequences listed first)
    2. OCR_CHAR_MAP           (single-char substitutions)
    3. Field-specific rules   (e.g. revert_I_in_pn_prefix on PART_NUMBER)
    4. Pattern validation     (regex check)

Conventions:
- Vendor / Manufacturer / CAGE codes are 5-character uppercase alphanumeric.
- Part numbers are uppercase alphanumeric (with `-`); no spaces, no `|`,
  no leading or trailing `-`.
- Serial numbers may contain `/`.
- ATA chapters are 2 digits, typically 20–83 for aircraft systems.
- Leading-letter prefixes of PNs are up to 3 letters; `1` between letters
  in that prefix is an OCR misread of `I` and is reverted.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Multi-character OCR sequence replacements.
# Applied BEFORE OCR_CHAR_MAP. Order matters — list longer / more specific
# sequences first so they aren't shadowed by single-char rules.
# ---------------------------------------------------------------------------
SEQUENCE_REPLACEMENTS: list[tuple[str, str]] = [
    # Apostrophe-dash combinations are misreads of "7"
    ("-'", "7"),
    ("'-", "7"),
    # Degree-1 is also a "7" (e.g. "°1" rendering of a "7")
    ("°1", "7"),
    ("1°", "7"),
    # Doubled tildes / interpuncts collapse to a single dash
    ("~~", "-"),
    ("··", "-"),
]


# ---------------------------------------------------------------------------
# Single-character OCR substitutions.
# Applied AFTER SEQUENCE_REPLACEMENTS, on fields with `char_map` in their rule.
# ---------------------------------------------------------------------------
OCR_CHAR_MAP: dict[str, str] = {
    "O": "0",
    "o": "0",
    "l": "1",
    "I": "1",      # often reverted on PART_NUMBER's leading letter prefix
    "|": "",
    "$": "S",
    "£": "E",
    "€": "E",
    # Single tildes / interpuncts / degrees become dashes after the
    # sequence pass has handled the doubled / "°1" cases.
    "~": "-",
    "·": "-",
    "°": "-",
    # Stray quote chars left over after sequence replacements get dropped
    "'": "",
    "`": "",
    # NOTE: S/5 disambiguation deferred — needs a per-airframe PN reference
    # list (an authoritative PN master) to be reliable.
}


# ---------------------------------------------------------------------------
# Per-column rules.
# Missing keys mean "no rule" (flag-friendly default).
# ---------------------------------------------------------------------------
COLUMN_RULES: dict[str, dict] = {
    "ATA": {
        "pattern": r"^\d{2}$",
        "int_range": (20, 83),
    },
    "ZONE": {
        "pattern": r"^\d{2,3}$",
    },
    "FIN": {
        "pattern": r"^[A-Z0-9]{2,8}$",
        "uppercase": True,
        "char_map": OCR_CHAR_MAP,
        "sequence_map": SEQUENCE_REPLACEMENTS,
        "no_spaces": True,
    },
    "DESCRIPTION": {
        "uppercase": True,
    },
    "VENDOR_CODE": {
        "pattern": r"^[A-Z0-9]{4,5}$",
        "uppercase": True,
        "char_map": OCR_CHAR_MAP,
        "sequence_map": SEQUENCE_REPLACEMENTS,
        "no_spaces": True,
    },
    "PART_NUMBER": {
        # Pattern: must start AND end with alphanumeric (no leading/trailing `-`).
        # Internal hyphens are fine. Single-char PNs allowed.
        "pattern": r"^[A-Z0-9](?:[A-Z0-9\-]*[A-Z0-9])?$",
        "uppercase": True,
        "char_map": OCR_CHAR_MAP,
        "sequence_map": SEQUENCE_REPLACEMENTS,
        "no_spaces": True,
        # Field-specific: revert I→1 within the leading letter prefix.
        # Catches OCR cases like "S1C5059" → "SIC5059".
        "revert_I_in_pn_prefix": True,
        # Strip indentation-marker punctuation (`.`, `,`, `..`) that some
        # MIS exports (TAP, Swiss A340, EL AL B767 MSN 28132) emit on
        # sub-component rows. The dots are formatting, not real PN chars.
        "_strip_leading_punct": True,
    },
    "SERIAL_NUMBER": {
        # SNs may contain forward slashes (per real-world examples).
        "pattern": r"^[A-Z0-9/](?:[A-Z0-9\-/]*[A-Z0-9/])?$",
        "uppercase": True,
        "char_map": OCR_CHAR_MAP,
        "sequence_map": SEQUENCE_REPLACEMENTS,
        # SN keeps slashes; pipes still stripped via char_map.
        # SNs occasionally inherit the same `.` indentation prefix; strip
        # for the same reason as PART_NUMBER.
        "_strip_leading_punct": True,
    },
}
