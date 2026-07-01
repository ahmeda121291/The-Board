"""Execution truth + run health: every fill is persisted the moment the broker
returns, every checkpoint leaves a run record (ok or crashed), breakers are
evaluated inside the run, and venue holdings reconcile against tracked
positions."""

from __future__ import annotations

import datetime as dt
import uuid

import pytest

from boardroom.brokers.base import Broker, Fill, Order, OrderSide
from boardroom.brokers.stub import StubBroker
from boardroom.factory import build_default_org
from boardroom.persistence.repository import InMemoryRepository, OpenPosition
from boardroom.schemas import (
    ComputedSignals,
    DataSnapshot,
    Decision,
    DecisionKind,
    Division,
    Pitch,
    ProcessLuckTag,
    ResolvedOutcome,
    Venue,
)


def _crypto_pitch(symbol: str = "XBTUSD") -> Pitch:
    snap = DataSnapshot(
        symbol=symbol, venue=Venue.KRAKEN, as_of=dt.datetime.now(dt.timezone.utc),
        age_seconds=10, is_fresh=True, rows=60, content_hash="h", source="test",
    )
    sig = ComputedSignals(
        features={"volatility": 0.02}, model_name="m", model_version="v0",
        expected_return=0.05, win_probability=0.7, raw_confidence=0.7, horizon_days=5.0,
    )
    return Pitch(
        pitch_id=str(uuid.uuid4()), division=Division.EVENT, venue=Venue.KRAKEN,
        symbol=symbol, snapshot=snap, signals=sig, capital_required=20.0,
        expected_return=0.05, confidence=0.7, time_horizon_days=5.0, max_loss=4.0,
        expected_cost=0.1,
    )


def _fund(org, pitch: Pitch, size: float = 20.0) -> Decision:
    decision = Decision(
        decision_id=str(uuid.uuid4()), kind=DecisionKind.FUND, division=pitch.division,
        pitch_id=pitch.pitch_id, size_cad=size,
    )
    org.execute(decision, [pitch])
    return decision


# ---- fills are the record of truth ----------------------------------------------

def test_buy_records_a_fill_row():
    repo = InMemoryRepository()
    org = build_default_org(data_mode="synthetic", repo=repo)
    pitch = _crypto_pitch()
    decision = _fund(org, pitch)

    fills = repo.recent_fills()
    assert len(fills) == 1
    f = fills[0]
    assert f["side"] == "buy"
    assert f["symbol"] == pitch.symbol
    assert f["venue"] == "kraken"
    assert f["decision_id"] == decision.decision_id
    assert f["notional_cad"] and f["notional_cad"] > 0
    assert f["is_live"] is False  # dry-run


def test_fill_survives_position_save_failure():
    # The 2026-07-01 incident: execution succeeded, then persistence crashed and
    # the trade vanished. Now the fill row lands first and a position-save
    # failure is audited, not fatal.
    class BoomPositionRepo(InMemoryRepository):
        def save_open_position(self, position):
            raise RuntimeError("simulated postgrest failure")

    repo = BoomPositionRepo()
    org = build_default_org(data_mode="synthetic", repo=repo)
    _fund(org, _crypto_pitch())

    assert len(repo.recent_fills()) == 1          # the trade is on record
    assert repo.open_positions() == []            # position save did fail
    events = [e for e, _ in repo.audit_log]
    assert "position_record_error" in events      # ...and loudly


def test_live_sell_records_fill_with_exit_reason():
    class LiveSellBroker(StubBroker):
        # Not named StubBroker so the sell path treats it as a real adapter,
        # and reports the sell as live so the close finalizes.
        def place_order(self, order: Order, *, live: bool) -> Fill:
            f = super().place_order(order, live=live)
            return Fill(**{**f.__dict__, "is_live": True})

    repo = InMemoryRepository()
    org = build_default_org(
        data_mode="synthetic", repo=repo,
        brokers={Venue.KRAKEN: LiveSellBroker(Venue.KRAKEN), Venue.IBKR: StubBroker(Venue.IBKR)},
    )
    pos = OpenPosition(
        decision_id=str(uuid.uuid4()), division="event", venue="kraken", symbol="XBTCAD",
        size_cad=25.0, predicted_return=0.05, predicted_confidence=0.7, cost_cad=0.1,
        stop_fraction=0.05, band_low=-0.05, band_high=0.15, horizon_days=5.0,
        opened_at=dt.datetime.now(dt.timezone.utc), live=True, qty=0.001,
    )
    outcome = ResolvedOutcome(
        decision_id=pos.decision_id, division=Division.EVENT, predicted_return=0.05,
        realized_return=-0.06, predicted_confidence=0.7, win=False, pnl_cad=-1.5,
        cost_cad=0.1, inside_band=True, process_luck=ProcessLuckTag.GOOD_PROCESS_BAD_OUTCOME,
    )
    closed = org._close_position_live(pos, outcome)
    assert closed is True
    fills = repo.recent_fills()
    assert len(fills) == 1
    assert fills[0]["side"] == "sell"
    assert fills[0]["exit_reason"] == "stop_loss"  # -6% breached the 5% stop


