// Cypher — Pyodide bootstrap and UI wiring.
//
// Loads Pyodide, installs pdfplumber + pymupdf via micropip, mounts our Python
// modules into the Pyodide virtual filesystem, then routes PDF bytes through
// main.run() which auto-detects the OCCM variant and dispatches.

import { hasTextLayer } from "./ocr_bridge.js?__CACHE_BUST__";

const NO_TEXT_LAYER_WARNING = (
  "This PDF has no extractable text layer, which usually means it's a " +
  "scanned or image-only document. This build has no in-browser OCR yet " +
  "(Tesseract.js isn't wired in), so it can't be processed here. If you " +
  "have local Python access to this project, the local pipeline already " +
  "handles some scanned formats."
);

const $ = (id) => document.getElementById(id);
const status = $("status");
let pyodide = null;
let lastResult = null;

// Python module list comes from _pymods/manifest.json, which is regenerated
// every time deploy/build.py runs. This means changes to module structure
// only require updating build.py — no parallel JS edits needed. (Previously
// adding a new variant required editing both files; build.py and app.js
// would silently drift, breaking the deploy.)
let PY_FILES = null;   // populated at boot

// Python's http.server (and possibly a future host) sends no strong
// cache-control headers, so browsers are free to serve a stale cached copy
// of any of these on a repeat visit -- after any future deploy update, a
// returning visitor could keep running yesterday's Python modules with no
// indication anything is wrong. One cache-busting query param per page
// load, applied to every mounted-file fetch, forces a fresh copy each time
// without needing no-store everywhere.
const _cacheBust = Date.now();
function _bust(path) {
  return path + (path.includes("?") ? "&" : "?") + "v=" + _cacheBust;
}

async function fetchText(path) {
  const resp = await fetch(_bust(path));
  if (!resp.ok) throw new Error(`Failed to fetch ${path}: ${resp.status}`);
  return resp.text();
}

async function boot() {
  status.textContent = "Loading Pyodide…";
  pyodide = await loadPyodide();

  status.textContent = "Installing pdfplumber (one-time, ~10 s)…";
  await pyodide.loadPackage("micropip");
  await pyodide.runPythonAsync(`
import micropip
# IMPORTANT: pin to pdfplumber 0.9.0. From 0.10 onwards pdfplumber requires
# pypdfium2, which is a C extension with no Pyodide-compatible wheel.
# 0.9.0 is the last release that uses pure-Python pdfminer.six only.
# Pillow comes from Pyodide's bundled package set (no micropip needed).
await micropip.install(["pdfplumber==0.9.0"])
`);

  status.textContent = "Mounting modules…";
  // Pull the manifest written by deploy/build.py.
  const manifestResp = await fetch(_bust("_pymods/manifest.json"));
  if (!manifestResp.ok) {
    throw new Error("Could not fetch _pymods/manifest.json — did you run deploy/build.py?");
  }
  const manifest = await manifestResp.json();
  PY_FILES = [...manifest.files, manifest.main_entry];

  for (const entry of PY_FILES) {
    const content = await fetchText(entry.fetch);
    const parts = entry.mount.split("/");
    let dir = "/home/pyodide";
    for (let i = 0; i < parts.length - 1; i++) {
      dir += "/" + parts[i];
      try { pyodide.FS.mkdir(dir); } catch (_) { /* exists */ }
    }
    pyodide.FS.writeFile(`/home/pyodide/${entry.mount}`, content);
  }

  // If a Bloom filter binary is shipped, copy it into Pyodide's filesystem
  // alongside shared/pn_master.py so the loader finds it.
  try {
    const bloomResp = await fetch(_bust("_pymods/shared/pn_master.bloom"));
    if (bloomResp.ok) {
      const buf = new Uint8Array(await bloomResp.arrayBuffer());
      pyodide.FS.writeFile("/home/pyodide/shared/pn_master.bloom", buf);
    }
  } catch (_) { /* no master bundled — optional */ }
  await pyodide.runPythonAsync(`
import sys
if "/home/pyodide" not in sys.path:
    sys.path.insert(0, "/home/pyodide")
import main
`);

  status.textContent = "Ready. Choose a PDF.";
  $("run").disabled = false;
  // Combined-mode pair button is enabled once both files are chosen
  // (the picker change handlers manage that).
}

