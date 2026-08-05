"""The resolve→learn loop: positions resolve correctly and feed the adaptive engine.

These tests prove the transmission that makes the system self-improve actually
turns — outcomes resolve off real prices, net-of-cost, and update calibration,
leash, and retirement through the existing guardrails.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from boardroom.graph.resolution_loop import (
    build_open_position,
    resolve_open_positions,
    resolve_position,
)
from boardroom.persistence.repository import InMemoryRepository, OpenPosition
from boardroom.schemas import (
    ComputedSignals,
    DataSnapshot,
    Decision,
    DecisionKind,
    Division,
    Pitch,
    Venue,
)

_BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _bars(closes: list[float]) -> "object":
    from boardroom.data.snapshot import Bars

    n = len(closes)
    times = pd.to_datetime([_BASE + timedelta(days=i) for i in range(n)], utc=True)
    df = pd.DataFrame(
        {
            "time": times,
            "open": closes,
            "high": [c * 1.02 for c in closes],
            "low": [c * 0.98 for c in closes],
            "close": closes,
            "volume": [1e6] * n,
        }
    )
    return Bars(symbol="SPY", venue=Venue.KRAKEN, df=df, source="test")


def _pos(**overrides) -> OpenPosition:
    base = dict(
        decision_id="d1",
        division="directional",
        venue="ibkr",
        symbol="SPY",
        size_cad=40.0,
        predicted_return=0.02,
        predicted_confidence=0.6,
        cost_cad=0.40,            # 1% of size
        stop_fraction=0.10,
        band_low=-0.20,
        band_high=0.20,
        horizon_days=3.0,
        opened_at=_BASE,
        live=False,
    )
    base.update(overrides)
    return OpenPosition(**base)


# --------------------------------------------------------------------------- #
# resolve_position
# --------------------------------------------------------------------------- #
def test_not_resolved_before_horizon():
    pos = _pos(horizon_days=10.0)
    bars = _bars([100.0, 101.0, 102.0, 103.0])  # only 3 days elapsed, no stop
    assert resolve_position(pos, bars) is None


def test_resolves_at_horizon_as_win():
    pos = _pos()
    bars = _bars([100.0, 101.0, 102.0, 105.0, 106.0, 107.0])  # +7% by the end
    out = resolve_position(pos, bars)
    assert out is not None
    assert out.realized_return == pytest.approx(0.07)
    assert out.win is True                       # 7% gain - 1% cost > 0
    assert out.pnl_cad == pytest.approx(40.0 * 0.07)
    assert out.inside_band is True


def test_stop_out_resolves_early_as_loss():
    pos = _pos(horizon_days=30.0)  # well before horizon
    bars = _bars([100.0, 98.0, 88.0, 95.0])  # -12% breaches the 10% stop on day 2
    out = resolve_position(pos, bars)
    assert out is not None
    assert out.realized_return == pytest.approx(-0.12)
    assert out.win is False
    assert out.pnl_cad == pytest.approx(40.0 * -0.12)


def test_small_gain_below_cost_is_a_loss():
    # Net-of-cost semantics: a +0.5% move doesn't clear the 1% round-trip cost.
    pos = _pos()
    bars = _bars([100.0, 100.1, 100.2, 100.5, 100.5, 100.5])
    out = resolve_position(pos, bars)
    assert out is not None
    assert out.realized_return == pytest.approx(0.005)
    assert out.win is False


def test_realized_outside_band_flags_process():
    pos = _pos(band_low=-0.01, band_high=0.01)
    # Arms the trail at +1%, rides to +6%, and the pullback close exits at -5%
    # — far outside the ±1% predicted band.
    bars = _bars([100.0, 101.0, 102.0, 105.0, 106.0, 95.0])
    out = resolve_position(pos, bars)
    assert out is not None
    assert out.inside_band is False  # landed well outside the predicted band


# --------------------------------------------------------------------------- #
# build_open_position
# --------------------------------------------------------------------------- #
def test_build_open_position_recovers_stop_and_band():
    snap = DataSnapshot(
        symbol="SPY", venue=Venue.IBKR, as_of=_BASE, age_seconds=0.0,
        is_fresh=True, rows=60, content_hash="x", source="test",
    )
    signals = ComputedSignals(
        features={"volatility": 0.02}, model_name="m", model_version="v",
        expected_return=0.03, win_probability=0.6, raw_confidence=0.4, horizon_days=5.0,
    )
    pitch = Pitch(
        pitch_id="p1", division=Division.DIRECTIONAL, venue=Venue.IBKR, symbol="SPY",
        snapshot=snap, signals=signals, capital_required=40.0, expected_return=0.03,
        confidence=0.6, time_horizon_days=5.0, max_loss=4.4, expected_cost=0.4,
    )
    decision = Decision(
        decision_id="d9", kind=DecisionKind.FUND, division=Division.DIRECTIONAL,
        pitch_id="p1", size_cad=40.0,
    )
    pos = build_open_position(pitch, decision)
    # raw stop = (max_loss - cost) / capital = (4.4 - 0.4) / 40 = 0.10, at the
    # lotto-mandate EXIT_STOP_CAP_PCT (10%); the trail arms at 1.25R.
    assert pos.stop_fraction == pytest.approx(0.10)
    assert pos.take_profit == pytest.approx(0.125)
    # band = expected_return ± 2 * vol * sqrt(horizon) — Critic window unchanged
    half = 2.0 * 0.02 * (5.0 ** 0.5)
    assert pos.band_low == pytest.approx(0.03 - half)
    assert pos.band_high == pytest.approx(0.03 + half)
    assert pos.opened_at == decision.created_at


# --------------------------------------------------------------------------- #
# resolve_open_positions — end to end into the adaptive engine
# --------------------------------------------------------------------------- #
def test_resolution_loop_updates_calibration_and_closes_position():
    repo = InMemoryRepository()
    repo.save_open_position(_pos(decision_id="win1"))
    bars = _bars([100.0, 101.0, 102.0, 105.0, 106.0, 107.0])  # a clear win

    updates = resolve_open_positions(repo, lambda pos: bars)

    assert len(updates) == 1
    assert repo.open_positions() == []                 # position closed
    assert len(repo.recent_outcomes()) == 1            # outcome persisted
    state = repo.get_division_state("directional")
    assert state.n_resolved == 1
    assert state.alpha == 2.0                           # one win advanced the posterior
    assert updates[0].posterior_mean > 0.5


def test_resolution_loop_skips_unready_and_handles_fetch_failure():
    repo = InMemoryRepository()
    repo.save_open_position(_pos(decision_id="young", horizon_days=30.0))
    # Not enough elapsed time -> stays open; a fetch failure must not crash.
    bars = _bars([100.0, 100.5, 101.0])

    def flaky(pos):
        if pos.decision_id == "boom":
            raise RuntimeError("feed down")
        return bars

    repo.save_open_position(_pos(decision_id="boom"))
    updates = resolve_open_positions(repo, flaky)

    assert updates == []                               # neither resolved
    assert len(repo.open_positions()) == 2             # both still open


# ---- fallback pricing: a HELD coin that left the scanned universe -------------------

def test_resolution_fallback_prices_position_outside_universe():
    """Six coins (AXS, BLUR, DRV, PYTH, SYRUP, TRU) churned out of the dynamic
    universe on 2026-07-26 and their positions sat unmanaged — no division
    fetcher covered them, so stops/take-profit/horizon never evaluated. The
    orchestrator must fall back to fetching a held symbol's series directly."""
    from boardroom.data.snapshot import Bars
    from boardroom.factory import build_default_org

    now = datetime.now(timezone.utc)
    times = pd.to_datetime([now - timedelta(days=15 - i) for i in range(16)], utc=True)
    closes = [100.0] * 15 + [110.0]
    df = pd.DataFrame(
        {"time": times, "open": closes, "high": closes, "low": closes,
         "close": closes, "volume": [1e6] * 16}
    )
    axs_bars = Bars(symbol="AXSUSD", venue=Venue.KRAKEN, df=df, source="test")

    fetched: list[str] = []

    def fallback(sym: str) -> Bars:
        fetched.append(sym)
        if sym != "AXSUSD":
            raise RuntimeError(f"no series for {sym}")
        return axs_bars

    repo = InMemoryRepository()
    repo.save_open_position(
        OpenPosition(
            decision_id=str(__import__("uuid").uuid4()), division="crypto_trend",
            venue="kraken", symbol="AXSUSD", size_cad=25.0, predicted_return=0.02,
            predicted_confidence=0.6, cost_cad=0.1, stop_fraction=0.5, band_low=-1.0,
            band_high=5.0, horizon_days=5.0, opened_at=now - timedelta(days=10),
            live=False,  # paper — resolves without a real sell
        )
    )
    org = build_default_org(data_mode="synthetic", repo=repo)
    assert org.resolution_fallback_fetch is None, "synthetic mode must stay offline"
    org.resolution_fallback_fetch = fallback

    org.resolve_positions()

    assert "AXSUSD" in fetched, "the held symbol must be fetched directly"
    assert repo.open_positions() == [], "the past-horizon position must resolve"
    assert len(repo.outcomes) == 1
    assert not any(e == "resolution_no_data" for e, _ in repo.audit_log)


