"""Pure transforms for client (entity) payloads."""

from __future__ import annotations

from typing import Any


def summarize_client(doc: dict[str, Any]) -> dict[str, Any]:
    """Compact list-view shape: id, name, email, tax_code."""
    return {
        "id": doc.get("id"),
        "name": doc.get("name"),
        "email": doc.get("email"),
        "tax_code": doc.get("tax_code"),
    }


def detail_client(doc: dict[str, Any]) -> dict[str, Any]:
    """Full single-client view including address breakdown."""
    address = {
        "street": doc.get("address_street"),
        "postal_code": doc.get("address_postal_code"),
        "city": doc.get("address_city"),
        "province": doc.get("address_province"),
        "extra": doc.get("address_extra"),
        "country": doc.get("country"),
    }
    return {
        "id": doc.get("id"),
        "name": doc.get("name"),
        "email": doc.get("email"),
        "certified_email": doc.get("certified_email"),
        "phone": doc.get("phone"),
        "tax_code": doc.get("tax_code"),
        "vat_number": doc.get("vat_number"),
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
