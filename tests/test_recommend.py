"""The equities recommendation engine: ranking, weighting, and the holdings diff.

Stocks are advisory — these functions turn ranked pitches into a target book and
reconcile it against the actual IBKR holdings. Every number is code-computed.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest

from boardroom.agents.advisor import fallback_narrative
from boardroom.brokers.ibkr import IBKRBroker
from boardroom.brokers.stub import StubBroker
from boardroom.config import RiskCaps
from boardroom.recommend import (
    CurrentHolding,
    build_recommended_portfolio,
    diff_portfolio,
)
from boardroom.schemas import (
    ComputedSignals,
    DataSnapshot,
    Division,
    Pitch,
    Venue,
)


def _caps() -> RiskCaps:
    return RiskCaps(
        total_deployable_pct=0.80,
        per_trade_max_pct=0.20,
        event_hard_cap_pct=0.05,
        daily_loss_limit_pct=0.06,
        max_drawdown_pct=0.15,
        fee_drag_limit_pct=0.05,
    )


def _pitch(
    symbol="AAPL",
    venue=Venue.IBKR,
    division=Division.DIRECTIONAL,
    expected_return=0.06,
    confidence=0.7,
    capital=30.0,
    max_loss=6.0,
    expected_cost=0.3,
    price=100.0,
) -> Pitch:
    snap = DataSnapshot(
        symbol=symbol, venue=venue, as_of=dt.datetime.now(dt.timezone.utc),
        age_seconds=10, is_fresh=True, rows=60, content_hash="h", source="test",
    )
    sig = ComputedSignals(
        features={"price": price, "volatility": 0.02}, model_name="m", model_version="v0",
        expected_return=expected_return, win_probability=confidence,
        raw_confidence=confidence, horizon_days=5.0,
    )
    return Pitch(
        pitch_id=str(uuid.uuid4()), division=division, venue=venue, symbol=symbol,
        snapshot=snap, signals=sig, capital_required=capital, expected_return=expected_return,
        confidence=confidence, time_horizon_days=5.0, max_loss=max_loss, expected_cost=expected_cost,
    )


# ---- ranking & weighting ----------------------------------------------------
def test_recommends_only_equity_venue_survivors():
    pitches = [
        _pitch("AAPL", expected_return=0.08),
        _pitch("MSFT", expected_return=0.06),
        _pitch("XBTUSD", venue=Venue.KRAKEN, division=Division.EVENT, expected_return=0.20),  # crypto excluded
        _pitch("DUD", expected_return=0.0, expected_cost=5.0),  # fails the floor/cost → dropped
    ]
    recs = build_recommended_portfolio(
        pitches, hurdle_rate=0.0002, stock_equity_cad=1000.0, caps=_caps()
    )
    syms = [h.symbol for h in recs]
    assert "XBTUSD" not in syms  # crypto auto-trades, never recommended as a stock
    assert "DUD" not in syms
    assert syms[0] == "AAPL"  # strongest edge ranks first
    assert recs[0].rank == 1


def test_weights_capped_and_within_deployable():
    # One dominant name must still be capped at the per-trade ceiling (20%).
    pitches = [_pitch("AAPL", expected_return=0.50), _pitch("MSFT", expected_return=0.02)]
    recs = build_recommended_portfolio(
        pitches, hurdle_rate=0.0002, stock_equity_cad=1000.0, caps=_caps()
    )
    for h in recs:
        assert h.target_weight <= _caps().per_trade_max_pct + 1e-9
    assert sum(h.target_weight for h in recs) <= _caps().total_deployable_pct + 1e-9
    assert recs[0].target_cad == pytest.approx(recs[0].target_weight * 1000.0, abs=0.01)


def test_no_recommendations_when_nothing_beats_floor():
    pitches = [_pitch("AAPL", expected_return=0.0, expected_cost=10.0)]
    recs = build_recommended_portfolio(
        pitches, hurdle_rate=0.0002, stock_equity_cad=1000.0, caps=_caps()
    )
    assert recs == []


# ---- the holdings diff ------------------------------------------------------
def test_diff_buys_sells_and_holds():
    recs = build_recommended_portfolio(
        [_pitch("AAPL", expected_return=0.08), _pitch("MSFT", expected_return=0.06)],
        hurdle_rate=0.0002, stock_equity_cad=1000.0, caps=_caps(),
    )
    aapl_target = next(h.target_cad for h in recs if h.symbol == "AAPL")
    current = [
        CurrentHolding("AAPL", qty=1, avg_cost=90, market_value_cad=aapl_target),  # on target → hold
        CurrentHolding("SNDK", qty=5, avg_cost=50, market_value_cad=400.0),         # not recommended → sell
    ]
    actions = diff_portfolio(current, recs)
    by_sym = {a.symbol: a for a in actions}
    assert by_sym["SNDK"].action == "sell"
    assert by_sym["AAPL"].action == "hold"
    assert by_sym["MSFT"].action == "buy"  # recommended, not held
    # Sells are surfaced first.
    assert actions[0].action == "sell"


def test_diff_trim_when_overweight():
    recs = build_recommended_portfolio(
        [_pitch("AAPL", expected_return=0.08)], hurdle_rate=0.0002,
        stock_equity_cad=1000.0, caps=_caps(),
    )
    target = recs[0].target_cad
    current = [CurrentHolding("AAPL", qty=10, avg_cost=90, market_value_cad=target * 3)]
    actions = diff_portfolio(current, recs)
    assert actions[0].action == "trim"
    assert actions[0].delta_cad < 0


# ---- advisor fallback -------------------------------------------------------
def test_fallback_narrative_names_tickers():
    recs = build_recommended_portfolio(
        [_pitch("AAPL", expected_return=0.08)], hurdle_rate=0.0002,
        stock_equity_cad=1000.0, caps=_caps(),
    )
    current = [CurrentHolding("SNDK", qty=5, avg_cost=50, market_value_cad=400.0)]
    actions = diff_portfolio(current, recs)
    note = fallback_narrative(actions, recs, current)
    assert "SNDK" in note and "AAPL" in note


def test_fallback_narrative_empty_is_graceful():
    note = fallback_narrative([], [], [])
    assert "No stock recommendations" in note


# ---- broker positions -------------------------------------------------------
def test_stub_broker_has_no_positions():
    assert StubBroker(Venue.IBKR).get_positions() == []


def test_ibkr_positions_empty_without_account():
    # No account id configured (test env strips creds) → no positions, no crash.
    assert IBKRBroker().get_positions() == []
