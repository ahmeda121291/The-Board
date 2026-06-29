"""Unit tests for the pure technical feature functions (the spine, scope §5).

Deterministic synthetic arrays only — no randomness, no network. If these pass,
the numbers the divisions feed into expected_return / win_probability are correct.
"""

from __future__ import annotations

import numpy as np
import pytest

from boardroom.features import (
    atr,
    beta,
    bollinger_bandwidth,
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
    zscore_meanrev,
)


# --------------------------------------------------------------------------- #
# momentum
# --------------------------------------------------------------------------- #
def test_momentum_geometric_series():
    # Constant 1% per-bar growth: total return over lookback bars is (1.01**lb - 1).
    lookback = 20
    closes = 100.0 * (1.01 ** np.arange(lookback + 5))
    expected = 1.01 ** lookback - 1.0
    assert momentum(closes, lookback=lookback) == pytest.approx(expected)


def test_momentum_flat_series_is_zero():
    closes = np.full(30, 50.0)
    assert momentum(closes, lookback=10) == pytest.approx(0.0)


def test_momentum_too_short_raises():
    with pytest.raises(ValueError):
        momentum(np.arange(1, 6, dtype=float), lookback=20)


# --------------------------------------------------------------------------- #
# volatility
# --------------------------------------------------------------------------- #
def test_volatility_zero_on_constant_series():
    closes = np.full(40, 25.0)
    assert volatility(closes, lookback=20) == pytest.approx(0.0)


def test_volatility_positive_on_varying_series():
    # Alternating up/down moves -> non-zero dispersion of log returns.
    closes = np.array([100.0, 110.0, 99.0, 121.0, 95.0, 130.0, 90.0, 140.0])
    assert volatility(closes, lookback=5) > 0.0


def test_volatility_matches_numpy_log_return_std():
    closes = np.array([10.0, 11.0, 10.5, 12.0, 11.5, 13.0])
    log_rets = np.diff(np.log(closes))
    assert volatility(closes, lookback=5) == pytest.approx(np.std(log_rets, ddof=1))


def test_volatility_too_short_raises():
    with pytest.raises(ValueError):
        volatility(np.array([1.0, 2.0]), lookback=20)


# --------------------------------------------------------------------------- #
# zscore_meanrev
# --------------------------------------------------------------------------- #
def test_zscore_positive_when_above_mean():
    # Flat then a spike up at the end -> last close well above window mean -> +z.
    closes = np.concatenate([np.full(19, 100.0), [130.0]])
    assert zscore_meanrev(closes, lookback=20) > 0.0


def test_zscore_negative_when_below_mean():
    closes = np.concatenate([np.full(19, 100.0), [70.0]])
    assert zscore_meanrev(closes, lookback=20) < 0.0


def test_zscore_zero_variance_returns_zero():
    closes = np.full(30, 100.0)
    assert zscore_meanrev(closes, lookback=20) == 0.0


def test_zscore_too_short_raises():
    with pytest.raises(ValueError):
        zscore_meanrev(np.array([1.0, 2.0, 3.0]), lookback=20)


# --------------------------------------------------------------------------- #
# drawdown / max_drawdown
# --------------------------------------------------------------------------- #
def test_drawdown_zero_at_new_high():
    closes = np.array([10.0, 11.0, 12.0, 13.0, 14.0])
    assert drawdown(closes) == pytest.approx(0.0)


def test_drawdown_negative_after_decline():
    closes = np.array([100.0, 120.0, 90.0])  # peak 120, last 90
    assert drawdown(closes) == pytest.approx(90.0 / 120.0 - 1.0)
    assert drawdown(closes) < 0.0


def test_max_drawdown_known_value():
    # Peak 100 -> trough 60 is the worst: -40%.
    closes = np.array([80.0, 100.0, 60.0, 90.0, 95.0])
    assert max_drawdown(closes) == pytest.approx(-0.4)


def test_max_drawdown_le_drawdown():
    closes = np.array([100.0, 120.0, 60.0, 110.0, 100.0])
    assert max_drawdown(closes) <= drawdown(closes)


def test_max_drawdown_zero_on_monotonic_increase():
    closes = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    assert max_drawdown(closes) == pytest.approx(0.0)


def test_drawdown_empty_raises():
    with pytest.raises(ValueError):
        drawdown(np.array([]))


def test_max_drawdown_empty_raises():
    with pytest.raises(ValueError):
        max_drawdown(np.array([]))


# --------------------------------------------------------------------------- #
# rolling_correlation
# --------------------------------------------------------------------------- #
def test_rolling_correlation_identical_trend_near_plus_one():
    a = 100.0 * (1.01 ** np.arange(30)) + np.tile([0.0, 0.5], 15)
    b = 50.0 * (1.01 ** np.arange(30)) + np.tile([0.0, 0.25], 15)
    assert rolling_correlation(a, b, lookback=20) == pytest.approx(1.0, abs=1e-6)