// ---------------------------------------------------------------------------
// Mode selector — toggles between single-PDF and OCCM+HT combined input
// ---------------------------------------------------------------------------
document.querySelectorAll("input[name='mode']").forEach((radio) => {
  radio.addEventListener("change", () => {
    const mode = document.querySelector("input[name='mode']:checked").value;
    $("action-single").hidden = (mode !== "single");
    $("action-combined").hidden = (mode !== "combined");
    hide("variant-info"); hide("summary"); hide("downloads");
    $("results").innerHTML = "";
    $("empty-state").hidden = false;
    status.textContent = (mode === "combined"
      ? "Combined mode — choose one OCCM PDF and one HT PDF."
      : "Choose a PDF.");
  });
});

function _updateCombinedReady() {
  const haveBoth = $("occm-input").files[0] && $("ht-input").files[0];
  const btn = $("run-combined");
  if (btn) btn.disabled = !haveBoth || !pyodide;
}
["occm-input", "ht-input"].forEach((id) => {
  const el = $(id);
  if (!el) return;
  el.addEventListener("change", () => {
    const lbl = $(id === "occm-input" ? "occm-picker-label" : "ht-picker-label");
    const f = el.files[0];
    if (lbl) lbl.textContent = f ? f.name : (id === "occm-input" ? "Choose OCCM PDF" : "Choose HT PDF");
    _updateCombinedReady();
  });
});

boot().catch((e) => {
  status.textContent = "Failed to load: " + e.message;
  console.error(e);
});

$("pdf-input").addEventListener("change", () => {
  const f = $("pdf-input").files[0];
  $("file-picker-label").textContent = f ? f.name : "Choose a PDF";
  status.textContent = f
    ? `Loaded ${f.name} (${(f.size / 1024).toFixed(1)} KB) — click Extract.`
    : "No file.";
  if (f) markStep(1, "done");
});

function markStep(n, state) {
  const li = document.querySelector(`.step[data-step="${n}"]`);
  if (!li) return;
  li.classList.remove("current", "done");
  if (state) li.classList.add(state);
  // Advance the next step to "current" if the previous is done
  if (state === "done") {
    const next = document.querySelector(`.step[data-step="${n + 1}"]`);
    if (next && !next.classList.contains("done")) next.classList.add("current");
  }
}

$("run").addEventListener("click", async () => {
  const f = $("pdf-input").files[0];
  if (!f) { status.textContent = "Choose a PDF first."; return; }

  markStep(2, "current");
  status.textContent = `Detecting variant and extracting from ${f.name}…`;
  $("run").disabled = true;
  hide("variant-info"); hide("summary"); hide("downloads");
  $("results").innerHTML = "";
  hide("empty-state");

  try {
    // Fast pre-check in pdf.js, BEFORE ever touching Pyodide: confirmed that
    // pdfplumber/pdfminer.six under Pyodide can take 2.5+ minutes with zero
    // feedback on a genuinely scanned PDF (root cause not identified --
    // ruled out image size/format/count, cold-import cost, and
    // page.chars vs extract_text() as explanations). pdf.js is a separate
    // codebase with no such issue: both known-hanging files processed in
    // under 600ms here. If this pre-check itself fails for any reason,
    // fall through to the normal path rather than block on it -- it's a
    // fast-path optimization, not a gate.
    let hasText = true;
    try {
      const checkBuf = await f.arrayBuffer();
      hasText = await hasTextLayer(new Uint8Array(checkBuf));
    } catch (checkErr) {
      console.warn("Text-layer pre-check failed, proceeding without it:", checkErr);
    }
    if (!hasText) {
      const data = { ok: true, sheet_type: "Unknown", variant: "Unknown",
                      columns: [], rows: [], warning: NO_TEXT_LAYER_WARNING };
      lastResult = data;
      render(data, f.name);
      return;
    }

    const buf = await f.arrayBuffer();   // fresh read -- pdf.js may have detached the check buffer
    pyodide.FS.writeFile("/tmp/_input.pdf", new Uint8Array(buf));
    const jsonStr = await pyodide.runPythonAsync(`
import json
with open("/tmp/_input.pdf", "rb") as fh:
    _bytes = fh.read()
json.dumps(main.run(_bytes))
`);
    const data = JSON.parse(jsonStr);
    lastResult = data;
    render(data, f.name);
  } catch (e) {
    status.textContent = "Error: " + e.message;
    console.error(e);
  } finally {
    $("run").disabled = false;
  }
});

