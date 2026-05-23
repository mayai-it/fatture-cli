"""MCP server exposing fatture-cli as native tools for AI agents.

Runs over stdio with FastMCP. A lifespan context loads credentials and
opens a single APIClient at startup; tools read it from
`ctx.request_context.lifespan_context`.

All stdout is reserved for the MCP transport — never `print()` here.
Diagnostics (if any) must go to stderr via `logging`.
"""

from __future__ import annotations

import base64
import datetime as _dt
import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from fatture_cli.api import APIClient, APIError
from fatture_cli.api.endpoints import (
    CLIENTS_LIST,
    INVOICE_DETAIL,
    INVOICES_LIST,
)
from fatture_cli.auth import load_credentials
from fatture_cli.transforms.client import (
    build_client_create_body,
    build_client_update_body,
    summarize_client,
)
from fatture_cli.transforms.invoice import (
    build_invoice_create_body,
    build_invoice_query,
    build_invoice_update_body,
    build_mark_paid_body,
    build_send_invoice_email_body,
    detail_invoice,
    is_overdue,
    summarize_created_invoice,
    summarize_ei_status,
    summarize_invoice,
)

log = logging.getLogger("fatture.mcp")


@dataclass
class AppContext:
    """Lifespan-scoped state shared by all tool invocations."""

    client: APIClient | None
    company_id: int | None


@asynccontextmanager
async def lifespan(_server: FastMCP) -> AsyncIterator[AppContext]:
    creds = load_credentials()
    if creds is None:
        # Yield an empty context — individual tools raise ToolError with a
        # clear message so the agent learns it must run `fatture auth login`.
        log.warning("no credentials on disk — tools will fail until login")
        yield AppContext(client=None, company_id=None)
        return

    client = APIClient(creds)
    try:
        yield AppContext(client=client, company_id=creds.company_id)
    finally:
        client.close()


mcp = FastMCP("fatture", lifespan=lifespan)


def _require(ctx: Context) -> tuple[APIClient, int]:
    """Return a live (client, company_id) pair or raise ToolError."""
    app: AppContext = ctx.request_context.lifespan_context
    if app.client is None:
        raise ToolError("not authenticated — run `fatture auth login` first")
    if not app.company_id:
        raise ToolError("no active company — run `fatture auth login` again")
    return app.client, app.company_id


def _paginate(client: APIClient, path: str, params: dict[str, str]) -> list[dict]:
    """Walk all pages of a FiC list endpoint and return concatenated `data`."""
    out: list[dict] = []
    page = 1
    while True:
        params["page"] = str(page)
        payload = client.get_paginated(path, params=params)
        for doc in payload.get("data") or []:
            out.append(doc)
        last_page = payload.get("last_page") or 1
        if page >= last_page:
            break
        page += 1
    return out


@mcp.tool()
def fatture_list_invoices(
    ctx: Context,
    year: int | None = None,
    status: str | None = None,
    overdue: bool = False,
    limit: int = 20,
) -> list[dict]:
    """List invoices. Returns id, date, number, client, total, status."""
    client, company_id = _require(ctx)
    path = INVOICES_LIST.format(company_id=company_id)
    params = build_invoice_query(year, status, overdue=overdue)
    today = _dt.date.today().isoformat()

    rows: list[dict] = []
    page = 1
    try:
        while True:
            params["page"] = str(page)
            payload = client.get_paginated(path, params=params)
            for doc in payload.get("data") or []:
                if overdue:
                    if (doc.get("status") or "").lower() == "paid":
                        continue
                    if not is_overdue(doc, today):
                        continue
                rows.append(summarize_invoice(doc))
                if len(rows) >= limit:
                    return rows
            last_page = payload.get("last_page") or 1
            if page >= last_page:
                return rows
            page += 1
    except APIError as exc:
        raise ToolError(exc.message) from exc


@mcp.tool()
def fatture_get_invoice(ctx: Context, invoice_id: int) -> dict:
    """Get full invoice details including lines and payments."""
    client, company_id = _require(ctx)
    path = INVOICE_DETAIL.format(company_id=company_id, document_id=invoice_id)
    try:
        payload = client.get_resource(path, params={"type": "invoice"})
    except APIError as exc:
        raise ToolError(exc.message) from exc
    return detail_invoice(payload.get("data") or {})


@mcp.tool()
def fatture_list_clients(ctx: Context, limit: int = 50) -> list[dict]:
    """List clients. Returns id, name, email, tax_code."""
    client, company_id = _require(ctx)
    path = CLIENTS_LIST.format(company_id=company_id)
    params: dict[str, str] = {
        "fields": "id,name,email,tax_code",
        "per_page": "100",
        "sort": "name",
    }

    rows: list[dict] = []
    page = 1
    try:
        while True:
            params["page"] = str(page)
            payload = client.get_paginated(path, params=params)
            for doc in payload.get("data") or []:
                rows.append(summarize_client(doc))
                if len(rows) >= limit:
                    return rows
            last_page = payload.get("last_page") or 1
            if page >= last_page:
                return rows
            page += 1
    except APIError as exc:
        raise ToolError(exc.message) from exc


