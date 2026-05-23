# Authentication

Fatture in Cloud uses the OAuth2 Authorization Code flow. The CLI handles
the full round-trip locally — no web service in the middle.

## Setup

1. Create an app at https://developers.fattureincloud.it/ (free).
2. Register a redirect URI of the form `http://127.0.0.1:<port>/callback`.
   The default port is `8080`; you can change it at login time.
3. Copy the `client_id` and `client_secret` from the developer console.

## Login

```bash
fatture auth login --client-id YOUR_ID --client-secret YOUR_SECRET
```

What happens:

1. The CLI spins up a one-shot HTTP server on the configured callback port.
2. Your browser opens the Fatture in Cloud consent screen.
3. After you approve, the provider redirects to the local callback with an
   authorization code.
4. The CLI exchanges the code for an `access_token` + `refresh_token`.
5. It then calls `/user/companies` to pick the first company id as the
   default for subsequent commands.
6. Tokens land in the config file (see below) with `0600` permissions.

## Picking a port

If `8080` is taken or your firewall blocks it, pass `--port`:

```bash
# Pick a specific port (must match the redirect URI registered on FiC)
fatture auth login --client-id ... --client-secret ... --port 9090

# Or let the OS pick a free one (only works if your FiC app uses a
# wildcard-capable redirect URI; otherwise the registration won't match)
fatture auth login --client-id ... --client-secret ... --port 0
```

The chosen port is printed before opening the browser; copy it into the
FiC app's redirect URI registration if you change it.

## Non-interactive environments

If you can't open a browser (SSH session, container), pass `--no-browser`:

```bash
fatture auth login --client-id ... --client-secret ... --no-browser
```

The CLI will print the authorization URL — open it manually on a machine
that has a browser, complete the consent, and the local callback server
will still capture the code (you'll need port-forwarding for that).

## Refresh and expiry

`access_token` expiry is checked before every request. If the token is
within 60 seconds of expiry (or the API returns 401 anyway), the CLI
silently refreshes using the saved `refresh_token` and retries the
request once.

You shouldn't need to re-login until the refresh token itself expires
(weeks to months, depending on the provider's policy).

## Where credentials are stored

In order of precedence:

1. `$XDG_CONFIG_HOME/mayai-cli/fatture/credentials.json`
2. `~/.config/mayai-cli/fatture/credentials.json` (Unix)
3. `%USERPROFILE%\.config\mayai-cli\fatture\credentials.json` (Windows)
4. `./.fatture-cli/credentials.json` (fallback for sandboxed envs without
   `HOME` or `USERPROFILE`)

File permissions: `0600` (owner read+write only) on Unix. Windows ACLs are
left to the OS defaults.

## Revoking locally

```bash
fatture auth logout
```

Deletes `credentials.json`. This does not revoke the token on the Fatture
in Cloud side — to do that, go to the developer console and revoke the app.

## Multiple companies

The first company id discovered is saved as the default. Today the CLI
doesn't expose a `switch-company` command; if you need to operate on a
different one, edit `company_id` in `credentials.json` (it's a plain JSON
file). A `fatture auth use-company` command is planned.
