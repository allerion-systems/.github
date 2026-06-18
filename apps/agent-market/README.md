# Allerion Agent Market

A functional **agent-to-agent (A2A) commerce** simulation: AI **merchant agents**
sell services (summarize, translate, enrich, copywrite) to AI **buyer agents**.
Buyers discover suppliers, **negotiate price** through alternating offers,
transact through a **settlement ledger**, and the platform takes a **commission
on every deal** — that's the revenue model.

It runs with **zero dependencies and no API key** (deterministic fulfilment).
Point it at any **OpenAI-compatible endpoint** — the Allerion gateway, OpenRouter,
NVIDIA, OpenAI — to fulfil purchased work with a real model.

## Run it

```bash
cd apps/agent-market

# Offline, deterministic — no key needed:
python run_demo.py

# Live fulfilment via a real model (example: OpenRouter):
LLM_BASE_URL=https://openrouter.ai/api \
LLM_API_KEY=sk-or-... \
LLM_MODEL=openai/gpt-4o-mini \
python run_demo.py

# Live via the Allerion gateway (PR #2):
LLM_BASE_URL=https://api.allerion.io LLM_API_KEY=sk-... LLM_MODEL=deepseek-r1 python run_demo.py
```

## Tests

```bash
pip install pytest
pytest -q
```

## How it works

```
buyer.need ─discover→ marketplace ─quotes→ negotiate (alternating offers)
                                              │  deal price within [floor, value]
                                              ▼
                                          ledger.settle  ──fee──> platform wallet
                                              │ net
                                              ▼
                                          merchant wallet ;  llm.fulfill() delivers work
```

| Module | Responsibility |
|--------|----------------|
| `protocol.py` | `Service`, `Need`, `Deal`, A2A `Message` types |
| `agents.py` | `MerchantAgent` (quoting, concession) and `BuyerAgent` (ranking, bidding) |
| `marketplace.py` | registry, capability discovery, the negotiation engine |
| `ledger.py` | wallets, settlement, platform commission, money-conservation invariant |
| `llm.py` | service fulfilment — real model or deterministic stub |
| `market.py` | the round loop + analytics (GMV, revenue, P&L) |
| `run_demo.py` | seeds an economy and prints transcript + ledger |

## Economic model
- Each service has a `list_price` (opening ask) and a `floor_price` (walk-away).
- Each buyer need has a `value` (max willingness to pay).
- A deal closes only when the bargaining range overlaps (`floor ≤ value`), at a
  price in between — so margins and outcomes vary by agent strategy.
- **Money is conserved**: every settlement moves funds buyer → merchant + a
  commission to the platform. `summary()["money_conserved"]` must stay `0.00`
  (opening balances are funded from a mint account that nets out).

## Going further
- Swap deterministic agent policies for **LLM-driven negotiation** (have each
  agent reason about its next offer via `llm.fulfill`).
- Wire settlement to the **Stripe metered billing** in `infra/ai-gateway/billing`
  so agent spend becomes real invoices.
- Expose the marketplace over HTTP so external agents can register and trade.
