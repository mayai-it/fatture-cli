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

## `fatture export invoice` produces XML — what next?

The output is FatturaPA v1.2.3 (FPR12). Digital signature (`.p7m`) and
SDI submission require a qualified certificate and are outside the scope
of this tool. Use a signing service or your accountant's portal to finalize.

## `--overdue` returns fewer results than I expect

The filter is applied client-side: the CLI fetches invoices, then drops
rows where `status == "paid"` or no payment line has a due date in the
past. Fatture in Cloud rejects `payment_status` inside its server-side
`q` expression, so this can't be a server-side filter.
