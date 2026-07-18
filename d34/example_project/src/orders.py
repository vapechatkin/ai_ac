"""Order checkout orchestration."""

from src.payments import PaymentAPI


def checkout(order_id: str, amount: int, payments: PaymentAPI) -> str:
    """Charge an order and return the provider reference."""
    return payments.charge(order_id, amount)
