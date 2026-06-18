# Allerion AI Gateway (`api.allerion.io`)

An OpenAI-compatible API gateway that fronts **NVIDIA's hosted model API**
under your own domain. Clients talk to `https://api.allerion.io`; the gateway
authenticates them with **your** virtual keys, swaps in the NVIDIA key
server-side, and enforces rate limits and budgets.

```
client ──TLS──> api.allerion.io ──> Caddy ──> LiteLLM ──> integrate.api.nvidia.com/v1
                                                  │
                                              Postgres (virtual keys, spend)
```

> **This is a proxy, not self-hosting.** Inference runs on NVIDIA's GPUs. It is
> the fastest path to a branded endpoint and the right first step. When you add
> your own GPU nodes later, register them in `litellm/config.yaml` and nothing
> else changes — same URL, same client keys. See the upgrade-path comments in
> that file.

## Stack

| Component | Role |
|-----------|------|
| **Caddy** | TLS termination (auto Let's Encrypt) + reverse proxy |
| **LiteLLM** | OpenAI-compatible proxy, virtual keys, rate limits, budgets, logging |
| **Postgres** | Stores virtual keys, teams, and spend |

No GPU required.

## Prerequisites

1. A VPS (1 vCPU / 1–2 GB RAM is plenty — this only proxies) with Docker + Docker Compose.
2. Ports **80** and **443** open to the internet.
3. An NVIDIA API key from <https://build.nvidia.com>.
4. DNS: an `A` (and `AAAA` if you have IPv6) record for **`api.allerion.io`**
   pointing at the VPS IP. Caddy needs this resolving before it can issue a cert.

## Setup

```bash
cd infra/ai-gateway
cp .env.example .env
# Fill in NVIDIA_API_KEY and generate the secrets:
#   openssl rand -hex 32   (for LITELLM_MASTER_KEY -> prefix sk-, and SALT_KEY)
#   openssl rand -hex 24   (for POSTGRES_PASSWORD)
$EDITOR .env

# (optional) set your ACME email in the Caddyfile global block

docker compose up -d
docker compose logs -f caddy   # watch the TLS cert get issued
```

Once Caddy reports a valid certificate, the gateway is live at
`https://api.allerion.io`.

## Mint a client key (don't share the master key)

The master key is admin-only. Issue scoped virtual keys per app/team:

```bash
curl https://api.allerion.io/key/generate \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
        "models": ["deepseek-r1", "llama-3.3-70b"],
        "max_budget": 25,
        "budget_duration": "30d",
        "rpm_limit": 60
      }'
```

That returns an `sk-...` key safe to give to a client.

## Use it (drop-in OpenAI client)

```bash
curl https://api.allerion.io/v1/chat/completions \
  -H "Authorization: Bearer sk-the-virtual-key" \
  -H "Content-Type: application/json" \
  -d '{
        "model": "deepseek-r1",
        "messages": [{"role": "user", "content": "Hello from allerion.io"}]
      }'
```

Any OpenAI SDK works — set `base_url="https://api.allerion.io/v1"` and the
virtual key as the API key.

## Models

Edit `litellm/config.yaml`. The `model_name` is the alias clients call; the
`model:` value must match an exact ID from <https://build.nvidia.com/models>.
Verify IDs against the catalog and your entitlement before enabling them.

## Hardening checklist

- [ ] `.env` is git-ignored (it is) and never committed.
- [ ] Master key used only for admin / key minting, never in client apps.
- [ ] Every client uses a scoped virtual key with `max_budget` + `rpm_limit`.
- [ ] A global `max_budget` is set in `config.yaml` as a backstop.
- [ ] VPS firewall allows only 80/443 (and your SSH).
- [ ] Review NVIDIA's `build.nvidia.com` / NGC terms before exposing the
      endpoint to third parties or commercial users — proxying their hosted
      API to others may be restricted.

## Upgrade path → real sovereign AI

To make this genuinely self-hosted, stand up NIM or vLLM on your own GPU nodes
and add them to `model_list` (see the commented `*-sovereign` example in
`config.yaml`). The gateway, domain, and client keys are unchanged — you're
just swapping the backend from NVIDIA's cloud to your own silicon.
