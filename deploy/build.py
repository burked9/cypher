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
    # OCCM variant added 2026-09-05 — "MSN <msn> OCCM PART STATUS" header,
    # real text layer, row anchored on trailing (POSITION, INST_DATE, TSN,
    # CSN)-shaped tokens rather than word x-position.
    "sheet_types/occm_variants/occm_part_status.py",
    # OCCM variant added 2026-09-05 — two-description-column layout ("ATA
    # DESCRIPTION PART NO. SERIAL NO. DESCRIPTION2 POS. INST-DATE" header),
    # real text layer, word x-position bucketing; row anchor differs from
    # occm_summary_list.py's sibling format since only the chapter-heading
    # row (not every row) starts with an ATA-shaped token here.
    "sheet_types/occm_variants/occm_dual_description_list.py",
    # OCCM variant added 2026-09-05 — "OCCM Control Sheet" header block,
    # real text layer, word x-position bucketing; unusual column order with
    # ATA as the LAST column (DESCRIPTION/PN/SN/POSITION/INSTALL_DATE/FH/
    # FC/TSI/CSI/ATA) rather than first as in several sibling variants.
    "sheet_types/occm_variants/occm_control_sheet.py",
    # OCCM variant added 2026-09-05 — "All Fitted Aircraft Component LOG"
    # header block (AIRCRAFT <reg> / SINCE NEW HOUR / CYCLES / UNIT REMOVAL
    # BASED ON.../A/C at installation), real text layer, word x-position
    # bucketing; PART_NUMBER/DESCRIPTION print once per part group and are
    # blank on subsequent same-group rows (left as literal blanks, not
    # forward-filled).
    "sheet_types/occm_variants/all_fitted_aircraft_component_log.py",
    # OCCM variant added 2026-09-05 — "MSN <msn> OCCM COMPONENT INVENTORY"
    # header, real text layer, plain token splitting (no word x-position
    # needed); row anchored on a trailing ISO installed-date token, with
    # multi-line PART_DESCRIPTION wraps reassembled from the bare
    # description-only lines either side of the row's own data line.
    "sheet_types/occm_variants/occm_component_inventory.py",
    # OCCM variant added 2026-09-05 — "OCCM Listing" header block (<model> /
    # MSN <msn> Regn <reg> / OCCM Listing / Total Aircraft Hours <n> and <n>
    # Flight Cycles), real text layer, word x-position bucketing; the header
    # row's own "Unit" column is never populated on the real sample (data
    # fills flush against Description instead), so UNIT is always emitted
    # empty. Row anchored on a bare 2-digit ATA in the leftmost column.
    "sheet_types/occm_variants/occm_listing.py",
    # OCCM variant added 2026-09-05 — "<facility> sn <msn> OCCM Component"
    # header block, real text layer, word x-position bucketing (tight
    # x_tolerance to split an ATA glued directly onto PART_NUMBER with no
    # space). Six-column trailing time group (TAH Inst/TAC Inst/TSI/CSI/
    # TSN/CSN) and CON vocabulary (IN/IT/MO/NE/OH/RE/SV/TE) both confirmed
    # distinct from occm_list_msn_dotdate.py's own four-column trailing
    # group and different CON set.
    "sheet_types/occm_variants/occm_component_status_facility_msn.py",
    # OCCM variant added 2026-09-05 — "<code> OC/CM(MSN<n>)" header block,
    # real text layer, word x-position bucketing across a paired "at
    # install" / "current" TSN/TSO/CSN/CSO layout; CSN/CSO at install are
    # sparsely populated on most rows (legitimate missing data, not a parse
    # gap) and an ambiguous numeric-region collision (rare, e.g. an upstream
    # "#REF!" export artifact) folds into STATUS_TRAIL rather than guessing.
    "sheet_types/occm_variants/occm_component_data_install_current.py",
    # OCCM variant added 2026-09-05 — "Serialized Component List" header
    # block (AIRCRAFT / AIRBUS <type> HOURS <n> / MSN <msn> CYCLES <n> /
    # REG <reg> DATE <date> / DOM <date>), real text layer, word
    # x-position bucketing (some middle columns -- P/N, S/N, Install Date,
    # TSN, CSN -- are legitimately blank together on a subset of rows).
    "sheet_types/occm_variants/serialized_component_list.py",
    # OCCM variant added 2026-09-05 — "INSTALLED PARTS LIST" header block
    # (StatusASAT/UnitMSN/Item type/UnitTSN/UnitCSN/reg+serial/UnitDSN),
    # real text layer, row anchored purely by exactly-8-token count plus a
    # date-shaped 6th token (no word x-position bucketing needed); header
    # metadata locked from the first page where every field parses cleanly,
    # since later pages carry occasional rendering glitches on the same
    # fields.
    "sheet_types/occm_variants/installed_parts_list.py",
    # OCCM variant added 2026-09-05 — "<report_id> SERIALIZATION LIST by ATA
    # CHAPTER" header block, landing-gear-focused parts serialization/
    # interchangeability list (tracks verification status, not TSN/CSN
    # flight-hour life), real text layer, word x-position bucketing;
    # LIFED/MANUF_DATE/SERIAL/INTRCHGE/RPLCBLE are independent marker
    # columns not mutually exclusive or sequential, and a stray token that
    # can't be confirmed as belonging to a marker column is folded into
    # STATUS_TRAIL rather than guessed (see the module docstring).
    "sheet_types/occm_variants/serialization_list_by_ata.py",
    # OCCM Index — born-digital, full text layer; ATA/DESCRIPTION/
    # PART_NUMBER/SERIAL_NUMBER/INSTALL_DATE/TSN/CSN rows anchored on the
    # trailing install-date token, with MSN/type/reg/MFG/FH/FC/report-date
    # header metadata stamped on every row.
    "sheet_types/occm_variants/occm_index.py",
    # Assembly Configuration / Status Report — born-digital, full text
    # layer; each component prints as 4 physical lines (FHR/CYC/CAL basis
    # rows plus a trailing serial/position/GRN line), CON-token x-position
    # anchored (not text search, since the same literal tokens also appear
    # as trailing status values); expanded to 3 rows per component with a
    # BASIS column, ambiguous per-basis numeric trail kept verbatim in
    # STATUS_TRAIL rather than force-split into named sub-columns.
    "sheet_types/occm_variants/assembly_configuration_status_report.py",
    # Maintenance Status Report (Report PR21) — born-digital, full text
    # layer; "Aircraft Inventory and Maintenance System" export with no
    # "OCCM" text anywhere in it (confirmed via direct inspection). Each
    # record spans 2+ physical lines anchored on a TASK_CODE (C/M or O/C)
    # token; the raw span between SERIAL_NUMBER and LOG_REF on line 2, and
    # any extra continuation lines restating TASK_CODE with an alternate
    # time basis, fold into POSITION/STATUS_TRAIL verbatim rather than
    # being guessed apart (see the module docstring).
    "sheet_types/occm_variants/maintenance_status_report_pr21.py",
    # "COMPONENT LIST" Kardex-style OCCM summary — born-digital, real text
    # layer (noisy per-page OCR-like re-render, not scanned), no "OCCM"
    # text anywhere in it (confirmed via direct inspection). Rows anchored
    # on tail-registration + TYPE token; multi-line descriptions resolved
    # by which neighbouring row's own description cell is empty (see the
    # module docstring for the full geometric-attribution rule).
    "sheet_types/occm_variants/component_list_kardex.py",
    # A/C Installed Parts Print — born-digital, real text layer; each
    # component spans 2 physical lines (a P/N-anchored data line plus a
    # trailing DESCRIPTION line), row anchored from the right via a TIME
    # token immediately preceding an ATA token (POSITION is variable-
    # length so cannot be anchored by fixed token count); the constant
    # per-row "A/C" tail code and report date are parsed once and stamped
    # as header metadata. On a confirmed minority of real rows the
    # POSITION+DATE span is character-interleaved in the source PDF's own
    # text stream and unparseable -- those are left blank and folded into
    # STATUS_TRAIL verbatim rather than guessed (see the module
    # docstring).
    "sheet_types/occm_variants/aircraft_installed_parts_print.py",
    # OCCM COMPONENTS STATUS — born-digital, full text layer with
    # character-substitution noise (same "real but noisy" pattern as
    # llp_variants/engine_items_control_llp_status.py), no OCR needed.
    # Two page layouts (letterhead first/last page vs plain interior
    # pages) handled via proportional column-fraction interpolation per
    # row plus a small per-layout absolute-boundary table for the
    # trailing TTSN/TCSN/TSI/CSI/DOCUMENT span; ambiguous orphan
    # fragments fold into STATUS_TRAIL rather than being guessed (see
    # the module docstring).
    "sheet_types/occm_variants/occm_components_status.py",
    # OCCM Component (Corrected A/C Data at Install) — born-digital, full
    # text layer; "OCCM COMPONENT" header block (A/C TSN/A/C CSN/AS OF,
    # parsed once from page 1 only -- it does not repeat per page), word
    # x-position bucketing across a paired "Corrected A/C Data at Install" /
    # "Component Data at Install" TSN/TSO/CSN/CSO layout (distinct from
    # occm_component_data_install_current.py's own "at install"/"current"
    # pairing, despite sharing one literal header phrase -- see that
    # module's docstring and sheet_types/occm.py's VARIANTS ordering note).
    # Each record spans 2 (occasionally 3) physical lines, grouped by
    # anchoring on the DESCRIPTION column rather than line-gap proximity
    # (the gap between a record's own continuation line and the next
    # record's first line is not reliably larger). An ambiguous numeric-
    # region collision folds into STATUS_TRAIL rather than guessing.
    "sheet_types/occm_variants/occm_component_ac_corrected_at_install.py",
    # OCCM List (Certificate/Remark) — born-digital, full text layer;
    # word x-position column bucketing with a per-page header cutoff
    # anchored on the header's own "Remark" word (the column-header line's
    # vertical position isn't fixed page to page on this format's known
    # source file). Multi-line DESCRIPTION wraps above and/or below its
    # anchor row and is reassembled by nearest-anchor vertical proximity;
    # anything not confidently a description continuation folds into
    # STATUS_TRAIL rather than being guessed (see the module docstring).
    "sheet_types/occm_variants/occm_list_cert_remark.py",
    # OC/CM Components (Installation / Current) — born-digital, full text
    # layer; fixed 5-line per-page header (AIRCRAFT_TYPE/AIRCRAFT_REG/
    # CURRENT_DATE/MSN/MFD/TOTAL_AIRCRAFT_HOURS/TOTAL_AIRCRAFT_CYCLES)
    # parsed once per page and stamped onto every row; word x-position
    # column bucketing across a paired "INSTALLATION" (DATE/TAT/TAC) /
    # "CURRENT" (TSN/CSN) layout, distinct from occm_component_data_
    # install_current.py's own differently-shaped install/current pairing.
    # Row validity needs no marker-string matching: every genuine row's
    # first two buckets are clean Item/ATA integers, which the repeating
    # header/footer/signature-block noise never produces. A genuine
    # numeric-bucket split collision folds into STATUS_TRAIL rather than
    # guessing (see the module docstring).
    "sheet_types/occm_variants/oc_cm_components_install_current.py",
    # Aircraft OCCM List (H/C/D Basis) -- complex multi-line-per-component
    # export (one main line + three H/C/D basis sub-lines per component),
    # real text layer, no OCR needed.
    "sheet_types/occm_variants/aircraft_occm_list_hcd.py",
    # OCCM Components Control (S.M.A. MIS, form PASCOM1R) -- real text
    # layer, no OCR needed.
    "sheet_types/occm_variants/occm_components_control_sma.py",
    # On Condition Monitoring Components ("<operator> ATA <n>[-<n>] ON
    # CONDITION MONITORING COMPONENTS" title) -- real text layer, no OCR
    # needed; rows parsed by right-anchored token shape rather than
    # x-position bucketing, since column x-positions shift page to page and
    # a minority of pages carry no repeated column-header line to derive
    # per-page anchors from.
    "sheet_types/occm_variants/on_condition_monitoring_components.py",
    # OCCM Component Status Report ("OCCM COMPONENT STATUS" title, singular
    # "Component") -- real text layer, real but heavily OCR-noise-corrupted
    # (character-substitution pattern), no OCR needed; rows parsed by word
    # x-position bucketing.
    "sheet_types/occm_variants/occm_component_status_report.py",
    # Component Fit List ("COMPONENT FIT LIST" title) -- real text layer,
    # no OCR needed; rows parsed by word x-position bucketing, with a
    # deterministic per-row de-interleave for a rare doubled-character
    # rendering artifact (see the module's own docstring).
    "sheet_types/occm_variants/component_fit_list.py",
    # Serialised Components Report ("Serialised Components Report" title,
    # British spelling) -- real text layer, no OCR needed; rows anchored
    # by an ATA-chapter-subchapter token and parsed by word x-position
    # bucketing. Only the main repeating detail table is modeled; the
    # page-1-only "life-limited parts" summary section uses an unrelated
    # multi-line layout and isn't parsed (see the module's own docstring).
    # Everything right of Serial Number (logbook/date/hours/work-order
    # columns) has no reliable per-column boundary on the real sample file
    # and is kept as one free-text STATUS_TRAIL column rather than guessed.
    "sheet_types/occm_variants/serialised_components_report.py",
    # OCCM UIC Status ("OCCMUIC <reg> (MSN <msn>), TSN: ..., CSN: ..."
    # aircraft-summary line) -- real text layer, no OCR needed; rows parsed
    # by word x-position bucketing with a wider row-clustering tolerance
    # than most sibling modules to cope with this file's own wider word
    # scatter within a logical row (see the module's own docstring).
    "sheet_types/occm_variants/occm_uic_status.py",
    # Condition Monitoring Components Status -- real text layer, no OCR
    # needed; rows detected via PART_NUMBER/SERIAL_NUMBER-shaped anchor
    # tokens (falling back to plain line-clustering on the small minority
    # of pages with no such anchor at all) and columns parsed by word
    # x-position bucketing. Everything right of POSITION (install date /
    # hours / cycles / TSN-ish values) has no reliable per-column boundary
    # on the real sample file -- values were observed glued together,
    # duplicated, and/or out of the document's own row order -- so it's
    # kept as one free-text STATUS_TRAIL column rather than guessed (see
    # the module's own docstring for the full reliability discussion).
    "sheet_types/occm_variants/condition_monitoring_components_status.py",
    # On-Condition Components Report (Install / Current) -- real text
    # layer, no OCR needed; page 1 is a cover/signature page only (real
    # data table starts page 2). Columns parsed by word x-position
    # bucketing: left-aligned leading fields by x0, the six trailing
    # numeric columns (right-aligned) by x1 instead, since digit count
    # otherwise shifts x0 across column boundaries (see the module's own
    # docstring).
    "sheet_types/occm_variants/on_condition_components_install_current.py",
    # Aircraft Fitlist (OCCM) -- scanned, no text layer, async OCR bridge
    # (render_page/ocr_text/page_count), same pattern as this batch's other
    # scanned OCCM variants.
    "sheet_types/occm_variants/aircraft_fitlist_occm.py",
    # OCCM List (Func.loc / A/C Hours Header) -- scanned, no text layer,
    # async OCR bridge (render_page/ocr_words/ocr_text/page_count), same
    # pattern as this batch's other scanned OCCM variants.
    "sheet_types/occm_variants/occm_list_func_loc_scanned.py",
    # On Condition Items (OCCM Status) -- scanned, no text layer, async OCR
    # bridge (render_page/ocr_text/ocr_words/page_count), same pattern as
    # this batch's other scanned OCCM variants.
    "sheet_types/occm_variants/occm_status_on_condition_items.py",
    # Component List OCCM- Airframe -- scanned, no text layer, async OCR
    # bridge (render_page/ocr_text/ocr_words/page_count), same pattern as
    # this batch's other scanned OCCM variants.
    "sheet_types/occm_variants/component_list_occm_airframe.py",
    # COMPONENTES OC/CM -- scanned, no text layer, async OCR bridge
    # (render_page/ocr_text/ocr_words/page_count), same pattern as this
    # batch's other scanned OCCM variants.
    "sheet_types/occm_variants/componentes_oc_cm.py",
    # OCCM List (MSN-Prefixed Title) -- scanned, no text layer, async OCR
    # bridge (render_page/ocr_text/ocr_words/page_count), same pattern as
    # this batch's other scanned OCCM variants.
    "sheet_types/occm_variants/msn_occm_list_scanned.py",
    # On Condition, Condition Monitoring Components List -- scanned, no
    # text layer, async OCR bridge (render_page/ocr_text/ocr_words/
    # page_count), same pattern as this batch's other scanned OCCM
    # variants.
    "sheet_types/occm_variants/on_condition_cm_components_list.py",
    # OCCM Parts Compliance Status Report -- scanned, no text layer, async
    # OCR bridge (render_page/ocr_text/ocr_words/page_count), same pattern
    # as this batch's other scanned OCCM variants.
    "sheet_types/occm_variants/occm_parts_compliance_status.py",
    # On-Component/ Component Monitoring Listing Status -- scanned, no text
    # layer, async OCR bridge (render_page/ocr_text/ocr_words/page_count),
    # same pattern as this batch's other scanned OCCM variants.
    "sheet_types/occm_variants/on_component_monitoring_listing_status.py",
    # OCCM Inventory (Spanish SAP-style header) -- real text layer, single-
    # line rows, compound Ubicac.técnica/Material columns split per its own
    # module docstring.
    "sheet_types/occm_variants/occm_inventory_sap_es.py",
    # OCCM Component Status (Parent Serial / TSN-CSN Grid, Scanned) --
    # scanned, no text layer, async OCR bridge, ruled-grid row/column
    # detection via numpy darkfrac scan + per-cell OCR fallback, same
    # pattern as this batch's other scanned OCCM variants.
    "sheet_types/occm_variants/occm_component_status_parent_serial_grid.py",
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
