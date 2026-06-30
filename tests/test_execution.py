"""Live-execution safety: CAD-pair translation + a rejected order can't crash.

A CAD-funded account must place CAD-quoted orders (not USD), and a broker
rejection (insufficient funds, no market, min-size) must be caught so the
checkpoint still finishes and refreshes balances/recommendations/portfolio.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest

from boardroom.brokers.base import Broker, Fill, Order, OrderSide
from boardroom.brokers.kraken import exec_pair_for
from boardroom.factory import build_default_org
from boardroom.persistence.repository import InMemoryRepository
from boardroom.schemas import (
    ComputedSignals,
    DataSnapshot,
    Decision,
    DecisionKind,
    Division,
    Pitch,
    Venue,
)


# ---- CAD pair translation ---------------------------------------------------
@pytest.mark.parametrize(
    "symbol,expected",
    [
        ("XBTUSD", "XBTCAD"),
        ("ETHUSD", "ETHCAD"),
        ("SOLUSD", "SOLCAD"),
        ("XBTCAD", "XBTCAD"),     # already CAD → unchanged
        ("ETHUSDT", "ETHCAD"),    # USDT quote → CAD
        ("ETHUSDC", "ETHCAD"),    # USDC quote → CAD
    ],
)
def test_exec_pair_translates_to_account_quote(symbol, expected):
    assert exec_pair_for(symbol, "CAD") == expected


# ---- a rejected order doesn't crash the checkpoint --------------------------
class _BoomBroker(Broker):
    venue = Venue.KRAKEN
    supports_withdrawal = False

    def health_check(self) -> bool:
        return True

    def get_cash_cad(self) -> float:
        return 100.0

    def place_order(self, order: Order, *, live: bool) -> Fill:
        raise RuntimeError("Kraken AddOrder error: ['EOrder:Insufficient funds']")


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


def test_execute_swallows_broker_rejection():
    repo = InMemoryRepository()
    org = build_default_org(
        data_mode="synthetic", repo=repo,
        brokers={Venue.KRAKEN: _BoomBroker(), Venue.IBKR: _BoomBroker()},
    )
    pitch = _crypto_pitch()
    decision = Decision(
        decision_id=str(uuid.uuid4()), kind=DecisionKind.FUND, division=Division.EVENT,
        pitch_id=pitch.pitch_id, size_cad=20.0,
    )
    # Must NOT raise even though the broker rejects the order.
    fills = org.execute(decision, [pitch])
    assert fills == []
    assert decision.live is False
    assert not repo.open_positions()                      # no position recorded on failure
    assert any(ev == "execute_error" for ev, _ in repo.audit_log)
