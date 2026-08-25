"""Async OCR primitives — page rendering and text recognition, backed by
fitz+pytesseract locally and a JS/Tesseract.js bridge under Pyodide.

Pyodide can run neither: fitz/PyMuPDF needs a native C++ renderer, and
pytesseract just shells out to a `tesseract` binary — neither exists in
WebAssembly. `deploy/assets/ocr_bridge.js` provides three matching globals
(cypherRenderPage/cypherOcrText/cypherOcrWords) backed by pdf.js (rendering)
and Tesseract.js (recognition) instead.

Every OCR-capable variant module should call render_page()/ocr_text()/
ocr_words() instead of touching fitz/pytesseract directly — that is the
ONLY thing that needs to differ between local and in-browser execution.
Everything else a variant does (numpy grid-line detection, line/token
parsing, column mapping) runs identically either way, unchanged, since it
all operates on the PIL.Image / str / word-list these return regardless of
which backend produced them.
"""
from __future__ import annotations
import inspect
import io


async def maybe_await(value):
    """`ocr_detect()`/`extract()` are async on OCR-migrated variants (they
    await render_page()/ocr_text()/ocr_words()) and plain sync elsewhere.
    Callers always do `await maybe_await(v.ocr_detect(pdf_path))` so they
    don't need to know which kind a given variant is."""
    if inspect.isawaitable(value):
        return await value
    return value


def _js_bridge():
    """The JS-side primitives, registered as plain `window` globals by
    deploy/assets/ocr_bridge.js — Pyodide's `js` module proxies the
    browser's global namespace automatically, no explicit registration
    handshake needed. None outside Pyodide (or before those globals
    exist), which every function below treats as "use the local
    fitz/pytesseract path instead."""
    try:
        import js
    except ImportError:
        return None
    if not hasattr(js, "cypherRenderPage"):
        return None
    return js


async def page_count(pdf_path: str) -> int:
    """Number of pages in a PDF."""
    bridge = _js_bridge()
    if bridge is None:
        import fitz  # pymupdf
        doc = fitz.open(pdf_path)
        try:
            return doc.page_count
        finally:
            doc.close()
    with open(pdf_path, "rb") as fh:
        pdf_bytes = fh.read()
    return int(await bridge.cypherPageCount(pdf_bytes))


async def render_page(pdf_path: str, page_index: int, dpi: int = 300):
    """Render one page of a PDF to a PIL Image (mode RGB)."""
    from PIL import Image

    bridge = _js_bridge()
    if bridge is None:
        import fitz  # pymupdf
        doc = fitz.open(pdf_path)
        try:
            pix = doc[page_index].get_pixmap(dpi=dpi)
            return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        finally:
            doc.close()

    # main.py's _save_temp() already wrote the upload to Pyodide's virtual
    # FS before any router/variant code runs, so this is a normal read —
    # no separate bytes-passing path needed for the PDF itself.
    with open(pdf_path, "rb") as fh:
        pdf_bytes = fh.read()
    result = await bridge.cypherRenderPage(pdf_bytes, page_index, dpi)
    width, height = int(result.width), int(result.height)
    pixels = bytes(result.pixels.to_py())
    return Image.frombytes("RGBA", (width, height), pixels).convert("RGB")


async def ocr_text(image, psm: int = 6, whitelist: str | None = None) -> str:
    """OCR an image, returning plain text — mirrors
    `pytesseract.image_to_string(image, config=f"--psm {psm} -c tessedit_char_whitelist={whitelist}")`
    (whitelist restricts recognized characters, e.g. digits-only for a
    numeric cell — meaningfully improves accuracy on those, so it's a real
    parameter here, not dropped for simplicity)."""
    bridge = _js_bridge()
    if bridge is None:
        import pytesseract
        cfg = f"--psm {psm}"
        if whitelist:
            cfg += f" -c tessedit_char_whitelist={whitelist}"
        return pytesseract.image_to_string(image, config=cfg)
    result = await bridge.cypherOcrText(_to_png_bytes(image), psm, whitelist or "")
    return str(result)


async def ocr_words(image, psm: int = 6, min_conf: float = 30) -> list[dict]:
    """OCR an image, returning word-level boxes shaped
    {left, top, width, height, conf, text} — mirrors the useful columns of
    `pytesseract.image_to_data(image, config=f"--psm {psm}")`, including its
    conf > 30 confidence filter by default (levels/L3_ocr/extract.py's
    `_ocr_page` applies that same filter itself locally, but the
    browser-side equivalent needs it applied here since it has no separate
    filtering step of its own).

    `min_conf` is an escape hatch for unusually noisy scans whose median
    word confidence sits near/below the default threshold — filtering
    those at the word level drops the majority of the table rather than
    just the genuinely unreadable ones, when downstream row-shape parsing
    already discards garbage on its own terms. Pass `min_conf=-1` (or any
    value below Tesseract's floor of 0) to keep every recognized word."""
    bridge = _js_bridge()
    if bridge is None:
        import pytesseract
        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT,
                                          config=f"--psm {psm}")
        words = []
        for i in range(len(data["text"])):
            if not data["text"][i].strip():
                continue
            conf = float(data["conf"][i])
            if conf <= min_conf:
                continue
            words.append({
                "left": data["left"][i], "top": data["top"][i],
                "width": data["width"][i], "height": data["height"][i],
                "conf": conf, "text": data["text"][i],
            })
        return words
    result = await bridge.cypherOcrWords(_to_png_bytes(image), psm, min_conf)
    return [dict(w.to_py()) if hasattr(w, "to_py") else dict(w) for w in result]


def _to_png_bytes(image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()