# ---- run records: ok and crashed --------------------------------------------------

def test_run_once_records_an_ok_run_with_breakers_evaluated():
    repo = InMemoryRepository()
    org = build_default_org(data_mode="synthetic", repo=repo)
    org.run_once(portfolio_value_cad=250.0, trigger="run_now")

    runs = repo.recent_runs()
    assert len(runs) == 1
    r = runs[0]
    assert r["trigger"] == "run_now"
    assert r["status"] == "ok"
    assert r["breakers_evaluated"] is True
    assert r["breakers"] == []
    assert r["decision_id"]


def test_crashed_run_is_recorded_as_crashed():
    class BoomDecisionRepo(InMemoryRepository):
        def save_decision(self, decision, ranking):
            raise RuntimeError("simulated mid-run crash")

    repo = BoomDecisionRepo()
    org = build_default_org(data_mode="synthetic", repo=repo)
    with pytest.raises(RuntimeError):
        org.run_once(portfolio_value_cad=250.0, trigger="wide")

    runs = repo.recent_runs()
    assert len(runs) == 1
    assert runs[0]["status"] == "crashed"
    assert "simulated mid-run crash" in runs[0]["error"]


# ---- breakers halt new risk inside the run -----------------------------------------

def test_daily_loss_breaker_forces_hold_and_is_persisted():
    repo = InMemoryRepository()
    # A realized loss today beyond 6% of a 250 CAD book (limit 15 CAD).
    repo.save_outcome(
        ResolvedOutcome(
            decision_id=str(uuid.uuid4()), division=Division.EVENT, predicted_return=0.02,
            realized_return=-0.2, predicted_confidence=0.4, win=False, pnl_cad=-30.0,
            cost_cad=0.5, inside_band=False,
            process_luck=ProcessLuckTag.GOOD_PROCESS_BAD_OUTCOME,
        )
    )
    org = build_default_org(data_mode="synthetic", repo=repo)
    result = org.run_once(portfolio_value_cad=250.0)

    assert result.breakers, "breaker should have tripped"
    assert result.decision.kind == DecisionKind.HOLD
    assert "Circuit breaker" in result.decision.rationale
    assert result.pitches == [] and result.fills == []
    runs = repo.recent_runs()
    assert runs[0]["breakers"] and runs[0]["status"] == "ok"
    assert any(e == "circuit_breaker" for e, _ in repo.audit_log)


# ---- reconciliation: venue holdings vs tracked positions ----------------------------

class HoldingsBroker(Broker):
    venue = Venue.KRAKEN
    supports_withdrawal = False

    def __init__(self, holdings):
        self._holdings = holdings

    def health_check(self) -> bool:
        return True

    def get_cash_cad(self) -> float:
        return 100.0

    def get_positions(self):
        return self._holdings

    def place_order(self, order: Order, *, live: bool) -> Fill:
        raise AssertionError("not used")


def test_reconciliation_flags_untracked_holdings():
    repo = InMemoryRepository()
    org = build_default_org(
        data_mode="synthetic", repo=repo,
        brokers={
            Venue.KRAKEN: HoldingsBroker(
                [{"symbol": "SOL", "qty": 0.2, "market_value_cad": 52.0}]
            ),
            Venue.IBKR: StubBroker(Venue.IBKR),
        },
    )
    recon = org.reconcile_positions()
    assert recon is not None
    assert recon["untracked"] == [{"asset": "SOL", "qty": 0.2, "market_value_cad": 52.0}]
    assert any(e == "reconciliation_untracked" for e, _ in repo.audit_log)


def test_reconciliation_clear_when_position_tracked():
    repo = InMemoryRepository()
    repo.save_open_position(
        OpenPosition(
            decision_id=str(uuid.uuid4()), division="crypto_trend", venue="kraken",
            symbol="SOLCAD", size_cad=25.0, predicted_return=0.02, predicted_confidence=0.6,
            cost_cad=0.1, stop_fraction=0.05, band_low=-0.1, band_high=0.15,
            horizon_days=5.0, opened_at=dt.datetime.now(dt.timezone.utc), live=True, qty=0.2,
        )
    )
    org = build_default_org(
        data_mode="synthetic", repo=repo,
        brokers={
            Venue.KRAKEN: HoldingsBroker(
                [{"symbol": "SOL", "qty": 0.2, "market_value_cad": 52.0}]
            ),
            Venue.IBKR: StubBroker(Venue.IBKR),
        },
    )
    recon = org.reconcile_positions()
    assert recon is not None and recon["untracked"] == []


# ---- NaN never crashes a persistence write ------------------------------------------

def test_json_safe_strips_nan_and_infinity():
    from boardroom.persistence.supabase_repo import _json_safe

    dirty = {"a": float("nan"), "b": [1.0, float("inf")], "c": {"d": float("-inf"), "e": 2.0}}
    clean = _json_safe(dirty)
    assert clean == {"a": None, "b": [1.0, None], "c": {"d": None, "e": 2.0}}
