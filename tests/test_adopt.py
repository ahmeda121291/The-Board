"""`boardroom adopt` — reconcile untracked Kraken holdings (list + flatten).

An orphan is a coin held on the venue with no tracked open position (crash
residue, or a buy made outside the loop) — money the auto-sell loop can't manage.
These tests drive the Orchestrator with a fake live Kraken so nothing hits the
network or real money.
"""

from __future__ import annotations

import datetime as dt

from boardroom.brokers.base import Broker, Fill, Order, OrderSide
from boardroom.brokers.stub import StubBroker
from boardroom.factory import build_default_org
from boardroom.persistence.repository import InMemoryRepository, OpenPosition
from boardroom.schemas import Venue


class FakeKraken(Broker):
    """A live (non-stub) Kraken that reports fixed holdings and records orders."""

    venue = Venue.KRAKEN
    supports_withdrawal = False

    def __init__(self, holdings: list[dict]) -> None:
        self._holdings = holdings
        self.orders: list[Order] = []

    def health_check(self) -> bool:
        return True

    def get_cash_cad(self) -> float:
        return 50.0

    def get_positions(self) -> list[dict]:
        return [dict(h) for h in self._holdings]

    def place_order(self, order: Order, *, live: bool) -> Fill:
        self.orders.append(order)
        price = 137.7
        qty = order.base_qty if order.base_qty is not None else order.notional_cad / price
        return Fill(
            client_order_id=order.client_order_id, venue=Venue.KRAKEN, symbol=order.symbol,
            side=order.side, filled_qty=qty, avg_price=price,
            fee_cad=abs(order.notional_cad) * 0.0026, fx_cost_cad=0.0,
            filled_at=dt.datetime.now(dt.timezone.utc), is_live=bool(live), raw={"txid": ["TX1"]},
        )


def _org(holdings, repo=None):
    return build_default_org(
        data_mode="synthetic",
        repo=repo or InMemoryRepository(),
        brokers={Venue.KRAKEN: FakeKraken(holdings), Venue.IBKR: StubBroker(Venue.IBKR)},
    )


def _aave_holding():
    return {"symbol": "AAVE", "qty": 0.7399, "market_value_cad": 101.91}


# ---- detection --------------------------------------------------------------
def test_orphan_is_flagged_as_untracked():
    org = _org([_aave_holding()])
    recon = org.reconcile_positions()
    assert [u["asset"] for u in recon["untracked"]] == ["AAVE"]


def test_tracked_position_is_not_flagged():
    repo = InMemoryRepository()
    repo.save_open_position(
        OpenPosition(
            decision_id="d1", division="event", venue="kraken", symbol="AAVEUSD",
            size_cad=100.0, predicted_return=0.0, predicted_confidence=0.5, cost_cad=0.3,
            stop_fraction=0.15, band_low=-1.0, band_high=1.0, horizon_days=7.0,
            opened_at=dt.datetime.now(dt.timezone.utc), live=True, qty=0.7399,
        )
    )
    org = _org([_aave_holding()], repo=repo)
    assert org.reconcile_positions()["untracked"] == []


# ---- flatten ----------------------------------------------------------------
def test_flatten_live_sells_exact_qty(monkeypatch):
    org = _org([_aave_holding()])
    org.confirm_live = True
    monkeypatch.setattr(org.settings, "live_trading", True)

    res = org.flatten_holding("aave")  # case-insensitive
    assert res["live"] is True
    order = org.brokers[Venue.KRAKEN].orders[-1]
    assert order.side is OrderSide.SELL
    assert order.base_qty == 0.7399          # sells the EXACT held quantity
    assert order.symbol == "AAVECAD"          # account-quote pair (CAD-funded)
    # The exit is recorded and audited.
    assert org.repo.fills
    assert any(ev == "position_flattened" for ev, _ in org.repo.audit_log)


def test_flatten_dry_run_places_no_real_order(monkeypatch):
    # No --confirm-live → effective_live False → simulated fill, nothing recorded.
    org = _org([_aave_holding()])
    monkeypatch.setattr(org.settings, "live_trading", True)  # armed, but not confirmed
    res = org.flatten_holding("AAVE")
    assert res["live"] is False
    assert not org.repo.fills
    assert not any(ev == "position_flattened" for ev, _ in org.repo.audit_log)


def test_flatten_unknown_asset_returns_none():
    org = _org([_aave_holding()])
    assert org.flatten_holding("DOGE") is None


def test_flatten_needs_a_live_broker():
    # A stub Kraken (no creds) cannot reconcile or flatten.
    org = build_default_org(
        data_mode="synthetic",
        repo=InMemoryRepository(),
        brokers={Venue.KRAKEN: StubBroker(Venue.KRAKEN), Venue.IBKR: StubBroker(Venue.IBKR)},
    )
    assert org.flatten_holding("AAVE") is None
    assert org.reconcile_positions() is None
