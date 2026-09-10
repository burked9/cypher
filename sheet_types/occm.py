"""OCCM router — detects which OCCM variant a PDF is, dispatches to its parser.

Variants live under `sheet_types/occm_variants/`. Each exposes a uniform
interface (NAME, SIGNATURES, CANONICAL_COLUMNS, RULES, extract).

Public functions:
    detect_variant(pdf_path) -> str            — name of detected variant
    extract(pdf_path) -> dict                  — {variant, columns, records}
    normalize_and_validate(records, variant)   — apply per-variant rules
"""
from __future__ import annotations
import re
import pdfplumber

from sheet_types.occm_variants import (
    a330_engineering_planning, aegean_erj_occm, avianca_occm,
    b777_annex7_occm, b777_annex8_occm,
    cca_a340_occm, swiss_a340_occm, a305_a340_occm, on_condition_monitoring_occm,
    msn_components_status_list, sedor_b737_occm, elal_b767_records_package,
    georgian_airways_b737,
    aeroflot, aircraft_inventory_report, aircraft_rotables_report,
    aircraft_spec_file_occm, amos,
    cathay_occm, config_slot_occm, iberia_listado, oases,
    occm_list_as_at, occm_status_list, on_condition_components_report,
    remaining_potentials, standard_occm, tap_compact_occm, technical_object_listing,
    aircraft_components_list, stars_trax_occm, sriwijaya_b737_occm,
    aircraft_inventory_report_scanned, xiamen_b737_installed_components,
    aircraft_rotables_report_scanned, occm_list_for_registration,
    fl_compound_code_occm, occm_tah_tac_at_install, occm_report_scanned,
    occm_report, aircraft_occm_list_scanned,
    occm_summary_list, occm_list_msn_dotdate,
    eastar_jet_occm_list, occm_list_at_aircraft_fh,
    multi_basis_accumulated_occm, components_list_status_matrix,
    occm_report_time_matrix, oc_cm_status_report,
    occm_component_list, occm_status_by_ata_chapter,
    occm_component_status_dual_basis, oc_component_status,
    occm_dual_description_list, occm_part_status,
    occm_control_sheet, all_fitted_aircraft_component_log,
    occm_component_inventory, occm_listing,
    occm_component_status_facility_msn,
    occm_component_data_install_current,
    occm_component_ac_corrected_at_install,
    serialized_component_list,
    installed_parts_list,
    serialization_list_by_ata,
    occm_index,
    assembly_configuration_status_report,
    maintenance_status_report_pr21,
    component_list_kardex,
    aircraft_installed_parts_print,
    occm_components_status,
    occm_list_cert_remark,
    oc_cm_components_install_current,
    aircraft_occm_list_hcd,
    occm_components_control_sma,
    on_condition_monitoring_components,
    occm_component_status_report,
    component_fit_list,
    serialised_components_report,
    occm_uic_status,
    condition_monitoring_components_status,
    on_condition_components_install_current,
    aircraft_fitlist_occm,
    occm_list_func_loc_scanned,
    occm_component_inventory_list_scanned,
    occm_status_on_condition_items,
    component_list_occm_airframe,
    componentes_oc_cm,
    msn_occm_list_scanned,
    on_condition_cm_components_list,
    on_condition_components_list_tt_tc,
    occm_parts_compliance_status,
    on_component_monitoring_listing_status,
    occm_inventory_sap_es,
    occm_component_status_parent_serial_grid,
    occm_status_list_type_model_header,
    aircraft_build_occm_status_boxed_header_scanned,
    aircraft_build_occm_status_scanned,
    aircraft_build_occm_status_rotated_scanned,
    aircraft_occm_components_status_scanned,
    on_condition_monitored_components_engine_list,
    on_condition_component_status_scanned,
    component_inventory_oc_cm_status_scanned,
    occm_status_aircraft_info_box,
    component_localization_list,
    occm_component_status_posn_fin,
    occm_components_status_ruled_grid,
    emb190_occm_status_list_ruled_grid,
    aircraft_installed_parts_list_scanned,
    occm_list_current_fh_fc_ruled_grid,
    aircraft_kardex_status_broken_font_scanned,
    occm_list_pn_description_rotated_scanned,
)
from shared.cleanup import clean_record, forward_fill_ata
from shared.ocr_bridge import maybe_await

