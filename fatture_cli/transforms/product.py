"""Pure transforms for product (article / service) payloads."""

from __future__ import annotations

from typing import Any


def summarize_product(doc: dict[str, Any]) -> dict[str, Any]:
    """Compact list-view shape: id, name, price, vat_type."""
    vat = doc.get("vat") or {}
    return {
        "id": doc.get("id"),
        "name": doc.get("name"),
        "price": doc.get("net_price"),
        "vat_type": vat.get("description") or vat.get("value"),
    }
