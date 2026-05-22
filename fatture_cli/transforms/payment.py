"""Pure transforms for payment entries inside an invoice's ``payments_list``."""

from __future__ import annotations

from typing import Any

from fatture_cli.models.invoice import InvoicePayment


def summarize_payment(p: dict[str, Any] | InvoicePayment) -> dict[str, Any]:
    """Compact payment shape used inside detail_invoice's ``payments`` list.

    Accepts either a raw dict or an already-parsed ``InvoicePayment``. When a
    dict is passed it is validated through the model, which coerces ``amount``
    from string to ``Decimal`` and ``due_date`` / ``paid_date`` to ``date``.
    """
    payment = p if isinstance(p, InvoicePayment) else InvoicePayment.model_validate(p)
    account = payment.payment_account or {}
    return {
        "due_date": payment.due_date.isoformat() if payment.due_date else None,
        "amount": payment.amount,
        "status": payment.status,
        "paid_date": payment.paid_date.isoformat() if payment.paid_date else None,
        "payment_account": account.get("name"),
    }
