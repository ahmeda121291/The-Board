"""The CEO's reasoning layer — writes the human-readable rationale for a decision
the MATH already made (``boardroom.ceo.engine``). It adjudicates genuinely
qualitative factors and explains the call. It cannot change the decision or any
number; it annotates them.
"""

from __future__ import annotations

from boardroom.agents.llm import LLM
from boardroom.ceo.engine import RankedPitch
from boardroom.schemas import Decision, DecisionKind

_SYSTEM = (
    "You are the CEO of an autonomous capital allocator. The DECISION and all "
    "numbers are already fixed by deterministic math — you do not change them. "
    "In two or three sentences, explain the call in plain language: why this beat "
    "(or failed to beat) the floor, what the track-record/trust weighting implied, "
    "and why the null default (stay in the floor) was or wasn't overcome. Honest "
    "and terse. Most days the right answer is 'do nothing' — say so plainly."
)


def write_rationale(
    decision: Decision, ranked: list[RankedPitch], llm: LLM | None = None
) -> str:
    """Return a plain-language rationale. Falls back to the deterministic one."""
    llm = llm or LLM()
    top = ranked[0] if ranked else None
    summary = "\n".join(
        f"- {r.pitch.division.value} {r.pitch.symbol}: score={r.score:.3f} "
        f"trust={r.trust:.2f} size={r.trusted_size_cad:.2f} "
        f"{'(' + r.rejected_reason + ')' if r.rejected_reason else ''}"
        for r in ranked[:5]
    )
    user = (
        f"Decision: {decision.kind.value}"
        + (f" {decision.division.value} {decision.size_cad:.2f} CAD" if decision.division else "")
        + f"\nHurdle (floor) rate this horizon: {decision.hurdle_rate:.5f}\n"
        f"Ranked pitches:\n{summary or '(none)'}\n\n"
        "Explain the decision."
    )
    text = llm.complete(system=_SYSTEM, user=user, max_tokens=220)
    if text:
        return text
    # Deterministic fallback already set on the decision by the engine.
    if decision.kind == DecisionKind.HOLD:
        return decision.rationale or "Stay in the floor — nothing cleared the bar."
    return decision.rationale or "Decision made on deterministic ranking."