def test_rolling_correlation_mirrored_near_minus_one():
    base = np.array([100.0, 110.0, 95.0, 120.0, 90.0, 130.0, 85.0])
    # Mirror the per-bar returns of `base` to build `mirror`.
    rets = np.diff(base) / base[:-1]
    mirror = [100.0]
    for r in rets:
        mirror.append(mirror[-1] * (1.0 - r))
    mirror = np.array(mirror)
    assert rolling_correlation(base, mirror, lookback=6) == pytest.approx(-1.0, abs=1e-6)


def test_rolling_correlation_zero_variance_returns_zero():
    a = np.full(30, 100.0)  # constant -> zero return variance
    b = 100.0 * (1.01 ** np.arange(30))
    assert rolling_correlation(a, b, lookback=20) == 0.0


def test_rolling_correlation_length_mismatch_raises():
    with pytest.raises(ValueError):
        rolling_correlation(np.arange(30, dtype=float), np.arange(25, dtype=float))


def test_rolling_correlation_too_short_raises():
    with pytest.raises(ValueError):
        rolling_correlation(np.arange(5, dtype=float), np.arange(5, dtype=float), lookback=20)


# --------------------------------------------------------------------------- #
# realized_sharpe
# --------------------------------------------------------------------------- #
def test_realized_sharpe_zero_on_constant():
    closes = np.full(30, 100.0)
    assert realized_sharpe(closes) == 0.0


def test_realized_sharpe_positive_on_steady_uptrend():
    closes = 100.0 * (1.005 ** np.arange(30))
    s = realized_sharpe(closes, periods_per_year=252)
    assert s > 0.0
    assert np.isfinite(s)


def test_realized_sharpe_sign_flips_on_downtrend():
    closes = 100.0 * (0.995 ** np.arange(30))
    assert realized_sharpe(closes) < 0.0


def test_realized_sharpe_too_short_raises():
    with pytest.raises(ValueError):
        realized_sharpe(np.array([100.0]))


# --------------------------------------------------------------------------- #
# liquidity_proxy
# --------------------------------------------------------------------------- #
def test_liquidity_proxy_constant_equals_price_times_volume():
    closes = np.full(30, 12.0)
    volumes = np.full(30, 1000.0)
    assert liquidity_proxy(closes, volumes, lookback=20) == pytest.approx(12.0 * 1000.0)


def test_liquidity_proxy_uses_last_lookback_only():
    closes = np.concatenate([np.full(10, 1.0), np.full(10, 5.0)])
    volumes = np.full(20, 2.0)
    # Last 10 bars: price 5, volume 2 -> 10 each.
    assert liquidity_proxy(closes, volumes, lookback=10) == pytest.approx(10.0)


def test_liquidity_proxy_length_mismatch_raises():
    with pytest.raises(ValueError):
        liquidity_proxy(np.arange(30, dtype=float), np.arange(25, dtype=float))


def test_liquidity_proxy_too_short_raises():
    with pytest.raises(ValueError):
        liquidity_proxy(np.arange(5, dtype=float), np.arange(5, dtype=float), lookback=20)


# --------------------------------------------------------------------------- #
# rsi
# --------------------------------------------------------------------------- #
def test_rsi_strictly_increasing_is_100():
    closes = np.arange(1.0, 30.0)
    assert rsi(closes, lookback=14) == pytest.approx(100.0)


def test_rsi_strictly_decreasing_is_0():
    closes = np.arange(30.0, 1.0, -1.0)
    assert rsi(closes, lookback=14) == pytest.approx(0.0)


def test_rsi_within_bounds_on_mixed_series():
    closes = np.array(
        [44.0, 44.3, 44.1, 44.6, 45.1, 45.4, 45.0, 45.9, 46.0, 45.6,
         46.3, 46.4, 46.2, 45.7, 46.5, 46.8, 46.0, 46.9, 47.1, 46.7]
    )
    value = rsi(closes, lookback=14)
    assert 0.0 <= value <= 100.0


def test_rsi_too_short_raises():
    with pytest.raises(ValueError):
        rsi(np.arange(10.0), lookback=14)


# --------------------------------------------------------------------------- #
# atr
# --------------------------------------------------------------------------- #
def test_atr_constant_range_known_value():
    # Flat closes at 100, bands +/-1: TR each bar = max(2, 1, 1) = 2 -> ATR 2.
    closes = np.full(20, 100.0)
    highs = closes + 1.0
    lows = closes - 1.0
    assert atr(highs, lows, closes, lookback=10) == pytest.approx(2.0)


def test_atr_nonnegative_and_captures_gap():
    closes = np.array([100.0, 105.0, 95.0, 110.0, 90.0, 115.0])
    highs = closes + 2.0
    lows = closes - 2.0
    assert atr(highs, lows, closes, lookback=3) > 0.0


def test_atr_length_mismatch_raises():
    with pytest.raises(ValueError):
        atr(np.arange(20.0), np.arange(19.0), np.arange(20.0), lookback=10)