# Specific-format variants must precede generic ones: detection returns the
# first match. Specific airframe/operator variants are listed first.
VARIANTS = [
    aircraft_spec_file_occm,
    all_fitted_aircraft_component_log,
    aegean_erj_occm,
    a330_engineering_planning,
    avianca_occm,
    b777_annex8_occm,
    b777_annex7_occm,
    cca_a340_occm,
    swiss_a340_occm,
    a305_a340_occm,
    occm_part_status,
    occm_component_inventory,
    on_condition_monitoring_occm,
    msn_components_status_list,
    sedor_b737_occm,
    elal_b767_records_package,
    georgian_airways_b737,
    fl_compound_code_occm,
    occm_tah_tac_at_install,
    occm_list_msn_dotdate,
    occm_component_status_facility_msn,
    aeroflot, aircraft_inventory_report, aircraft_rotables_report, amos,
    cathay_occm, config_slot_occm, iberia_listado, oases,
    occm_list_as_at, occm_status_list, on_condition_components_report,
    remaining_potentials, standard_occm, tap_compact_occm, technical_object_listing,
    aircraft_components_list, stars_trax_occm, sriwijaya_b737_occm,
    aircraft_inventory_report_scanned, xiamen_b737_installed_components,
    aircraft_rotables_report_scanned, occm_list_for_registration,
    occm_report, occm_report_scanned, aircraft_occm_list_scanned,
    occm_summary_list, eastar_jet_occm_list,
    occm_list_at_aircraft_fh,
    multi_basis_accumulated_occm,
    components_list_status_matrix,
    occm_report_time_matrix,
    # occm_status_by_ata_chapter.py MUST precede oc_cm_status_report.py:
    # both known source files share the same "OC/CM status" front-matter
    # line, but oc_cm_status_report.py's own SIGNATURES entry is that
    # generic phrase (matching either file), while this module's is the
    # more specific column-header line unique to its own format (see its
    # module docstring) -- so it needs the earlier slot per this file's
    # "specific formats before generic ones" convention, or its own real
    # files would get mis-routed to oc_cm_status_report.py first.
    occm_status_by_ata_chapter,
    oc_cm_status_report,
    occm_component_list,
    occm_component_status_dual_basis,
    oc_component_status,
    occm_dual_description_list,
    occm_control_sheet,
    occm_listing,
    # occm_component_ac_corrected_at_install.py MUST precede
    # occm_component_data_install_current.py: both known source files share
    # the literal header phrase "Component Data at Install" (confirmed
    # directly), but occm_component_data_install_current.py's own
    # SIGNATURES entry is that exact shared phrase (matching either file),
    # while this earlier module's own SIGNATURES entries ("Corrected A/C
    # Data at Install", "Posi (May be differ with A/C Log)") are unique,
    # more specific phrases confirmed NOT present in the other module's
    # known source file -- so it needs the earlier slot per this file's
    # "specific formats before generic ones" convention, or its own real
    # files would get mis-routed to occm_component_data_install_current.py
    # first (confirmed directly: detect_variant() returns the wrong module
    # without this ordering).
    occm_component_ac_corrected_at_install,
    occm_component_data_install_current,
    serialized_component_list,
    installed_parts_list,
    serialization_list_by_ata,
    occm_index,
    assembly_configuration_status_report,
    maintenance_status_report_pr21,
    # component_list_kardex.py's known source file's title reads literally
    # "COMPONENT LIST" -- a generic phrase, so it's placed near the end of
    # this list (after every more-specific format) to minimise the risk of
    # it stealing a real file that belongs to an earlier, more specific
    # variant. Checked directly: no earlier variant's own SIGNATURES phrase
    # appears in the real sample file's text, and this phrase does not
    # appear as a substring of (nor contain as a substring) any other
    # variant's SIGNATURES entries checked.
    component_list_kardex,
    # A/C Installed Parts Print — its known source file's title line reads
    # literally "A/C Installed Parts Print" (a distinctive, specific
    # phrase), so it's safe to place near the other specific-format
    # variants rather than at the very end. Checked directly: no earlier
    # variant's own SIGNATURES phrase appears in the real sample file's
    # text, and this phrase does not appear as a substring of (nor
    # contain as a substring) any other variant's SIGNATURES entries.
    aircraft_installed_parts_print,
    # OCCM Components Status — its own variant-level SIGNATURES entry is
    # the column-header line "ATA Description P/N S/N Position Date TTSN
    # TCSN TSI CSI Document" (a distinctive, specific phrase; the report's
    # own title text "OCCM COMPONENTS STATUS" is a prefix substring of
    # occm_status_list.py's "OCCM COMPONENTS STATUS LIST" signature above,
    # so the title text alone is NOT used here to avoid stealing that
    # variant's files). Checked directly: no earlier variant's own
    # SIGNATURES phrase appears in the real sample file's text, and this
    # phrase does not appear as a substring of (nor contain as a
    # substring) any other variant's SIGNATURES entries checked.
    occm_components_status,
    # OC/CM Components (Installation / Current) -- its own variant-level
    # SIGNATURES entries ("AIRCRAFT REG. :", "MFD :") are distinctive
    # phrases unique to its own known source file. Checked directly: no
    # earlier variant's own SIGNATURES phrase appears in the real sample
    # file's text, and neither of these phrases appears as a substring of
    # (nor contains as a substring) any other variant's SIGNATURES entries
    # checked, including occm_component_data_install_current.py and
    # occm_component_ac_corrected_at_install.py above.
    oc_cm_components_install_current,
    # OCCM List (Certificate/Remark) -- its variant-level SIGNATURES entry
    # is the column-header line "Part No. Serial No. INST_DATE TSN CSN
    # Certificate Remark", a distinctive, specific phrase unique to this
    # module's own known source file. Checked directly: no earlier
    # variant's own SIGNATURES phrase appears in the real sample file's
    # text (in particular, occm_list_as_at.py's "OCCM LIST AS AT",
    # occm_list_for_registration.py's "OCCM LIST FOR",
    # occm_list_msn_dotdate.py's "OCCM LIST MSN", and
    # aircraft_components_list.py's "...INST_DATE TSN CSN" phrase are all
    # NOT substrings of this module's own signature or vice versa), and
    # this phrase does not appear as a substring of (nor contain as a
    # substring) any other variant's SIGNATURES entries checked.
    occm_list_cert_remark,
    # Aircraft OCCM List (H/C/D Basis) -- its own variant-level SIGNATURES
    # entries are the two real column-header lines ("Zone ATA POS1 P/N S/N
    # Inst. Date Parts Name NHA P/N NHA S/N Originator" and "TSI TST TSO
    # TSN TTR TCI Limit Limit Type T/C# TASK Repairer # CERT # SER.DATE
    # Task Note"), distinctive phrases unique to this module's own known
    # source file. Checked directly (grep across every SIGNATURES list in
    # sheet_types/{occm,ht,llp}.py and every existing occm_variants file):
    # neither phrase appears anywhere else, and doesn't contain (nor is
    # contained by) any other variant's own SIGNATURES entries.
    aircraft_occm_list_hcd,
    # OCCM Components Control (S.M.A. PASCOM1R) -- its own variant-level
    # SIGNATURES entries ("PASCOM1R", "COMPONENTS CONTROL", and the real
    # column-header line "Install. Date Map Description Pos P/N S/N TSN CSN
    # TSI CSI TSO CSO TSR CSR TLP") are distinctive phrases unique to this
    # module's own known source file. Checked directly (grep across every
    # SIGNATURES list in sheet_types/{occm,ht,llp}.py and every existing
    # occm_variants file): none of these phrases appear anywhere else, and
    # none is a substring of (nor contains) any other variant's own
    # SIGNATURES entries.
    occm_components_control_sma,
    # On Condition Monitoring Components -- its own variant-level SIGNATURES
    # entry ("ON CONDITION MONITORING COMPONENTS") is a distinctive phrase
    # unique to this module's own known source file's title line. Checked
    # directly (grep across every SIGNATURES list in sheet_types/
    # {occm,ht,llp}.py and every existing occm_variants/ht_variants/
    # llp_variants file): the phrase appears nowhere else, and is not a
    # substring of (nor contains) any other variant's own SIGNATURES
    # entries -- in particular occm_component_status_dual_basis.py's own
    # title phrase "ON CONDITION COMPONENTS REPORT" (no "MONITORING") is
    # distinct in both directions.
    on_condition_monitoring_components,
    # OCCM Component Status Report -- its own variant-level SIGNATURES entry
    # ("OCCM COMPONENT STATUS", singular "COMPONENT") is a distinctive
    # phrase unique to this module's own known source file's title line.
    # Checked directly (grep across every SIGNATURES list in sheet_types/
    # {occm,ht,llp}.py and every existing occm_variants/ht_variants/
    # llp_variants file): the exact phrase "OCCM COMPONENT STATUS" appears
    # nowhere else -- in particular occm.py's own top-level "OCCM COMPONENTS
    # STATUS LIST" entry and occm_components_status.py's own SIGNATURES
    # (plural "COMPONENTS") do NOT contain this singular phrase as a
    # substring (the character after "COMPONENT" differs, "S" vs " "), so
    # no collision risk in either direction.
    occm_component_status_report,
    # Component Fit List -- its own variant-level SIGNATURES entry
    # ("COMPONENT FIT LIST") is a distinctive phrase unique to this
    # module's own known source file's title line. Checked directly (grep
    # across every SIGNATURES list in sheet_types/{occm,ht,llp}.py and
    # every existing occm_variants/ht_variants/llp_variants file): the
    # phrase appears nowhere else, and is not a substring of (nor
    # contains) any other variant's own SIGNATURES entries.
    component_fit_list,
    # Serialised Components Report -- its own variant-level SIGNATURES
    # entry ("serialised components report") is the report's own title
    # line, a distinctive phrase unique to this module's own known source
    # file (confirmed via direct inspection -- no "OCCM" text anywhere in
    # it). Checked directly (grep across every SIGNATURES list in
    # sheet_types/{occm,ht,llp}.py and every existing occm_variants/
    # ht_variants/llp_variants file): the phrase appears nowhere else, and
    # is not a substring of (nor contains) any other variant's own
    # SIGNATURES entries.
    serialised_components_report,
    # OCCM UIC Status -- its own variant-level SIGNATURES entry ("OCCMUIC")
    # is the report's own aircraft-summary line ("OCCMUIC <reg> (MSN <msn>),
    # TSN: ..., CSN: ...", confirmed to render with "OCCM" and "UIC" glued
    # together, no space, on this module's own known source file's first
    # page). Checked directly (grep across every SIGNATURES list in
    # sheet_types/{occm,ht,llp}.py and every existing occm_variants/
    # ht_variants/llp_variants file): the phrase appears nowhere else, and
    # is not a substring of (nor contains) any other variant's own
    # SIGNATURES entries.
    occm_uic_status,
    # Condition Monitoring Components Status -- its own variant-level
    # SIGNATURES entry ("CONDITION MONITORING COMPONENTS STATUS") is the
    # report's own title-line phrase (confirmed to render contiguously on
    # this module's own known source file's first page, despite heavy
    # surrounding character-substitution noise elsewhere in that line).
    # Checked directly (grep across every SIGNATURES list in
    # sheet_types/{occm,ht,llp}.py and every existing occm_variants/
    # ht_variants/llp_variants file): the phrase appears nowhere else --
    # in particular on_condition_monitoring_components.py's own phrase
    # "ON CONDITION MONITORING COMPONENTS" (leading "ON", no "STATUS"
    # suffix) is NOT a substring of this phrase nor vice versa.
    condition_monitoring_components_status,
    # On-Condition Components Report (Install / Current) -- its own
    # variant-level SIGNATURES entries are the paired-column group label
    # line ("INSTALLATION DATA CURRENT DATA (<date>)") and the report's own
    # column-header line ("## ATA PN SN DESCRIPTION POS INST Date TAH TAC
    # TSN CSN TSI CSI"), both distinctive phrases confirmed unique to this
    # module's own known source file. Note this module's title line reads
    # literally "On-Condition Components Report" (hyphenated, mixed case)
    # -- deliberately NOT used as a SIGNATURES entry here, since it is NOT
    # the same string as occm_component_status_dual_basis.py's own title
    # phrase "ON CONDITION COMPONENTS REPORT" (all-caps, no hyphen) is a
    # substring of, or contains -- confirmed directly, the hyphen makes the
    # two strings differ at the second character, so neither is a
    # substring of the other, but the title text alone was still avoided
    # as the anchor here in favour of the two more specific phrases above.
    # Checked directly (grep across every SIGNATURES list in
    # sheet_types/{occm,ht,llp}.py and every existing occm_variants/
    # ht_variants/llp_variants file): neither phrase appears anywhere else,
    # and neither is a substring of (nor contains) any other variant's own
    # SIGNATURES entries.
    on_condition_components_install_current,
    # Aircraft Fitlist (OCCM) -- known source file has no text layer at all
    # (confirmed via pdfplumber -- near-zero chars on every page), so it is
    # only ever reached via ocr_detect()'s blank-text fallback below, never
    # through the normal pdfplumber SIGNATURES match. Its own variant-level
    # SIGNATURES ("AIRCRAFT FITLIST (OCCM)" and the column-header phrase
    # "PART NUMBER SERIAL NUMBER POSITION INST-DATE") are still declared,
    # per this file's convention, as a documented anchor / safety net for
    # any future born-digital re-export. Checked directly (grep across
    # every SIGNATURES list in sheet_types/{occm,ht,llp}.py and every
    # existing occm_variants/ht_variants/llp_variants file, including every
    # module added in this same batch): neither phrase appears anywhere
    # else, and neither is a substring of (nor contains) any other
    # variant's own SIGNATURES entries.
    aircraft_fitlist_occm,
    # On Condition Items (OCCM Status) -- known source file has no text
    # layer at all (confirmed via the router's own pdfplumber head-text
    # check returning "Unknown" -- fewer than 50 chars recovered), so it is
    # only ever reached via ocr_detect()'s blank-text fallback below. Its
    # own variant-level SIGNATURES ("ON CONDITION ITEMS" and the
    # column-header fragment "Partno | Serialno | Description") are still
    # declared, per this file's convention, as a documented anchor / safety
    # net for any future born-digital re-export. Checked directly (grep
    # across every SIGNATURES list in sheet_types/{occm,ht,llp}.py and
    # every existing occm_variants file): neither phrase appears anywhere
    # else, and neither is a substring of (nor contains) any other
    # variant's own SIGNATURES entries.
    occm_status_on_condition_items,
    # OCCM List (Func.loc / A/C Hours Header) -- known source file has no
    # text layer at all (confirmed via pdfplumber -- 0 chars on every
    # page), so it is only ever reached via ocr_detect()'s blank-text
    # fallback below; SIGNATURES is deliberately empty (see module
    # docstring). Its ocr_detect() anchor ("OCCM LIST A/C HOURS") is a more
    # specific phrase than the bare "OCCM LIST" substring shared by
    # occm_list_msn_dotdate.py/occm_list_as_at.py/occm_list_for_registration.py
    # (see occm_list_at_aircraft_fh.py's own docstring note on that
    # collision) -- checked directly (grep across every SIGNATURES list in
    # sheet_types/{occm,ht,llp}.py and every existing occm_variants file,
    # aircraft_fitlist_occm.py included): the fuller phrase appears nowhere
    # else.
    occm_list_func_loc_scanned,
    # Component Inventory List (Func.loc / A/C Hours Header, Wide) -- known
    # source file has no text layer at all (confirmed via pdfplumber -- 0
    # chars on every page), so it is only ever reached via ocr_detect()'s
    # blank-text fallback below; SIGNATURES is deliberately empty (see
    # module docstring). Its ocr_detect() anchor ("COMPONENT INVENTORY
    # LIST" + "A/C HOURS") is checked directly (grep across every
    # SIGNATURES list in sheet_types/{occm,ht,llp}.py and every existing
    # occm_variants file, occm_list_func_loc_scanned.py and
    # occm_component_inventory.py included): the combined phrase appears
    # nowhere else, and it does not collide with
    # occm_list_func_loc_scanned.py's own "OCCM LIST A/C HOURS" anchor
    # (the title words themselves differ).
    occm_component_inventory_list_scanned,
    # Component List OCCM- Airframe -- known source file has no text layer
    # at all (confirmed via pdfplumber -- 0 chars on every page), so it is
    # only ever reached via ocr_detect()'s blank-text fallback below. Its
    # own variant-level SIGNATURES entry (the report's own title line,
    # "COMPONENT LIST OCCM- AIRFRAME") is still declared, per this file's
    # convention, as a documented anchor / safety net for any future
    # born-digital re-export. Checked directly (grep across every
    # SIGNATURES list in sheet_types/{occm,ht,llp}.py and every existing
    # occm_variants file): no other module's own SIGNATURES entry contains
    # "AIRFRAME" combined with "COMPONENT LIST", and this phrase is not a
    # substring of (nor contains) any of them -- in particular
    # component_list_kardex.py's own generic "COMPONENT LIST" phrase IS a
    # substring of this fuller title (by design, see that module's own
    # docstring on why it's generic and placed near the end of this list;
    # this module's detection never goes through that generic entry since
    # its known source file has no text layer for the pdfplumber path to
    # match against in the first place).
    component_list_occm_airframe,
    # COMPONENTES OC/CM -- known source file has no text layer at all
    # (confirmed via pdfplumber -- 0 chars on every page), so it is only
    # ever reached via ocr_detect()'s blank-text fallback below; SIGNATURES
    # is deliberately empty (see module docstring). Its ocr_detect() anchor
    # ("COMPONENTES" + "OC/CM") is checked directly (grep across every
    # SIGNATURES list in sheet_types/{occm,ht,llp}.py and every existing
    # occm_variants/ht_variants/llp_variants file): "COMPONENTES" (Spanish
    # spelling) appears nowhere else in this package, and is not a
    # substring of (nor contains) any other variant's own SIGNATURES
    # entries -- in particular a305_a340_occm.py's own "Components >> OC/CM
    # Components" phrase (English spelling) differs at the first
    # distinguishing letter in both directions.
    componentes_oc_cm,
    # OCCM List (MSN-Prefixed Title, Scanned) -- known source file has no
    # text layer at all (confirmed via pdfplumber -- 0 chars on every
    # page), so it is only ever reached via ocr_detect()'s blank-text
    # fallback below; SIGNATURES is deliberately empty (see module
    # docstring). Its ocr_detect() anchor ("MSN<n> OCCM LIST", no space
    # between "MSN" and the digit run) is checked directly (grep across
    # every SIGNATURES list in sheet_types/{occm,ht,llp}.py and every
    # existing occm_variants/ht_variants/llp_variants file): no other
    # module's own SIGNATURES/ocr_detect anchor combines the literal
    # substring "MSN" immediately (no space) followed by digits and then
    # "OCCM" -- in particular occm_component_inventory.py's own title
    # ("MSN <n> OCCM COMPONENT INVENTORY") and occm_summary_list.py's own
    # title ("OCCM SUMMARY LIST MSN <n>") both differ, the former by the
    # space after "MSN" and by what follows "OCCM", the latter by placing
    # "OCCM" before "MSN" entirely.
    msn_occm_list_scanned,
    # On Condition, Condition Monitoring Components List -- known source
    # file has no text layer at all (confirmed via pdfplumber -- 0 chars on
    # its only page), so it is only ever reached via ocr_detect()'s
    # blank-text fallback below; SIGNATURES is deliberately empty (see
    # module docstring). Its ocr_detect() anchor (the title line's own
    # leading "ON CONDITION," comma plus "CONDITION MONITORING COMPONENTS"
    # plus a trailing "LIST", not "STATUS") is checked directly (grep
    # across every SIGNATURES list in sheet_types/{occm,ht,llp}.py and
    # every existing occm_variants/ht_variants/llp_variants file, this same
    # batch's siblings included): no other module's own SIGNATURES/
    # ocr_detect anchor combines all three of those -- in particular
    # on_condition_monitoring_components.py's own title phrase has no
    # leading comma and no trailing "LIST", and
    # condition_monitoring_components_status.py's own title phrase has no
    # leading "ON" and ends in "STATUS" not "LIST".
    on_condition_cm_components_list,
    # On Condition Components List (T.T./T.C. Header) -- known source file
    # has no text layer at all (confirmed via pdfplumber -- 0 chars on
    # every page sampled), so it is only ever reached via ocr_detect()'s
    # blank-text fallback below; SIGNATURES is deliberately empty (see
    # module docstring). Its ocr_detect() anchor ("ON CONDITION COMPONENTS
    # LIST") is checked directly (grep across every SIGNATURES list in
    # sheet_types/{occm,ht,llp}.py and every existing occm_variants file,
    # this batch's own on_condition_cm_components_list.py included): the
    # bare phrase appears nowhere else -- in particular
    # on_condition_cm_components_list.py's own anchor requires an extra
    # leading "ON CONDITION," comma and "CONDITION MONITORING" insert not
    # present here, so `detect_variant()` cannot route this module's real
    # sample file to that earlier variant nor vice versa (confirmed
    # directly: `detect_variant()` returned "Unknown" against this
    # module's own real sample file before it existed).
    on_condition_components_list_tt_tc,
    # OCCM Parts Compliance Status Report -- known source file has no text
    # layer at all (confirmed via pdfplumber -- 0 chars on every page), so
    # it is only ever reached via ocr_detect()'s blank-text fallback below;
    # SIGNATURES is deliberately empty (see module docstring). Its
    # ocr_detect() anchor ("OCCM PARTS COMPLIANCE STATUS REPORT") is
    # checked directly (grep across every SIGNATURES list in
    # sheet_types/{occm,ht,llp}.py and every existing occm_variants file,
    # this same batch's siblings included): the phrase "PARTS COMPLIANCE"/
    # "COMPLIANCE STATUS" appears nowhere else, and is not a substring of
    # (nor contains) any other variant's own SIGNATURES/ocr_detect anchor.
    occm_parts_compliance_status,
    # On-Component/ Component Monitoring Listing Status -- known source file
    # has no text layer at all (confirmed via pdfplumber -- 0 chars on every
    # page), so it is only ever reached via ocr_detect()'s blank-text
    # fallback below; SIGNATURES is deliberately empty (see module
    # docstring). Its ocr_detect() anchor ("COMPONENT MONITORING LISTING
    # STATUS") is checked directly (grep across every SIGNATURES list in
    # sheet_types/{occm,ht,llp}.py and every existing occm_variants/
    # ht_variants/llp_variants file): the phrase appears nowhere else, and
    # is not a substring of (nor contains) any other variant's own
    # SIGNATURES/ocr_detect anchor.
    on_component_monitoring_listing_status,
    # OCCM Inventory (Spanish SAP-style header) -- its own variant-level
    # SIGNATURES entry is the exact Spanish column-header line
    # "Ubicac.técnica Denominación Material Número de serie Válido de",
    # a distinctive phrase unique to this module's own known source file.
    # Checked directly (grep across every SIGNATURES list in
    # sheet_types/{occm,ht,llp}.py and every existing occm_variants file):
    # no accent-insensitive substring match ("ubicac", "denominaci",
    # "valido de", "numero de serie") appears anywhere else, and this
    # phrase does not contain (nor is contained by) any other variant's
    # own SIGNATURES entries.
    occm_inventory_sap_es,
    # OCCM Component Status (Parent Serial / TSN-CSN Grid, Scanned) -- known
    # source file has no text layer at all (0 chars via pdfplumber on every
    # page), so it is only ever reached via ocr_detect()'s blank-text
    # fallback below; SIGNATURES is deliberately empty (see module
    # docstring). Its own title line ("OCCM COMPONENT STATUS") is shared
    # with occm_component_status_report.py's SIGNATURES entry, but that
    # module is reached only via the pdfplumber text-match path above (its
    # own known source file has a real, if corrupted, text layer) and
    # never via ocr_detect(), so the two cannot collide on the same file.
    # This module's own ocr_detect() anchor ("PARENT SERIAL") is checked
    # directly (grep across every SIGNATURES list in
    # sheet_types/{occm,ht,llp}.py and every existing occm_variants/
    # ht_variants/llp_variants file): the phrase appears nowhere else, and
    # is not a substring of (nor contains) any other variant's own
    # SIGNATURES/ocr_detect anchor.
    occm_component_status_parent_serial_grid,
    # OCCM Status List (Type/Model Header, Scanned) -- known source file's
    # title/header page and closing page are scanned (no text layer at
    # all, confirmed via pdfplumber), so it is only ever reached via
    # ocr_detect()'s blank-text fallback below; SIGNATURES is declared
    # ("OCCM STATUS LIST") as a documented anchor / safety net for any
    # future born-digital re-export only. Checked directly (grep across
    # every SIGNATURES list in sheet_types/{occm,ht,llp}.py and every
    # existing occm_variants/ht_variants/llp_variants file): "OCCM STATUS
    # LIST" is not a substring of (nor contains) occm_status_list.py's own
    # "OCCM COMPONENTS STATUS LIST" / "COMPONENTS STATUS LIST" entries (the
    # word "COMPONENTS" sits between "OCCM" and "STATUS" there but not
    # here), and appears nowhere else in this package.
    occm_status_list_type_model_header,
    # Aircraft Build OCCM Status (Boxed Header Scan) -- same underlying
    # report template and data-grid layout as the sibling module directly
    # below, but its own known source file's identity metadata renders as a
    # genuine shaded two-row table rather than that sibling's own plain OCR
    # text line (confirmed directly, see module docstring). Placed ahead of
    # both "Aircraft Build" siblings per this file's "specific formats
    # before generic ones" convention: this module's own ocr_detect()
    # requires the confirmed-distinctive shaded "Aircraft Reg" label row in
    # addition to the shared "AIRCRAFT BUILD" title anchor, so it cannot
    # steal either sibling's own known source file (neither carries that
    # boxed label row, confirmed directly) -- but ordering still matters so
    # a file satisfying more than one module's own ocr_detect is resolved
    # to the more specific check here rather than falling through to a
    # sibling's plain-line header parser, which was confirmed directly to
    # stamp unrelated OCR noise onto every row of this module's own known
    # source file. SIGNATURES is deliberately empty (see module docstring);
    # only ever reached via ocr_detect()'s blank-text fallback below.
    # Checked directly (grep across every SIGNATURES list in
    # sheet_types/{occm,ht,llp}.py and every existing occm_variants/
    # ht_variants/llp_variants file): no other module's own SIGNATURES/
    # ocr_detect anchor is the bare "AIRCRAFT BUILD" phrase.
    aircraft_build_occm_status_boxed_header_scanned,
    # Aircraft Build OCCM Status (Scanned) -- known source file has no text
    # layer at all (0 chars via pdfplumber on every page), so it is only
    # ever reached via ocr_detect()'s blank-text fallback below; SIGNATURES
    # is deliberately empty (see module docstring). Shares its "Aircraft
    # Build" header phrase and Since-New/Fit/Overhaul/Repair matrix with
    # oases.py's own SIGNATURES entries, but oases.py has no ocr_detect() of
    # its own (pdfplumber-only) and this module's SIGNATURES is empty, so
    # the two cannot collide on the pdfplumber-text match path OR the
    # ocr_detect fallback loop. Confirmed directly on the real sample file:
    # `occm.detect_variant()` returned "Unknown" before this module existed.
    # Checked directly (grep across every SIGNATURES list in
    # sheet_types/{occm,ht,llp}.py and every existing occm_variants/
    # ht_variants/llp_variants file): no other module's own SIGNATURES/
    # ocr_detect anchor is the bare "AIRCRAFT BUILD" phrase.
    aircraft_build_occm_status_scanned,
    # Aircraft Build OCCM Status (Rotated Scan) -- same underlying report
    # template as the sibling module just above, but its own known source
    # file stores every page portrait-shaped with the content drawn
    # sideways (no `/Rotate` flag set -- a scan/export artifact, confirmed
    # directly by rendering the real sample file). SIGNATURES is
    # deliberately empty (see module docstring); only ever reached via
    # ocr_detect()'s blank-text fallback below. Its own ocr_detect() only
    # fires when the page-1 render is portrait-shaped (width < height),
    # which the sibling module's own already-landscape source is not, and
    # the sibling's own ocr_detect() was confirmed directly to return
    # False on this module's sideways-page sample file (its unrotated
    # header crop OCRs to noise, never "AIRCRAFT BUILD") -- so the two
    # cannot collide. Checked directly (grep across every SIGNATURES list
    # in sheet_types/{occm,ht,llp}.py and every existing occm_variants/
    # ht_variants/llp_variants file): no other module's own SIGNATURES/
    # ocr_detect anchor is the bare "AIRCRAFT BUILD" phrase.
    aircraft_build_occm_status_rotated_scanned,
    # Aircraft OC/CM Components Status (Scanned) -- known source file has
    # no text layer at all (0 chars via pdfplumber on every page sampled),
    # so it is only ever reached via ocr_detect()'s blank-text fallback
    # below; SIGNATURES is deliberately empty (see module docstring).
    # Confirmed directly on the real sample file: `occm.detect_variant()`
    # returned "Unknown" before this module existed. Its own ocr_detect()
    # anchor is the bare title phrase "AIRCRAFT OC/CM COMPONENTS STATUS",
    # checked directly (grep across every SIGNATURES list in
    # sheet_types/{occm,ht,llp}.py and every existing occm_variants/
    # ht_variants/llp_variants file): no other module's own SIGNATURES/
    # ocr_detect anchor is this phrase, nor a substring of it, nor does it
    # contain any other module's own anchor.
    aircraft_occm_components_status_scanned,
    # On-Condition Monitored Components List (Engine, Scanned) -- its known
    # source file has no text layer at all (confirmed via pdfplumber -- 0
    # chars on every page of its own report section), so it is only ever
    # reached via ocr_detect()'s blank-text fallback below; SIGNATURES is
    # deliberately empty (see module docstring). Its own ocr_detect()
    # anchor is the report's own generic title phrase "ON-CONDITION
    # MONITORED COMPONENTS LIST - <LH or RH> ENGINE" (no organization name,
    # per this project's data-sensitivity convention), checked directly
    # (grep across every SIGNATURES list in sheet_types/{occm,ht,llp}.py
    # and every existing occm_variants/ht_variants/llp_variants file): no
    # other module's own SIGNATURES/ocr_detect anchor is this phrase, nor a
    # substring of it, nor does it contain any other module's own anchor.
    on_condition_monitored_components_engine_list,
    # Component Inventory (OC/CM Status, Scanned) -- known source file has
    # no text layer at all (0 chars via pdfplumber on every page), so it is
    # only ever reached via ocr_detect()'s blank-text fallback below;
    # SIGNATURES is deliberately empty (see module docstring). Its
    # ocr_detect() anchor combines "COMPONENT INVENTORY" with the
    # space-tolerant "OC / CM" title fragment -- checked directly (grep
    # across every SIGNATURES list in sheet_types/{occm,ht,llp}.py and
    # every existing occm_variants file, occm_component_inventory.py,
    # occm_component_inventory_list_scanned.py and componentes_oc_cm.py
    # included): no other module's own SIGNATURES/ocr_detect anchor
    # combines both of those (see this module's own ocr_detect() docstring
    # for the specific distinctions checked against each).
    component_inventory_oc_cm_status_scanned,
    # On-Condition Component Status (Boeing 767 Specification Sheet,
    # Scanned) -- known source file has no text layer at all (confirmed
    # via pdfplumber -- 0 extractable chars/words/rects on every page), so
    # it is only ever reached via ocr_detect()'s blank-text fallback below.
    # Its own variant-level SIGNATURES entries ("BOEING 767 SPECIFICATION
    # SHEET" and "On-Condition Component Status") are still declared, per
    # this file's convention, as a documented anchor / safety net for any
    # future born-digital re-export. Checked directly (grep across every
    # SIGNATURES list in sheet_types/{occm,ht,llp}.py and every existing
    # occm_variants/ht_variants/llp_variants file, this batch's siblings
    # included): neither phrase appears anywhere else, and neither is a
    # substring of (nor contains) any other variant's own SIGNATURES
    # entries.
    on_condition_component_status_scanned,
    # OCCM Status (Aircraft Information Box, Scanned) -- known source file
    # has no text layer at all (confirmed via pdfplumber -- 0 chars on
    # every page), so it is only ever reached via ocr_detect()'s blank-text
    # fallback below; SIGNATURES is deliberately empty (see module
    # docstring). Its ocr_detect() anchor requires BOTH the report's own
    # title phrase ("OCCM STATUS") and its info-box's own title-cell phrase
    # ("AIRCRAFT INFORMATION") together. "OCCM STATUS" alone is also
    # standard_occm.py's own SIGNATURES entry, but that module is a
    # born-digital variant reached only through the router's pdfplumber
    # text-match path above (its own known source file has a real text
    # layer), so it can never reach this module's ocr_detect() fallback on
    # the same file -- same reasoning documented in
    # occm_component_status_parent_serial_grid.py's own docstring for its
    # analogous "OCCM COMPONENT STATUS" case. "AIRCRAFT INFORMATION" is
    # checked directly (grep across every SIGNATURES list in
    # sheet_types/{occm,ht,llp}.py and every existing occm_variants file,
    # this module's own siblings included): appears nowhere else in this
    # package.
    occm_status_aircraft_info_box,
    # Component Localization List -- its own variant-level SIGNATURES entries
    # ("AIRPLANE MODEL:", "AIRPLANE SERIAL NUMBER:", "LOCALIZATION") are the
    # report's own aircraft-summary field labels and repeating column-header
    # word, distinctive phrases unique to this module's own known source
    # file. Checked directly (grep across every SIGNATURES list in
    # sheet_types/{occm,ht,llp}.py and every existing occm_variants/
    # ht_variants/llp_variants file): none of these phrases appear anywhere
    # else, and none is a substring of (nor contains) any other variant's
    # own SIGNATURES entries. Confirmed directly on the real sample file:
    # `occm.detect_variant()` returned "Unknown" before this module existed.
    component_localization_list,
    # OCCM Component Status (Posn/Fin Ruled Grid, Scanned) -- known source
    # file has no text layer at all (confirmed via pdfplumber -- 0 chars on
    # every page), so it is only ever reached via ocr_detect()'s blank-text
    # fallback below; SIGNATURES is deliberately empty (see module
    # docstring). Its ocr_detect() anchor requires BOTH the report's own
    # title-line phrase ("COMPONENT STATUS") and a `<reg> (<type>)`-shaped
    # first line in the same title-band crop -- checked directly (grep
    # across every SIGNATURES list in sheet_types/{occm,ht,llp}.py and every
    # existing occm_variants/ht_variants/llp_variants file) against this
    # package's two other "OCCM Component Status"-titled modules:
    # occm_component_status_report.py is a born-digital variant reached only
    # through the router's pdfplumber SIGNATURES match above (never through
    # this ocr_detect fallback, since this module's own known source file
    # has no text layer for that path to match against); and
    # occm_component_status_parent_serial_grid.py's own ocr_detect() anchor
    # ("PARENT SERIAL") does not appear anywhere in this module's own known
    # source file (confirmed directly -- it has no PARENT_SERIAL column at
    # all), and that module's own known source file's header does not carry
    # a `<reg> (<type>)`-shaped title line (its reg/model/MSN print as
    # separate labelled lines instead), so this module's own combined anchor
    # cannot mis-fire on its file either.
    occm_component_status_posn_fin,
    # OCCM Components Status (Plain Ruled Grid, Scanned) -- known source
    # file has no text layer at all (confirmed via pdfplumber -- 0 chars on
    # every page), so it is only ever reached via ocr_detect()'s blank-text
    # fallback below; SIGNATURES is deliberately empty (see module
    # docstring). Its ocr_detect() anchor requires the report's own
    # plural-COMPONENTS title phrase ("OCCM COMPONENTS STATUS") together
    # with the column-header words "INSTALL DATE" and "POSITION" (checked
    # independently rather than as one exact phrase -- the column-header
    # band's own two-line-wrapped cell text was confirmed directly to
    # sometimes OCR with its wrapped fragment reordered at this psm).
    # Checked directly (grep across every SIGNATURES list in
    # sheet_types/{occm,ht,llp}.py and every existing occm_variants file,
    # plus every module's own ocr_detect() anchor text): no other module's
    # own anchor requires this same combination. The bare title phrase
    # alone is a prefix substring of occm_status_list.py's own SIGNATURES
    # entry ("OCCM COMPONENTS STATUS LIST") -- a born-digital module never
    # reachable through this ocr_detect fallback on a blank-text file, so
    # no real collision, but not reused bare here regardless. Also
    # confirmed NOT a match for occm_component_status_posn_fin.py's own
    # anchor ("COMPONENT STATUS", singular, immediately above in this
    # list): the character right after "COMPONENT" differs ("S" here vs a
    # space there) so neither phrase contains the other, and that module's
    # own ocr_detect additionally requires a `<reg> (<type>)`-shaped title
    # line this report's own label:value header box never produces; and
    # NOT a match for aircraft_occm_components_status_scanned.py's own
    # anchor ("AIRCRAFT" + "OC/CM" + "COMPONENTS" + "STATUS"): this
    # report's own title band has no "AIRCRAFT" and renders "OCCM" as one
    # word with no "/", so that anchor cannot fire here either.
    occm_components_status_ruled_grid,
    # EMB-190 OC/CM Status List (Ruled Grid, Scanned) -- known source file
    # has no text layer at all (confirmed via pdfplumber -- 0 chars on
    # every page), so it is only ever reached via ocr_detect()'s
    # blank-text fallback below. Its own ocr_detect() anchor requires
    # BOTH "EMB-190" and "OC/CM Status List" together (see that module's
    # own docstring for the full collision analysis). Checked directly
    # (grep across every SIGNATURES list in sheet_types/{occm,ht,llp}.py
    # and every existing occm_variants/ht_variants/llp_variants file, plus
    # every module's own ocr_detect() anchor text): no other module's own
    # SIGNATURES/ocr_detect anchor requires this combination, and neither
    # "EMB-190" nor the slash-bearing "OC/CM STATUS LIST" phrase (as
    # opposed to the no-slash "OCCM...STATUS LIST" phrases used elsewhere
    # in this package) appears standalone as any other module's own
    # anchor.
    emb190_occm_status_list_ruled_grid,
    # A/C Installed Parts (Scanned) -- known source file has no text layer
    # at all (confirmed via pdfplumber -- 0 chars on every page), so it is
    # only ever reached via ocr_detect()'s blank-text fallback below;
    # SIGNATURES is deliberately empty (see module docstring). Its own
    # ocr_detect() anchor requires BOTH the report's own bare title "A/C
    # Installed Parts" (no trailing "Print") and its column-header phrase
    # "Installed Position" together -- see that module's own docstring for
    # the full collision analysis against aircraft_installed_parts_print.py
    # (a born-digital sibling reached only through the pdfplumber
    # text-match path above, never through this ocr_detect fallback) and
    # against occm_part_status.py (whose own "installed position" text is
    # prose/docstring only, never an actual SIGNATURES entry). Checked
    # directly (grep across every SIGNATURES list in
    # sheet_types/{occm,ht,llp}.py and every existing occm_variants file):
    # no other module's own SIGNATURES/ocr_detect anchor requires this
    # combination.
    aircraft_installed_parts_list_scanned,
    # OCCM List (Current FH/FC Header, Ruled Grid, Scanned) -- known source
    # file has no text layer at all (confirmed via pdfplumber -- 0 chars on
    # every page), so it is only ever reached via ocr_detect()'s blank-text
    # fallback below; SIGNATURES is deliberately empty (see module
    # docstring). Its own ocr_detect() anchor requires BOTH the report's
    # own bare title "OCCM LIST" and its column-header line's own
    # distinctive trailing phrase "AMM STRUCTURE" together -- see that
    # module's own docstring for the full collision analysis (in
    # particular against `occm_list_at_aircraft_fh.py`,
    # `occm_list_func_loc_scanned.py` and `msn_occm_list_scanned.py`, this
    # package's other scanned "OCCM LIST"-titled siblings, none of which
    # require "AMM STRUCTURE" too). Checked directly (grep across every
    # SIGNATURES list in sheet_types/{occm,ht,llp}.py and every existing
    # occm_variants/ht_variants/llp_variants file): "AMM STRUCTURE" appears
    # nowhere else in this package at all.
    occm_list_current_fh_fc_ruled_grid,
    # Aircraft KARDEX Status (AMASIS, Broken Font, Scanned) -- known source
    # file has a NON-blank pdfplumber text layer, but that text is
    # unusable: nearly every recovered character is pdfplumber's own
    # "(cid:<n>)" placeholder token, confirmed directly (the embedded font
    # has no working ToUnicode/Encoding table). This is NOT the same
    # failure mode as this package's other scanned variants (whose own
    # known source files return truly blank/near-zero text), so neither of
    # the router's two existing OCR-fallback checks below would have
    # caught it on its own -- see `_is_cid_garbled()` just below, added
    # specifically for this case, and used as an additional `or` in the
    # trigger condition (never replacing the existing checks). SIGNATURES
    # is deliberately empty (see module docstring); only ever reached via
    # `ocr_detect()`. Checked directly (grep across every SIGNATURES list
    # in sheet_types/{occm,ht,llp}.py and every existing occm_variants/
    # ht_variants/llp_variants module, plus every module's own ocr_detect()
    # anchor text): its own combined anchor ("AMASIS" + "REPORT KARDEX BY
    # AIRCRAFT") does not collide with any other module's own SIGNATURES or
    # ocr_detect anchor -- see that module's own `ocr_detect()` docstring
    # for the full collision analysis, in particular against the bare
    # "KARDEX" SIGNATURES entries used by `remaining_potentials.py` and
    # `technical_object_listing.py` (both reached only through the normal
    # pdfplumber SIGNATURES path, which requires real extracted text this
    # module's own known source file never has, so the two paths cannot
    # collide on the same file either way) and against
    # `component_list_kardex.py`'s own "COMPONENT LIST" SIGNATURES entry
    # (no "KARDEX" substring at all).
    aircraft_kardex_status_broken_font_scanned,
    # OCCM List (PN_description Column Headers, Rotated Scan) -- known
    # source file has no text layer at all (confirmed via pdfplumber -- 0
    # chars on every page), so it is only ever reached via ocr_detect()'s
    # blank-text fallback below; SIGNATURES is deliberately empty (see
    # module docstring). Its own ocr_detect() anchor requires the report's
    # own bare title ("OCCM LIST") together with ALL THREE of its own
    # snake_case column-header labels ("PN description", "installed date",
    # "installed position", underscore/space-normalized) -- see that
    # module's own docstring for the full collision analysis. Checked
    # directly (grep across every SIGNATURES list in
    # sheet_types/{occm,ht,llp}.py and every existing occm_variants/
    # ht_variants/llp_variants file): a bare "OCCM LIST" title is already
    # shared by several sibling "OCCM LIST"-titled variants in this
    # package, so never used alone here; combined with "INSTALLED DATE"
    # (not a substring of, nor containing, `occm_components_status_ruled_
    # grid.py`'s own "INSTALL DATE" anchor -- the extra "ED" breaks the
    # contiguous match either direction) no other module's own SIGNATURES/
    # ocr_detect anchor requires this combination.
    occm_list_pn_description_rotated_scanned,
]

