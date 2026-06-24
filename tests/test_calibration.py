"""Deterministic tests for the adaptive engine (no network, no LLM, no DB)."""

from __future__ import annotations

import pytest

from boardroom.adaptive import (
    CalibrationPosterior,
    bounded_weight_update,
    can_refit,
    posterior_from_outcomes,
    seed_prior,
    should_retire,
    trust_multiplier,
    update_leash,
    walk_forward_ok,
)
from boardroom.schemas import Division, ResolvedOutcome


def make_outcome(*, division: Division = Division.DIRECTIONAL, win: bool = False) -> ResolvedOutcome:
    return ResolvedOutcome(
        decision_id="d",
        division=division,
        predicted_return=0.0,
        realized_return=0.0,
        predicted_confidence=0.5,
        win=win,
        pnl_cad=0.0,
        cost_cad=0.0,
        inside_band=True,
    )


def post(mean: float, n: float, division: str = "directional") -> CalibrationPosterior:
    """Build a posterior with a target mean and observed pseudo-count n."""
    # alpha + beta - 2 == n  and  alpha / (alpha+beta) == mean
    total = n + 2.0
    alpha = mean * total
    beta = total - alpha
    return CalibrationPosterior(division=division, alpha=alpha, beta=beta)


# --------------------------------------------------------------------------- #
# seed_prior
# --------------------------------------------------------------------------- #

def test_seed_prior_mean_matches_hit_rate():
    # The weak +1/+1 prior pulls the mean slightly toward 0.5, so ~0.6 (scope §5).
    p = seed_prior(0.6)
    assert p.mean() == pytest.approx(0.6, abs=0.05)
    # higher hit-rate -> higher mean (monotonic)
    assert seed_prior(0.8).mean() > seed_prior(0.6).mean()


def test_seed_prior_is_weak():
    # default strength 4 -> only ~4 pseudo-observations of conviction
    p = seed_prior(0.6, strength=4.0)
    assert p.n() == pytest.approx(4.0, abs=1e-9)


def test_seed_prior_clamps():
    # out-of-range hit-rates are clamped to [0, 1] before seeding;
    # equivalently seed_prior(2.0) == seed_prior(1.0).
    assert seed_prior(2.0).mean() == pytest.approx(seed_prior(1.0).mean(), abs=1e-9)
    assert seed_prior(-1.0).mean() == pytest.approx(seed_prior(0.0).mean(), abs=1e-9)
    # and the clamped means are the extreme valid values
    assert seed_prior(1.0).mean() == pytest.approx(5.0 / 6.0, abs=1e-9)
    assert seed_prior(0.0).mean() == pytest.approx(1.0 / 6.0, abs=1e-9)


# --------------------------------------------------------------------------- #
# posterior updates
# --------------------------------------------------------------------------- #

def test_update_returns_new_posterior():
    p = CalibrationPosterior(division="d", alpha=1.0, beta=1.0)
    p2 = p.update(True)
    assert p2 is not p
    assert p.alpha == 1.0 and p2.alpha == 2.0


def test_seven_wins_three_losses_from_flat_prior():
    outcomes = [make_outcome(win=True) for _ in range(7)]
    outcomes += [make_outcome(win=False) for _ in range(3)]
    p = posterior_from_outcomes("directional", outcomes)
    # flat Beta(1,1) + 7 wins + 3 losses -> Beta(8,4), mean = 8/12 = 0.667
    assert 0.6 <= p.mean() <= 0.67
    assert p.n() == pytest.approx(10.0, abs=1e-9)


def test_posterior_ignores_other_divisions():
    outcomes = [
        make_outcome(division=Division.DIRECTIONAL, win=True),
        make_outcome(division=Division.EVENT, win=False),
        make_outcome(division=Division.EVENT, win=False),
    ]
    p = posterior_from_outcomes("directional", outcomes)
    assert p.n() == pytest.approx(1.0, abs=1e-9)
    assert p.division == "directional"


def test_posterior_uses_prior():
    prior = seed_prior(0.6, strength=4.0)
    outcomes = [make_outcome(win=True)]
    p = posterior_from_outcomes("directional", outcomes, prior=prior)
    assert p.n() == pytest.approx(5.0, abs=1e-9)  # 4 prior + 1 observed


# --------------------------------------------------------------------------- #
# trust_multiplier
# --------------------------------------------------------------------------- #

def test_trust_multiplier_discounts_overclaim_large_sample():
    # says 0.9, demonstrated 0.5 over a large sample -> well below 1
    p = post(mean=0.5, n=200)
    m = trust_multiplier(p, stated_confidence=0.9)
    assert m < 0.7
    # raw ratio is 0.5/0.9 ~= 0.556; large sample => close to raw
    assert m == pytest.approx(0.556, abs=0.03)


def test_trust_multiplier_tiny_sample_shrinks_toward_neutral():
    # tiny sample: even a perfectly-calibrated claim is not fully trusted
    p = post(mean=0.9, n=2)
    m = trust_multiplier(p, stated_confidence=0.9)
    # raw == 1.0 but shrunk toward 0.5; must not be full trust
    assert m < 1.0
    assert m == pytest.approx(0.5 + (2.0 / 12.0) * 0.5, abs=1e-6)


