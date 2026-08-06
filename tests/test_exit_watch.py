"""The intraday exit engine — the fix for the $969 peak that never sold.

On 2026-08-06 the book rode LIT +75% overnight and round-tripped to a -14%
stop-out while four checkpoints watched: exits evaluated on daily closes, the
pump never printed as a close, and the trailing stop's armed/peak state was
recomputed from scratch on every walk. These tests pin the three structural
fixes: exits measure from the persisted fill-time entry price, the trail arms
and rides off intraday bar HIGHS, and armed/peak state persists across passes
so a ride survives restarts and rolling bar windows. Plus the watcher itself
and the no-balance void that unsticks phantom rows.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from boardroom.graph.exit_watch import watch_exits
from boardroom.graph.resolution_loop import resolve_open_positions, walk_position
from boardroom.persistence.repository import InMemoryRepository, OpenPosition
from boardroom.schemas import Venue

_BASE = datetime(2026, 8, 5, 18, 0, tzinfo=timezone.utc)


def _bars(closes, highs=None, *, start=None, step_minutes=60, symbol="LITUSD"):
    from boardroom.data.snapshot import Bars

    start = start or _BASE
    n = len(closes)
    highs = highs or closes
    times = pd.to_datetime(
        [start + timedelta(minutes=step_minutes * (i + 1)) for i in range(n)], utc=True
    )
    df = pd.DataFrame(
        {
            "time": times,
            "open": closes,
            "high": [max(h, c) for h, c in zip(highs, closes)],
            "low": [min(h, c) for h, c in zip(highs, closes)],
            "close": closes,
            "volume": [1e6] * n,
        }
    )
    return Bars(symbol=symbol, venue=Venue.KRAKEN, df=df, source="test")


def _pos(**overrides) -> OpenPosition:
    base = dict(
        decision_id="lit-1",
        division="event",
        venue="kraken",
        symbol="LITUSD",
        size_cad=172.0,
        predicted_return=0.03,
        predicted_confidence=0.6,
        cost_cad=1.0,
        stop_fraction=0.10,
        band_low=-0.30,
        band_high=0.30,
        horizon_days=3.0,
        opened_at=_BASE,
        live=False,
        qty=468.0,
        take_profit=0.125,
    )
    base.update(overrides)
    return OpenPosition(**base)


# --------------------------------------------------------------------------- #
# walk_position — entry price, highs, persisted trail state
# --------------------------------------------------------------------------- #
def test_persisted_entry_price_beats_series_recovery():
    # Series says 100 at open; the fill actually printed at 105. A +7% move off
    # the series (112.35) is only +7/105 = +7% off the fill — the stop and TP
    # must measure from where money actually entered.
    pos = _pos(entry_price=105.0, horizon_days=0.01)
    out = walk_position(pos, _bars([100.0, 112.35])).outcome
    assert out is not None
    assert out.realized_return == pytest.approx(112.35 / 105.0 - 1.0)


def test_trail_arms_off_the_high_not_the_close():
    # The pump is a WICK: closes never print above +5% but the high spikes +40%.
    # The trail must arm off the high and the same bar's weak close exits with
    # the banked gain — this is the LIT overnight shape.
    pos = _pos(entry_price=100.0)
    walk = walk_position(pos, _bars([101.0, 105.0], highs=[101.0, 140.0]))
    assert walk.outcome is not None
    assert walk.outcome.realized_return == pytest.approx(0.05)
    assert walk.outcome.win is True


def test_open_ride_reports_state_for_persistence():
    # +30% high arms the trail; the close holds near the peak → still riding,
    # and the walk hands back the state the repo must persist.
    pos = _pos(entry_price=100.0)
    walk = walk_position(pos, _bars([101.0, 128.0], highs=[101.0, 130.0]))
    assert walk.outcome is None
    assert walk.trail_armed is True
    assert walk.peak_return == pytest.approx(0.30)
    assert walk.entry_price == pytest.approx(100.0)


def test_legacy_entry_recovered_from_the_series_and_backfilled():
    # A pre-migration row (entry_price=0) still prices its entry by timestamp:
    # the last close at or before the open. The walk reports it for backfill.
    pos = _pos()  # entry_price defaults to 0
    bars = _bars(
        [100.0, 100.0, 128.0], highs=[100.0, 100.0, 130.0],
        start=_BASE - timedelta(hours=2),
    )  # bars at -1h, 0h (entry), +1h
    walk = walk_position(pos, bars)
    assert walk.outcome is None
    assert walk.entry_price == pytest.approx(100.0)
    assert walk.trail_armed is True
    assert walk.peak_return == pytest.approx(0.30)


def test_persisted_peak_survives_a_rolled_window():
    # Pass 1 saw the peak; pass 2's window no longer contains it (rolling
    # intraday history). The persisted peak must still drive the trail exit.
    pos = _pos(entry_price=100.0, trail_armed=True, peak_return=0.75)
    # Window shows only the fade: closes at +40% — more than 10% below the
    # persisted +75% peak → exit, banking +40%.
    walk = walk_position(pos, _bars([140.0]))
    assert walk.outcome is not None
    assert walk.outcome.realized_return == pytest.approx(0.40)
    assert walk.outcome.win is True


def test_resolution_loop_persists_trail_state():
    repo = InMemoryRepository()
    repo.save_open_position(_pos(entry_price=100.0))
    bars = _bars([113.0, 128.0], highs=[115.0, 130.0])  # armed + riding

    updates = resolve_open_positions(repo, lambda pos: bars)

    assert updates == []                       # still open — riding the trail
    pos = repo.open_positions()[0]
    assert pos.trail_armed is True
    assert pos.peak_return == pytest.approx(0.30)


def test_stop_still_fires_first():
    pos = _pos(entry_price=100.0)
    walk = walk_position(pos, _bars([89.0]))
    assert walk.outcome is not None
    assert walk.outcome.realized_return == pytest.approx(-0.11)
    assert walk.outcome.win is False


# --------------------------------------------------------------------------- #
# the watcher — sells only, cheap, never raises
# --------------------------------------------------------------------------- #
def _org(repo, fine_bars):
    from boardroom.factory import build_default_org

    org = build_default_org(data_mode="synthetic", repo=repo)
    org.resolution_fetch = lambda sym: fine_bars
    return org


def test_watch_exits_closes_triggered_positions_and_audits():
    repo = InMemoryRepository()
    repo.save_open_position(_pos(entry_price=100.0, trail_armed=True, peak_return=0.75))
    org = _org(repo, _bars([140.0]))

    updates = watch_exits(org)

    assert len(updates) == 1
    assert repo.open_positions() == []
    assert len(repo.outcomes) == 1
    assert any(e == "exit_watch" for e, _ in repo.audit_log)


def test_watch_exits_quiet_pass_touches_nothing():
    repo = InMemoryRepository()
    org = _org(repo, _bars([100.0]))
    assert watch_exits(org) == []
    assert repo.audit_log == []


def test_watch_exits_prefers_the_intraday_series():
    # The division fetchers must NOT run on a watcher pass — only the held
    # symbol's fine series is fetched.
    repo = InMemoryRepository()
    repo.save_open_position(_pos(entry_price=100.0, horizon_days=99.0))
    fetched: list[str] = []

    def fine(sym):
        fetched.append(sym)
        return _bars([100.5], symbol=sym)

    from boardroom.factory import build_default_org

    org = build_default_org(data_mode="synthetic", repo=repo)
    org.resolution_fetch = fine
    watch_exits(org)

    assert fetched == ["LITUSD"]
    assert getattr(org, "_price_cache", None) in (None, {}), (
        "a quiet watcher pass must not build the full division price cache"
    )


def test_watch_exits_never_raises():
    repo = InMemoryRepository()
    repo.save_open_position(_pos(entry_price=100.0))

    from boardroom.factory import build_default_org

    org = build_default_org(data_mode="synthetic", repo=repo)

    def boom(sym):
        raise RuntimeError("feed down")

    org.resolution_fetch = boom
    org.resolution_fallback_fetch = boom
    # Division fetchers won't cover LITUSD → unpriceable, but never an exception.
    assert watch_exits(org) == []


# --------------------------------------------------------------------------- #
# no-balance void — phantom rows stop erroring forever
# --------------------------------------------------------------------------- #
class _NoBalanceKraken:
    """A live-looking broker whose sell bounces and whose book holds nothing —
    the TRU/EUL phantom shape (an earlier clamped sell swept the balance)."""

    def assert_no_withdrawal(self) -> None:
        pass

    def get_positions(self):
        return []

    def place_order(self, order, *, live):
        raise RuntimeError("Kraken AddOrder error: ['EOrder:Insufficient funds']")


def test_exit_no_balance_voids_the_phantom_row():
    repo = InMemoryRepository()
    repo.save_open_position(_pos(entry_price=100.0, live=True, trail_armed=True, peak_return=0.75))

    from boardroom.factory import build_default_org

    org = build_default_org(
        data_mode="synthetic", repo=repo, brokers={Venue.KRAKEN: _NoBalanceKraken()},
    )
    org.resolution_fetch = lambda sym: _bars([140.0])

    updates = watch_exits(org)

    assert len(updates) == 1
    assert repo.open_positions() == [], "the phantom row must close"
    assert len(repo.outcomes) == 1, "the round-trip still books an outcome"
    assert any(e == "exit_no_balance" for e, _ in repo.audit_log)


def test_exit_error_with_real_balance_keeps_the_position():
    class _HoldsCoins(_NoBalanceKraken):
        def get_positions(self):
            return [{"symbol": "LIT", "qty": 468.0, "market_value_cad": 170.0}]

    repo = InMemoryRepository()
    repo.save_open_position(_pos(entry_price=100.0, live=True, trail_armed=True, peak_return=0.75))

    from boardroom.factory import build_default_org

    org = build_default_org(
        data_mode="synthetic", repo=repo, brokers={Venue.KRAKEN: _HoldsCoins()},
    )
    org.resolution_fetch = lambda sym: _bars([140.0])

    updates = watch_exits(org)

    assert updates == []
    assert len(repo.open_positions()) == 1, "a real failed sell must retry, not void"
    assert repo.outcomes == []
    assert any(e == "exit_error" for e, _ in repo.audit_log)


# --------------------------------------------------------------------------- #
# entry price capture at fill time
# --------------------------------------------------------------------------- #
def test_execute_captures_the_fill_time_entry_price():
    from boardroom.factory import build_default_org
    from boardroom.schemas import (
        ComputedSignals, DataSnapshot, Decision, DecisionKind, Division, Pitch,
    )

    repo = InMemoryRepository()
    org = build_default_org(data_mode="synthetic", repo=repo)
    org.resolution_fetch = lambda sym: _bars([104.2], symbol=sym)

    snap = DataSnapshot(
        symbol="ETHUSD", venue=Venue.KRAKEN, as_of=datetime.now(timezone.utc),
        age_seconds=5, is_fresh=True, rows=90, content_hash="x", source="test",
    )
    sig = ComputedSignals(
        features={"volatility": 0.05}, model_name="m", model_version="v",
        expected_return=0.05, win_probability=0.6, raw_confidence=0.6, horizon_days=3.0,
    )
    pitch = Pitch(
        pitch_id="p-entry", division=Division.EVENT, venue=Venue.KRAKEN, symbol="ETHUSD",
        snapshot=snap, signals=sig, capital_required=25.0, expected_return=0.05,
        confidence=0.6, time_horizon_days=3.0, max_loss=2.5, expected_cost=0.25,
    )
    decision = Decision(
        decision_id="d-entry", kind=DecisionKind.FUND, division=Division.EVENT,
        pitch_id="p-entry", size_cad=25.0,
    )
    org.execute(decision, [pitch])

    positions = repo.open_positions()
    assert len(positions) == 1
    assert positions[0].entry_price == pytest.approx(104.2)
