"""Pydantic model for the Product resource.

Field names mirror the JSON wire format verified against the official Python
SDK's ``Product`` schema. Monetary fields are ``Decimal`` (the SDK uses
``float``; we override for accounting precision).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict


class Product(BaseModel):
    """A Product / service catalog entry. All fields optional."""

    model_config = ConfigDict(extra="allow")

    id: int | None = None
    name: str | None = None
    code: str | None = None
    # Money — Decimal mandatory.
    net_price: Decimal | None = None
    gross_price: Decimal | None = None
    use_gross_price: bool | None = None
    default_vat: dict[str, Any] | None = None
    # Some FiC list-endpoint responses flatten the field name to plain `vat`.
    # Keeping both lets summarize_product fall back without losing precision.
    vat: dict[str, Any] | None = None
    net_cost: Decimal | None = None
    measure: str | None = None
    description: str | None = None
    category: str | None = None
    notes: str | None = None
    in_stock: bool | None = None
    # Stock counts can be fractional (e.g. 1.5 kg of bulk goods).
    stock_initial: Decimal | None = None
    stock_current: Decimal | None = None
    average_cost: Decimal | None = None
    average_price: Decimal | None = None
    created_at: str | None = None
    updated_at: str | None = None
