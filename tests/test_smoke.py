"""Smoke tests — pure functions only, no network, no credentials."""

from __future__ import annotations

import subprocess
import sys

from fatture_cli.api import endpoints
from fatture_cli.output.formatter import _is_empty, _strip_empty
from fatture_cli.transforms.client import (
    build_client_create_body,
    summarize_client,
)
from fatture_cli.transforms.invoice import (
    build_invoice_create_body,
    build_invoice_query,
    build_invoice_update_body,
    is_overdue,
    summarize_created_invoice,
    summarize_invoice,
)

# ---------- API endpoint URL constants ----------

def test_api_base_url_is_v2_https():
    assert endpoints.API_BASE_URL == "https://api-v2.fattureincloud.it"
    assert endpoints.API_BASE_URL.startswith("https://")


def test_oauth_urls_are_strings_and_match_base():
    assert isinstance(endpoints.OAUTH_AUTHORIZE_URL, str)
    assert isinstance(endpoints.OAUTH_TOKEN_URL, str)
    assert endpoints.OAUTH_AUTHORIZE_URL.endswith("/oauth/authorize")
    assert endpoints.OAUTH_TOKEN_URL.endswith("/oauth/token")


def test_invoice_endpoints_have_company_placeholder():
    assert "{company_id}" in endpoints.INVOICES_LIST
    assert "{company_id}" in endpoints.INVOICE_DETAIL
    assert "{document_id}" in endpoints.INVOICE_DETAIL


def test_client_and_product_endpoints_have_placeholders():
    assert endpoints.CLIENTS_LIST.format(company_id=42) == "/c/42/entities/clients"
    assert endpoints.CLIENT_DETAIL.format(company_id=1, client_id=2) == "/c/1/entities/clients/2"
    assert endpoints.PRODUCTS_LIST.format(company_id=7) == "/c/7/products"
    assert endpoints.PRODUCT_DETAIL.format(company_id=7, product_id=9) == "/c/7/products/9"


# ---------- Output formatter: strips empty fields ----------

def test_is_empty_detects_none_empty_string_list_dict():
    assert _is_empty(None)
    assert _is_empty("")
    assert _is_empty([])
    assert _is_empty({})
    assert not _is_empty(0)
    assert not _is_empty("x")
    assert not _is_empty([1])


def test_strip_empty_removes_none_and_empty_values():
    data = {"a": 1, "b": None, "c": "", "d": [], "e": "ok", "f": {}}
    assert _strip_empty(data) == {"a": 1, "e": "ok"}


def test_strip_empty_recurses_into_nested_structures():
    data = {
        "outer": {"keep": "v", "drop": None},
        "list": [{"a": 1, "b": None}, {}],
    }
    cleaned = _strip_empty(data)
    assert cleaned == {"outer": {"keep": "v"}, "list": [{"a": 1}]}


# ---------- summarize_invoice handles missing fields ----------

def test_summarize_invoice_full_payload():
    doc = {
        "id": 1,
        "date": "2026-01-15",
        "number": 7,
        "numeration": "/A",
        "entity": {"name": "Acme S.r.l."},
        "amount_gross": 1220.0,
        "status": "paid",
    }
    out = summarize_invoice(doc)
    assert out == {
        "id": 1,
        "date": "2026-01-15",
        "number": "7/A",
        "client": "Acme S.r.l.",
        "total": 1220.0,
        "status": "paid",
    }


def test_summarize_invoice_handles_empty_dict():
    out = summarize_invoice({})
    assert out == {
        "id": None,
        "date": None,
        "number": None,
        "client": None,
        "total": None,
        "status": None,
    }


def test_summarize_invoice_missing_numeration_and_entity():
    out = summarize_invoice({"id": 99, "number": 42})
    assert out["id"] == 99
    assert out["number"] == 42
    assert out["client"] is None


# ---------- summarize_client handles missing fields ----------

def test_summarize_client_full_payload():
    out = summarize_client(
        {"id": 5, "name": "Rossi", "email": "a@b.it", "tax_code": "RSSMRA"}
    )
    assert out == {"id": 5, "name": "Rossi", "email": "a@b.it", "tax_code": "RSSMRA"}


def test_summarize_client_handles_empty_dict():
    assert summarize_client({}) == {
        "id": None,
        "name": None,
        "email": None,
        "tax_code": None,
    }


