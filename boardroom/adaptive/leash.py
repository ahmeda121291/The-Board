"""Per-division risk leash (scope §6).

The leash is a multiplier in ``[0, leash_max]`` that gates how much capital a
division may be sized to. It is *earned*: it grows as a division proves it is
well-calibrated AND profitable versus the floor, and it shrinks the moment that
breaks down.

The single most important property here is the BOUNDED MOVE. The leash never
jumps — it moves by at most ``max_step`` per update. This is deliberate
anti-overfitting: one good (or bad) day must not lurch the allocation. Trust is
slow to gain and slow to lose, which keeps the system from chasing noise.
"""

from __future__ import annotations

from boardroom.adaptive.calibration import CalibrationPosterior


def update_leash(
    current_leash: float,
    *,
    posterior: CalibrationPosterior,
    realized_edge_vs_floor: float,
    leash_max: float = 1.0,
    max_step: float = 0.1,
    leash_min: float = 0.0,
) -> float:
    """Nudge a division's leash based on demonstrated calibration and edge.

    Rules
    -----
    - Good calibration (``posterior.mean() > 0.55``) AND positive edge vs the
      floor -> increase the leash by up to ``max_step``.
    - Poor calibration (``posterior.mean() < 0.45``) OR negative edge vs the
      floor -> decrease the leash by up to ``max_step``.
    - Otherwise (the ambiguous middle) -> hold steady.

    Bounded move: the change is always clamped to ``[-max_step, +max_step]`` so
    no single update can lurch the allocation. The result is then clamped to
    ``[leash_min, leash_max]``.

    ``leash_min`` is the comeback floor (owner mandate 2026-08-04): a leash that
    reaches exactly 0 is an absorbing state — the division sizes to zero, never
    trades, never produces new evidence, and can never recover. Flooring at a
    small positive value keeps a struggling division trading at minimum size so
    it can earn its trust back (or go on to retire properly). Retirement — the
    deliberate kill switch — still forces 0 at the caller.
    """
    mean = posterior.mean()
    good_calibration = mean > 0.55
    poor_calibration = mean < 0.45
    positive_edge = realized_edge_vs_floor > 0.0
    negative_edge = realized_edge_vs_floor < 0.0

    delta = 0.0
    if good_calibration and positive_edge:
        delta = max_step
    elif poor_calibration or negative_edge:
        delta = -max_step

    # Enforce the bounded move explicitly (defensive; delta already obeys it).
    delta = min(max_step, max(-max_step, delta))

    new_leash = current_leash + delta
    return min(leash_max, max(max(0.0, leash_min), new_leash))