def test_trust_multiplier_zero_sample_is_neutral():
    p = post(mean=0.6, n=0)
    assert trust_multiplier(p, stated_confidence=0.9) == pytest.approx(0.5, abs=1e-9)


def test_trust_multiplier_capped_at_one():
    # demonstrated above stated -> capped at 1, then shrunk by sample weight
    p = post(mean=0.9, n=1000)
    m = trust_multiplier(p, stated_confidence=0.5)
    assert m <= 1.0
    assert m == pytest.approx(1.0, abs=0.02)


# --------------------------------------------------------------------------- #
# update_leash
# --------------------------------------------------------------------------- #

def test_leash_increases_with_good_calibration_and_edge():
    p = post(mean=0.7, n=50)
    new = update_leash(0.5, posterior=p, realized_edge_vs_floor=0.02)
    assert new == pytest.approx(0.6, abs=1e-9)


def test_leash_decreases_with_poor_calibration():
    p = post(mean=0.4, n=50)
    new = update_leash(0.5, posterior=p, realized_edge_vs_floor=0.02)
    assert new == pytest.approx(0.4, abs=1e-9)


def test_leash_decreases_with_negative_edge():
    p = post(mean=0.7, n=50)
    new = update_leash(0.5, posterior=p, realized_edge_vs_floor=-0.01)
    assert new == pytest.approx(0.4, abs=1e-9)


def test_leash_never_moves_more_than_max_step():
    p = post(mean=0.9, n=50)
    new = update_leash(0.5, posterior=p, realized_edge_vs_floor=1.0, max_step=0.1)
    assert abs(new - 0.5) <= 0.1 + 1e-12


def test_leash_clamps_to_bounds():
    p_good = post(mean=0.9, n=50)
    # cannot exceed leash_max
    assert update_leash(1.0, posterior=p_good, realized_edge_vs_floor=0.5, leash_max=1.0) == pytest.approx(1.0)
    p_bad = post(mean=0.1, n=50)
    # cannot go below 0
    assert update_leash(0.05, posterior=p_bad, realized_edge_vs_floor=-0.5) == pytest.approx(0.0)


def test_leash_holds_in_ambiguous_middle():
    p = post(mean=0.5, n=50)
    assert update_leash(0.5, posterior=p, realized_edge_vs_floor=0.0) == pytest.approx(0.5)


# --------------------------------------------------------------------------- #
# should_retire
# --------------------------------------------------------------------------- #

def test_no_retire_below_min_sample_even_if_terrible():
    p = post(mean=0.1, n=5)
    assert should_retire(posterior=p, net_vs_floor_cad=-100.0, n_resolved=5, min_sample=20) is False


def test_retire_when_miscalibrated_with_enough_sample():
    p = post(mean=0.4, n=50)
    assert should_retire(posterior=p, net_vs_floor_cad=10.0, n_resolved=50, min_sample=20) is True


def test_retire_when_net_negative_with_enough_sample():
    p = post(mean=0.7, n=50)  # well calibrated...
    assert should_retire(posterior=p, net_vs_floor_cad=-1.0, n_resolved=50, min_sample=20) is True


def test_no_retire_when_healthy():
    p = post(mean=0.7, n=50)
    assert should_retire(posterior=p, net_vs_floor_cad=25.0, n_resolved=50, min_sample=20) is False


# --------------------------------------------------------------------------- #
# refit
# --------------------------------------------------------------------------- #

def test_can_refit_gate():
    assert can_refit(29, min_sample=30) is False
    assert can_refit(30, min_sample=30) is True


def test_bounded_weight_update_caps_relative_change():
    old = [1.0, -4.0, 2.0]
    new = [5.0, 0.0, -10.0]
    out = bounded_weight_update(old, new, max_rel_step=0.25)
    for o, n_, r in zip(old, new, out):
        assert abs(r - o) <= 0.25 * abs(o) + 1e-12
    # moves are in the right direction
    assert out[0] > old[0]
    assert out[1] > old[1]
    assert out[2] < old[2]


def test_bounded_weight_update_zero_weight_fallback():
    out = bounded_weight_update([0.0], [10.0], max_rel_step=0.25)
    assert out[0] == pytest.approx(0.25, abs=1e-9)


def test_bounded_weight_update_length_mismatch():
    with pytest.raises(ValueError):
        bounded_weight_update([1.0, 2.0], [1.0])


def test_walk_forward_rejects_oos_collapse():
    assert walk_forward_ok(1.0, 0.3, min_ratio=0.6) is False
    assert walk_forward_ok(1.0, 0.7, min_ratio=0.6) is True


def test_walk_forward_non_positive_in_sample():
    # no positive in-sample edge: accept only if OOS is non-negative
    assert walk_forward_ok(0.0, 0.1) is True
    assert walk_forward_ok(-1.0, -0.1) is False
