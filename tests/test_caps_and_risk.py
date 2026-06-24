"""Hard caps (percent of portfolio), circuit breakers, and the risk manager."""

from __future__ import annotations

import datetime as dt
import uuid

from boardroom.config import RiskCaps
from boardroom.risk.caps import PortfolioState, circuit_breaker_tripped, clamp_size
from boardroom.risk.cost import CostModel
from boardroom.schemas import ComputedSignals, DataSnapshot, Division, Pitch, Venue

PV = 200.0


def _caps() -> RiskCaps:
    # 0.80 / 0.20 / 0.05 / 0.06 -> at PV=200: 160 / 40 / 10 / 12 CAD.
    return RiskCaps(0.80, 0.20, 0.05, 0.06, 0.15, 0.05)


def test_clamp_size_per_trade():
    v = clamp_size(division=Division.DIRECTIONAL, requested_cad=100, caps=_caps(), deployed_cad=0, portfolio_value_cad=PV)
    assert v.clamped_size_cad == 40
    assert any("per-trade" in r for r in v.reasons)


def test_clamp_size_event_hard_cap():
    v = clamp_size(division=Division.EVENT, requested_cad=100, caps=_caps(), deployed_cad=0, portfolio_value_cad=PV)
    assert v.clamped_size_cad == 10


def test_clamp_size_headroom():
    v = clamp_size(division=Division.DIRECTIONAL, requested_cad=40, caps=_caps(), deployed_cad=150, portfolio_value_cad=PV)
    assert v.clamped_size_cad == 10


def test_caps_scale_up():
    # Same percentages, 10x portfolio -> 10x the dollar ceilings.
    v = clamp_size(division=Division.DIRECTIONAL, requested_cad=10_000, caps=_caps(), deployed_cad=0, portfolio_value_cad=2000)
    assert v.clamped_size_cad == 400


def test_circuit_breaker_daily_loss():
    # daily limit = 6% of equity = 0.06*190 = 11.4; loss of 13 trips it.
    state = PortfolioState(equity_cad=190, peak_equity_cad=200, realized_pnl_today_cad=-13,
                           cumulative_cost_cad=0, cumulative_gross_return_cad=0)
    assert any("daily loss" in r for r in circuit_breaker_tripped(state, _caps()))


def test_circuit_breaker_drawdown():
    state = PortfolioState(equity_cad=160, peak_equity_cad=200, realized_pnl_today_cad=0,
                           cumulative_cost_cad=0, cumulative_gross_return_cad=0)
    assert any("drawdown" in r for r in circuit_breaker_tripped(state, _caps()))


def test_circuit_breaker_all_clear():
    state = PortfolioState(equity_cad=199, peak_equity_cad=200, realized_pnl_today_cad=-1,
                           cumulative_cost_cad=1, cumulative_gross_return_cad=100)
    assert circuit_breaker_tripped(state, _caps()) == []


def test_cost_model_pessimistic_round_trip():
    cm = CostModel()
    kr = cm.round_trip_cost_cad(venue=Venue.KRAKEN, notional_cad=40, needs_fx=False)
    ib = cm.round_trip_cost_cad(venue=Venue.IBKR, notional_cad=40, needs_fx=True)
    assert kr > 0 and ib > 0
    assert kr > ib


def _pitch(max_loss=6.0, expected_cost=0.3, capital=30.0, expected_return=0.05, liq=None) -> Pitch:
    feats = {"volatility": 0.02}
    if liq is not None:
        feats["liquidity"] = liq
    snap = DataSnapshot(symbol="X", venue=Venue.IBKR, as_of=dt.datetime.now(dt.timezone.utc),
                        age_seconds=10, is_fresh=True, rows=60, content_hash="h", source="t")
    sig = ComputedSignals(features=feats, model_name="m", model_version="v0",
                          expected_return=expected_return, win_probability=0.7, raw_confidence=0.7, horizon_days=5)
    return Pitch(pitch_id=str(uuid.uuid4()), division=Division.DIRECTIONAL, venue=Venue.IBKR, symbol="X",
                 snapshot=snap, signals=sig, capital_required=capital, expected_return=expected_return,
                 confidence=0.7, time_horizon_days=5, max_loss=max_loss, expected_cost=expected_cost)


def test_risk_manager_vetoes_on_cost():
    from boardroom.agents.risk_manager import RiskManager

    rm = RiskManager(caps=_caps())
    ch = rm.challenge(_pitch(expected_return=0.001, capital=30, expected_cost=5.0), PV)
    assert ch.approved is False
    assert ch.hard_objections


def test_risk_manager_vetoes_low_liquidity():
    from boardroom.agents.risk_manager import RiskManager

    rm = RiskManager(caps=_caps())
    ch = rm.challenge(_pitch(liq=1000.0), PV)
    assert ch.approved is False


def test_risk_manager_approves_clean_pitch():
    from boardroom.agents.risk_manager import RiskManager

    rm = RiskManager(caps=_caps())
    ch = rm.challenge(_pitch(max_loss=4.0, expected_cost=0.3, capital=30, expected_return=0.05, liq=1e7), PV)
    assert ch.approved is True
