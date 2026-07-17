"""Small order analytics helper used by the AI-review test PR."""


def average_order_value(values: list[float]) -> float:
    """Return the arithmetic mean for collected order values."""
    return sum(values) / len(values)
