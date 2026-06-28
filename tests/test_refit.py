"""The guardrailed walk-forward re-fit of the Directional model.

A refit may adapt the coefficients, but only within the anti-overfit fence:
enough data, survives out-of-sample, and moves by a bounded step. A rejected
refit must leave the model byte-for-byte unchanged.
"""

from __future__ import annotations

import pytest

from boardroom.adaptive.refit import RefitResult, refit_directional
from boardroom.data.sources import synthetic_bars
from boardroom.models.directional import DirectionalModel
from boardroom.schemas import Venue


def _coeffs(m: DirectionalModel) -> tuple:
    return (m.intercept, m.w_momentum, m.w_meanrev, m.w_rsi)


def test_thin_data_is_rejected_and_model_unchanged():
    model = DirectionalModel()
    before = _coeffs(model)
    bars = synthetic_bars("SPY.US", Venue.IBKR, n=60, seed=1)  # too few after split
    result = refit_directional(model, bars, min_sample=30)
    assert result.accepted is False
    assert _coeffs(model) == before  # untouched


def test_refit_runs_and_respects_guardrails_on_ample_data():
    model = DirectionalModel()
    before = _coeffs(model)
    bars = synthetic_bars("SPY.US", Venue.IBKR, n=400, seed=3, drift=0.0006, vol=0.012)
    result = refit_directional(model, bars, min_sample=30, max_rel_step=0.25)
    assert isinstance(result, RefitResult)
    assert result.n_train >= 30
    if result.accepted:
        # Each coefficient moved by at most max_rel_step of its old magnitude
        # (zeroed weights may take a small absolute step).
        for name in ("w_momentum", "w_meanrev", "w_rsi"):
            old = result.old_coefficients[name]
            new = result.new_coefficients[name]
            cap = 0.25 * abs(old) if old != 0 else 0.25
            assert abs(new - old) <= cap + 1e-9
        assert model.coefficients_source == "walk_forward_refit"
    else:
        assert _coeffs(model) == before  # rejection leaves the model intact


def test_rejected_refit_leaves_model_intact():
    # A degenerate flat-ish series shouldn't produce an accepted, model-changing fit.
    model = DirectionalModel()
    before = _coeffs(model)
    bars = synthetic_bars("SPY.US", Venue.IBKR, n=400, seed=99, drift=0.0, vol=0.001)
    result = refit_directional(model, bars)
    if not result.accepted:
        assert _coeffs(model) == before


def test_refit_persists_and_reloads_via_orchestrator():
    from boardroom.factory import build_default_org

    org = build_default_org(data_mode="synthetic")
    results = org.refit_models()
    # Whatever the verdict, the call is safe and returns results for fittable divs.
    assert isinstance(results, list)
    accepted = [r for r in results if r.accepted]
    if accepted:
        params = org.repo.get_model_params("directional")
        assert params is not None and "w_momentum" in params
        # Reloading applies the persisted coefficients without error.
        org.load_model_params()