function render(data, fname) {
  if (!data.ok) {
    showStatus(`Extraction failed: ${data.error || "unknown"}`, "error");
    return;
  }

  // Sheet type + variant info
  const variant = data.variant || "Unknown";
  const sheetType = data.sheet_type || "Unknown";
  const tagCls = ({ "AMOS": "tag-amos", "Aeroflot": "tag-aero",
                    "China Eastern": "tag-ce", "Vietnam Airlines": "tag-vie" }[variant]) || "tag-unk";
  $("variant-info").hidden = false;
  $("variant-info").innerHTML =
    `Sheet type: <strong>${escapeHtml(sheetType)}</strong> &middot; ` +
    `Variant: <span class="tag ${tagCls}">${escapeHtml(variant)}</span>`;

  // Warning case
  if (data.warning) {
    showStatus(data.warning, "warning");
    return;
  }

  status.textContent = "Done.";
  markStep(2, "done");
  markStep(3, "done");

  // Summary
  const s = data.summary || { total: data.rows.length, clean: 0, flagged: 0, imputed_ata: 0 };
  $("summary").hidden = false;
  $("summary").innerHTML =
    `<strong>${s.total}</strong> rows extracted &middot; ` +
    `<strong>${s.clean}</strong> clean &middot; ` +
    `<strong>${s.flagged}</strong> flagged for review &middot; ` +
    `<strong>${s.imputed_ata}</strong> imputed ATA`;

  // Table with filter controls
  const cols = data.columns;
  const rows = data.rows;
  const tableId = "results-table";
  let html = `<div class="table-controls">
    <input type="text" class="search-box" placeholder="Filter rows…" oninput="filterTable(this.value)">
    <label><input type="checkbox" onchange="toggleFlagged(this.checked)"> Flagged only</label>
    <span class="row-count" id="row-count">${rows.length} rows shown</span>
  </div><div class="table-scroll"><table id="${tableId}"><thead><tr>`;
  for (const c of cols) html += `<th>${escapeHtml(c)}</th>`;
  html += "</tr></thead><tbody>";
  for (const r of rows) {
    const flagged = r._issues ? "flagged" : "";
    html += `<tr class="${flagged}" data-flagged="${r._issues ? 1 : 0}">`;
    for (const c of cols) {
      const v = r[c] == null ? "" : String(r[c]);
      const cls = c === "_issues" ? "issues" : "";
      html += `<td class="${cls}">${escapeHtml(v)}</td>`;
    }
    html += "</tr>";
  }
  html += "</tbody></table></div>";
  $("results").innerHTML = html;

  // Downloads
  const csv = toCSV(rows, cols);
  const blob = new Blob([csv], { type: "text/csv" });
  $("download-csv").href = URL.createObjectURL(blob);
  $("download-csv").download = fname.replace(/\.pdf$/i, "") + "_cypher.csv";
  $("downloads").hidden = false;
}

// Expose simple filter functions on window for inline handlers
window.filterTable = function (query) {
  const table = $("results-table");
  if (!table) return;
  const rows = table.tBodies[0].rows;
  const q = query.toLowerCase();
  const flaggedOnly = table.dataset.flaggedOnly === "1";
  let shown = 0;
  for (const row of rows) {
    const visible = (!q || row.textContent.toLowerCase().includes(q))
                  && (!flaggedOnly || row.dataset.flagged === "1");
    row.style.display = visible ? "" : "none";
    if (visible) shown++;
  }
  $("row-count").textContent = `${shown} rows shown`;
};
window.toggleFlagged = function (on) {
  const table = $("results-table");
  if (!table) return;
  table.dataset.flaggedOnly = on ? "1" : "0";
  const search = document.querySelector(".search-box");
  window.filterTable(search ? search.value : "");
};

