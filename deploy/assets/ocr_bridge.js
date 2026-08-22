// Tesseract.js bridge — runs OCR client-side and hands word-level boxes to Python.
//
// Why a bridge: Pyodide cannot run Tesseract directly (the engine is a C++
// binary; pytesseract just shells out, and there's no `tesseract` binary in
// WebAssembly). Tesseract.js is a maintained WASM port maintained separately;
// it does not need Pyodide. The bridge:
//
//   1. Renders a PDF page to a Canvas via pdf.js.
//   2. Runs Tesseract.js on the canvas at PSM 12 (sparse text, the mode the
//      local L3 extractor settled on for bordered tables).
//   3. Hands the resulting word list + bounding boxes back to Python for
//      the existing column-projection logic in levels/L3_ocr/extract.py.
//
// Status: implemented for the Aeroflot OCCM variant only -- the one variant
// levels/L3_ocr/extract.py's column-projection logic (ATA/ZONE row anchors)
// was actually built for. Every other OCR-capable local variant (e.g. Part
// M's engine LLP sheet, grid-detection-based) has no browser-side path yet
// and would need its own detector + adapter, not a copy of this one.

const TESSERACT_CDN = "https://cdn.jsdelivr.net/npm/tesseract.js@5.0.5/dist/tesseract.min.js";
const PDFJS_WORKER  = "https://cdn.jsdelivr.net/npm/pdfjs-dist@4.0.379/build/pdf.worker.min.mjs";

let _tesseractLoaded = false;
let _pdfjsLib        = null;

async function loadTesseract() {
  if (_tesseractLoaded) return window.Tesseract;
  await new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = TESSERACT_CDN;
    s.onload = resolve;
    s.onerror = () => reject(new Error("Failed to load Tesseract.js"));
    document.head.appendChild(s);
  });
  _tesseractLoaded = true;
  return window.Tesseract;
}

async function loadPdfJs() {
  if (_pdfjsLib) return _pdfjsLib;
  // pdf.js is loaded via the <script type="module"> tag in index.html. We just
  // need to reach into globalThis once it's been imported.
  const lib = await import("https://cdn.jsdelivr.net/npm/pdfjs-dist@4.0.379/build/pdf.min.mjs");
  lib.GlobalWorkerOptions.workerSrc = PDFJS_WORKER;
  _pdfjsLib = lib;
  return lib;
}

/**
 * Fast text-layer check using pdf.js, run BEFORE handing bytes to Pyodide.
 *
 * Why this exists: pdfplumber/pdfminer.six under Pyodide can take minutes
 * (confirmed: 2.5+ min with zero feedback, on files as small as 89KB) to
 * determine that a genuinely scanned/image-only PDF has no text -- the
 * exact files most likely to need this check are the ones where the
 * Python-side check itself is what hangs. Root cause not identified (ruled
 * out: image size/format/count, cold-import cost, page.chars vs
 * extract_text()); all confirmed slow cases were genuinely zero-text scans.
 * pdf.js is a separate, mature codebase with no such issue -- confirmed
 * directly: both known-hanging files processed in under 600ms here, and a
 * real 30-page text PDF correctly returned 12k+ characters in ~1.5s.
 *
 * Returns true if the first `maxPages` pages have fewer than `threshold`
 * total characters combined.
 */
export async function hasTextLayer(pdfBytes, maxPages = 3, threshold = 50) {
  const lib = await loadPdfJs();
  const pdf = await lib.getDocument({ data: pdfBytes }).promise;
  let totalChars = 0;
  for (let i = 1; i <= Math.min(maxPages, pdf.numPages); i++) {
    const page = await pdf.getPage(i);
    const content = await page.getTextContent();
    totalChars += content.items.reduce((s, it) => s + (it.str || "").length, 0);
    if (totalChars >= threshold) return true;
  }
  return totalChars >= threshold;
}

// Takes an already-loaded pdf.js document proxy, not raw bytes -- pdf.js
// transfers (detaches) the underlying ArrayBuffer to its worker the moment
// getDocument() is called on it, so calling getDocument() a second time on
// the same bytes throws `DataCloneError: ArrayBuffer ... already detached`.
// Callers that need multiple pages (or a detect pass + a full OCR pass)
// must call getDocument() exactly once and reuse the resulting proxy.
async function renderPageToCanvas(pdf, pageNum, dpi = 300) {
  const page = await pdf.getPage(pageNum);
  const scale = dpi / 72;          // pdf.js default is 72 DPI; scale up for OCR
  const viewport = page.getViewport({ scale });
  const canvas = document.createElement("canvas");
  canvas.width  = viewport.width;
  canvas.height = viewport.height;
  await page.render({ canvasContext: canvas.getContext("2d"), viewport }).promise;
  return canvas;
}

