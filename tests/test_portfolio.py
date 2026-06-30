"""Portfolio snapshot assembly — crypto + stocks + merged, with performance.

Pure computation over raw broker position dicts: weights, P&L, the venue split,
and the day's top movers. Missing prices degrade to None, never a fabricated value.
"""

from __future__ import annotations

import pytest

from boardroom.brokers.kraken import KrakenBroker, _normalize_kraken_asset
from boardroom.brokers.stub import StubBroker
from boardroom.portfolio import build_portfolio_snapshot
from boardroom.schemas import Venue


def test_merged_totals_and_split():
    snap = build_portfolio_snapshot(
        generated_at="t",
        kraken_cash_cad=100.0,
        kraken_positions=[{"symbol": "XBT", "qty": 0.001, "market_value_cad": 150.0, "day_change_pct": 0.03}],
        ibkr_cash_cad=50.0,
        ibkr_positions=[{"symbol": "AAPL", "qty": 2, "avg_cost": 90.0, "market_value_cad": 200.0,
                         "unrealized_pnl_cad": 20.0, "day_change_pct": 0.012}],
    ).as_dict()
    # crypto total = 100 cash + 150 = 250; stocks = 50 + 200 = 250; total 500
    assert snap["crypto"]["total_value_cad"] == 250.0
    assert snap["stocks"]["total_value_cad"] == 250.0
    assert snap["total_value_cad"] == 500.0
    assert snap["crypto_weight"] == pytest.approx(0.5)
    assert snap["stocks_weight"] == pytest.approx(0.5)


def test_stock_unrealized_pnl_pct_from_cost_basis():
    snap = build_portfolio_snapshot(
        generated_at="t", kraken_cash_cad=None, kraken_positions=[],
        ibkr_cash_cad=0.0,
        ibkr_positions=[{"symbol": "AAPL", "qty": 2, "market_value_cad": 200.0,
                         "unrealized_pnl_cad": 20.0, "day_change_pct": 0.0}],
    )
    h = snap.stocks.holdings[0]
    # cost basis = 200 - 20 = 180; pnl% = 20/180
    assert h.unrealized_pnl_pct == pytest.approx(20.0 / 180.0, abs=1e-4)
    assert snap.stocks.unrealized_pnl_cad == 20.0


def test_top_movers_rank_across_both_venues():
    snap = build_portfolio_snapshot(
        generated_at="t",
        kraken_cash_cad=0.0,
        kraken_positions=[
            {"symbol": "XBT", "qty": 1, "market_value_cad": 100.0, "day_change_pct": 0.05},
            {"symbol": "ETH", "qty": 1, "market_value_cad": 100.0, "day_change_pct": -0.04},
        ],
        ibkr_cash_cad=0.0,
        ibkr_positions=[
            {"symbol": "AAPL", "qty": 1, "market_value_cad": 100.0, "day_change_pct": 0.02},
        ],
    )
    assert snap.top_gainers[0]["symbol"] == "XBT"   # +5% leads
    assert snap.top_losers[0]["symbol"] == "ETH"    # -4% worst
    # AAPL (+2%) is a gainer, not a loser.
    assert all(m["day_change_pct"] > 0 for m in snap.top_gainers)
    assert all(m["day_change_pct"] < 0 for m in snap.top_losers)


def test_coin_without_price_is_listed_not_dropped():
    snap = build_portfolio_snapshot(
        generated_at="t",
        kraken_cash_cad=10.0,
        kraken_positions=[{"symbol": "OBSCURE", "qty": 5.0, "market_value_cad": None, "day_change_pct": None}],
        ibkr_cash_cad=None, ibkr_positions=[],
    )
    coin = snap.crypto.holdings[0]
    assert coin.symbol == "OBSCURE" and coin.qty == 5.0
    assert coin.market_value_cad is None and coin.weight is None
    # Unpriced holding doesn't count toward value; cash still does.
    assert snap.crypto.total_value_cad == 10.0
    # An unpriced holding can't be a mover.
    assert snap.top_gainers == [] and snap.top_losers == []


def test_weights_sum_within_priced_book():
    snap = build_portfolio_snapshot(
        generated_at="t",
        kraken_cash_cad=0.0,
        kraken_positions=[
            {"symbol": "XBT", "qty": 1, "market_value_cad": 75.0, "day_change_pct": 0.0},
            {"symbol": "ETH", "qty": 1, "market_value_cad": 25.0, "day_change_pct": 0.0},
        ],
        ibkr_cash_cad=None, ibkr_positions=[],
    )
    weights = [h.weight for h in snap.crypto.holdings]
    assert sum(weights) == pytest.approx(1.0)
    assert snap.crypto.holdings[0].symbol == "XBT"  # biggest first


def test_empty_everything_is_safe():
    snap = build_portfolio_snapshot(
        generated_at="t", kraken_cash_cad=None, kraken_positions=[],
        ibkr_cash_cad=None, ibkr_positions=[],
    ).as_dict()
    assert snap["total_value_cad"] == 0.0
    assert snap["crypto_weight"] == 0.0 and snap["stocks_weight"] == 0.0
    assert snap["top_gainers"] == [] and snap["top_losers"] == []


# ---- broker helpers ---------------------------------------------------------
@pytest.mark.parametrize(
    "code,expected",
    [("XXBT", "XBT"), ("XETH", "ETH"), ("XXRP", "XRP"), ("SOL", "SOL"),
     ("ADA", "ADA"), ("DOT.S", "DOT"), ("ETH2.S", "ETH2"), ("USDC", "USDC")],
)
def test_normalize_kraken_asset(code, expected):
    assert _normalize_kraken_asset(code) == expected


def test_kraken_positions_empty_without_creds():
    # Test env strips creds → no positions, no crash, no network.
    assert KrakenBroker().get_positions() == []


def test_stub_positions_empty():
    assert StubBroker(Venue.KRAKEN).get_positions() == []
