"""OCCM router — detects which OCCM variant a PDF is, dispatches to its parser.

Variants live under `sheet_types/occm_variants/`. Each exposes a uniform
interface (NAME, SIGNATURES, CANONICAL_COLUMNS, RULES, extract).

Public functions:
    detect_variant(pdf_path) -> str            — name of detected variant
    extract(pdf_path) -> dict                  — {variant, columns, records}
    normalize_and_validate(records, variant)   — apply per-variant rules
"""
from __future__ import annotations
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
    occm_status_on_condition_items,
    component_list_occm_airframe,
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


async def detect_variant(pdf_path: str) -> str:
    head = _read_head_text(pdf_path).upper()
    for v in VARIANTS:
        for sig in v.SIGNATURES:
            if sig.upper() in head:
                return v.NAME
    if len(head.strip()) < 50:
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
