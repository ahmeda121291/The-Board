"""The adaptive engine (scope §6): the system gets better at knowing what it knows.

Every function here is pure and deterministic — no network, no LLM, no DB. They
turn resolved outcomes into slowly-updated trust:

- ``calibration`` — Bayesian track-record-weighted trust per division.
- ``leash`` — earned, bounded per-division risk multiplier.
- ``retirement`` — the kill switch for divisions that don't earn their keep.
- ``refit`` — periodic model re-fit, fenced by anti-overfit guardrails.

The whole design point is to adapt *without* adapting into garbage: tiny samples
aren't trusted, moves are bounded, and re-fits must survive walk-forward.
"""

from __future__ import annotations

from boardroom.adaptive.calibration import (
    CalibrationPosterior,
    posterior_from_outcomes,
    seed_prior,
    trust_multiplier,
)
from boardroom.adaptive.leash import update_leash
from boardroom.adaptive.refit import (
    RefitResult,
    bounded_weight_update,
    can_refit,
    refit_directional,
    walk_forward_ok,
)
from boardroom.adaptive.retirement import should_retire

__all__ = [
    "CalibrationPosterior",
    "seed_prior",
    "posterior_from_outcomes",
    "trust_multiplier",
    "update_leash",
    "should_retire",
    "can_refit",
    "bounded_weight_update",
    "walk_forward_ok",
    "refit_directional",
    "RefitResult",
]