# Sheet-type level signatures, used by the top-level router (sheet_types/router.py)
SIGNATURES = [
    "OCCM",
    "AVIONIC INSTALLED UNITS",
    "AIRCRAFT EQUIPMENT LIST REPORT",
    "OCCM COMPONENTS STATUS LIST",
    "OCCM STATUS",
    "AIRCRAFT REGISTRATION:",
    # Variants added later that don't carry "OCCM" in the header text but
    # ARE OCCM-class data. Without these the in-browser top-level router
    # returns "Unknown" on these files and the single-PDF UI shows a
    # confusing "sheet type not recognised" error — even though we have
    # working per-variant parsers for each.
    "PROG. MAN:",                         # TAP Compact OCCM (CS-T**)
    "AIRCRAFT-EQUIPMENT-LIST",            # hyphenated AMOS variant
    "AIRCRAFT COMPONENT LOG",             # Georgian Airways variant
    "Parts Remaining Fitted at Build",    # EL AL B767 records-package
    "Parts Remaining fitted at Build",    # same, case variation
    "I-BIX",                              # Alitalia I-BIX* registrations
    "AIRCRAFT COMPONENTS LIST",           # aircraft_components_list.py
    # stars_trax_occm.py's OTHER signature, "A/C Detail Items Print", is
    # deliberately NOT added here -- it's also ht_variants/stars_trax.py's
    # signature, and the same "STARS/Trax" MIS tool emits it verbatim for
    # both an OCCM-shaped and an HT-shaped export (confirmed no reliable
    # discriminating phrase exists in the header either way, same root
    # cause as the mm510_llp.py gap below). Adding it here would risk
    # silently stealing genuinely-HT files from stars_trax.py, since LLP
    # and HT are both checked before OCCM in router.py's DETECTION_ORDER.
    # This means only the "A/C Status Audit Print"-headed half of
    # stars_trax_occm's cluster is reachable via normal routing today --
    # see docs/TODO.md for the other half and a real fix.
    "A/C Status Audit Print",             # stars_trax_occm.py (partial -- see above)
    # remaining_potentials.py's AMASIS template also emits an HT-flavoured
    # export of the same report ("Protocol Type H/T" in the header);
    # ht.py's own top-level SIGNATURES claims that specific phrase first
    # per DETECTION_ORDER, so this generic phrase is safe here for every
    # other (OCCM-flavoured) export of the same template.
    "Remaining potentials report",
    # occm_report.py's known source file has no "OCCM" text anywhere in it
    # (confirmed via direct inspection) -- its column-header line is the
    # only reliable anchor, and doubles as its own variant-level SIGNATURES
    # entry (checked for collisions against every SIGNATURES list in
    # sheet_types/{occm,ht,llp}.py and every existing variant file).
    "ATA INSTALL DATE POSITION PN SN DESCRIPTION",
    # occm_summary_list.py's own column-header line and title line both
    # contain "OCCM" already, but its variant-level SIGNATURES phrase
    # ("OCCM SUMMARY LIST") is added explicitly too, since it's a more
    # precise anchor than the generic "OCCM" entry above (checked for
    # collisions against every SIGNATURES list in sheet_types/
    # {occm,ht,llp}.py and every existing variant file first).
    "OCCM SUMMARY LIST",
    # sriwijaya_b737_occm.py needs no entry here: its files have no text
    # layer at all (confirmed near-zero chars), so they're only ever
    # reached via the ocr_detect fallback loop below, not this list.
    # occm_report_scanned.py: same reason -- no text layer on its known
    # source file either.
    # components_list_status_matrix.py's known source file has no "OCCM"/
    # "OC&CM"/"OC/CM" text anywhere in it either (confirmed via direct
    # inspection of every page) -- its column-header line is the only
    # reliable anchor, and doubles as its own variant-level SIGNATURES
    # entry (checked for collisions against every SIGNATURES list in
    # sheet_types/{occm,ht,llp}.py and every existing variant file).
    "Pos InstDate OvhDateDSO",
    # occm_report_time_matrix.py's known source file has no "OCCM" text
    # collision risk here since its title line literally starts "OCCM
    # Report Date :" -- the generic "OCCM" entry above already matches it,
    # but this more precise phrase (and its column-header line) are added
    # too, distinguishing it from occm_report.py's own, differently-worded
    # column-header signature above (checked for collisions against every
    # SIGNATURES list in sheet_types/{occm,ht,llp}.py and every existing
    # variant file, occm_report.py included).
    "OCCM Report Date :",
    "Serial # Position Description Installation Date",
    # oc_cm_status_report.py's known source file's header is literally
    # "OC/CM status <date>" -- the slash means it does NOT contain "OCCM"
    # as a substring, so without this entry the top-level router returns
    # "Unknown" on it (confirmed directly: none of the existing entries in
    # this list, nor any ht.py/llp.py signature, match its header text).
    # Checked for collisions against every SIGNATURES list in
    # sheet_types/{occm,ht,llp}.py and every existing variant file first.
    "OC/CM STATUS",
    # occm_component_status_dual_basis.py's known source file has no
    # "OCCM" text anywhere in it either (confirmed via direct inspection
    # of every page) -- its title line reads "ON CONDITION COMPONENTS
    # REPORT" and its column-header line is the only reliable anchor,
    # doubling as its own variant-level SIGNATURES entry (checked for
    # collisions against every SIGNATURES list in sheet_types/
    # {occm,ht,llp}.py and every existing variant file first).
    "ATA P/N DESCRIPTION S/N POS MPCODE INST. DATE UNIT TSN TSI LSN LSI",
    # oc_component_status.py's known source file's title reads literally
    # "O/C COMPONENT STATUS" -- the slash means it does NOT contain "OCCM"
    # as a substring, so without this entry the top-level router returns
    # "Unknown" on it (confirmed directly: none of the existing entries in
    # this list, nor any ht.py/llp.py signature, match its header text).
    # Checked for collisions against every SIGNATURES list in
    # sheet_types/{occm,ht,llp}.py and every existing variant file first.
    "O/C COMPONENT STATUS",
    # occm_control_sheet.py's known source file already contains "OCCM" in
    # its title line ("OCCM Control Sheet"), so the generic "OCCM" entry
    # above already matches it -- its own variant-level SIGNATURES phrase
    # is added here too anyway, as the more precise anchor, per this file's
    # convention (checked for collisions against every SIGNATURES list in
    # sheet_types/{occm,ht,llp}.py and every existing variant file first).
    "OCCM Control Sheet",
    # all_fitted_aircraft_component_log.py's known source file has no "OCCM"
    # text anywhere in it (confirmed via direct inspection) -- its title
    # line reads literally "All Fitted Aircraft Component LOG". The
    # existing generic "AIRCRAFT COMPONENT LOG" entry above (added for
    # georgian_airways_b737.py) already matches it as a substring, so this
    # more precise full-title phrase is added too as the sharper anchor, per
    # this file's convention (checked for collisions against every
    # SIGNATURES list in sheet_types/{occm,ht,llp}.py and every existing
    # variant file first -- including georgian_airways_b737.py's own
    # variant-level SIGNATURES, which use a different, more specific phrase
    # and do not match this title).
    "All Fitted Aircraft Component LOG",
    # occm_component_inventory.py's title line already contains "OCCM"
    # ("MSN <msn> OCCM COMPONENT INVENTORY"), so the generic "OCCM" entry
    # above already matches it -- this more precise phrase is added anyway
    # as the sharper anchor, per this file's convention (checked for
    # collisions against every SIGNATURES list in sheet_types/
    # {occm,ht,llp}.py and every existing variant file first).
    "OCCM COMPONENT INVENTORY",
    # occm_listing.py's title line already contains "OCCM" ("OCCM Listing"),
    # so the generic "OCCM" entry above already matches it -- this more
    # precise phrase is added anyway as the sharper anchor, per this file's
    # convention (checked for collisions against every SIGNATURES list in
    # sheet_types/{occm,ht,llp}.py and every existing variant file first).
    "OCCM Listing",
    # occm_component_data_install_current.py's known source file's title
    # line reads literally "<code> OC/CM(MSN<n>)" -- the slash means it does
    # NOT contain "OCCM" as a substring (confirmed directly), so without an
    # entry here the top-level router returns "Unknown" on it. Its own
    # variant-level SIGNATURES phrase ("Component Data at Install") is used
    # here too since it's a more precise, title-independent anchor. Checked
    # for collisions against every SIGNATURES list in sheet_types/
    # {occm,ht,llp}.py and every existing variant file first.
    "Component Data at Install",
    # serialized_component_list.py's known source file has no "OCCM" text
    # anywhere in it (confirmed via direct inspection) -- its title line
    # reads literally "Serialized Component List", added here as its own
    # variant-level SIGNATURES phrase, doubling as the top-level anchor.
    # Checked for collisions against every SIGNATURES list in sheet_types/
    # {occm,ht,llp}.py and every existing variant file first -- in
    # particular llp_variants/aar_landing_gear_serialized_list.py's
    # "Serialized List" and llp_variants/serialized_unit_hard_limits.py's
    # "Serialized Unit List - Hard Limits" are NOT substrings of this
    # phrase (or vice versa), so no collision risk with either.
    "Serialized Component List",
    # installed_parts_list.py's known source file has no "OCCM" text
    # anywhere in it (confirmed via direct inspection) -- its title line
    # reads literally "INSTALLED PARTS LIST" (rendered with or without the
    # space between PARTS and LIST depending on the page), added here as
    # its own variant-level SIGNATURES phrase, doubling as the top-level
    # anchor. Checked for collisions against every SIGNATURES list in
    # sheet_types/{occm,ht,llp}.py and every existing variant file first.
    "INSTALLED PARTS LIST",
    # serialization_list_by_ata.py's known source file has no "OCCM" text
    # anywhere in it (confirmed via direct inspection) -- its title line
    # reads "<report_id> SERIALIZATION LIST by ATA CHAPTER", added here as
    # its own variant-level SIGNATURES phrase, doubling as the top-level
    # anchor. Checked for collisions against every SIGNATURES list in
    # sheet_types/{occm,ht,llp}.py and every existing variant file first --
    # in particular llp_variants/aar_landing_gear_serialized_list.py's
    # "Serialized List" and serialized_component_list.py's "Serialized
    # Component List" are NOT substrings of this phrase (or vice versa), so
    # no collision risk with either.
    "SERIALIZATION LIST by ATA CHAPTER",
    # assembly_configuration_status_report.py's known source file has no
    # "OCCM" text anywhere in it (confirmed via direct inspection of every
    # page) -- its title line reads literally "ASSEMBLY CONFIGURATION /
    # STATUS REPORT", added here as its own variant-level SIGNATURES phrase,
    # doubling as the top-level anchor. Checked for collisions against every
    # SIGNATURES list in sheet_types/{occm,ht,llp}.py and every existing
    # variant file first.
    "ASSEMBLY CONFIGURATION / STATUS REPORT",
    # maintenance_status_report_pr21.py's known source file has no "OCCM"
    # text anywhere in it (confirmed via direct inspection of every page)
    # -- its title line reads literally "MAINTENANCE STATUS REPORT Report
    # PR21", added here as its own variant-level SIGNATURES phrase,
    # doubling as the top-level anchor. Checked for collisions against
    # every SIGNATURES list in sheet_types/{occm,ht,llp}.py and every
    # existing variant file first.
    "MAINTENANCE STATUS REPORT",
    # component_list_kardex.py's known source file has no "OCCM" text
    # anywhere in it (confirmed via direct inspection of every page) -- its
    # title line reads literally "COMPONENT LIST", added here as its own
    # variant-level SIGNATURES phrase, doubling as the top-level anchor.
    # This is a generic phrase, so it's added last and the variant itself
    # is placed near the end of VARIANTS (see that list) to minimise
    # misrouting risk. Checked for collisions against every SIGNATURES list
    # in sheet_types/{occm,ht,llp}.py and every existing variant file first.
    "COMPONENT LIST",
    # aircraft_installed_parts_print.py's known source file has no "OCCM"
    # text anywhere in it (confirmed via direct inspection of every page)
    # -- its title line reads literally "A/C Installed Parts Print", added
    # here as its own variant-level SIGNATURES phrase, doubling as the
    # top-level anchor. Checked for collisions against every SIGNATURES
    # list in sheet_types/{occm,ht,llp}.py and every existing variant file
    # first.
    "A/C Installed Parts Print",
    # oc_cm_components_install_current.py's known source file's title reads
    # literally "OC/CM COMPONENTS" -- no "OCCM" substring (confirmed
    # directly), so without an entry here the top-level router returns
    # "Unknown" on it. "AIRCRAFT REG. :" is used instead of the title
    # phrase itself, since "OC/CM COMPONENTS" is a substring of
    # a305_a340_occm.py's own SIGNATURES phrase ("Components >> OC/CM
    # Components", confirmed directly) and would risk stealing that
    # variant's files at the top-level sheet-type check; "AIRCRAFT REG. :"
    # is checked for collisions against every SIGNATURES list in
    # sheet_types/{occm,ht,llp}.py and every existing variant file first,
    # with none found.
    "AIRCRAFT REG. :",
    # occm_components_control_sma.py's known source file has no "OCCM" text
    # anywhere in it (confirmed via direct inspection of every page) -- its
    # title line reads literally "COMPONENTS CONTROL". Without an entry
    # here the top-level router returns "Unknown" on it. Checked for
    # collisions against every SIGNATURES list in sheet_types/
    # {occm,ht,llp}.py and every existing variant file first, with none
    # found.
    "COMPONENTS CONTROL",
    # on_condition_monitoring_components.py's known source file has no
    # "OCCM" text anywhere in it (confirmed via direct inspection) -- its
    # title line reads literally "... ATA <n>[-<n>] ON CONDITION MONITORING
    # COMPONENTS". Without an entry here the top-level router returns
    # "Unknown" on it. Checked for collisions against every SIGNATURES list
    # in sheet_types/{occm,ht,llp}.py and every existing variant file first,
    # with none found.
    "ON CONDITION MONITORING COMPONENTS",
    # serialised_components_report.py's known source file has no "OCCM"
    # text anywhere in it (confirmed via direct inspection) -- its title
    # line reads literally "Serialised Components Report", added here as
    # its own variant-level SIGNATURES phrase, doubling as the top-level
    # anchor. Checked for collisions against every SIGNATURES list in
    # sheet_types/{occm,ht,llp}.py and every existing variant file first --
    # in particular serialized_component_list.py's "Serialized Component
    # List" (American spelling, singular "Component") is NOT a substring
    # of this phrase (or vice versa), so no collision risk with it.
    "serialised components report",
    # occm_uic_status.py's known source file's title line already contains
    # "OCCM" ("OCCMUIC <reg> (MSN <msn>), TSN: ..., CSN: ..."), so the
    # generic "OCCM" entry above already matches it -- this more precise
    # phrase is added anyway as the sharper anchor, per this file's
    # convention (checked for collisions against every SIGNATURES list in
    # sheet_types/{occm,ht,llp}.py and every existing variant file first).
    "OCCMUIC",
    # on_condition_components_install_current.py's known source file has no
    # "OCCM" text anywhere in it either (confirmed via direct inspection of
    # every page) -- its title line reads literally "On-Condition
    # Components Report" (hyphenated, mixed case, so it does NOT contain
    # "OCCM" as a substring). Without an entry here the top-level router
    # returns "Unknown" on it. Its own variant-level SIGNATURES phrase
    # ("INSTALLATION DATA CURRENT DATA (") is used here too since it's a
    # more precise, title-independent anchor. Checked for collisions
    # against every SIGNATURES list in sheet_types/{occm,ht,llp}.py and
    # every existing variant file first.
    "INSTALLATION DATA CURRENT DATA (",
    # condition_monitoring_components_status.py's known source file has no
    # "OCCM" text anywhere in it either (confirmed via direct inspection)
    # -- its title line reads literally "... CONDITION MONITORING
    # COMPONENTS STATUS ..." (renders contiguously despite heavy
    # surrounding character-substitution noise). Without an entry here the
    # top-level router returns "Unknown" on it. Checked for collisions
    # against every SIGNATURES list in sheet_types/{occm,ht,llp}.py and
    # every existing variant file first -- in particular
    # on_condition_monitoring_components.py's own phrase "ON CONDITION
    # MONITORING COMPONENTS" (leading "ON", no "STATUS" suffix) is NOT a
    # substring of this phrase nor vice versa, so no collision risk.
    "CONDITION MONITORING COMPONENTS STATUS",
    # component_localization_list.py's known source file has no "OCCM" text
    # anywhere in it either (confirmed via direct inspection of every page)
    # -- its own repeating column-header word is "Localization". Without an
    # entry here the top-level router returns "Unknown" on it. Checked for
    # collisions against every SIGNATURES list in sheet_types/
    # {occm,ht,llp}.py and every existing variant file first, with none
    # found.
    "LOCALIZATION",
]
_BY_NAME = {v.NAME: v for v in VARIANTS}

