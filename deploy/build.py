"""Mirror the Python modules the deployed site needs into deploy/_pymods/.

Run from the project root:

    python deploy/build.py

GitHub Pages serves static files only — the deploy folder must be self-contained.
This script copies the canonical sources under shared/, sheet_types/, and
levels/L1_text/ into deploy/_pymods/ so app.js can fetch them at runtime.

It also writes `deploy/_pymods/manifest.json` listing the files in dependency
load order. `app.js` fetches the manifest at boot and iterates it — meaning
the JS file no longer needs to be edited when modules are added/removed.
"""
from __future__ import annotations
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEPLOY = ROOT / "deploy"
TARGET = DEPLOY / "_pymods"

# Order: dependencies before dependents (low-level shared → variants →
# sheet-type routers → top-level router). Mount order doesn't actually matter
# for Python import resolution (all files must exist before any import runs),
# but this is the order a reader expects.
SOURCES = [
    # foundations
    "shared/__init__.py",
    "shared/aviation_rules.py",
    "shared/pn_master.py",
    "shared/cleanup.py",

    # variants — pure leaves, no inter-variant dependencies
    "sheet_types/__init__.py",
    "sheet_types/occm_variants/__init__.py",
    "sheet_types/occm_variants/_base.py",
    "sheet_types/occm_variants/aeroflot.py",
    "sheet_types/occm_variants/aircraft_inventory_report.py",
    "sheet_types/occm_variants/aircraft_rotables_report.py",
    "sheet_types/occm_variants/amos.py",
    "sheet_types/occm_variants/cathay_occm.py",
    "sheet_types/occm_variants/config_slot_occm.py",
    "sheet_types/occm_variants/iberia_listado.py",
    "sheet_types/occm_variants/oases.py",
    "sheet_types/occm_variants/occm_list_as_at.py",
    "sheet_types/occm_variants/occm_status_list.py",
    "sheet_types/occm_variants/on_condition_components_report.py",
    "sheet_types/occm_variants/remaining_potentials.py",
    "sheet_types/occm_variants/standard_occm.py",
    "sheet_types/occm_variants/tap_compact_occm.py",
    "sheet_types/occm_variants/technical_object_listing.py",
    # 12 OCCM variants built later in the session
    "sheet_types/occm_variants/a305_a340_occm.py",
    "sheet_types/occm_variants/a330_engineering_planning.py",
    "sheet_types/occm_variants/aegean_erj_occm.py",
    "sheet_types/occm_variants/aircraft_spec_file_occm.py",
    "sheet_types/occm_variants/avianca_occm.py",
    "sheet_types/occm_variants/b777_annex7_occm.py",
    "sheet_types/occm_variants/b777_annex8_occm.py",
    "sheet_types/occm_variants/cca_a340_occm.py",
    "sheet_types/occm_variants/msn_components_status_list.py",
    "sheet_types/occm_variants/on_condition_monitoring_occm.py",
    "sheet_types/occm_variants/sedor_b737_occm.py",
    "sheet_types/occm_variants/swiss_a340_occm.py",
    # HT variants
    "sheet_types/ht_variants/__init__.py",
    "sheet_types/ht_variants/_base.py",
    "sheet_types/ht_variants/vietnam_airlines.py",
    # LLP variants — original + 5 added this session
    "sheet_types/llp_variants/__init__.py",
    "sheet_types/llp_variants/_base.py",
    "sheet_types/llp_variants/amos.py",
    "sheet_types/llp_variants/cfm56_7b_llp.py",
    "sheet_types/llp_variants/cfm_overhaul_llp.py",
    "sheet_types/llp_variants/lan_engine_llp.py",
    "sheet_types/llp_variants/pro_rata_engine_llp.py",
    "sheet_types/llp_variants/subject.py",
    "sheet_types/llp_variants/vietnam_airlines.py",

    # sheet-type routers — depend on their variants
    "sheet_types/occm.py",
    "sheet_types/ht.py",
    "sheet_types/llp.py",

    # top-level router — depends on the three sheet-type routers
    "sheet_types/router.py",

    # extraction levels (L3/L4 are local-only and not in the deploy)
    "levels/__init__.py",
    "levels/L1_text/__init__.py",
    "levels/L1_text/extract.py",
]


def main():
    if TARGET.exists():
        shutil.rmtree(TARGET)
    TARGET.mkdir(parents=True)

    copied: list[str] = []
    for rel in SOURCES:
        src = ROOT / rel
        if not src.exists():
            print(f"  WARN: {rel} missing")
            continue
        dst = TARGET / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        copied.append(rel)
        print(f"  copied {rel}")

    # Optional bundled assets — only copied if present
    optional = [
        "shared/pn_master.bloom",          # Bloom filter for PN master cross-check
    ]
    for rel in optional:
        src = ROOT / rel
        if src.exists():
            dst = TARGET / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
            copied.append(rel)
            print(f"  copied {rel} (optional)")

    # Write a manifest that app.js consumes — fetch path + Pyodide mount path.
    # Only Python source files end up in the manifest; binary assets like
    # pn_master.bloom are loaded separately by their consumers.
    py_only = [c for c in copied if c.endswith(".py")]
    manifest = {
        "format": 1,
        "files": [
            {"fetch": f"_pymods/{rel}", "mount": rel}
            for rel in py_only
        ],
        "main_entry": {"fetch": "main.py", "mount": "main.py"},
    }
    manifest_path = TARGET / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"\nDone. Mirrored {len(copied)} files into {TARGET.relative_to(ROOT)}/")
    print(f"Manifest: {manifest_path.relative_to(ROOT)} ({len(py_only)} Python modules)")


if __name__ == "__main__":
    main()
