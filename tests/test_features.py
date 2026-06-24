"""Unit tests for the pure technical feature functions (the spine, scope §5).

Deterministic synthetic arrays only — no randomness, no network. If these pass,
the numbers the divisions feed into expected_return / win_probability are correct.
"""

from __future__ import annotations

import numpy as np
import pytest

from boardroom.features import (
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
