[![PyPI version](https://img.shields.io/pypi/v/mayai-fatture-cli.svg)](https://pypi.org/project/mayai-fatture-cli/)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Built for AI agents](https://img.shields.io/badge/Built%20for-AI%20agents-purple)](https://mayai.it)
[![Tests](https://github.com/mayai-it/fatture-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/mayai-it/fatture-cli/actions/workflows/ci.yml)
[![mypy](https://img.shields.io/badge/mypy-strict-blue)](https://mypy-lang.org/)

# fatture-cli

> 🇮🇹 [Documentazione in italiano](README.it.md) — versione ridotta.

Command-line client for the [Fatture in Cloud](https://developers.fattureincloud.it/)
API, built for both humans and AI agents. Default output strips empty fields,
`--json` produces NDJSON suitable for piping into LLMs or jq.

Part of [MayAI](https://mayai.it).

## Installation

```bash
pip install mayai-fatture-cli
```

Or from source:

```bash
git clone https://github.com/mayai-it/fatture-cli
cd fatture-cli
pip install -e .
```

For development with linting and tests:

```bash
pip install -e ".[dev]"
```

Requires Python 3.11+ and a free Fatture in Cloud developer app from
https://developers.fattureincloud.it/.

## Quick start

```bash
# 1. Authenticate (opens a browser for OAuth2 consent)
fatture auth login --client-id YOUR_ID --client-secret YOUR_SECRET

# 2. Verify
fatture auth status

# 3. List the 10 most recent paid invoices, as NDJSON
fatture --json list invoices --status paid --limit 10

# 4. Fetch a single invoice with lines and payments
fatture get invoice 526346861
```

## Example output

Default (compact, human-readable):

```
$ fatture list invoices --status paid --limit 3
526346861  2026-03-15  Rossi SRL              €1,200.00  paid
526346840  2026-03-12  Studio Bianchi & Co    €  450.00  paid
526346801  2026-03-08  ACME Italia            €2,300.00  paid
```

With `--json` (NDJSON, one object per line, pipe-able to jq):

```
$ fatture --json list invoices --status paid --limit 1
{"id":526346861,"date":"2026-03-15","client":"Rossi SRL","total":"1200.00","status":"paid"}
```

With `--verbose` (HTTP timing on stderr, response on stdout):

```
$ fatture --verbose get invoice 526346861
[fatture] GET https://api-v2.fattureincloud.it/c/123/issued_documents/526346861 -> 200 in 287ms
{ ... invoice details on stdout ... }
```

## Why this exists

Most CLIs for Italian invoicing services are wrappers around heavy SDKs, not
designed for terminal workflows or AI agents. `fatture-cli` is built for both:

- **Agent-friendly**: NDJSON output, stable exit codes, errors on stderr —
  pipe it into Claude, jq, or any LLM workflow.
- **Human-friendly**: compact text output that strips empty fields, one
  command per common task.
- **Italian-native**: built for the real workflows of Italian SMEs and
  accounting studios.
- **Self-hosted auth**: OAuth2 round-trip handled locally, tokens stored
  with `0600` permissions.

## Command reference

| Command | Description |
|---|---|
| `fatture auth login --client-id ID --client-secret SECRET` | Run the OAuth2 flow and save credentials. |
| `fatture auth status` | Show whether credentials are present and valid. |
| `fatture auth logout` | Delete saved credentials. |
| `fatture list invoices [--year Y] [--status S] [--overdue] [--limit N]` | List issued invoices. |
| `fatture get invoice <id>` | Fetch a single invoice with lines and payments. |
| `fatture create invoice --client ID --product NAME --amount AMT --date YYYY-MM-DD` | Create a new invoice with a single line item. |
| `fatture update invoice <id> --status paid\|not_paid` | Update payment status of an existing invoice. |
| `fatture list clients [--limit N]` | List all clients. |
| `fatture get client <id>` | Fetch a single client with address details. |
| `fatture create client --name NAME [--email E] [--vat V]` | Create a new client. |
| `fatture search clients <query>` | Search clients by name (`LIKE '%query%'`). |
| `fatture list products [--limit N]` | List products / services. |
| `fatture get product <id>` | Fetch a single product. |
| `fatture export invoice <id> [--output FILE]` | Export as FatturaPA v1.2.3 XML. |
| `fatture validate invoice <id>` | Validate an invoice against the FatturaPA XSD. |

**Global flags** (work in any position): `--json` NDJSON output, `--verbose`
HTTP timing on stderr, `-h` / `--help` per-command help.

**Exit codes**: `0` success, `1` application error (API 4xx/5xx, validation),
`2` not authenticated.

**Note on `--overdue`**: applied client-side. Fatture in Cloud rejects
`payment_status` inside the `q` filter expression, so the CLI fetches the
page server-side then drops rows where status is `paid` or no payment line
is past-due.

## Engineering notes

A few choices worth calling out:

- **All monetary fields are `Decimal`, not `float`.** Fatture in Cloud's
  official Python SDK uses `float` for amounts; we override to `Decimal`
  to avoid the `0.1 + 0.2 = 0.30000000000000004` problem when talking
  to Italian accountants.

- **MCP server is decoupled from the CLI.** Shared helpers live in
  `fatture_cli.transforms`, so the CLI and the MCP server depend on
  transforms — not on each other. Either can change without breaking
  the other.

- **Retry on rate limit (429) and 5xx with `Retry-After`** handling for
  both delta-seconds and HTTP-date formats (RFC 7231).

- **Config paths resolved lazily** with three-tier fallback:
  `$XDG_CONFIG_HOME` → `~/.config` → `./.fatture-cli`. Works in sandboxed
  environments without `HOME` / `USERPROFILE`.

- **mypy strict with zero unmotivated `# type: ignore`.** Includes
  `disallow_subclassing_any`, `strict_equality`, `extra_checks`. Type
  regressions fail CI.

Quality bar: 96 tests on Ubuntu / macOS / Windows × Python 3.11 / 3.12 / 3.13.
Coverage ~70%, critical paths (MCP server, API client) >85%.

## MCP Server

`fatture-cli` ships with a native MCP server, letting AI agents like Claude
access your Fatture in Cloud data directly.

![MCP demo](docs/mcp-demo.png)

### Setup with Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "fatture": {
      "command": "/path/to/fatture-mcp"
    }
  }
}
```

Find your path with `which fatture-mcp`.

### Compatible MCP clients

| Client | Status |
|--------|--------|
| Claude Desktop | Tested |
| Cursor | Same stdio config |
| Continue (VS Code) | Same stdio config |
| Zed | Same stdio config |
| ChatGPT | MCP support coming soon |

### Available tools

| Tool | Description |
|------|-------------|
| `fatture_list_invoices` | List invoices (year, status, overdue, limit). |
| `fatture_get_invoice` | Get full invoice with lines and payments. |
| `fatture_list_clients` | List all clients. |
| `fatture_search_clients` | Search clients by name. |
| `fatture_create_invoice` | Create a new invoice. |
| `fatture_create_client` | Create a new client. |
| `fatture_auth_status` | Check authentication status. |

## FatturaPA XML

Generate and validate FatturaPA v1.2.3 (FPR12) XML from a Fatture in Cloud
invoice. The schema is the official one from fatturapa.gov.it, bundled and
validated offline.

```bash
fatture export invoice <id>                          # print XML to stdout
fatture export invoice <id> --output IT12345.xml     # save to file
fatture validate invoice <id>                        # validate against XSD
```

Digital signature and SDI submission require a qualified certificate and are
outside the scope of this tool.

## Authentication

Fatture in Cloud uses OAuth2 Authorization Code flow; the CLI handles the
full round-trip locally. Quick path:

1. Create an app at https://developers.fattureincloud.it/ with redirect URI
   `http://127.0.0.1:<port>/callback` (default port 8080; use `--port 0`
   for auto).
2. `fatture auth login --client-id ... --client-secret ...` — opens browser,
   captures callback, exchanges code for tokens.
3. Tokens land in `~/.config/mayai-cli/fatture/credentials.json` (`0600`).
   Refresh is automatic.

Full details, port configuration, and revocation steps in
[docs/AUTHENTICATION.md](docs/AUTHENTICATION.md).

## Development

```bash
pip install -e ".[dev]"
pytest tests/
ruff check fatture_cli/ tests/
mypy fatture_cli/
```

A `Makefile` is provided as a shortcut for the same commands (`make test`,
`make lint`, `make dev`). See [CONTRIBUTING.md](CONTRIBUTING.md) for the
full contribution workflow.

> This repository contains a `CLAUDE.md` file with instructions for AI
> coding agents. Published for transparency; not required reading for users.

## Help

See [docs/FAQ.md](docs/FAQ.md) for common issues and solutions.
For bugs, please open an [issue](https://github.com/mayai-it/fatture-cli/issues).

## License

MIT — see [LICENSE](LICENSE).