@mcp.tool()
def fatture_search_clients(ctx: Context, query: str) -> list[dict]:
    """Search clients by name."""
    client, company_id = _require(ctx)
    path = CLIENTS_LIST.format(company_id=company_id)
    escaped = query.replace("'", "")
    params: dict[str, str] = {
        "fields": "id,name,email,tax_code",
        "per_page": "100",
        "sort": "name",
        "q": f"name LIKE '%{escaped}%'",
    }
    try:
        docs = _paginate(client, path, params)
    except APIError as exc:
        raise ToolError(exc.message) from exc
    return [summarize_client(d) for d in docs]


@mcp.tool()
def fatture_create_invoice(
    ctx: Context,
    client_id: int,
    product: str,
    amount: float,
    date: str | None = None,
) -> dict:
    """Create invoice. date format YYYY-MM-DD. Returns id and number."""
    client, company_id = _require(ctx)
    issue_date = date or _dt.date.today().isoformat()
    body = build_invoice_create_body(client_id, product, amount, issue_date)
    path = INVOICES_LIST.format(company_id=company_id)
    try:
        payload = client.post_resource(path, json=body)
    except APIError as exc:
        raise ToolError(exc.message) from exc
    return summarize_created_invoice(payload.get("data") or {})


@mcp.tool()
def fatture_create_client(
    ctx: Context,
    name: str,
    email: str | None = None,
    vat: str | None = None,
) -> dict:
    """Create a new client. Returns id and name."""
    client, company_id = _require(ctx)
    body = build_client_create_body(name, email, vat)
    path = CLIENTS_LIST.format(company_id=company_id)
    try:
        payload = client.post_resource(path, json=body)
    except APIError as exc:
        raise ToolError(exc.message) from exc
    data = payload.get("data") or {}
    return {"id": data.get("id"), "name": data.get("name")}


@mcp.tool()
def fatture_auth_status(ctx: Context) -> dict:
    """Check auth status. Returns authenticated, company_id, expires_at."""
    app: AppContext = ctx.request_context.lifespan_context
    if app.client is None:
        return {"authenticated": False}
    creds = app.client.credentials
    return {
        "authenticated": True,
        "company_id": creds.company_id,
        "expires_at": creds.expires_at,
        "expired": creds.is_expired,
    }


# ---------------------------------------------------------------------------
# Write tools (added in 0.3.0)
# ---------------------------------------------------------------------------


@mcp.tool()
def update_invoice(
    ctx: Context,
    invoice_id: int,
    payment_status: str | None = None,
    date: str | None = None,
    number: int | None = None,
    notes: str | None = None,
    visible_subject: str | None = None,
) -> dict[str, Any]:
    """Update an existing invoice. Pass only the fields you want to change
    (delta mode); fields left as None stay untouched on the server.

    IMPORTANT: invoices already transmitted to SDI cannot be modified.
    The API will return 4xx; check `get_invoice_ei_status` first if unsure.
    """
    client, company_id = _require(ctx)
    fields: dict[str, Any] = {
        k: v
        for k, v in {
            "payment_status": payment_status,
            "date": date,
            "number": number,
            "notes": notes,
            "visible_subject": visible_subject,
        }.items()
        if v is not None
    }
    if not fields:
        raise ToolError("update_invoice: at least one field must be specified")

    body = build_invoice_update_body(**fields)
    path = INVOICE_DETAIL.format(company_id=company_id, document_id=invoice_id)
    try:
        payload = client.put_resource(path, json=body)
    except APIError as exc:
        raise ToolError(exc.message) from exc
    data = payload.get("data") or {}
    return {"id": data.get("id") or invoice_id, "updated_fields": list(fields)}


@mcp.tool()
def mark_invoice_paid(
    ctx: Context, invoice_id: int, paid_date: str | None = None
) -> dict[str, Any]:
    """Mark an invoice as paid. `paid_date` defaults to today (YYYY-MM-DD).

    Note: this updates the document-level `payment_status` only — it does
    NOT record an actual cash/bank movement against the company books.
    """
    client, company_id = _require(ctx)
    effective_date = paid_date or _dt.date.today().isoformat()
    body = build_mark_paid_body(paid_date=effective_date)
    path = INVOICE_DETAIL.format(company_id=company_id, document_id=invoice_id)
    try:
        payload = client.put_resource(path, json=body)
    except APIError as exc:
        raise ToolError(exc.message) from exc
    data = payload.get("data") or {}
    return {
        "id": data.get("id") or invoice_id,
        "payment_status": "paid",
        "paid_date": effective_date,
    }


