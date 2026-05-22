"""Credential persistence and token-refresh tests.

The OAuth browser flow (perform_oauth_flow) opens a local HTTP callback and
waits on the user's browser — too noisy to exercise reliably in unit tests.
We cover save/load/delete, ``is_expired`` semantics, and the refresh-token
HTTP path; the interactive flow stays at partial coverage by design.
"""

from __future__ import annotations

import json
import os
import stat
import sys
import time
from pathlib import Path

import httpx
import pytest

from fatture_cli.auth.oauth import (
    Credentials,
    delete_credentials,
    load_credentials,
    refresh_access_token,
    save_credentials,
)


def _make_creds(**overrides: object) -> Credentials:
    defaults: dict[str, object] = {
        "client_id": "cid",
        "client_secret": "sec",
        "access_token": "tok",
        "refresh_token": "ref",
        "expires_at": time.time() + 3600,
        "token_type": "Bearer",
        "company_id": 1,
        "scopes": ["entity.clients:r"],
    }
    defaults.update(overrides)
    return Credentials(**defaults)  # type: ignore[arg-type]


@pytest.fixture
def isolated_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Redirect get_config_dir() to a per-test temp directory."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return tmp_path / "mayai-cli" / "fatture"


# ---------------------------------------------------------------------------
# is_expired property
# ---------------------------------------------------------------------------


def test_credentials_is_expired_true_when_past() -> None:
    creds = _make_creds(expires_at=time.time() - 100)
    assert creds.is_expired is True


def test_credentials_is_expired_true_within_safety_margin() -> None:
    # The 60s safety margin treats tokens expiring "soon" as already expired.
    creds = _make_creds(expires_at=time.time() + 30)
    assert creds.is_expired is True


def test_credentials_is_expired_false_with_comfortable_margin() -> None:
    creds = _make_creds(expires_at=time.time() + 3600)
    assert creds.is_expired is False


# ---------------------------------------------------------------------------
# save / load / delete
# ---------------------------------------------------------------------------


def test_save_load_credentials_roundtrip(isolated_config: Path) -> None:
    original = _make_creds(company_id=42, scopes=["a", "b"])

    save_credentials(original)
    loaded = load_credentials()

    assert loaded is not None
    assert loaded.access_token == original.access_token
    assert loaded.refresh_token == original.refresh_token
    assert loaded.company_id == 42
    assert loaded.scopes == ["a", "b"]


def test_load_credentials_returns_none_when_file_missing(isolated_config: Path) -> None:
    assert load_credentials() is None


def test_delete_credentials_removes_file(isolated_config: Path) -> None:
    save_credentials(_make_creds())
    assert load_credentials() is not None

    removed = delete_credentials()

    assert removed is True
    assert load_credentials() is None


def test_delete_credentials_returns_false_when_absent(isolated_config: Path) -> None:
    assert delete_credentials() is False


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX mode bits only")
def test_save_credentials_writes_0600_permissions(isolated_config: Path) -> None:
    save_credentials(_make_creds())

    creds_file = isolated_config / "credentials.json"
    mode = stat.S_IMODE(os.stat(creds_file).st_mode)
    # 0600 = readable+writable by owner, nothing for group/world.
    assert mode == 0o600, f"expected 0600, got {oct(mode)}"


def test_save_credentials_writes_json_with_indent(isolated_config: Path) -> None:
    save_credentials(_make_creds(access_token="my-secret"))

    raw = (isolated_config / "credentials.json").read_text(encoding="utf-8")
    # Pretty-printed JSON has a newline after the opening brace.
    assert raw.startswith("{\n")
    payload = json.loads(raw)
    assert payload["access_token"] == "my-secret"


# ---------------------------------------------------------------------------
# refresh_access_token
# ---------------------------------------------------------------------------


def test_refresh_access_token_updates_in_place(httpx_mock: object) -> None:
    httpx_mock.add_response(  # type: ignore[attr-defined]
        method="POST",
        json={
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "expires_in": 7200,
            "token_type": "Bearer",
        },
    )
    creds = _make_creds(access_token="old", refresh_token="old-ref")
    before = creds.expires_at

    refresh_access_token(creds)

    assert creds.access_token == "new-access"
    assert creds.refresh_token == "new-refresh"
    assert creds.expires_at > before


def test_refresh_access_token_keeps_old_refresh_when_provider_omits_it(
    httpx_mock: object,
) -> None:
    # Some OAuth providers only rotate the refresh_token periodically. When
    # the response omits refresh_token, we must NOT clobber the existing one.
    httpx_mock.add_response(  # type: ignore[attr-defined]
        method="POST",
        json={"access_token": "fresh", "expires_in": 3600},
    )
    creds = _make_creds(refresh_token="keep-me")

    refresh_access_token(creds)

    assert creds.access_token == "fresh"
    assert creds.refresh_token == "keep-me"


def test_refresh_access_token_raises_on_4xx(httpx_mock: object) -> None:
    httpx_mock.add_response(  # type: ignore[attr-defined]
        method="POST",
        status_code=401,
        json={"error": "invalid_grant"},
    )
    creds = _make_creds()

    with pytest.raises(RuntimeError, match="Token refresh failed"):
        refresh_access_token(creds)


def test_refresh_access_token_propagates_network_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _BoomClient:
        def __init__(self, *a: object, **kw: object) -> None: ...

        def __enter__(self) -> _BoomClient:
            return self

        def __exit__(self, *exc: object) -> None: ...

        def post(self, *a: object, **kw: object) -> None:
            raise httpx.ConnectError("boom")

    monkeypatch.setattr("fatture_cli.auth.oauth.httpx.Client", _BoomClient)

    with pytest.raises(httpx.ConnectError):
        refresh_access_token(_make_creds())
