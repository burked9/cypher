---
title: "Cypher — aviation maintenance data, finally on tap"
subtitle: "An in-browser, zero-trust, variant-aware extractor for OCCMs, Hard-Time lists and LLPs. Built by Church Bay Consulting."
status: coming-soon
audience: aviation operators, MROs, lease administrators
hero_image: assets/01_landing.png
---

# Cypher

> Drop the PDF. Get the table. Walk away.

For two decades, the same scene has played out in airline back offices and lease return rooms across the world: an analyst opens a 50-page maintenance PDF, triple-screens a spreadsheet, opens a third spreadsheet, and starts typing. Every part number, every serial, every cycle count — by hand. One typo away from a costly mistake. One missed row away from an audit finding.

There has to be a better way.

There is. **It just runs in your browser.**

![Cypher landing page — clean hero, three-step indicator, choose-PDF button, three info cards](assets/01_landing.png)

*From PDF to validated CSV in three clicks. No upload. No account. No server. No telemetry. Just a single static page that pulls a Python runtime into your browser the first time you visit, then runs it forever — even with the network unplugged.*

## What it does, in one breath

Cypher reads aviation maintenance documents — **OCCMs, Hard-Time lists, Life-Limited-Part records, Avionic Inventories, Aircraft Equipment List Reports** — and produces clean, structured, validated data ready for Excel, your MIS, or your records system. It runs **entirely in your browser**. Your PDFs never leave your laptop. Nothing is uploaded anywhere. Ever.

That is not marketing language. It is an architectural fact, verifiable in 30 seconds with the browser's network panel.

![Sample LLP extraction — 25 rows extracted, 25 clean, filter bar, sticky headers, columns including Engine S/N](assets/02_llp_extraction.png)

*A real Life-Limited-Parts list, parsed in under a second. 25 rows, 25 clean, zero flagged. Engine serial number propagated to every row from the document header so the data is one `GROUP BY` away from a fleet-wide LLP burn-down chart. Try doing that with a screenshot of a PDF and a hand-typed spreadsheet.*

## Why it's different

### Variant-aware, by construction

Operators don't agree on document formats. China Eastern's OCCM doesn't look like Vietnam Airlines'. Aeroflot ships a scanned PDF with no text layer. AMOS-driven equipment lists from Swiss-AS are line-anchored. Most "PDF table extractors" treat all documents as one shape — and break the moment they don't.

Cypher does not. Every operator gets its own **sealed variant module** — a single Python file that pins the column schema, the validation rules, and the parser logic. When a new VNA document arrives, it is fingerprinted from the first three pages and routed to exactly the same parser that handled the last 50 VNA documents. Same input shape → same output shape. Every. Single. Time.

### Soft validation, aviation-domain-aware

Cypher knows that part numbers don't contain the letter `O` (it's a `0`). It knows ATA chapters live between 20 and 83. It knows that vendor codes are five characters, that `S` and `5` get confused at the start of a PN, that `~` in a scan is almost always a `-`, that `°1` is a `7` Tesseract got wrong. These rules — dozens of them — are encoded once, applied everywhere, and easy for a domain expert to extend.

Every cell is checked. Every suspicious cell is **flagged** for review. **Nothing is dropped.** The analyst sees what the machine wasn't sure about and decides.

![Issue frequency analysis — horizontal bar chart of (column, reason) flags across the corpus](assets/03_issue_analysis.png)

*Cross-corpus issue analysis surfaces patterns at a glance. The two long bars at the top are not bugs — they are exactly the cells an analyst should eyeball first, surfaced from a corpus of 3,300 rows in milliseconds. Tuning a rule moves the bars; the chart is the feedback loop.*

### Four-level extraction pipeline

Different documents need different muscles. Cypher escalates per page:

- **L1** — text-layer parsing for selectable PDFs (most operators, sub-second per page)
- **L2** — layout-aware reconstruction for awkwardly-typeset tables *(reserved)*
- **L3** — Tesseract OCR for scanned PDFs
- **L4** — PaddleOCR `PP-Structure` for fringe-quality scans (Colab notebook)

A single document can be a mix. A 24-page OCCM with 13 text-layer pages and 11 scanned pages is parsed in one pass — text rows extracted directly, scanned pages routed to OCR, every row tagged with its provenance.

### Privacy by design, not by promise

Cypher is a **Pyodide application** — Python compiled to WebAssembly, executing in the same JavaScript sandbox as a Wikipedia page. The PDF you select is read into the browser's memory and parsed there. No HTTP requests carry document bytes. No third-party telemetry. No cookies. Disconnect from the internet after the page loads and Cypher still works for the rest of the session.

For privacy-conscious operators, lease return work, ITAR-adjacent records, or anyone who has ever felt uncomfortable uploading a maintenance file to a "free SaaS extraction tool" — this is what you've been waiting for.

### Open source, MIT-licensed

The full source is on GitHub. The validation rules are readable. The parsers are auditable. The privacy claims are verifiable line by line. **Trust by inspection, not by trust me bro.**

## Real numbers, real PDFs

Three operator variants in production today, tested on a corpus of 11 documents totalling **3,300+ extracted rows**:

| Document type | Rows extracted | Cleanly validated |
|---------------|---------------:|------------------:|
| Vietnam Airlines OCCM × 2 | 2,313 | 88% on first run |
| Vietnam Airlines HT × 2 | 245 | **99.6%** |
| Vietnam Airlines LLP × 4 | 100 | **100%** |
| China Eastern OCCM | 429 | **99%** |
| AMOS Equipment List | 1,265 | 81% |
| Aeroflot Avionic Inventory | 71 | 68% (scanned, OCR-bounded) |

Adding a new operator is a one-file affair. Tuning a rule is a one-line affair. Re-running the whole corpus and rebuilding the dashboard takes ninety seconds.

## What's coming next

- **Bloom-filter PN cross-check** — validate every extracted part number against an authoritative master list, in-browser, without ever shipping the master list itself. Mathematically one-way, zero-trust by construction.
- **Aircraft-type sub-variants** — operator + airframe specificity for the rare cases where one operator emits different formats per fleet.
- **Tesseract.js for in-browser L3** — the last variant moves to client-side OCR, completing the privacy story for scanned documents.
- **Snapshot diffing** — feed two monthly OCCMs in, see exactly what changed: components installed, components removed, hours and cycles delta. Audit-grade traceability.

## Try it

Cypher launches publicly at [your URL here]. If you'd like a private walkthrough, drop me a line.

— **Daniel Burke**, Church Bay Consulting

---

*Cypher is an open-source project under the MIT license. The deployed site is hosted on GitHub Pages with no analytics, no cookies, and no server. Source: [link to GitHub repo]. Built with Pyodide, pdfplumber, pdfminer.six, and the goodwill of every aviation engineer who has ever lost a Saturday to manual data entry.*
