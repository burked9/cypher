"""HT (Hard Time) sheet-type router.

Mirrors `sheet_types/occm.py`. Detects which HT variant a PDF is and
dispatches to the variant's `extract()`.
"""
from __future__ import annotations
import pdfplumber

from sheet_types.ht_variants import (
    vietnam_airlines, amos, mm510, tap, iberia, oases_lifed_components,
    stars_trax, aircraft_rotables_ht,
    georgian_airways_ht_components_status, mpd_hard_time_list, htll_status,
    hard_time_component_status_mpd_task,
    aercap_hard_time_component_status, aercap_oxygen_generator_status,
    emes_hard_time_component_status,
    xiamen_time_controlled_components, aircraft_rotables_ht_scanned,
    amos_scanned, aircraft_inspection_report_scanned,
    georgian_airways_ht_components_status_scanned,
    hard_time_report_config_slot,
    al_development_controlled_items_list,
    time_controlled_components_status,
    air_france_ccinv_aircraft_inventory,
    activity_life_expiry_report,
    time_controlled_items_status,
    time_controlled_items_report,
    remaining_potentials,
    cognos_ht_listing,
    maintenance_due_report_porp96rr,
    ca004_hard_time_monitoring_sheet,
    time_controlled_items_current_status,
    hard_time_component_list,
    fit_ac_hr_cyc_bilingual_status,
    hard_time_components_bordered_table,
    hard_time_status_ata_reference,
    fire_extinguisher_oxygen_status_list,
    emer_inventory_list,
    ht_list_report,
    hard_time_status_mpd_cert_fin,
    tci_list,
    hard_time_componets_status_mpd_ruled,
    hard_time_snake_case_eo_listing,
    hard_time_limit_control_status,
    functional_location_ht_component,
    mpd_service_interval_status,
    amos_reference_equipment_list,
    hard_time_aircraft_components_status_broken_font,
    trp_status_dual_layer_scanned,
    tci_status_broken_font,
    fl_compound_code_ht,
    maintenance_status_report_erm1,
    ht_components_status_ruled_grid,
    ht_components_list_limite_control,
    oases_component_report_fitted_to_matrix,
    ht_aircraft_component_log,
    airframe_htc_llp_status,
    hard_time_day_fhr_cyc_matrix_scanned,
)
from shared.cleanup import clean_record
from shared.ocr_bridge import maybe_await

# Order matters: more-specific signatures must precede generic ones.
# Variants with distinctive headers sit before the AMOS catch-all.
VARIANTS = [vietnam_airlines, mm510, tap, iberia,
            oases_lifed_components, stars_trax, aircraft_rotables_ht, amos,
            amos_reference_equipment_list,
            georgian_airways_ht_components_status, mpd_hard_time_list, htll_status,
            hard_time_component_status_mpd_task,
            aercap_hard_time_component_status, aercap_oxygen_generator_status,
            emes_hard_time_component_status,
            xiamen_time_controlled_components, aircraft_rotables_ht_scanned,
            amos_scanned, aircraft_inspection_report_scanned,
            georgian_airways_ht_components_status_scanned,
            hard_time_report_config_slot,
            al_development_controlled_items_list,
            time_controlled_components_status,
            air_france_ccinv_aircraft_inventory,
            activity_life_expiry_report,
            time_controlled_items_status,
            time_controlled_items_report,
            remaining_potentials,
            cognos_ht_listing,
            maintenance_due_report_porp96rr,
            ca004_hard_time_monitoring_sheet,
            time_controlled_items_current_status,
            hard_time_component_list,
            fit_ac_hr_cyc_bilingual_status,
            hard_time_components_bordered_table,
            hard_time_status_ata_reference,
            fire_extinguisher_oxygen_status_list,
            emer_inventory_list,
            ht_list_report,
            hard_time_status_mpd_cert_fin,
            tci_list,
            hard_time_componets_status_mpd_ruled,
            hard_time_snake_case_eo_listing,
            hard_time_limit_control_status,
            functional_location_ht_component,
            mpd_service_interval_status,
            hard_time_aircraft_components_status_broken_font,
            trp_status_dual_layer_scanned,
            tci_status_broken_font,
            fl_compound_code_ht,
            maintenance_status_report_erm1,
            ht_components_status_ruled_grid,
            ht_components_list_limite_control,
            oases_component_report_fitted_to_matrix,
            ht_aircraft_component_log,
            airframe_htc_llp_status,
            hard_time_day_fhr_cyc_matrix_scanned]
