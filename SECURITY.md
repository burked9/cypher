# Security policy

## Reporting a vulnerability

Cypher is a small open-source project. If you find a security issue —
particularly anything that could cause data leakage from the in-browser
deploy, or a way to exfiltrate the optional bundled PN master Bloom filter
beyond its designed false-positive rate — please report it privately rather
than opening a public issue.

Contact: **daniel.burke@amraero.co.uk**

You can expect an acknowledgement within 7 days. If the issue is confirmed,
a fix will land in `main` and the deploy will be rebuilt as quickly as
possible.

## Scope

In scope:
- The browser-side application in `deploy/`
- The Python parsing and validation modules in `shared/`, `sheet_types/`,
  `levels/`
- Bundled binary assets (e.g. `shared/pn_master.bloom`)
- The build/release tooling in `deploy/build.py` and `tools/`

Out of scope (unless the issue is reproducible *via* Cypher):
- Vulnerabilities in upstream dependencies (Pyodide, pdfplumber,
  pdfminer.six, etc.) — please report those to the upstream maintainers.
- Issues affecting only stale browsers or unsupported configurations.

## Threat model

Cypher's design intentionally minimizes the attack surface:

- **No server**, so no server-side compromise paths.
- **No file upload**, so no surface for malicious uploads attacking other
  users.
- **No persistent storage** of user data — everything is browser-memory only.
- **No third-party telemetry, no cookies, no analytics.**
- **Static-site host** (GitHub Pages) — compromise requires GitHub-account
  takeover or a successful supply-chain attack on Pyodide / pdfplumber's
  CDN delivery.

Issues that don't fit this model (e.g. "the user's browser is compromised")
are out of scope — Cypher cannot harden against a compromised host.
