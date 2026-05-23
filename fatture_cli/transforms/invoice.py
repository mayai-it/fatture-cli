"""Pure transforms for invoice payloads.

Builders translate user/CLI inputs into Fatture in Cloud request bodies and
query params; summarizers/detailers parse FiC response payloads through
Pydantic models (validation + Decimal coercion for money) and collapse them
into the compact dict shapes the CLI and MCP server emit. No I/O, no APIClient.
"""

from __future__ import annotations

from typing import Any

from fatture_cli.models.invoice import Invoice
from fatture_cli.transforms.payment import summarize_payment

_INVOICE_FIELDS = "id,number,numeration,date,entity,amount_net,amount_gross,status"
_INVOICE_FIELDS_WITH_PAYMENTS = _INVOICE_FIELDS + ",payments_list"


def build_invoice_query(
    year: int | None,
    status: str | None,
    overdue: bool = False,
) -> dict[str, str]:
    """Translate user flags into Fatture in Cloud query params.

    FiC takes `type` as a top-level query param. Additional filters go into
    the `q=` expression — and `q` must be omitted entirely when empty,
    otherwise the API responds 422.

    When `overdue` is set we request `payments_list` so the caller can apply
    a client-side due-date check. We deliberately do NOT add `payment_status`
    to `q` — FiC rejects it as "Invalid query syntax". The overdue filter is
    therefore entirely client-side.
    """
    params: dict[str, str] = {
        "type": "invoice",
        "fields": _INVOICE_FIELDS_WITH_PAYMENTS if overdue else _INVOICE_FIELDS,
        "per_page": "100",
        "sort": "-date",
    }
    filters: list[str] = []
    if year is not None:
        filters.append(f"year(date) = {year}")
    if status:
        filters.append(f'status = "{status}"')
    if filters:
        params["q"] = " AND ".join(filters)
    return params


def is_overdue(doc: dict[str, Any], today: str) -> bool:
    """True if any unpaid payment on `doc` has due_date strictly before `today`.

    `today` is an ISO date string (YYYY-MM-DD). ISO strings compare
    lexicographically the same way as chronologically, so we avoid parsing.
    A payment whose status is "paid" never counts as overdue, regardless of
    its due date.

    Operates on raw dicts (no Invoice model) so the list-invoices loop can
    cheaply filter before paying the full validation cost.
    """
    for p in doc.get("payments_list") or []:
        if (p.get("status") or "").lower() == "paid":
            continue
        due = p.get("due_date")
        if due and str(due) < today:
            return True
    return False


def summarize_invoice(doc: dict[str, Any]) -> dict[str, Any]:
    """Compact list-view shape: id, date, number, client, total, status.

    Validates through the ``Invoice`` model so monetary fields land as
    ``Decimal`` and dates as ``date`` regardless of whether the API sent
    numbers, strings, or ISO dates.
    """
    inv = Invoice.model_validate(doc)
    entity = inv.entity or {}
    full_number = f"{inv.number}{inv.numeration}" if inv.numeration else inv.number
    return {
        "id": inv.id,
        "date": inv.date.isoformat(),
        "number": full_number,
        "client": entity.get("name"),
        "total": inv.amount_gross,
        "status": inv.status,
    }


def detail_invoice(doc: dict[str, Any]) -> dict[str, Any]:
    """Full single-invoice view including line items and payment schedule."""
    inv = Invoice.model_validate(doc)
    entity = inv.entity or {}
    currency = inv.currency or {}
    payment_method = inv.payment_method or {}

    full_number = f"{inv.number}{inv.numeration}" if inv.numeration else inv.number

    lines: list[dict[str, Any]] = []
    for item in inv.items_list or []:
        lines.append({
            "description": item.name or item.description,
            "qty": item.qty,
            "amount_net": item.net_price,
            "amount_gross": item.gross_price,
        })

    payments = [summarize_payment(p) for p in inv.payments_list or []]

    return {
        "id": inv.id,
        "date": inv.date.isoformat(),
        "number": full_number,
        "client": entity.get("name"),
        "client_id": entity.get("id"),
        "lines": lines,
        "amount_net": inv.amount_net,
        "total": inv.amount_gross,
        "currency": currency.get("id"),
        "status": inv.status,
        "payment_method": payment_method.get("name"),
        "payments": payments,
    }


