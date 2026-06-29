"""Venue adapters: pure helpers + the live-gating safety logic (no network)."""

from __future__ import annotations

import pytest

from boardroom.brokers.base import Order, OrderSide
from boardroom.brokers.ibkr import IBKRBroker, build_order_payload
from boardroom.brokers.kraken import KrakenBroker, sign, volume_from_notional
from boardroom.schemas import Venue


def _order(symbol="XBTCAD", notional=10.0, limit=None) -> Order:
    return Order(
        symbol=symbol, side=OrderSide.BUY, notional_cad=notional,
        division="event", client_order_id="cid-123", limit_price=limit,
    )


# ---- pure helpers -----------------------------------------------------------
def test_kraken_sign_is_deterministic_and_b64():
    import base64

    secret = base64.b64encode(b"super-secret-bytes-1234567890").decode()
    data = {"nonce": 1234567890, "pair": "XBTCAD", "type": "buy"}
    s1 = sign("/0/private/AddOrder", dict(data), secret)
    s2 = sign("/0/private/AddOrder", dict(data), secret)
    assert s1 == s2
    assert base64.b64decode(s1)  # valid base64


def test_volume_from_notional():
    assert volume_from_notional(100.0, 50.0) == 2.0
    with pytest.raises(ValueError):
        volume_from_notional(100.0, 0.0)


def test_ibkr_payload_uses_cash_qty():
    payload = build_order_payload(_order(symbol="SPY", notional=25.0), conid=756733)
    o = payload["orders"][0]
    assert o["conid"] == 756733
    assert o["side"] == "BUY"
    assert o["orderType"] == "MKT"
    assert o["cashQty"] == 25.0
    assert o["cOID"] == "cid-123"


def test_ibkr_payload_limit_order():
    o = build_order_payload(_order(symbol="SPY", limit=400.0), conid=1)["orders"][0]
    assert o["orderType"] == "LMT"
    assert o["price"] == 400.0


# ---- safety: no withdrawal, no accidental live ------------------------------
def test_brokers_never_support_withdrawal():
    for b in (KrakenBroker(), IBKRBroker()):
        assert b.supports_withdrawal is False
        b.assert_no_withdrawal()  # must not raise


def test_kraken_simulates_without_creds_even_if_live_requested():
    # No credentials in the test env -> a live=True request must SIMULATE,
    # never touch the network, never claim to be live.
    fill = KrakenBroker().place_order(_order(limit=100.0), live=True)
    assert fill.is_live is False
    assert fill.raw == {"simulated": True}


def test_ibkr_simulates_without_account_even_if_live_requested():
    fill = IBKRBroker().place_order(_order(symbol="SPY", limit=400.0), live=True)
    assert fill.is_live is False
    assert fill.raw == {"simulated": True}


def test_effective_live_requires_global_flag(monkeypatch):
    # Even with creds present, effective_live is False unless LIVE_TRADING is on.
    kb = KrakenBroker()
    monkeypatch.setattr(type(kb), "_has_creds", property(lambda self: True))
    monkeypatch.setattr(kb._settings, "live_trading", False)
    assert kb._effective_live(live=True) is False
    monkeypatch.setattr(kb._settings, "live_trading", True)
    assert kb._effective_live(live=True) is True
    # And a per-call live=False always wins.
    assert kb._effective_live(live=False) is False


def test_make_brokers_defaults_to_stubs():
    from boardroom.brokers import make_brokers
    from boardroom.brokers.stub import StubBroker

    brokers = make_brokers(prefer_live=False)
    assert isinstance(brokers[Venue.KRAKEN], StubBroker)
    # Directional defaults to the IBKR venue with a stub when no creds are set.
    assert isinstance(brokers[Venue.IBKR], StubBroker)


def test_ibkr_fx_cost_adds_for_usd():
    from boardroom.risk.cost import CostModel

    cm = CostModel()
    cad = cm.round_trip_cost_cad(venue=Venue.IBKR, notional_cad=40, needs_fx=False)
    usd = cm.round_trip_cost_cad(venue=Venue.IBKR, notional_cad=40, needs_fx=True)
    # Crossing CAD<->USD on IBKR costs a bit more than a same-currency trade.
    assert usd > cad
