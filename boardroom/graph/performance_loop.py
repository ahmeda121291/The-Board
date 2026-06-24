"""Performance loop (scope §10): daily snapshot + weekly readout, and the
circuit breaker that auto-de-risks ALL capital to the floor when drawdown or fee
drag crosses a limit.
"""

from __future__ import annotations

from dataclasses import dataclass

from boardroom.config import get_settings
from boardroom.measurement.performance import compute_performance
from boardroom.persistence.repository import Repository, get_repository
from boardroom.risk.caps import PortfolioState, circuit_breaker_tripped
from boardroom.schemas import Division


@dataclass
class WeeklyReadout:
    text: str
    breaker_tripped: list[str]


def run_performance_loop(
    *,
    carry_apr: float,
    period_days: float,
    bnh_start: float,
    bnh_end: float,
    starting_equity_cad: float,
    portfolio: PortfolioState,
    repo: Repository | None = None,
) -> WeeklyReadout:
    repo = repo or get_repository()
    settings = get_settings()
    outcomes = repo.recent_outcomes(limit=1000)

    report = compute_performance(
        outcomes,
        carry_apr=carry_apr,
        period_days=period_days,
        bnh_start=bnh_start,
        bnh_end=bnh_end,
        starting_equity_cad=starting_equity_cad,
    )
    tripped = circuit_breaker_tripped(portfolio, settings.caps)

    lines = ["# Boardroom weekly readout", ""]
    lines += report.summary_lines()
    if tripped:
        lines += ["", "CIRCUIT BREAKER TRIPPED — all capital forced to the floor:"]
        lines += [f"  - {t}" for t in tripped]
        repo.audit("circuit_breaker", {"reasons": tripped})
    else:
        lines += ["", "Circuit breakers: all clear."]

    text = "\n".join(lines)
    payload = {
        "net_roi": report.net_roi,
        "attribution": report.attribution,
        "hit_rate": report.hit_rate,
        "excess_vs_floor": report.benchmark.excess_vs_floor,
        "excess_vs_bnh": report.benchmark.excess_vs_bnh,
        "cost_drag_pct": report.cost_drag_pct,
        "breaker": tripped,
    }
    repo.save_performance(payload)
    repo.save_weekly_report(text, payload)
    return WeeklyReadout(text=text, breaker_tripped=tripped)


def division_names() -> list[str]:
    return [d.value for d in Division]
