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
    # Directional defaults to IBKR venue with a stub when no creds are set.
    assert isinstance(brokers[Venue.IBKR], StubBroker)


# ---- SnapTrade --------------------------------------------------------------
def test_snaptrade_market_order_uses_notional_value():
    from boardroom.brokers.snaptrade import build_force_order_payload

    body = build_force_order_payload(_order(symbol="XIC.TO", notional=30.0), account_id="acc-1")
    assert body["account_id"] == "acc-1"
    assert body["action"] == "BUY"
    assert body["order_type"] == "Market"
    assert body["notional_value"] == {"amount": 30.0, "currency": "CAD"}
    assert "units" not in body


def test_snaptrade_limit_order_uses_units():
    from boardroom.brokers.snaptrade import build_force_order_payload

    body = build_force_order_payload(_order(symbol="XIC.TO", notional=30.0, limit=30.0), account_id="a")
    assert body["order_type"] == "Limit"
    assert body["price"] == 30.0
    assert body["units"] == 1.0


def test_snaptrade_simulates_without_creds():
    from boardroom.brokers.snaptrade import SnapTradeBroker

    b = SnapTradeBroker()
    assert b.supports_withdrawal is False
    fill = b.place_order(_order(symbol="XIC.TO", limit=30.0), live=True)
    assert fill.is_live is False
    assert fill.raw == {"simulated": True}


def test_snaptrade_fx_cost_punishes_usd():
    from boardroom.risk.cost import CostModel

    cm = CostModel()
    cad = cm.round_trip_cost_cad(venue=Venue.SNAPTRADE, notional_cad=40, needs_fx=False)
    usd = cm.round_trip_cost_cad(venue=Venue.SNAPTRADE, notional_cad=40, needs_fx=True)
    # CAD-listed is cheap; USD pays ~1.5% each way -> the cost gate steers to CAD.
    assert cad < usd
    assert usd >= 40 * 0.03 * 0.99  # ~3% round-trip FX floor