# ---------- create / update body builders ----------

def test_build_invoice_create_body_shape():
    body = build_invoice_create_body(
        client_id=42, product="Consulenza", amount=500.0, date="2026-05-19"
    )
    data = body["data"]
    assert data["type"] == "invoice"
    assert data["entity"] == {"id": 42}
    assert data["date"] == "2026-05-19"
    items = data["items_list"]
    assert len(items) == 1
    line = items[0]
    assert line["description"] == "Consulenza"
    assert line["net_price"] == 500.0


def test_build_invoice_create_body_coerces_types():
    body = build_invoice_create_body(client_id="7", product="X", amount="12.5", date="2026-01-01")
    assert body["data"]["entity"]["id"] == 7
    assert body["data"]["items_list"][0]["net_price"] == 12.5


def test_build_client_create_body_keeps_optional_fields():
    body = build_client_create_body(name="ACME", email="a@b.it", vat="IT123")
    assert body["data"]["name"] == "ACME"
    assert body["data"]["email"] == "a@b.it"
    assert body["data"]["vat_number"] == "IT123"


def test_build_client_create_body_drops_empty_optionals():
    body = build_client_create_body(name="Solo Name", email=None, vat="")
    assert body["data"] == {"name": "Solo Name", "type": "company"}


def test_build_invoice_update_body_only_touches_payment_status():
    body = build_invoice_update_body("paid")
    assert body == {"data": {"payment_status": "paid"}}


def test_summarize_created_invoice_combines_number_and_numeration():
    assert summarize_created_invoice(
        {"id": 99, "number": 3, "numeration": "/B", "date": "2026-05-19"}
    ) == {"id": 99, "number": "3/B", "date": "2026-05-19"}


def test_summarize_created_invoice_handles_missing_numeration():
    assert summarize_created_invoice({"id": 1, "number": 5})["number"] == 5


# ---------- list-invoices query builder ----------

def test_build_invoice_query_no_filters_omits_q():
    params = build_invoice_query(year=None, status=None)
    assert params["type"] == "invoice"
    assert "q" not in params  # 422 if q is sent empty


def test_build_invoice_query_overdue_requests_payments_list_only():
    # FiC rejects `payment_status` inside `q` with "Invalid query syntax".
    # Overdue must be enforced client-side only — the query must NOT contain it.
    params = build_invoice_query(year=None, status=None, overdue=True)
    assert "payments_list" in params["fields"]
    assert "payment_status" not in params.get("q", "")
    assert "q" not in params  # no other filter => no q at all


def test_build_invoice_query_combines_year_and_overdue():
    params = build_invoice_query(year=2026, status=None, overdue=True)
    assert params["q"] == "year(date) = 2026"
    assert "payment_status" not in params["q"]
    assert "payments_list" in params["fields"]


# ---------- is_overdue ----------

def test_is_overdue_true_when_unpaid_due_in_past():
    doc = {"payments_list": [{"due_date": "2026-01-01", "status": "not_paid"}]}
    assert is_overdue(doc, today="2026-05-19") is True


def test_is_overdue_false_when_due_in_future():
    doc = {"payments_list": [{"due_date": "2099-01-01", "status": "not_paid"}]}
    assert is_overdue(doc, today="2026-05-19") is False


def test_is_overdue_ignores_paid_payments():
    doc = {
        "payments_list": [
            {"due_date": "2020-01-01", "status": "paid"},
            {"due_date": "2099-01-01", "status": "not_paid"},
        ]
    }
    assert is_overdue(doc, today="2026-05-19") is False


def test_is_overdue_handles_missing_payments_list():
    assert is_overdue({}, today="2026-05-19") is False


# ---------- Exit code conventions ----------

def test_exit_code_two_for_missing_auth():
    # `fatture list invoices` with no credentials must exit 2 (auth error).
    result = subprocess.run(
        [sys.executable, "-m", "fatture_cli.main", "list", "invoices"],
        env={"HOME": "/tmp/__fatture_cli_no_such_home__", "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2, f"stderr={result.stderr!r}"


def test_exit_code_two_for_auth_status_when_logged_out():
    result = subprocess.run(
        [sys.executable, "-m", "fatture_cli.main", "auth", "status"],
        env={"HOME": "/tmp/__fatture_cli_no_such_home__", "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
