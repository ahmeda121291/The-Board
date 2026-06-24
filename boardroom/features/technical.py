"""Pure technical feature functions — the deterministic spine (scope §5).

Every function here is a PURE, deterministic numpy calculation: no randomness, no
network, no LLM. They consume a 1-D array of closing prices (oldest first) — and
sometimes highs/lows/volumes — and return a plain Python ``float``. These are the
numbers a *division* hands to an explicit model that maps to ``expected_return``
and ``win_probability``. The LLM reasons; this code calculates.

Input convention: ``closes`` is a 1-D numpy array of closing prices, oldest
first. The data layer guarantees length via ``min_rows``, but each function still
defends against too-short input by raising :class:`ValueError`.
"""

from __future__ import annotations

import numpy as np

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


def _as_1d(name: str, arr) -> np.ndarray:
    """Coerce ``arr`` to a 1-D float ndarray or raise :class:`ValueError`."""
    a = np.asarray(arr, dtype=float)
    if a.ndim != 1:
        raise ValueError(f"{name} must be 1-D, got shape {a.shape}")
    return a


def momentum(closes: np.ndarray, lookback: int = 20) -> float:
    """Total simple return over the last ``lookback`` bars.

    ``closes[-1] / closes[-1 - lookback] - 1``. Positive == price trending up; a
    momentum division reads a large positive value as a continuation signal.
    """
    c = _as_1d("closes", closes)
    if lookback < 1:
        raise ValueError(f"lookback must be >= 1, got {lookback}")
    if c.size < lookback + 1:
        raise ValueError(f"closes too short: need {lookback + 1}, got {c.size}")
    prev = c[-1 - lookback]
    if prev == 0:
        raise ValueError("base price is zero; cannot compute momentum")
    return float(c[-1] / prev - 1.0)


def volatility(closes: np.ndarray, lookback: int = 20) -> float:
    """Sample stdev (ddof=1) of the last ``lookback`` per-bar log returns.

    Per-bar, not annualized. Higher == noisier/riskier; a division uses it to
    size positions and to scale expected-return into a probability.
    """
    c = _as_1d("closes", closes)
    if lookback < 2:
        raise ValueError(f"lookback must be >= 2, got {lookback}")
    # Need lookback log-returns -> lookback + 1 prices.
    if c.size < lookback + 1:
        raise ValueError(f"closes too short: need {lookback + 1}, got {c.size}")
    window = c[-(lookback + 1):]
    if np.any(window <= 0):
        raise ValueError("non-positive prices; cannot compute log returns")
    log_rets = np.diff(np.log(window))
    return float(np.std(log_rets, ddof=1))


def zscore_meanrev(closes: np.ndarray, lookback: int = 20) -> float:
    """Mean-reversion z-score of the latest close vs the last ``lookback`` bars.

    ``(closes[-1] - mean) / std`` (std uses ddof=1). Positive == stretched ABOVE
    the mean, which a mean-reversion division reads as a DOWN signal. Returns 0.0
    when the window has zero variance.
    """
    c = _as_1d("closes", closes)
    if lookback < 2:
        raise ValueError(f"lookback must be >= 2, got {lookback}")
    if c.size < lookback:
        raise ValueError(f"closes too short: need {lookback}, got {c.size}")
    window = c[-lookback:]
    sd = float(np.std(window, ddof=1))
    if sd == 0.0:
        return 0.0
    return float((c[-1] - float(np.mean(window))) / sd)


def drawdown(closes: np.ndarray) -> float:
    """Current drawdown from the running peak over the full series.

    ``closes[-1] / max(closes) - 1`` (<= 0). 0.0 means a fresh high; -0.2 means
    the latest close sits 20% below the best price seen.
    """
    c = _as_1d("closes", closes)
    if c.size < 1:
        raise ValueError("closes is empty")
    peak = float(np.max(c))
    if peak == 0:
        raise ValueError("peak price is zero; cannot compute drawdown")
    return float(c[-1] / peak - 1.0)


def max_drawdown(closes: np.ndarray) -> float:
    """Worst peak-to-trough drawdown over the whole series (<= 0).

    The most painful decline an investor would have ridden through. Always
    ``<= drawdown(closes)`` since the current drawdown is one such trough.
    """
    c = _as_1d("closes", closes)
    if c.size < 1:
        raise ValueError("closes is empty")
    running_peak = np.maximum.accumulate(c)
    if np.any(running_peak == 0):
        raise ValueError("non-positive peak price; cannot compute drawdown")
    dd = c / running_peak - 1.0
    return float(np.min(dd))


