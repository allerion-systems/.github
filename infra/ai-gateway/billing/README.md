# Metered billing (Stripe)

Turns gateway usage into invoices. LiteLLM already records the underlying USD
cost of every request per virtual key; this worker maps each key to a Stripe
customer and reports usage to a **Stripe Billing Meter**. The **markup lives in
the Stripe price**, so a customer's bill = `underlying_cost x markup` — correct
across every model with no per-model price tables to maintain.

```
LiteLLM_SpendLogs ──> billing_sync ──> Stripe Meter Event ──> Price (markup) ──> Invoice
        (usage)        (this worker)        (value = $ cost)      (x multiplier)
```

## How a request becomes revenue
1. You create a **Stripe Customer** for a client and subscribe them to the metered price.
2. You **mint a LiteLLM key** for that client with `metadata.stripe_customer_id` set.
3. Every request that key makes is logged by LiteLLM with its USD cost.
4. `billing_sync` emits a meter event (`value` = that cost, `identifier` = request id) to Stripe.
5. Stripe aggregates and invoices automatically at the markup price.

## One-time setup

```bash
cd infra/ai-gateway/billing
pip install -r requirements.txt
STRIPE_API_KEY=sk_test_... MARKUP_MULTIPLIER=2.0 python setup_stripe.py
# prints the Meter id + Price id
```

Set `STRIPE_API_KEY` (and optionally `MARKUP_MULTIPLIER`) in `../.env`, then:

```bash
cd ..
docker compose --profile billing up -d
docker compose logs -f billing
```

## Onboard a paying customer

```bash
# 1. Stripe customer
stripe customers create --email="dev@acme.com"          # -> cus_XXX
# 2. Subscribe them to the metered price from setup_stripe.py
stripe subscriptions create --customer=cus_XXX \
  -d "items[0][price]=price_XXX"
# 3. Mint a scoped LiteLLM key tied to that customer
curl https://api.allerion.io/key/generate \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
        "models": ["deepseek-r1", "llama-3.3-70b"],
        "rpm_limit": 120,
        "metadata": {"stripe_customer_id": "cus_XXX"}
      }'
```

Hand the returned `sk-...` key to the customer. Usage now bills automatically.

## Design notes
- **Idempotent:** each meter event uses LiteLLM's `request_id` as its Stripe
  identifier, so retries after a crash never double-bill.
- **No silent leakage:** usage from a key with no `stripe_customer_id` is written
  to a `billing_unmapped` table for reconciliation instead of being dropped.
- **Watermark:** a `(startTime, request_id)` cursor in `billing_state` tracks
  progress exactly, with no gaps or overlaps across restarts.
- **Schema drift:** all LiteLLM table/column names are isolated in
  `fetch_rows()` in `billing_sync.py` — adjust there if your LiteLLM version
  differs.

## Reconcile unmapped usage
```sql
SELECT api_key, count(*), sum(spend) FROM billing_unmapped GROUP BY api_key;
```
Attach a `stripe_customer_id` to those keys to bill them going forward.
