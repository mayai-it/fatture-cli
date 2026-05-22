"""Pure data-transform helpers shared by the CLI and the MCP server.

These functions never perform I/O. They take raw API payloads and produce
the compact dict shapes used for human/JSON output, or build request bodies
to send back to Fatture in Cloud. Keeping them I/O-free makes them trivially
unit-testable and safe to reuse from any caller — CLI, MCP server, future
HTTP wrapper, scripts.
"""

from __future__ import annotations

from fatture_cli.transforms.client import (
    build_client_create_body,
    detail_client,
    summarize_client,
)
from fatture_cli.transforms.invoice import (
    build_invoice_create_body,
    build_invoice_query,
    build_invoice_update_body,
    detail_invoice,
    is_overdue,
    summarize_created_invoice,
    summarize_invoice,
)
from fatture_cli.transforms.payment import summarize_payment
from fatture_cli.transforms.product import summarize_product

__all__ = [
    "build_client_create_body",
    "build_invoice_create_body",
    "build_invoice_query",
    "build_invoice_update_body",
    "detail_client",
    "detail_invoice",
    "is_overdue",
    "summarize_client",
    "summarize_created_invoice",
    "summarize_invoice",
    "summarize_payment",
    "summarize_product",
]
