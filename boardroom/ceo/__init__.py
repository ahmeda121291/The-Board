"""The CEO — judgment as structured math with a thin reasoning layer on top.

The ranking, the hurdle comparison, the trust-weighting, and the sizing are ALL
deterministic (scope §4). The LLM (``boardroom.agents.ceo``) only adjudicates
genuinely qualitative factors and writes the human-readable rationale — it never
squints at numbers and decides.
"""

from boardroom.ceo.engine import CEODecisionEngine, RankedPitch
from boardroom.ceo.hurdle import excess_over_floor, risk_adjusted_score
from boardroom.ceo.sizing import conviction_size

__all__ = [
    "CEODecisionEngine",
    "RankedPitch",
    "excess_over_floor",
    "risk_adjusted_score",
    "conviction_size",
]