def build_invoice_create_body(
    client_id: int,
    product: str,
    amount: float,
    date: str,
) -> dict[str, Any]:
    """Build the POST body for `create invoice`.

    Minimal valid shape per FiC: entity.id, items_list[0].description, date.
    We send `name` too so the line item renders with a label in the FiC UI.
    """
    return {
        "data": {
            "type": "invoice",
            "entity": {"id": int(client_id)},
            "date": date,
            "items_list": [
                {
                    "name": product,
                    "description": product,
                    "qty": 1,
                    "net_price": float(amount),
                }
            ],
        }
    }


def build_invoice_update_body(**patch_fields: Any) -> dict[str, Any]:
    """Build the PUT body for ``update invoice``.

    FiC's modify_issued_document endpoint operates in delta mode: only the
    fields included in ``data`` are touched, the rest stay as-is. Callers
    pass keyword arguments for every field they want to modify; ``None``
    values are filtered out so a missing CLI flag never accidentally clears
    a server-side value.
    """
    data = {k: v for k, v in patch_fields.items() if v is not None}
    return {"data": data}


def build_mark_paid_body(paid_date: str | None = None) -> dict[str, Any]:
    """Build the PUT body for marking an invoice as paid.

    Sets ``payment_status="paid"`` at the document level. ``paid_date`` is
    accepted for future use (per-payment tracking would require fetching
    payments_list first) but currently informational — the document-level
    payment_status is what FiC's UI reflects.
    """
    fields: dict[str, Any] = {"payment_status": "paid"}
    if paid_date:
        fields["paid_date"] = paid_date
    return build_invoice_update_body(**fields)


def build_send_invoice_email_body(
    recipient_email: str,
    sender_email: str | None = None,
    subject: str | None = None,
    body: str | None = None,
    attach_pdf: bool = True,
) -> dict[str, Any]:
    """Build the POST body for the schedule-email endpoint.

    Matches FiC's ``ScheduleEmailRequest`` → ``data: EmailSchedule`` shape.
    ``sender_email`` is optional: when omitted, FiC falls back to the
    company's default sender configured in the developer console.
    """
    email: dict[str, Any] = {
        "recipient_email": recipient_email,
        "attach_pdf": attach_pdf,
    }
    if sender_email:
        email["sender_email"] = sender_email
    if subject:
        email["subject"] = subject
    if body:
        email["body"] = body
    return {"data": email}


def summarize_ei_status(doc: dict[str, Any]) -> dict[str, Any]:
    """Diagnostic summary of an invoice's e-invoice / SDI transmission state.

    Returns only the fields relevant to "will this go to SDI? has it gone?"
    without exposing the full IssuedDocument surface. Pure read-only — no
    transmission, no mutation.
    """
    inv = Invoice.model_validate(doc)
    ei_data_raw = doc.get("ei_data") if isinstance(doc.get("ei_data"), dict) else {}
    return {
        "id": inv.id,
        "number": f"{inv.number}{inv.numeration}" if inv.numeration else inv.number,
        "e_invoice": inv.e_invoice,
        "ei_status": inv.ei_status,
        "ei_data": {k: v for k, v in (ei_data_raw or {}).items() if v not in (None, "", [], {})},
    }


def summarize_created_invoice(doc: dict[str, Any]) -> dict[str, Any]:
    """Compact response for `create invoice`: just enough to confirm + reference."""
    inv = Invoice.model_validate(doc)
    full_number = f"{inv.number}{inv.numeration}" if inv.numeration else inv.number
    return {
        "id": inv.id,
        "number": full_number,
        "date": inv.date.isoformat(),
    }