// ---------------------------------------------------------------------------
// Combined-mode Extract — pair two PDFs, then route through main.run_combined()
// ---------------------------------------------------------------------------
const runCombinedBtn = $("run-combined");
if (runCombinedBtn) runCombinedBtn.addEventListener("click", async () => {
  const occmFile = $("occm-input").files[0];
  const htFile   = $("ht-input").files[0];
  if (!occmFile || !htFile) { status.textContent = "Choose both PDFs first."; return; }
  const manualKey = ($("manual-key") && $("manual-key").value || "").trim();

  markStep(2, "current");
  status.textContent = `Pairing ${occmFile.name} ⟷ ${htFile.name}…`;
  $("run-combined").disabled = true;
  hide("variant-info"); hide("summary"); hide("downloads");
  $("results").innerHTML = "";
  hide("empty-state");

  try {
    // Same fast pre-check as the single-PDF path (see its comment for why):
    // catch a scanned PDF here in under a second rather than let Pyodide
    // hang on it for minutes. Checked independently per file so the error
    // names the actual problem drop zone.
    for (const [file, stage, label] of [[occmFile, "occm", "OCCM"], [htFile, "ht", "HT"]]) {
      let hasText = true;
      try {
        hasText = await hasTextLayer(new Uint8Array(await file.arrayBuffer()));
      } catch (checkErr) {
        console.warn("Text-layer pre-check failed, proceeding without it:", checkErr);
      }
      if (!hasText) {
        const data = { ok: false, stage,
          error: `The ${label} PDF ("${file.name}") has no extractable text layer ` +
                 `(looks scanned or image-only). This build has no in-browser OCR yet.` };
        lastResult = data;
        renderCombined(data);
        return;
      }
    }

    const occmBuf = await occmFile.arrayBuffer();   // fresh reads -- pdf.js may have detached the check buffers
    const htBuf   = await htFile.arrayBuffer();
    pyodide.FS.writeFile("/tmp/_occm.pdf", new Uint8Array(occmBuf));
    pyodide.FS.writeFile("/tmp/_ht.pdf",   new Uint8Array(htBuf));
    pyodide.globals.set("_manual_key", manualKey);
    // Original filenames, so shared/pairing.py's filename-derived fallback
    // (used when neither PDF's header carries a usable MSN/registration)
    // has something real to read instead of a temp path it never sees.
    pyodide.globals.set("_occm_filename", occmFile.name);
    pyodide.globals.set("_ht_filename", htFile.name);
    const jsonStr = await pyodide.runPythonAsync(`
import json
with open("/tmp/_occm.pdf", "rb") as fh: _occm = fh.read()
with open("/tmp/_ht.pdf", "rb") as fh:   _ht   = fh.read()
json.dumps(main.run_combined(_occm, _ht, _manual_key, _occm_filename, _ht_filename))
`);
    const data = JSON.parse(jsonStr);
    lastResult = data;
    renderCombined(data);
  } catch (e) {
    status.textContent = "Error: " + e.message;
    console.error(e);
  } finally {
    $("run-combined").disabled = false;
  }
});

