"""Division base — the pitch-or-abstain machinery shared by all divisions.

The flow is the grounding rule made concrete (scope §5):
    fetch real data -> snapshot (freshness/sanity) -> model.predict ->
    deterministic sizing/risk/cost -> Pitch with COMPUTED fields and EMPTY
    narrative. If data is stale/insane or the model has no edge -> return None.
"""

from __future__ import annotations

import abc
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from boardroom.data.snapshot import Bars, SanityError, build_snapshot
from boardroom.models.base import ModelOutput, PredictionModel
from boardroom.risk.cost import CostModel
from boardroom.schemas import ComputedSignals, Division as DivisionEnum, Pitch, Venue


@dataclass
class Division(abc.ABC):
    """Abstract division. Subclasses set the enum, venue, model, and stop logic."""

    division: DivisionEnum
    venue: Venue
    model: PredictionModel
    fetch: Callable[[], Bars] | None = None  # real data source; None -> needs injected bars
    enabled: bool = True
    max_age_seconds: float = 60 * 60 * 36  # daily bars: ~1.5 days tolerance
    min_rows: int = 40
    min_stop_fraction: float = 0.01
    stop_vol_multiple: float = 2.0
    cost_model: CostModel = field(default_factory=CostModel)
    #: Human-readable outcome of the last propose() — for the boardroom session
    #: feed (why a division abstained or what it pitched).
    last_status: str = "idle"

    # ---- subclass hooks ------------------------------------------------------
    def needs_fx(self) -> bool:
        """True if the trade crosses CAD<->USD (IBKR USD names, USD crypto pairs)."""
        return self.venue == Venue.IBKR

    def stop_fraction(self, output: ModelOutput) -> float:
        """Fractional loss if the stop is hit — grounds max_loss in real volatility."""
        vol = output.features.get("volatility", 0.0)
        return max(self.min_stop_fraction, vol * self.stop_vol_multiple)

    def base_size_cad(self, output: ModelOutput, bankroll_cad: float) -> float:
        """The division's own sizing request (CEO re-sizes authoritatively).

        A timid fraction of bankroll scaled by confidence — the division proposes,
        the CEO disposes.
        """
        conf = output.raw_confidence
        return round(max(0.0, conf) * 0.15 * bankroll_cad, 2)

    # ---- the public entry point ---------------------------------------------
    def propose(
        self, *, bars: Bars | None = None, bankroll_cad: float = 200.0
    ) -> Pitch | None:
        """Produce a computed Pitch, or None to abstain (recording why)."""
        if not self.enabled:
            self.last_status = "disabled"
            return None

        try:
            bars = bars if bars is not None else (self.fetch() if self.fetch else None)
        except Exception:
            self.last_status = "abstained — data feed unavailable"
            return None  # any data failure -> abstain (no trade on garbage)
        if bars is None:
            self.last_status = "abstained — no data"
            return None

        try:
            snapshot = build_snapshot(
                bars, max_age_seconds=self.max_age_seconds, min_rows=self.min_rows
            )
        except SanityError as e:
            self.last_status = f"abstained — data failed sanity checks ({e})"
            return None
        if not snapshot.is_fresh:
            self.last_status = f"abstained — stale data ({snapshot.age_seconds / 3600:.0f}h old)"
            return None  # stale data -> abstain

        output = self.model.predict(bars)
        if output.raw_confidence <= 0.0:
            self.last_status = "abstained — no edge / trigger not fired"
            return None  # no edge / sentinel not fired -> abstain

        capital = self.base_size_cad(output, bankroll_cad)
        if capital <= 0.0:
            self.last_status = "abstained — computed size rounds to zero"
            return None

        stop_frac = self.stop_fraction(output)
        cost = self.cost_model.round_trip_cost_cad(
            venue=self.venue, notional_cad=capital, needs_fx=self.needs_fx()
        )
        max_loss = round(capital * stop_frac + cost, 2)

        signals = ComputedSignals(
            features=output.features,
            model_name=output.model_name,
            model_version=output.model_version,
            expected_return=output.expected_return,
            win_probability=output.win_probability,
            raw_confidence=output.raw_confidence,
            horizon_days=output.horizon_days,
        )

        self.last_status = "pitched"
        return Pitch(
            pitch_id=str(uuid.uuid4()),
            division=self.division,
            venue=self.venue,
            symbol=bars.symbol,
            snapshot=snapshot,
            signals=signals,
            capital_required=capital,
            expected_return=output.expected_return,
            confidence=output.win_probability,
            time_horizon_days=output.horizon_days,
            max_loss=max_loss,
            expected_cost=round(cost, 2),
            opportunity="",  # narrative filled by the LLM narrator, never here
            why_now="",
        )
