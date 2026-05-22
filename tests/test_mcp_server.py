"""MCP tool tests.

The ``@mcp.tool()`` decorator registers the function with FastMCP but
returns the original callable unchanged — we exercise the tool logic by
calling those functions directly with a hand-rolled Context whose
``request_context.lifespan_context`` exposes a real ``AppContext``.
The APIClient is mocked: no HTTP, no credentials.
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from fatture_cli.api.client import APIError
from fatture_cli.auth.oauth import Credentials
from fatture_cli.mcp_server import (
    AppContext,
    fatture_auth_status,
    fatture_create_client,
    fatture_create_invoice,
    fatture_get_invoice,
    fatture_list_clients,
    fatture_list_invoices,
    fatture_search_clients,
)

DEFAULT_COMPANY_ID = 999


def _fake_ctx(client: Any, company_id: int | None = DEFAULT_COMPANY_ID) -> Any:
    """Build the minimal Context surface the tools actually read."""
    return SimpleNamespace(
        request_context=SimpleNamespace(
            lifespan_context=AppContext(client=client, company_id=company_id),
        ),
    )


def _make_client_mock() -> MagicMock:
    mock = MagicMock()
    mock.credentials = Credentials(
        client_id="cid",
        client_secret="sec",
        access_token="tok",
        refresh_token="ref",
        expires_at=time.time() + 3600,
        token_type="Bearer",
        company_id=DEFAULT_COMPANY_ID,
    )
    return mock


# ---------------------------------------------------------------------------
# list_invoices
# ---------------------------------------------------------------------------


def test_fatture_list_invoices_returns_summary() -> None:
    client = _make_client_mock()
    client.get_paginated.return_value = {
        "data": [
            {
                "id": 1,
                "date": "2026-01-15",
                "number": 7,
                "numeration": "/A",
                "entity": {"name": "Acme"},
                "amount_gross": "1220.00",
                "status": "not_paid",
            },
        ],
        "current_page": 1,
        "last_page": 1,
    }

    rows = fatture_list_invoices(_fake_ctx(client))

    assert len(rows) == 1
    assert rows[0]["id"] == 1
    assert rows[0]["client"] == "Acme"
    assert rows[0]["number"] == "7/A"


def test_fatture_list_invoices_overdue_filter_keeps_only_unpaid_past_due() -> None:
    client = _make_client_mock()
    client.get_paginated.return_value = {
        "data": [
            # paid → filtered out
            {
                "id": 1,
                "date": "2026-01-01",
                "status": "paid",
                "payments_list": [{"due_date": "2020-01-01", "status": "paid"}],
            },
            # unpaid, due in the future → filtered out
            {
                "id": 2,
                "date": "2026-01-02",
                "status": "not_paid",
                "payments_list": [{"due_date": "2099-12-31", "status": "not_paid"}],
            },
            # unpaid, due in the past → kept
            {
                "id": 3,
                "date": "2026-01-03",
                "status": "not_paid",
                "payments_list": [{"due_date": "2020-01-01", "status": "not_paid"}],
            },
        ],
        "current_page": 1,
        "last_page": 1,
    }

    rows = fatture_list_invoices(_fake_ctx(client), overdue=True)

    assert [r["id"] for r in rows] == [3]


def test_fatture_list_invoices_respects_limit() -> None:
    client = _make_client_mock()
    client.get_paginated.return_value = {
        "data": [{"id": i, "date": "2026-01-15"} for i in range(1, 6)],
        "current_page": 1,
        "last_page": 1,
    }

    rows = fatture_list_invoices(_fake_ctx(client), limit=2)

    assert len(rows) == 2


def test_fatture_list_invoices_walks_two_pages() -> None:
    client = _make_client_mock()
    page1 = {
        "data": [{"id": 1, "date": "2026-01-01"}, {"id": 2, "date": "2026-01-02"}],
        "current_page": 1,
        "last_page": 2,
    }
    page2 = {
        "data": [{"id": 3, "date": "2026-01-03"}],
        "current_page": 2,
        "last_page": 2,
    }
    client.get_paginated.side_effect = [page1, page2]

    rows = fatture_list_invoices(_fake_ctx(client))

    assert [r["id"] for r in rows] == [1, 2, 3]


# ---------------------------------------------------------------------------
# get_invoice / detail
# ---------------------------------------------------------------------------


def test_fatture_get_invoice_returns_detail() -> None:
    client = _make_client_mock()
    client.get_resource.return_value = {
        "data": {
            "id": 42,
            "date": "2026-03-01",
            "number": 3,
            "numeration": "/B",
            "entity": {"id": 7, "name": "Rossi"},
            "amount_net": "1000.00",
            "amount_gross": "1220.00",
            "items_list": [{"name": "Consulenza", "qty": "10", "net_price": "100"}],
            "payments_list": [],
        }
    }

    out = fatture_get_invoice(_fake_ctx(client), invoice_id=42)

    assert out["id"] == 42
    assert out["client"] == "Rossi"
    assert out["client_id"] == 7
    assert len(out["lines"]) == 1


# ---------------------------------------------------------------------------
# list_clients / search_clients
# ---------------------------------------------------------------------------


def test_fatture_list_clients_paginated_across_two_pages() -> None:
    client = _make_client_mock()
    client.get_paginated.side_effect = [
        {
            "data": [{"id": 1, "name": "A"}, {"id": 2, "name": "B"}],
            "current_page": 1,
            "last_page": 2,
        },
        {"data": [{"id": 3, "name": "C"}], "current_page": 2, "last_page": 2},
    ]

    rows = fatture_list_clients(_fake_ctx(client))

    assert [r["name"] for r in rows] == ["A", "B", "C"]


def test_fatture_search_clients_passes_like_filter() -> None:
    client = _make_client_mock()
    client.get_paginated.return_value = {
        "data": [{"id": 1, "name": "Rossi Mario"}],
        "current_page": 1,
        "last_page": 1,
    }

    rows = fatture_search_clients(_fake_ctx(client), query="Rossi")

    assert rows[0]["name"] == "Rossi Mario"
    # The LIKE pattern wraps the query in % and lives in `q`.
    sent_params = client.get_paginated.call_args.kwargs["params"]
    assert "name LIKE '%Rossi%'" in sent_params["q"]


def test_fatture_search_clients_strips_single_quotes_to_prevent_injection() -> None:
    client = _make_client_mock()
    client.get_paginated.return_value = {"data": [], "current_page": 1, "last_page": 1}

    fatture_search_clients(_fake_ctx(client), query="O'Hara")

    sent_params = client.get_paginated.call_args.kwargs["params"]
    assert "'" not in sent_params["q"].replace("%", "").replace(
        "name LIKE ", ""
    ).replace(" ", "").strip("'")  # only the LIKE delimiters remain
    assert "OHara" in sent_params["q"]


# ---------------------------------------------------------------------------
# create_invoice / create_client
# ---------------------------------------------------------------------------


def test_fatture_create_invoice_returns_id_and_number() -> None:
    client = _make_client_mock()
    client.post_resource.return_value = {
        "data": {"id": 501, "number": 12, "numeration": "/A", "date": "2026-05-22"},
    }

    out = fatture_create_invoice(
        _fake_ctx(client),
        client_id=7,
        product="Consulenza",
        amount=500.0,
        date="2026-05-22",
    )

    assert out == {"id": 501, "number": "12/A", "date": "2026-05-22"}


def test_fatture_create_invoice_defaults_date_to_today() -> None:
    client = _make_client_mock()
    client.post_resource.return_value = {
        "data": {"id": 1, "number": 1, "date": "2026-05-22"},
    }

    fatture_create_invoice(
        _fake_ctx(client), client_id=1, product="X", amount=10.0
    )

    body = client.post_resource.call_args.kwargs["json"]
    # Body must contain a non-null date; we don't pin to today exactly so
    # the test stays stable across time zones / midnight rollovers.
    assert body["data"]["date"]
    assert len(body["data"]["date"]) == 10  # YYYY-MM-DD


def test_fatture_create_client_minimal_payload() -> None:
    client = _make_client_mock()
    client.post_resource.return_value = {"data": {"id": 9, "name": "Solo"}}

    out = fatture_create_client(_fake_ctx(client), name="Solo")

    assert out == {"id": 9, "name": "Solo"}
    sent = client.post_resource.call_args.kwargs["json"]
    assert sent["data"] == {"name": "Solo", "type": "company"}


# ---------------------------------------------------------------------------
# auth_status
# ---------------------------------------------------------------------------


def test_fatture_auth_status_returns_authenticated_payload() -> None:
    client = _make_client_mock()

    out = fatture_auth_status(_fake_ctx(client))

    assert out["authenticated"] is True
    assert out["company_id"] == DEFAULT_COMPANY_ID
    assert "expires_at" in out
    assert out["expired"] is False


def test_fatture_auth_status_not_authenticated_when_no_client() -> None:
    out = fatture_auth_status(_fake_ctx(client=None, company_id=None))

    assert out == {"authenticated": False}


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_tools_raise_tool_error_when_unauthenticated() -> None:
    ctx = _fake_ctx(client=None, company_id=None)

    with pytest.raises(ToolError, match="not authenticated"):
        fatture_get_invoice(ctx, invoice_id=1)
    with pytest.raises(ToolError, match="not authenticated"):
        fatture_list_clients(ctx)


def test_tool_raises_tool_error_when_company_missing() -> None:
    client = _make_client_mock()
    ctx = _fake_ctx(client, company_id=None)

    with pytest.raises(ToolError, match="no active company"):
        fatture_get_invoice(ctx, invoice_id=1)


def test_tool_translates_apierror_into_tool_error() -> None:
    client = _make_client_mock()
    client.get_resource.side_effect = APIError(404, "not found")

    with pytest.raises(ToolError, match="not found"):
        fatture_get_invoice(_fake_ctx(client), invoice_id=999)
