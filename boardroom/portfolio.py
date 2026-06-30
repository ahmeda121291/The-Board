"""Portfolio snapshot — what you actually hold, across both venues.

Assembles three views the dashboard renders:
  - **Crypto (Kraken):** coins held + value + intraday change, and cash left.
  - **Stocks (IBKR):** holdings + value + unrealized P&L + intraday change, cash.
  - **Merged:** total equity, the crypto/stock split, and the day's top movers.

Pure and deterministic: it takes already-fetched cash + raw position dicts (from
the brokers) and computes every derived number — weights, P&L, the split. Nothing
here is an LLM guess (scope §2). Missing inputs (an un-synced venue, a coin with no
CAD market) degrade to ``None`` rather than a fabricated value.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class HoldingView:
    symbol: str
    venue: str
    qty: float
    market_value_cad: float | None
    weight: float | None = None              # share of this venue's book
    avg_cost: float | None = None
    unrealized_pnl_cad: float | None = None
    unrealized_pnl_pct: float | None = None
    day_change_pct: float | None = None

    def as_dict(self) -> dict:
        def r(x, n=2):
            return round(x, n) if isinstance(x, (int, float)) else None
        return {
            "symbol": self.symbol,
            "venue": self.venue,
            "qty": r(self.qty, 8),
            "market_value_cad": r(self.market_value_cad),
            "weight": r(self.weight, 4),
            "avg_cost": r(self.avg_cost, 4),
            "unrealized_pnl_cad": r(self.unrealized_pnl_cad),
            "unrealized_pnl_pct": r(self.unrealized_pnl_pct, 4),
            "day_change_pct": r(self.day_change_pct, 4),
        }


@dataclass
class VenueBook:
    venue: str
    cash_cad: float | None
    holdings: list[HoldingView] = field(default_factory=list)
    holdings_value_cad: float = 0.0
    total_value_cad: float | None = None
    unrealized_pnl_cad: float | None = None

    def as_dict(self) -> dict:
        def r(x):
            return round(x, 2) if isinstance(x, (int, float)) else None
        return {
            "venue": self.venue,
            "cash_cad": r(self.cash_cad),
            "holdings": [h.as_dict() for h in self.holdings],
            "holdings_value_cad": r(self.holdings_value_cad),
            "total_value_cad": r(self.total_value_cad),
            "unrealized_pnl_cad": r(self.unrealized_pnl_cad),
        }


@dataclass
class PortfolioSnapshot:
    generated_at: str
    crypto: VenueBook
    stocks: VenueBook
    total_value_cad: float
    crypto_weight: float
    stocks_weight: float
    top_gainers: list[dict] = field(default_factory=list)
    top_losers: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "crypto": self.crypto.as_dict(),
            "stocks": self.stocks.as_dict(),
            "total_value_cad": round(self.total_value_cad, 2),
            "crypto_weight": round(self.crypto_weight, 4),
            "stocks_weight": round(self.stocks_weight, 4),
            "top_gainers": self.top_gainers,
            "top_losers": self.top_losers,
        }


def _build_book(venue: str, cash_cad: float | None, raw_positions: list[dict]) -> VenueBook:
    """Turn one venue's cash + raw position dicts into a valued, weighted book."""
    holdings: list[HoldingView] = []
    for p in raw_positions or []:
        mv = p.get("market_value_cad")
        mv = float(mv) if isinstance(mv, (int, float)) else None
        avg_cost = p.get("avg_cost")
        avg_cost = float(avg_cost) if isinstance(avg_cost, (int, float)) and avg_cost else None
        upnl = p.get("unrealized_pnl_cad")
        upnl = float(upnl) if isinstance(upnl, (int, float)) else None
        qty = float(p.get("qty", 0.0) or 0.0)
        # Unrealized P&L % vs cost, when we know both the P&L and the cost basis.
        upnl_pct = None
        if upnl is not None and mv is not None:
            cost_basis = mv - upnl
            if cost_basis > 0:
                upnl_pct = upnl / cost_basis
        day = p.get("day_change_pct")
        day = float(day) if isinstance(day, (int, float)) else None
        holdings.append(
            HoldingView(
                symbol=p.get("symbol", ""),
                venue=venue,
                qty=qty,
                market_value_cad=mv,
                avg_cost=avg_cost,
                unrealized_pnl_cad=upnl,
                unrealized_pnl_pct=upnl_pct,
                day_change_pct=day,
            )
        )

    holdings_value = sum(h.market_value_cad for h in holdings if h.market_value_cad is not None)
    # Per-holding weight within the venue book (priced holdings only).
    for h in holdings:
        if h.market_value_cad is not None and holdings_value > 0:
            h.weight = h.market_value_cad / holdings_value
    pnl_known = [h.unrealized_pnl_cad for h in holdings if h.unrealized_pnl_cad is not None]
    total = None
    if cash_cad is not None or holdings:
        total = round((cash_cad or 0.0) + holdings_value, 2)
    # Sort biggest position first for display.
    holdings.sort(key=lambda h: (h.market_value_cad or 0.0), reverse=True)
    return VenueBook(
        venue=venue,
        cash_cad=cash_cad,
        holdings=holdings,
        holdings_value_cad=round(holdings_value, 2),
        total_value_cad=total,
        unrealized_pnl_cad=round(sum(pnl_known), 2) if pnl_known else None,
    )


def build_portfolio_snapshot(
    *,
    generated_at: str,
    kraken_cash_cad: float | None,
    kraken_positions: list[dict],
    ibkr_cash_cad: float | None,
    ibkr_positions: list[dict],
    movers_top_n: int = 3,
) -> PortfolioSnapshot:
    """Assemble the full crypto + stocks + merged snapshot from real broker data."""
    crypto = _build_book("kraken", kraken_cash_cad, kraken_positions)
    stocks = _build_book("ibkr", ibkr_cash_cad, ibkr_positions)

    crypto_total = crypto.total_value_cad or 0.0
    stocks_total = stocks.total_value_cad or 0.0
    total = round(crypto_total + stocks_total, 2)
    crypto_w = (crypto_total / total) if total > 0 else 0.0
    stocks_w = (stocks_total / total) if total > 0 else 0.0

    # Top movers across BOTH books, ranked by intraday change (the metric we have
    # for every priced holding). Only priced holdings with a known day change.
    movers = [
        {
            "symbol": h.symbol,
            "venue": h.venue,
            "day_change_pct": h.day_change_pct,
            "market_value_cad": h.market_value_cad,
        }
        for h in (*crypto.holdings, *stocks.holdings)
        if h.day_change_pct is not None and h.market_value_cad is not None
    ]
    gainers = sorted(movers, key=lambda m: m["day_change_pct"], reverse=True)
    losers = sorted(movers, key=lambda m: m["day_change_pct"])
    top_gainers = [m for m in gainers if m["day_change_pct"] > 0][:movers_top_n]
    top_losers = [m for m in losers if m["day_change_pct"] < 0][:movers_top_n]

    return PortfolioSnapshot(
        generated_at=generated_at,
        crypto=crypto,
        stocks=stocks,
        total_value_cad=total,
        crypto_weight=crypto_w,
        stocks_weight=stocks_w,
        top_gainers=top_gainers,
        top_losers=top_losers,
    )
