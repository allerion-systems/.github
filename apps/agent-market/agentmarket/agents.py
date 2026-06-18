"""The agents: merchants that sell services and buyers that procure them."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional

from .protocol import Need, Service


@dataclass
class MerchantAgent:
    id: str
    name: str
    services: List[Service] = field(default_factory=list)
    concession: float = 0.4   # how fast it moves from ask toward floor (0..1)
    sales: int = 0
    connector: Optional[Any] = None  # gateway connector (see connector.Connector)

    def offer(self, service: Service) -> "MerchantAgent":
        self.services.append(service)
        return self

    def quote(self, service: Service) -> float:
        return service.list_price

    def counter(self, service: Service, current_ask: float, buyer_bid: float) -> float:
        """Concede toward the buyer, but never below the service floor."""
        target = max(service.floor_price, current_ask - (current_ask - service.floor_price) * self.concession)
        # If the buyer's bid already clears the floor, meet in the middle.
        if buyer_bid >= service.floor_price:
            return round(max(service.floor_price, min(target, (target + buyer_bid) / 2)), 2)
        return round(target, 2)


@dataclass
class BuyerAgent:
    id: str
    name: str
    needs: List[Need] = field(default_factory=list)
    quality_weight: float = 0.5   # how much it trades price for quality
    concession: float = 0.4
    purchases: int = 0
    connector: Optional[Any] = None  # gateway connector (see connector.Connector)

    def score(self, need: Need, service: Service) -> float:
        """Expected utility of a supplier before negotiating: value adjusted
        for quality, minus the opening ask. Higher is better."""
        perceived_value = need.value * (0.5 + self.quality_weight * service.quality)
        return perceived_value - service.list_price

    def rank(self, need: Need, services: List[Service]) -> List[Service]:
        return sorted(services, key=lambda s: self.score(need, s), reverse=True)

    def opening_bid(self, need: Need, service: Service) -> float:
        # Lowball but never above what the need is worth.
        return round(min(need.value, service.list_price * 0.6), 2)

    def raise_bid(self, need: Need, current_bid: float) -> float:
        return round(min(need.value, current_bid + (need.value - current_bid) * self.concession), 2)

    def accepts(self, need: Need, price: float) -> bool:
        return price <= need.value

    def next_need(self) -> Optional[Need]:
        return self.needs.pop(0) if self.needs else None
