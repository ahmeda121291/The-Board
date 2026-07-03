"""Executability gate + funding-currency FX: a coin with no market in the
account's quote currency never eats a funding slot (UNIUSD burned three before
the gate existed), and a non-CAD-funded account sizes orders through a live FX
rate — never at 1:1."""

from __future__ import annotations

import datetime as dt
import uuid

from boardroom.brokers.base import Order, OrderSide
from boardroom.brokers.kraken import KrakenBroker, exec_pair_for, quote_to_cad_rate
from boardroom.config import Settings
from boardroom.factory import build_default_org
from boardroom.persistence.repository import InMemoryRepository
from boardroom.schemas import ComputedSignals, DataSnapshot, Division, Pitch, Venue

CAD_PAIRS = frozenset({"XBTCAD", "ETHCAD", "SOLCAD", "XRPCAD", "PEPECAD"})
USD_PAIRS = frozenset({"XBTUSD", "ETHUSD", "SOLUSD", "XRPUSD", "UNIUSD", "ADAUSD"})


def _pitch(symbol: str, er: float = 0.05, capital: float = 20.0) -> Pitch:
    snap = DataSnapshot(
        symbol=symbol, venue=Venue.KRAKEN, as_of=dt.datetime.now(dt.timezone.utc),
        age_seconds=10, is_fresh=True, rows=60, content_hash="h", source="test",
    )
    sig = ComputedSignals(
        features={"volatility": 0.02}, model_name="m", model_version="v0",
        expected_return=er, win_probability=0.7, raw_confidence=0.7, horizon_days=5.0,
    )
    return Pitch(
        pitch_id=str(uuid.uuid4()), division=Division.EVENT, venue=Venue.KRAKEN,
        symbol=symbol, snapshot=snap, signals=sig, capital_required=capital,
        expected_return=er, confidence=0.7, time_horizon_days=5.0,
        max_loss=capital * 0.06, expected_cost=0.1,
    )


def _org(repo, pitches, exec_pair_lookup, **settings_kwargs):
    org = build_default_org(
        data_mode="synthetic",
        repo=repo,
        settings=Settings(_env_file=None, **settings_kwargs),
        exec_pair_lookup=exec_pair_lookup,
    )
    org.gather_pitches = lambda pv: list(pitches)
    org.risk_review = lambda ps, pv: (list(ps), {})
    return org


def test_exec_pair_translation():
    assert exec_pair_for("UNIUSD") == "UNICAD"
    assert exec_pair_for("XBTUSD") == "XBTCAD"
    assert exec_pair_for("SOLCAD") == "SOLCAD"   # already correct: unchanged
    # USD-funded account: USD signal pairs execute as-is; stablecoin quotes map.
    assert exec_pair_for("XBTUSD", "USD") == "XBTUSD"
    assert exec_pair_for("PEPEUSDT", "USD") == "PEPEUSD"


def test_no_exec_market_never_eats_a_funding_slot():
    repo = InMemoryRepository()
    # UNI has the better edge but no CAD market; SOL is executable.
    uni, sol = _pitch("UNIUSD", er=0.09), _pitch("SOLUSD", er=0.05)
    org = _org(repo, [uni, sol], exec_pair_lookup=lambda: CAD_PAIRS)
    result = org.run_once(portfolio_value_cad=200.0)

    assert result.decision.kind.value == "fund"
    assert result.decision.pitch_id == sol.pitch_id, "the slot goes to the executable coin"

    skips = [p for e, p in repo.audit_log if e == "no_exec_market_skip"]
    assert len(skips) == 1
    assert skips[0]["symbol"] == "UNIUSD" and skips[0]["exec_pair"] == "UNICAD"
    assert skips[0]["quote"] == "CAD"

    # The session tells the human WHY the better-scoring idea wasn't funded.
    _, session = repo.decisions[0]
    uni_row = next(r for r in session["pitches"] if r["symbol"] == "UNIUSD")
    assert uni_row["status"] == "passed"
    assert "no CAD market" in uni_row["reason"]


