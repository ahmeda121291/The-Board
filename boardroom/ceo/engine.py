"""The CEO's deterministic decision engine.

Pure math: cost gate -> floor gate -> trust-weighting -> conviction sizing ->
risk-adjusted ranking -> null-default arbitration. The LLM never enters here; it
only writes the rationale afterward (``boardroom.agents.ceo``).

The single most important rule (scope §4): the null choice — stay in the floor —
is the DEFAULT prior. A division must produce sufficient evidence to deviate.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from boardroom.adaptive.calibration import CalibrationPosterior, trust_multiplier
from boardroom.ceo.hurdle import excess_over_floor, risk_adjusted_score
from boardroom.ceo.sizing import conviction_size
from boardroom.config import RiskCaps
from boardroom.schemas import Decision, DecisionKind, Division, Pitch


@dataclass
class RankedPitch:
    pitch: Pitch
    trust: float                 # trust multiplier in [0,1]
    trusted_confidence: float    # stated confidence x trust
    trusted_size_cad: float      # conviction size after trust + leash + caps
    score: float                 # risk-adjusted net excess edge per unit risk
    rejected_reason: str | None = None


@dataclass
class CEODecisionEngine:
    caps: RiskCaps
    #: Minimum risk-adjusted score required to deviate from the floor. The bar
    #: that makes "do nothing" win most days.
    deviation_threshold: float = 0.02
    posteriors: dict[str, CalibrationPosterior] = field(default_factory=dict)
    leashes: dict[str, float] = field(default_factory=dict)

    def _rank_one(self, pitch: Pitch, hurdle_rate: float, deployed_cad: float) -> RankedPitch:
        div = pitch.division.value

        # 1. Cost gate — drop anything whose edge doesn't clear its expected cost.
        if not pitch.clears_cost():
            return RankedPitch(pitch, 0.0, 0.0, 0.0, -1.0, "fails cost gate")

        # 2. Floor gate — must beat carry over the horizon.
        if excess_over_floor(pitch, hurdle_rate) <= 0:
            return RankedPitch(pitch, 0.0, 0.0, 0.0, -1.0, "does not beat the floor")

        # 3. Trust-weighting — distrust stated confidence, trust demonstrated calibration.
        posterior = self.posteriors.get(div)
        trust = (
            trust_multiplier(posterior, pitch.confidence) if posterior is not None else 0.5
        )
        trusted_conf = pitch.confidence * trust

        # 4. Conviction sizing with the trust-adjusted confidence and the leash.
        risk_unit = (pitch.max_loss / pitch.capital_required) if pitch.capital_required else 0.0
        size = conviction_size(
            division=pitch.division,
            edge=excess_over_floor(pitch, hurdle_rate),
            win_probability=trusted_conf,
            risk_unit_fraction=risk_unit,
            caps=self.caps,
            deployed_cad=deployed_cad,
            leash=self.leashes.get(div, 1.0),
        )

        # 5. Risk-adjusted score (rank metric), computed on the trust-adjusted size.
        scored = pitch.model_copy(update={"capital_required": size}) if size > 0 else pitch
        score = risk_adjusted_score(scored, hurdle_rate) if size > 0 else -1.0
        reason = None if size > 0 else "sized to zero after trust/caps"
        return RankedPitch(pitch, trust, trusted_conf, size, score, reason)

    def decide(
        self, pitches: list[Pitch], *, hurdle_rate: float, deployed_cad: float = 0.0
    ) -> tuple[Decision, list[RankedPitch]]:
        """Rank pitches and return the CEO's verdict + the full ranking.

        - No fundable pitch survived the gates  -> FUND_NONE.
        - Survivors exist but none clears the deviation threshold -> HOLD (floor).
        - Otherwise -> FUND the top-ranked pitch at its trust-adjusted size.
        """
        ranked = sorted(
            (self._rank_one(p, hurdle_rate, deployed_cad) for p in pitches),
            key=lambda r: r.score,
            reverse=True,
        )
        survivors = [r for r in ranked if r.score > 0 and r.trusted_size_cad > 0]
        ranked_ids = [r.pitch.pitch_id for r in ranked]
        decision_id = str(uuid.uuid4())

        if not survivors:
            kind = DecisionKind.FUND_NONE if pitches else DecisionKind.HOLD
            return (
                Decision(
                    decision_id=decision_id,
                    kind=kind,
                    hurdle_rate=hurdle_rate,
                    ranked_pitch_ids=ranked_ids,
                    rationale=(
                        "No pitch cleared cost and the floor."
                        if pitches
                        else "No fundable pitches — stay in the floor."
                    ),
                ),
                ranked,
            )

        best = survivors[0]
        if best.score < self.deviation_threshold:
            return (
                Decision(
                    decision_id=decision_id,
                    kind=DecisionKind.HOLD,
                    hurdle_rate=hurdle_rate,
                    ranked_pitch_ids=ranked_ids,
                    rationale=(
                        f"Best score {best.score:.3f} below deviation threshold "
                        f"{self.deviation_threshold:.3f} — stay in the floor."
                    ),
                ),
                ranked,
            )

        return (
            Decision(
                decision_id=decision_id,
                kind=DecisionKind.FUND,
                division=best.pitch.division,
                pitch_id=best.pitch.pitch_id,
                size_cad=best.trusted_size_cad,
                hurdle_rate=hurdle_rate,
                ranked_pitch_ids=ranked_ids,
                rationale=(
                    f"{best.pitch.division.value} cleared the bar: score {best.score:.3f}, "
                    f"trust {best.trust:.2f}, size {best.trusted_size_cad:.2f} CAD."
                ),
            ),
            ranked,
        )
