# Payment API

`PaymentAPI.charge(order_id, amount)` charges a positive integer amount and returns
a provider reference prefixed with `payment:`.

## Consumers

- `src/orders.py` uses the API during checkout.
- `src/refunds.py` uses its type in the refund workflow.
