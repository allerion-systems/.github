#!/usr/bin/env python3
"""One-time helper: create Stripe Products + one-time Prices for the catalog.

Run once with your Stripe secret key to mint a Price for each catalog item, then
export the printed STRIPE_PRICE_* env vars so the store uses stable price ids
(instead of inline price_data). Idempotency is on you — running twice creates
duplicate prices in Stripe.

    STRIPE_API_KEY=sk_test_... python3 setup_stripe.py

Stdlib only.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

import catalog

KEY = os.environ.get("STRIPE_API_KEY", "").strip()
API = "https://api.stripe.com/v1"


def _post(path: str, params: list[tuple[str, str]]) -> dict:
    req = urllib.request.Request(
        f"{API}{path}", data=urllib.parse.urlencode(params).encode(),
        headers={"Authorization": f"Bearer {KEY}",
                 "Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def main() -> int:
    if not KEY:
        print("Set STRIPE_API_KEY first.")
        return 1
    print("Creating Stripe products + prices...\n")
    print("# Export these so the store uses stable Price ids:")
    for slug, p in catalog.PRODUCTS.items():
        product = _post("/products", [("name", p["name"]),
                                      ("description", p["tagline"])])
        price = _post("/prices", [
            ("product", product["id"]),
            ("unit_amount", str(p["price"])),
            ("currency", "usd"),
        ])
        print(f'export {p["price_env"]}={price["id"]}    # {p["name"]} {catalog.usd(p["price"])}')
    print("\nDone. Add the exports to your environment and restart the store.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
