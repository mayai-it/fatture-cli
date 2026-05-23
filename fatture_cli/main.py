"""Entry point for the `fatture` CLI.

Top-level layout:

    fatture auth login   [--client-id ... --client-secret ...]
    fatture auth status
    fatture auth logout
    fatture list invoices | clients | products
    fatture get  invoice  | client  | product   <id>
    fatture create invoice --client <id> --file invoice.json
    fatture search clients <query>

Only `auth` is fully wired in this base scaffold; the resource commands are
registered as stubs so the surface area is reserved and discoverable via --help.
"""

from __future__ import annotations

import datetime as _dt
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, ParamSpec, TypeVar, cast

import click
import httpx

from fatture_cli import __version__
from fatture_cli.api import APIClient, APIError
from fatture_cli.api.endpoints import (
    CLIENT_DETAIL,
    CLIENTS_LIST,
    INVOICE_DETAIL,
    INVOICES_LIST,
    PRODUCT_DETAIL,
    PRODUCTS_LIST,
    USER_COMPANIES,
)
from fatture_cli.auth import (
    delete_credentials,
    load_credentials,
    perform_oauth_flow,
    save_credentials,
)
from fatture_cli.auth.oauth import DEFAULT_CALLBACK_PORT
from fatture_cli.output import emit, error
from fatture_cli.transforms.client import (
    build_client_create_body,
    build_client_update_body,
    detail_client,
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
from fatture_cli.transforms.product import summarize_product

# ---------------------------------------------------------------------------
# Shared CLI context
# ---------------------------------------------------------------------------


class CLIContext:
    """Carries flags shared across subcommands (set on the root group)."""

    def __init__(self, as_json: bool, verbose: bool) -> None:
        self.as_json = as_json
        self.verbose = verbose

    def require_client(self) -> APIClient:
        creds = load_credentials()
        if creds is None:
            error("not authenticated — run `fatture auth login` first")
            sys.exit(2)
        return APIClient(creds, verbose=self.verbose)


pass_ctx = click.make_pass_decorator(CLIContext)

P = ParamSpec("P")
R = TypeVar("R")


def common_flags(func: Callable[P, R]) -> Callable[P, R]:
    """Re-declare the root `--json` / `--verbose` flags on a subcommand.

    Click only consumes options at the level where they are declared, so
    `fatture list invoices --json` would otherwise fail with "No such option".
    We accept the flags here too and promote them onto the shared CLIContext
    so the position of `--json` no longer matters.

    The wrapper preserves the wrapped function's parameter spec; the two
    Click-injected extras ``_local_json`` / ``_local_verbose`` are pulled out
    of ``kwargs`` before delegating, so callers of the wrapped function still
    see the original signature.
    """
    import functools

    @click.option("--json", "_local_json", is_flag=True, default=False,
                  help="Output one JSON object per line (NDJSON).")
    @click.option("--verbose", "_local_verbose", is_flag=True, default=False,
                  help="Log HTTP requests and timings to stderr.")
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        local_json = bool(kwargs.pop("_local_json", False))
        local_verbose = bool(kwargs.pop("_local_verbose", False))
        cli_ctx = click.get_current_context().find_object(CLIContext)
        if cli_ctx is not None:
            if local_json:
                cli_ctx.as_json = True
            if local_verbose:
                cli_ctx.verbose = True
        return func(*args, **kwargs)

    return wrapper


# ---------------------------------------------------------------------------
# Root group
# ---------------------------------------------------------------------------


@click.group(
    context_settings={"help_option_names": ["-h", "--help"]},
    help="CLI for Fatture in Cloud — built for AI agents and developers.",
)
@click.version_option(__version__, prog_name="fatture")
@click.option("--json", "as_json", is_flag=True, help="Output one JSON object per line (NDJSON).")
@click.option("--verbose", is_flag=True, help="Log HTTP requests and timings to stderr.")
@click.pass_context
def cli(ctx: click.Context, as_json: bool, verbose: bool) -> None:
    ctx.obj = CLIContext(as_json=as_json, verbose=verbose)


# ---------------------------------------------------------------------------
# auth
# ---------------------------------------------------------------------------


@cli.group(help="Manage authentication with Fatture in Cloud.")
def auth() -> None: ...


@auth.command("login", help="Run the OAuth2 flow and save credentials.")
@click.option(
    "--client-id",
    required=True,
    help="OAuth client_id from developers.fattureincloud.it",
)
@click.option("--client-secret", required=True, help="OAuth client_secret.")
@click.option(
    "--no-browser",
    is_flag=True,
    help="Do not auto-open the browser (print the authorize URL instead).",
)
@click.option(
    "--port",
    type=int,
    default=DEFAULT_CALLBACK_PORT,
    help=f"Local callback port (default {DEFAULT_CALLBACK_PORT}; 0 = auto).",
)
@pass_ctx
def auth_login(
    ctx: CLIContext,
    client_id: str,
    client_secret: str,
    no_browser: bool,
    port: int,
) -> None:
    try:
        creds = perform_oauth_flow(
            client_id=client_id,
            client_secret=client_secret,
            open_browser=not no_browser,
            callback_port=port,
        )
    except (RuntimeError, TimeoutError, httpx.HTTPError) as exc:
        error(str(exc))
        sys.exit(1)

    # After token exchange, pick the first company by default so subsequent
    # calls have a usable company_id. Users with multiple companies can switch
    # with a future `auth use-company` command.
    try:
        with APIClient(creds, verbose=ctx.verbose) as client:
            companies = client.get_resource(USER_COMPANIES)
        first = (companies.get("data") or {}).get("companies") or []
        if first:
            creds.company_id = int(first[0]["id"])
    except APIError as exc:
        # Don't fail login if /user/companies hiccups — token is still valid.
        error(f"warning: could not fetch companies ({exc.message})")

    save_credentials(creds)

    summary: dict[str, Any] = {
        "status": "ok",
        "company_id": creds.company_id,
        "scopes": creds.scopes,
    }
    emit(summary, as_json=ctx.as_json)


@auth.command("status", help="Show whether credentials are present and valid.")
@pass_ctx
def auth_status(ctx: CLIContext) -> None:
    creds = load_credentials()
    if creds is None:
        emit({"authenticated": False}, as_json=ctx.as_json)
        sys.exit(2)

    info = {
        "authenticated": True,
        "company_id": creds.company_id,
        "expires_at": creds.expires_at,
        "expired": creds.is_expired,
        "scopes": creds.scopes,
    }
    emit(info, as_json=ctx.as_json)


@auth.command("logout", help="Delete saved credentials from disk.")
@pass_ctx
def auth_logout(ctx: CLIContext) -> None:
    removed = delete_credentials()
    emit({"removed": removed}, as_json=ctx.as_json)


# ---------------------------------------------------------------------------
# Resource groups (stubs — filled in by subsequent iterations)
# ---------------------------------------------------------------------------


@cli.group(name="list", help="List collections (invoices, clients, products).")
def list_() -> None: ...


@cli.group(help="Fetch a single resource by id.")
def get() -> None: ...


@cli.group(help="Create a new resource (invoice, client, product).")
def create() -> None: ...


@cli.group(help="Update an existing resource (invoice, client, product).")
def update() -> None: ...


@cli.group(help="Search resources by free-text query.")
def search() -> None: ...


@cli.group(help="Export resources in interchange formats (FatturaPA, …).")
def export() -> None: ...


@cli.group(help="Validate resources against external schemas.")
def validate() -> None: ...


@list_.command("invoices", help="List issued invoices for the active company.")
@click.option("--year", type=int, help="Filter by year of issue date.")
@click.option(
    "--status",
    help="Filter by status (e.g. paid, not_paid, partially_paid, expired).",
)
@click.option(
    "--overdue",
    is_flag=True,
    help="Only show unpaid invoices whose payment due date is in the past.",
)
@click.option("--limit", type=int, default=None, help="Stop after N invoices.")
@common_flags
@pass_ctx
def _list_invoices(
    ctx: CLIContext,
    year: int | None,
    status: str | None,
    overdue: bool,
    limit: int | None,
) -> None:
    with ctx.require_client() as client:
        company_id = client.credentials.company_id
        if not company_id:
            error("no active company — run `fatture auth login` again")
            sys.exit(2)

        path = INVOICES_LIST.format(company_id=company_id)
        params = build_invoice_query(year, status, overdue=overdue)
        today = _dt.date.today().isoformat()

        rows: list[dict] = []
        page = 1
        while True:
            params["page"] = str(page)
            try:
                payload = client.get_paginated(path, params=params)
            except APIError as exc:
                error(exc.message)
                sys.exit(1)

            for doc in payload.get("data") or []:
                if overdue:
                    if (doc.get("status") or "").lower() == "paid":
                        continue
                    if not is_overdue(doc, today):
                        continue
                rows.append(summarize_invoice(doc))
                if limit is not None and len(rows) >= limit:
                    break

            if limit is not None and len(rows) >= limit:
                break
            last_page = payload.get("last_page") or 1
            if page >= last_page:
                break
            page += 1

    emit(rows, as_json=ctx.as_json)


_CLIENT_FIELDS = "id,name,email,tax_code"


@list_.command("clients", help="List clients for the active company.")
@click.option("--limit", type=int, default=None, help="Stop after N clients.")
@common_flags
@pass_ctx
def _list_clients(ctx: CLIContext, limit: int | None) -> None:
    with ctx.require_client() as client:
        company_id = client.credentials.company_id
        if not company_id:
            error("no active company — run `fatture auth login` again")
            sys.exit(2)

        path = CLIENTS_LIST.format(company_id=company_id)
        params: dict[str, str] = {
            "fields": _CLIENT_FIELDS,
            "per_page": "100",
            "sort": "name",
        }

        rows: list[dict] = []
        page = 1
        while True:
            params["page"] = str(page)
            try:
                payload = client.get_paginated(path, params=params)
            except APIError as exc:
                error(exc.message)
                sys.exit(1)

            for doc in payload.get("data") or []:
                rows.append(summarize_client(doc))
                if limit is not None and len(rows) >= limit:
                    break

            if limit is not None and len(rows) >= limit:
                break
            last_page = payload.get("last_page") or 1
            if page >= last_page:
                break
            page += 1

    emit(rows, as_json=ctx.as_json)


_PRODUCT_FIELDS = "id,name,net_price,gross_price,vat,measure,description,code,category"


@list_.command("products", help="List products / services for the active company.")
@click.option("--limit", type=int, default=None, help="Stop after N products.")
@common_flags
@pass_ctx
def _list_products(ctx: CLIContext, limit: int | None) -> None:
    with ctx.require_client() as client:
        company_id = client.credentials.company_id
        if not company_id:
            error("no active company — run `fatture auth login` again")
            sys.exit(2)

        path = PRODUCTS_LIST.format(company_id=company_id)
        params: dict[str, str] = {
            "fields": _PRODUCT_FIELDS,
            "per_page": "100",
            "sort": "name",
        }

        rows: list[dict] = []
        page = 1
        while True:
            params["page"] = str(page)
            try:
                payload = client.get_paginated(path, params=params)
            except APIError as exc:
                error(exc.message)
                sys.exit(1)

            for doc in payload.get("data") or []:
                rows.append(summarize_product(doc))
                if limit is not None and len(rows) >= limit:
                    break

            if limit is not None and len(rows) >= limit:
                break
            last_page = payload.get("last_page") or 1
            if page >= last_page:
                break
            page += 1

    emit(rows, as_json=ctx.as_json)


@get.command("invoice", help="Fetch a single invoice by id.")
@click.argument("invoice_id", type=int)
@common_flags
@pass_ctx
def _get_invoice(ctx: CLIContext, invoice_id: int) -> None:
    with ctx.require_client() as client:
        company_id = client.credentials.company_id
        if not company_id:
            error("no active company — run `fatture auth login` again")
            sys.exit(2)

        path = INVOICE_DETAIL.format(company_id=company_id, document_id=invoice_id)
        try:
            payload = client.get_resource(path, params={"type": "invoice"})
        except APIError as exc:
            error(exc.message)
            sys.exit(1)

    data = payload.get("data") or {}
    emit(detail_invoice(data), as_json=ctx.as_json)


@get.command("client", help="Fetch a single client by id.")
@click.argument("client_id", type=int)
@common_flags
@pass_ctx
def _get_client(ctx: CLIContext, client_id: int) -> None:
    with ctx.require_client() as client:
        company_id = client.credentials.company_id
        if not company_id:
            error("no active company — run `fatture auth login` again")
            sys.exit(2)

        path = CLIENT_DETAIL.format(company_id=company_id, client_id=client_id)
        try:
            payload = client.get_resource(path)
        except APIError as exc:
            error(exc.message)
            sys.exit(1)

    data = payload.get("data") or {}
    emit(detail_client(data), as_json=ctx.as_json)


@get.command("product", help="Fetch a single product by id.")
@click.argument("product_id", type=int)
@common_flags
@pass_ctx
def _get_product(ctx: CLIContext, product_id: int) -> None:
    with ctx.require_client() as client:
        company_id = client.credentials.company_id
        if not company_id:
            error("no active company — run `fatture auth login` again")
            sys.exit(2)

        path = PRODUCT_DETAIL.format(company_id=company_id, product_id=product_id)
        try:
            payload = client.get_resource(path)
        except APIError as exc:
            error(exc.message)
            sys.exit(1)

    emit(payload.get("data") or {}, as_json=ctx.as_json)


@create.command("invoice", help="Create a new invoice from inline flags.")
@click.option("--client", "client_id", required=True, type=int, help="Client (entity) id.")
@click.option("--product", required=True, help="Product / service description line.")
@click.option("--amount", required=True, type=float, help="Net price for the single line.")
@click.option("--date", required=True, help="Issue date (YYYY-MM-DD).")
@common_flags
@pass_ctx
def _create_invoice(
    ctx: CLIContext,
    client_id: int,
    product: str,
    amount: float,
    date: str,
) -> None:
    body = build_invoice_create_body(client_id, product, amount, date)
    with ctx.require_client() as client:
        company_id = client.credentials.company_id
        if not company_id:
            error("no active company — run `fatture auth login` again")
            sys.exit(2)

        path = INVOICES_LIST.format(company_id=company_id)
        try:
            payload = client.post_resource(path, json=body)
        except APIError as exc:
            error(exc.message)
            sys.exit(1)

    emit(summarize_created_invoice(payload.get("data") or {}), as_json=ctx.as_json)


@create.command("client", help="Create a new client from inline flags.")
@click.option("--name", required=True, help="Display name of the client.")
@click.option("--email", help="Primary email address.")
@click.option("--vat", "vat", help="VAT number (partita IVA).")
@common_flags
@pass_ctx
def _create_client(
    ctx: CLIContext,
    name: str,
    email: str | None,
    vat: str | None,
) -> None:
    body = build_client_create_body(name, email, vat)
    with ctx.require_client() as client:
        company_id = client.credentials.company_id
        if not company_id:
            error("no active company — run `fatture auth login` again")
            sys.exit(2)

        path = CLIENTS_LIST.format(company_id=company_id)
        try:
            payload = client.post_resource(path, json=body)
        except APIError as exc:
            error(exc.message)
            sys.exit(1)

    data = payload.get("data") or {}
    emit({"id": data.get("id"), "name": data.get("name")}, as_json=ctx.as_json)


@update.command("invoice", help="Update an existing invoice (delta — only passed fields).")
@click.argument("invoice_id", type=int)
@click.option(
    "--status",
    type=click.Choice(["paid", "not_paid", "partially_paid"]),
    help="Payment status.",
)
@click.option("--date", help="Issue date (YYYY-MM-DD).")
@click.option("--number", type=int, help="Document number.")
@click.option("--notes", help="Internal notes (not visible on the PDF).")
@click.option("--visible-subject", help="Subject visible on the document.")
@common_flags
@pass_ctx
def _update_invoice(
    ctx: CLIContext,
    invoice_id: int,
    status: str | None,
    date: str | None,
    number: int | None,
    notes: str | None,
    visible_subject: str | None,
) -> None:
    fields: dict[str, Any] = {}
    if status is not None:
        fields["payment_status"] = status
    if date is not None:
        fields["date"] = date
    if number is not None:
        fields["number"] = number
    if notes is not None:
        fields["notes"] = notes
    if visible_subject is not None:
        fields["visible_subject"] = visible_subject

    if not fields:
        error("update invoice: at least one field option is required")
        sys.exit(1)

    body = build_invoice_update_body(**fields)
    with ctx.require_client() as client:
        company_id = client.credentials.company_id
        if not company_id:
            error("no active company — run `fatture auth login` again")
            sys.exit(2)

        path = INVOICE_DETAIL.format(company_id=company_id, document_id=invoice_id)
        try:
            payload = client.put_resource(path, json=body)
        except APIError as exc:
            _handle_update_error(exc)
            sys.exit(1)

    data = payload.get("data") or {}
    emit(
        {"id": data.get("id") or invoice_id, "updated_fields": list(fields)},
        as_json=ctx.as_json,
    )


def _handle_update_error(exc: APIError) -> None:
    """Surface a sharper message when a 4xx hints at SDI-sent immutability."""
    msg = exc.message or ""
    if exc.status_code in (400, 409, 422) and (
        "sent" in msg.lower() or "sdi" in msg.lower() or "e-invoice" in msg.lower()
    ):
        error(
            f"{msg}\n"
            "hint: invoices already transmitted to SDI cannot be modified. "
            "Issue a credit note (nota di credito, TipoDocumento TD04) instead.",
        )
    else:
        error(msg)


@search.command("clients", help="Search clients by free-text name match.")
@click.argument("query")
@click.option("--limit", type=int, default=None, help="Stop after N results.")
@common_flags
@pass_ctx
def _search_clients(ctx: CLIContext, query: str, limit: int | None) -> None:
    with ctx.require_client() as client:
        company_id = client.credentials.company_id
        if not company_id:
            error("no active company — run `fatture auth login` again")
            sys.exit(2)

        path = CLIENTS_LIST.format(company_id=company_id)
        # FiC's `q` accepts an expression language; `name LIKE` is the natural
        # fit for free-text name search and what the CLAUDE.md spec describes
        # (`fatture search clients "Rossi"`).
        # FiC's `q` accepts a SQL-like expression language; string literals must
        # be wrapped in single quotes (double quotes return 422 "Invalid query
        # syntax"). Strip single quotes from the user input rather than escape
        # them — the dialect has no documented escape sequence.
        escaped = query.replace("'", "")
        params: dict[str, str] = {
            "fields": _CLIENT_FIELDS,
            "per_page": "100",
            "sort": "name",
            "q": f"name LIKE '%{escaped}%'",
        }

        rows: list[dict] = []
        page = 1
        while True:
            params["page"] = str(page)
            try:
                payload = client.get_paginated(path, params=params)
            except APIError as exc:
                error(exc.message)
                sys.exit(1)

            for doc in payload.get("data") or []:
                rows.append(summarize_client(doc))
                if limit is not None and len(rows) >= limit:
                    break

            if limit is not None and len(rows) >= limit:
                break
            last_page = payload.get("last_page") or 1
            if page >= last_page:
                break
            page += 1

    emit(rows, as_json=ctx.as_json)


def _fetch_invoice_raw(client: APIClient, company_id: int, invoice_id: int) -> dict:
    """Return the raw `data` payload for an invoice — same shape FatturaPA needs."""
    path = INVOICE_DETAIL.format(company_id=company_id, document_id=invoice_id)
    payload = client.get_resource(path, params={"type": "invoice"})
    return payload.get("data") or {}


def _fetch_active_company(client: APIClient, company_id: int) -> dict[str, Any]:
    """Return the active company dict from /user/companies (matching company_id)."""
    payload = client.get_resource(USER_COMPANIES)
    companies = (payload.get("data") or {}).get("companies") or []
    for c in companies:
        if int(c.get("id") or 0) == company_id:
            return cast("dict[str, Any]", c)
    return cast("dict[str, Any]", companies[0]) if companies else {}


@export.command("invoice", help="Export an invoice as FatturaPA v1.2.3 XML.")
@click.argument("invoice_id", type=int)
@click.option(
    "--output",
    "-o",
    type=click.Path(dir_okay=False, writable=True),
    help="Write XML to FILE (default: stdout). Use IT{vat}_{id}.xml convention.",
)
@common_flags
@pass_ctx
def _export_invoice(ctx: CLIContext, invoice_id: int, output: str | None) -> None:
    from fatture_cli.fatturapa import build_fattura_xml

    with ctx.require_client() as client:
        company_id = client.credentials.company_id
        if not company_id:
            error("no active company — run `fatture auth login` again")
            sys.exit(2)

        try:
            invoice = _fetch_invoice_raw(client, company_id, invoice_id)
            company = _fetch_active_company(client, company_id)
        except APIError as exc:
            error(exc.message)
            sys.exit(1)

    xml = build_fattura_xml(invoice, company)

    if output:
        Path(output).write_text(xml, encoding="utf-8")
        emit({"file": output, "bytes": len(xml.encode("utf-8"))}, as_json=ctx.as_json)
    else:
        # The XML already starts with `<?xml ... ?>` — write raw, no extra newline.
        sys.stdout.write(xml)


@validate.command("invoice", help="Validate an invoice's FatturaPA XML against the XSD.")
@click.argument("invoice_id", type=int)
@common_flags
@pass_ctx
def _validate_invoice(ctx: CLIContext, invoice_id: int) -> None:
    from fatture_cli.fatturapa import build_fattura_xml, validate_fattura_xml

    with ctx.require_client() as client:
        company_id = client.credentials.company_id
        if not company_id:
            error("no active company — run `fatture auth login` again")
            sys.exit(2)

        try:
            invoice = _fetch_invoice_raw(client, company_id, invoice_id)
            company = _fetch_active_company(client, company_id)
        except APIError as exc:
            error(exc.message)
            sys.exit(1)

    xml = build_fattura_xml(invoice, company)
    errors = validate_fattura_xml(xml)

    if not errors:
        emit({"valid": True}, as_json=ctx.as_json)
        return

    emit({"valid": False, "errors": errors}, as_json=ctx.as_json)
    sys.exit(1)


# ---------------------------------------------------------------------------
# update client
# ---------------------------------------------------------------------------


@update.command("client", help="Update an existing client (delta — only passed fields).")
@click.argument("client_id", type=int)
@click.option("--name", help="Client display name.")
@click.option("--email", help="Primary email.")
@click.option("--certified-email", help="Certified email (PEC).")
@click.option("--phone", help="Phone number.")
@click.option("--vat-number", help="VAT number (e.g. IT01234567890).")
@click.option("--tax-code", help="Codice fiscale.")
@click.option("--address-street", help="Street address.")
@click.option("--address-postal-code", help="Postal code (CAP).")
@click.option("--address-city", help="City.")
@click.option("--address-province", help="Province code (e.g. RM, MI).")
@click.option("--notes", help="Internal notes.")
@common_flags
@pass_ctx
def _update_client(
    ctx: CLIContext,
    client_id: int,
    name: str | None,
    email: str | None,
    certified_email: str | None,
    phone: str | None,
    vat_number: str | None,
    tax_code: str | None,
    address_street: str | None,
    address_postal_code: str | None,
    address_city: str | None,
    address_province: str | None,
    notes: str | None,
) -> None:
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
        error("update client: at least one field option is required")
        sys.exit(1)

    body = build_client_update_body(**fields)
    with ctx.require_client() as client:
        company_id = client.credentials.company_id
        if not company_id:
            error("no active company — run `fatture auth login` again")
            sys.exit(2)

        path = CLIENT_DETAIL.format(company_id=company_id, client_id=client_id)
        try:
            payload = client.put_resource(path, json=body)
        except APIError as exc:
            error(exc.message)
            sys.exit(1)

    data = payload.get("data") or {}
    emit(
        {"id": data.get("id") or client_id, "updated_fields": list(fields)},
        as_json=ctx.as_json,
    )


# ---------------------------------------------------------------------------
# mark-paid invoice
# ---------------------------------------------------------------------------


@cli.group(name="mark-paid", help="Shortcut: mark a resource as paid.")
def mark_paid() -> None: ...


@mark_paid.command("invoice", help="Mark an invoice as paid (sets payment_status=paid).")
@click.argument("invoice_id", type=int)
@click.option(
    "--date",
    "paid_date",
    help="Date of payment (YYYY-MM-DD). Defaults to today. Note: this updates "
    "the document-level payment_status only and does not record an actual "
    "cash/bank movement.",
)
@common_flags
@pass_ctx
def _mark_paid_invoice(
    ctx: CLIContext, invoice_id: int, paid_date: str | None
) -> None:
    effective_date = paid_date or _dt.date.today().isoformat()
    body = build_mark_paid_body(paid_date=effective_date)

    with ctx.require_client() as client:
        company_id = client.credentials.company_id
        if not company_id:
            error("no active company — run `fatture auth login` again")
            sys.exit(2)

        path = INVOICE_DETAIL.format(company_id=company_id, document_id=invoice_id)
        try:
            payload = client.put_resource(path, json=body)
        except APIError as exc:
            _handle_update_error(exc)
            sys.exit(1)

    data = payload.get("data") or {}
    emit(
        {"id": data.get("id") or invoice_id, "payment_status": "paid", "paid_date": effective_date},
        as_json=ctx.as_json,
    )


# ---------------------------------------------------------------------------
# send invoice (email)
# ---------------------------------------------------------------------------


@cli.group(help="Send a resource (email, etc.).")
def send() -> None: ...


@send.command("invoice", help="Email an invoice to a recipient.")
@click.argument("invoice_id", type=int)
@click.option("--to", "to_email", required=True, help="Recipient email.")
@click.option(
    "--from",
    "from_email",
    help="Sender email. If omitted, FiC uses the company default sender.",
)
@click.option("--subject", help="Custom subject (otherwise FiC default).")
@click.option("--body", "body_text", help="Custom body text.")
@click.option(
    "--attach-pdf/--no-attach-pdf",
    default=True,
    help="Attach the invoice PDF to the email (default: yes).",
)
@common_flags
@pass_ctx
def _send_invoice_email(
    ctx: CLIContext,
    invoice_id: int,
    to_email: str,
    from_email: str | None,
    subject: str | None,
    body_text: str | None,
    attach_pdf: bool,
) -> None:
    body = build_send_invoice_email_body(
        recipient_email=to_email,
        sender_email=from_email,
        subject=subject,
        body=body_text,
        attach_pdf=attach_pdf,
    )

    with ctx.require_client() as client:
        company_id = client.credentials.company_id
        if not company_id:
            error("no active company — run `fatture auth login` again")
            sys.exit(2)

        path = f"/c/{company_id}/issued_documents/{invoice_id}/email"
        try:
            payload = client.post_resource(path, json=body)
        except APIError as exc:
            error(exc.message)
            sys.exit(1)

    data = payload.get("data") or {}
    emit(
        {
            "scheduled": True,
            "invoice_id": invoice_id,
            "recipient": to_email,
            "response": data or None,
        },
        as_json=ctx.as_json,
    )


# ---------------------------------------------------------------------------
# ei-status invoice (diagnostic — no transmission)
# ---------------------------------------------------------------------------


@cli.group(name="ei-status", help="Diagnose e-invoice / SDI transmission status.")
def ei_status() -> None: ...


@ei_status.command("invoice", help="Inspect an invoice's SDI transmission state.")
@click.argument("invoice_id", type=int)
@common_flags
@pass_ctx
def _ei_status_invoice(ctx: CLIContext, invoice_id: int) -> None:
    with ctx.require_client() as client:
        company_id = client.credentials.company_id
        if not company_id:
            error("no active company — run `fatture auth login` again")
            sys.exit(2)

        path = INVOICE_DETAIL.format(company_id=company_id, document_id=invoice_id)
        try:
            payload = client.get_resource(path, params={"type": "invoice"})
        except APIError as exc:
            error(exc.message)
            sys.exit(1)

    emit(summarize_ei_status(payload.get("data") or {}), as_json=ctx.as_json)


# ---------------------------------------------------------------------------
# export-pdf invoice
# ---------------------------------------------------------------------------


@cli.group(name="export-pdf", help="Download a resource as PDF.")
def export_pdf() -> None: ...


@export_pdf.command("invoice", help="Download an invoice PDF to a local file.")
@click.argument("invoice_id", type=int)
@click.option(
    "--output",
    "output_path",
    help="Output file path. Defaults to invoice_<id>.pdf in the current directory.",
)
@common_flags
@pass_ctx
def _export_pdf_invoice(
    ctx: CLIContext, invoice_id: int, output_path: str | None
) -> None:
    with ctx.require_client() as client:
        company_id = client.credentials.company_id
        if not company_id:
            error("no active company — run `fatture auth login` again")
            sys.exit(2)

        path = INVOICE_DETAIL.format(company_id=company_id, document_id=invoice_id)
        try:
            payload = client.get_resource(path, params={"type": "invoice"})
        except APIError as exc:
            error(exc.message)
            sys.exit(1)

        invoice_data = payload.get("data") or {}
        pdf_url = invoice_data.get("url")
        if not pdf_url:
            error(
                "invoice has no downloadable PDF "
                "(the API response did not include a 'url' field)"
            )
            sys.exit(1)

        try:
            pdf_bytes = client.get_binary_url(pdf_url)
        except APIError as exc:
            error(f"PDF download failed: {exc.message}")
            sys.exit(1)

    target = output_path or f"invoice_{invoice_id}.pdf"
    Path(target).write_bytes(pdf_bytes)
    emit({"saved": target, "size_bytes": len(pdf_bytes)}, as_json=ctx.as_json)


if __name__ == "__main__":
    cli()
