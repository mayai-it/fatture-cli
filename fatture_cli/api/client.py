"""Authenticated HTTP client for the Fatture in Cloud API.

Handles:
- Bearer-token injection
- Transparent access-token refresh on 401 / near-expiry
- Per-CLI request timing (for --verbose)
- Structured error surfacing
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import httpx

from fatture_cli.api.endpoints import API_BASE_URL

if TYPE_CHECKING:
    from fatture_cli.auth.oauth import Credentials


def _extract_error_message(payload: Any) -> str | None:
    """Pull a human-readable message out of a Fatture in Cloud error body.

    The API is inconsistent: errors can arrive as
        {"error": {"message": "..."}}    # nested object
        {"error": "..."}                 # flat string
        {"message": "..."}               # top-level message
        "Unauthorized"                   # plain string body
        ["..."] / null                   # anything else
    """
    if isinstance(payload, str):
        return payload or None
    if isinstance(payload, dict):
        error_field = payload.get("error")
        if isinstance(error_field, dict):
            return error_field.get("message") or error_field.get("description")
        if isinstance(error_field, str):
            return error_field
        return payload.get("message")
    return None


class APIError(Exception):
    """Raised when the Fatture in Cloud API returns a non-2xx response."""

    def __init__(self, status_code: int, message: str, payload: Any = None) -> None:
        super().__init__(f"HTTP {status_code}: {message}")
        self.status_code = status_code
        self.message = message
        self.payload = payload


class APIClient:
    def __init__(
        self,
        credentials: Credentials,
        base_url: str = API_BASE_URL,
        timeout: float = 30.0,
        verbose: bool = False,
    ) -> None:
        self._credentials = credentials
        self._verbose = verbose
        self._http = httpx.Client(
            base_url=base_url,
            timeout=timeout,
            headers={"Accept": "application/json"},
        )

    def __enter__(self) -> APIClient:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    @property
    def credentials(self) -> Credentials:
        return self._credentials

    def _auth_headers(self) -> dict[str, str]:
        # RFC 6750 prescribes the literal "Bearer" scheme. Normalize so we
        # never send "bearer" or a stray token_type from a non-conforming
        # provider response.
        scheme = (self._credentials.token_type or "Bearer").strip().capitalize() or "Bearer"
        return {"Authorization": f"{scheme} {self._credentials.access_token}"}

    def _ensure_fresh_token(self) -> None:
        if self._credentials.is_expired:
            from fatture_cli.auth.oauth import refresh_access_token, save_credentials

            refresh_access_token(self._credentials)
            save_credentials(self._credentials)

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json: Any = None,
    ) -> dict | list | None:
        self._ensure_fresh_token()

        started = time.perf_counter()
        response = self._http.request(
            method,
            path,
            params=params,
            json=json,
            headers=self._auth_headers(),
        )
        # One automatic retry after a 401: refresh, then resend exactly once.
        if response.status_code == 401:
            from fatture_cli.auth.oauth import refresh_access_token, save_credentials

            refresh_access_token(self._credentials)
            save_credentials(self._credentials)
            response = self._http.request(
                method,
                path,
                params=params,
                json=json,
                headers=self._auth_headers(),
            )

        elapsed_ms = (time.perf_counter() - started) * 1000
        if self._verbose:
            import sys

            print(
                f"[fatture] {method} {response.request.url} -> "
                f"{response.status_code} in {elapsed_ms:.0f}ms",
                file=sys.stderr,
            )

        if response.status_code >= 400:
            try:
                payload = response.json()
            except ValueError:
                payload = response.text

            message = _extract_error_message(payload) or response.reason_phrase
            raise APIError(response.status_code, message, payload)

        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    def get(self, path: str, params: dict | None = None) -> dict | list | None:
        return self.request("GET", path, params=params)

    def post(self, path: str, json: Any = None) -> dict | list | None:
        return self.request("POST", path, json=json)

    def put(self, path: str, json: Any = None) -> dict | list | None:
        return self.request("PUT", path, json=json)

    def delete(self, path: str) -> dict | list | None:
        return self.request("DELETE", path)
