"""Execution robustness (found live 2026-08-05):

1. Sell clamp — a tracked position can exceed the actually-sellable spot
   balance (in-kind fee dust, Earn-allocated coins). TRU/EUL exits bounced for
   days on EOrder:Insufficient funds over ~1e-6 coins, leaving money stuck.
   Sells now clamp to the venue's own available balance.
2. Restricted assets — Kraken listed BLESSUSD but refused the order
   ("EAccount:Invalid permissions: BLESS trading restricted for CA:ON"),
   burning a funding slot. Refused assets are remembered and never funded again.
"""

from __future__ import annotations

import pytest

from boardroom.brokers.base import Order, OrderSide
from boardroom.brokers.kraken import KrakenBroker
from boardroom.persistence.repository import InMemoryRepository


def _sell_order(symbol: str, qty: float) -> Order:
    return Order(
        symbol=symbol, side=OrderSide.SELL, notional_cad=25.0,
        division="crypto_trend", client_order_id="c1", base_qty=qty,
    )


def _broker(monkeypatch, balances: dict) -> tuple[KrakenBroker, dict]:
    broker = KrakenBroker()
    monkeypatch.setattr(type(broker), "_has_creds", property(lambda self: True))
    monkeypatch.setattr(broker, "_effective_live", lambda live: True)
    monkeypatch.setattr(broker, "_ticker_price", lambda pair: 1.5)
    sent: dict = {}

    def private(method, data=None, retries=1):
        if method == "Balance":
            return dict(balances)
        if method == "AddOrder":
            sent.update(data or {})
            return {"txid": ["TXID1"]}
        raise AssertionError(method)

    monkeypatch.setattr(broker, "_private", private)
    monkeypatch.setattr(
        "boardroom.brokers.kraken.quote_to_cad_rate", lambda q, timeout=15.0: 1.35
    )
    return broker, sent


def test_sell_clamps_to_available_spot_balance(monkeypatch):
    # Tracked 10.80666498 EUL, venue holds 10.806664 — the dust short that
    # bounced every exit. The sell must go through at the venue's number.
    broker, sent = _broker(monkeypatch, {"EUL": "10.806664"})
    fill = broker.place_order(_sell_order("EULUSD", 10.80666498), live=True)
    assert fill.is_live
    assert float(sent["volume"]) == pytest.approx(10.806664)


def test_sell_ignores_earn_variants_and_counts_spot_only(monkeypatch):
    broker, sent = _broker(monkeypatch, {"TRU": "100.0", "TRU.F": "50.0"})
    broker.place_order(_sell_order("TRUUSD", 120.0), live=True)
    assert float(sent["volume"]) == pytest.approx(100.0)  # .F is not spot-sellable


def test_sell_with_no_balance_raises_cleanly(monkeypatch):
    broker, _ = _broker(monkeypatch, {"XXBT": "1.0"})
    with pytest.raises(RuntimeError, match="no available spot balance"):
        broker.place_order(_sell_order("EULUSD", 10.0), live=True)


def test_sell_without_balance_read_trades_tracked_qty(monkeypatch):
    broker, sent = _broker(monkeypatch, {})
    def private(method, data=None, retries=1):
        if method == "Balance":
            raise RuntimeError("boom")
        sent.update(data or {})
        return {"txid": ["TXID1"]}
    monkeypatch.setattr(broker, "_private", private)
    broker.place_order(_sell_order("EULUSD", 10.5), live=True)
    assert float(sent["volume"]) == pytest.approx(10.5)


def test_legacy_xbt_codes_match_for_clamp(monkeypatch):
    broker, sent = _broker(monkeypatch, {"XXBT": "0.5"})
    broker.place_order(_sell_order("XBTUSD", 0.6), live=True)
    assert float(sent["volume"]) == pytest.approx(0.5)


# ---- restricted-asset memory -------------------------------------------------

def test_repo_remembers_restricted_assets():
    repo = InMemoryRepository()
    assert repo.restricted_assets() == set()
    repo.add_restricted_asset("bless")
    repo.add_restricted_asset("BLESS")
    assert repo.restricted_assets() == {"BLESS"}