# ---- exit asymmetry fix: capped stop + R-multiple take-profit -----------------------

def _pitch_for_exit(max_loss=5.0, cost=0.25, capital=25.0, expected=0.08, vol=0.05):
    snap = DataSnapshot(
        symbol="ETHUSD", venue=Venue.KRAKEN, as_of=datetime.now(timezone.utc),
        age_seconds=5, is_fresh=True, rows=90, content_hash="x", source="test",
    )
    sig = ComputedSignals(
        features={"volatility": vol}, model_name="m", model_version="v",
        expected_return=expected, win_probability=0.6, raw_confidence=0.6, horizon_days=5.0,
    )
    return Pitch(
        pitch_id="p-exit", division=Division.EVENT, venue=Venue.KRAKEN, symbol="ETHUSD",
        snapshot=snap, signals=sig, capital_required=capital, expected_return=expected,
        confidence=0.6, time_horizon_days=5.0, max_loss=max_loss, expected_cost=cost,
    )


def test_stop_is_capped_and_tp_is_r_multiple():
    # Raw stop would be (5.0-0.25)/25 = 19% — the old deep-stop shape. It must
    # cap at the lotto-mandate 10% with the trail arming at 1.25R = 12.5%.
    decision = Decision(decision_id="d-exit", kind=DecisionKind.FUND, size_cad=25.0)
    pos = build_open_position(_pitch_for_exit(), decision)
    assert pos.stop_fraction == pytest.approx(0.10)
    assert pos.take_profit == pytest.approx(0.125)
    # The Critic's scoring band is untouched by the exit change.
    assert pos.band_high == pytest.approx(0.08 + 2 * 0.05 * (5.0 ** 0.5))


