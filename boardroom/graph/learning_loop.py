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
    resolved outcomes, within the adaptive guardrails.

    ``n_resolved`` and ``net_vs_floor_cad`` are recomputed from the actual
    outcome history every time (they previously were never updated, so the
    retirement sample floor could never be reached and divisions starved
    silently at leash zero instead of retiring with an audit trail).
    Calibration is judged on a ROLLING window of the most recent
    ``CALIBRATION_WINDOW`` outcomes so old results age out — trust follows what
    the division is doing lately, in both directions. A retired division stays
    retired until an explicit ``revive_division`` (no auto-revive)."""
    from boardroom.config import get_settings

    s = get_settings()
    repo = repo or get_repository()
    state = repo.get_division_state(division)
    outcomes = repo.recent_outcomes(division=division, limit=1000)
    ordered = sorted(outcomes, key=lambda o: o.resolved_at)

    n_resolved = len(ordered)
    net_vs_floor = sum(o.pnl_cad - o.cost_cad for o in ordered)
    window = ordered[-max(1, int(s.calibration_window)):]
    posterior = posterior_from_outcomes(
        division, window, prior=CalibrationPosterior(division, alpha=1.0, beta=1.0)
    )
    new_leash = update_leash(
        state.leash,
        posterior=posterior,
        realized_edge_vs_floor=net_vs_floor,
        leash_min=s.leash_min,
    )
    was_retired = state.retired
    retired = was_retired or should_retire(
        posterior=posterior,
        net_vs_floor_cad=net_vs_floor,
        n_resolved=n_resolved,
        min_sample=int(s.retire_min_sample),
        mean_below=s.retire_mean_below,
    )

    state.alpha = posterior.alpha
    state.beta = posterior.beta
    state.n_resolved = n_resolved
    state.net_vs_floor_cad = net_vs_floor
    state.leash = 0.0 if retired else new_leash
    state.retired = retired
    repo.upsert_division_state(state)
    if retired and not was_retired:
        repo.audit(
            "division_retired",
            {"division": division, "mean": posterior.mean(), "net_vs_floor_cad": round(net_vs_floor, 2)},
        )

    return LearningUpdate(
        division=division,
        posterior_mean=posterior.mean(),
        new_leash=state.leash,
        retired=retired,
        n_resolved=n_resolved,
    )


def revive_division(
    division: str, repo: Repository | None = None, *, leash: float = 0.5
) -> DivisionState:
    """Explicit human override: bring a retired (or leash-starved) division back.

    Resets the division to a fresh flat prior (``Beta(1,1)``), clears the
    retired flag, and hands it a working leash (default 0.5 — real capital,
    not the floor). The comeback is audited. This is the ONLY revival path;
    the learning loop never un-retires on its own."""
    repo = repo or get_repository()
    state = repo.get_division_state(division)
    state.alpha = 1.0
    state.beta = 1.0
    state.leash = min(1.0, max(0.0, leash))
    state.retired = False
    repo.upsert_division_state(state)
    repo.audit("division_revived", {"division": division, "leash": state.leash})
    return state


def weekly_quality_report(repo: Repository | None = None) -> str:
    repo = repo or get_repository()
    outcomes = repo.recent_outcomes(limit=1000)
    rep = critique(outcomes)
    return "\n".join(rep.summary_lines()) if hasattr(rep, "summary_lines") else (
        f"resolved={rep.n_resolved} calib_err={rep.calibration_error:.3f} "
        f"brier={rep.brier_score:.3f} inside_band={rep.inside_band_rate:.2%}"
    )
