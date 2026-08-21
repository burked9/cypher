"""link_pair — pair an OCCM PDF with an HT PDF for one airframe.

Phase-2 of the OCCM+HT combined-mode roadmap. Standalone module so it can
be invoked from:

  * The local CLI (`tools/export_combined.py --occm-pdf ... --ht-pdf ...`)
  * A future in-browser combined-mode UI (dual drop zone)
  * Tests and ad-hoc scripts

The function inspects the two PDFs, extracts their identifying metadata
(MSN, registration, filename-derived aircraft_key), and returns a
`PairResult` describing the link status. The caller decides what to do
with each status — a CLI tool can fail fast on mismatch, an in-browser
UI can show a confirmation banner and offer a manual override.

Confidence ladder (mirrors the existing aircraft_key derivation):

  +-------------------+-------------------------------------------------+
  | status            | meaning                                         |
  +-------------------+-------------------------------------------------+
  | manual_override   | caller supplied an aircraft_key; trust it       |
  | msn_match         | both PDFs carry the same MSN in their headers   |
  | registration_match| same registration tail (e.g. "4X-EAM")          |
  | msn_one_side_only | one side has MSN, the other doesn't — match if  |
  |                   | the other side's filename-derived key matches   |
  | msn_mismatch      | both have MSN, they DON'T match — STOP          |
  | registration_mismatch | both have reg, they don't match              |
  | filename_only     | neither header carries strong ID — fall back    |
  |                   | to filename-derived keys; warn if they differ   |
  | no_match          | nothing matches; manual override required       |
  +-------------------+-------------------------------------------------+

The first three are "auto-pair safe". The next two are hard errors that
must surface to the user. The last three are "ask before combining."
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import pathlib
import re
import sys

# Reach the shared header-parsing helpers in extract_file_metadata.py.
ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.extract_file_metadata import (
    read_header, extract_msn, extract_registration, derive_family,
)
from tools.build_positions_db import derive_aircraft_key


@dataclass
class SideInfo:
    """What we learnt about one PDF (OCCM or HT side of a pair)."""
    pdf_path: str
    filename: str
    msn: str = ""
    registration: str = ""
    family: str = ""
    aircraft_key: str = ""
    aircraft_key_source: str = ""
    header_snippet: str = ""


@dataclass
class PairResult:
    """Outcome of `link_pair(occm_pdf, ht_pdf)`."""
    status: str                       # see ladder above
    aircraft_key: str = ""            # the agreed key (empty on hard mismatch)
    confidence: str = ""              # 'high' | 'medium' | 'manual_required'
    occm: Optional[SideInfo] = None
    ht: Optional[SideInfo] = None
    warnings: list[str] = field(default_factory=list)

    @property
    def is_safe_auto_pair(self) -> bool:
        return self.status in (
            "manual_override", "msn_match", "registration_match",
            "msn_one_side_only",
        )

    @property
    def needs_user_decision(self) -> bool:
        return self.status in (
            "filename_only", "no_match",
        )

    @property
    def is_hard_mismatch(self) -> bool:
        return self.status in (
            "msn_mismatch", "registration_mismatch",
        )

    def summary(self) -> str:
        ak = self.aircraft_key or "(none)"
        return (f"PairResult(status={self.status}, aircraft_key={ak}, "
                f"confidence={self.confidence}, "
                f"occm={self.occm.filename if self.occm else None}, "
                f"ht={self.ht.filename if self.ht else None}, "
                f"warnings={len(self.warnings)})")


def inspect_side(pdf_path: str) -> SideInfo:
    """Read header, derive identifying metadata for one PDF.

    Returns a SideInfo even on error — the empty fields are themselves
    a signal to the caller.
    """
    p = pathlib.Path(pdf_path)
    info = SideInfo(pdf_path=str(p), filename=p.name)
    try:
        head = read_header(str(p))
    except Exception as e:
        info.warnings = [f"header read failed: {e}"]  # field added inline
        return info
    info.header_snippet = " ".join(head[:240].split())
    msn = extract_msn(head)
    reg = extract_registration(head)
    fam, _model, _conf = derive_family(head)
    info.msn = (msn or "").strip()
    info.registration = (reg or "").strip()
    # Filename fallback for MSN — mirrors the same fallback in
    # tools/extract_file_metadata.py main(). Many filenames embed MSN
    # as `MSN12345`, `MSN 12345`, or `_msn12345_` even when the header
    # text doesn't surface it (e.g. TAP's MSN223 log files).
    if not info.msn:
        fn_m = re.search(r"\bMSN[ _-]?(\d{3,6})\b", info.filename, re.I)
        if fn_m:
            info.msn = fn_m.group(1)
    info.family = fam if fam != "Unknown" else ""
    # aircraft_key: header MSN > registration > filename-derived.
    if info.msn:
        info.aircraft_key, info.aircraft_key_source = info.msn, "header_msn"
    elif info.registration:
        info.aircraft_key, info.aircraft_key_source = info.registration, "header_registration"
    else:
        ak, src = derive_aircraft_key(info.filename)
        info.aircraft_key, info.aircraft_key_source = ak, src
    return info


def link_pair(occm_pdf: str, ht_pdf: str,
              manual_override: Optional[str] = None) -> PairResult:
    """Pair the two PDFs. Returns a PairResult describing link status."""
    if manual_override:
        # Caller-supplied key wins unconditionally — still inspect both
        # sides so the caller can show what was overridden.
        occm_info = inspect_side(occm_pdf)
        ht_info = inspect_side(ht_pdf)
        return PairResult(
            status="manual_override",
            aircraft_key=manual_override,
            confidence="manual_required",
            occm=occm_info,
            ht=ht_info,
            warnings=[],
        )

    occm_info = inspect_side(occm_pdf)
    ht_info = inspect_side(ht_pdf)
    warnings: list[str] = []

    # Strongest signal: both headers carry an MSN
    if occm_info.msn and ht_info.msn:
        if occm_info.msn == ht_info.msn:
            return PairResult(
                status="msn_match", aircraft_key=occm_info.msn,
                confidence="high", occm=occm_info, ht=ht_info)
        else:
            return PairResult(
                status="msn_mismatch", aircraft_key="",
                confidence="manual_required",
                occm=occm_info, ht=ht_info,
                warnings=[f"OCCM MSN {occm_info.msn!r} != HT MSN {ht_info.msn!r}"])

    # Next: both have registration
    if occm_info.registration and ht_info.registration:
        if occm_info.registration == ht_info.registration:
            return PairResult(
                status="registration_match",
                aircraft_key=occm_info.registration,
                confidence="high", occm=occm_info, ht=ht_info)
        else:
            return PairResult(
                status="registration_mismatch", aircraft_key="",
                confidence="manual_required",
                occm=occm_info, ht=ht_info,
                warnings=[f"OCCM reg {occm_info.registration!r} "
                          f"!= HT reg {ht_info.registration!r}"])

    # One-sided MSN: does the silent side's filename-derived key agree?
    if occm_info.msn and not ht_info.msn:
        if ht_info.aircraft_key == occm_info.msn:
            return PairResult(
                status="msn_one_side_only", aircraft_key=occm_info.msn,
                confidence="medium", occm=occm_info, ht=ht_info,
                warnings=[f"HT header carried no MSN; matched on "
                          f"filename-derived key {ht_info.aircraft_key!r}"])
        warnings.append(
            f"OCCM MSN {occm_info.msn!r}; HT header silent and filename "
            f"yields {ht_info.aircraft_key!r} ({ht_info.aircraft_key_source})")
    if ht_info.msn and not occm_info.msn:
        if occm_info.aircraft_key == ht_info.msn:
            return PairResult(
                status="msn_one_side_only", aircraft_key=ht_info.msn,
                confidence="medium", occm=occm_info, ht=ht_info,
                warnings=[f"OCCM header carried no MSN; matched on "
                          f"filename-derived key {occm_info.aircraft_key!r}"])
        warnings.append(
            f"HT MSN {ht_info.msn!r}; OCCM header silent and filename "
            f"yields {occm_info.aircraft_key!r} ({occm_info.aircraft_key_source})")

    # Fallback: both filename-derived. Agree?
    if occm_info.aircraft_key and occm_info.aircraft_key == ht_info.aircraft_key:
        return PairResult(
            status="filename_only", aircraft_key=occm_info.aircraft_key,
            confidence="manual_required", occm=occm_info, ht=ht_info,
            warnings=warnings + [
                "Neither header carried a strong MSN/registration — "
                "matched on filename-derived key. Confirm before relying on this."])

    # Nothing matches.
    warnings.append(
        f"No common identifier: OCCM={occm_info.aircraft_key!r} "
        f"({occm_info.aircraft_key_source}); "
        f"HT={ht_info.aircraft_key!r} ({ht_info.aircraft_key_source})")
    return PairResult(
        status="no_match", aircraft_key="",
        confidence="manual_required",
        occm=occm_info, ht=ht_info, warnings=warnings)
