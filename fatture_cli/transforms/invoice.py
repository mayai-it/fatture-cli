"""Pure transforms for invoice payloads.

Builders translate user/CLI inputs into Fatture in Cloud request bodies and
query params; summarizers/detailers collapse FiC response payloads into the
compact dict shapes the CLI and MCP server emit. No I/O, no APIClient.
"""

from __future__ import annotations

from typing import Any

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
    """
    for p in doc.get("payments_list") or []:
        if (p.get("status") or "").lower() == "paid":
            continue
        due = p.get("due_date")
        if due and str(due) < today:
            return True
    return False


def summarize_invoice(doc: dict[str, Any]) -> dict[str, Any]:
    """Compact list-view shape: id, date, number, client, total, status."""
    entity = doc.get("entity") or {}
    number = doc.get("number")
    numeration = doc.get("numeration")
    full_number = f"{number}{numeration}" if numeration else number
    return {
        "id": doc.get("id"),
        "date": doc.get("date"),
        "number": full_number,
        "client": entity.get("name"),
        "total": doc.get("amount_gross"),
        "status": doc.get("status"),
    }


def detail_invoice(doc: dict[str, Any]) -> dict[str, Any]:
    """Full single-invoice view including line items and payment schedule."""
    entity = doc.get("entity") or {}
    number = doc.get("number")
    numeration = doc.get("numeration")
    full_number = f"{number}{numeration}" if numeration else number

    lines: list[dict[str, Any]] = []
    for item in doc.get("items_list") or []:
        lines.append({
            "description": item.get("name") or item.get("description"),
            "qty": item.get("qty"),
            "amount_net": item.get("net_price"),
            "amount_gross": item.get("gross_price"),
        })

    payments = [summarize_payment(p) for p in doc.get("payments_list") or []]

    return {
        "id": doc.get("id"),
        "date": doc.get("date"),
        "number": full_number,
        "client": entity.get("name"),
        "client_id": entity.get("id"),
        "lines": lines,
        "amount_net": doc.get("amount_net"),
        "total": doc.get("amount_gross"),
        "currency": (doc.get("currency") or {}).get("id"),
        "status": doc.get("status"),
        "payment_method": (doc.get("payment_method") or {}).get("name"),
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


def build_invoice_update_body(status: str) -> dict[str, Any]:
    """Build the PUT body for `update invoice --status`. Touches only payment_status."""
    return {"data": {"payment_status": status}}


def summarize_created_invoice(doc: dict[str, Any]) -> dict[str, Any]:
    """Compact response for `create invoice`: just enough to confirm + reference."""
    number = doc.get("number")
    numeration = doc.get("numeration")
    full_number = f"{number}{numeration}" if numeration else number
    return {
        "id": doc.get("id"),
        "number": full_number,
        "date": doc.get("date"),
    }
