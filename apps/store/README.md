# Allerion Skills Store

A zero-dependency storefront (Python standard library only) that **sells digital
developer products** — Claude Agent Skills and a Codex MCP plugin — through
Stripe one-time checkout, with instant, license-gated download delivery.

```bash
cd apps/store
python3 server.py            # http://127.0.0.1:8088
```

No `pip install` — it uses only `http.server`, `sqlite3`, `zipfile`, and `urllib`.

## What it sells

| Product | Kind | Price |
|---------|------|-------|
| **PR Review Pro** | Claude Skill | $49 |
| **Changelog Craft** | Claude Skill | $29 |
| **Test Forge** | Claude Skill | $39 |
| **Allerion DevKit for Codex** | Codex plugin (MCP) | $79 |
| **DevKit Complete Bundle** | All four | $149 |

The products are real and live under `products/`:

- `products/claude-skills/*` — each a Claude Agent Skill (a `SKILL.md` plus
  helper scripts). Drop the folder into `~/.claude/skills/`.
- `products/codex-devkit/` — an MCP server (`server.py`) that adds `review_diff`,
  `draft_changelog`, and `scaffold_tests` to OpenAI Codex. Verify it with
  `python3 products/codex-devkit/server.py --selftest`.

## How a sale works

1. Buyer clicks **Buy** → `GET /buy/<slug>` creates a Stripe Checkout Session
   (`mode=payment`) and redirects to Stripe.
2. Stripe sends the buyer back to `GET /success?session_id=…`. The server
   **retrieves the session from Stripe and confirms `payment_status == "paid"`**
   before delivering anything — the redirect alone is never trusted.
3. The order is recorded in SQLite and a **signed license token** is minted
   (HMAC-SHA256 over `{slug, email}`), tied to the buyer's email.
4. `GET /download?token=…` verifies the signature and streams a zip built on the
   fly from the product's source dirs, with a **personalized `LICENSE.txt`** and
   a `README-FIRST.txt` injected. Forged or altered tokens get a `403`.

## Going live (Stripe)

The store runs without Stripe (storefront preview). To take real payments:

```bash
export STRIPE_API_KEY=sk_live_...            # or sk_test_... to rehearse
export STORE_BASE_URL=https://skills.allerion.io
export STORE_SIGNING_SECRET=$(python3 -c "import secrets;print(secrets.token_hex(32))")
python3 server.py --host 0.0.0.0 --port 8088
```

- `STRIPE_API_KEY` — turns checkout on. With `sk_test_…` you can run the full
  flow using Stripe test cards (e.g. `4242 4242 4242 4242`).
- `STORE_BASE_URL` — public URL for Stripe success/cancel redirects.
- `STORE_SIGNING_SECRET` — **required for production.** Without it, license
  tokens are signed with a known dev key and the server warns on startup.

Optional — use stable Stripe Price ids instead of inline prices:

```bash
STRIPE_API_KEY=sk_test_... python3 setup_stripe.py   # prints export lines
```

## Routes

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Storefront (product grid) |
| GET | `/api/products` | Catalog as JSON |
| GET | `/buy/<slug>` | Create Stripe Checkout + redirect |
| GET | `/success?session_id=…` | Verify payment, mint license, show download |
| GET | `/download?token=…` | Verify license, stream product zip |
| GET | `/healthz` | Health + Stripe/signing status + order count |

## Local testing without Stripe

Set `STORE_DEV_FULFILLMENT=1` to enable a **dev grant** link on the checkout page
that mints a license without payment — for testing fulfillment on your machine
only. Dev grants are recorded with `source='dev'` and never counted as revenue.

```bash
STORE_DEV_FULFILLMENT=1 STORE_SIGNING_SECRET=test python3 server.py --port 8090
```

## Tests

```bash
python3 -m pytest tests/ -q          # catalog, license signing, zip delivery
python3 products/codex-devkit/server.py --selftest
```

## Data

SQLite at `apps/store/store.db` (git-ignored), overridable via `STORE_DB`. The
`orders` table records each fulfilled purchase (slug, email, amount, Stripe
session id) and is created automatically.

## How it fits the platform

This is the **revenue front** of the Allerion stack. The marketing site +
embedded CRM (`apps/platform/`) sells the platform tiers and captures leads; this
store sells productized, self-serve developer tools that anyone can buy and
download in one click. Both checkout flows run through the same Stripe account.
