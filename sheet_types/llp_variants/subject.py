"""Subject classifier for LLP sheets.

Categorises an LLP report as one of:
    "Engine"          — engine LLPs (CFM56, V2500, PW, GE, Trent, RB211, JT8D)
    "APU"             — APU LLPs (GTCP, APIC, APS, 131-9, GTCP331)
    "Landing Gear"    — MLG / NLG / LH-MLG / RH-MLG / nose-gear LLPs
    "Other"           — anything else (cargo doors, props, etc.)

Signal sources, in order of strength:
  1. Engine / APU / landing-gear model strings in the document header.
  2. Module labels in the data records (LPC / HPC / HPT / LPT / FAN for
     engines; ATA 32 + descriptions like AXLE / STRUT for landing gear).
  3. Part-number shape (e.g. GE/CFM `1856M89P01`, IAE V2500 `338-001-906-0`,
     Honeywell APU `3800152-XX`).
  4. Cycle-limit magnitude (engine 15-30k, APU 6-15k, landing-gear 50-80k).
     Used as a tiebreaker, not the primary signal.

The function takes the file's full text + extracted records and returns a
`(subject, confidence, signals)` tuple where `confidence` is "high" /
"medium" / "low" and `signals` is a list of strings explaining the call.
"""
from __future__ import annotations
import re
from typing import Iterable

_ENGINE_MODEL_RE = re.compile(
    r"\b(CFM56|CFM-56|CF34|CF6|GE9X|GEnx|LEAP[\- ]?1[AB]|V2500|V2527|V2533|"
    r"PW[12]\d{3}|PW4\d{3}|PW6\d{3}|JT8D|JT9D|RB211|TRENT[ \-]?\d{0,4}|"
    r"GP7\d{3}|GTF)\b",
    re.IGNORECASE,
)

_APU_MODEL_RE = re.compile(
    r"\b(APU|GTCP\d*|GTCP-\d+|APIC|APS\d{3,4}|131-9[AB]?|331-\d{3})\b",
    re.IGNORECASE,
)

_LG_MODEL_RE = re.compile(
    r"\b(MLG|NLG|MAIN\s+LANDING\s+GEAR|NOSE\s+LANDING\s+GEAR|"
    r"LANDING\s+GEAR|SHOCK\s+STRUT|TORQUE\s+LINK|TRUNNION|PINTLE)\b",
    re.IGNORECASE,
)

# Distinctive PN prefixes
_ENGINE_PN_RE = re.compile(
    r"^(?:\d{3,4}M\d{1,3}[GP]\d{1,3}|"     # GE/CFM: 1856M89P01, 338M..
    r"338-\d{3}-\d{3}-\d|"                 # IAE V2500: 338-001-906-0
    r"336-\d{3}-\d{3}-\d|"                 # IAE V2500: 336-001-804-0
    r"50N\d{4}|"                           # PW PW1100G
    r"3\d{4}-\d{2,4}|"                     # CFMI: 1502M..)
    r"\d{4}M\d{1,3})",
    re.IGNORECASE,
)
_APU_PN_RE = re.compile(r"^(?:3800\d{3}-|389\d{4}-|GTCP)", re.IGNORECASE)

# Module labels typical of engine LLP reports
_ENGINE_MODULE_LABELS = {
    "LPC", "HPC", "HPT", "LPT", "FAN", "BOOSTER", "COMBUSTOR",
    "COMBUSTION", "COMP", "TURBINE",
}

# Description keywords characteristic of landing gear
_LG_DESC_KEYWORDS = re.compile(
    r"\b(AXLE|TRUNNION|SLIDING\s+TUBE|OUTER\s+CYLINDER|INNER\s+CYLINDER|"
    r"SHIMMY|TORQUE\s+LINK|MAIN\s+FITTING|SHOCK\s+STRUT|PINTLE|"
    r"DRAG\s+STRUT|SIDE\s+STAY|PIN/BOLT)\b",
    re.IGNORECASE,
)


