"""Learning loop (scope §10): per resolved decision + weekly.

The Critic scores each resolved decision; calibration updates the CEO's trust and
each division's risk leash; persistently broken divisions are benched. The
anti-overfit guardrails live in ``boardroom.adaptive`` and are applied here.
"""

from __future__ import annotations

from dataclasses import dataclass

from boardroom.adaptive.calibration import CalibrationPosterior, posterior_from_outcomes
from boardroom.adaptive.leash import update_leash
from boardroom.adaptive.retirement import should_retire
from boardroom.agents.critic import write_postmortem
from boardroom.measurement.critic import critique, tag_process_luck
from boardroom.persistence.repository import DivisionState, Repository, get_repository
from boardroom.schemas import ResolvedOutcome


@dataclass
class LearningUpdate:
    division: str
    posterior_mean: float
    new_leash: float
    retired: bool
    n_resolved: int


def record_resolution(outcome: ResolvedOutcome, repo: Repository | None = None) -> ResolvedOutcome:
    """Tag, post-mortem, and persist a freshly resolved outcome."""
    repo = repo or get_repository()
    good_process = outcome.inside_band  # within the predicted band == sound process
    outcome.process_luck = tag_process_luck(good_process=good_process, win=outcome.win)
    outcome.postmortem = write_postmortem(outcome)
    repo.save_outcome(outcome)
    return outcome


def update_division(division: str, repo: Repository | None = None) -> LearningUpdate:
    """Re-derive calibration, leash, and retirement for one division from its
    resolved outcomes, within the adaptive guardrails."""
    repo = repo or get_repository()
    state = repo.get_division_state(division)
    outcomes = repo.recent_outcomes(division=division, limit=1000)

    posterior = posterior_from_outcomes(
        division, outcomes, prior=CalibrationPosterior(division, alpha=1.0, beta=1.0)
    )
    net_vs_floor = state.net_vs_floor_cad
    new_leash = update_leash(
        state.leash, posterior=posterior, realized_edge_vs_floor=net_vs_floor
    )
    retired = should_retire(
        posterior=posterior, net_vs_floor_cad=net_vs_floor, n_resolved=state.n_resolved
    )

    state.alpha = posterior.alpha
    state.beta = posterior.beta
    state.leash = 0.0 if retired else new_leash
    state.retired = retired
    repo.upsert_division_state(state)
    if retired:
        repo.audit("division_retired", {"division": division, "mean": posterior.mean()})

    return LearningUpdate(
        division=division,
        posterior_mean=posterior.mean(),
        new_leash=state.leash,
        retired=retired,
        n_resolved=state.n_resolved,
    )


def weekly_quality_report(repo: Repository | None = None) -> str:
    repo = repo or get_repository()
    outcomes = repo.recent_outcomes(limit=1000)
    rep = critique(outcomes)
    return "\n".join(rep.summary_lines()) if hasattr(rep, "summary_lines") else (
        f"resolved={rep.n_resolved} calib_err={rep.calibration_error:.3f} "
        f"brier={rep.brier_score:.3f} inside_band={rep.inside_band_rate:.2%}"
    )
