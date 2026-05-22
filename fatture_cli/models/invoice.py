"""Pydantic models for the Issued Document (invoice) resource.

Field names mirror the JSON wire format returned by Fatture in Cloud API v2.
Verified against the official Python SDK's documented schemas
(IssuedDocument, IssuedDocumentItemsListItem, IssuedDocumentPaymentsListItem).

CRITICAL: every monetary field is ``Decimal``, never ``float``. The official
SDK uses ``float`` but float arithmetic produces 0.1 + 0.2 = 0.30000000000000004
— unacceptable for accounting. Pydantic 2 coerces both numeric and string
inputs (FiC sometimes returns "1234.56") into ``Decimal``.

Only ``id`` and ``date`` are required; everything else is optional so partial
responses (e.g. ``fields=`` query trimming) don't fail validation. ``extra="allow"``
keeps the model forward-compatible with FiC field additions.
"""

from __future__ import annotations

from datetime import date as _date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict


class InvoiceLine(BaseModel):
    """A single line item inside ``items_list`` (IssuedDocumentItemsListItem)."""

    model_config = ConfigDict(extra="allow")

    id: int | None = None
    product_id: int | None = None
    code: str | None = None
    name: str | None = None
    category: str | None = None
    description: str | None = None
    # qty is allowed to be fractional; Decimal preserves precision in totals.
    qty: Decimal | None = None
    measure: str | None = None
    net_price: Decimal | None = None
    gross_price: Decimal | None = None
    vat: dict[str, Any] | None = None
    not_taxable: bool | None = None
    apply_withholding_taxes: bool | None = None
    discount: Decimal | None = None
    discount_highlight: bool | None = None
    in_dn: bool | None = None
    stock: bool | None = None


class InvoicePayment(BaseModel):
    """A single payment expiry inside ``payments_list`` (IssuedDocumentPaymentsListItem)."""

    model_config = ConfigDict(extra="allow")

    id: int | None = None
    due_date: _date | None = None
    amount: Decimal | None = None
    # Kept as plain str — the upstream IssuedDocumentStatus enum is rendered as a
    # string on the wire ("paid", "not_paid", ...); we don't reflect the enum here.
    status: str | None = None
    paid_date: _date | None = None
    payment_account: dict[str, Any] | None = None


class Invoice(BaseModel):
    """An Issued Document (typically an invoice).

    Required: ``id`` and ``date``. All other fields optional.

    Note on naming: the official Python SDK exposes ``date`` as ``var_date``
    purely to avoid shadowing the ``datetime.date`` type inside its generated
    code. The JSON wire field is plain ``date``; we keep the Python attribute
    name aligned with the wire (no alias needed — ``_date`` import sidesteps
    the type-vs-name conflict).
    """

    model_config = ConfigDict(extra="allow")

    id: int
    date: _date

    # Identification
    type: str | None = None
    number: int | None = None
    numeration: str | None = None
    year: int | None = None
    subject: str | None = None
    visible_subject: str | None = None
    notes: str | None = None

    # Nested references kept as plain dicts: we only ever read one or two
    # attributes from them (e.g. entity.name), and modeling each fully would
    # explode the type surface for no real gain.
    entity: dict[str, Any] | None = None
    currency: dict[str, Any] | None = None
    payment_method: dict[str, Any] | None = None

    # Collections
    items_list: list[InvoiceLine] | None = None
    payments_list: list[InvoicePayment] | None = None

    # Monetary totals — Decimal mandatory.
    amount_net: Decimal | None = None
    amount_vat: Decimal | None = None
    amount_gross: Decimal | None = None

    # Status and flags
    status: str | None = None
    use_split_payment: bool | None = None
    use_gross_prices: bool | None = None
    e_invoice: bool | None = None
    ei_status: str | None = None

    # Audit
    created_at: str | None = None
    updated_at: str | None = None
