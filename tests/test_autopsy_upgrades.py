"""Trade-autopsy upgrades (owner mandate 2026-08-05, "make it go BOOM"):

The one-time read of every resolved trade showed: horizon exits +$27 / stops
-$68 (evaluated only at checkpoints, so gaps blow through the 6% cap), repeat
winners (KAITO 7/7 +$43) vs repeat losers (TRU 0/4 -$23) with no per-asset
memory, and every crash ever being a transient network failure. Hence:
per-asset score tilts, network retries, and denser checkpoints.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest

from boardroom.ceo.engine import CEODecisionEngine, DecisionKind, _base_of
from boardroom.config import RiskCaps, Settings
from boardroom.persistence.repository import InMemoryRepository
from boardroom.schemas import Division, ResolvedOutcome, Venue

from boardroom.schemas import ComputedSignals, DataSnapshot, Pitch


def _pitch(*, division, venue, symbol, expected_return, capital, max_loss,
           expected_cost, confidence) -> Pitch:
    snap = DataSnapshot(
        symbol=symbol, venue=venue, as_of=dt.datetime.now(dt.timezone.utc),
        age_seconds=10, is_fresh=True, rows=60, content_hash="h", source="test",
    )
    sig = ComputedSignals(
        features={"volatility": 0.02}, model_name="m", model_version="v0",
        expected_return=expected_return, win_probability=confidence,
        raw_confidence=confidence, horizon_days=5.0,
    )
    return Pitch(
        pitch_id=str(uuid.uuid4()), division=division, venue=venue, symbol=symbol,
        snapshot=snap, signals=sig, capital_required=capital,
        expected_return=expected_return, confidence=confidence, time_horizon_days=5.0,
        max_loss=max_loss, expected_cost=expected_cost,
    )


def _caps() -> RiskCaps:
    return RiskCaps(
        total_deployable_pct=0.80, per_trade_max_pct=0.20, event_hard_cap_pct=0.05,
        daily_loss_limit_pct=0.06, max_drawdown_pct=0.15, fee_drag_limit_pct=0.05,
    )


def test_base_of_strips_quotes():
    assert _base_of("KAITOUSD") == "KAITO"
    assert _base_of("SOLCAD") == "SOL"
    assert _base_of("XBTUSDT") == "XBT"


def test_proven_winner_outranks_proven_loser():
    winner = _pitch(
        division=Division.CRYPTO_TREND, venue=Venue.KRAKEN, symbol="KAITOUSD",
        expected_return=0.05, capital=30.0, max_loss=2.0, expected_cost=0.02, confidence=0.7,
    )
    loser = _pitch(
        division=Division.CRYPTO_TREND, venue=Venue.KRAKEN, symbol="TRUUSD",
        expected_return=0.05, capital=30.0, max_loss=2.0, expected_cost=0.02, confidence=0.7,
    )
    eng = CEODecisionEngine(
        caps=_caps(), deviation_threshold=0.0,
        symbol_tilts={"KAITO": 0.6, "TRU": -0.6},
    )
    decision, ranked = eng.decide(
        [loser, winner], hurdle_rate=0.0002, deployed_cad=0.0, portfolio_value_cad=676.0
    )
    assert decision.kind == DecisionKind.FUND
    assert decision.pitch_id == winner.pitch_id          # identical signals — record breaks the tie
    assert ranked[0].pitch.symbol == "KAITOUSD"
    assert ranked[0].score > ranked[1].score * 2         # 1.6x vs 0.4x multiplier


def test_tilt_never_flips_a_positive_score_negative():
    p = _pitch(
        division=Division.CRYPTO_TREND, venue=Venue.KRAKEN, symbol="TRUUSD",
        expected_return=0.05, capital=30.0, max_loss=2.0, expected_cost=0.02, confidence=0.7,
    )
    eng = CEODecisionEngine(caps=_caps(), deviation_threshold=0.0, symbol_tilts={"TRU": -0.6})
    decision, ranked = eng.decide([p], hurdle_rate=0.0002, deployed_cad=0.0, portfolio_value_cad=676.0)
    assert ranked[0].score > 0        # demoted, not banned
    assert decision.kind == DecisionKind.FUND  # alone in the queue, it still funds


def _outcome(symbol: str, pnl: float) -> ResolvedOutcome:
    return ResolvedOutcome(
        decision_id=str(uuid.uuid4()), division=Division.CRYPTO_TREND, symbol=symbol,
        resolved_at=dt.datetime.now(dt.timezone.utc), predicted_return=0.05,
        realized_return=pnl / 25.0, predicted_confidence=0.7, win=pnl > 0,
        pnl_cad=pnl, cost_cad=0.1, inside_band=True,
    )


def test_loader_builds_bounded_tilts_from_outcomes():
    from boardroom.factory import build_default_org

    repo = InMemoryRepository()
    for _ in range(3):
        repo.save_outcome(_outcome("KAITOUSD", 15.0))   # net +44.7 -> clamped +0.6
    for _ in range(2):
        repo.save_outcome(_outcome("TRUUSD", -6.0))     # net -12.2 -> -0.488
    repo.save_outcome(_outcome("ZECUSD", -1.0))         # single sample -> no tilt

    org = build_default_org(data_mode="synthetic", repo=repo)
    org.load_adaptive_state()
    tilts = org.engine.symbol_tilts
    assert tilts["KAITO"] == pytest.approx(0.6)
    assert tilts["TRU"] == pytest.approx(-0.488)
    assert "ZEC" not in tilts


def test_autopsy_defaults():
    s = Settings(_env_file=None)
    assert s.min_order_pct == pytest.approx(0.40)
    assert s.max_fundings_per_checkpoint == 3
    assert s.exit_tp_r_multiple == pytest.approx(1.25)
    assert s.rotation_edge_multiple == pytest.approx(2.0)
    assert len(s.checkpoint_times.split(",")) == 8      # every 3 hours


# ---- volatility tilt: spot's honest substitute for leverage ------------------

def _vol_pitch(symbol: str, vol: float):
    p = _pitch(
        division=Division.CRYPTO_TREND, venue=Venue.KRAKEN, symbol=symbol,
        expected_return=0.05, capital=30.0, max_loss=2.0, expected_cost=0.02, confidence=0.7,
    )
    p.signals.features["volatility"] = vol
    return p


def test_wildest_mover_wins_at_equal_edge():
    calm = _vol_pitch("XBTUSD", 0.02)    # majors-grade 2% daily vol
    wild = _vol_pitch("PEPEUSD", 0.12)   # meme-grade 12% daily vol
    eng = CEODecisionEngine(
        caps=_caps(), deviation_threshold=0.0,
        vol_tilt_strength=0.5, vol_tilt_ref=0.05,
    )
    decision, ranked = eng.decide(
        [calm, wild], hurdle_rate=0.0002, deployed_cad=0.0, portfolio_value_cad=676.0
    )
    assert decision.pitch_id == wild.pitch_id
    assert ranked[0].pitch.symbol == "PEPEUSD"
    # wild multiplier capped at 1 + 0.5*2.0 = 2.0x; calm gets 1 + 0.5*0.4 = 1.2x
    assert ranked[0].score / ranked[1].score == pytest.approx(2.0 / 1.2, rel=1e-6)


def test_vol_tilt_disabled_is_neutral():
    calm = _vol_pitch("XBTUSD", 0.02)
    wild = _vol_pitch("PEPEUSD", 0.12)
    eng = CEODecisionEngine(caps=_caps(), deviation_threshold=0.0, vol_tilt_strength=0.0)
    _, ranked = eng.decide(
        [calm, wild], hurdle_rate=0.0002, deployed_cad=0.0, portfolio_value_cad=676.0
    )
    assert ranked[0].score == pytest.approx(ranked[1].score)


def test_vol_tilt_never_rescues_a_gated_pitch():
    # A pitch that fails the cost gate stays dead no matter how wild the coin.
    p = _vol_pitch("PEPEUSD", 0.20)
    p.expected_cost = 100.0  # cost gate kills it
    eng = CEODecisionEngine(caps=_caps(), deviation_threshold=0.0, vol_tilt_strength=0.5)
    decision, ranked = eng.decide([p], hurdle_rate=0.0002, deployed_cad=0.0, portfolio_value_cad=676.0)
    assert ranked[0].score <= 0
    assert decision.kind != DecisionKind.FUND


def test_vol_tilt_defaults_on():
    s = Settings(_env_file=None)
    assert s.vol_tilt_strength == pytest.approx(0.5)
    assert s.vol_tilt_ref == pytest.approx(0.05)