@mcp.tool()
def send_invoice_email(
    ctx: Context,
    invoice_id: int,
    to_email: str,
    from_email: str | None = None,
    subject: str | None = None,
    body: str | None = None,
    attach_pdf: bool = True,
) -> dict[str, Any]:
    """Email an invoice to a recipient.

    `from_email` is optional: if omitted, FiC uses the company's default
    sender configured in the developer console. Returns the API confirmation.
    """
    client, company_id = _require(ctx)
    payload_body = build_send_invoice_email_body(
        recipient_email=to_email,
        sender_email=from_email,
        subject=subject,
        body=body,
        attach_pdf=attach_pdf,
    )
    path = f"/c/{company_id}/issued_documents/{invoice_id}/email"
    try:
        payload = client.post_resource(path, json=payload_body)
    except APIError as exc:
        raise ToolError(exc.message) from exc
    return {
        "scheduled": True,
        "invoice_id": invoice_id,
        "recipient": to_email,
        "response": payload.get("data"),
    }


@mcp.tool()
def get_invoice_pdf(ctx: Context, invoice_id: int) -> dict[str, Any]:
    """Download an invoice PDF and return it as a base64 string.

    The MCP transport is JSON, so the binary content is base64-encoded.
    Agents save the file by base64-decoding `pdf_base64` and writing the
    resulting bytes locally.
    """
    client, company_id = _require(ctx)
    path = INVOICE_DETAIL.format(company_id=company_id, document_id=invoice_id)
    try:
        payload = client.get_resource(path, params={"type": "invoice"})
    except APIError as exc:
        raise ToolError(exc.message) from exc

    data = payload.get("data") or {}
    pdf_url = data.get("url")
    if not pdf_url:
        raise ToolError(
            "invoice has no downloadable PDF (no 'url' field in API response)"
        )
    try:
        pdf_bytes = client.get_binary_url(pdf_url)
    except APIError as exc:
        raise ToolError(f"PDF download failed: {exc.message}") from exc
    return {
        "invoice_id": invoice_id,
        "size_bytes": len(pdf_bytes),
        "pdf_base64": base64.b64encode(pdf_bytes).decode("ascii"),
    }


@mcp.tool()
def get_invoice_ei_status(ctx: Context, invoice_id: int) -> dict[str, Any]:
    """Inspect an invoice's e-invoice / SDI transmission state. Read-only.

    Returns `ei_status` (one of: missing, not_sent, attempt, pending, sent,
    rejected, ...), the `e_invoice` flag, and the populated subset of
    `ei_data` (CodiceDestinatario etc.). Useful before attempting an update
    or to diagnose why an invoice didn't reach SDI.

    Note: Fatture in Cloud's REST API has no "send to SDI" endpoint —
    transmission is triggered server-side when the invoice is created with
    `e_invoice=true` and a valid recipient. This tool is diagnostic only.
    """
    client, company_id = _require(ctx)
    path = INVOICE_DETAIL.format(company_id=company_id, document_id=invoice_id)
    try:
        payload = client.get_resource(path, params={"type": "invoice"})
    except APIError as exc:
        raise ToolError(exc.message) from exc
    return summarize_ei_status(payload.get("data") or {})


@mcp.tool()
def update_client(
    ctx: Context,
    client_id: int,
    name: str | None = None,
    email: str | None = None,
    certified_email: str | None = None,
    phone: str | None = None,
    vat_number: str | None = None,
    tax_code: str | None = None,
    address_street: str | None = None,
    address_postal_code: str | None = None,
    address_city: str | None = None,
    address_province: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Update an existing client. Pass only the fields you want to change
    (delta mode); fields left as None stay untouched on the server.
    """
    client, company_id = _require(ctx)
    fields: dict[str, Any] = {
        k: v
        for k, v in {
            "name": name,
            "email": email,
            "certified_email": certified_email,
            "phone": phone,
            "vat_number": vat_number,
            "tax_code": tax_code,
            "address_street": address_street,
            "address_postal_code": address_postal_code,
            "address_city": address_city,
            "address_province": address_province,
            "notes": notes,
        }.items()
        if v is not None
    }
    if not fields:
        raise ToolError("update_client: at least one field must be specified")

    body = build_client_update_body(**fields)
    path = f"/c/{company_id}/entities/clients/{client_id}"
    try:
        payload = client.put_resource(path, json=body)
    except APIError as exc:
        raise ToolError(exc.message) from exc
    data = payload.get("data") or {}
    return {"id": data.get("id") or client_id, "updated_fields": list(fields)}


def main() -> None:
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    mcp.run()


if __name__ == "__main__":
    main()
