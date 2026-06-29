"""The CEO decision spine: sizing, hurdle, null-default, cost gate, trust.

Caps are percentages of portfolio value; PV=200 reproduces the original dollar
ceilings (0.20*200=40/trade, 0.05*200=10 event, 0.80*200=160 deployable).
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest

from boardroom.adaptive.calibration import CalibrationPosterior, seed_prior
from boardroom.ceo.engine import CEODecisionEngine
from boardroom.ceo.hurdle import excess_over_floor, risk_adjusted_score
from boardroom.ceo.sizing import conviction_size
from boardroom.config import RiskCaps
from boardroom.schemas import (
    ComputedSignals,
    DataSnapshot,
    DecisionKind,
    Division,
    Pitch,
    Venue,
)

PV = 200.0


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
    division=Division.DIRECTIONAL,
    venue=Venue.IBKR,
    expected_return=0.05,
    confidence=0.7,
    capital=30.0,
    max_loss=6.0,
    expected_cost=0.3,
    horizon=5.0,
) -> Pitch:
    snap = DataSnapshot(
        symbol="X", venue=venue, as_of=dt.datetime.now(dt.timezone.utc),
        age_seconds=10, is_fresh=True, rows=60, content_hash="h", source="test",
    )
    sig = ComputedSignals(
        features={"volatility": 0.02}, model_name="m", model_version="v0",
        expected_return=expected_return, win_probability=confidence,
        raw_confidence=confidence, horizon_days=horizon,
    )
    return Pitch(
        pitch_id=str(uuid.uuid4()), division=division, venue=venue, symbol="X",
        snapshot=snap, signals=sig, capital_required=capital, expected_return=expected_return,
        confidence=confidence, time_horizon_days=horizon, max_loss=max_loss, expected_cost=expected_cost,
    )


# ---- percent-based caps -----------------------------------------------------
def test_caps_scale_with_portfolio():
    caps = _caps()
    assert caps.per_trade_cad(200) == 40
    assert caps.per_trade_cad(2000) == 400  # same 20%, 10x the account
    assert caps.cap_for("event", 200) == 10
    assert caps.deployable_cad(200) == 160


# ---- sizing -----------------------------------------------------------------
def test_conviction_size_zero_on_no_edge():
    assert conviction_size(
        division=Division.DIRECTIONAL, edge=0.0, win_probability=0.7,
        risk_unit_fraction=0.2, caps=_caps(), deployed_cad=0.0, portfolio_value_cad=PV,
    ) == 0.0


def test_conviction_size_respects_per_trade_cap():
    size = conviction_size(
        division=Division.DIRECTIONAL, edge=0.5, win_probability=0.9,
        risk_unit_fraction=0.05, caps=_caps(), deployed_cad=0.0, portfolio_value_cad=PV, leash=1.0,
    )
    assert size <= _caps().per_trade_cad(PV)


def test_event_hard_cap_binds():
    size = conviction_size(
        division=Division.EVENT, edge=0.9, win_probability=0.9,
        risk_unit_fraction=0.05, caps=_caps(), deployed_cad=0.0, portfolio_value_cad=PV, leash=1.0,
    )
    assert size <= _caps().cap_for("event", PV)


def test_sizing_clamped_by_headroom():
    size = conviction_size(
        division=Division.DIRECTIONAL, edge=0.5, win_probability=0.9,
        risk_unit_fraction=0.05, caps=_caps(), deployed_cad=155.0, portfolio_value_cad=PV, leash=1.0,
    )
    assert size <= 5.0 + 1e-9


# ---- hurdle -----------------------------------------------------------------
def test_excess_over_floor():
    p = _pitch(expected_return=0.05)
    assert excess_over_floor(p, 0.01) == pytest.approx(0.04)


def test_risk_adjusted_score_negative_when_below_floor():
    p = _pitch(expected_return=0.005)
    assert risk_adjusted_score(p, 0.01) < 0


# ---- engine -----------------------------------------------------------------
def test_null_default_when_no_pitches():
    eng = CEODecisionEngine(caps=_caps())
    decision, ranked = eng.decide([], hurdle_rate=0.0001, portfolio_value_cad=PV)
    assert decision.kind == DecisionKind.HOLD
    assert ranked == []


def test_cost_gate_rejects_uneconomic_pitch():
    p = _pitch(expected_return=0.02, capital=30.0, expected_cost=5.0)
    eng = CEODecisionEngine(caps=_caps())
    decision, ranked = eng.decide([p], hurdle_rate=0.0001, portfolio_value_cad=PV)
    assert decision.kind in (DecisionKind.FUND_NONE, DecisionKind.HOLD)
    assert ranked[0].rejected_reason is not None


def test_strong_pitch_gets_funded():
    p = _pitch(expected_return=0.06, capital=30.0, max_loss=6.0, expected_cost=0.3, confidence=0.75)
    eng = CEODecisionEngine(
        caps=_caps(),
        posteriors={"directional": seed_prior(0.7)},
        leashes={"directional": 1.0},
        deviation_threshold=0.0,
    )
    decision, ranked = eng.decide([p], hurdle_rate=0.0002, deployed_cad=0.0, portfolio_value_cad=PV)
    assert decision.kind == DecisionKind.FUND
    assert decision.division == Division.DIRECTIONAL
    assert decision.size_cad > 0


def test_trust_discounts_overclaiming_division():
    poor = CalibrationPosterior("directional", alpha=4.0, beta=6.0)  # mean 0.4, n=8
    eng = CEODecisionEngine(caps=_caps(), posteriors={"directional": poor}, leashes={"directional": 1.0})
    p = _pitch(expected_return=0.06, confidence=0.9)
    _, ranked = eng.decide([p], hurdle_rate=0.0002, portfolio_value_cad=PV)
    assert ranked[0].trust < 0.9


# ---- aggression schedule: bolder while small, calmer as it grows ------------
def test_aggression_schedule_scales_the_bar_with_equity():
    eng = CEODecisionEngine(
        caps=_caps(),
        deviation_threshold=0.02,        # conservative (grown) bar
        deviation_threshold_low=0.005,   # aggressive (small-account) bar
        aggressive_below_cad=500.0,
        conservative_above_cad=5000.0,
    )
    assert eng._effective_threshold(200) == pytest.approx(0.005)    # small -> low bar
    assert eng._effective_threshold(500) == pytest.approx(0.005)    # at floor of the ramp
    assert eng._effective_threshold(5000) == pytest.approx(0.02)    # grown -> conservative
    assert eng._effective_threshold(50000) == pytest.approx(0.02)   # clamped above
    mid = eng._effective_threshold(2750)  # halfway up the ramp
    assert 0.005 < mid < 0.02


def test_no_schedule_keeps_the_fixed_bar():
    # Without deviation_threshold_low set, behaviour is the old fixed threshold.
    eng = CEODecisionEngine(caps=_caps())
    assert eng._effective_threshold(200) == pytest.approx(0.02)
    assert eng._effective_threshold(100000) == pytest.approx(0.02)
