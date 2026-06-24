"""Divisions abstain correctly; the full decision loop runs end-to-end offline."""

from __future__ import annotations

import datetime as dt

import pandas as pd

from boardroom.data.sources import synthetic_bars
from boardroom.data.snapshot import Bars
from boardroom.divisions.directional import DirectionalDivision
from boardroom.divisions.event import EventDivision
from boardroom.divisions.effort import EffortDivision
from boardroom.factory import build_default_org
from boardroom.persistence.repository import InMemoryRepository
from boardroom.schemas import DecisionKind, Venue


def test_directional_abstains_on_stale_data():
    old = synthetic_bars("SPY.US", Venue.IBKR, n=120, seed=1,
                         end=dt.datetime(2000, 1, 1, tzinfo=dt.timezone.utc))
    div = DirectionalDivision(fetch=lambda: old)
    assert div.propose() is None  # stale -> abstain


def test_directional_abstains_on_too_few_rows():
    bars = synthetic_bars("SPY.US", Venue.IBKR, n=10, seed=1)
    div = DirectionalDivision(fetch=lambda: bars)
    assert div.propose() is None  # < min_rows -> abstain


def test_directional_produces_pitch_on_fresh_data():
    bars = synthetic_bars("SPY.US", Venue.IBKR, n=160, seed=2, drift=0.002, vol=0.01)
    div = DirectionalDivision(fetch=lambda: bars)
    pitch = div.propose(bankroll_cad=200)
    assert pitch is not None
    # Quantitative fields are populated by code; narrative is still empty here.
    assert pitch.capital_required > 0
    assert pitch.max_loss > 0
    assert pitch.opportunity == ""


def test_event_sentinel_abstains_when_no_trigger():
    # Calm, trendless series -> no dislocation -> sentinel silent.
    bars = synthetic_bars("XBTUSD", Venue.KRAKEN, n=160, seed=4, drift=0.0, vol=0.005)
    div = EventDivision(fetch=lambda: bars)
    assert div.propose() is None


def test_effort_division_disabled():
    assert EffortDivision().propose() is None


def test_full_loop_runs_offline():
    repo = InMemoryRepository()
    org = build_default_org(data_mode="synthetic", repo=repo)
    result = org.run_once(bankroll_cad=200)
    assert result.decision.kind in (DecisionKind.FUND, DecisionKind.FUND_NONE, DecisionKind.HOLD)
    # The decision and any pitches were persisted.
    assert len(repo.decisions) == 1
    # Brokers are stubs: nothing executed live.
    for fill in result.fills:
        assert fill.is_live is False


def test_loop_never_executes_live_without_flag():
    repo = InMemoryRepository()
    org = build_default_org(data_mode="synthetic", repo=repo)
    result = org.run_once(bankroll_cad=200)
    assert result.decision.live is False
