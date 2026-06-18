"""Stripe Checkout for the Allerion platform — stdlib only.

Creates Stripe Checkout Sessions for a pricing tier via Stripe's REST API
(no `stripe` package needed). Configure with environment variables:

    STRIPE_API_KEY        your Stripe secret key (sk_test_... / sk_live_...)
    PLATFORM_BASE_URL     public URL for success/cancel redirects
    STRIPE_PRICE_TEAM     (optional) an existing Stripe Price id for the Team tier

Without STRIPE_API_KEY the platform still runs; checkout links report that
billing isn't configured yet instead of erroring.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

STRIPE_API_KEY = os.environ.get("STRIPE_API_KEY", "").strip()
BASE_URL = os.environ.get("PLATFORM_BASE_URL", "http://127.0.0.1:8099").rstrip("/")

# Sellable tiers. If a tier has a Stripe price id (env), it's used directly;
# otherwise a price is created inline from `amount` (cents) / `interval`.
TIERS = {
    "team": {
        "label": "Allerion Team",
        "price_id": os.environ.get("STRIPE_PRICE_TEAM", "").strip(),
        "amount": 200000,        # $2,000.00 / month
        "interval": "month",
    },
}


def live() -> bool:
    return bool(STRIPE_API_KEY)


def _line_items(cfg: dict) -> list[tuple[str, str]]:
    if cfg["price_id"]:
        return [("line_items[0][price]", cfg["price_id"]), ("line_items[0][quantity]", "1")]
    return [
        ("line_items[0][price_data][currency]", "usd"),
        ("line_items[0][price_data][product_data][name]", cfg["label"]),
        ("line_items[0][price_data][unit_amount]", str(cfg["amount"])),
        ("line_items[0][price_data][recurring][interval]", cfg["interval"]),
        ("line_items[0][quantity]", "1"),
    ]


def create_checkout(tier: str, customer_email: str | None = None) -> dict:
    """Create a Stripe Checkout Session; returns the Stripe object (has `url`)."""
    cfg = TIERS.get(tier)
    if not cfg:
        raise ValueError(f"unknown tier: {tier}")
    if not live():
        raise RuntimeError("STRIPE_API_KEY is not set — billing isn't configured")

    params = [
        ("mode", "subscription"),
        ("success_url", f"{BASE_URL}/crm?checkout=success"),
        ("cancel_url", f"{BASE_URL}/#pricing"),
        ("allow_promotion_codes", "true"),
    ]
    if customer_email:
        params.append(("customer_email", customer_email))
    params += _line_items(cfg)

    req = urllib.request.Request(
        "https://api.stripe.com/v1/checkout/sessions",
        data=urllib.parse.urlencode(params).encode(),
        headers={
            "Authorization": f"Bearer {STRIPE_API_KEY}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        raise RuntimeError(f"Stripe error {e.code}: {detail}") from e
