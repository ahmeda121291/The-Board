"""Hard caps and circuit breakers — enforced outside any agent's control.

The CEO allocates *within* these; it can never widen them. Any breach forces all
capital back to the floor (scope §7, §10). These functions are pure so the rules
are unit-testable in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass

from boardroom.config import RiskCaps
from boardroom.schemas import Division


@dataclass(frozen=True)
class PortfolioState:
    """Just enough live state to evaluate the breakers."""

    equity_cad: float           # current total account value
    peak_equity_cad: float      # high-water mark, for drawdown
    realized_pnl_today_cad: float
    cumulative_cost_cad: float
    #: Retained for callers/tests; no longer the fee-drag denominator (equity is).
    cumulative_gross_return_cad: float


@dataclass(frozen=True)
class CapVerdict:
    allowed: bool
    clamped_size_cad: float
    reasons: list[str]


def clamp_size(
    *,
    division: Division,
    requested_cad: float,
    caps: RiskCaps,
    deployed_cad: float,
    portfolio_value_cad: float,
) -> CapVerdict:
    """Clamp a requested position to the hard caps (percent of portfolio value).
    Never raises; always returns the largest *permitted* size (possibly 0) plus
    the reasons it was clamped.
    """
    reasons: list[str] = []
    size = max(0.0, requested_cad)

    per_trade = caps.cap_for(division.value, portfolio_value_cad)
    if size > per_trade:
        reasons.append(
            f"clamped to per-trade/division cap {per_trade:.2f} CAD "
            f"({caps.per_trade_max_pct:.0%} of portfolio)"
        )
        size = per_trade

    headroom = max(0.0, caps.deployable_cad(portfolio_value_cad) - deployed_cad)
    if size > headroom:
        reasons.append(f"clamped to deployable headroom {headroom:.2f} CAD")
        size = headroom

    return CapVerdict(allowed=size > 0, clamped_size_cad=size, reasons=reasons)


def circuit_breaker_tripped(state: PortfolioState, caps: RiskCaps) -> list[str]:
    """Return the list of tripped breakers (empty == all clear).

    Any non-empty result means: force ALL capital to the floor immediately.
    The daily-loss limit is a percent of current equity.
    """
    tripped: list[str] = []

    daily_limit = caps.daily_loss_limit_cad(state.equity_cad)
    if -state.realized_pnl_today_cad >= daily_limit:
        tripped.append(
            f"daily loss {-state.realized_pnl_today_cad:.2f} CAD >= limit "
            f"{daily_limit:.2f} ({caps.daily_loss_limit_pct:.0%} of equity)"
        )

    if state.peak_equity_cad > 0:
        drawdown = 1.0 - (state.equity_cad / state.peak_equity_cad)
        if drawdown >= caps.max_drawdown_pct:
            tripped.append(
                f"drawdown {drawdown:.1%} >= max {caps.max_drawdown_pct:.1%}"
            )

    # Fee drag is measured against EQUITY (the documented "5% of equity" cap),
    # NOT against gross winning P&L — with a handful of resolved trades that
    # ratio explodes ($0.29 of fees over one $1.15 win read as "25% drag" and
    # froze the system on 2026-07-09). Costs vs the book answers the question
    # the cap asks: is trading activity itself eating the account?
    if state.equity_cad > 0:
        drag = state.cumulative_cost_cad / state.equity_cad
        if drag >= caps.fee_drag_limit_pct:
            tripped.append(
                f"fee drag {drag:.1%} of equity >= limit {caps.fee_drag_limit_pct:.1%}"
            )

    return tripped
