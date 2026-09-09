"""Stripe one-time checkout for digital products — stdlib only.

Creates Checkout Sessions in `payment` mode (not subscription) and verifies a
session was actually paid before we hand over a download. No `stripe` package.

Env:
    STRIPE_API_KEY     secret key (sk_test_… / sk_live_…)
    STORE_BASE_URL     public base URL for success/cancel redirects
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

import catalog

STRIPE_API_KEY = os.environ.get("STRIPE_API_KEY", "").strip()
BASE_URL = os.environ.get("STORE_BASE_URL", "http://127.0.0.1:8088").rstrip("/")
_API = "https://api.stripe.com/v1"


def live() -> bool:
    return bool(STRIPE_API_KEY)


def _request(method: str, path: str, params: list[tuple[str, str]] | None = None) -> dict:
    url = f"{_API}{path}"
    data = urllib.parse.urlencode(params).encode() if params else None
    req = urllib.request.Request(
        url, data=data,
        headers={"Authorization": f"Bearer {STRIPE_API_KEY}",
                 "Content-Type": "application/x-www-form-urlencoded"},
        method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        raise RuntimeError(f"Stripe {e.code}: {detail[:300]}") from e


def _line_items(slug: str, cfg: dict) -> list[tuple[str, str]]:
    pid = catalog.price_id(slug)
    if pid:
        return [("line_items[0][price]", pid), ("line_items[0][quantity]", "1")]
    return [
        ("line_items[0][price_data][currency]", "usd"),
        ("line_items[0][price_data][product_data][name]", cfg["name"]),
        ("line_items[0][price_data][product_data][description]", cfg["tagline"]),
        ("line_items[0][price_data][unit_amount]", str(cfg["price"])),
        ("line_items[0][quantity]", "1"),
    ]


def create_checkout(slug: str) -> dict:
    """Create a one-time Checkout Session for a product; returns Stripe object."""
    cfg = catalog.PRODUCTS.get(slug)
    if not cfg:
        raise ValueError(f"unknown product: {slug}")
    if not live():
        raise RuntimeError("STRIPE_API_KEY not set")
    params = [
        ("mode", "payment"),
        ("success_url", f"{BASE_URL}/success?session_id={{CHECKOUT_SESSION_ID}}"),
        ("cancel_url", f"{BASE_URL}/#catalog"),
        ("allow_promotion_codes", "true"),
        ("metadata[slug]", slug),
        ("payment_intent_data[metadata][slug]", slug),
    ]
    params += _line_items(slug, cfg)
    return _request("POST", "/checkout/sessions", params)


def retrieve_session(session_id: str) -> dict:
    """Fetch a Checkout Session to confirm payment + read buyer email/slug."""
    if not live():
        raise RuntimeError("STRIPE_API_KEY not set")
    safe = urllib.parse.quote(session_id, safe="")
    return _request("GET", f"/checkout/sessions/{safe}")
