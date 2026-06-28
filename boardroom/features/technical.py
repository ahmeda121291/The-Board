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
    "atr",
    "downside_deviation",
    "sortino_ratio",
    "return_skew",
    "return_kurtosis",
    "macd_histogram",
    "bollinger_bandwidth",
    "beta",
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


# --------------------------------------------------------------------------- #
# Diligence features — risk-quality measures the divisions and the risk manager
# read to size, gate, and diversify. All pure, deterministic numpy.
# --------------------------------------------------------------------------- #
def _simple_returns(closes: np.ndarray) -> np.ndarray:
    """Per-bar simple returns ``c[t]/c[t-1] - 1``; raises on a zero price."""
    if np.any(closes[:-1] == 0):
        raise ValueError("zero price in series; cannot compute returns")
    return np.diff(closes) / closes[:-1]


def atr(
    highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, lookback: int = 14
) -> float:
    """Average True Range over the last ``lookback`` bars (Wilder's TR, simple mean).

    True range per bar is ``max(high-low, |high-prev_close|, |low-prev_close|)``;
    ATR averages it. Unlike :func:`volatility` (a return stdev) this is in *price*
    units and captures intraday gaps — a sturdier stop-distance input. Returns a
    non-negative float.
    """
    h = _as_1d("highs", highs)
    low_arr = _as_1d("lows", lows)
    c = _as_1d("closes", closes)
    if not (h.size == low_arr.size == c.size):
        raise ValueError(
            f"highs/lows/closes must be equal length: {h.size}/{low_arr.size}/{c.size}"
        )
    if lookback < 1:
        raise ValueError(f"lookback must be >= 1, got {lookback}")
    # Need a previous close for each TR -> lookback + 1 bars.
    if c.size < lookback + 1:
        raise ValueError(f"series too short: need {lookback + 1}, got {c.size}")
    h = h[-(lookback + 1):]
    low_arr = low_arr[-(lookback + 1):]
    c = c[-(lookback + 1):]
    prev_close = c[:-1]
    tr = np.maximum.reduce(
        [
            h[1:] - low_arr[1:],
            np.abs(h[1:] - prev_close),
            np.abs(low_arr[1:] - prev_close),
        ]
    )
    return float(np.mean(tr))


def downside_deviation(closes: np.ndarray, mar: float = 0.0) -> float:
    """Root-mean-square of per-bar returns that fall below ``mar`` (downside risk).

    Only losses count toward the dispersion (upside is not "risk"); the mean is
    taken over *all* periods, so a series with few, shallow drawdowns scores low.
    Returns a non-negative float; 0.0 when nothing dips below ``mar``.
    """
    c = _as_1d("closes", closes)
    if c.size < 2:
        raise ValueError(f"closes too short: need >= 2, got {c.size}")
    rets = _simple_returns(c)
    shortfall = np.minimum(0.0, rets - mar)
    return float(np.sqrt(np.mean(shortfall**2)))


def sortino_ratio(
    closes: np.ndarray, periods_per_year: int = 252, mar: float = 0.0
) -> float:
    """Annualized Sortino ratio: excess mean return per unit of *downside* risk.

    Like :func:`realized_sharpe` but penalizes only downside volatility, so a
    smooth grinder isn't dinged for upside variance. Returns 0.0 when there is no
    downside deviation in the window.
    """
    c = _as_1d("closes", closes)
    if c.size < 2:
        raise ValueError(f"closes too short: need >= 2, got {c.size}")
    rets = _simple_returns(c)
    dd = downside_deviation(c, mar=mar)
    if dd == 0.0:
        return 0.0
    return float((np.mean(rets) - mar) / dd * np.sqrt(periods_per_year))


def return_skew(closes: np.ndarray) -> float:
    """Skewness of per-bar simple returns (Fisher-Pearson, population moment).

    Negative skew == fat left tail (crash risk); positive == lottery-like upside.
    Returns 0.0 when there are fewer than 3 returns or zero return variance.
    """
    c = _as_1d("closes", closes)
    if c.size < 4:
        return 0.0
    rets = _simple_returns(c)
    sd = float(np.std(rets))
    if sd == 0.0:
        return 0.0
    centered = rets - np.mean(rets)
    return float(np.mean(centered**3) / sd**3)


