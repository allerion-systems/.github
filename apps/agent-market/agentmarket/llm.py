"""Service fulfilment.

If LLM_BASE_URL and LLM_API_KEY are set, fulfilment calls a real
OpenAI-compatible endpoint (point it at the Allerion gateway, OpenRouter,
NVIDIA, OpenAI, etc.). Otherwise it returns a deterministic stub so the whole
market runs offline with no keys.
"""
from __future__ import annotations

import os
import textwrap

BASE_URL = os.environ.get("LLM_BASE_URL", "").rstrip("/")
API_KEY = os.environ.get("LLM_API_KEY", "")
MODEL = os.environ.get("LLM_MODEL", "deepseek-r1")


def live() -> bool:
    return bool(BASE_URL and API_KEY)


def _stub(capability: str, prompt: str) -> str:
    body = prompt or f"(no prompt supplied for {capability})"
    return textwrap.shorten(
        f"[stub:{capability}] delivered work for → {body}", width=160, placeholder=" …"
    )


def fulfill(capability: str, prompt: str) -> str:
    """Return the work product for one purchased service unit."""
    if not live():
        return _stub(capability, prompt)

    # Use the standard library so live mode needs no extra dependency.
    import json
    import urllib.request

    system = f"You are a specialist agent providing the '{capability}' service. Be concise."
    payload = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt or capability},
        ],
        "max_tokens": 120,
    }).encode()
    req = urllib.request.Request(
        f"{BASE_URL}/v1/chat/completions",
        data=payload,
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:  # noqa: BLE001 — never let fulfilment crash the market
        return f"[fulfilment error via {MODEL}: {e}]"
