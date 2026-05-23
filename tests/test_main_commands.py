"""CLI command tests via click.testing.CliRunner.

Invokes the Click commands in-process (no subprocess, so no env-inheritance
quirks like the WinError 10106 path) and asserts on exit code + stdout.
APIClient is patched at the main-module level so commands run without a
network or saved credentials.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
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


# ---------------------------------------------------------------------------
# Write commands (0.3.0)
# ---------------------------------------------------------------------------


def test_update_invoice_modifies_specified_fields(api_mock: MagicMock) -> None:
    api_mock.put_resource.return_value = {"data": {"id": 42}}
    runner = CliRunner()

    result = runner.invoke(
        cli,
        ["--json", "update", "invoice", "42",
         "--status", "paid", "--notes", "Pagata in contanti il 22/05"],
    )

    assert result.exit_code == 0
    body = api_mock.put_resource.call_args.kwargs["json"]
    assert body["data"] == {"payment_status": "paid", "notes": "Pagata in contanti il 22/05"}


def test_update_invoice_requires_at_least_one_field(api_mock: MagicMock) -> None:
    runner = CliRunner()

    result = runner.invoke(cli, ["update", "invoice", "42"])

    assert result.exit_code == 1
    assert "at least one field" in result.output or "at least one field" in (
        result.stderr or ""
    )
    api_mock.put_resource.assert_not_called()


def test_mark_paid_invoice_defaults_paid_date_to_today(api_mock: MagicMock) -> None:
    api_mock.put_resource.return_value = {"data": {"id": 42}}
    runner = CliRunner()

    result = runner.invoke(cli, ["--json", "mark-paid", "invoice", "42"])

    assert result.exit_code == 0
    body = api_mock.put_resource.call_args.kwargs["json"]
    assert body["data"]["payment_status"] == "paid"
    # paid_date defaults to today — assert it's a date-shaped string, not the
    # exact value (test would be flaky around midnight).
    assert len(body["data"]["paid_date"]) == 10


def test_mark_paid_invoice_respects_explicit_date(api_mock: MagicMock) -> None:
    api_mock.put_resource.return_value = {"data": {"id": 42}}
    runner = CliRunner()

    result = runner.invoke(
        cli, ["--json", "mark-paid", "invoice", "42", "--date", "2026-03-01"]
    )

    assert result.exit_code == 0
    body = api_mock.put_resource.call_args.kwargs["json"]
    assert body["data"]["paid_date"] == "2026-03-01"


def test_send_invoice_email_minimal_args(api_mock: MagicMock) -> None:
    api_mock.post_resource.return_value = {"data": {"status": "queued"}}
    runner = CliRunner()

    result = runner.invoke(
        cli,
        ["--json", "send", "invoice", "42", "--to", "cliente@example.com"],
    )

    assert result.exit_code == 0
    body = api_mock.post_resource.call_args.kwargs["json"]
    assert body["data"]["recipient_email"] == "cliente@example.com"
    assert body["data"]["attach_pdf"] is True


def test_send_invoice_email_passes_subject_and_body(api_mock: MagicMock) -> None:
    api_mock.post_resource.return_value = {"data": {}}
    runner = CliRunner()

    result = runner.invoke(
        cli,
        [
            "send", "invoice", "42",
            "--to", "cliente@example.com",
            "--from", "fatture@studio.it",
            "--subject", "Fattura marzo 2026",
            "--body", "In allegato la fattura.",
        ],
    )

    assert result.exit_code == 0
    body = api_mock.post_resource.call_args.kwargs["json"]
    assert body["data"]["sender_email"] == "fatture@studio.it"
    assert body["data"]["subject"] == "Fattura marzo 2026"
    assert body["data"]["body"] == "In allegato la fattura."


def test_ei_status_invoice_shows_sdi_state(api_mock: MagicMock) -> None:
    api_mock.get_resource.return_value = {
        "data": {
            "id": 42,
            "date": "2026-01-15",
            "number": 7,
            "e_invoice": True,
            "ei_status": "sent",
            "ei_data": {"vat_kind": "I", "payment_method": "MP05", "empty_field": ""},
        }
    }
    runner = CliRunner()

    result = runner.invoke(cli, ["--json", "ei-status", "invoice", "42"])

    assert result.exit_code == 0
    payload = json.loads(result.output.strip())
    assert payload["ei_status"] == "sent"
    assert payload["e_invoice"] is True
    # Empty fields stripped from ei_data.
    assert "empty_field" not in payload["ei_data"]


def test_export_pdf_invoice_writes_default_filename(
    api_mock: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api_mock.get_resource.return_value = {
        "data": {
            "id": 42, "date": "2026-01-15", "number": 7,
            "url": "https://cdn.fattureincloud.it/sig/abc123.pdf",
        }
    }
    api_mock.get_binary_url.return_value = b"%PDF-1.4\n%fake pdf bytes\n"
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    result = runner.invoke(cli, ["--json", "export-pdf", "invoice", "42"])

    assert result.exit_code == 0
    saved = tmp_path / "invoice_42.pdf"
    assert saved.exists()
    assert saved.read_bytes().startswith(b"%PDF-")


def test_export_pdf_invoice_fails_when_no_url(api_mock: MagicMock) -> None:
    api_mock.get_resource.return_value = {
        "data": {"id": 42, "date": "2026-01-15"}  # no `url` field
    }
    runner = CliRunner()

    result = runner.invoke(cli, ["export-pdf", "invoice", "42"])

    assert result.exit_code == 1
    api_mock.get_binary_url.assert_not_called()


def test_update_client_modifies_specified_fields(api_mock: MagicMock) -> None:
    api_mock.put_resource.return_value = {"data": {"id": 7}}
    runner = CliRunner()

    result = runner.invoke(
        cli,
        ["--json", "update", "client", "7",
         "--name", "Acme S.r.l.", "--email", "info@acme.it"],
    )

    assert result.exit_code == 0
    body = api_mock.put_resource.call_args.kwargs["json"]
    assert body["data"] == {"name": "Acme S.r.l.", "email": "info@acme.it"}


def test_update_invoice_surface_sdi_hint_on_409(api_mock: MagicMock) -> None:
    from fatture_cli.api.client import APIError

    api_mock.put_resource.side_effect = APIError(
        409, "document already sent to SDI cannot be modified"
    )
    runner = CliRunner()

    result = runner.invoke(cli, ["update", "invoice", "42", "--status", "paid"])

    assert result.exit_code == 1
    combined = (result.output or "") + (result.stderr or "")
    assert "TD04" in combined or "credit note" in combined.lower()
