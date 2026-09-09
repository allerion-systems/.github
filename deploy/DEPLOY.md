# Deploy Allerion to your VPS

One Docker stack puts the **marketing site + CRM** on `allerion.io` and the
**skills store** on `skills.allerion.io`, behind Caddy with automatic HTTPS.
From a clean VPS, going live is ~10 minutes.

## 0. Prerequisites

- A VPS with a public IP, ports **80** and **443** open in the firewall.
- The `allerion.io` domain (you have it).
- Docker + the Compose plugin on the VPS:
  ```bash
  curl -fsSL https://get.docker.com | sh
  ```

## 1. Point DNS at the VPS

Create **A records** for each hostname → your VPS public IP:

| Host | Type | Value |
|------|------|-------|
| `allerion.io` | A | `<your VPS IP>` |
| `www.allerion.io` | A | `<your VPS IP>` |
| `skills.allerion.io` | A | `<your VPS IP>` |

(If you also run the AI gateway, `api.allerion.io` → same IP — see step 6.)
Wait for DNS to propagate (`dig +short allerion.io` should return your IP).
Caddy can't issue certificates until DNS resolves to this box.

## 2. Get the code on the VPS

```bash
git clone https://github.com/allerion-systems/.github.git allerion
cd allerion
git checkout claude/nvidia-ai-models-access-mmn5n5   # until this is merged to main
cd deploy
```

## 3. Configure

```bash
cp .env.example .env
# generate a strong, STABLE signing secret (don't change it after launch):
echo "STORE_SIGNING_SECRET=$(openssl rand -hex 32)" >> .env
nano .env     # set ACME_EMAIL, and STRIPE_API_KEY when ready (see step 5)
```

Leaving `STRIPE_API_KEY` blank is fine for a first boot — the store comes up in
**preview** mode (browsable, checkout shows "configuring"). Add the key when
you're ready to charge.

## 4. Launch

Pre-flight first (checks docker/compose, `.env` secrets, DNS, and ports 80/443):

```bash
./preflight.sh
```

Then bring the stack up, and once it's running confirm both sites are healthy:

```bash
make up                           # = docker compose up -d --build  (see `make help`)
docker compose logs -f caddy      # watch it obtain TLS certs (Ctrl-C to stop tailing)
./smoke.sh                        # checks https://allerion.io/healthz + https://skills.allerion.io/healthz
```

Then open:

- **https://allerion.io** — marketing site + CRM console at `/crm`
- **https://skills.allerion.io** — the store (and `…/healthz` for status)

If certs don't issue: DNS isn't pointing here yet, or 80/443 are firewalled.

## 5. Turn on payments (Stripe)

1. Create a Stripe account → get your secret key.
2. **Rehearse first** with a test key:
   ```bash
   # in deploy/.env
   STRIPE_API_KEY=sk_test_...
   ```
   `docker compose up -d` again, then buy a product using Stripe's test card
   `4242 4242 4242 4242` (any future expiry, any CVC). You should be redirected
   back and get a real download link.
3. **Go live**: swap in `sk_live_...` and `docker compose up -d`. Real cards now
   charge real money; purchases deliver the license-keyed zip instantly.
4. **Add the webhook (recommended)** so sales record durably even if the buyer
   closes the success page. In the Stripe Dashboard → Developers → Webhooks →
   Add endpoint, enter `https://skills.allerion.io/webhook`, subscribe to the
   `checkout.session.completed` event, and copy the generated **Signing secret**
   (`whsec_…`) into `STRIPE_WEBHOOK_SECRET` in `.env`, then `docker compose up -d`.

Optional — mint stable Stripe Price ids instead of inline prices (cleaner Stripe
dashboard / analytics):
```bash
STRIPE_API_KEY=sk_live_... python3 ../apps/store/setup_stripe.py   # prints export lines
# paste the printed STRIPE_PRICE_* values into deploy/.env, then: docker compose up -d
```

**Test-mode Price ids already exist** for the sandbox account
`acct_1TissgDCOCaYiMmZ` — see `deploy/stripe-prices.test.env`. While rehearsing
with that account's `sk_test_` key, append that file's lines to `.env`. For live
mode, mint fresh ids with the command above (test ids don't work with live keys).

## 6. If you already run the AI gateway (`infra/ai-gateway`)

That stack ships its **own** Caddy, and only one process can bind ports 80/443.
Pick one:

- **Simplest:** stop the gateway's standalone Caddy, uncomment the
  `api.allerion.io` block in `deploy/Caddyfile`, put the LiteLLM container on the
  same Docker network, and let this single Caddy serve all of
  `allerion.io` / `skills.allerion.io` / `api.allerion.io`.
- **Or:** run the gateway on a different box / IP and keep `api.allerion.io`'s
  DNS pointed there.

## Operating it

```bash
docker compose ps                 # status
docker compose logs -f store      # store logs
docker compose pull && docker compose up -d --build   # update after a git pull
docker compose down               # stop (data persists in named volumes)
```

Data lives in Docker volumes (`platform_data`, `store_data`) — SQLite for CRM
leads and store orders. `make backup` tars both volumes to timestamped files;
`make help` lists every shortcut (`up`, `down`, `logs`, `pull`, `ps`, `backup`).

## Automate updates (optional)

`.github/workflows/deploy.yml` can redeploy on every push: it SSHes into the VPS
and runs `git pull --ff-only && docker compose up -d --build`. It stays inert
until you add these repo secrets (GitHub → Settings → Secrets and variables →
Actions): `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY` (a private key authorized on the
box), and optional `VPS_PORT`. It assumes the repo is checked out at `~/allerion`
on the VPS (step 2). Until then, just `make pull` on the box to update by hand.

## What "live" then means

- `https://allerion.io` and `https://skills.allerion.io` are public with HTTPS.
- With a live `STRIPE_API_KEY`, the store takes real payments and delivers
  downloads automatically.
- `https://skills.allerion.io/healthz` reports `stripe_live: true` and your
  order/revenue counts once sales come in.
