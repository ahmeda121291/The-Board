"""Pure, deterministic feature functions — the computational spine (scope §5).

These are the numbers a division computes and an explicit model maps to
``expected_return`` / ``win_probability``. The LLM reasons; this code calculates.
"""

from __future__ import annotations

from boardroom.features.technical import (
    atr,
    beta,
    bollinger_bandwidth,
    breakout_strength,
    downside_deviation,
    drawdown,
    liquidity_proxy,
    macd_histogram,
    max_drawdown,
    momentum,
    realized_sharpe,
    return_kurtosis,
    return_skew,
    rolling_correlation,
    rsi,
    sortino_ratio,
    volatility,
    volume_surge,
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
    "atr",
    "downside_deviation",
    "sortino_ratio",
    "return_skew",
    "return_kurtosis",
    "macd_histogram",
    "bollinger_bandwidth",
    "beta",
    "volume_surge",
    "breakout_strength",
]