def return_kurtosis(closes: np.ndarray) -> float:
    """Excess kurtosis of per-bar simple returns (normal == 0).

    High excess kurtosis == fat tails / outlier-prone (more frequent extreme
    moves than a normal). Returns 0.0 when there are too few returns or zero
    variance.
    """
    c = _as_1d("closes", closes)
    if c.size < 5:
        return 0.0
    rets = _simple_returns(c)
    var = float(np.var(rets))
    if var == 0.0:
        return 0.0
    centered = rets - np.mean(rets)
    return float(np.mean(centered**4) / var**2 - 3.0)


def _ema(values: np.ndarray, span: int) -> np.ndarray:
    """Exponential moving average with ``alpha = 2/(span+1)`` (pandas-compatible)."""
    alpha = 2.0 / (span + 1.0)
    out = np.empty_like(values, dtype=float)
    out[0] = values[0]
    for i in range(1, values.size):
        out[i] = alpha * values[i] + (1.0 - alpha) * out[i - 1]
    return out


def macd_histogram(
    closes: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9
) -> float:
    """Latest MACD histogram value: ``(EMA_fast - EMA_slow) - signal_EMA``.

    Positive == short-term trend accelerating above the longer trend (bullish
    momentum), negative == decelerating. A bounded, scale-relative read on trend
    change. Requires at least ``slow + signal`` closes.
    """
    c = _as_1d("closes", closes)
    if min(fast, slow, signal) < 1:
        raise ValueError("fast/slow/signal must each be >= 1")
    if fast >= slow:
        raise ValueError(f"fast ({fast}) must be < slow ({slow})")
    if c.size < slow + signal:
        raise ValueError(f"closes too short: need {slow + signal}, got {c.size}")
    macd_line = _ema(c, fast) - _ema(c, slow)
    signal_line = _ema(macd_line, signal)
    return float(macd_line[-1] - signal_line[-1])


def bollinger_bandwidth(closes: np.ndarray, lookback: int = 20, num_std: float = 2.0) -> float:
    """Bollinger bandwidth: ``(upper - lower) / middle`` over the last ``lookback`` bars.

    Width of the ``num_std``-deviation envelope relative to the moving average — a
    normalized volatility/compression gauge. A low value flags a squeeze (coiled
    range); a high value flags an expansion. Returns 0.0 when the window has zero
    variance. Raises if the moving average is zero.
    """
    c = _as_1d("closes", closes)
    if lookback < 2:
        raise ValueError(f"lookback must be >= 2, got {lookback}")
    if c.size < lookback:
        raise ValueError(f"closes too short: need {lookback}, got {c.size}")
    window = c[-lookback:]
    middle = float(np.mean(window))
    if middle == 0.0:
        raise ValueError("moving average is zero; cannot compute bandwidth")
    sd = float(np.std(window, ddof=1))
    if sd == 0.0:
        return 0.0
    return float(2.0 * num_std * sd / middle)


def beta(asset: np.ndarray, benchmark: np.ndarray, lookback: int = 20) -> float:
    """Beta of ``asset`` vs ``benchmark`` over the last ``lookback`` per-bar returns.

    ``cov(asset, benchmark) / var(benchmark)`` — how much the asset moves per unit
    of benchmark move. ~1 tracks the benchmark, >1 amplifies it, <0 moves against
    it. Used as a concentration/diversification gate. Returns 0.0 when the
    benchmark return window has zero variance.
    """
    a = _as_1d("asset", asset)
    b = _as_1d("benchmark", benchmark)
    if a.size != b.size:
        raise ValueError(f"asset and benchmark must be equal length: {a.size} != {b.size}")
    if lookback < 2:
        raise ValueError(f"lookback must be >= 2, got {lookback}")
    if a.size < lookback + 1:
        raise ValueError(f"series too short: need {lookback + 1}, got {a.size}")
    ra = _simple_returns(a[-(lookback + 1):])
    rb = _simple_returns(b[-(lookback + 1):])
    var_b = float(np.var(rb))
    if var_b == 0.0:
        return 0.0
    cov = float(np.mean((ra - np.mean(ra)) * (rb - np.mean(rb))))
    return float(cov / var_b)
