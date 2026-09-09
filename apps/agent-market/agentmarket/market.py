"""The market loop: runs rounds where buyers procure from merchants."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from . import llm
from .agents import BuyerAgent, MerchantAgent
from .ledger import InsufficientFunds, Ledger
from .marketplace import Marketplace
from .protocol import Deal, Message


@dataclass
class RoundReport:
    round: int
    deals: List[Deal] = field(default_factory=list)
    transcript: List[Message] = field(default_factory=list)
    no_deals: int = 0


@dataclass
class Market:
    marketplace: Marketplace
    ledger: Ledger
    buyers: Dict[str, BuyerAgent] = field(default_factory=dict)
    reports: List[RoundReport] = field(default_factory=list)

    def add_buyer(self, buyer: BuyerAgent, opening_balance: float) -> None:
        self.buyers[buyer.id] = buyer
        self.ledger.open_account(buyer.id, opening_balance)

    def _ensure_accounts(self) -> None:
        for mid in self.marketplace.merchants:
            self.ledger.open_account(mid)
        self.ledger.open_account(self.ledger.house_id)

    def run_round(self, round_no: int, fulfill: bool = True) -> RoundReport:
        self._ensure_accounts()
        self.marketplace.reset_round()
        report = RoundReport(round=round_no)

        for buyer in self.buyers.values():
            need = buyer.next_need()
            if need is None:
                continue

            suppliers = self.marketplace.discover(need.capability)
            if not suppliers:
                report.no_deals += 1
                continue

            closed = False
            for service in buyer.rank(need, suppliers):
                if self.marketplace._remaining_capacity.get(service.id, 0) <= 0:
                    continue
                price, n, transcript = self.marketplace.negotiate(buyer, need, service)
                report.transcript.extend(transcript)
                if price is None:
                    continue
                if self.ledger.balance(buyer.id) < price:
                    continue  # can't afford; try next supplier

                deal = Deal(round_no, buyer.id, service.merchant_id, service.id,
                            need.capability, price, n)
                try:
                    self.ledger.settle(deal)
                except InsufficientFunds:
                    continue

                self.marketplace.consume_capacity(service)
                self.marketplace.merchants[service.merchant_id].sales += 1
                buyer.purchases += 1
                if fulfill:
                    deal.delivered = llm.fulfill(need.capability, need.prompt)
                report.deals.append(deal)
                closed = True
                break

            if not closed:
                report.no_deals += 1

        self.reports.append(report)
        return report

    def run(self, rounds: int, fulfill: bool = True) -> List[RoundReport]:
        return [self.run_round(r, fulfill=fulfill) for r in range(1, rounds + 1)]

    # --- analytics ---------------------------------------------------------
    def all_deals(self) -> List[Deal]:
        return [d for rep in self.reports for d in rep.deals]

    def summary(self) -> dict:
        deals = self.all_deals()
        gmv = round(sum(d.price for d in deals), 2)
        return {
            "deals": len(deals),
            "gmv": gmv,
            "platform_revenue": self.ledger.platform_revenue(),
            "avg_price": round(gmv / len(deals), 2) if deals else 0.0,
            "money_conserved": self.ledger.total_money(),
        }
