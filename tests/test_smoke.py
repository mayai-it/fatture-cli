"""Smoke tests — pure functions only, no network, no credentials."""

from __future__ import annotations

import subprocess
import sys

from fatture_cli.api import endpoints
from fatture_cli.main import _summarize_client, _summarize_invoice
from fatture_cli.output.formatter import _is_empty, _strip_empty


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


# ---------- _summarize_invoice handles missing fields ----------

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
    out = _summarize_invoice(doc)
    assert out == {
        "id": 1,
        "date": "2026-01-15",
        "number": "7/A",
        "client": "Acme S.r.l.",
        "total": 1220.0,
        "status": "paid",
    }


def test_summarize_invoice_handles_empty_dict():
    out = _summarize_invoice({})
    assert out == {
        "id": None,
        "date": None,
        "number": None,
        "client": None,
        "total": None,
        "status": None,
    }


def test_summarize_invoice_missing_numeration_and_entity():
    out = _summarize_invoice({"id": 99, "number": 42})
    assert out["id"] == 99
    assert out["number"] == 42
    assert out["client"] is None


# ---------- _summarize_client handles missing fields ----------

def test_summarize_client_full_payload():
    out = _summarize_client(
        {"id": 5, "name": "Rossi", "email": "a@b.it", "tax_code": "RSSMRA"}
    )
    assert out == {"id": 5, "name": "Rossi", "email": "a@b.it", "tax_code": "RSSMRA"}


def test_summarize_client_handles_empty_dict():
    assert _summarize_client({}) == {
        "id": None,
        "name": None,
        "email": None,
        "tax_code": None,
    }


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