_BY_NAME = {v.NAME: v for v in VARIANTS}

# Sheet-type level signatures (used by the top-level router)
SIGNATURES = [
    "PLAN OF AIRCRAFT COMPONENT REPLACEMENT",
    "HARD TIME COMPONENTS STATUS FOR A/C-REGISTRATION",  # georgian_airways_ht_components_status.py
    "HARD TIME LIST AS AT",                              # mpd_hard_time_list.py
    "HT-LL STATUS",                                      # htll_status.py
    "HT&LLP STATUS",                                     # htll_status.py, other sub-format
    "MPD TASK NO",                                       # hard_time_component_status_mpd_task.py
    "COMP.TIMELINE",                                     # aercap_hard_time_component_status.py
    "OXYGEN GENERATOR STATUS",                           # aercap_oxygen_generator_status.py
    # NOT "FROM E.MES" -- that phrase is also emes_airframe_llp_status.py's
    # (LLP) own signature, the same cross-sheet-type MIS-vendor-boilerplate
    # pattern as MM_510/STARS Trax elsewhere in this file. This phrase is
    # unique to the HT-side format instead.
    "T/C # TASK HT",                                     # emes_hard_time_component_status.py
    "Time-controlled Components",                        # xiamen_time_controlled_components.py
    "HARD TIME REPORT",                                  # hard_time_report_config_slot.py --
                                                          # same South American MIS family as
                                                          # config_slot_occm.py (OCCM) and
                                                          # landing_gear_llp_report.py (LLP);
                                                          # this title phrase is unique to the
                                                          # HT-side export, no collision checked
                                                          # against llp.py/occm.py's own lists.
    "MPD TASK Work Type ZONE",                           # al_development_controlled_items_list.py --
                                                          # checked against every SIGNATURES list in
                                                          # occm.py/ht.py/llp.py and every ht_variants
                                                          # module; no collision found.
    "TIME CONTROLLED COMPONENTS STATUS",                 # time_controlled_components_status.py --
                                                          # checked against every SIGNATURES list in
                                                          # occm.py/ht.py/llp.py and every ht_variants
                                                          # module; no collision found.
    "AIRCRAFT REGLEMENTARY INVENTORY",                   # air_france_ccinv_aircraft_inventory.py --
                                                          # checked against every SIGNATURES list in
                                                          # occm.py/ht.py/llp.py and every ht_variants
                                                          # module; no collision found.
    "AIRCRAFT FULL INVENTORY",                           # air_france_ccinv_aircraft_inventory.py --
                                                          # sibling report subtype of the same CCINV
                                                          # export family as the REGLEMENTARY variant
                                                          # above (same parser). Checked against every
                                                          # SIGNATURES list in occm.py/ht.py/llp.py and
                                                          # every ht_variants module; no collision
                                                          # found.
    "Activity Life Expiry Report",                       # activity_life_expiry_report.py --
                                                          # checked against every SIGNATURES list in
                                                          # occm.py/ht.py/llp.py and every ht_variants
                                                          # module; no collision found.
    "TIME CONTROLLED ITEMS STATUS",                      # time_controlled_items_status.py --
                                                          # checked against every SIGNATURES list in
                                                          # occm.py/ht.py/llp.py and every ht_variants
                                                          # module (including the similarly-named but
                                                          # structurally different
                                                          # time_controlled_components_status.py); no
                                                          # collision found.
    "Time Controlled Items Report",                      # time_controlled_items_report.py --
                                                          # checked against every SIGNATURES list in
                                                          # occm.py/ht.py/llp.py and every ht_variants
                                                          # module (including the similarly-named but
                                                          # structurally different
                                                          # time_controlled_items_status.py and
                                                          # time_controlled_components_status.py); no
                                                          # collision found.
    "Protocol Type H/T",                                 # remaining_potentials.py -- the AMASIS
                                                          # "Remaining potentials report" template
                                                          # (shared with occm_variants/
                                                          # remaining_potentials.py) is emitted for
                                                          # both OCCM- and HT-flavored exports; this
                                                          # phrase only appears when the export was
                                                          # filtered to Hard-Time positions, so it's
                                                          # the mutually-exclusive discriminator used
                                                          # here instead of the shared generic header
                                                          # phrases (deliberately NOT added to this
                                                          # list -- see remaining_potentials.py's own
                                                          # docstring for why).
    "HT LISTING",                                        # cognos_ht_listing.py -- checked against
                                                          # every SIGNATURES list in occm.py/ht.py/
                                                          # llp.py and every ht_variants module; no
                                                          # collision found.
    "MAINTENANCE DUE REPORT",                            # maintenance_due_report_porp96rr.py --
                                                          # checked against every SIGNATURES list in
                                                          # occm.py/ht.py/llp.py and every
                                                          # occm_variants/ht_variants/llp_variants
                                                          # module; no collision found.
    "Hard Time Monitoring Sheet",                        # ca004_hard_time_monitoring_sheet.py --
                                                          # checked against every SIGNATURES list in
                                                          # occm.py/ht.py/llp.py and every
                                                          # occm_variants/ht_variants/llp_variants
                                                          # module; no collision found.
    "Time Controlled Items Current Status",              # time_controlled_items_current_status.py --
                                                          # deliberately includes "Current" so it can't
                                                          # collide with this file's own
                                                          # "TIME CONTROLLED ITEMS STATUS" or
                                                          # "TIME CONTROLLED COMPONENTS STATUS" entries
                                                          # above (neither phrase is a contiguous
                                                          # substring of this one, in either direction).
                                                          # Checked against every SIGNATURES list in
                                                          # occm.py/ht.py/llp.py and every
                                                          # occm_variants/ht_variants/llp_variants
                                                          # module; no collision found.
    "HARD TIME COMPONENT LIST",                          # hard_time_component_list.py --
                                                          # checked against every SIGNATURES list in
                                                          # occm.py/ht.py/llp.py and every
                                                          # occm_variants/ht_variants/llp_variants
                                                          # module; no collision found.
    "FIT A/C Hr FIT A/C Cyc",                            # fit_ac_hr_cyc_bilingual_status.py --
                                                          # checked against every SIGNATURES list in
                                                          # occm.py/ht.py/llp.py and every
                                                          # occm_variants/ht_variants/llp_variants
                                                          # module; no collision found (nearest
                                                          # look-alike, occm_variants/
                                                          # assembly_configuration_status_report.py's
                                                          # "Current A/C Times", is a different phrase).
    "TOTAL TIMES SINCE NEW",                             # hard_time_components_bordered_table.py --
                                                          # checked against every SIGNATURES list in
                                                          # occm.py/ht.py/llp.py and every
                                                          # occm_variants/ht_variants/llp_variants
                                                          # module (including a plain grep for "SINCE
                                                          # NEW"); no collision found -- nearest
                                                          # look-alikes (config_slot_occm.py's "TIME
                                                          # SINCE NEW ...", mm510.py's "Time Since New
                                                          # : ...") use "TIME"/"Time" singular, not
                                                          # "TOTAL TIMES".
    "HARD TIME STATUS",                                  # hard_time_status_ata_reference.py --
                                                          # checked against every SIGNATURES list in
                                                          # occm.py/ht.py/llp.py and every
                                                          # occm_variants/ht_variants/llp_variants
                                                          # module; no collision found. Not a
                                                          # substring of, and does not contain as a
                                                          # substring, any other variant's own
                                                          # signature phrase (e.g. distinct from
                                                          # georgian_airways_ht_components_status.py's
                                                          # "HARD TIME COMPONENTS STATUS FOR
                                                          # A/C-REGISTRATION" and
                                                          # hard_time_component_list.py's "HARD TIME
                                                          # COMPONENT LIST").
    "Fire Extinguisher Status List",                     # fire_extinguisher_oxygen_status_list.py --
                                                          # checked against every SIGNATURES list in
                                                          # occm.py/ht.py/llp.py and every
                                                          # occm_variants/ht_variants/llp_variants
                                                          # module; no collision found.
    "OXYGEN STATUS LIST",                                # fire_extinguisher_oxygen_status_list.py --
                                                          # sibling report template, same source file
                                                          # family as the entry above. Checked against
                                                          # every SIGNATURES list in occm.py/ht.py/
                                                          # llp.py and every occm_variants/ht_variants/
                                                          # llp_variants module (including a plain grep
                                                          # for "OXYGEN"); no collision found -- distinct
                                                          # from aercap_oxygen_generator_status.py's own
                                                          # "OXYGEN GENERATOR STATUS".
    "EMER INVENTORY MSN",                                # emer_inventory_list.py --
                                                          # checked against every SIGNATURES list in
                                                          # occm.py/ht.py/llp.py and every
                                                          # occm_variants/ht_variants/llp_variants
                                                          # module's own SIGNATURES list (plus a plain
                                                          # grep for "EMER INVENTORY" and each of this
                                                          # file's own eight section-title phrases);
                                                          # no collision found.
    "HT LIST REPORT",                                    # ht_list_report.py -- checked against every
                                                          # SIGNATURES list in occm.py/ht.py/llp.py and
                                                          # every occm_variants/ht_variants/llp_variants
                                                          # module's own SIGNATURES list; no collision
                                                          # found. Not a substring of, and does not
                                                          # contain as a substring, cognos_ht_listing.py's
                                                          # own "HT LISTING" in either direction.
    "MPD Item #",                                        # hard_time_status_mpd_cert_fin.py --
                                                          # checked against every SIGNATURES list in
                                                          # occm.py/ht.py/llp.py and every
                                                          # occm_variants/ht_variants/llp_variants
                                                          # module; no collision found.
    "LAST INSP/OVH",                                     # hard_time_status_mpd_cert_fin.py -- sibling
                                                          # anchor from the same template's own header,
                                                          # same collision check as above.
    "ATA OMP REF REQ PN SN DESCRIPTION POS INST DATE",   # tci_list.py -- the full column-header line
                                                          # from this template's own ruled table.
                                                          # Checked against every SIGNATURES list in
                                                          # occm.py/ht.py/llp.py and every
                                                          # occm_variants/ht_variants/llp_variants
                                                          # module (including a plain grep for "OMP REF"
                                                          # and "TCI"); no collision found -- the only
                                                          # existing "TCI" occurrence anywhere in the
                                                          # project is occm_variants/
                                                          # aircraft_occm_list_hcd.py's unrelated
                                                          # "TSI TST TSO TSN TTR TCI Limit Limit Type
                                                          # ..." column-header phrase.
    "HT COMPONETS STATUS",                               # hard_time_componets_status_mpd_ruled.py --
                                                          # checked against every SIGNATURES list in
                                                          # occm.py/ht.py/llp.py and every
                                                          # occm_variants/ht_variants/llp_variants
                                                          # module; no collision found. Not a substring
                                                          # of, and does not contain as a substring,
                                                          # occm_variants/cca_a340_occm.py's own
                                                          # "OCCM COMPONETS STATUS" (different sheet-type
                                                          # prefix, "OCCM" vs "HT").
    "EO ATA_CHAPTER PN SN PN_DESCRIPTION INSTALLED_POSITION INSTALLED_DATE "
    "ACTUAL_HOURS ACTUAL_CYCLES TASK REQUIREMENT SCHEDULE_HOURS "
    "SCHEDULE_CYCLES SCHEDULE_DAYS DUE_DATE DUE_AT_HOURS DUE_AT_CYCLES "
    "REMAIN_HOURS REMAIN_MINUTES REMAIN_CYCLES REMAIN_DAYS NHA_PN NHA_SN",
                                                          # hard_time_snake_case_eo_listing.py -- the
                                                          # full column-header line, verbatim. Checked
                                                          # against every SIGNATURES list in
                                                          # occm.py/ht.py/llp.py and every
                                                          # occm_variants/ht_variants/llp_variants
                                                          # module (including a plain grep for
                                                          # "ata_chapter", "installed_position",
                                                          # "pn_description", "nha_pn",
                                                          # "schedule_hours" and "remain_minutes"); no
                                                          # collision found. The nearest look-alike,
                                                          # occm_variants/
                                                          # occm_list_pn_description_rotated_scanned.py,
                                                          # shares this same snake_case-header-label
                                                          # convention (same source MIS vendor family)
                                                          # but a different column set and a
                                                          # deliberately empty SIGNATURES list of its
                                                          # own (scanned-only, detected via its own
                                                          # ocr_detect() instead), so there is nothing
                                                          # to collide with there.
    "LIMIT CONTROL NEXT DUE REMAINING NOTES",            # hard_time_limit_control_status.py -- this
                                                          # file's own column-header line, verbatim.
                                                          # Checked against every SIGNATURES list in
                                                          # occm.py/ht.py/llp.py and every
                                                          # occm_variants/ht_variants/llp_variants
                                                          # module (including a plain grep for "LIMIT
                                                          # CONTROL", "NEXT DUE REMAINING" and "CONTROL
                                                          # NEXT DUE"); no collision found. The nearest
                                                          # look-alike, georgian_airways_ht_components_
                                                          # status.py's own "... SPEC LIMIT NEXT DUE
                                                          # REMAINING", is a different, shorter phrase
                                                          # (no "CONTROL", no "NOTES") and not a
                                                          # substring of this one in either direction.
    "HT-COMPONENT",                                      # functional_location_ht_component.py --
                                                          # checked against every SIGNATURES list in
                                                          # occm.py/ht.py/llp.py and every
                                                          # occm_variants/ht_variants/llp_variants
                                                          # module (including a plain grep for
                                                          # "HT-COMPONENT"); no collision found.
    "HT ‐ COMPONENT STATUS",                             # mpd_service_interval_status.py -- this
                                                          # file's own title line, verbatim (the
                                                          # character between "HT" and "COMPONENT" is
                                                          # U+2010 HYPHEN, not ASCII hyphen-minus).
                                                          # Checked against every SIGNATURES list in
                                                          # occm.py/ht.py/llp.py and every
                                                          # occm_variants/ht_variants/llp_variants
                                                          # module (including a plain grep for "HT" +
                                                          # "COMPONENT STATUS" combinations); no
                                                          # collision found -- not a substring of, and
                                                          # does not contain as a substring, any other
                                                          # variant's own signature phrase, including
                                                          # this same file's own "HT-COMPONENT" entry
                                                          # just above (ASCII hyphen, no spaces, no
                                                          # "STATUS").
    "MPD PART SERIAL INSTALLED SERVICE INTERVAL NEXT DUE REMAINING REMARKS",
                                                          # mpd_service_interval_status.py -- backup
                                                          # anchor, this file's own ruled-table header
                                                          # row, verbatim. Checked against every
                                                          # SIGNATURES list in occm.py/ht.py/llp.py and
                                                          # every occm_variants/ht_variants/llp_variants
                                                          # module (including a plain grep for "MPD PART
                                                          # SERIAL"); no collision found.
    "ACRF REG. :",                                       # hard_time_aircraft_components_status_broken_font.py --
                                                          # see that module's own docstring for why this
                                                          # short fragment survives its file's otherwise
                                                          # broken text-layer decode. Checked against every
                                                          # SIGNATURES list in occm.py/ht.py/llp.py and every
                                                          # occm_variants/ht_variants/llp_variants module
                                                          # (including a plain grep for "ACRF"); no
                                                          # collision found. The nearest look-alike,
                                                          # occm.py's own "AIRCRAFT REG. :", is a different
                                                          # phrase (neither a substring of the other).
    "TRPSTATUS",                                         # trp_status_dual_layer_scanned.py -- this
                                                          # file's own title, "TRP STATUS", decodes with
                                                          # no space via plain extract_text() despite the
                                                          # rest of the page's text layer being an
                                                          # unusable doubled/garbled jumble (see that
                                                          # module's own docstring). Checked against every
                                                          # SIGNATURES list in occm.py/ht.py/llp.py and
                                                          # every occm_variants/ht_variants/llp_variants
                                                          # module (including a plain grep for "TRP
                                                          # STATUS"/"TRPSTATUS"); no collision found.
    "Hard Time Components List",                         # fl_compound_code_ht.py -- this file's own
                                                          # title-line phrase (plural "Components"),
                                                          # deliberately not the shared column-header
                                                          # line it has in common with its OCCM-flavored
                                                          # sibling occm_variants/fl_compound_code_occm.py
                                                          # (see that module's own SIGNATURES for why).
                                                          # Checked against every SIGNATURES list in
                                                          # occm.py/ht.py/llp.py and every
                                                          # occm_variants/ht_variants/llp_variants module
                                                          # (including a plain grep for "hard time
                                                          # components list", case-insensitive); no
                                                          # collision found -- not a substring of, and
                                                          # does not contain as a substring, this same
                                                          # file's own singular "HARD TIME COMPONENT LIST"
                                                          # entry above (hard_time_component_list.py).
    "MAINTENANCE STATUS REPORT Report ERM1",             # maintenance_status_report_erm1.py -- this
                                                          # file's own title line, verbatim, including
                                                          # the report-ID suffix. Deliberately NOT the
                                                          # bare "MAINTENANCE STATUS REPORT" phrase alone
                                                          # -- that shorter phrase is already
                                                          # occm.py's own (broader) top-level signature
                                                          # for its sibling report ID, PR21
                                                          # (occm_variants/maintenance_status_report_
                                                          # pr21.py); this HT-flavored ERM1 report shares
                                                          # the same "Aircraft Inventory and Maintenance
                                                          # System" MIS boilerplate but a structurally
                                                          # different (Hard-Time) row layout, so the full,
                                                          # more specific phrase (with "Report ERM1") is
                                                          # used here as the HT-side anchor -- since
                                                          # DETECTION_ORDER in sheet_types/router.py
                                                          # checks HT before OCCM, this specific phrase
                                                          # matches first and the file is never misrouted
                                                          # to occm.py's broader phrase. Checked against
                                                          # every SIGNATURES list in occm.py/ht.py/llp.py
                                                          # and every occm_variants/ht_variants/
                                                          # llp_variants module (including a plain grep
                                                          # for "ERM1"); no collision found.
    "HT COMPONENTS STATUS",                              # ht_components_status_ruled_grid.py --
                                                          # this template's own bare title line
                                                          # (plural COMPONENTS, singular STATUS, no
                                                          # "HARD TIME"/"FOR A/C-REGISTRATION"/"LIST"/
                                                          # "REPORT" suffix). Checked against every
                                                          # SIGNATURES list in occm.py/ht.py/llp.py and
                                                          # every occm_variants/ht_variants/llp_variants
                                                          # module (including a plain grep for "HT
                                                          # COMPONENTS STATUS"); no collision found --
                                                          # not a substring of, and does not contain as
                                                          # a substring, georgian_airways_ht_components_
                                                          # status.py's own "HARD TIME COMPONENTS STATUS
                                                          # FOR A/C-REGISTRATION" or hard_time_status_
                                                          # mpd_cert_fin.py's own "HARD TIME COMPONENTS
                                                          # STATUS" (both start with "HARD TIME", not the
                                                          # bare "HT" this template uses).
    "LIMITE CONTROL CHECK",                              # ht_components_list_limite_control.py --
                                                          # this template's own header-row phrase,
                                                          # verbatim, present on every page of the
                                                          # sample file (unlike its "HT COMPONENTS
                                                          # LIST" title line, which the sample's own
                                                          # first page omits). Checked against every
                                                          # SIGNATURES list in occm.py/ht.py/llp.py and
                                                          # every occm_variants/ht_variants/llp_variants
                                                          # module (including a plain grep for "LIMITE
                                                          # CONTROL"); no collision found.
    "Fitted to part Fitted to serial",                   # oases_component_report_fitted_to_matrix.py
                                                          # -- this OASES export's own repeating
                                                          # column-header line, checked directly
                                                          # against every SIGNATURES list in
                                                          # sheet_types/{occm,ht,llp}.py and every
                                                          # existing occm_variants/ht_variants/
                                                          # llp_variants module file; no collision
                                                          # found. Used instead of the report's own
                                                          # title line ("... Component Report") since
                                                          # that shorter phrase is a substring of
                                                          # oases_lifed_components.py's own anchor
                                                          # ("Lifed Component Report") and would be
                                                          # ambiguous as a sheet-type-level signature.
    "HT Aircraft Component LOG",                         # ht_aircraft_component_log.py -- this
                                                          # template's own title line, verbatim.
                                                          # Checked against every SIGNATURES list in
                                                          # occm.py/ht.py/llp.py and every
                                                          # occm_variants/ht_variants/llp_variants
                                                          # module; no collision found. NOTE: this
                                                          # phrase contains occm.py's own broader
                                                          # generic "AIRCRAFT COMPONENT LOG" entry
                                                          # (Georgian Airways variant) as a substring --
                                                          # not a problem for sheet_types/router.py's
                                                          # top-level dispatch, since DETECTION_ORDER
                                                          # there checks HT before OCCM, so this
                                                          # sheet-type's own SIGNATURES list (this one)
                                                          # is matched first and OCCM's broader phrase
                                                          # is never reached for this file.
    "AIRFRAME HTC/LLP STATUS",                           # airframe_htc_llp_status.py -- this
                                                          # template's own title line, verbatim.
                                                          # Checked against every SIGNATURES list in
                                                          # occm.py/ht.py/llp.py and every
                                                          # occm_variants/ht_variants/llp_variants
                                                          # module (including a plain grep for
                                                          # "HTC/LLP", "HTC / LLP" and "HTC LLP"); no
                                                          # collision found. Not a substring of, and
                                                          # does not contain as a substring,
                                                          # htll_status.py's own "HT-LL STATUS"/
                                                          # "HT&LLP STATUS" (different abbreviation,
                                                          # "HTC" not "HT", different punctuation).
    "HARD TIME COMPONENTS STATUS REPORT",                # hard_time_day_fhr_cyc_matrix_scanned.py --
                                                          # this phrase decodes cleanly through the
                                                          # file's own otherwise badly scrambled
                                                          # baked-in OCR text layer (see that module's
                                                          # own docstring for why the rest of the page
                                                          # isn't trustworthy). Checked against every
                                                          # SIGNATURES list in occm.py/ht.py/llp.py and
                                                          # every occm_variants/ht_variants/llp_variants
                                                          # module (including a plain grep for
                                                          # "COMPONENTS STATUS REPORT" and "HARD TIME
                                                          # COMPONENTS"); no collision found -- not a
                                                          # substring of, and does not contain as a
                                                          # substring, georgian_airways_ht_components_
                                                          # status.py's own "HARD TIME COMPONENTS STATUS
                                                          # FOR A/C-REGISTRATION" (diverges right after
                                                          # "STATUS").
]


def _read_head_text(pdf_path: str, n_pages: int = 3) -> str:
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
        # No usable text layer -- likely a scanned PDF. Ask any OCR-capable
        # variant to confirm its own template via a cheap header OCR pass
        # rather than guessing (mirrors occm.py/llp.py). Without this block,
        # router.py's own OCR-fallback loop can still correctly resolve
        # sheet_type="HT" for a blank-text file (it checks every sheet
        # type's variants directly), but then this function -- called next,
        # to pick the specific variant -- would return "Unknown" regardless,
        # since it only checked plain-text SIGNATURES above.
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


def normalize_and_validate(records: list[dict], variant_name: str = "Vietnam Airlines") -> list[dict]:
    v = _BY_NAME.get(variant_name, vietnam_airlines)
    return [clean_record(dict(r), v.RULES) for r in records]
