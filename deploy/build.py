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
    "shared/pairing.py",   # OCCM+HT combined-mode link_pair() (Phase 2)
    "shared/ocr_bridge.py",  # async render_page()/ocr_text()/ocr_words() primitives
    # tools.extract_file_metadata + tools.build_positions_db are pure-Python
    # modules that pairing.py imports for the header-parse + filename-key
    # helpers. Mirrored here so the in-browser combined mode can pair PDFs.
    # NOTE: only their importable surface is used in the browser — main()
    # of either module is not invoked under Pyodide.
    "tools/__init__.py",
    "tools/extract_file_metadata.py",
    "tools/build_positions_db.py",

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
    # OCCM variants added in the OCCM+HT session
    "sheet_types/occm_variants/elal_b767_records_package.py",
    "sheet_types/occm_variants/georgian_airways_b737.py",
    # OCCM variants added from the 2026-08-22 triage-driven build
    "sheet_types/occm_variants/aircraft_components_list.py",
    "sheet_types/occm_variants/stars_trax_occm.py",
    "sheet_types/occm_variants/sriwijaya_b737_occm.py",
    # OCCM variants added during the post-marathon corpus re-triage
    "sheet_types/occm_variants/aircraft_inventory_report_scanned.py",
    "sheet_types/occm_variants/xiamen_b737_installed_components.py",
    "sheet_types/occm_variants/aircraft_rotables_report_scanned.py",
    "sheet_types/occm_variants/occm_list_for_registration.py",
    "sheet_types/occm_variants/fl_compound_code_occm.py",
    # OCCM variant added 2026-08-26 — "TAH@INS/TAC@INS at-install" OCCM list
    "sheet_types/occm_variants/occm_tah_tac_at_install.py",
    # OCCM variant added 2026-08-27 — "OCCM LIST MSN <n>" dot-dated list
    # with a CON(dition) column
    "sheet_types/occm_variants/occm_list_msn_dotdate.py",
    "sheet_types/occm_variants/occm_report_scanned.py",
    "sheet_types/occm_variants/occm_report.py",
    "sheet_types/occm_variants/aircraft_occm_list_scanned.py",
    "sheet_types/occm_variants/occm_summary_list.py",
    # OCCM variant added 2026-08-27 — "EASTAR JET OC/CM List" scanned export
    "sheet_types/occm_variants/eastar_jet_occm_list.py",
    # OCCM variant added 2026-09-05 — "<reg> OCCM LIST - <date> AT AIRCRAFT
    # FH:" six-pair FH/CYC time-matrix export, real text layer
    "sheet_types/occm_variants/occm_list_at_aircraft_fh.py",
    # OCCM variant added 2026-09-05 — wide multi-basis (NEW/OHAU/REPA/BENC/
    # INST accumulated) per-component OCCM export, real text layer.
    "sheet_types/occm_variants/multi_basis_accumulated_occm.py",
    # OCCM variant added 2026-09-05 — "Components List" dense 3-line-per-row
    # status matrix (Plane/TS Util/CS Util header), real text layer.
    "sheet_types/occm_variants/components_list_status_matrix.py",
    # OCCM variant added 2026-09-05 — "OC/CM status <date>" header,
    # position-anchored word-bucketing parse, real text layer.
    "sheet_types/occm_variants/oc_cm_status_report.py",
    # OCCM variant added 2026-09-05 — "OCCM Report Date :" header block +
    # 10-column T@I/C@I/TSI@Today/CSI@Today time-matrix grid, real text
    # layer. Distinct from occm_report.py's own differently-titled 6-column
    # "OCCM Report" variant (confirmed via direct inspection).
    "sheet_types/occm_variants/occm_report_time_matrix.py",
    # OCCM variant added 2026-09-05 — "ON CONDITION CONDITION MONITORING
    # STATUS" / "OCCM Component List" header, two-band INSTALLATION DATA /
    # COMPONENT DATA column groups resolved by word x-position rather than
    # token count, real text layer.
    "sheet_types/occm_variants/occm_component_list.py",
    # OCCM variant added 2026-09-05 — "OC/CM status" header, rows grouped
    # under repeated "ATA <n> - <description>" section headings rather
    # than carrying ATA as an inline column, real text layer. Distinct
    # from oc_cm_status_report.py's own same-day, flat-column "OC/CM
    # status" sibling (confirmed via direct inspection) — must be listed
    # before it in sheet_types/occm.py's VARIANTS so its more specific
    # column-header signature gets first refusal.
    "sheet_types/occm_variants/occm_status_by_ata_chapter.py",
    # OCCM variant added 2026-09-05 — "ON CONDITION COMPONENTS REPORT"
    # header, dual hours/landings basis (TSN/TSI vs LSN/LSI) resolved via
    # word x-position bucketing, real text layer.
    "sheet_types/occm_variants/occm_component_status_dual_basis.py",
    # OCCM variant added 2026-09-05 — "O/C COMPONENT STATUS" header, real
    # text layer, word x-position bucketing (PN/SN/DESC/ZONE/FIN/ATA/
    # install-date/TSN/CSN/TSI-TSR/CSI-CSR/certificate columns).
    "sheet_types/occm_variants/oc_component_status.py",
    # HT variants — original + 6 added during the HT-coverage waves
    "sheet_types/ht_variants/__init__.py",
    "sheet_types/ht_variants/_base.py",
    "sheet_types/ht_variants/vietnam_airlines.py",
    "sheet_types/ht_variants/amos.py",
    "sheet_types/ht_variants/mm510.py",
    "sheet_types/ht_variants/tap.py",
    "sheet_types/ht_variants/iberia.py",
    "sheet_types/ht_variants/oases_lifed_components.py",
    "sheet_types/ht_variants/stars_trax.py",
    "sheet_types/ht_variants/aircraft_rotables_ht.py",
    # HT variants added from the 2026-08-22 triage-driven build
    "sheet_types/ht_variants/georgian_airways_ht_components_status.py",
    "sheet_types/ht_variants/mpd_hard_time_list.py",
    "sheet_types/ht_variants/htll_status.py",
    "sheet_types/ht_variants/hard_time_component_status_mpd_task.py",
    "sheet_types/ht_variants/aercap_hard_time_component_status.py",
    "sheet_types/ht_variants/aercap_oxygen_generator_status.py",
    "sheet_types/ht_variants/emes_hard_time_component_status.py",
    # HT variants added during the post-marathon corpus re-triage
    "sheet_types/ht_variants/xiamen_time_controlled_components.py",
    "sheet_types/ht_variants/aircraft_rotables_ht_scanned.py",
    "sheet_types/ht_variants/amos_scanned.py",
    "sheet_types/ht_variants/aircraft_inspection_report_scanned.py",
    "sheet_types/ht_variants/georgian_airways_ht_components_status_scanned.py",
    "sheet_types/ht_variants/hard_time_report_config_slot.py",
    "sheet_types/ht_variants/al_development_controlled_items_list.py",
    "sheet_types/ht_variants/time_controlled_components_status.py",
    "sheet_types/ht_variants/air_france_ccinv_aircraft_inventory.py",
    "sheet_types/ht_variants/activity_life_expiry_report.py",
    "sheet_types/ht_variants/time_controlled_items_status.py",
    "sheet_types/ht_variants/time_controlled_items_report.py",
    "sheet_types/ht_variants/remaining_potentials.py",
    "sheet_types/ht_variants/cognos_ht_listing.py",
    # LLP variants — original + 5 added this session
    "sheet_types/llp_variants/__init__.py",
    "sheet_types/llp_variants/_base.py",
    "sheet_types/llp_variants/amos.py",
    "sheet_types/llp_variants/cfm56_7b_llp.py",
    "sheet_types/llp_variants/cfm_overhaul_llp.py",
    "sheet_types/llp_variants/lan_engine_llp.py",
    "sheet_types/llp_variants/lan_engine_control_fleet_llp.py",
    "sheet_types/llp_variants/engine_items_control_llp_status.py",
    "sheet_types/llp_variants/pro_rata_engine_llp.py",
    "sheet_types/llp_variants/subject.py",
    "sheet_types/llp_variants/vietnam_airlines.py",
    # LLP variants added from the 2026-08-22 triage-driven build. All four
    # sibling modules originally built OCR-only that night
    # (kalstar_aviation_llp_status.py, thai_landing_gear_llp_status.py,
    # b777_gear_llp_availability.py, part_m_engine_disk_sheet.py) have now
    # been migrated to the async ocr_bridge primitives and are deploy-safe,
    # so they're all listed below with the rest.
    "sheet_types/llp_variants/erj190_landing_gear_llp.py",
    "sheet_types/llp_variants/n3_engine_overhaul_llp.py",
    "sheet_types/llp_variants/messier_dowty_landing_gear_llp.py",
    "sheet_types/llp_variants/gear_llp_status_list.py",
    "sheet_types/llp_variants/emes_airframe_llp_status.py",
    "sheet_types/llp_variants/serialized_unit_hard_limits.py",
    "sheet_types/llp_variants/cai_first_landing_gear_llp.py",
    "sheet_types/llp_variants/mm510_llp.py",
    "sheet_types/llp_variants/swiss_a340_ldg_llp.py",
    "sheet_types/llp_variants/landing_gear_llp_report.py",
    "sheet_types/llp_variants/aircraft_llp_status_report.py",
    "sheet_types/llp_variants/sas_drawing_item_llp.py",
    "sheet_types/llp_variants/sky_airlines_llp_summary.py",
    "sheet_types/llp_variants/b737_gear_llp_inventory.py",
    # LLP variant added during the post-marathon corpus re-triage
    "sheet_types/llp_variants/egat_llp_on_log_list.py",
    "sheet_types/llp_variants/ihi_engine_llp_time_cycle_record.py",
    "sheet_types/llp_variants/elal_internal_parts_list.py",
    "sheet_types/llp_variants/iai_dual_rating_engine_llp.py",
    "sheet_types/llp_variants/kalstar_engine_llp_status.py",
    "sheet_types/llp_variants/kalstar_aviation_llp_status.py",
    "sheet_types/llp_variants/thai_landing_gear_llp_status.py",
    "sheet_types/llp_variants/b777_gear_llp_availability.py",
    "sheet_types/llp_variants/part_m_engine_disk_sheet.py",
    "sheet_types/llp_variants/revima_landing_gear_als_status.py",
    "sheet_types/llp_variants/powerplant_maintenance_center_llp_status.py",
    "sheet_types/llp_variants/master_tracking_list.py",
    "sheet_types/llp_variants/aar_landing_gear_serialized_list.py",
    "sheet_types/llp_variants/turbine_acceptance_tag.py",
    "sheet_types/llp_variants/esn_disc_sheet.py",
    "sheet_types/llp_variants/oases_lifed_components_llp.py",
    "sheet_types/llp_variants/llp_pn_sn_event_log.py",
    "sheet_types/llp_variants/lta_fan_module_llp_status.py",
    "sheet_types/llp_variants/apu_llp_inventory.py",
    "sheet_types/llp_variants/sas_component_drawing_parts_list.py",
    "sheet_types/llp_variants/cf34_life_limited_major_component.py",
    "sheet_types/llp_variants/esn_llps_status.py",
    "sheet_types/llp_variants/pw4056_pw4060_dual_rating_llp_status.py",
    "sheet_types/llp_variants/engine_current_installation_llp.py",
    "sheet_types/llp_variants/engine_propeller_component_llp.py",

    # sheet-type routers — depend on their variants
    "sheet_types/occm.py",
    "sheet_types/ht.py",
    "sheet_types/llp.py",

    # top-level router — depends on the three sheet-type routers
    "sheet_types/router.py",

    # extraction levels (L4 is local-only and not in the deploy; L3's
    # extract_records_from_words() is Pyodide-safe -- fitz/pytesseract are
    # lazy-imported inside the two functions that need them, neither of
    # which the in-browser OCR path touches -- so it ships here too)
    "levels/__init__.py",
    "levels/L1_text/__init__.py",
    "levels/L1_text/extract.py",
    "levels/L3_ocr/__init__.py",
    "levels/L3_ocr/extract.py",
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
