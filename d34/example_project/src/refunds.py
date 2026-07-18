"""Refund workflow shares the payment client type."""

from src.payments import PaymentAPI


def can_refund(payments: PaymentAPI, payment_id: str) -> bool:
    return bool(payments and payment_id.startswith("payment:"))
