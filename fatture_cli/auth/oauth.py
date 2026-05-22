"""OAuth2 authorization-code flow with local callback server.

Fatture in Cloud requires OAuth2 with the following steps:
1. Open the authorize URL in the user's browser
2. User grants consent; provider redirects to our redirect_uri with `code`
3. Exchange the code for access_token + refresh_token at the token endpoint
4. Persist tokens (and the chosen company_id) to disk
"""

from __future__ import annotations

import http.server
import json
import os
import secrets
import socket
import stat
import threading
import time
import urllib.parse
import webbrowser
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import httpx

from fatture_cli.api.endpoints import (
    DEFAULT_SCOPES,
    OAUTH_AUTHORIZE_URL,
    OAUTH_TOKEN_URL,
)

DEFAULT_CALLBACK_HOST = "127.0.0.1"
DEFAULT_CALLBACK_PORT = 8080


def get_config_dir() -> Path:
    """Resolve the directory where credentials are stored.

    Resolution order:
    1. ``$XDG_CONFIG_HOME/mayai-cli/fatture`` if XDG_CONFIG_HOME is set
       (Linux/freedesktop convention; respected on any OS that exports it).
    2. ``~/.config/mayai-cli/fatture`` — on Windows, ``Path.home()`` resolves
       via ``USERPROFILE`` (and ``HOMEDRIVE``+``HOMEPATH`` as fallback).
    3. ``./.fatture-cli`` — degraded fallback used only when neither HOME
       nor USERPROFILE is set (e.g. minimal CI / sandbox environments).
       Without this, importing the module itself crashes before the CLI
       can emit a sensible error.
    """
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "mayai-cli" / "fatture"
    try:
        return Path.home() / ".config" / "mayai-cli" / "fatture"
    except RuntimeError:
        return Path.cwd() / ".fatture-cli"


def get_credentials_file() -> Path:
    """Absolute path to the persisted credentials JSON file."""
    return get_config_dir() / "credentials.json"


@dataclass
class Credentials:
    """Persisted OAuth2 credentials + the active company context."""

    client_id: str
    client_secret: str
    access_token: str
    refresh_token: str
    expires_at: float  # unix timestamp
    token_type: str = "Bearer"
    company_id: int | None = None
    scopes: list[str] = field(default_factory=list)

    @property
    def is_expired(self) -> bool:
        # Refresh 60s before actual expiry to be safe.
        return time.time() >= (self.expires_at - 60)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Credentials:
        return cls(**data)


def load_credentials() -> Credentials | None:
    path = get_credentials_file()
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as fh:
        return Credentials.from_dict(json.load(fh))


def save_credentials(creds: Credentials) -> None:
    path = get_credentials_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write atomically and lock down to 0600 so other users can't read tokens.
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(creds.to_dict(), fh, indent=2)
    os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
    tmp.replace(path)


def delete_credentials() -> bool:
    path = get_credentials_file()
    if path.exists():
        path.unlink()
        return True
    return False


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    """Captures the OAuth redirect from Fatture in Cloud."""

    # Class-level slots populated by perform_oauth_flow before serving.
    expected_state: str = ""
    received: dict = {}

    def do_GET(self) -> None:  # noqa: N802 (stdlib API)
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        code = params.get("code", [None])[0]
        state = params.get("state", [None])[0]
        error = params.get("error", [None])[0]

        type(self).received = {"code": code, "state": state, "error": error}

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        if error:
            body = f"<h1>Authorization failed</h1><p>{error}</p>"
        elif not code or state != type(self).expected_state:
            body = "<h1>Invalid response</h1><p>State mismatch or missing code.</p>"
        else:
            body = (
                "<h1>Authorization complete</h1>"
                "<p>You can close this window and return to the terminal.</p>"
            )
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        # Silence the default stderr logging of the dev server.
        return


def _start_callback_server(host: str, port: int) -> tuple[http.server.HTTPServer, int]:
    server = http.server.HTTPServer((host, port), _CallbackHandler)
    actual_port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, actual_port


def perform_oauth_flow(
    client_id: str,
    client_secret: str,
    scopes: list[str] | None = None,
    open_browser: bool = True,
    callback_host: str = DEFAULT_CALLBACK_HOST,
    callback_port: int = DEFAULT_CALLBACK_PORT,
    timeout: float = 300.0,
) -> Credentials:
    """Run the full OAuth2 authorization-code flow.

    The redirect URI registered in the Fatture in Cloud developer console MUST
    match the one this function uses. We default to `http://127.0.0.1:<port>/callback`.
    """
    scopes = scopes or DEFAULT_SCOPES
    state = secrets.token_urlsafe(24)

    # Reserve a port up-front so we can put it in the redirect_uri.
    if callback_port == 0:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind((callback_host, 0))
            callback_port = probe.getsockname()[1]

    redirect_uri = f"http://{callback_host}:{callback_port}/callback"

    _CallbackHandler.expected_state = state
    _CallbackHandler.received = {}
    server, _ = _start_callback_server(callback_host, callback_port)

    try:
        authorize_url = (
            f"{OAUTH_AUTHORIZE_URL}?"
            + urllib.parse.urlencode(
                {
                    "response_type": "code",
                    "client_id": client_id,
                    "redirect_uri": redirect_uri,
                    "scope": " ".join(scopes),
                    "state": state,
                }
            )
        )

        if open_browser:
            webbrowser.open(authorize_url)

        deadline = time.time() + timeout
        while time.time() < deadline and not _CallbackHandler.received:
            time.sleep(0.2)

        received = _CallbackHandler.received
        if not received:
            raise TimeoutError("OAuth callback not received within timeout")
        if received.get("error"):
            raise RuntimeError(f"OAuth error: {received['error']}")
        if received.get("state") != state:
            raise RuntimeError("OAuth state mismatch — possible CSRF")
        code = received.get("code")
        if not code:
            raise RuntimeError("OAuth callback missing authorization code")
    finally:
        server.shutdown()
        server.server_close()

    # Exchange code for tokens.
    with httpx.Client(timeout=30.0) as http_client:
        response = http_client.post(
            OAUTH_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
            },
            headers={"Accept": "application/json"},
        )
    if response.status_code != 200:
        raise RuntimeError(f"Token exchange failed: HTTP {response.status_code} {response.text}")

    payload = response.json()
    return Credentials(
        client_id=client_id,
        client_secret=client_secret,
        access_token=payload["access_token"],
        refresh_token=payload["refresh_token"],
        expires_at=time.time() + float(payload.get("expires_in", 3600)),
        token_type=payload.get("token_type", "Bearer"),
        scopes=scopes,
    )


def refresh_access_token(creds: Credentials) -> Credentials:
    """Use the refresh_token to obtain a fresh access_token."""
    with httpx.Client(timeout=30.0) as http_client:
        response = http_client.post(
            OAUTH_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "client_id": creds.client_id,
                "client_secret": creds.client_secret,
                "refresh_token": creds.refresh_token,
            },
            headers={"Accept": "application/json"},
        )
    if response.status_code != 200:
        raise RuntimeError(f"Token refresh failed: HTTP {response.status_code} {response.text}")

    payload = response.json()
    creds.access_token = payload["access_token"]
    # FiC rotates refresh tokens, so always pick up the new one when present.
    creds.refresh_token = payload.get("refresh_token", creds.refresh_token)
    creds.expires_at = time.time() + float(payload.get("expires_in", 3600))
    creds.token_type = payload.get("token_type", creds.token_type)
    return creds
