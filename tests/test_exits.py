"""Auto-sell exits: take-profit trigger + real-sell gating on resolution.

The system now SELLS to close (stop-loss / take-profit / horizon), not just
books paper P&L. A resolution only finalizes when the sell actually executes, so
the record never claims a sale that didn't happen.
"""

from __future__ import annotations

from boardroom.brokers.base import Order, OrderSide
from boardroom.brokers.stub import StubBroker
from boardroom.graph.resolution_loop import resolve_open_positions, resolve_position
from boardroom.persistence.repository import InMemoryRepository
from boardroom.schemas import Venue

from tests.test_resolution_loop import _bars, _pos


# ---- take-profit exit -------------------------------------------------------
def test_take_profit_exits_before_horizon():
    pos = _pos(horizon_days=30.0, band_high=0.05, stop_fraction=0.10)
    bars = _bars([100.0, 101.0, 103.0, 106.0, 106.0, 106.0])  # +6% on day 3, well before horizon
    out = resolve_position(pos, bars)
    assert out is not None
    assert out.realized_return >= 0.05      # exited at the take-profit, not at +0 horizon drift
    assert out.win is True


# ---- a failed sell must NOT finalize the position ---------------------------
def test_failed_exit_keeps_position_open_and_books_nothing():
    repo = InMemoryRepository()
    repo.save_open_position(_pos(decision_id="live1", live=True, qty=0.5))
    bars = _bars([100.0, 101.0, 102.0, 105.0, 106.0, 107.0])  # ready to resolve (win)

    called = {}
    def closer(pos, outcome):
        called["hit"] = True
        return False  # the sell was rejected

    updates = resolve_open_positions(repo, lambda pos: bars, close_live=closer)
    assert called.get("hit")
    assert updates == []
    assert len(repo.open_positions()) == 1          # left open to retry
    assert repo.recent_outcomes() == []             # no fictional realized P&L


def test_successful_exit_closes_and_books():
    repo = InMemoryRepository()
    repo.save_open_position(_pos(decision_id="live2", live=True, qty=0.5))
    bars = _bars([100.0, 101.0, 102.0, 105.0, 106.0, 107.0])

    updates = resolve_open_positions(repo, lambda pos: bars, close_live=lambda p, o: True)
    assert len(updates) == 1
    assert repo.open_positions() == []
    assert len(repo.recent_outcomes()) == 1


# ---- selling the exact held quantity ----------------------------------------
def test_sell_order_uses_exact_base_qty():
    b = StubBroker(Venue.KRAKEN)
    fill = b.place_order(
        Order(symbol="XBTCAD", side=OrderSide.SELL, notional_cad=25.0,
              division="crypto_trend", client_order_id="x", base_qty=0.123),
        live=False,
    )
    assert fill.filled_qty == 0.123  # sells what's held, not a notional-derived size


# ---- orchestrator closer: paper resolves; live can't close on a stub --------
def test_orchestrator_closer_paper_vs_live():
    from boardroom.factory import build_default_org

    org = build_default_org(data_mode="synthetic")  # stub brokers

    class _Outcome:
        realized_return = 0.05
        pnl_cad = 2.0

    paper = _pos(decision_id="p", live=False)
    live = _pos(decision_id="l", live=True, venue="kraken", qty=0.5)
    assert org._close_position_live(paper, _Outcome()) is True   # nothing to sell
    assert org._close_position_live(live, _Outcome()) is False   # stub can't close a real position
