"""The CEO decision spine: sizing, hurdle, null-default, cost gate, trust."""

from __future__ import annotations

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
    Decision,
    DecisionKind,
    Division,
    Pitch,
    Venue,
)


def _caps() -> RiskCaps:
    return RiskCaps(
        total_deployable_cad=160,
        per_trade_max_cad=40,
        event_hard_cap_cad=10,
        daily_loss_limit_cad=12,
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
        symbol="X", venue=venue, as_of=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
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


# ---- sizing -----------------------------------------------------------------
def test_conviction_size_zero_on_no_edge():
    assert conviction_size(
        division=Division.DIRECTIONAL, edge=0.0, win_probability=0.7,
        risk_unit_fraction=0.2, caps=_caps(), deployed_cad=0.0,
    ) == 0.0


def test_conviction_size_respects_per_trade_cap():
    size = conviction_size(
        division=Division.DIRECTIONAL, edge=0.5, win_probability=0.9,
        risk_unit_fraction=0.05, caps=_caps(), deployed_cad=0.0, leash=1.0,
    )
    assert size <= _caps().per_trade_max_cad


def test_event_hard_cap_binds():
    size = conviction_size(
        division=Division.EVENT, edge=0.9, win_probability=0.9,
        risk_unit_fraction=0.05, caps=_caps(), deployed_cad=0.0, leash=1.0,
    )
    assert size <= _caps().event_hard_cap_cad


def test_sizing_clamped_by_headroom():
    size = conviction_size(
        division=Division.DIRECTIONAL, edge=0.5, win_probability=0.9,
        risk_unit_fraction=0.05, caps=_caps(), deployed_cad=155.0, leash=1.0,
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
    decision, ranked = eng.decide([], hurdle_rate=0.0001)
    assert decision.kind == DecisionKind.HOLD
    assert ranked == []


def test_cost_gate_rejects_uneconomic_pitch():
    # edge in CAD = 30 * 0.02 = 0.6; cost 5.0 -> fails cost gate
    p = _pitch(expected_return=0.02, capital=30.0, expected_cost=5.0)
    eng = CEODecisionEngine(caps=_caps())
    decision, ranked = eng.decide([p], hurdle_rate=0.0001)
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
    decision, ranked = eng.decide([p], hurdle_rate=0.0002, deployed_cad=0.0)
    assert decision.kind == DecisionKind.FUND
    assert decision.division == Division.DIRECTIONAL
    assert decision.size_cad > 0


def test_trust_discounts_overclaiming_division():
    # A division that says 0.9 but is demonstrated to hit ~0.4 should be distrusted.
    poor = CalibrationPosterior("directional", alpha=4.0, beta=6.0)  # mean 0.4, n=8
    eng = CEODecisionEngine(caps=_caps(), posteriors={"directional": poor}, leashes={"directional": 1.0})
    p = _pitch(expected_return=0.06, confidence=0.9)
    _, ranked = eng.decide([p], hurdle_rate=0.0002)
    assert ranked[0].trust < 0.9
