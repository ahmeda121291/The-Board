"""The Critic's narrative layer — a short, structured post-mortem for a resolved
decision. The quantitative judgement (calibration, Brier, process-vs-luck) is
deterministic in ``boardroom.measurement.critic``; this only writes the prose
that tags recurring error trends to feed the adaptive engine (scope §8).
"""

from __future__ import annotations

from boardroom.agents.llm import LLM
from boardroom.schemas import ProcessLuckTag, ResolvedOutcome

_SYSTEM = (
    "You are the Critic in an autonomous capital allocator. Judge the PROCESS, "
    "not just the P&L. Reward good process even when unlucky; punish bad process "
    "even when lucky. Given predicted vs realized and the process/luck tag, write "
    "a two-sentence post-mortem and, if any, name ONE recurring error pattern to "
    "watch. Terse and concrete."
)


def write_postmortem(outcome: ResolvedOutcome, llm: LLM | None = None) -> str:
    llm = llm or LLM()
    tag = outcome.process_luck.value if outcome.process_luck else "untagged"
    user = (
        f"Division: {outcome.division.value}\n"
        f"predicted_return: {outcome.predicted_return:.4f}\n"
        f"realized_return: {outcome.realized_return:.4f}\n"
        f"predicted_confidence: {outcome.predicted_confidence:.2f}\n"
        f"win: {outcome.win}\ninside_band: {outcome.inside_band}\n"
        f"pnl_cad: {outcome.pnl_cad:.2f}\nprocess_luck: {tag}\n\n"
        "Write the post-mortem."
    )
    text = llm.complete(system=_SYSTEM, user=user, max_tokens=180)
    if text:
        return text
    # Deterministic fallback.
    luck = {
        ProcessLuckTag.GOOD_PROCESS_BAD_OUTCOME: "Good process, unlucky outcome — do not change behavior.",
        ProcessLuckTag.BAD_PROCESS_GOOD_OUTCOME: "Bad process, lucky outcome — do not reward this.",
        ProcessLuckTag.GOOD_PROCESS_GOOD_OUTCOME: "Sound process and a good outcome.",
        ProcessLuckTag.BAD_PROCESS_BAD_OUTCOME: "Bad process and a bad outcome — fix the process.",
    }.get(outcome.process_luck, "Outcome recorded.")
    band = "inside" if outcome.inside_band else "outside"
    return f"{luck} Realized {outcome.realized_return:.3f} vs predicted {outcome.predicted_return:.3f} ({band} band)."