# Backwards-compat for code that still imports CANONICAL_COLUMNS from occm.
CANONICAL_COLUMNS = aeroflot.CANONICAL_COLUMNS


def _read_head_text(pdf_path: str, n_pages: int = 3) -> str:
    """Read the first n_pages of text. Uses pdfplumber so the deploy needs
    only one PDF library (avoids the pymupdf binary dependency)."""
    parts = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for p in pdf.pages[:n_pages]:
                parts.append(p.extract_text() or "")
    except Exception:
        pass
    return "\n".join(parts)


def _read_page1_text(pdf_path: str) -> str:
    """Text of page 1 alone (vs. `_read_head_text`'s 3-page aggregate) --
    see its one caller in `detect_variant()` for why this is checked
    separately."""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            if pdf.pages:
                return pdf.pages[0].extract_text() or ""
    except Exception:
        pass
    return ""


_CID_GARBLE_RE = re.compile(r"\(cid:\d+\)", re.IGNORECASE)


def _is_cid_garbled(text: str) -> bool:
    """True when `text` (pdfplumber's own `extract_text()` output) is
    dominated by "(cid:<n>)" placeholder tokens -- the literal string
    pdfplumber emits for a glyph it cannot map through the embedded font's
    (missing/broken) ToUnicode table, rather than raising or returning
    blank text. Confirmed directly on
    `aircraft_kardex_status_broken_font_scanned.py`'s own known source
    file: every page's `extract_text()` comes back non-blank (thousands of
    characters), so neither of `detect_variant()`'s two existing
    blank-text checks below catches it -- they only look at recovered
    LENGTH, never at what the recovered text actually says. A real,
    otherwise-working text layer occasionally embeds one or two truly
    unmapped glyphs (an unusual symbol/ligature) without being globally
    broken, so only text where these placeholders make up the bulk of the
    recovered characters (checked directly against the real broken file:
    "(cid:<n>)" tokens account for ~98% of every page's own recovered
    text) is treated as unusable here -- a low, incidental rate is left
    alone. Measured by total matched-character coverage rather than a
    bare token count: "(cid:9)" and "(cid:123456)" cover very different
    shares of a short head-text sample, and a count-only ratio was
    confirmed directly to under-count this real file's own ~8-characters-
    per-token average and miss it entirely at a naive per-token threshold."""
    if not text:
        return False
    matches = _CID_GARBLE_RE.findall(text)
    covered = sum(len(m) for m in matches)
    return covered * 2 >= len(text)


