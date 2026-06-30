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
    #: Minimum risk-adjusted score required to deviate from the floor — the
    #: CONSERVATIVE (grown-account) bar. The bar that makes "do nothing" win.
    deviation_threshold: float = 0.02
    #: Equity-scaled "aggression schedule" (off unless ``deviation_threshold_low``
    #: is set). When set, the bar is LOW for a small account (deploy and grow) and
    #: rises linearly to ``deviation_threshold`` as equity climbs from
    #: ``aggressive_below_cad`` to ``conservative_above_cad``. The hard caps
    #: (per-trade, daily-loss, drawdown, fee-drag) are untouched — this only
    #: changes how readily the CEO acts, never the blast radius.
    deviation_threshold_low: float | None = None
    aggressive_below_cad: float = 500.0
    conservative_above_cad: float = 5000.0
    #: Equity-scaled crypto Event position cap (off unless set). While the account
    #: is small the Event hard cap is this fraction (bold — defaults to the
    #: per-trade max); it tapers to ``caps.event_hard_cap_pct`` as equity grows.
    #: The daily-loss / drawdown / fee-drag breakers are untouched.
    event_cap_pct_small: float | None = None
    posteriors: dict[str, CalibrationPosterior] = field(default_factory=dict)
    leashes: dict[str, float] = field(default_factory=dict)

    def _ramp(self, equity: float, at_small: float, at_grown: float) -> float:
        """Linear aggression ramp: ``at_small`` while equity <= aggressive_below_cad,
        ``at_grown`` while >= conservative_above_cad, interpolated between. Works
        either direction (a rising bar, or a shrinking cap)."""
        lo_cad, hi_cad = self.aggressive_below_cad, self.conservative_above_cad
        if equity <= lo_cad:
            return at_small
        if hi_cad <= lo_cad or equity >= hi_cad:
            return at_grown
        frac = (equity - lo_cad) / (hi_cad - lo_cad)
        return at_small + frac * (at_grown - at_small)

    def _effective_threshold(self, equity: float) -> float:
        """The deviation bar at this equity. Smaller account -> lower bar."""
        if self.deviation_threshold_low is None:
            return self.deviation_threshold
        return self._ramp(equity, self.deviation_threshold_low, self.deviation_threshold)

    def _effective_caps(self, equity: float) -> RiskCaps:
        """Caps for this decision, with the crypto Event hard cap riding the
        aggression ramp (bold while small) when ``event_cap_pct_small`` is set.
        Per-trade, deployable, daily-loss, drawdown and fee-drag are untouched."""
        if self.event_cap_pct_small is None:
            return self.caps
        event_pct = self._ramp(equity, self.event_cap_pct_small, self.caps.event_hard_cap_pct)
        return RiskCaps(
            total_deployable_pct=self.caps.total_deployable_pct,
            per_trade_max_pct=self.caps.per_trade_max_pct,
            event_hard_cap_pct=event_pct,
            daily_loss_limit_pct=self.caps.daily_loss_limit_pct,
            max_drawdown_pct=self.caps.max_drawdown_pct,
            fee_drag_limit_pct=self.caps.fee_drag_limit_pct,
        )

    def _rank_one(
        self, pitch: Pitch, hurdle_rate: float, deployed_cad: float, portfolio_value_cad: float,
        caps: RiskCaps | None = None,
    ) -> RankedPitch:
        div = pitch.division.value
        caps = caps if caps is not None else self.caps

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
            caps=caps,
            deployed_cad=deployed_cad,
            portfolio_value_cad=portfolio_value_cad,
            leash=self.leashes.get(div, 1.0),
        )

        # 5. Risk-adjusted score (rank metric), computed on the trust-adjusted size.
        scored = pitch.model_copy(update={"capital_required": size}) if size > 0 else pitch
        score = risk_adjusted_score(scored, hurdle_rate) if size > 0 else -1.0
        reason = None if size > 0 else "sized to zero after trust/caps"
        return RankedPitch(pitch, trust, trusted_conf, size, score, reason)

    def decide(
        self,
        pitches: list[Pitch],
        *,
        hurdle_rate: float,
        deployed_cad: float = 0.0,
        portfolio_value_cad: float = 200.0,
    ) -> tuple[Decision, list[RankedPitch]]:
        """Rank pitches and return the CEO's verdict + the full ranking.

        - No fundable pitch survived the gates  -> FUND_NONE.
        - Survivors exist but none clears the deviation threshold -> HOLD (floor).
        - Otherwise -> FUND the top-ranked pitch at its trust-adjusted size.

        Hard caps resolve as percentages of ``portfolio_value_cad``.
        """
        caps = self._effective_caps(portfolio_value_cad)
        ranked = sorted(
            (self._rank_one(p, hurdle_rate, deployed_cad, portfolio_value_cad, caps) for p in pitches),
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
        threshold = self._effective_threshold(portfolio_value_cad)
        if best.score < threshold:
            return (
                Decision(
                    decision_id=decision_id,
                    kind=DecisionKind.HOLD,
                    hurdle_rate=hurdle_rate,
                    ranked_pitch_ids=ranked_ids,
                    rationale=(
                        f"Best score {best.score:.3f} below deviation threshold "
                        f"{threshold:.3f} — stay in the floor."
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
