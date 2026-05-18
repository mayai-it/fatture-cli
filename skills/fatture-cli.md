---
name: fatture-cli
description: Use whenever the user asks about invoices, clients, or products in their Fatture in Cloud account, or mentions "fatture", "fattureincloud", "fattura". Provides a CLI to read invoices, clients, and products via the Fatture in Cloud API.
---

# fatture-cli — agent usage guide

`fatture` is a command-line wrapper around the Fatture in Cloud v2 REST API.
Use it any time the user asks you to look up invoices, clients, or
products from their Fatture in Cloud account.

## When to use this skill

Trigger on user prompts like:
- "How many invoices did I issue in 2025?"
- "Find the client Rossi"
- "What did I bill to ACME last quarter?"
- "Show me my unpaid invoices"
- "Get invoice 526346861"
- "Which products do I have set up?"

## Golden rules

1. **Always pass `--json`** when you intend to parse the output. The default
   format is for humans; `--json` is NDJSON (one object per line) and is what
   you should consume.
2. **Check auth first** with `fatture auth status` if you're unsure whether
   the user is logged in. Exit code `2` means not authenticated — tell the
   user to run `fatture auth login --client-id ... --client-secret ...`.
3. **Use `--limit N`** when you only need a sample. The API paginates 100 at
   a time; iterating all pages costs requests against the 1000/hour quota.
4. **Read stderr separately.** Errors are written to stderr with the prefix
   `error:`. Exit codes: `0` ok, `1` application error, `2` not authenticated.
5. **Never echo `credentials.json` contents** — they live at
   `~/.config/mayai-cli/fatture/credentials.json` and contain OAuth tokens.

## Command cheat sheet

### Auth
```bash
fatture auth login --client-id <ID> --client-secret <SECRET>
fatture auth status
fatture auth logout
```

### Invoices
```bash
# All invoices (paginated, full year)
fatture --json list invoices

# Filter by year and status
fatture --json list invoices --year 2025 --status not_paid

# Status values: paid, not_paid, partially_paid, expired, partially_expired
# Latest 5 only
fatture --json list invoices --limit 5

# Detail with line items and payment schedule
fatture --json get invoice 526346861
```

List row shape:
```json
{"id": 526346861, "date": "2026-05-18", "number": "1", "client": "...",
 "total": 122.0, "status": "not_paid"}
```

Detail shape:
```json
{"id": ..., "date": "...", "number": "...", "client": "...",
 "lines": [{"description": "...", "qty": 1, "amount_net": 100, "amount_gross": 122}],
 "amount_net": 100, "total": 122, "currency": "EUR", "status": "...",
 "payment_method": "...",
 "payments": [{"due_date": "...", "amount": ..., "status": "...",
               "paid_date": "...", "payment_account": "..."}]}
```

### Clients
```bash
fatture --json list clients
fatture --json list clients --limit 20
fatture --json get client 12345
fatture --json search clients "Rossi"          # name LIKE '%Rossi%'
```

List/search row shape:
```json
{"id": 12345, "name": "...", "email": "...", "tax_code": "..."}
```

Detail shape:
```json
{"id": ..., "name": "...", "email": "...", "certified_email": "...",
 "phone": "...", "tax_code": "...", "vat_number": "...",
 "address": {"street": "...", "postal_code": "...", "city": "...",
             "province": "...", "extra": "...", "country": "..."}}
```

### Products
```bash
fatture --json list products
fatture --json get product 67890
```

List row shape:
```json
{"id": 67890, "name": "...", "price": 100.0, "vat_type": "22%"}
```

## Common workflows

### "How much did I bill in 2025?"
```bash
fatture --json list invoices --year 2025 | jq '[.[] | .total] | add'
```

### "Find a client by name and show their unpaid invoices"
```bash
CLIENT_ID=$(fatture --json search clients "ACME" --limit 1 | jq -r .id)
# Then filter invoices client-side (the list endpoint does not filter by
# client; use jq):
fatture --json list invoices --status not_paid \
  | jq --argjson id "$CLIENT_ID" 'select(.client_id == $id)'
```

### "Show me the full breakdown of invoice X"
```bash
fatture --json get invoice 526346861
```

### "Debug why a call is failing"
Add `--verbose` to see the exact URL and status code on stderr:
```bash
fatture --verbose --json list invoices --year 2025
```

## Things this CLI does NOT do (yet)

- `fatture create invoice` is a stub — do not promise the user you can
  create invoices.
- No supplier / received-document support.
- No webhook or real-time features.
- No client-side rate-limiting; respect 1000 req/hour per token.

## Error patterns and what they mean

| stderr message | Likely cause |
|---|---|
| `error: not authenticated — run \`fatture auth login\` first` (exit 2) | No credentials saved. |
| `error: HTTP 401: ...` after retry | Refresh token expired — user must re-login. |
| `error: HTTP 404: Resource not found.` | The id does not exist in the active company. |
| `error: Invalid query syntax.` | A malformed `q` was sent — check single-quote wrapping. |
| `error: HTTP 429: ...` | Rate-limited. Back off; quota resets hourly. |

## When in doubt

Run `fatture --help`, `fatture <group> --help`, or
`fatture <group> <command> --help`. The help text is the source of truth for
flags and arguments.
