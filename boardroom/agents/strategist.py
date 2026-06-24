"""The Strategist (CFO) — the reflective agent that studies the scoreboard.

It reads the whole measurement layer — performance, per-division calibration,
recurring error patterns, what the adaptive engine re-weighted, the reserve — and
writes a strategic review: a headline, a plain-language analysis, and grounded
recommendations.

Discipline (scope §6): it may surface *parameter* tweaks as safe/automatic, but
any STRUCTURAL change (new signal/division, changed mandate or hard cap) is
tagged ``requires_human`` — the CFO recommends, a human ratifies. Autonomous
structural self-modification is the failure mode we refuse to build.

The standing and the recommendations are computed deterministically from real
records; the LLM only writes the narrative grounded in those facts.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from boardroom.adaptive.calibration import CalibrationPosterior
from boardroom.agents.llm import LLM
from boardroom.measurement.critic import critique
from boardroom.persistence.repository import Repository
from boardroom.schemas import Division

_DIVISIONS = [d.value for d in Division]
_MIN_SAMPLE = 20  # outcomes before calibration verdicts are trusted


@dataclass
class StrategyReview:
    headline: str
    narrative: str
    recommendations: list[dict] = field(default_factory=list)
    standing: dict = field(default_factory=dict)


def build_standing(repo: Repository, starting_portfolio_cad: float) -> dict:
    """Deterministic snapshot of where the organization stands."""
    outcomes = repo.recent_outcomes(limit=5000)
    realized = sum(o.pnl_cad for o in outcomes)
    cost = sum(o.cost_cad for o in outcomes)
    equity = starting_portfolio_cad + realized
    roi = realized / starting_portfolio_cad if starting_portfolio_cad else 0.0

    sys = repo.get_system_state()
    crit = critique(outcomes)

    divisions = []
    for d in _DIVISIONS:
        st = repo.get_division_state(d)
        post = CalibrationPosterior(d, st.alpha, st.beta)
        divisions.append(
            {
                "division": d,
                "calibration_mean": round(post.mean(), 3),
                "n_observed": round(post.n(), 1),
                "n_resolved": st.n_resolved,
                "leash": round(st.leash, 2),
                "retired": st.retired,
                "shadow": st.shadow,
                "net_vs_floor_cad": round(st.net_vs_floor_cad, 2),
            }
        )

    return {
        "equity_cad": round(equity, 2),
        "starting_cad": starting_portfolio_cad,
        "realized_pnl_cad": round(realized, 2),
        "roi": round(roi, 4),
        "cost_cad": round(cost, 2),
        "reserve_cad": round(sys.get("reserve_cad", 0.0), 2),
        "n_resolved_total": len(outcomes),
        "calibration_error": round(crit.calibration_error, 3),
        "brier": round(crit.brier_score, 3),
        "inside_band_rate": round(crit.inside_band_rate, 3),
        "process_luck": crit.process_luck_counts,
        "divisions": divisions,
    }


def build_recommendations(standing: dict) -> list[dict]:
    """Grounded, deterministic recommendations. Structural ones require a human."""
    recs: list[dict] = []
    n_total = standing["n_resolved_total"]

    if n_total < _MIN_SAMPLE:
        recs.append(
            {
                "area": "system",
                "suggestion": (
                    f"Only {n_total} resolved outcome(s) so far — keep accruing evidence "
                    "before increasing risk. Holding the floor is correct here."
                ),
                "requires_human": False,
            }
        )

    for d in standing["divisions"]:
        name = d["division"]
        if name in ("yield", "effort"):
            continue
        if d["n_resolved"] >= _MIN_SAMPLE and d["calibration_mean"] < 0.45:
            recs.append(
                {
                    "area": name,
                    "suggestion": (
                        f"{name} is miscalibrated ({d['calibration_mean']:.0%} hit rate over "
                        f"{d['n_resolved']} outcomes) — leash auto-reduced. Review its model/signals."
                    ),
                    "requires_human": True,
                }
            )
        if d["n_resolved"] >= _MIN_SAMPLE and d["net_vs_floor_cad"] < 0:
            recs.append(
                {
                    "area": name,
                    "suggestion": (
                        f"{name} is net-negative vs the floor ({d['net_vs_floor_cad']:.2f} CAD) — "
                        "candidate for benching. Confirm before retiring."
                    ),
                    "requires_human": True,
                }
            )
        if d["n_resolved"] >= _MIN_SAMPLE and d["calibration_mean"] > 0.60 and d["net_vs_floor_cad"] > 0:
            recs.append(
                {
                    "area": name,
                    "suggestion": (
                        f"{name} is calibrated and earning ({d['calibration_mean']:.0%}); its leash "
                        "can grow within guardrails (automatic)."
                    ),
                    "requires_human": False,
                }
            )

    if standing["reserve_cad"] > 0:
        recs.append(
            {
                "area": "reserve",
                "suggestion": (
                    f"{standing['reserve_cad']:.2f} CAD locked in the untouchable reserve by the "
                    "ratchet — protected from re-risking."
                ),
                "requires_human": False,
            }
        )
    return recs


_SYSTEM = (
    "You are the CFO / Chief Strategist of an autonomous capital allocator. You are "
    "given a COMPUTED standing (real numbers) and a list of grounded recommendations. "
    "Write a concise strategic review: 3-5 sentences of plain-language analysis of how "
    "the organization is doing, what's working, what isn't, and what you're watching. "
    "Ground every claim in the numbers given; invent nothing. Be honest — if there's "
    "little data, say the disciplined thing is to keep holding. Do not propose autonomous "
    "structural changes; those are flagged for human review."
)


def _headline(standing: dict) -> str:
    roi = standing["roi"]
    n = standing["n_resolved_total"]
    if n == 0:
        return "No resolved decisions yet — establishing a track record, holding the floor."
    return f"ROI {roi:+.2%} over {n} resolved · equity {standing['equity_cad']:.2f} CAD"


def generate_review(
    repo: Repository, llm: LLM | None = None, starting_portfolio_cad: float = 200.0
) -> StrategyReview:
    llm = llm or LLM()
    standing = build_standing(repo, starting_portfolio_cad)
    recommendations = build_recommendations(standing)
    headline = _headline(standing)

    user = (
        f"STANDING (computed, real):\n{standing}\n\n"
        f"GROUNDED RECOMMENDATIONS:\n{recommendations}\n\n"
        "Write the strategic review (analysis only; the recommendations are already listed)."
    )
    narrative = llm.complete(system=_SYSTEM, user=user, max_tokens=320)
    if not narrative:
        narrative = _fallback_narrative(standing, recommendations)

    return StrategyReview(
        headline=headline,
        narrative=narrative,
        recommendations=recommendations,
        standing=standing,
    )


def _fallback_narrative(standing: dict, recs: list[dict]) -> str:
    n = standing["n_resolved_total"]
    if n == 0:
        return (
            "The organization has not resolved a decision yet, so no division has earned a "
            "track record. The correct posture is exactly what the CEO is doing: hold the floor "
            "and accrue evidence. Calibration and trust will build as outcomes resolve; until "
            "then, deploying real risk would be guessing, not allocating."
        )
    parts = [
        f"Realized P&L is {standing['realized_pnl_cad']:+.2f} CAD ({standing['roi']:+.2%}) over "
        f"{n} resolved decisions, with {standing['cost_cad']:.2f} CAD of cost drag.",
        f"Calibration error sits at {standing['calibration_error']:.2f} (lower is better).",
    ]
    if standing["reserve_cad"] > 0:
        parts.append(f"{standing['reserve_cad']:.2f} CAD is locked in the protected reserve.")
    if recs:
        parts.append(f"{len(recs)} recommendation(s) are listed below.")
    return " ".join(parts)


def generate_and_save_review(
    repo: Repository, llm: LLM | None = None, starting_portfolio_cad: float = 200.0
) -> StrategyReview:
    review = generate_review(repo, llm, starting_portfolio_cad)
    repo.save_strategy_review(
        review.headline, review.narrative, review.recommendations, review.standing
    )
    return review
