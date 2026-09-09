#!/usr/bin/env python3
"""Allerion Agent Market — runnable demo.

Seeds a small economy of merchant and buyer agents, runs several trading
rounds, and prints the negotiation transcript, the settlement ledger, and the
platform's take. Runs with no API key (deterministic fulfilment); set
LLM_BASE_URL + LLM_API_KEY to fulfil purchased work with a real model.

    python run_demo.py            # offline, deterministic
    LLM_BASE_URL=https://api.allerion.io LLM_API_KEY=sk-... python run_demo.py
"""
from __future__ import annotations

import random

from agentmarket import llm
from agentmarket.agents import BuyerAgent, MerchantAgent
from agentmarket.ledger import Ledger
from agentmarket.market import Market
from agentmarket.marketplace import Marketplace
from agentmarket.protocol import Need, Service

ROUNDS = 5
SEED = 7


def build_marketplace() -> Marketplace:
    mp = Marketplace()
    scribe = MerchantAgent("scribe", "Scribe.ai", concession=0.35)
    scribe.offer(Service("scribe-sum", "Premium Summaries", "summarize", "scribe", 10, 6, 0.90, 3))
    scribe.offer(Service("scribe-copy", "Brand Copy", "copywrite", "scribe", 14, 9, 0.85, 2))

    lingua = MerchantAgent("lingua", "Lingua.ai", concession=0.5)
    lingua.offer(Service("lingua-tr", "Fast Translate", "translate", "lingua", 8, 5, 0.80, 4))
    lingua.offer(Service("lingua-sum", "Budget Summaries", "summarize", "lingua", 7, 4, 0.60, 3))

    forge = MerchantAgent("forge", "DataForge", concession=0.3)
    forge.offer(Service("forge-en", "Deep Enrichment", "enrich", "forge", 20, 12, 0.95, 2))
    forge.offer(Service("forge-tr", "Technical Translate", "translate", "forge", 9, 6, 0.70, 2))

    quill = MerchantAgent("quill", "Quill", concession=0.45)
    quill.offer(Service("quill-copy", "Value Copy", "copywrite", "quill", 11, 7, 0.70, 3))
    quill.offer(Service("quill-sum", "Standard Summaries", "summarize", "quill", 9, 5, 0.75, 2))

    for m in (scribe, lingua, forge, quill):
        mp.register(m)
    return mp


def needs_for(buyer_id: str, templates, rounds: int):
    out = []
    for r in range(rounds):
        cap, value, prompt = templates[r % len(templates)]
        out.append(Need(f"{buyer_id}-n{r}", buyer_id, cap, value, prompt))
    return out


def build_market() -> Market:
    mp = build_marketplace()
    ledger = Ledger(house_id="allerion", fee_rate=0.10)
    market = Market(marketplace=mp, ledger=ledger)

    atlas = BuyerAgent("atlas", "Atlas Corp", quality_weight=0.7, concession=0.4)
    atlas.needs = needs_for("atlas", [
        ("enrich", 25, "enrich 500 B2B leads with firmographics"),
        ("summarize", 12, "summarize the Q2 earnings call"),
        ("copywrite", 16, "write a launch announcement for our API"),
    ], ROUNDS)

    nimbus = BuyerAgent("nimbus", "Nimbus Labs", quality_weight=0.3, concession=0.45)
    nimbus.needs = needs_for("nimbus", [
        ("summarize", 10, "tl;dr this support thread"),
        ("translate", 9, "translate docs to Spanish"),
    ], ROUNDS)

    orbit = BuyerAgent("orbit", "Orbit Retail", quality_weight=0.5, concession=0.4)
    orbit.needs = needs_for("orbit", [
        ("translate", 10, "translate product listings to German"),
        ("copywrite", 15, "write 20 product descriptions"),
        ("enrich", 22, "enrich our customer table with industry codes"),
    ], ROUNDS)

    market.add_buyer(atlas, opening_balance=200.0)
    market.add_buyer(nimbus, opening_balance=120.0)
    market.add_buyer(orbit, opening_balance=150.0)
    return market


def hr(char="─", n=72):
    print(char * n)


def main() -> None:
    random.seed(SEED)
    market = build_market()

    print()
    hr("═")
    print("  ALLERION AGENT MARKET — agent-to-agent commerce")
    print(f"  fulfilment: {'LIVE via ' + llm.MODEL if llm.live() else 'deterministic stub (no API key)'}")
    print(f"  platform commission: {market.ledger.fee_rate:.0%}   rounds: {ROUNDS}")
    hr("═")

    reports = market.run(ROUNDS, fulfill=True)

    print("\n  Sample negotiation transcript (round 1):")
    hr()
    for msg in reports[0].transcript[:14]:
        print("   " + msg.render())
    hr()

    print("\n  Per-round activity:")
    for rep in reports:
        gmv = sum(d.price for d in rep.deals)
        print(f"   round {rep.round}: {len(rep.deals)} deals  ·  ${gmv:6.2f} GMV  ·  {rep.no_deals} unmatched")

    print("\n  Closed deals:")
    hr()
    for d in market.all_deals():
        print(f"   r{d.round}  {d.buyer_id:>7} → {d.merchant_id:<7} {d.capability:<10} "
              f"${d.price:6.2f}  (fee ${d.fee:.2f}, {d.rounds_negotiated} rounds)")
    hr()

    print("\n  Final balances (wallets):")
    for aid, bal in sorted(market.ledger.balances.items(), key=lambda kv: -kv[1]):
        if aid == "__mint__":
            continue
        tag = "  ← platform" if aid == market.ledger.house_id else ""
        print(f"   {aid:>10}: ${bal:8.2f}{tag}")

    s = market.summary()
    print("\n  Summary:")
    hr()
    print(f"   deals closed     : {s['deals']}")
    print(f"   GMV              : ${s['gmv']:.2f}")
    print(f"   platform revenue : ${s['platform_revenue']:.2f}  ({market.ledger.fee_rate:.0%} of GMV)")
    print(f"   avg deal price   : ${s['avg_price']:.2f}")
    print(f"   money conserved  : ${s['money_conserved']:.2f}  (sum of all wallets incl. mint == 0.00)")
    hr()

    if market.all_deals() and market.all_deals()[0].delivered:
        print("\n  Sample delivered work product:")
        print("   " + market.all_deals()[0].delivered)
    print()


if __name__ == "__main__":
    main()
