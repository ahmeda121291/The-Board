"""Pure, deterministic feature functions — the computational spine (scope §5).

These are the numbers a division computes and an explicit model maps to
``expected_return`` / ``win_probability``. The LLM reasons; this code calculates.
"""

from __future__ import annotations

from boardroom.features.technical import (
    drawdown,
    liquidity_proxy,
    max_drawdown,
    momentum,
    realized_sharpe,
    rolling_correlation,
    rsi,
    volatility,
    zscore_meanrev,
)

__all__ = [
    "momentum",
    "volatility",
    "zscore_meanrev",
    "drawdown",
    "max_drawdown",
    "rolling_correlation",
    "realized_sharpe",
    "liquidity_proxy",
    "rsi",
]
