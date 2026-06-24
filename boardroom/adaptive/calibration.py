"""Bayesian track-record-weighted trust per division (scope §6).

The CEO distrusts *stated* confidence and trusts *demonstrated* calibration. A
division can claim a 0.9 win-probability all day; what matters is whether it
actually hits at 0.9 over a real track record. We model each division's true
hit-rate as a ``Beta(alpha, beta)`` posterior, seeded from the backtest (a weak
prior, scope §5) and folded forward one resolved outcome at a time.

Anti-overfit stance: tiny samples are NOT trusted. A division with three
resolved trades does not get to swing the allocation — its trust multiplier is
shrunk toward a neutral value until the evidence accumulates.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from boardroom.schemas import ResolvedOutcome


@dataclass(frozen=True)
class CalibrationPosterior:
    """A ``Beta(alpha, beta)`` posterior over a division's true hit-rate.

    The prior contributes ``alpha + beta - 2`` pseudo-observations (a flat
    ``Beta(1, 1)`` prior has ``n() == 0``), so ``n()`` reads as "how many real
    observations have I effectively seen".
    """

    division: str
    alpha: float
    beta: float

    def mean(self) -> float:
        """Posterior mean hit-rate = alpha / (alpha + beta)."""
        return self.alpha / (self.alpha + self.beta)

    def n(self) -> float:
        """Pseudo-count of *observed* outcomes (excludes the +1/+1 prior mass)."""
        return self.alpha + self.beta - 2.0

    def update(self, win: bool) -> "CalibrationPosterior":
        """Fold in one resolved outcome, returning a NEW posterior.

        A win adds to ``alpha`` (successes); a loss adds to ``beta`` (failures).
        """
        if win:
            return replace(self, alpha=self.alpha + 1.0)
        return replace(self, beta=self.beta + 1.0)


def seed_prior(backtest_hit_rate: float, strength: float = 4.0) -> CalibrationPosterior:
    """Turn a backtest hit-rate into a *weak* Beta prior (scope §5).

    ``strength`` is how many pseudo-observations the backtest is worth. We keep
    it small (default 4) on purpose: the backtest seeds the calibration but must
    not dominate real, live evidence. With ``strength == 4`` and hit-rate 0.6
    the prior is ``Beta(0.6*4 + 1, 0.4*4 + 1) = Beta(3.4, 2.6)``, mean 0.6 but
    only ~4 pseudo-observations of conviction.

    ``backtest_hit_rate`` is clamped to ``[0, 1]``.
    """
    p = min(1.0, max(0.0, backtest_hit_rate))
    s = max(0.0, strength)
    alpha = p * s + 1.0
    beta = (1.0 - p) * s + 1.0
    return CalibrationPosterior(division="", alpha=alpha, beta=beta)


def posterior_from_outcomes(
    division: str,
    outcomes: list[ResolvedOutcome],
    prior: CalibrationPosterior | None = None,
) -> CalibrationPosterior:
    """Fold a division's resolved wins/losses into a posterior.

    Starts from ``prior`` (or a flat ``Beta(1, 1)`` if none) and applies each
    outcome's ``win`` flag in order. Outcomes for other divisions are ignored so
    callers can safely pass a mixed list.
    """
    post = prior if prior is not None else CalibrationPosterior(
        division=division, alpha=1.0, beta=1.0
    )
    post = replace(post, division=division)
    for o in outcomes:
        if o.division.value != division:
            continue
        post = post.update(o.win)
    return post


def trust_multiplier(
    posterior: CalibrationPosterior, stated_confidence: float
) -> float:
    """How much to trust a pitch's stated confidence, given track record.

    Returns a factor in ``[0, 1]`` that the CEO multiplies into a pitch's stated
    confidence. The idea: a division that SAYS 0.7 but HITS 0.5 is overconfident
    and gets discounted; a division that hits *above* what it claims is capped at
    full trust (1.0, never a reward multiplier > 1).

    Formula
    -------
    1. ``raw = clamp(demonstrated_mean / stated_confidence, 0, 1)``
       — the ratio of what it actually hits to what it claims.
    2. Shrink toward a neutral 0.5 when the sample is tiny, using a
       sample-weight ``w = n / (n + K)`` with ``K = 10``::

           multiplier = w * raw + (1 - w) * 0.5

       With ``n == 0`` the multiplier is exactly 0.5 (we neither trust nor
       distrust an untested division); as ``n`` grows it converges to ``raw``.

    This is the anti-overfit guardrail: a 3-sample division can't earn full
    trust, and an over-claiming division gets demoted as evidence mounts.
    """
    K = 10.0
    sc = stated_confidence
    if sc <= 0.0:
        # No meaningful claim to discount; treat as fully calibrated.
        raw = 1.0
    else:
        raw = posterior.mean() / sc
        raw = min(1.0, max(0.0, raw))

    n = max(0.0, posterior.n())
    w = n / (n + K)
    return w * raw + (1.0 - w) * 0.5
