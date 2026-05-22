"""Pydantic model for the Entity (client) resource.

Field names mirror the JSON wire format verified against the official Python
SDK's ``Entity`` schema. All fields are optional — the FiC ``Entity`` doc
itself declares every property without a required marker.
"""

from __future__ import annotations

from datetime import date as _date

from pydantic import BaseModel, ConfigDict


class Client(BaseModel):
    """An Entity record (client or supplier). All fields optional."""

    model_config = ConfigDict(extra="allow")

    id: int | None = None
    code: str | None = None
    name: str | None = None
    type: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    contact_person: str | None = None
    vat_number: str | None = None
    tax_code: str | None = None
    address_street: str | None = None
    address_postal_code: str | None = None
    address_city: str | None = None
    address_province: str | None = None
    address_extra: str | None = None
    country: str | None = None
    country_iso: str | None = None
    email: str | None = None
    certified_email: str | None = None
    phone: str | None = None
    fax: str | None = None
    notes: str | None = None
    default_payment_terms: int | None = None
    bank_name: str | None = None
    bank_iban: str | None = None
    bank_swift_code: str | None = None
    shipping_address: str | None = None
    e_invoice: bool | None = None
    ei_code: str | None = None
    has_intent_declaration: bool | None = None
    intent_declaration_protocol_number: str | None = None
    intent_declaration_protocol_date: _date | None = None
    created_at: str | None = None
    updated_at: str | None = None
