"""The Allerion gateway connector — embedded into every agent.

A Connector is an agent's handle to the Allerion AI gateway (the
OpenAI-compatible endpoint from infra/ai-gateway). Each agent carries its own
Connector, so fulfilment and reasoning route through the shared gateway —
metered, rate-limited, and billable per agent. When no gateway/key is
configured the connector falls back to deterministic stubs, so a whole fleet
runs offline with zero credentials.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import llm


@dataclass
class Connector:
    """Per-agent connection to the gateway."""

    agent_id: str
    model: str = llm.MODEL
    calls: int = 0

    @property
    def live(self) -> bool:
        return llm.live()

    def status(self) -> str:
        return f"live:{self.model}" if self.live else "stub"

    def fulfill(self, capability: str, prompt: str) -> str:
        """Route a unit of work through the gateway on this agent's behalf."""
        self.calls += 1
        return llm.fulfill(capability, prompt)


def attach(agents) -> int:
    """Embed a fresh Connector into each agent. Returns the count wired."""
    n = 0
    for a in agents:
        a.connector = Connector(agent_id=a.id)
        n += 1
    return n
