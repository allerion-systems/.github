#!/usr/bin/env python3
"""Allerion Agent Market — 80-agent fleet on the gateway connector.

Spins up 80 agents (30 merchants + 50 buyers), embeds a gateway Connector into
each one, runs the A2A market, and fulfils every closed deal through the
merchant's connector. Demonstrates "the connector embedded into 80 agents":
all 80 route work through the shared Allerion gateway (live with a key, stub
without).

    python3 run_fleet.py
    LLM_BASE_URL=https://openrouter.ai/api LLM_API_KEY=sk-or-... \
        LLM_MODEL=openai/gpt-4o-mini python3 run_fleet.py
"""
from __future__ import annotations

import random

from agentmarket import connector, llm
from agentmarket.agents import BuyerAgent, MerchantAgent
from agentmarket.ledger import Ledger
from agentmarket.market import Market
from agentmarket.marketplace import Marketplace
from agentmarket.protocol import Need, Service

N_MERCHANTS = 30
N_BUYERS = 50
ROUNDS = 4
SEED = 11

CAPS = ["summarize", "translate", "enrich", "copywrite", "classify", "extract"]
PROMPTS = {
    "summarize": "summarize this quarter's field report",
    "translate": "translate the spec sheet to German",
    "enrich": "enrich 200 supplier records with firmographics",
    "copywrite": "write launch copy for the new module",
    "classify": "classify these 500 support tickets",
    "extract": "extract line items from these invoices",
}


def build_fleet():
    rng = random.Random(SEED)
    mp = Marketplace()
    merchants = []
    for i in range(N_MERCHANTS):
        m = MerchantAgent(f"m{i:02d}", f"Vendor-{i:02d}", concession=rng.uniform(0.3, 0.55))
        # each merchant offers 1-2 capabilities
        for cap in rng.sample(CAPS, k=rng.randint(1, 2)):
            base = rng.uniform(6, 22)
            m.offer(Service(
                id=f"{m.id}-{cap}", name=f"{cap} by {m.name}", capability=cap,
                merchant_id=m.id, list_price=round(base, 2),
                floor_price=round(base * rng.uniform(0.5, 0.7), 2),
                quality=round(rng.uniform(0.55, 0.97), 2),
                capacity_per_round=rng.randint(2, 6),
            ))
        mp.register(m)
        merchants.append(m)

    ledger = Ledger(house_id="allerion", fee_rate=0.10)
    market = Market(marketplace=mp, ledger=ledger)
    buyers = []
    for i in range(N_BUYERS):
        b = BuyerAgent(f"b{i:02d}", f"Buyer-{i:02d}",
                       quality_weight=rng.uniform(0.2, 0.8), concession=rng.uniform(0.3, 0.5))
        b.needs = [
            Need(f"{b.id}-n{r}", b.id, (cap := rng.choice(CAPS)),
                 value=round(rng.uniform(8, 26), 2), prompt=PROMPTS[cap])
            for r in range(ROUNDS)
        ]
        market.add_buyer(b, opening_balance=round(rng.uniform(120, 320), 2))
        buyers.append(b)

    # Embed the gateway connector into every agent — this is the "80 agents".
    wired = connector.attach(merchants) + connector.attach(buyers)
    return market, merchants, buyers, wired


def main() -> None:
    random.seed(SEED)
    market, merchants, buyers, wired = build_fleet()

    print()
    print("=" * 70)
    print("  ALLERION FLEET — agent-to-agent commerce on the gateway connector")
    print(f"  agents wired to connector: {wired}  ({len(merchants)} merchants + {len(buyers)} buyers)")
    print(f"  gateway: {'LIVE via ' + llm.MODEL if llm.live() else 'deterministic stub (no key)'}")
    print("=" * 70)

    # Run the market WITHOUT auto-fulfil; we fulfil via each merchant's connector.
    market.run(ROUNDS, fulfill=False)
    deals = market.all_deals()

    # Fulfil each closed deal through the selling merchant's embedded connector.
    by_id = {m.id: m for m in merchants}
    for d in deals:
        conn = by_id[d.merchant_id].connector
        d.delivered = conn.fulfill(d.capability, PROMPTS.get(d.capability, d.capability))

    s = market.summary()
    active = sum(1 for m in merchants if m.connector.calls) + \
        sum(1 for b in buyers if b.purchases)
    total_calls = sum(m.connector.calls for m in merchants)

    print(f"\n  rounds: {ROUNDS}   deals: {s['deals']}   GMV: ${s['gmv']:.2f}")
    print(f"  platform revenue: ${s['platform_revenue']:.2f} (10% of GMV)")
    print(f"  connector calls through gateway: {total_calls}")
    print(f"  agents that transacted: {active}/{wired}")
    print(f"  money conserved: ${s['money_conserved']:.2f}")

    print("\n  Top 5 merchants by gateway calls:")
    for m in sorted(merchants, key=lambda x: -x.connector.calls)[:5]:
        print(f"   {m.id} {m.name:<11} {m.connector.status():<22} calls={m.connector.calls} sales={m.sales}")

    if deals and deals[0].delivered:
        print("\n  Sample delivered work (via connector):")
        print("   " + deals[0].delivered[:160])
    print()


if __name__ == "__main__":
    main()