function renderCombined(data) {
  if (!data.ok) {
    showStatus(`Extraction failed (${data.stage || "?"}): ${data.error || "unknown"}`, "error");
    return;
  }
  const pair = data.pair || {};
  const sevClass = pair.is_hard_mismatch ? "error"
                 : pair.status === "manual_override" ? "warning"
                 : pair.is_safe_auto_pair ? "" : "warning";
  $("variant-info").hidden = false;
  $("variant-info").innerHTML =
    `<strong>Pair:</strong> ${escapeHtml(pair.status || "?")} ` +
    `(${escapeHtml(pair.confidence || "")}) &middot; ` +
    `aircraft_key: <code>${escapeHtml(pair.aircraft_key || "(none)")}</code><br>` +
    `<small>OCCM: ${escapeHtml(pair.occm_filename || "")} — msn=${escapeHtml(pair.occm_msn || "-")}, reg=${escapeHtml(pair.occm_registration || "-")} &middot; ` +
    `HT: ${escapeHtml(pair.ht_filename || "")} — msn=${escapeHtml(pair.ht_msn || "-")}, reg=${escapeHtml(pair.ht_registration || "-")}</small>`;
  if (pair.warnings && pair.warnings.length) {
    $("variant-info").innerHTML += `<br><small class="warning">⚠ ${pair.warnings.map(escapeHtml).join("; ")}</small>`;
  }

  if (!data.combined_ok) {
    showStatus("Pair was a hard mismatch — combined view not generated. "
               + "Type an aircraft_key into the override box if you want to force a pair.", "warning");
    // Still expose per-sheet rows
    _renderPerSheetTabs(data);
    return;
  }

  const cov = data.combined.coverage;
  status.textContent = "Done.";
  markStep(2, "done"); markStep(3, "done");
  $("summary").hidden = false;
  $("summary").innerHTML =
    `<strong>${cov.both}</strong> joined slots &middot; ` +
    `<strong>${cov.occm_only}</strong> OCCM-only &middot; ` +
    `<strong>${cov.ht_only}</strong> HT-only &middot; ` +
    `<strong>${data.occm.rows.length + data.ht.rows.length}</strong> total source rows`;

  _renderPerSheetTabs(data);

  // Downloads — combined CSV is primary; per-sheet CSVs available too
  const occmCsv = toCSV(data.occm.rows, data.occm.columns);
  const htCsv   = toCSV(data.ht.rows,   data.ht.columns);
  const combinedCsv = toCSV(data.combined.rows, data.combined.columns);
  const ak = (data.pair && data.pair.aircraft_key) || "combined";
  $("downloads").hidden = false;
  $("downloads").innerHTML =
    `<a id="download-csv" download="${escapeHtml(ak)}_combined.csv" ` +
    `href="${URL.createObjectURL(new Blob([combinedCsv], {type:'text/csv'}))}">↓ Combined CSV</a>` +
    `<a download="${escapeHtml(ak)}_occm.csv" ` +
    `href="${URL.createObjectURL(new Blob([occmCsv], {type:'text/csv'}))}">↓ OCCM CSV</a>` +
    `<a download="${escapeHtml(ak)}_ht.csv" ` +
    `href="${URL.createObjectURL(new Blob([htCsv], {type:'text/csv'}))}">↓ HT CSV</a>`;
}

function _renderPerSheetTabs(data) {
  // Three stacked sections: Combined, OCCM, HT (combined section may be absent
  // when the pair was a hard mismatch).
  let html = "";
  if (data.combined_ok && data.combined && data.combined.rows.length) {
    html += `<h3 class="results-section-title">Combined slot view</h3>` +
            _buildResultsTable(data.combined.columns, data.combined.rows, "combined-table");
  }
  html += `<h3 class="results-section-title">OCCM rows (${data.occm.rows.length})</h3>` +
          _buildResultsTable(data.occm.columns, data.occm.rows, "occm-table");
  html += `<h3 class="results-section-title">HT rows (${data.ht.rows.length})</h3>` +
          _buildResultsTable(data.ht.columns, data.ht.rows, "ht-table");
  $("results").innerHTML = html;
}

function _buildResultsTable(cols, rows, id) {
  let html = `<div class="table-scroll"><table id="${id}"><thead><tr>`;
  for (const c of cols) html += `<th>${escapeHtml(c)}</th>`;
  html += "</tr></thead><tbody>";
  for (const r of rows) {
    const flagged = r._issues ? "flagged" : "";
    html += `<tr class="${flagged}">`;
    for (const c of cols) {
      const v = r[c] == null ? "" : String(r[c]);
      const cls = c === "_issues" || c === "slot_coverage" ? "issues" : "";
      html += `<td class="${cls}">${escapeHtml(v)}</td>`;
    }
    html += "</tr>";
  }
  html += "</tbody></table></div>";
  return html;
}

function hide(id) { const e = $(id); if (e) e.hidden = true; }
function showStatus(msg, type) {
  $("variant-info").hidden = false;
  $("summary").hidden = false;
  $("summary").className = "summary " + (type || "");
  $("summary").textContent = msg;
}
function toCSV(rows, cols) {
  const esc = (v) => {
    const s = v == null ? "" : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return [cols.map(esc).join(","), ...rows.map(r => cols.map(c => esc(r[c])).join(","))].join("\n");
}
function escapeHtml(s) {
  return s.replace(/[&<>"']/g, c => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[c]));
}
