# fatture-cli

Command-line client for the [Fatture in Cloud](https://developers.fattureincloud.it/)
API, built for both humans and AI agents. Designed to be context-efficient: the
default output strips empty fields, and `--json` produces NDJSON suitable for
piping into LLMs or jq.

Part of [MayAI CLI](https://mayai.it).

## Requirements

- Python 3.11+
- A Fatture in Cloud developer app (free) — create one at
  https://developers.fattureincloud.it/

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

For local development (adds `pytest`, `ruff`):

```bash
make dev
```

## Quick start

```bash
# 1. Authenticate (opens a browser for OAuth2 consent)
fatture auth login --client-id YOUR_ID --client-secret YOUR_SECRET

# 2. Verify
fatture auth status

# 3. List the 10 most recent invoices, paid only, as NDJSON
fatture --json list invoices --status paid --limit 10

# 4. Fetch a single invoice
fatture get invoice 526346861

# 5. Search clients by name
fatture search clients "Rossi"
```

## Command reference

| Command | Description |
|---|---|
| `fatture auth login --client-id ID --client-secret SECRET` | Run the OAuth2 flow and save credentials. |
| `fatture auth status` | Show whether credentials are present and valid. |
| `fatture auth logout` | Delete saved credentials. |
| `fatture list invoices [--year Y] [--status S] [--limit N]` | List issued invoices for the active company. |
| `fatture get invoice <id>` | Fetch a single invoice with lines and payments. |
| `fatture list clients [--limit N]` | List all clients. |
| `fatture get client <id>` | Fetch a single client with address details. |
| `fatture search clients <query>` | Search clients by name (`LIKE '%query%'`). |
| `fatture list products [--limit N]` | List products / services. |
| `fatture get product <id>` | Fetch a single product. |

### Global flags

These work in any position (before or after the subcommand):

| Flag | Effect |
|---|---|
| `--json` | Emit one JSON object per line (NDJSON). |
| `--verbose` | Log HTTP method, URL, status, and duration to stderr. |
| `-h`, `--help` | Show help for the current command. |

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | Application error (API 4xx/5xx, validation, etc.) |
| `2` | Not authenticated — run `fatture auth login` |

## Authentication

Fatture in Cloud uses OAuth2 Authorization Code flow. The CLI handles the
full round-trip locally:

1. Create an app at https://developers.fattureincloud.it/ and register a
   redirect URI of the form `http://127.0.0.1:<port>/callback`. The default
   port is shown by `fatture auth login --no-browser`; use `--port 0` to pick
   a free one automatically.
2. Run `fatture auth login --client-id ... --client-secret ...`. The CLI
   spins up a one-shot HTTP server on the callback port, opens your browser
   to the Fatture in Cloud consent screen, captures the authorization code,
   and exchanges it for an access + refresh token.
3. After login the CLI fetches `/user/companies` and stores the first
   company's id as the default `company_id` for subsequent calls.
4. Tokens are saved to `~/.config/mayai-cli/fatture/credentials.json` with
   `0600` permissions. Refresh happens transparently on near-expiry or 401.

To revoke locally:

```bash
fatture auth logout
```

## Output format

- **Default** — compact human-readable text. Empty / null fields are stripped
  so terminal output stays scannable.
- **`--json`** — NDJSON. One object per line; lists stream one element per
  line so consumers can process incrementally.
- **`--verbose`** — adds one stderr line per HTTP request:
  `[fatture] GET https://... -> 200 in 287ms`.

Errors always go to stderr, prefixed with `error:`.

## Development

```bash
make dev       # install with dev extras
make test      # run pytest
make lint      # run ruff
make clean     # remove caches and build artifacts
```

## License

MIT — see [LICENSE](./LICENSE).
