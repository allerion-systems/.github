"""The marketplace: a registry, discovery, and the negotiation engine."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .agents import BuyerAgent, MerchantAgent
from .protocol import Deal, Message, MessageType, Need, Service

MAX_NEGOTIATION_ROUNDS = 6


@dataclass
class Marketplace:
    merchants: Dict[str, MerchantAgent] = field(default_factory=dict)
    services: List[Service] = field(default_factory=list)
    _remaining_capacity: Dict[str, int] = field(default_factory=dict)

    def register(self, merchant: MerchantAgent) -> None:
        self.merchants[merchant.id] = merchant
        for svc in merchant.services:
            self.services.append(svc)

    def reset_round(self) -> None:
        self._remaining_capacity = {s.id: s.capacity_per_round for s in self.services}

    def discover(self, capability: str) -> List[Service]:
        """Suppliers for a capability that still have capacity this round."""
        return [
            s for s in self.services
            if s.capability == capability and self._remaining_capacity.get(s.id, 0) > 0
        ]

    def negotiate(
        self, buyer: BuyerAgent, need: Need, service: Service
    ) -> Tuple[Optional[float], int, List[Message]]:
        """Alternating-offer bargaining. Returns (agreed_price | None, rounds, transcript)."""
        merchant = self.merchants[service.merchant_id]
        transcript: List[Message] = [
            Message(MessageType.DISCOVER, buyer.id, service.merchant_id, need.capability)
        ]

        ask = merchant.quote(service)
        transcript.append(Message(MessageType.QUOTE, service.merchant_id, buyer.id, need.capability, ask))

        # Impossible deal: merchant's floor is above what the need is worth.
        if service.floor_price > need.value:
            transcript.append(Message(MessageType.REJECT, buyer.id, service.merchant_id, need.capability))
            return None, 0, transcript

        bid = buyer.opening_bid(need, service)
        transcript.append(Message(MessageType.OFFER, buyer.id, service.merchant_id, need.capability, bid))

        for r in range(1, MAX_NEGOTIATION_ROUNDS + 1):
            if bid >= ask:  # buyer's bid meets the ask → done at the ask
                transcript.append(Message(MessageType.ACCEPT, buyer.id, service.merchant_id, need.capability, ask))
                return round(ask, 2), r, transcript

            ask = merchant.counter(service, ask, bid)
            transcript.append(Message(MessageType.COUNTER, service.merchant_id, buyer.id, need.capability, ask))

            if bid >= ask and buyer.accepts(need, ask):
                transcript.append(Message(MessageType.ACCEPT, buyer.id, service.merchant_id, need.capability, ask))
                return round(ask, 2), r, transcript

            bid = buyer.raise_bid(need, bid)
            transcript.append(Message(MessageType.OFFER, buyer.id, service.merchant_id, need.capability, bid))

            if bid >= ask and buyer.accepts(need, ask):
                price = round((ask + bid) / 2, 2)
                transcript.append(Message(MessageType.ACCEPT, buyer.id, service.merchant_id, need.capability, price))
                return price, r, transcript

        transcript.append(Message(MessageType.REJECT, buyer.id, service.merchant_id, need.capability))
        return None, MAX_NEGOTIATION_ROUNDS, transcript

    def consume_capacity(self, service: Service) -> None:
        self._remaining_capacity[service.id] -= 1
