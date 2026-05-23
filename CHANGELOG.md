# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.3.0] — 2026-05-23

### Added
- `fatture update invoice <id>` extended to multi-field delta updates
  (status, date, number, notes, visible-subject).
- `fatture mark-paid invoice <id>` — shortcut for `update --status paid`
  with `--date` defaulting to today.
- `fatture send invoice <id> --to EMAIL` — email an invoice via the FiC
  schedule-email endpoint. Supports custom `--from`, `--subject`, `--body`,
  and `--attach-pdf` / `--no-attach-pdf`.
- `fatture export-pdf invoice <id>` — download the invoice PDF locally
  via the temporary signed URL returned by the API.
- `fatture ei-status invoice <id>` — diagnostic read of the e-invoice /
  SDI transmission state (`ei_status`, `e_invoice`, populated `ei_data`).
- `fatture update client <id>` — delta-mode client patch with the most
  common fields (name, email, phone, address, vat, tax code).
- Six matching MCP tools: `update_invoice`, `mark_invoice_paid`,
  `send_invoice_email`, `get_invoice_pdf` (base64-encoded), `get_invoice_ei_status`,
  `update_client`. The PDF tool base64-encodes the bytes for JSON transport.
- `APIClient.get_binary_url(url)` — fetch a presigned URL without sending
  the bearer token, used for PDF downloads from FiC's CDN.
- Body builders: `build_invoice_update_body` (now `**fields`),
  `build_mark_paid_body`, `build_send_invoice_email_body`,
  `build_client_update_body`, plus `summarize_ei_status`.

### Changed
- `build_invoice_update_body(status)` → `build_invoice_update_body(**fields)`.
  Existing callers updated; the smoke test now exercises the kwargs form.
- `update invoice` error handler surfaces a hint pointing to TD04
  (credit note) when the API rejects a modification on an SDI-transmitted
  invoice.

### Not added (and why)
- `fatture send-sdi invoice <id>` was scoped but dropped: Fatture in Cloud's
  REST API exposes no "send to SDI" endpoint. Transmission happens
  server-side when the invoice has `e_invoice: true` and a valid recipient
  identifier. See [docs/FAQ.md](docs/FAQ.md) for the workflow.

## [0.2.0] — 2026-05-23

### Added
- Pydantic 2 models for Invoice, Client, Product with `Decimal` precision on
  every monetary field (overrides the official SDK's `float`).
- MCP server exposing native tools for AI agents (`fatture-mcp` entry point):
  list/get/search/create for invoices and clients, plus auth status.
- Retry logic on 429 and 5xx with `Retry-After` header support (delta-seconds
  and HTTP-date per RFC 7231); exponential backoff fallback.
- Lazy config path resolution with three-tier fallback (`$XDG_CONFIG_HOME` →
  `~/.config` → `./.fatture-cli`). Works in sandboxed environments without
  `HOME` / `USERPROFILE`.
- Multi-OS CI matrix: Ubuntu / macOS / Windows × Python 3.11 / 3.12 / 3.13.
- FatturaPA v1.2.3 (FPR12) XML generation and XSD validation
  (`fatture export invoice`, `fatture validate invoice`).
- 96 tests with ~70% coverage; mypy strict enforced (0 errors) and blocking in CI.

### Changed
- Refactored pure helpers into `fatture_cli/transforms/` (invoice, client,
  product, payment). MCP server and CLI now both depend on transforms,
  not on each other.
- API client exposes typed methods alongside the low-level ones:
  `get_resource`, `get_paginated`, `post_resource`, `put_resource` — all
  returning `dict[str, Any]` so call sites no longer carry a `dict | list | None` union.
- Package renamed on PyPI to `mayai-fatture-cli`.

### Fixed
- `WinError 10106` on Windows subprocess tests caused by environment stripping
  (now inherit + selective override).
- `Path.home()` crash at module-load on systems without `HOME` / `USERPROFILE`.

## [0.1.0] — 2026-05-18

- Initial release. CLI for Fatture in Cloud with OAuth2 login, invoice/client/
  product list/get/create/search, and human + NDJSON output.
