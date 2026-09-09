"""A2A protocol primitives: the things agents offer, want, and exchange."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class MessageType(str, Enum):
    DISCOVER = "discover"
    QUOTE = "quote"
    OFFER = "offer"
    COUNTER = "counter"
    ACCEPT = "accept"
    REJECT = "reject"
    DELIVER = "deliver"
    SETTLE = "settle"


@dataclass(frozen=True)
class Service:
    """A capability a merchant agent sells, with its pricing envelope."""

    id: str
    name: str
    capability: str          # the tag buyers search on, e.g. "summarize"
    merchant_id: str
    list_price: float        # opening ask
    floor_price: float       # walk-away minimum
    quality: float           # 0..1, drives buyer's perceived value
    capacity_per_round: int  # how many deals it can fulfil per round

    def __post_init__(self) -> None:
        if self.floor_price > self.list_price:
            raise ValueError(f"{self.id}: floor_price exceeds list_price")
        if not 0.0 <= self.quality <= 1.0:
            raise ValueError(f"{self.id}: quality must be in [0,1]")


@dataclass(frozen=True)
class Need:
    """Something a buyer agent wants done, with its max willingness to pay."""

    id: str
    buyer_id: str
    capability: str
    value: float             # the most this buyer will pay for one unit
    prompt: str = ""         # passed to fulfilment


@dataclass
class Deal:
    """A closed transaction between a buyer and a merchant."""

    round: int
    buyer_id: str
    merchant_id: str
    service_id: str
    capability: str
    price: float
    rounds_negotiated: int
    delivered: Optional[str] = None
    fee: float = 0.0


@dataclass
class Message:
    """An A2A message exchanged during negotiation (kept for the transcript)."""

    mtype: MessageType
    sender: str
    recipient: str
    capability: str
    price: Optional[float] = None
    meta: dict = field(default_factory=dict)

    def render(self) -> str:
        amount = f" ${self.price:,.2f}" if self.price is not None else ""
        return f"{self.sender:>12} →{self.recipient:>12}  {self.mtype.value.upper():<8}{amount}  [{self.capability}]"
