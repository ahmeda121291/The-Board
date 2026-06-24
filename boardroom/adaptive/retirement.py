"""The kill switch — divisions that don't earn their keep get retired (scope §6).

Retirement is the terminal anti-overfit guardrail: a division that is
persistently miscalibrated or net-negative after costs over a meaningful sample
is shut off. A retired division's leash goes to ZERO — it deploys no capital —
and it can only revive after explicit re-validation (a fresh backtest / a new
seed prior, handled by the orchestrator, not here).

The crucial counterweight is the sample floor. Below ``min_sample`` resolved
outcomes we NEVER retire, no matter how ugly the early numbers look. A small
sample of bad luck is not evidence of a broken edge.
"""

from __future__ import annotations

from boardroom.adaptive.calibration import CalibrationPosterior


def should_retire(
    *,
    posterior: CalibrationPosterior,
    net_vs_floor_cad: float,
    n_resolved: int,
    min_sample: int = 20,
) -> bool:
    """Decide whether to retire a division.

    Returns ``True`` only after at least ``min_sample`` resolved outcomes AND
    either of:

    - persistent miscalibration: ``posterior.mean() < 0.45``, or
    - net-negative vs the floor after cost: ``net_vs_floor_cad < 0``.

    Below ``min_sample`` resolved outcomes this always returns ``False`` — not
    enough evidence to justify the kill switch.

    A ``True`` verdict means the orchestrator must drop this division's leash to
    ZERO. The division can only come back after re-validation (a new backtest
    seeds a fresh prior); this function does not implement revival.
    """
    if n_resolved < min_sample:
        return False
    miscalibrated = posterior.mean() < 0.45
    net_negative = net_vs_floor_cad < 0.0
    return miscalibrated or net_negative
