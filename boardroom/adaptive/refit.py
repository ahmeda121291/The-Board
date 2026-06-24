"""Periodic model re-fit with anti-overfit guardrails (scope §6).

The system re-fits its models as new resolved outcomes arrive — but a re-fit is
the single easiest way to adapt into garbage. Three guardrails keep it honest:

1. ``can_refit`` — don't even attempt a re-fit until there is enough fresh
   evidence to fit on (``min_sample`` resolved outcomes).
2. ``bounded_weight_update`` — when accepting new weights, move toward them but
   cap the per-update *relative* change. Smooth, don't lurch.
3. ``walk_forward_ok`` — accept the re-fit only if out-of-sample performance
   retains a meaningful fraction of in-sample performance. This is the core
   overfitting check: a model that scores brilliantly in-sample but collapses
   out-of-sample has fit the fit window's noise and must be rejected.
"""

from __future__ import annotations


def can_refit(n_resolved: int, *, min_sample: int = 30) -> bool:
    """Only re-fit once at least ``min_sample`` outcomes have resolved.

    Fitting on a handful of points is how you overfit; this is the gate.
    """
    return n_resolved >= min_sample


def bounded_weight_update(
    old_weights: list[float],
    new_weights: list[float],
    *,
    max_rel_step: float = 0.25,
) -> list[float]:
    """Move each weight toward its new value, capping the relative change.

    For each component the move is limited so that
    ``|result - old| <= max_rel_step * |old|``. That is, no single re-fit may
    shift a weight by more than ``max_rel_step`` (default 25%) of its current
    magnitude — smooth adaptation, never a lurch.

    When ``old`` is exactly 0 there is no magnitude to scale against, so we allow
    a small absolute step of ``max_rel_step`` toward the new value (otherwise a
    zeroed weight could never come back).

    Raises ``ValueError`` if the two weight vectors differ in length.
    """
    if len(old_weights) != len(new_weights):
        raise ValueError(
            f"weight length mismatch: {len(old_weights)} != {len(new_weights)}"
        )

    out: list[float] = []
    for old, new in zip(old_weights, new_weights):
        desired = new - old
        if old == 0.0:
            cap = max_rel_step  # absolute fallback for a zeroed weight
        else:
            cap = max_rel_step * abs(old)
        step = min(cap, max(-cap, desired))
        out.append(old + step)
    return out


def walk_forward_ok(
    in_sample_score: float,
    out_of_sample_score: float,
    *,
    min_ratio: float = 0.6,
) -> bool:
    """Accept a re-fit only if it generalizes out-of-sample.

    Returns ``True`` iff ``out_of_sample_score >= min_ratio * in_sample_score``,
    i.e. the model keeps at least ``min_ratio`` (default 60%) of its in-sample
    performance on unseen data. A sharp OOS collapse signals overfitting and is
    rejected.

    Edge cases:
    - ``in_sample_score <= 0``: there is no positive in-sample edge to retain, so
      the re-fit is only accepted if the OOS score is itself non-negative
      (a model that wasn't good in-sample shouldn't be promoted on the strength
      of a negative OOS score either).
    """
    if in_sample_score <= 0.0:
        return out_of_sample_score >= 0.0
    return out_of_sample_score >= min_ratio * in_sample_score
