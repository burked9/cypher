// Tesseract.js bridge — runs OCR client-side, PDF rendering client-side via
// pdf.js, both exposed as plain generic globals Python calls through
// Pyodide's `js` module (see shared/ocr_bridge.py). Pyodide cannot render a
// PDF page (fitz needs a native C++ engine) or run OCR (pytesseract shells
// out to a `tesseract` binary) — neither exists in WebAssembly — so both of
// those two operations, and only those two, happen here instead. Every
// other piece of every variant's extraction logic (numpy grid-detection,
// line/token parsing, column mapping) runs unchanged in Python either way.

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
  // Pointing GlobalWorkerOptions.workerSrc straight at the CDN URL makes
  // pdf.js construct `new Worker(crossOriginUrl, {type: "module"})`
  // internally -- browsers refuse to construct a Worker directly from a
  // cross-origin script URL (confirmed: throws "cannot be accessed from
  // origin ..." when done directly; through pdf.js's own construction path
  // it instead hangs page.render() forever with no error at all, having
  // silently failed to ever get a worker message back). Fetching the
  // script ourselves and wrapping it in a same-origin blob URL is the
  // standard workaround -- construct our own working worker and hand it to
  // pdf.js via workerPort (a pre-built worker instance) instead of
  // workerSrc (a URL pdf.js would try to construct one from itself).
  const workerText = await (await fetch(PDFJS_WORKER)).text();
  const workerBlobUrl = URL.createObjectURL(
    new Blob([workerText], { type: "application/javascript" })
  );
  lib.GlobalWorkerOptions.workerPort = new Worker(workerBlobUrl, { type: "module" });
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
 * Number of pages in a PDF — the generic replacement for
 * `fitz.open(path).page_count`.
 */
window.cypherPageCount = async function (pdfBytes) {
  const lib = await loadPdfJs();
  const pdf = await lib.getDocument({ data: new Uint8Array(pdfBytes) }).promise;
  return pdf.numPages;
};

/**
 * Render one page of a PDF to raw RGBA pixels — the generic replacement
 * for `fitz.open(path).load_page(i).get_pixmap(dpi=dpi)` (see
 * shared/ocr_bridge.py's render_page(), which reconstructs a PIL Image
 * from this). `pageIndex` is 0-based to match that Python/fitz convention;
 * pdf.js itself is 1-based, converted here so callers on both sides never
 * have to think about the mismatch.
 */
window.cypherRenderPage = async function (pdfBytes, pageIndex, dpi = 300) {
  const lib = await loadPdfJs();
  const pdf = await lib.getDocument({ data: new Uint8Array(pdfBytes) }).promise;
  const canvas = await renderPageToCanvas(pdf, pageIndex + 1, dpi);
  const ctx = canvas.getContext("2d");
  const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
  return {
    width: canvas.width,
    height: canvas.height,
    pixels: imageData.data,   // Uint8ClampedArray, RGBA
  };
};

async function _canvasFromPngBytes(pngBytes) {
  // Force an explicit, fully-materialized copy before constructing the
  // Blob. Pyodide hands JS a view into its own WASM heap for a Python
  // `bytes` argument rather than a plain copied Uint8Array -- confirmed:
  // Python's own byte length and PNG magic-number signature were both
  // correct right before the call, yet createImageBitmap() on the
  // resulting Blob threw "source image could not be decoded" on the
  // first real-browser attempt. `new Uint8Array(pngBytes)` copies
  // element-by-element into a fresh, ordinary buffer Blob can read
  // safely, regardless of what kind of view/proxy Pyodide handed over.
  const bytes = new Uint8Array(pngBytes);
  const blob = new Blob([bytes], { type: "image/png" });
  const bitmap = await createImageBitmap(blob);
  const canvas = document.createElement("canvas");
  canvas.width = bitmap.width;
  canvas.height = bitmap.height;
  canvas.getContext("2d").drawImage(bitmap, 0, 0);
  return canvas;
}

/**
 * OCR an image (PNG-encoded bytes, as produced by PIL's Image.save) to
 * plain text — the generic replacement for
 * `pytesseract.image_to_string(image, config=f"--psm {psm} -c tessedit_char_whitelist={whitelist}")`.
 * `whitelist`, when non-empty, restricts recognized characters exactly
 * like pytesseract's own `tessedit_char_whitelist` config value.
 */
window.cypherOcrText = async function (pngBytes, psm = 6, whitelist = "") {
  const canvas = await _canvasFromPngBytes(pngBytes);
  const Tesseract = await loadTesseract();
  const opts = { tessedit_pageseg_mode: psm };
  if (whitelist) opts.tessedit_char_whitelist = whitelist;
  const result = await Tesseract.recognize(canvas, "eng", opts);
  return result.data.text;
};

/**
 * OCR an image to word-level boxes, shaped to match what
 * `pytesseract.image_to_data` returns locally (see
 * shared/ocr_bridge.py's ocr_words()) -- the generic replacement for that
 * call. `psm` must match whatever the calling Python code used to pass to
 * pytesseract's own `--psm` config for the two backends to behave the same
 * way (confirmed: dropping this silently changed which page-segmentation
 * mode ran, changing row counts).
 */
window.cypherOcrWords = async function (pngBytes, psm = 6) {
  const canvas = await _canvasFromPngBytes(pngBytes);
  const Tesseract = await loadTesseract();
  const result = await Tesseract.recognize(canvas, "eng", { tessedit_pageseg_mode: psm });
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
};
