"""Benchmarks: the two hurdles every strategy is judged against (scope §8).

A trade that made money is not automatically good. It must beat the *floor*
(the carry/yield it displaced) and it must beat *buy-and-hold* (doing nothing
but owning the asset). Both comparisons are pure arithmetic on real numbers.
"""

from __future__ import annotations

from dataclasses import dataclass


def floor_return(carry_apr: float, days: float) -> float:
    """The floor hurdle: simple carry accrued over the holding period.

    ``carry_apr`` is an annualized rate (e.g. 0.05 == 5%/yr). The floor is what
    the capital would have earned resting in the yield division, so any active
    bet must clear at least this to justify its risk.
    """
    return carry_apr * (days / 365.0)


def buy_and_hold_return(start_price: float, end_price: float) -> float:
    """The buy-and-hold hurdle: the fractional return of just owning the asset."""
    if start_price == 0:
        raise ValueError("start_price must be non-zero for buy_and_hold_return")
    return end_price / start_price - 1.0


@dataclass
class BenchmarkComparison:
    """How a strategy stacked up against both hurdles."""

    strategy_return: float
    floor_return: float
    buy_and_hold_return: float
    excess_vs_floor: float
    excess_vs_bnh: float

    def beat_floor(self) -> bool:
        return self.excess_vs_floor > 0

    def beat_buy_and_hold(self) -> bool:
        return self.excess_vs_bnh > 0


def compare(
    strategy_return: float,
    carry_apr: float,
    days: float,
    start_price: float,
    end_price: float,
) -> BenchmarkComparison:
    """Build a :class:`BenchmarkComparison` from raw inputs."""
    fr = floor_return(carry_apr, days)
    bnh = buy_and_hold_return(start_price, end_price)
    return BenchmarkComparison(
        strategy_return=strategy_return,
        floor_return=fr,
        buy_and_hold_return=bnh,
        excess_vs_floor=strategy_return - fr,
        excess_vs_bnh=strategy_return - bnh,
    )
