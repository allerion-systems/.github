#!/usr/bin/env python3
"""One-time Stripe setup for Allerion metered billing.

Creates a Billing Meter (sums per-customer usage) and a metered Price whose
per-unit amount encodes the markup. Run once:

    STRIPE_API_KEY=sk_test_... MARKUP_MULTIPLIER=2.0 python setup_stripe.py

The billing_sync worker only needs STRIPE_METER_EVENT_NAME to match the meter
created here — Stripe handles aggregation -> price -> invoice from there.
"""
import os
import stripe

stripe.api_key = os.environ["STRIPE_API_KEY"]
EVENT_NAME = os.environ.get("STRIPE_METER_EVENT_NAME", "allerion_api_usage")
MARKUP = float(os.environ.get("MARKUP_MULTIPLIER", "2.0"))

# Unit of usage = $1.00 of underlying provider cost. The price charges
# (MARKUP x 100) cents per unit, so the customer pays underlying_cost x MARKUP.
unit_amount_decimal = format(MARKUP * 100, "f")

meter = stripe.billing.Meter.create(
    display_name="Allerion API usage",
    event_name=EVENT_NAME,
    default_aggregation={"formula": "sum"},
    customer_mapping={"type": "by_id", "event_payload_key": "stripe_customer_id"},
    value_settings={"event_payload_key": "value"},
)
print(f"Meter created: {meter.id}  (event_name={EVENT_NAME})")

product = stripe.Product.create(name="Allerion API")
price = stripe.Price.create(
    currency="usd",
    unit_amount_decimal=unit_amount_decimal,
    billing_scheme="per_unit",
    recurring={"interval": "month", "usage_type": "metered", "meter": meter.id},
    product=product.id,
)
print(f"Price created:  {price.id}  ({MARKUP}x markup => {unit_amount_decimal} cents/unit)")
print()
print("Next:")
print("  1. Create a Stripe Customer per client and subscribe them to this price.")
print("  2. Mint a LiteLLM key with metadata.stripe_customer_id = that customer id.")
print("  3. Start billing:  docker compose --profile billing up -d")
