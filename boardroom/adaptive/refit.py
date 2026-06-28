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

from dataclasses import dataclass, replace


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


# --------------------------------------------------------------------------- #
# Walk-forward refit harness for the Directional model.
#
# Ties the three guardrails above together into one accept/reject decision:
#   1. split history into in-sample (fit) and out-of-sample (validate) halves,
#   2. fit a candidate on in-sample only (no lookahead),
#   3. accept ONLY if it generalizes (walk_forward_ok) and there was enough data
#      (can_refit), then move the live coefficients toward the candidate by a
#      BOUNDED step. A rejected refit leaves the model exactly as it was.
# --------------------------------------------------------------------------- #
_COEF_NAMES = ("intercept", "w_momentum", "w_meanrev", "w_rsi")


@dataclass
class RefitResult:
    accepted: bool
    reason: str
    n_train: int
    in_sample_score: float
    out_of_sample_score: float
    old_coefficients: dict
    new_coefficients: dict


def _coefficients(model) -> dict:
    return {k: float(getattr(model, k)) for k in _COEF_NAMES}


def _training_set(model, bars, *, lo: int, hi: int, horizon: int):
    """Feature rows + up/down labels over ``[lo, hi)`` using prefix-only windows."""
    from boardroom.data.snapshot import Bars

    closes = bars.closes
    rows: list[dict] = []
    labels: list[bool] = []
    for i in range(lo, hi - horizon):
        window = Bars(symbol=bars.symbol, venue=bars.venue, df=bars.df.iloc[: i + 1], source=bars.source)
        f = model._features(window)
        rows.append({k: f[k] for k in ("momentum", "meanrev_z", "rsi_centered")})
        labels.append(bool(closes[i + horizon] > closes[i]))
    return rows, labels


def _net_edge_score(model, bars, *, lo: int, hi: int, horizon: int, cost_frac: float) -> float:
    """Mean per-trade net (after-cost) fractional return of ``model`` over a segment.

    Takes the side the model leans; mirrors the backtest's accounting so the score
    is comparable to the live gate. 0.0 if the model never trades in the segment.
    """
    from boardroom.data.snapshot import Bars

    closes = bars.closes
    total = 0.0
    n = 0
    for i in range(lo, hi - horizon):
        window = Bars(symbol=bars.symbol, venue=bars.venue, df=bars.df.iloc[: i + 1], source=bars.source)
        out = model.predict(window)
        if out.raw_confidence <= 0.0:
            continue
        realized = closes[i + horizon] / closes[i] - 1.0
        directional = realized if out.expected_return >= 0 else -realized
        total += directional - cost_frac
        n += 1
    return total / n if n else 0.0


def refit_directional(
    model,
    bars,
    *,
    warmup: int = 40,
    min_sample: int = 30,
    split_frac: float = 0.7,
    max_rel_step: float = 0.25,
    min_ratio: float = 0.6,
    cost_frac: float = 0.01,
) -> RefitResult:
    """Walk-forward re-fit of a DirectionalModel's coefficients, guardrailed.

    Returns a :class:`RefitResult`; the model is mutated in place ONLY when the
    refit is accepted, and even then each coefficient moves by at most
    ``max_rel_step`` toward the fitted value. Never raises on thin/degenerate
    data — it returns a rejecting result instead.
    """
    old = _coefficients(model)
    closes = bars.closes
    n = len(closes)
    horizon = max(1, int(round(getattr(model, "horizon_days", 5.0))))
    split = int(n * split_frac)

    if n - horizon - warmup < min_sample or split <= warmup or split >= n - horizon:
        return RefitResult(False, "insufficient data for a walk-forward split", 0, 0.0, 0.0, old, old)

    rows, labels = _training_set(model, bars, lo=warmup, hi=split, horizon=horizon)
    if not can_refit(len(rows), min_sample=min_sample):
        return RefitResult(False, f"only {len(rows)} training rows (< {min_sample})", len(rows), 0.0, 0.0, old, old)
    if len(set(labels)) < 2:
        return RefitResult(False, "degenerate labels (no up/down variation)", len(rows), 0.0, 0.0, old, old)

    candidate = replace(model)
    candidate.fit(rows, labels)

    in_score = _net_edge_score(candidate, bars, lo=warmup, hi=split, horizon=horizon, cost_frac=cost_frac)
    oos_score = _net_edge_score(candidate, bars, lo=split, hi=n, horizon=horizon, cost_frac=cost_frac)

    if not walk_forward_ok(in_score, oos_score, min_ratio=min_ratio):
        return RefitResult(
            False, "failed walk-forward (overfit risk)", len(rows), in_score, oos_score, old, _coefficients(candidate)
        )

    # Accept — move live coefficients toward the candidate by a bounded step.
    new_vec = bounded_weight_update(
        [old[k] for k in _COEF_NAMES],
        [getattr(candidate, k) for k in _COEF_NAMES],
        max_rel_step=max_rel_step,
    )
    for name, value in zip(_COEF_NAMES, new_vec):
        setattr(model, name, float(value))
    model.coefficients_source = "walk_forward_refit"
    model.version = "v1-fit"
    return RefitResult(True, "accepted", len(rows), in_score, oos_score, old, _coefficients(model))
