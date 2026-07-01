"""The two-key live gate: a real order (buy OR sell) requires BOTH the
LIVE_TRADING env flag AND the per-run --confirm-live. Either alone is a
dry-run. Regression tests for the gate being enforced in the execution layer,
not just the CLI banner."""

from __future__ import annotations

import datetime as dt
import uuid

from boardroom.brokers.stub import StubBroker
from boardroom.config import Settings
from boardroom.factory import build_default_org
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


class SpyBroker(StubBroker):
    """A stub that records the ``live`` flag it was told to trade with.

    Deliberately NOT named StubBroker so the sell path's real-broker check
    (`type(broker).__name__ == "StubBroker"`) treats it as a live adapter.
    """

    def __init__(self, venue):
        super().__init__(venue)
        self.live_flags: list[bool] = []

    def place_order(self, order, *, live):
        self.live_flags.append(live)
        return super().place_order(order, live=live)


def _crypto_pitch() -> Pitch:
    snap = DataSnapshot(
        symbol="XBTUSD", venue=Venue.KRAKEN, as_of=dt.datetime.now(dt.timezone.utc),
        age_seconds=10, is_fresh=True, rows=60, content_hash="h", source="test",
    )
    sig = ComputedSignals(
        features={"price": 80000.0}, model_name="m", model_version="v0",
        expected_return=0.05, win_probability=0.7, raw_confidence=0.7, horizon_days=5.0,
    )
    return Pitch(
        pitch_id=str(uuid.uuid4()), division=Division.EVENT, venue=Venue.KRAKEN,
        symbol="XBTUSD", snapshot=snap, signals=sig, capital_required=20.0,
        expected_return=0.05, confidence=0.7, time_horizon_days=5.0, max_loss=4.0,
        expected_cost=0.1,
    )


def _org(*, live_trading: bool, confirm_live: bool, spy: SpyBroker):
    return build_default_org(
        data_mode="synthetic",
        repo=InMemoryRepository(),
        brokers={Venue.KRAKEN: spy, Venue.IBKR: StubBroker(Venue.IBKR)},
        settings=Settings(LIVE_TRADING=live_trading, _env_file=None),
        confirm_live=confirm_live,
    )


def _fund_one(org, spy: SpyBroker) -> list[bool]:
    pitch = _crypto_pitch()
    decision = Decision(
        decision_id=str(uuid.uuid4()), kind=DecisionKind.FUND, division=Division.EVENT,
        pitch_id=pitch.pitch_id, size_cad=20.0,
    )
    org.execute(decision, [pitch])
    return spy.live_flags


# ---- BUY path -----------------------------------------------------------------

def test_live_trading_alone_stays_dry():
    # The historical bug: LIVE_TRADING=true + no --confirm-live placed real
    # orders while the console said "dry-run". The broker must be told dry-run.
    spy = SpyBroker(Venue.KRAKEN)
    org = _org(live_trading=True, confirm_live=False, spy=spy)
    assert _fund_one(org, spy) == [False]


def test_confirm_live_alone_stays_dry():
    spy = SpyBroker(Venue.KRAKEN)
    org = _org(live_trading=False, confirm_live=True, spy=spy)
    assert _fund_one(org, spy) == [False]


def test_both_keys_go_live():
    spy = SpyBroker(Venue.KRAKEN)
    org = _org(live_trading=True, confirm_live=True, spy=spy)
    assert _fund_one(org, spy) == [True]


# ---- SELL path (position close) --------------------------------------------------

def _live_position() -> OpenPosition:
    return OpenPosition(
        decision_id=str(uuid.uuid4()), division="event", venue="kraken",
        symbol="XBTCAD", size_cad=25.0, predicted_return=0.05,
        predicted_confidence=0.7, cost_cad=0.1, stop_fraction=0.05,
        band_low=-0.05, band_high=0.15, horizon_days=5.0,
        opened_at=dt.datetime.now(dt.timezone.utc), live=True, qty=0.0003,
    )


def test_sell_without_confirm_live_stays_dry_and_keeps_position_open():
    spy = SpyBroker(Venue.KRAKEN)
    org = _org(live_trading=True, confirm_live=False, spy=spy)
    closed = org._close_position_live(_live_position(), None)
    assert spy.live_flags == [False]   # the exit order must NOT be live
    assert closed is False             # a dry-run can't close a real live position


def test_sell_with_both_keys_is_told_live():
    spy = SpyBroker(Venue.KRAKEN)
    org = _org(live_trading=True, confirm_live=True, spy=spy)
    org._close_position_live(_live_position(), None)
    assert spy.live_flags == [True]
