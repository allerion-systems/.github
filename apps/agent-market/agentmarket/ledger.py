"""Settlement ledger: wallets, transactions, and the platform's cut.

Money is conserved: every settlement moves funds from a buyer to a merchant
and a commission to the platform (house) wallet — no money is created or
destroyed. `total_money()` is the invariant the tests assert on.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from .protocol import Deal


class InsufficientFunds(Exception):
    pass


@dataclass
class Entry:
    round: int
    debit: str          # who paid
    credit: str         # who received
    amount: float
    memo: str


@dataclass
class Ledger:
    house_id: str = "allerion"
    fee_rate: float = 0.10          # platform commission on every deal
    balances: Dict[str, float] = field(default_factory=dict)
    entries: List[Entry] = field(default_factory=list)

    def open_account(self, agent_id: str, opening_balance: float = 0.0) -> None:
        self.balances.setdefault(agent_id, 0.0)
        if opening_balance:
            # Opening balances are funded from a mint account so the live
            # economy still conserves money after seeding.
            self.balances[agent_id] += opening_balance
            self.balances.setdefault("__mint__", 0.0)
            self.balances["__mint__"] -= opening_balance

    def balance(self, agent_id: str) -> float:
        return self.balances.get(agent_id, 0.0)

    def settle(self, deal: Deal) -> Deal:
        """Move `deal.price` buyer→merchant, skimming `fee_rate` to the house."""
        if self.balance(deal.buyer_id) < deal.price:
            raise InsufficientFunds(
                f"{deal.buyer_id} has ${self.balance(deal.buyer_id):,.2f}, "
                f"needs ${deal.price:,.2f}"
            )
        fee = round(deal.price * self.fee_rate, 2)
        net = round(deal.price - fee, 2)

        self.balances[deal.buyer_id] -= deal.price
        self.balances.setdefault(deal.merchant_id, 0.0)
        self.balances[deal.merchant_id] += net
        self.balances.setdefault(self.house_id, 0.0)
        self.balances[self.house_id] += fee

        self.entries.append(Entry(deal.round, deal.buyer_id, deal.merchant_id, net,
                                  f"{deal.capability} ({deal.service_id})"))
        self.entries.append(Entry(deal.round, deal.buyer_id, self.house_id, fee,
                                  f"commission {self.fee_rate:.0%}"))
        deal.fee = fee
        return deal

    def total_money(self) -> float:
        return round(sum(self.balances.values()), 2)

    def platform_revenue(self) -> float:
        return round(self.balance(self.house_id), 2)
