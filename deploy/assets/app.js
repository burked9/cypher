// Cypher — Pyodide bootstrap and UI wiring.
//
// Loads Pyodide, installs pdfplumber + pymupdf via micropip, mounts our Python
// modules into the Pyodide virtual filesystem, then routes PDF bytes through
// main.run() which auto-detects the OCCM variant and dispatches.

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

async function fetchText(path) {
  const resp = await fetch(path);
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
  const manifestResp = await fetch("_pymods/manifest.json");
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
    const bloomResp = await fetch("_pymods/shared/pn_master.bloom");
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
}

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
    const buf = await f.arrayBuffer();
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