def rolling_correlation(a: np.ndarray, b: np.ndarray, lookback: int = 20) -> float:
    """Pearson correlation of the last ``lookback`` per-bar simple returns of two series.

    Measures co-movement; a division uses it for diversification / hedging. +1 ==
    move together, -1 == mirror. Returns 0.0 if either return window has zero
    variance (correlation undefined).
    """
    ca = _as_1d("a", a)
    cb = _as_1d("b", b)
    if ca.size != cb.size:
        raise ValueError(f"a and b must be equal length: {ca.size} != {cb.size}")
    if lookback < 2:
        raise ValueError(f"lookback must be >= 2, got {lookback}")
    # Need lookback returns -> lookback + 1 prices.
    if ca.size < lookback + 1:
        raise ValueError(f"series too short: need {lookback + 1}, got {ca.size}")
    ra = np.diff(ca[-(lookback + 1):]) / ca[-(lookback + 1):-1]
    rb = np.diff(cb[-(lookback + 1):]) / cb[-(lookback + 1):-1]
    if np.std(ra) == 0.0 or np.std(rb) == 0.0:
        return 0.0
    corr = float(np.corrcoef(ra, rb)[0, 1])
    if not np.isfinite(corr):
        return 0.0
    return corr


def realized_sharpe(closes: np.ndarray, periods_per_year: int = 252) -> float:
    """Annualized realized Sharpe of per-bar simple returns (risk-free assumed 0).

    ``mean(returns) / stdev(returns) * sqrt(periods_per_year)``. Higher == more
    reward per unit of risk realized over the window. Returns 0.0 if the return
    stdev is 0.
    """
    c = _as_1d("closes", closes)
    if c.size < 2:
        raise ValueError(f"closes too short: need >= 2, got {c.size}")
    if np.any(c[:-1] == 0):
        raise ValueError("zero price in series; cannot compute returns")
    rets = np.diff(c) / c[:-1]
    sd = float(np.std(rets, ddof=1))
    if sd == 0.0:
        return 0.0
    return float(np.mean(rets) / sd * np.sqrt(periods_per_year))


def liquidity_proxy(closes: np.ndarray, volumes: np.ndarray, lookback: int = 20) -> float:
    """Mean dollar volume over the last ``lookback`` bars: ``mean(close * volume)``.

    A crude tradability gate — a division abstains on names where its intended
    position would dwarf typical dollar volume.
    """
    c = _as_1d("closes", closes)
    v = _as_1d("volumes", volumes)
    if c.size != v.size:
        raise ValueError(f"closes and volumes must be equal length: {c.size} != {v.size}")
    if lookback < 1:
        raise ValueError(f"lookback must be >= 1, got {lookback}")
    if c.size < lookback:
        raise ValueError(f"series too short: need {lookback}, got {c.size}")
    dollar_vol = c[-lookback:] * v[-lookback:]
    return float(np.mean(dollar_vol))


def rsi(closes: np.ndarray, lookback: int = 14) -> float:
    """Wilder-style Relative Strength Index over the last ``lookback`` bars, in [0, 100].

    Measures the balance of recent gains vs losses. >70 conventionally reads as
    overbought (mean-reversion DOWN), <30 oversold (UP). Returns 100.0 when there
    are no losses in the window, 0.0 when there are no gains.
    """
    c = _as_1d("closes", closes)
    if lookback < 1:
        raise ValueError(f"lookback must be >= 1, got {lookback}")
    # Need lookback price changes -> lookback + 1 prices.
    if c.size < lookback + 1:
        raise ValueError(f"closes too short: need {lookback + 1}, got {c.size}")
    deltas = np.diff(c[-(lookback + 1):])
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = float(np.mean(gains))
    avg_loss = float(np.mean(losses))
    if avg_loss == 0.0:
        return 100.0 if avg_gain > 0.0 else 50.0
    if avg_gain == 0.0:
        return 0.0
    rs = avg_gain / avg_loss
    return float(100.0 - 100.0 / (1.0 + rs))