/**
 * Run Tesseract on a canvas; return the words list with per-word bounding
 * boxes shaped to match what `pytesseract.image_to_data` returns locally.
 */
async function ocrCanvas(canvas) {
  const Tesseract = await loadTesseract();
  const result = await Tesseract.recognize(canvas, "eng", {
    tessedit_pageseg_mode: 12,
  });
  // Reshape Tesseract.js output to match the columns our Python extractor expects:
  //   left, top, width, height, conf, text
  return (result.data.words || [])
    .filter(w => w.text && w.text.trim() && w.confidence > 30)
    .map(w => ({
      left:   Math.round(w.bbox.x0),
      top:    Math.round(w.bbox.y0),
      width:  Math.round(w.bbox.x1 - w.bbox.x0),
      height: Math.round(w.bbox.y1 - w.bbox.y0),
      conf:   w.confidence,
      text:   w.text,
    }));
}

/**
 * Cheap page-1 OCR check for "is this the Aeroflot variant" -- the
 * in-browser mirror of `sheet_types/occm_variants/aeroflot.py`'s own
 * `ocr_detect()`, which can't run here (it needs fitz + pytesseract,
 * neither available under Pyodide). Same anchor text, same reasoning for
 * choosing it (confirmed against the real afl_test.pdf sample there): the
 * plain-text subject line reads reliably; the AEROFLOT wordmark sits in a
 * stylized logo graphic and is the wrong thing to anchor on.
 *
 * 300dpi, not a cheaper resolution: that Python-side check found "PART M"
 * (a different variant's anchor) misreading below 300dpi because of a
 * similar logo-graphic-adjacency issue. Never specifically tested this
 * phrase at lower DPI in a browser context, so this stays at the one
 * resolution actually confirmed to work rather than guessing a cheaper one.
 */
export async function detectAeroflot(pdfBytes) {
  try {
    const lib = await loadPdfJs();
    const pdf = await lib.getDocument({ data: pdfBytes }).promise;
    const canvas = await renderPageToCanvas(pdf, 1, 300);
    const w = canvas.width, h = canvas.height;
    const cropH = Math.round(h * 0.16);
    const cropTop = Math.round(h * 0.15);
    const cropCanvas = document.createElement("canvas");
    cropCanvas.width = w;
    cropCanvas.height = cropH;
    cropCanvas.getContext("2d").drawImage(canvas, 0, cropTop, w, cropH, 0, 0, w, cropH);
    const Tesseract = await loadTesseract();
    const result = await Tesseract.recognize(cropCanvas, "eng", { tessedit_pageseg_mode: 6 });
    const text = (result.data.text || "").toUpperCase();
    return text.includes("INVENTORY LISTING") && text.includes("AVIONIC");
  } catch (e) {
    console.warn("Aeroflot OCR-detection failed, treating as not-Aeroflot:", e);
    return false;
  }
}

/**
 * Top-level entry point — called from app.js once `detectAeroflot()` (the
 * only OCR-capable variant wired up on the browser side so far) confirms
 * a match. Renders + OCRs every page, then hands the word boxes to
 * `main.run_with_ocr()`, which routes into
 * `levels/L3_ocr/extract.py`'s `extract_records_from_words()` -- the same
 * column-projection logic the local pytesseract path uses, just fed word
 * boxes from Tesseract.js instead of pytesseract.
 *
 * `statusEl`, if given, gets a live per-page progress message -- OCR is
 * genuinely slow (unlike tonight's earlier "hang," which turned out not to
 * be real; this cost is real and worth being honest about rather than
 * leaving a stale status line during a multi-second wait).
 */
export async function runOcrPipeline(pdfBytes, pyodide, statusEl, sheetType, variant) {
  if (!(sheetType === "OCCM" && variant === "Aeroflot")) {
    return { ok: false, error: `In-browser OCR isn't wired up yet for ${sheetType} / ${variant}.` };
  }
  const lib = await loadPdfJs();
  const pdf = await lib.getDocument({ data: pdfBytes }).promise;
  const pagesWords = [];
  for (let i = 1; i <= pdf.numPages; i++) {
    if (statusEl) statusEl.textContent = `Running in-browser OCR — page ${i} of ${pdf.numPages}…`;
    const canvas = await renderPageToCanvas(pdf, i, 300);
    pagesWords.push(await ocrCanvas(canvas));
  }
  if (statusEl) statusEl.textContent = "OCR done, extracting rows…";

  pyodide.globals.set("_pages_words", pyodide.toPy(pagesWords));
  pyodide.globals.set("_ocr_sheet_type", sheetType);
  pyodide.globals.set("_ocr_variant", variant);
  const jsonStr = await pyodide.runPythonAsync(`
import json
json.dumps(main.run_with_ocr(_pages_words, _ocr_sheet_type, _ocr_variant))
`);
  return JSON.parse(jsonStr);
}