def classify(file_text: str, records: list[dict]) -> dict:
    """Return {subject, confidence, signals}."""
    signals: list[str] = []
    text_head = file_text[:3000]

    eng_hits = len(_ENGINE_MODEL_RE.findall(text_head))
    apu_hits = len(_APU_MODEL_RE.findall(text_head))
    lg_hits  = len(_LG_MODEL_RE.findall(text_head))

    if eng_hits:
        signals.append(f"header:engine-model-mentions×{eng_hits}")
    if apu_hits:
        signals.append(f"header:apu-mentions×{apu_hits}")
    if lg_hits:
        signals.append(f"header:landing-gear-mentions×{lg_hits}")

    # Module labels on records
    modules = {(r.get("MODULE") or "").upper() for r in records if r.get("MODULE")}
    eng_modules = modules & _ENGINE_MODULE_LABELS
    if eng_modules:
        signals.append(f"modules:{','.join(sorted(eng_modules))}")

    # ATA chapter signal (32 = LG, 49 = APU, 70-80 = engines/powerplant)
    atas: list[int] = []
    for r in records:
        a = (r.get("ATA") or "").strip()
        if a.isdigit():
            atas.append(int(a))
    eng_atas = sum(1 for a in atas if 70 <= a <= 80)
    lg_atas  = sum(1 for a in atas if a == 32)
    apu_atas = sum(1 for a in atas if a == 49)
    if eng_atas:
        signals.append(f"ata:engine×{eng_atas}")
    if lg_atas:
        signals.append(f"ata:landing-gear×{lg_atas}")
    if apu_atas:
        signals.append(f"ata:apu×{apu_atas}")

    # PN shape
    eng_pns = sum(1 for r in records if _ENGINE_PN_RE.match((r.get("PART_NUMBER") or "").strip()))
    apu_pns = sum(1 for r in records if _APU_PN_RE.match((r.get("PART_NUMBER") or "").strip()))
    if eng_pns:
        signals.append(f"pn-shape:engine×{eng_pns}")
    if apu_pns:
        signals.append(f"pn-shape:apu×{apu_pns}")

    # Description keywords (LG)
    lg_descs = sum(
        1 for r in records
        if _LG_DESC_KEYWORDS.search((r.get("DESCRIPTION") or ""))
    )
    if lg_descs:
        signals.append(f"desc:landing-gear-keywords×{lg_descs}")

    # Score
    eng_score = eng_hits * 2 + len(eng_modules) * 4 + eng_atas + (eng_pns >= 3) * 4
    lg_score  = lg_hits  + lg_atas * 2          + (lg_descs >= 3) * 4
    apu_score = apu_hits * 2 + apu_atas * 2     + (apu_pns >= 3) * 4

    scores = {"Engine": eng_score, "Landing Gear": lg_score, "APU": apu_score}
    winner = max(scores, key=scores.get)
    top = scores[winner]

    if top == 0:
        subject = "Other"
        confidence = "low"
    else:
        subject = winner
        # high if winner > 2 × runner-up, medium if winner > runner-up, low else
        runners = sorted(scores.values(), reverse=True)
        if len(runners) >= 2 and runners[0] >= 2 * max(runners[1], 1):
            confidence = "high"
        elif len(runners) >= 2 and runners[0] > runners[1]:
            confidence = "medium"
        else:
            confidence = "low"

    return {
        "subject": subject,
        "confidence": confidence,
        "signals": signals,
        "_scores": scores,
    }


# Convenience for callers that don't want to read the full text up-front.
def classify_for_pdf(pdf_path: str, records: list[dict]) -> dict:
    import pdfplumber
    with pdfplumber.open(pdf_path) as pdf:
        head_text = "\n".join((p.extract_text() or "") for p in pdf.pages[:3])
    return classify(head_text, records)
