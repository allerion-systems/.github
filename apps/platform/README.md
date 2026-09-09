# Allerion Platform — marketing site + embedded CRM

A single, zero-dependency app (Python standard library only) that serves the
Allerion **marketing website** and an **embedded CRM** over one SQLite store.
Access requests on the landing page become leads; the CRM tracks them through a
pipeline.

## Run

```bash
cd apps/platform
python3 server.py            # http://127.0.0.1:8099
python3 server.py --port 9000 --host 0.0.0.0
```

No `pip install` — it uses only `http.server` + `sqlite3`.

## Routes

| Method | Path | Purpose |
|--------|------|---------|
| GET  | `/` | Marketing landing page (capabilities, pricing, access form) |
| POST | `/api/leads` | Create a lead (HTML form post → redirects to `/crm`; JSON → returns the lead) |
| GET  | `/crm` | CRM dashboard: pipeline KPIs + lead table with inline status updates |
| GET  | `/api/leads` | List leads as JSON |
| POST | `/api/leads/<id>/status` | Advance a lead's pipeline status (`new → contacted → qualified → won/lost`) |
| GET  | `/healthz` | Health check |

## Examples

```bash
# Capture a lead via the JSON API
curl -X POST http://127.0.0.1:8099/api/leads -H 'Content-Type: application/json' \
  -d '{"name":"Jane","email":"jane@acme.co","company":"Acme","interest":"AI Gateway"}'

# Move it through the pipeline
curl -X POST http://127.0.0.1:8099/api/leads/1/status \
  -H 'Content-Type: application/json' -d '{"status":"qualified"}'

# Read the CRM
curl http://127.0.0.1:8099/api/leads
```

## Data

SQLite at `apps/platform/crm.db` (git-ignored), overridable via `ALLERION_CRM_DB`.
The `leads` table is created automatically on first run.

## How it fits the platform

This is the customer-facing front of the Allerion stack: the **landing page**
sells the AI Gateway / Agent Orchestration / Sovereign AI offerings, and the
**embedded CRM** captures and qualifies the demand. It runs standalone today;
the lead pipeline is the natural place to later connect Stripe billing
(`infra/ai-gateway/billing/`) when a lead converts to a paying gateway tenant.
