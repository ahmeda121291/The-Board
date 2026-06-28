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
    bars = _bars([100.0, 101.0, 102.0, 105.0, 106.0, 107.0])
    out = resolve_position(pos, bars)
    assert out.inside_band is False  # +7% landed well outside the predicted band


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
    # stop_fraction = (max_loss - cost) / capital = (4.4 - 0.4) / 40 = 0.10
    assert pos.stop_fraction == pytest.approx(0.10)
    # band = expected_return ± 2 * vol * sqrt(horizon)
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
