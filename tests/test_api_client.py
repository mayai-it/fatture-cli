"""Retry behavior for APIClient on 429 (rate limit) and 5xx (transient).

No real sleeps — time.sleep is intercepted so the assertions verify both
that we sleep at all and that the duration matches the expected policy.
"""

from __future__ import annotations

import time

from fatture_cli.api.client import APIClient
from fatture_cli.auth.oauth import Credentials


def _make_creds() -> Credentials:
    return Credentials(
        client_id="cid",
        client_secret="sec",
        access_token="tok",
        refresh_token="ref",
        expires_at=time.time() + 3600,
        token_type="Bearer",
        company_id=1,
    )


def test_retry_on_429_respects_retry_after(httpx_mock, monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr("time.sleep", lambda s: sleeps.append(s))

    httpx_mock.add_response(status_code=429, headers={"Retry-After": "2"})
    httpx_mock.add_response(status_code=200, json={"ok": True})

    client = APIClient(_make_creds(), max_retries=3)
    result = client.get("/ping")

    assert result == {"ok": True}
    assert sleeps == [2.0]


def test_retry_on_503_with_exponential_backoff(httpx_mock, monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr("time.sleep", lambda s: sleeps.append(s))

    httpx_mock.add_response(status_code=503)
    httpx_mock.add_response(status_code=503)
    httpx_mock.add_response(status_code=200, json={"ok": True})

    client = APIClient(_make_creds(), max_retries=3)
    result = client.get("/ping")

    assert result == {"ok": True}
    # attempts 0, 1 -> 2**0 = 1.0, 2**1 = 2.0
    assert sleeps == [1.0, 2.0]
