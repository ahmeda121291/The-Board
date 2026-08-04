"""Owner mandate 2026-08-04 ("go big or go home"): the system must never
silently park itself, and winners must be allowed to run.

- Leash floor: a losing streak walks the leash down to LEASH_MIN, never to the
  old absorbing zero (no trades -> no evidence -> no recovery).
- Rolling calibration: trust follows the recent window, so old losses age out.
- Retirement now needs BOTH persistent miscalibration AND net-negative money
  over a real sample — and revival is an explicit, audited human override.
- Trailing exits: hitting the take-profit arms a trailing stop instead of
  selling; the ride is uncapped and survives the horizon clock.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pandas as pd

from boardroom.adaptive.calibration import CalibrationPosterior
from boardroom.adaptive.leash import update_leash
from boardroom.adaptive.retirement import should_retire
from boardroom.config import Settings, get_settings
from boardroom.data.snapshot import Bars
from boardroom.graph.learning_loop import revive_division, update_division
from boardroom.graph.resolution_loop import resolve_position
from boardroom.persistence.repository import InMemoryRepository, OpenPosition
from boardroom.schemas import Division, ResolvedOutcome, Venue

UTC = dt.timezone.utc


# ---- leash floor -------------------------------------------------------------

def _bad_posterior() -> CalibrationPosterior:
    return CalibrationPosterior(division="momentum", alpha=2.0, beta=10.0)  # mean 0.167


def test_leash_floors_instead_of_zeroing():
    leash = 0.2
    for _ in range(10):  # a long losing streak keeps stepping it down
        leash = update_leash(
            leash, posterior=_bad_posterior(), realized_edge_vs_floor=-30.0, leash_min=0.15
        )
    assert leash == 0.15  # floored, not dead


def test_leash_floor_defaults_to_zero_for_backcompat():
    leash = update_leash(0.05, posterior=_bad_posterior(), realized_edge_vs_floor=-1.0)
    assert leash == 0.0


# ---- retirement: AND rule + sample floor ------------------------------------

def test_retire_needs_both_miscalibration_and_negative_money():
    bad_calib = CalibrationPosterior("d", alpha=5.0, beta=20.0)   # mean 0.2
    ok_calib = CalibrationPosterior("d", alpha=20.0, beta=20.0)   # mean 0.5
    # Miscalibrated but making money -> keep.
    assert not should_retire(posterior=bad_calib, net_vs_floor_cad=10.0, n_resolved=50)
    # Losing money but calling shots fine -> keep (cold streak, not broken).
    assert not should_retire(posterior=ok_calib, net_vs_floor_cad=-10.0, n_resolved=50)
    # Both -> retire.
    assert should_retire(posterior=bad_calib, net_vs_floor_cad=-10.0, n_resolved=50)
    # Small sample -> never, no matter how ugly.
    assert not should_retire(posterior=bad_calib, net_vs_floor_cad=-10.0, n_resolved=10)


# ---- update_division wires the real record ----------------------------------

def _outcome(division: str, win: bool, pnl: float, days_ago: int) -> ResolvedOutcome:
    return ResolvedOutcome(
        decision_id=str(uuid.uuid4()),
        division=Division(division),
        resolved_at=dt.datetime.now(UTC) - dt.timedelta(days=days_ago),
        predicted_return=0.05,
        realized_return=pnl / 25.0,
        predicted_confidence=0.7,
        win=win,
        pnl_cad=pnl,
        cost_cad=0.1,
        inside_band=True,
    )


def test_update_division_recomputes_n_and_net_from_history():
    repo = InMemoryRepository()
    for i in range(6):
        repo.save_outcome(_outcome("momentum", win=i % 2 == 0, pnl=2.0 if i % 2 == 0 else -1.0, days_ago=6 - i))
    upd = update_division("momentum", repo)
    st = repo.get_division_state("momentum")
    assert upd.n_resolved == 6 and st.n_resolved == 6
    assert abs(st.net_vs_floor_cad - (3 * 2.0 - 3 * 1.0 - 6 * 0.1)) < 1e-9
    assert st.leash >= get_settings().leash_min  # floored, still trading


def test_calibration_windows_out_old_losses():
    repo = InMemoryRepository()
    # 40 ancient losses, then a recent hot streak longer than the window.
    for i in range(40):
        repo.save_outcome(_outcome("momentum", win=False, pnl=-1.0, days_ago=200 - i))
    for i in range(30):
        repo.save_outcome(_outcome("momentum", win=True, pnl=2.0, days_ago=30 - i))
    upd = update_division("momentum", repo)
    # Windowed on the recent 30 wins: posterior should read HOT, not haunted.
    assert upd.posterior_mean > 0.9


def test_revive_resets_and_audits():
    repo = InMemoryRepository()
    st = repo.get_division_state("momentum")
    st.retired = True
    st.leash = 0.0
    repo.upsert_division_state(st)
    revived = revive_division("momentum", repo, leash=0.5)
    assert not revived.retired and revived.leash == 0.5
    assert revived.alpha == 1.0 and revived.beta == 1.0
    assert any(e[0] == "division_revived" for e in repo.audit_log)


def test_retired_division_stays_retired_until_revived():
    repo = InMemoryRepository()
    st = repo.get_division_state("momentum")
    st.retired = True
    repo.upsert_division_state(st)
    repo.save_outcome(_outcome("momentum", win=True, pnl=5.0, days_ago=1))
    upd = update_division("momentum", repo)
    assert upd.retired and repo.get_division_state("momentum").leash == 0.0


# ---- trailing exits ----------------------------------------------------------

def _bars(closes: list[float], start: dt.datetime) -> Bars:
    times = [start + dt.timedelta(days=i) for i in range(len(closes))]
    df = pd.DataFrame({"time": times, "close": closes})
    return Bars(symbol="SOLUSD", venue=Venue.KRAKEN, df=df, source="test")


def _pos(opened_at: dt.datetime, horizon_days: float = 5.0) -> OpenPosition:
    return OpenPosition(
        decision_id=str(uuid.uuid4()),
        division="crypto_trend",
        venue="kraken",
        symbol="SOLUSD",
        size_cad=25.0,
        predicted_return=0.05,
        predicted_confidence=0.7,
        cost_cad=0.1,
        stop_fraction=0.06,
        band_low=-0.10,
        band_high=0.25,
        horizon_days=horizon_days,
        opened_at=opened_at,
        live=False,
        qty=1.0,
        take_profit=0.09,
    )


def test_winner_rides_past_take_profit_and_exits_on_trail_break():
    start = dt.datetime(2026, 8, 1, tzinfo=UTC)
    pos = _pos(opened_at=start)
    # Entry 100 -> hits TP (+9%) -> keeps running to +50% -> gives back >6%.
    closes = [100.0, 105.0, 110.0, 125.0, 150.0, 139.0]
    out = resolve_position(pos, _bars(closes, start))
    assert out is not None
    assert abs(out.realized_return - 0.39) < 1e-9  # exited at 139, NOT at +9%


def test_armed_winner_is_not_cut_by_the_horizon():
    start = dt.datetime(2026, 8, 1, tzinfo=UTC)
    pos = _pos(opened_at=start, horizon_days=3.0)
    # TP armed, still climbing, horizon long elapsed -> keep riding (None).
    closes = [100.0, 110.0, 115.0, 120.0, 125.0, 130.0, 131.0]
    assert resolve_position(pos, _bars(closes, start)) is None


def test_stop_loss_still_exits_before_arming():
    start = dt.datetime(2026, 8, 1, tzinfo=UTC)
    pos = _pos(opened_at=start)
    closes = [100.0, 97.0, 93.0]
    out = resolve_position(pos, _bars(closes, start))
    assert out is not None and out.realized_return < 0


def test_trailing_disabled_restores_hard_take_profit(monkeypatch):
    from boardroom import config as config_mod

    s = Settings(_env_file=None, EXIT_TRAIL_ENABLED=False)
    monkeypatch.setattr(config_mod, "get_settings", lambda: s)
    import boardroom.graph.resolution_loop as rl
    start = dt.datetime(2026, 8, 1, tzinfo=UTC)
    pos = _pos(opened_at=start)
    closes = [100.0, 110.0, 150.0]
    out = rl.resolve_position(pos, _bars(closes, start))
    assert out is not None
    assert abs(out.realized_return - 0.10) < 1e-9  # sold at the TP print


# ---- deviation bar is ZERO while small (defaults) ----------------------------

def test_default_deviation_bar_is_zero_while_small():
    from boardroom.ceo.engine import CEODecisionEngine
    from boardroom.config import RiskCaps

    s = Settings(_env_file=None)
    assert s.ceo_deviation_threshold_low == 0.0
    assert s.aggressive_below_cad == 1000.0
    caps = RiskCaps(
        total_deployable_pct=s.total_deployable_pct,
        per_trade_max_pct=s.per_trade_max_pct,
        event_hard_cap_pct=s.event_hard_cap_pct,
        daily_loss_limit_pct=s.daily_loss_limit_pct,
        max_drawdown_pct=s.max_drawdown_pct,
        fee_drag_limit_pct=s.fee_drag_limit_pct,
    )
    eng = CEODecisionEngine(
        caps=caps,
        deviation_threshold=s.ceo_deviation_threshold,
        deviation_threshold_low=s.ceo_deviation_threshold_low,
        aggressive_below_cad=s.aggressive_below_cad,
        conservative_above_cad=s.conservative_above_cad,
    )
    # The live failure: equity ~672, best score 0.001, old bar ~0.0017 -> HOLD.
    # New defaults: under $1000 the bar is exactly zero -> any positive-score
    # survivor funds.
    assert eng._effective_threshold(672.0) == 0.0
    assert eng._effective_threshold(999.0) == 0.0
    assert eng._effective_threshold(5000.0) == s.ceo_deviation_threshold
