"""Pure transforms for product (article / service) payloads."""

from __future__ import annotations

from typing import Any

from fatture_cli.models.product import Product


def summarize_product(doc: dict[str, Any]) -> dict[str, Any]:
    """Compact list-view shape: id, name, price, vat_type."""
    product = Product.model_validate(doc)
    vat = product.vat or product.default_vat or {}
    return {
        "id": product.id,
        "name": product.name,
        "price": product.net_price,
        "vat_type": vat.get("description") or vat.get("value"),
    }