def test_take_profit_arms_trail_at_r_multiple():
    decision = Decision(decision_id="d-tp", kind=DecisionKind.FUND, size_cad=25.0)
    pos = build_open_position(_pitch_for_exit(), decision, opened_at=_BASE)
    # +13% crosses the 12.5% arm level and ARMS the trail; the ride peaks at
    # +25% and the first close giving back the 10% stop distance exits at +12%.
    outcome = resolve_position(pos, _bars([100, 100, 113, 125, 112]))
    assert outcome is not None
    assert outcome.realized_return == pytest.approx(0.12)


def test_legacy_position_still_uses_band_top():
    # A pre-migration row has take_profit=0 → the old band-top trigger applies.
    pos = OpenPosition(
        decision_id="d-legacy", division="event", venue="kraken", symbol="ETHUSD",
        size_cad=25.0, predicted_return=0.08, predicted_confidence=0.6, cost_cad=0.25,
        stop_fraction=0.15, band_low=-0.1, band_high=0.18, horizon_days=30.0,
        opened_at=_BASE, live=False, qty=0.0, take_profit=0.0,
    )
    # +10% must NOT trigger (band top is 18%); +20% arms the trail and the
    # pullback through the 15%-stop trail distance exits.
    assert resolve_position(pos, _bars([100, 110, 110])) is None
    outcome = resolve_position(pos, _bars([100, 120, 130, 108]))
    assert outcome is not None


# ---- prediction shrinkage: forecasts blend toward the realized record ---------------

def _outcome(division, realized):
    from boardroom.schemas import ResolvedOutcome

    return ResolvedOutcome(
        decision_id=str(__import__("uuid").uuid4()), division=division,
        predicted_return=0.08, realized_return=realized, predicted_confidence=0.6,
        win=realized > 0, pnl_cad=realized * 25.0, cost_cad=0.1, inside_band=False,
    )


def test_expected_return_shrinks_toward_realized_mean():
    from boardroom.factory import build_default_org

    repo = InMemoryRepository()
    for _ in range(10):
        repo.save_outcome(_outcome(Division.EVENT, -0.05))
    org = build_default_org(data_mode="synthetic", repo=repo)

    pitch = _pitch_for_exit(expected=0.08)
    adjusted = org._shrink_expected_return(pitch)
    # w = max(5/(5+10), 0.7) = 0.7 (owner dial 2026-08-05: the model keeps at
    # least 70% of its voice) → 0.7*0.08 + 0.3*(-0.05) = 0.041
    w = 0.7
    assert adjusted.expected_return == pytest.approx(w * 0.08 + (1 - w) * -0.05)
    assert adjusted.signals.features["expected_return_model_raw"] == pytest.approx(0.08)
    # The record still pulls the forecast DOWN (0.08 -> 0.041); with the owner's
    # softer floor the model keeps its voice instead of being silenced outright.
    assert adjusted.expected_return < 0.08


def test_no_history_means_no_shrink():
    from boardroom.factory import build_default_org

    org = build_default_org(data_mode="synthetic", repo=InMemoryRepository())
    pitch = _pitch_for_exit(expected=0.08)
    assert org._shrink_expected_return(pitch).expected_return == pytest.approx(0.08)
