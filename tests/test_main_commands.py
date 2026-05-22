"""CLI command tests via click.testing.CliRunner.

Invokes the Click commands in-process (no subprocess, so no env-inheritance
quirks like the WinError 10106 path) and asserts on exit code + stdout.
APIClient is patched at the main-module level so commands run without a
network or saved credentials.
"""

from __future__ import annotations

import json
import time
from typing import Any
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from fatture_cli.auth.oauth import Credentials
from fatture_cli.main import cli


def _valid_creds() -> Credentials:
    return Credentials(
        client_id="cid",
        client_secret="sec",
        access_token="tok",
        refresh_token="ref",
        expires_at=time.time() + 3600,
        token_type="Bearer",
        company_id=42,
        scopes=["entity.clients:r"],
    )


@pytest.fixture
def api_mock(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Patch ``fatture_cli.main.APIClient`` so commands never hit the network.

    The returned MagicMock is the *instance* the CLI will receive — set
    ``.get_paginated.return_value``, ``.get_resource.return_value``,
    ``.post_resource.return_value`` etc. on it from each test.
    """
    monkeypatch.setattr("fatture_cli.main.load_credentials", _valid_creds)

    instance = MagicMock()
    instance.__enter__.return_value = instance
    instance.__exit__.return_value = None
    instance.credentials = _valid_creds()

    monkeypatch.setattr("fatture_cli.main.APIClient", lambda *a, **kw: instance)
    return instance


# ---------------------------------------------------------------------------
# Top-level surface
# ---------------------------------------------------------------------------


def test_cli_help_lists_all_command_groups() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])

    assert result.exit_code == 0
    for group in ("auth", "list", "get", "create", "search", "update", "export"):
        assert group in result.output


def test_cli_version_flag_prints_version() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])

    assert result.exit_code == 0
    assert "fatture" in result.output


def test_list_help_shows_subcommands() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["list", "--help"])

    assert result.exit_code == 0
    assert "invoices" in result.output
    assert "clients" in result.output
    assert "products" in result.output


# ---------------------------------------------------------------------------
# Auth status branch
# ---------------------------------------------------------------------------


def test_auth_status_exits_2_when_logged_out(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("fatture_cli.main.load_credentials", lambda: None)
    runner = CliRunner()

    result = runner.invoke(cli, ["auth", "status"])

    assert result.exit_code == 2


def test_auth_status_prints_summary_when_logged_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("fatture_cli.main.load_credentials", _valid_creds)
    runner = CliRunner()

    result = runner.invoke(cli, ["--json", "auth", "status"])

    assert result.exit_code == 0
    payload = json.loads(result.output.strip())
    assert payload["authenticated"] is True
    assert payload["company_id"] == 42


def test_list_invoices_exits_2_without_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("fatture_cli.main.load_credentials", lambda: None)
    runner = CliRunner()

    result = runner.invoke(cli, ["list", "invoices"])

    assert result.exit_code == 2


# ---------------------------------------------------------------------------
# list / get / search via patched APIClient
# ---------------------------------------------------------------------------


def test_list_invoices_emits_ndjson(api_mock: MagicMock) -> None:
    api_mock.get_paginated.return_value = {
        "data": [
            {
                "id": 1,
                "date": "2026-01-15",
                "number": 7,
                "entity": {"name": "Acme"},
                "amount_gross": "1220.00",
                "status": "paid",
            },
            {
                "id": 2,
                "date": "2026-01-16",
                "number": 8,
                "entity": {"name": "Beta"},
                "amount_gross": "500.00",
                "status": "not_paid",
            },
        ],
        "current_page": 1,
        "last_page": 1,
    }
    runner = CliRunner()

    result = runner.invoke(cli, ["--json", "list", "invoices"])

    assert result.exit_code == 0
    rows = [json.loads(line) for line in result.output.strip().splitlines()]
    assert len(rows) == 2
    assert rows[0]["client"] == "Acme"
    assert rows[1]["status"] == "not_paid"


def test_list_invoices_overdue_filter(api_mock: MagicMock) -> None:
    api_mock.get_paginated.return_value = {
        "data": [
            {
                "id": 1,
                "date": "2026-01-01",
                "status": "not_paid",
                "payments_list": [{"due_date": "2099-12-31", "status": "not_paid"}],
            },
            {
                "id": 2,
                "date": "2026-01-02",
                "status": "not_paid",
                "payments_list": [{"due_date": "2020-01-01", "status": "not_paid"}],
            },
        ],
        "current_page": 1,
        "last_page": 1,
    }
    runner = CliRunner()

    result = runner.invoke(cli, ["--json", "list", "invoices", "--overdue"])

    assert result.exit_code == 0
    rows = [json.loads(line) for line in result.output.strip().splitlines()]
    assert [r["id"] for r in rows] == [2]


def test_list_clients_basic(api_mock: MagicMock) -> None:
    api_mock.get_paginated.return_value = {
        "data": [
            {"id": 1, "name": "A", "email": "a@x", "tax_code": "T1"},
            {"id": 2, "name": "B", "email": None, "tax_code": "T2"},
        ],
        "current_page": 1,
        "last_page": 1,
    }
    runner = CliRunner()

    result = runner.invoke(cli, ["--json", "list", "clients"])

    assert result.exit_code == 0
    rows = [json.loads(line) for line in result.output.strip().splitlines()]
    assert [r["name"] for r in rows] == ["A", "B"]


def test_get_invoice_by_id(api_mock: MagicMock) -> None:
    api_mock.get_resource.return_value = {
        "data": {
            "id": 42,
            "date": "2026-03-01",
            "number": 3,
            "entity": {"id": 7, "name": "Rossi"},
            "amount_gross": "1220.00",
            "items_list": [{"name": "Servizio", "qty": "1", "net_price": "1000"}],
        }
    }
    runner = CliRunner()

    result = runner.invoke(cli, ["--json", "get", "invoice", "42"])

    assert result.exit_code == 0
    payload: dict[str, Any] = json.loads(result.output.strip())
    assert payload["id"] == 42
    assert payload["client"] == "Rossi"
    assert payload["client_id"] == 7


def test_search_clients_passes_query(api_mock: MagicMock) -> None:
    api_mock.get_paginated.return_value = {
        "data": [{"id": 1, "name": "Rossi Mario"}],
        "current_page": 1,
        "last_page": 1,
    }
    runner = CliRunner()

    result = runner.invoke(cli, ["--json", "search", "clients", "Rossi"])

    assert result.exit_code == 0
    sent_params = api_mock.get_paginated.call_args.kwargs["params"]
    assert "name LIKE" in sent_params["q"]
    assert "Rossi" in sent_params["q"]


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


def test_create_invoice_returns_id(api_mock: MagicMock) -> None:
    api_mock.post_resource.return_value = {
        "data": {"id": 501, "number": 12, "numeration": "/A", "date": "2026-05-22"},
    }
    runner = CliRunner()

    result = runner.invoke(
        cli,
        [
            "--json", "create", "invoice",
            "--client", "7",
            "--product", "Consulenza",
            "--amount", "500",
            "--date", "2026-05-22",
        ],
    )

    assert result.exit_code == 0
    out = json.loads(result.output.strip())
    assert out["id"] == 501
    assert out["number"] == "12/A"


# ---------------------------------------------------------------------------
# Error surfacing
# ---------------------------------------------------------------------------


def test_apierror_during_list_invoices_exits_1(api_mock: MagicMock) -> None:
    from fatture_cli.api.client import APIError

    api_mock.get_paginated.side_effect = APIError(500, "boom")
    runner = CliRunner()

    result = runner.invoke(cli, ["list", "invoices"])

    assert result.exit_code == 1
    assert "boom" in result.output or "boom" in (result.stderr or "")
