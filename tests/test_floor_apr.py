"""The floor's carry APR: configurable, live-refreshable, and never corruptible.

The hurdle is load-bearing — every other division is priced against it — so an
externally-sourced APR is accepted only when finite and within a sanity band,
and ANY provider failure leaves the configured carry untouched.
"""

from __future__ import annotations

import math

import pytest

from boardroom.divisions.yield_div import YieldDivision
from boardroom.models.yield_model import YieldModel


def test_no_provider_keeps_configured_carry():
    div = YieldDivision(model=YieldModel(carry_apr=0.04))
    assert div.refresh_floor() == pytest.approx(0.04)
    assert div.hurdle_for(1.0) == pytest.approx(0.04 / 365.0)


def test_provider_value_is_adopted():
    model = YieldModel(carry_apr=0.04, apr_provider=lambda: 0.061)
    assert model.resolve_carry() == pytest.approx(0.061)
    assert model.carry_apr == pytest.approx(0.061)


def test_insane_high_apr_is_clamped_to_band():
    # A 500% feed must not blow the hurdle open — clamp to apr_max.
    model = YieldModel(carry_apr=0.04, apr_max=0.25, apr_provider=lambda: 5.0)
    assert model.resolve_carry() == pytest.approx(0.25)


def test_negative_apr_is_clamped_to_floor():
    model = YieldModel(carry_apr=0.04, apr_min=0.0, apr_provider=lambda: -0.10)
    assert model.resolve_carry() == pytest.approx(0.0)


def test_provider_exception_falls_back_to_config():
    def boom() -> float:
        raise RuntimeError("Kraken Earn endpoint unavailable")

    model = YieldModel(carry_apr=0.045, apr_provider=boom)
    assert model.resolve_carry() == pytest.approx(0.045)
    assert model.carry_apr == pytest.approx(0.045)


def test_non_finite_apr_is_rejected():
    model = YieldModel(carry_apr=0.04, apr_provider=lambda: math.nan)
    assert model.resolve_carry() == pytest.approx(0.04)


def test_refresh_updates_the_hurdle():
    model = YieldModel(carry_apr=0.04, apr_provider=lambda: 0.08)
    div = YieldDivision(model=model)
    div.refresh_floor()
    assert div.hurdle_for(365.0) == pytest.approx(0.08)
