"""Core data contracts shared across the whole organization.

The ``Pitch`` is the standardized interface every division speaks, so the CEO
compares opportunities on common terms. The split between *computed* and
*narrative* fields is the load-bearing rule of the entire project (scope §2, §5):

    computed  -> produced by deterministic code from real data. Authoritative.
    narrative -> authored by the LLM. Prose only. May never set a number.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from pydantic import BaseModel, Field, NonNegativeFloat


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Division(str, enum.Enum):
    """The four orthogonal divisions plus the floor's resting state."""

    YIELD = "yield"          # the floor / benchmark (cash flow)
    DIRECTIONAL = "directional"  # equities/ETFs trend & mean-reversion (price)
    EVENT = "event"          # rare asymmetric crypto bets (reflexivity)
    EFFORT = "effort"        # non-market operating bets (work) — disabled at launch


class Venue(str, enum.Enum):
    KRAKEN = "kraken"
    IBKR = "ibkr"
    NONE = "none"  # the floor's resting state needs no execution venue


class DataSnapshot(BaseModel):
    """A freshness- and sanity-checked bundle of real market data.

    ``content_hash`` pins exactly what the division saw, so any decision is fully
    reconstructable (scope §5 "Auditability"). If ``is_fresh`` is False the
    division MUST abstain — no trade on garbage.
    """

    symbol: str
    venue: Venue
    as_of: datetime
    age_seconds: float
    is_fresh: bool
    rows: int
    content_hash: str
    source: str
    notes: str | None = None


class ComputedSignals(BaseModel):
    """The deterministic outputs the model consumed, logged verbatim.

    Free-form so each division logs its own feature set, but every value here is
    code-computed and unit-tested — never an LLM guess.
    """

    features: dict[str, float] = Field(default_factory=dict)
    model_name: str
    model_version: str
    expected_return: float            # fractional, e.g. 0.012 == +1.2%
    win_probability: float            # [0, 1]
    raw_confidence: float             # model confidence before trust adjustment
    horizon_days: float


class Pitch(BaseModel):
    """A division's standardized proposal to the CEO.

    Quantitative fields are COMPUTED; narrative fields are LLM-AUTHORED. The
    ``Pitch.build`` constructor is the only sanctioned way to assemble one — it
    takes computed numbers as authoritative and lets the LLM fill prose only.
    """

    # identity / provenance
    pitch_id: str
    division: Division
    venue: Venue
    symbol: str
    created_at: datetime = Field(default_factory=utcnow)
    snapshot: DataSnapshot
    signals: ComputedSignals

    # ---- COMPUTED (authoritative; LLM may not set these) --------------------
    capital_required: NonNegativeFloat   # CAD, from the sizing function
    expected_return: float               # fractional excess vs nothing
    confidence: float                    # [0,1], trust-adjusted win-probability
    time_horizon_days: float             # when this resolves & can be scored
    max_loss: NonNegativeFloat           # CAD worst-case incl. stop, liquidity, cost
    expected_cost: NonNegativeFloat      # CAD round-trip fees + slippage + FX

    # ---- NARRATIVE (LLM-authored prose only) --------------------------------
    opportunity: str = ""   # what the bet is and the action to take
    why_now: str = ""       # the catalyst, grounded in the computed signals

    @property
    def expected_return_cad(self) -> float:
        return self.capital_required * self.expected_return

    @property
    def net_edge_cad(self) -> float:
        """Expected return minus expected transaction cost, in CAD.

        The cost gate (scope §8) rejects any pitch whose edge doesn't clear cost.
        """
        return self.expected_return_cad - self.expected_cost

    def clears_cost(self) -> bool:
        return self.net_edge_cad > 0


class DecisionKind(str, enum.Enum):
    FUND = "fund"            # deploy into a specific division
    FUND_NONE = "fund_none"  # nothing pitched today cleared the bar
    HOLD = "hold"           # stay in the floor (the default prior)


class Decision(BaseModel):
    """The CEO's daily verdict. Exactly one kind."""

    decision_id: str
    created_at: datetime = Field(default_factory=utcnow)
    kind: DecisionKind
    division: Division | None = None       # set iff kind == FUND
    pitch_id: str | None = None
    size_cad: float = 0.0
    hurdle_rate: float = 0.0               # the floor's carry, the bar to beat
    rationale: str = ""                    # LLM-authored, grounded in the ranking
    ranked_pitch_ids: list[str] = Field(default_factory=list)
    live: bool = False                     # whether this was executed for real


class ProcessLuckTag(str, enum.Enum):
    """The Critic's 2x2: reward good process even when unlucky."""

    GOOD_PROCESS_GOOD_OUTCOME = "good_process_good_outcome"
    GOOD_PROCESS_BAD_OUTCOME = "good_process_bad_outcome"   # unlucky — don't punish
    BAD_PROCESS_GOOD_OUTCOME = "bad_process_good_outcome"   # lucky — don't reward
    BAD_PROCESS_BAD_OUTCOME = "bad_process_bad_outcome"


class ResolvedOutcome(BaseModel):
    """A decision after its horizon elapsed — what actually happened."""

    decision_id: str
    division: Division
    resolved_at: datetime = Field(default_factory=utcnow)
    predicted_return: float
    realized_return: float
    predicted_confidence: float
    win: bool
    pnl_cad: float
    cost_cad: float
    inside_band: bool                      # realized within the predicted band?
    process_luck: ProcessLuckTag | None = None
    postmortem: str = ""                   # LLM-authored, short & structured
