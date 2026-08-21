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
// Status: scaffold only. The dependency tags are wired up in index.html.
// The next implementation step lives in `runOcrPipeline()` below — currently
// returns a clear "not yet implemented" error so the UX surfaces it cleanly
// rather than crashing.

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

async function renderPageToCanvas(pdfBytes, pageNum, dpi = 300) {
  const lib = await loadPdfJs();
  const pdf = await lib.getDocument({ data: pdfBytes }).promise;
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
 * Top-level entry point — called from the main app.js when the detected
 * variant requires L3.
 *
 * Returns: { ok: false, error: "<message>" } until the Python bridge to
 * receive these word lists is implemented (next step). Once that exists,
 * the structure is:
 *
 *   for each page:
 *     canvas = await renderPageToCanvas(pdfBytes, pageNum)
 *     words  = await ocrCanvas(canvas)
 *     all_pages.push({page: pageNum, words})
 *   call pyodide: main.run_with_ocr(pages, sheet_type, variant)
 */
export async function runOcrPipeline(pdfBytes, _pyodide, _statusEl) {
  return {
    ok: false,
    error: "Browser-side L3 OCR is wired up but not yet finished. " +
           "Next step: add `main.run_with_ocr(pages, ...)` and a column-projection " +
           "shim in levels/L3_ocr/extract.py that takes pre-OCR'd word boxes " +
           "instead of running pytesseract locally. For now, run the local " +
           "Python pipeline for Aeroflot variants.",
  };
}
