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

_QUOTES = ("USDT", "USDC", "CAD", "USD")


def _base_of(symbol: str) -> str:
    """Base asset of a pair symbol (SOLUSD → SOL) — tilt keys are per-asset."""
    s = symbol.upper()
    for q in _QUOTES:
        if s.endswith(q) and len(s) > len(q):
            return s[: -len(q)]
    return s


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
    #: Exchange minimum-order floor (CAD). A funded size below this is bumped up to
    #: it (clamped to the per-trade cap / headroom) so small-conviction crypto
    #: orders clear the venue's minimum instead of being rejected. 0 disables.
    min_order_cad: float = 0.0
    #: Conviction floor as a fraction of the book (owner mandate 2026-08-05):
    #: the effective floor is max(min_order_cad, min_order_pct × portfolio), so
    #: funded positions are a meaningful slice of equity and scale as it grows
    #: instead of pinning at the exchange minimum forever. Same clamps apply.
    min_order_pct: float = 0.0
    #: Kelly fraction for conviction sizing (owner dial 2026-08-05: full Kelly).
    #: The hard caps still clamp every size, whatever this is set to.
    kelly_fraction: float = 0.25
    posteriors: dict[str, CalibrationPosterior] = field(default_factory=dict)
    leashes: dict[str, float] = field(default_factory=dict)
    #: Per-ASSET realized track record tilt (trade autopsy 2026-08-05: repeat
    #: winners — KAITO 7/7 +$43 — and repeat losers — TRU 0/4 −$23 — but
    #: nothing remembered the asset, only the division). A positive score is
    #: multiplied by (1 + tilt), tilt in [-0.6, +0.6] computed by CODE from
    #: resolved outcomes, so proven coins outrank proven losers at the margin.
    #: A losing coin is demoted, never banned — a strong fresh signal can
    #: still fund it and give it a chance to redeem.
    symbol_tilts: dict[str, float] = field(default_factory=dict)

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
            kelly_fraction=self.kelly_fraction,
        )

        # 5. Risk-adjusted score (rank metric), computed on the trust-adjusted size.
        scored = pitch.model_copy(update={"capital_required": size}) if size > 0 else pitch
        score = risk_adjusted_score(scored, hurdle_rate) if size > 0 else -1.0
        # 6. Per-asset track-record tilt: multiply a positive score by (1+tilt)
        #    so coins that have actually made money outrank coins that have
        #    actually lost it. Gates/caps/sizing are already settled — this
        #    only reorders the queue.
        if score > 0 and self.symbol_tilts:
            tilt = self.symbol_tilts.get(_base_of(pitch.symbol), 0.0)
            if tilt:
                score *= 1.0 + tilt
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

        # Conviction floor: a small-conviction size can land below the exchange
        # minimum (rejected) or at dust that can't compound. Bump a funded size
        # up to max(exchange minimum, min_order_pct of the book) — but never
        # above the per-trade cap or the deployable headroom, so the floor can
        # never breach the risk envelope.
        size = best.trusted_size_cad
        floor = max(
            self.min_order_cad,
            max(0.0, self.min_order_pct) * max(0.0, portfolio_value_cad),
        )
        if floor > 0 and 0 < size < floor:
            per_trade = caps.cap_for(best.pitch.division.value, portfolio_value_cad)
            headroom = max(0.0, caps.deployable_cad(portfolio_value_cad) - deployed_cad)
            size = round(min(floor, per_trade, headroom), 2)
            best.trusted_size_cad = size  # keep the ranking display consistent

        return (
            Decision(
                decision_id=decision_id,
                kind=DecisionKind.FUND,
                division=best.pitch.division,
                pitch_id=best.pitch.pitch_id,
                size_cad=size,
                hurdle_rate=hurdle_rate,
                ranked_pitch_ids=ranked_ids,
                rationale=(
                    f"{best.pitch.division.value} cleared the bar: score {best.score:.3f}, "
                    f"trust {best.trust:.2f}, size {size:.2f} CAD."
                ),
            ),
            ranked,
        )
