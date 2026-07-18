"""Public payment API used by the order workflow."""


class PaymentAPI:
    def charge(self, order_id: str, amount: int) -> str:
        if amount <= 0:
            raise ValueError("amount must be positive")
        return f"payment:{order_id}"
