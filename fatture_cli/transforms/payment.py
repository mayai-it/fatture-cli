"""Pure transforms for payment entries inside an invoice's `payments_list`."""

from __future__ import annotations

from typing import Any


def summarize_payment(p: dict[str, Any]) -> dict[str, Any]:
    """Compact payment shape used inside detail_invoice's `payments` list."""
    return {
        "due_date": p.get("due_date"),
        "amount": p.get("amount"),
        "status": p.get("status"),
        "paid_date": p.get("paid_date"),
        "payment_account": (p.get("payment_account") or {}).get("name"),
    }
