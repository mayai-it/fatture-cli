"""Pydantic models for Fatture in Cloud resources.

These mirror the JSON wire format of the FiC API v2 (verified against the
official Python SDK schemas) with one deliberate deviation: every monetary
field is ``Decimal`` rather than ``float``, for accounting precision.
"""

from __future__ import annotations

from fatture_cli.models.client import Client
from fatture_cli.models.common import PaginatedResponse
from fatture_cli.models.invoice import Invoice, InvoiceLine, InvoicePayment
from fatture_cli.models.product import Product

__all__ = [
    "Client",
    "Invoice",
    "InvoiceLine",
    "InvoicePayment",
    "PaginatedResponse",
    "Product",
]