def test_usd_funded_account_can_buy_the_whole_usd_universe():
    # Same UNI pitch, but the account is USD-funded: UNIUSD executes as-is.
    repo = InMemoryRepository()
    uni = _pitch("UNIUSD", er=0.09)
    org = _org(
        repo, [uni],
        exec_pair_lookup=lambda: USD_PAIRS,
        ACCOUNT_BASE_CURRENCY="USD",
    )
    result = org.run_once(portfolio_value_cad=200.0)

    assert result.decision.pitch_id == uni.pitch_id
    assert not [e for e, _ in repo.audit_log if e == "no_exec_market_skip"]


def test_gate_fails_open_when_lookup_unavailable():
    # Lookup returns None (Kraken API down) -> no filtering, execution still
    # errors cleanly downstream, exactly the pre-gate behavior.
    repo = InMemoryRepository()
    uni = _pitch("UNIUSD", er=0.09)
    org = _org(repo, [uni], exec_pair_lookup=lambda: None)
    result = org.run_once(portfolio_value_cad=200.0)

    assert result.decision.pitch_id == uni.pitch_id  # still funded (stub broker fills)
    assert not [e for e, _ in repo.audit_log if e == "no_exec_market_skip"]


def test_gate_absent_in_synthetic_mode_by_default():
    org = build_default_org(data_mode="synthetic", repo=InMemoryRepository())
    assert org.exec_pair_lookup is None, "synthetic/test runs must never touch the network"


# ---- funding-currency FX at the broker boundary --------------------------------

def test_cad_rate_is_identity_without_network():
    assert quote_to_cad_rate("CAD") == 1.0
    assert quote_to_cad_rate("cad") == 1.0


def test_usd_order_sizes_through_the_fx_rate(monkeypatch):
    """A $25 CAD intent on a USD-funded account must buy 25/rate USD of coin —
    sizing at 1:1 would silently breach the CAD caps by ~37%."""
    kb = KrakenBroker()
    kb._quote_currency = "USD"
    monkeypatch.setattr(type(kb), "_has_creds", property(lambda self: True))
    monkeypatch.setattr(kb._settings, "live_trading", True)
    monkeypatch.setattr(kb, "_ticker_price", lambda pair: 100.0)  # USD price
    monkeypatch.setattr(
        "boardroom.brokers.kraken.quote_to_cad_rate", lambda q, **k: 1.25
    )
    sent = {}
    monkeypatch.setattr(kb, "_private", lambda method, data: sent.update(data) or {"txid": ["T"]})

    order = Order(
        symbol="UNIUSD", side=OrderSide.BUY, notional_cad=25.0,
        division="event", client_order_id=str(uuid.uuid4()),
    )
    fill = kb.place_order(order, live=True)

    assert sent["pair"] == "UNIUSD"
    # 25 CAD -> 20 USD at 1.25, at $100/coin -> 0.2 coins (NOT 0.25).
    assert abs(float(sent["volume"]) - 0.2) < 1e-9
    assert fill.is_live


def test_usd_order_refuses_to_size_without_fx_rate(monkeypatch):
    kb = KrakenBroker()
    kb._quote_currency = "USD"
    monkeypatch.setattr(type(kb), "_has_creds", property(lambda self: True))
    monkeypatch.setattr(kb._settings, "live_trading", True)
    monkeypatch.setattr(kb, "_ticker_price", lambda pair: 100.0)
    monkeypatch.setattr(
        "boardroom.brokers.kraken.quote_to_cad_rate", lambda q, **k: None
    )
    order = Order(
        symbol="XBTUSD", side=OrderSide.BUY, notional_cad=25.0,
        division="event", client_order_id=str(uuid.uuid4()),
    )
    try:
        kb.place_order(order, live=True)
        raise AssertionError("expected a refusal without an FX rate")
    except RuntimeError as e:
        assert "FX rate" in str(e)


def test_cash_counts_both_fiats_in_cad(monkeypatch):
    kb = KrakenBroker()
    monkeypatch.setattr(type(kb), "_has_creds", property(lambda self: True))
    monkeypatch.setattr(kb, "_private", lambda m, d=None: {"ZCAD": "10.0", "ZUSD": "100.0"})
    monkeypatch.setattr(
        "boardroom.brokers.kraken.quote_to_cad_rate", lambda q, **k: 1.35
    )
    assert abs(kb.get_cash_cad() - 145.0) < 1e-9  # 10 + 100 * 1.35