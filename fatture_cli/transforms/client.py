"""Pure transforms for client (entity) payloads."""

from __future__ import annotations

from typing import Any

from fatture_cli.models.client import Client


def summarize_client(doc: dict[str, Any]) -> dict[str, Any]:
    """Compact list-view shape: id, name, email, tax_code."""
    client = Client.model_validate(doc)
    return {
        "id": client.id,
        "name": client.name,
        "email": client.email,
        "tax_code": client.tax_code,
    }


def detail_client(doc: dict[str, Any]) -> dict[str, Any]:
    """Full single-client view including address breakdown."""
    client = Client.model_validate(doc)
    address = {
        "street": client.address_street,
        "postal_code": client.address_postal_code,
        "city": client.address_city,
        "province": client.address_province,
        "extra": client.address_extra,
        "country": client.country,
    }
    return {
        "id": client.id,
        "name": client.name,
        "email": client.email,
        "certified_email": client.certified_email,
        "phone": client.phone,
        "tax_code": client.tax_code,
        "vat_number": client.vat_number,
        "address": address,
    }


def build_client_create_body(
    name: str,
    email: str | None,
    vat: str | None,
) -> dict[str, Any]:
    """Build the POST body for `create client`. Drops empty optional fields."""
    data: dict[str, Any] = {"name": name, "type": "company"}
    if email:
        data["email"] = email
    if vat:
        data["vat_number"] = vat
    return {"data": data}
