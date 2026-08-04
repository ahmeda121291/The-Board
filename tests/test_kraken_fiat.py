"""Fiat balance codes: Kraken reports the same currency under several asset
codes (ZCAD, plain CAD, CAD.F for Rewards-enrolled balances, CAD.HOLD for
deposits on hold). A deposit landing under a variant code must still count as
cash — and must never be mistaken for a coin holding. The original bug: a
deposit sitting in USD.F/CAD.HOLD was invisible to get_cash_cad, so the
dashboard equity never moved."""

from __future__ import annotations

import pytest

from boardroom.brokers import kraken as kraken_mod
from boardroom.brokers.kraken import KrakenBroker, _fiat_currency


# ---- _fiat_currency classification ------------------------------------------

@pytest.mark.parametrize(
    "asset,expected",
    [
        ("ZCAD", "CAD"),
        ("ZUSD", "USD"),
        ("ZEUR", "EUR"),
        ("CAD", "CAD"),
        ("USD", "USD"),
        ("CAD.HOLD", "CAD"),
        ("USD.HOLD", "USD"),
        ("CAD.F", "CAD"),
        ("USD.F", "USD"),
        ("usd.f", "USD"),
    ],
)
def test_fiat_variants_recognized(asset, expected):
    assert _fiat_currency(asset) == expected


@pytest.mark.parametrize("asset", ["XXBT", "XETH", "SOL", "ETH2.S", "DOT.S", "ZRX", "COTI"])
def test_crypto_codes_are_not_fiat(asset):
    # ZRX (0x) starts with Z but is a coin — the old prefix check dropped it.
    assert _fiat_currency(asset) is None


# ---- get_cash_cad sums every fiat code --------------------------------------

def _broker_with_balances(monkeypatch, balances: dict, usdcad: float | None = 1.35):
    broker = KrakenBroker()
    monkeypatch.setattr(type(broker), "_has_creds", property(lambda self: True))
    monkeypatch.setattr(broker, "_private", lambda method, data=None: dict(balances))
    monkeypatch.setattr(kraken_mod, "quote_to_cad_rate", lambda quote, timeout=15.0: usdcad)
    return broker


def test_cash_counts_hold_and_rewards_variants(monkeypatch):
    broker = _broker_with_balances(
        monkeypatch,
        {"ZCAD": "100.00", "CAD.HOLD": "250.00", "CAD.F": "50.00", "XXBT": "0.01"},
    )
    assert broker.get_cash_cad() == pytest.approx(400.0)


def test_cash_converts_usd_variants_at_fx(monkeypatch):
    broker = _broker_with_balances(
        monkeypatch, {"ZUSD": "100.00", "USD.HOLD": "200.00"}, usdcad=1.35
    )
    assert broker.get_cash_cad() == pytest.approx(300.0 * 1.35)


def test_cash_usd_falls_back_to_one_to_one_without_fx(monkeypatch):
    # No FX rate: USD counts 1:1 (understatement), other fiat is skipped.
    broker = _broker_with_balances(
        monkeypatch, {"ZUSD": "100.00", "ZEUR": "40.00"}, usdcad=None
    )
    assert broker.get_cash_cad() == pytest.approx(100.0)


def test_cash_ignores_coins_and_garbage(monkeypatch):
    broker = _broker_with_balances(
        monkeypatch, {"XXBT": "1.5", "SOL": "10", "ZCAD": "not-a-number", "CAD": "25.00"}
    )
    assert broker.get_cash_cad() == pytest.approx(25.0)


# ---- get_positions never lists fiat as a coin --------------------------------

def test_positions_skip_fiat_variants(monkeypatch):
    broker = _broker_with_balances(
        monkeypatch,
        {"ZCAD": "100.00", "CAD.HOLD": "250.00", "USD.F": "75.00", "ZUSD": "10.00"},
    )
    # No priceable request should even be attempted for fiat codes.
    monkeypatch.setattr(
        broker, "_ticker_full", lambda pair: (_ for _ in ()).throw(AssertionError(pair))
    )
    assert broker.get_positions() == []
