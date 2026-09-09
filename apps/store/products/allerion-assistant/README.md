# Allerion Assistant

Your own AI assistant — a complete, self-hostable chat app you run and brand
yourself. Streaming web UI + a backend built on the **official Anthropic SDK**.
Point it at the Anthropic API directly, or at your own gateway.

## What you get

- A polished streaming chat UI (dark, on-brand) — no build step, one HTML page
  served by the app.
- A backend on `claude-opus-4-8` with **adaptive thinking** and **effort**
  control, streaming tokens (and a live "thinking" trace) to the browser.
- Multi-turn memory per browser session, with the correct Opus multi-turn
  replay (thinking blocks preserved across turns).
- Fully configurable by environment: model, effort, system prompt / persona,
  max tokens, and a custom base URL so it can run against your own gateway.
- Graceful error + refusal handling surfaced to the UI.

It's yours: change the persona, restyle the page, add tools, swap the in-memory
store for a database. ~1 file, no framework.

## Run it

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...        # get one at console.anthropic.com
python3 assistant.py                        # http://127.0.0.1:8077
python3 assistant.py --host 0.0.0.0 --port 9000
```

Open the URL and chat. Health check at `/healthz`.

## Configure

All optional (see `.env.example`):

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | **Required.** Your Anthropic key. |
| `ANTHROPIC_BASE_URL` | api.anthropic.com | Point at your own Anthropic-compatible gateway. |
| `ASSISTANT_MODEL` | `claude-opus-4-8` | Any current Claude model. |
| `ASSISTANT_EFFORT` | `high` | `low` / `medium` / `high` / `max` (some models also accept `xhigh`). Lower = faster/cheaper. |
| `ASSISTANT_SYSTEM` | a sensible default | The assistant's persona / instructions. |
| `ASSISTANT_MAX_TOKENS` | `8000` | Max output tokens per reply. |
| `ASSISTANT_NAME` | `Allerion Assistant` | Title shown in the UI. |

Want a snappier, cheaper assistant? Set `ASSISTANT_EFFORT=low` and
`ASSISTANT_MODEL=claude-haiku-4-5`. Want the most capable? `ASSISTANT_MODEL=claude-fable-5`.

## Make it yours

- **Persona**: set `ASSISTANT_SYSTEM` (e.g. "You are the support bot for Acme…").
- **Branding**: the UI is the `PAGE` string in `assistant.py` — restyle freely.
- **Persistence**: `SESSIONS` is an in-memory dict; back it with Redis/Postgres
  to survive restarts and scale across workers.
- **Tools**: the backend uses `client.messages.stream(...)` — add a `tools=[...]`
  list and a tool-execution loop to give your assistant abilities.

## What's included

- `assistant.py` — the app (UI + backend)
- `requirements.txt` — one dependency, the official `anthropic` SDK
- `.env.example` — configuration template
- `LICENSE.txt` — commercial license (one seat per purchase)

## License

Commercial license, one developer seat per purchase. See `LICENSE.txt`.
Sold by Allerion Systems — https://allerion.io