def test_atr_too_short_raises():
    with pytest.raises(ValueError):
        atr(np.arange(5.0), np.arange(5.0), np.arange(5.0), lookback=10)


# --------------------------------------------------------------------------- #
# downside_deviation / sortino_ratio
# --------------------------------------------------------------------------- #
def test_downside_deviation_zero_when_all_up():
    closes = 100.0 * (1.01 ** np.arange(20))
    assert downside_deviation(closes) == pytest.approx(0.0)


def test_downside_deviation_known_value():
    # returns: +0.1, -0.1 -> shortfall^2 mean = (0 + 0.01)/2 = 0.005.
    closes = np.array([100.0, 110.0, 99.0])
    assert downside_deviation(closes) == pytest.approx(np.sqrt(0.005))


def test_sortino_zero_when_no_downside():
    closes = 100.0 * (1.005 ** np.arange(30))
    assert sortino_ratio(closes) == 0.0


def test_sortino_negative_on_downtrend():
    closes = 100.0 * (0.99 ** np.arange(30))
    assert sortino_ratio(closes) < 0.0


# --------------------------------------------------------------------------- #
# return_skew / return_kurtosis
# --------------------------------------------------------------------------- #
def test_return_skew_zero_on_constant_returns():
    # Powers of two -> every simple return is exactly 1.0 (no FP noise) -> zero
    # dispersion -> skew is 0.0.
    closes = 2.0 ** np.arange(20)
    assert return_skew(closes) == pytest.approx(0.0)


def test_return_skew_negative_with_left_tail():
    # Mostly small gains, one large crash -> fat left tail -> negative skew.
    closes = [100.0]
    for _ in range(15):
        closes.append(closes[-1] * 1.01)
    closes.append(closes[-1] * 0.6)  # crash
    assert return_skew(np.array(closes)) < 0.0


def test_return_kurtosis_zero_on_too_short():
    assert return_kurtosis(np.array([100.0, 101.0])) == 0.0


def test_return_kurtosis_positive_with_outliers():
    # Calm returns punctuated by rare large moves -> fat tails -> +excess kurtosis.
    closes = [100.0]
    for i in range(40):
        step = 1.5 if i in (10, 30) else 1.001
        closes.append(closes[-1] * step)
    assert return_kurtosis(np.array(closes)) > 0.0


# --------------------------------------------------------------------------- #
# macd_histogram
# --------------------------------------------------------------------------- #
def test_macd_histogram_zero_on_flat_series():
    closes = np.full(50, 100.0)
    assert macd_histogram(closes) == pytest.approx(0.0)


def test_macd_histogram_finite_on_trend():
    closes = 100.0 * (1.01 ** np.arange(60))
    value = macd_histogram(closes)
    assert np.isfinite(value)


def test_macd_histogram_rejects_fast_ge_slow():
    with pytest.raises(ValueError):
        macd_histogram(np.full(50, 100.0), fast=26, slow=12)


def test_macd_histogram_too_short_raises():
    with pytest.raises(ValueError):
        macd_histogram(np.arange(10.0))


# --------------------------------------------------------------------------- #
# bollinger_bandwidth
# --------------------------------------------------------------------------- #
def test_bollinger_bandwidth_zero_on_constant():
    closes = np.full(30, 100.0)
    assert bollinger_bandwidth(closes, lookback=20) == pytest.approx(0.0)


def test_bollinger_bandwidth_positive_and_finite_on_varying():
    closes = np.array([100.0, 102.0, 98.0, 104.0, 96.0] * 5, dtype=float)
    value = bollinger_bandwidth(closes, lookback=20)
    assert value > 0.0 and np.isfinite(value)


def test_bollinger_bandwidth_too_short_raises():
    with pytest.raises(ValueError):
        bollinger_bandwidth(np.arange(5.0), lookback=20)


# --------------------------------------------------------------------------- #
# beta
# --------------------------------------------------------------------------- #
def test_beta_one_against_itself():
    series = 100.0 * (1.01 ** np.arange(30)) + np.tile([0.0, 0.7], 15)
    assert beta(series, series, lookback=20) == pytest.approx(1.0)


def test_beta_zero_when_benchmark_constant():
    asset = 100.0 * (1.01 ** np.arange(30))
    benchmark = np.full(30, 100.0)
    assert beta(asset, benchmark, lookback=20) == 0.0


def test_beta_negative_when_mirrored():
    base = np.array([100.0, 110.0, 95.0, 120.0, 90.0, 130.0, 85.0])
    rets = np.diff(base) / base[:-1]
    mirror = [100.0]
    for r in rets:
        mirror.append(mirror[-1] * (1.0 - r))
    assert beta(base, np.array(mirror), lookback=6) < 0.0


def test_beta_length_mismatch_raises():
    with pytest.raises(ValueError):
        beta(np.arange(30, dtype=float), np.arange(25, dtype=float))
