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
    min_sample: int = 30,
    mean_below: float = 0.35,
) -> bool:
    """Decide whether to retire a division.

    Returns ``True`` only after at least ``min_sample`` resolved outcomes AND
    BOTH of (owner mandate 2026-08-04 — retirement is for divisions that are
    demonstrably broken, not merely cold):

    - persistent miscalibration: ``posterior.mean() < mean_below``, and
    - net-negative vs the floor after cost: ``net_vs_floor_cad < 0``.

    The old rule (either condition, at a 0.45 mean bar) retired any division
    running below a coin-flip during a losing stretch — combined with the
    leash walking to zero it amounted to a one-way shutdown. Requiring both
    conditions on a rolling calibration window keeps a cold-but-recoverable
    division trading at the leash floor while still killing one that loses
    money AND can't call its shots over a real sample.

    Below ``min_sample`` resolved outcomes this always returns ``False`` — not
    enough evidence to justify the kill switch.

    A ``True`` verdict means the orchestrator must drop this division's leash to
    ZERO. The division comes back only via explicit human revival
    (``boardroom revive`` seeds a fresh prior); this function does not
    implement revival.
    """
    if n_resolved < min_sample:
        return False
    miscalibrated = posterior.mean() < mean_below
    net_negative = net_vs_floor_cad < 0.0
    return miscalibrated and net_negative
