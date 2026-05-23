# FAQ & Troubleshooting

## "Not authenticated" error (exit code 2)

You need to authenticate first:

```bash
fatture auth login --client-id YOUR_ID --client-secret YOUR_SECRET
```

## OAuth callback fails on a specific port

Use `--port 0` to pick a free port automatically:

```bash
fatture auth login --client-id ... --client-secret ... --port 0
```

Make sure the redirect URI in your Fatture in Cloud app settings matches
the port you're using (or use a wildcard if supported).

## Tokens expired and refresh keeps failing

Delete saved credentials and re-authenticate:

```bash
fatture auth logout
fatture auth login --client-id ... --client-secret ...
```

## Rate limit hit (HTTP 429)

The CLI retries automatically with backoff, honoring the `Retry-After`
header. If you're consistently hitting limits, reduce concurrency in
your scripts.

## Where are credentials stored?

In order of precedence:

1. `$XDG_CONFIG_HOME/mayai-cli/fatture/credentials.json` if `XDG_CONFIG_HOME` is set.
2. `~/.config/mayai-cli/fatture/credentials.json` on Unix.
3. `%USERPROFILE%\.config\mayai-cli\fatture\credentials.json` on Windows.
4. `./.fatture-cli/credentials.json` if no `HOME` / `USERPROFILE` is available
   (CI runners, sandboxed containers).

File permissions: `0600` (owner only) on Unix. Permissions are not enforced
on Windows.

## My agent (Claude / Cursor / etc.) can't see the MCP tools

Verify your client's config has:

```json
{
  "mcpServers": {
    "fatture": {
      "command": "/path/to/fatture-mcp"
    }
  }
}
```

Find the path with `which fatture-mcp`. Restart the agent after editing
the config.

## How do I send an invoice to SDI / Agenzia delle Entrate?

There is no `fatture send-sdi` command, and no MCP `send_invoice_sdi` tool,
because Fatture in Cloud's public REST API doesn't expose a "send to SDI"
endpoint. The transmission happens server-side when:

1. The invoice was created with `e_invoice: true`.
2. It has a valid recipient identifier — `CodiceDestinatario` (7-char SDI
   code) or the recipient's PEC address.

To check whether a given invoice has been transmitted (and to which state
the SDI moved it), use:

```bash
fatture ei-status invoice <id>
```

This returns `ei_status` (one of `missing`, `not_sent`, `attempt`, `pending`,
`sent`, `rejected`, ...), the `e_invoice` flag, and the populated
`ei_data` fields. If `ei_status` is `not_sent` or `missing`, the most
likely cause is incomplete `ei_data` on the invoice itself (no
CodiceDestinatario, no PEC) — fix that via `fatture update invoice` and
the server will re-attempt.

## Can I un-send a fattura already transmitted to SDI?

No. Once an invoice has `ei_status == "sent"` it's a legal fiscal act
registered with Agenzia delle Entrate; deletion is not possible. The
correct correction is a credit note (nota di credito, `TipoDocumento`
TD04) that references the original invoice. Fatture in Cloud's UI offers
this as a one-click operation; the CLI does not yet expose it (planned).

## What's the difference between `mark-paid` and recording a payment?

`fatture mark-paid invoice <id>` (and the equivalent
`update invoice --status paid`) updates the document-level
`payment_status` field in Fatture in Cloud. It is a label, not a
bookkeeping operation: no cash movement is recorded, no bank account
balance changes, no journal entry is created. If you also need to
register the actual money movement (entrata in cassa / banca), do that
separately in the Fatture in Cloud UI under Movimenti / Estratto conto.

## `fatture export invoice` produces XML — what next?

The output is FatturaPA v1.2.3 (FPR12). Digital signature (`.p7m`) and
SDI submission require a qualified certificate and are outside the scope
of this tool. Use a signing service or your accountant's portal to finalize.

## `--overdue` returns fewer results than I expect

The filter is applied client-side: the CLI fetches invoices, then drops
rows where `status == "paid"` or no payment line has a due date in the
past. Fatture in Cloud rejects `payment_status` inside its server-side
`q` expression, so this can't be a server-side filter.