async def detect_variant(pdf_path: str) -> str:
    head = _read_head_text(pdf_path).upper()
    for v in VARIANTS:
        for sig in v.SIGNATURES:
            if sig.upper() in head:
                return v.NAME
    # OCR-fallback trigger: either the whole 3-page aggregate has no usable
    # text (the original, wholly-scanned case), OR page 1 alone is blank
    # even though later pages carry a real text layer -- confirmed on a
    # real sample (occm_status_list_type_model_header.py's known source
    # file): its title/header page (page 1) is a flat scanned image with
    # 0 chars, but pages 2+ are born-digital with ~2.5-2.9k chars each, so
    # the 3-page aggregate alone sails past the 50-char floor and this
    # loop was never reached even though the header (and hence every
    # SIGNATURES phrase) is only ever visible via OCR. Checking page 1
    # alone catches that case without weakening the existing aggregate
    # check for any variant that already relied on it (this is an
    # additional `or`, not a replacement).
    #
    # A third case, also an additional `or`: the recovered text is
    # non-blank (sails past both length checks above) but dominated by
    # pdfplumber's own "(cid:<n>)" placeholder tokens -- a broken font
    # ToUnicode table, not a scan, but just as unusable as either blank
    # case above for SIGNATURES matching. See `_is_cid_garbled()` and
    # `aircraft_kardex_status_broken_font_scanned.py`'s own module
    # docstring for the real confirmed case this catches.
    if (len(head.strip()) < 50 or len(_read_page1_text(pdf_path).strip()) < 50
            or _is_cid_garbled(head)):
        # No usable text layer -- ask any OCR-capable variant to confirm its
        # own template via a cheap header OCR pass rather than guessing.
        # This used to default blind to "Aeroflot" (the only OCR variant
        # when that line was written), which meant ANY blank-text PDF got
        # confidently mislabeled "Aeroflot" -- including, in practice, a
        # scanned document that wasn't OCCM at all. Mirrors the same
        # pattern in sheet_types/llp.py and sheet_types/router.py.
        for v in VARIANTS:
            ocr_check = getattr(v, "ocr_detect", None)
            if ocr_check and await maybe_await(ocr_check(pdf_path)):
                return v.NAME
    return "Unknown"


async def extract(pdf_path: str, variant_name: str | None = None) -> dict:
    if variant_name is None:
        variant_name = await detect_variant(pdf_path)
    v = _BY_NAME.get(variant_name)
    if v is None:
        return {"variant": "Unknown", "columns": [], "records": []}
    records = await maybe_await(v.extract(pdf_path))
    return {"variant": v.NAME, "columns": v.CANONICAL_COLUMNS, "records": records}


def normalize_and_validate(records: list[dict], variant_name: str = "Aeroflot") -> list[dict]:
    v = _BY_NAME.get(variant_name, aeroflot)
    cleaned = [clean_record(dict(r), v.RULES) for r in records]
    # Generic post-process: forward-fill ATA chapters across rows. Cheap safety
    # net for variants where ATA only appears on section headings.
    if "ATA" in v.CANONICAL_COLUMNS:
        forward_fill_ata(cleaned)
    return cleaned
