"""The risk manager — adversarially challenges every surviving pitch.

LLMs are sycophantic; a risk manager that "reviews" will cave. So the VETO power
here is code, not vibes: hard objections are deterministic checks the LLM cannot
talk its way past (max loss, cost coverage, liquidity, cap breaches). The LLM
only adds qualitative concerns on top — it can raise an alarm, never lower one.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from boardroom.agents.llm import LLM
from boardroom.config import RiskCaps
from boardroom.schemas import Pitch

_SYSTEM = (
    "You are an adversarial risk manager. Your job is to find the single best "
    "reason this trade FAILS, not to approve it. Assume the pitch is too "
    "optimistic. Challenge liquidity, execution slippage, FX, stop integrity, and "
    "the realism of the expected return. Do NOT rubber-stamp. Reply with one "
    "sharp objection or 'NO MATERIAL QUALITATIVE OBJECTION' if you genuinely "
    "cannot find one. Two sentences max."
)


@dataclass
class RiskChallenge:
    pitch_id: str
    approved: bool
    hard_objections: list[str] = field(default_factory=list)
    qualitative_concern: str = ""
    recommended_max_size_cad: float | None = None


@dataclass
class RiskManager:
    caps: RiskCaps
    min_liquidity_cad: float = 50_000.0  # mean daily $ volume floor for tradability
    max_loss_fraction_ceiling: float = 0.6  # max_loss may not exceed this of capital
    llm: LLM | None = None

    def challenge(self, pitch: Pitch, portfolio_value_cad: float = 200.0) -> RiskChallenge:
        objections: list[str] = []
        daily_limit = self.caps.daily_loss_limit_cad(portfolio_value_cad)

        # 1. Cost coverage — the edge must clear expected cost.
        if not pitch.clears_cost():
            objections.append(
                f"edge {pitch.expected_return_cad:.2f} does not clear cost "
                f"{pitch.expected_cost:.2f} CAD"
            )

        # 2. Max loss vs the daily loss limit (percent of portfolio).
        if pitch.max_loss > daily_limit:
            objections.append(
                f"max_loss {pitch.max_loss:.2f} exceeds daily loss limit "
                f"{daily_limit:.2f} CAD"
            )

        # 3. Stop integrity — max_loss shouldn't be most of the position.
        if pitch.capital_required > 0 and (
            pitch.max_loss / pitch.capital_required > self.max_loss_fraction_ceiling
        ):
            objections.append("stop too wide: max_loss is an unsafe fraction of capital")

        # 4. Liquidity — only if the model surfaced a liquidity proxy.
        liq = pitch.signals.features.get("liquidity")
        if liq is not None and liq < self.min_liquidity_cad:
            objections.append(f"insufficient liquidity: {liq:.0f} < {self.min_liquidity_cad:.0f}")

        # 5. Hard cap on size for the division (percent of portfolio).
        cap = self.caps.cap_for(pitch.division.value, portfolio_value_cad)
        recommended = min(pitch.capital_required, cap)

        concern = self._qualitative(pitch)
        return RiskChallenge(
            pitch_id=pitch.pitch_id,
            approved=len(objections) == 0,
            hard_objections=objections,
            qualitative_concern=concern,
            recommended_max_size_cad=recommended,
        )

    def _qualitative(self, pitch: Pitch) -> str:
        llm = self.llm or LLM()
        user = (
            f"Pitch: {pitch.division.value} {pitch.symbol} on {pitch.venue.value}. "
            f"expected_return={pitch.expected_return:.4f}, win_prob={pitch.confidence:.2f}, "
            f"size={pitch.capital_required:.2f} CAD, max_loss={pitch.max_loss:.2f} CAD, "
            f"expected_cost={pitch.expected_cost:.2f} CAD, horizon={pitch.time_horizon_days:.0f}d, "
            f"features={pitch.signals.features}. Find the best reason this fails."
        )
        text = llm.complete(system=_SYSTEM, user=user, max_tokens=160, temperature=0.5)
        return text or "No qualitative review (LLM unavailable); hard checks applied."
