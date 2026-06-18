"""Tests for the agent market: money conservation, settlement, negotiation."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agentmarket.agents import BuyerAgent, MerchantAgent
from agentmarket.ledger import InsufficientFunds, Ledger
from agentmarket.marketplace import Marketplace
from agentmarket.market import Market
from agentmarket.protocol import Deal, Need, Service


def make_service(**kw):
    base = dict(id="s1", name="S", capability="summarize", merchant_id="m1",
                list_price=10, floor_price=6, quality=0.8, capacity_per_round=2)
    base.update(kw)
    return Service(**base)


def test_service_rejects_bad_envelope():
    with pytest.raises(ValueError):
        make_service(list_price=5, floor_price=9)
    with pytest.raises(ValueError):
        make_service(quality=1.5)


def test_ledger_conserves_money():
    led = Ledger(fee_rate=0.1)
    led.open_account("buyer", 100)
    led.open_account("m1")
    assert led.total_money() == 0.0  # mint offsets opening balances
    led.settle(Deal(1, "buyer", "m1", "s1", "summarize", 10, 1))
    assert led.total_money() == 0.0  # still conserved after a trade


def test_settlement_splits_fee():
    led = Ledger(fee_rate=0.1)
    led.open_account("buyer", 100)
    led.open_account("m1")
    led.settle(Deal(1, "buyer", "m1", "s1", "summarize", 10, 1))
    assert led.balance("buyer") == 90.0
    assert led.balance("m1") == 9.0           # 10 - 10% fee
    assert led.platform_revenue() == 1.0


def test_insufficient_funds_blocks_settlement():
    led = Ledger()
    led.open_account("buyer", 5)
    led.open_account("m1")
    with pytest.raises(InsufficientFunds):
        led.settle(Deal(1, "buyer", "m1", "s1", "summarize", 10, 1))


def test_negotiation_closes_when_overlap_exists():
    mp = Marketplace()
    m = MerchantAgent("m1", "M").offer(make_service(list_price=10, floor_price=6))
    mp.register(m)
    mp.reset_round()
    buyer = BuyerAgent("b1", "B")
    need = Need("n1", "b1", "summarize", value=12)
    price, rounds, transcript = mp.negotiate(buyer, need, mp.services[0])
    assert price is not None
    assert 6 <= price <= 12
    assert rounds >= 1


def test_negotiation_fails_when_floor_above_value():
    mp = Marketplace()
    m = MerchantAgent("m1", "M").offer(make_service(list_price=20, floor_price=15))
    mp.register(m)
    mp.reset_round()
    buyer = BuyerAgent("b1", "B")
    need = Need("n1", "b1", "summarize", value=10)  # worth less than the floor
    price, _, _ = mp.negotiate(buyer, need, mp.services[0])
    assert price is None


def test_full_market_run_conserves_and_trades():
    mp = Marketplace()
    seller = MerchantAgent("m1", "M", concession=0.4)
    seller.offer(make_service(capacity_per_round=5))
    mp.register(seller)
    market = Market(marketplace=mp, ledger=Ledger(fee_rate=0.1))
    buyer = BuyerAgent("b1", "B")
    buyer.needs = [Need(f"n{i}", "b1", "summarize", 12) for i in range(3)]
    market.add_buyer(buyer, opening_balance=100)

    market.run(3, fulfill=True)

    summary = market.summary()
    assert summary["deals"] >= 1
    assert summary["money_conserved"] == 0.0
    assert summary["platform_revenue"] > 0
    # GMV must equal what left the buyer's wallet.
    assert round(100 - market.ledger.balance("b1"), 2) == summary["gmv"]
