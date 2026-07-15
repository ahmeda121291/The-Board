"""Untracked-holdings adoption: the code path behind the dashboard's ⚠ alert.

An orphan (coin on the venue with no tracked position) can now be ADOPTED into
a live, auto-managed position or FLATTENED with a live market sell — instead of
"adopt or sell manually" being an instruction with no tool behind it.
"""

import datetime as dt
import uuid

import pytest

from boardroom.adoption import (
    adopt_untracked,
    build_adoption,
    find_untracked,
    sell_untracked,
    untracked_holdings,
)
from boardroom.brokers.base import Broker, Fill, Order, OrderSide
from boardroom.persistence.repository import InMemoryRepository, OpenPosition
from boardroom.schemas import DecisionKind, Venue


def _pos(symbol: str, qty: float = 1.0) -> OpenPosition:
    return OpenPosition(
        decision_id=str(uuid.uuid4()), division="crypto_trend", venue="kraken",
        symbol=symbol, size_cad=20.0, predicted_return=0.02, predicted_confidence=0.6,
        cost_cad=0.1, stop_fraction=0.05, band_low=-0.1, band_high=0.15,
        horizon_days=5.0, opened_at=dt.datetime.now(dt.timezone.utc), live=True, qty=qty,
    )


class VenueBroker(Broker):
    """Fake Kraken: fixed holdings; sells return a live (or paper) fill."""

    venue = Venue.KRAKEN
    supports_withdrawal = False

    def __init__(self, holdings, *, live_fills: bool = True):
        self._holdings = holdings
        self._live_fills = live_fills
        self.orders: list[Order] = []

    def health_check(self) -> bool:
        return True

    def get_cash_cad(self) -> float:
        return 100.0

    def get_positions(self):
        return self._holdings

    def place_order(self, order: Order, *, live: bool) -> Fill:
        self.orders.append(order)
        return Fill(
            client_order_id=order.client_order_id, venue=self.venue,
            symbol=order.symbol, side=order.side,
            filled_qty=order.base_qty or 1.0, avg_price=0.0357,
            fee_cad=0.4, fx_cost_cad=0.0,
            filled_at=dt.datetime.now(dt.timezone.utc),
            is_live=bool(live and self._live_fills),
            raw={"txid": ["TX-123"]},
        )


US_HOLDING = {"symbol": "US", "qty": 4361.8582, "market_value_cad": 155.67}


# ---- find_untracked (pure, shared with the checkpoint reconciliation) ---------------

def test_find_untracked_is_pure_and_skips_dust_and_tracked():
    held = [
        US_HOLDING,
        {"symbol": "SOL", "qty": 0.2, "market_value_cad": 52.0},
        {"symbol": "DUST", "qty": 1e-9, "market_value_cad": 0.0},
    ]
    orphans = find_untracked(held, {"SOL"})
    assert orphans == [{"asset": "US", "qty": 4361.8582, "market_value_cad": 155.67}]
    assert find_untracked(None, set()) == []


def test_untracked_holdings_ignores_other_venue_positions():
    repo = InMemoryRepository()
    repo.save_open_position(_pos("SOLUSD", qty=0.2))
    broker = VenueBroker([US_HOLDING, {"symbol": "SOL", "qty": 0.2, "market_value_cad": 52.0}])
    assert [o["asset"] for o in untracked_holdings(repo, broker)] == ["US"]


# ---- adopt ---------------------------------------------------------------------------

def test_adopt_creates_live_decision_and_position_and_clears_the_orphan():
    repo = InMemoryRepository()
    broker = VenueBroker([US_HOLDING])
    pos = adopt_untracked(repo, broker, "US", stop_fraction=0.15, horizon_days=3.0)

    # The FK parent exists and marks itself as an adoption, not a pitch win.
    decisions = [d for d, _ in repo.decisions]
    assert len(decisions) == 1
    d = decisions[0]
    assert d.kind == DecisionKind.FUND and d.live and d.pitch_id is None
    assert "ADOPTED" in d.rationale

    # The position is LIVE with the venue's real quantity — a close() must sell it.
    assert pos.live and pos.qty == pytest.approx(4361.8582)
    assert pos.symbol == "USUSD" and pos.venue == "kraken"
    assert pos.size_cad == pytest.approx(155.67)
    assert pos.stop_fraction == 0.15 and pos.horizon_days == 3.0
    assert pos.band_high == 0.0  # no take-profit: stop + horizon manage it
    assert repo.open_positions() == [pos]
    assert any(e == "position_adopted" for e, _ in repo.audit_log)

    # Once adopted it is no longer an orphan.
    assert untracked_holdings(repo, broker) == []


