"""Performance: the Analyst's answer to question (A) — *did the account grow?*

This is pure P&L accounting, all NET of cost. It says nothing about whether any
individual decision was *sound* (that is the Critic's job, see ``critic.py``).
The two must never be conflated (scope §8): you can grow the account on luck and
shrink it on good process.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from boardroom.schemas import ResolvedOutcome

from .benchmarks import BenchmarkComparison, compare


@dataclass
class PerformanceReport:
    """The Analyst's deterministic P&L summary for a set of resolved outcomes."""

    n_outcomes: int
    net_roi: float
    attribution: dict[str, float]
    hit_rate: float
    avg_win: float
    avg_loss: float
    profit_factor: float | None
    total_cost_cad: float
    cost_drag_pct: float
    sharpe: float
    max_drawdown_cad: float
    benchmark: BenchmarkComparison
    starting_equity_cad: float = field(default=0.0)

    def summary_lines(self) -> list[str]:
        """Plain-language report lines (no numbers an LLM has to invent)."""
        pf = (
            "inf"
            if self.profit_factor is None
            else f"{self.profit_factor:.2f}"
        )
        lines = [
            f"Resolved {self.n_outcomes} decision(s).",
            f"Net ROI: {self.net_roi * 100:.2f}% on "
            f"${self.starting_equity_cad:.2f} starting equity.",
            f"Hit rate: {self.hit_rate * 100:.1f}%.",
            f"Average win: ${self.avg_win:.2f}; average loss: ${self.avg_loss:.2f}.",
            f"Profit factor: {pf}.",
            f"Cost drag: ${self.total_cost_cad:.2f} "
            f"({self.cost_drag_pct * 100:.2f}% of equity).",
            f"Sharpe-style ratio: {self.sharpe:.2f}.",
            f"Max drawdown: ${self.max_drawdown_cad:.2f}.",
        ]
        for div, pnl in sorted(self.attribution.items()):
            lines.append(f"  {div}: ${pnl:.2f}")
        lines.append(
            f"Excess vs floor: {self.benchmark.excess_vs_floor * 100:.2f}%; "
            f"excess vs buy-and-hold: {self.benchmark.excess_vs_bnh * 100:.2f}%."
        )
        return lines


def _max_drawdown_cad(pnls: list[float]) -> float:
    """Max drawdown over the cumulative-pnl path. Always <= 0."""
    if not pnls:
        return 0.0
    cumulative = 0.0
    peak = 0.0
    max_dd = 0.0
    for pnl in pnls:
        cumulative += pnl
        if cumulative > peak:
            peak = cumulative
        drawdown = cumulative - peak  # <= 0
        if drawdown < max_dd:
            max_dd = drawdown
    return max_dd


def _sharpe(returns: list[float]) -> float:
    """Mean / population-std over per-outcome realized returns. 0 if undefined."""
    n = len(returns)
    if n < 2:
        return 0.0
    mean = sum(returns) / n
    variance = sum((r - mean) ** 2 for r in returns) / n
    std = math.sqrt(variance)
    if std == 0:
        return 0.0
    return mean / std


def compute_performance(
    outcomes: list[ResolvedOutcome],
    *,
    carry_apr: float,
    period_days: float,
    bnh_start: float,
    bnh_end: float,
    starting_equity_cad: float,
) -> PerformanceReport:
    """Compute a full :class:`PerformanceReport`, all net of cost."""
    n = len(outcomes)

    total_pnl = sum(o.pnl_cad for o in outcomes)
    net_roi = total_pnl / starting_equity_cad if starting_equity_cad else 0.0

    attribution: dict[str, float] = {}
    for o in outcomes:
        key = o.division.value
        attribution[key] = attribution.get(key, 0.0) + o.pnl_cad

    hit_rate = (sum(1 for o in outcomes if o.win) / n) if n else 0.0

    wins = [o.pnl_cad for o in outcomes if o.pnl_cad > 0]
    losses = [o.pnl_cad for o in outcomes if o.pnl_cad < 0]
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0

    sum_wins = sum(wins)
    sum_losses = abs(sum(losses))
    if sum_losses == 0:
        profit_factor: float | None = None if sum_wins > 0 else 0.0
    else:
        profit_factor = sum_wins / sum_losses

    total_cost = sum(o.cost_cad for o in outcomes)
    cost_drag_pct = total_cost / starting_equity_cad if starting_equity_cad else 0.0

    sharpe = _sharpe([o.realized_return for o in outcomes])
    max_dd = _max_drawdown_cad([o.pnl_cad for o in outcomes])

    benchmark = compare(
        strategy_return=net_roi,
        carry_apr=carry_apr,
        days=period_days,
        start_price=bnh_start,
        end_price=bnh_end,
    )

    return PerformanceReport(
        n_outcomes=n,
        net_roi=net_roi,
        attribution=attribution,
        hit_rate=hit_rate,
        avg_win=avg_win,
        avg_loss=avg_loss,
        profit_factor=profit_factor,
        total_cost_cad=total_cost,
        cost_drag_pct=cost_drag_pct,
        sharpe=sharpe,
        max_drawdown_cad=max_dd,
        benchmark=benchmark,
        starting_equity_cad=starting_equity_cad,
    )
