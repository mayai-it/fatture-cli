"""Pydantic model validation, type-coercion, and tolerance tests.

These guard the two non-negotiables: monetary fields are always Decimal
(never float) regardless of input shape, and unknown API fields don't break
existing clients.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from fatture_cli.models import (
    Client,
    Invoice,
    InvoiceLine,
    PaginatedResponse,
    Product,
)


def test_invoice_parses_minimal_payload():
    inv = Invoice.model_validate({"id": 42, "date": "2026-01-15"})

    assert inv.id == 42
    assert inv.date == date(2026, 1, 15)
    assert inv.amount_gross is None
    assert inv.entity is None


def test_invoice_validation_error_on_missing_required_fields():
    # Both id and date are required. The error must name the missing field so
    # API debugging stays readable.
    with pytest.raises(ValidationError) as exc_id:
        Invoice.model_validate({"date": "2026-01-15"})
    errors_id = exc_id.value.errors()
    assert any(e["loc"] == ("id",) and e["type"] == "missing" for e in errors_id)

    with pytest.raises(ValidationError) as exc_date:
        Invoice.model_validate({"id": 1})
    errors_date = exc_date.value.errors()
    assert any(e["loc"] == ("date",) and e["type"] == "missing" for e in errors_date)

    # Empty payload — both must be reported.
    with pytest.raises(ValidationError) as exc_both:
        Invoice.model_validate({})
    locs = {e["loc"] for e in exc_both.value.errors() if e["type"] == "missing"}
    assert ("id",) in locs
    assert ("date",) in locs


def test_invoice_tolerates_unknown_fields():
    # FiC adds fields over time. extra="allow" must keep payloads parseable.
    inv = Invoice.model_validate({
        "id": 1,
        "date": "2026-01-15",
        "future_field_we_dont_know_yet": "ignored gracefully",
        "another_new_thing": {"nested": [1, 2, 3]},
    })

    assert inv.id == 1
    # Unknown extras land in model_extra rather than being dropped.
    assert inv.model_extra is not None
    assert "future_field_we_dont_know_yet" in inv.model_extra


def test_invoice_amount_is_decimal_not_float():
    inv = Invoice.model_validate({
        "id": 1,
        "date": "2026-01-15",
        "amount_net": 1000.0,
        "amount_vat": 220.0,
        "amount_gross": 1220.0,
    })

    assert isinstance(inv.amount_net, Decimal)
    assert isinstance(inv.amount_vat, Decimal)
    assert isinstance(inv.amount_gross, Decimal)
    # The cardinal sin we're avoiding: 0.1 + 0.2 = 0.30000000000000004.
    inv2 = Invoice.model_validate({"id": 2, "date": "2026-01-01", "amount_net": "0.1"})
    inv3 = Invoice.model_validate({"id": 3, "date": "2026-01-01", "amount_net": "0.2"})
    assert inv2.amount_net is not None and inv3.amount_net is not None
    assert inv2.amount_net + inv3.amount_net == Decimal("0.3")


def test_invoice_handles_string_amounts():
    # FiC frequently returns amounts as strings ("1234.56"). Pydantic must coerce
    # them into Decimal without losing precision.
    inv = Invoice.model_validate({
        "id": 1,
        "date": "2026-01-15",
        "amount_gross": "1234.56",
    })

    assert inv.amount_gross == Decimal("1234.56")
    assert isinstance(inv.amount_gross, Decimal)


def test_invoice_line_qty_and_prices_are_decimal():
    line = InvoiceLine.model_validate({
        "name": "Consulenza",
        "qty": "2.5",
        "net_price": "100.00",
        "gross_price": "122.00",
    })

    assert isinstance(line.qty, Decimal)
    assert isinstance(line.net_price, Decimal)
    assert isinstance(line.gross_price, Decimal)
    assert line.qty * line.net_price == Decimal("250.00")


def test_client_parses_with_optional_email_none():
    client = Client.model_validate({
        "id": 5,
        "name": "Acme S.r.l.",
        "email": None,
    })

    assert client.id == 5
    assert client.name == "Acme S.r.l."
    assert client.email is None


def test_client_accepts_empty_dict():
    # Entity has no required fields — empty payload validates with all None.
    client = Client.model_validate({})

    assert client.id is None
    assert client.name is None


def test_product_net_price_is_decimal():
    product = Product.model_validate({
        "id": 7,
        "name": "Consulenza oraria",
        "net_price": "75.00",
    })

    assert isinstance(product.net_price, Decimal)
    assert product.net_price == Decimal("75.00")


def test_paginated_response_generic_with_invoice():
    page = PaginatedResponse[Invoice].model_validate({
        "data": [
            {"id": 1, "date": "2026-01-15"},
            {"id": 2, "date": "2026-01-16"},
        ],
        "current_page": 1,
        "last_page": 3,
        "per_page": 100,
        "total": 250,
    })

    assert len(page.data) == 2
    assert all(isinstance(item, Invoice) for item in page.data)
    assert page.data[0].id == 1
    assert page.last_page == 3


def test_paginated_response_generic_with_client():
    # Same generic with a different T binds correctly.
    page = PaginatedResponse[Client].model_validate({
        "data": [{"id": 1, "name": "ACME"}, {"id": 2, "name": "Rossi"}],
        "current_page": 1,
    })

    assert len(page.data) == 2
    assert all(isinstance(item, Client) for item in page.data)
    assert page.data[1].name == "Rossi"