def test_adopt_refuses_missing_tracked_or_unpriced_assets():
    repo = InMemoryRepository()
    broker = VenueBroker([US_HOLDING, {"symbol": "XYZ", "qty": 5.0, "market_value_cad": None}])

    with pytest.raises(ValueError, match="not an untracked holding"):
        adopt_untracked(repo, broker, "SOL")
    with pytest.raises(ValueError, match="no live market value"):
        adopt_untracked(repo, broker, "XYZ")

    adopt_untracked(repo, broker, "US")
    with pytest.raises(ValueError, match="not an untracked holding"):
        adopt_untracked(repo, broker, "US")  # already tracked now


def test_adopt_validates_parameters():
    repo = InMemoryRepository()
    broker = VenueBroker([US_HOLDING])
    with pytest.raises(ValueError, match="stop_fraction"):
        adopt_untracked(repo, broker, "US", stop_fraction=1.5)
    with pytest.raises(ValueError, match="horizon_days"):
        adopt_untracked(repo, broker, "US", horizon_days=0.0)


def test_build_adoption_numbers_are_deterministic():
    now = dt.datetime(2026, 7, 15, 12, 0, tzinfo=dt.timezone.utc)
    decision, pos = build_adoption(
        "US", 4361.8582, 155.67, stop_fraction=0.15, horizon_days=3.0, now=now
    )
    assert decision.decision_id == pos.decision_id
    assert pos.opened_at == now and decision.created_at == now
    assert pos.cost_cad == pytest.approx(155.67 * 0.0026, abs=0.01)  # the exit taker fee
    assert pos.predicted_return == 0.0 and pos.predicted_confidence == 0.5


# ---- sell ----------------------------------------------------------------------------

def test_sell_untracked_sells_full_qty_and_records_the_fill_first():
    repo = InMemoryRepository()
    broker = VenueBroker([US_HOLDING])
    fill = sell_untracked(repo, broker, "US", live=True)

    assert fill.is_live
    order = broker.orders[0]
    assert order.side == OrderSide.SELL and order.symbol == "USUSD"
    assert order.base_qty == pytest.approx(4361.8582)

    assert len(repo.fills) == 1
    row = repo.fills[0]
    assert row["side"] == "sell" and row["is_live"]
    assert row["exit_reason"] == "untracked_sell"
    assert row["order_ref"] == "TX-123"
    assert row["decision_id"] is None  # nothing decided the original buy
    assert any(e == "untracked_sold" for e, _ in repo.audit_log)
    assert repo.open_positions() == []  # selling never invents a tracked position


def test_sell_untracked_requires_the_live_gate_and_a_live_fill():
    repo = InMemoryRepository()

    with pytest.raises(RuntimeError, match="live gate"):
        sell_untracked(repo, VenueBroker([US_HOLDING]), "US", live=False)

    # The broker declining to go live (e.g. no creds) must record NOTHING.
    paper_broker = VenueBroker([US_HOLDING], live_fills=False)
    with pytest.raises(RuntimeError, match="refused to go live"):
        sell_untracked(repo, paper_broker, "US", live=True)
    assert repo.fills == [] and repo.audit_log == []

    with pytest.raises(ValueError, match="not an untracked holding"):
        sell_untracked(repo, VenueBroker([US_HOLDING]), "SOL", live=True)


# ---- resolution fallback: an adopted (or scan-dropped) coin can still price ----------

def test_resolution_lookup_falls_back_to_direct_ohlc_for_unscanned_coins():
    from boardroom.data.sources import synthetic_bars
    from boardroom.factory import build_default_org

    repo = InMemoryRepository()
    fetched: list[str] = []

    def fake_ohlc(pair: str):
        fetched.append(pair)
        if pair == "USUSD":
            return synthetic_bars("USUSD", Venue.KRAKEN, n=60, seed=7, drift=0.0, vol=0.03)
        raise RuntimeError("no market")

    org = build_default_org(
        data_mode="synthetic", repo=repo, resolution_bars_fallback=fake_ohlc
    )
    pos = _pos("USUSD", qty=4361.8582)
    lookup = org._resolution_price_lookup()

    bars = lookup(pos)
    assert bars is not None and bars.symbol == "USUSD"
    # Second lookup hits the per-checkpoint cache — no refetch.
    assert lookup(pos) is bars
    assert fetched == ["USUSD"]

    # A coin with no market anywhere is tried once per pair, then left to the
    # resolution_no_data audit — never a crash, never a refetch storm.
    ghost = _pos("GHOSTUSD")
    assert lookup(ghost) is None and lookup(ghost) is None
    assert fetched.count("GHOSTUSD") == 1


def test_resolution_lookup_without_fallback_stays_offline():
    from boardroom.factory import build_default_org

    org = build_default_org(data_mode="synthetic", repo=InMemoryRepository())
    assert org.resolution_bars_fallback is None
    assert org._resolution_price_lookup()(_pos("USUSD")) is None
