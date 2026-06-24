"""Effort division — the non-market bet (affiliate/content/digital arbitrage).

The only division whose returns don't depend on markets — pure diversification —
but the hardest to automate. Built as an INTERFACE and left DISABLED until the
core is proven (scope §3, Milestone 10). ``propose`` always abstains while
disabled.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from boardroom.models.base import ModelOutput, PredictionModel
from boardroom.data.snapshot import Bars
from boardroom.divisions.base import Division
from boardroom.schemas import Division as DivisionEnum, Pitch, Venue


class _NullModel(PredictionModel):
    name = "effort"
    version = "disabled"

    def predict(self, bars: Bars) -> ModelOutput:  # pragma: no cover - never called
        return ModelOutput(0.0, 0.0, 0.0, 0.0, {}, self.name, self.version)


@dataclass
class EffortDivision(Division):
    division: DivisionEnum = DivisionEnum.EFFORT
    venue: Venue = Venue.NONE
    model: PredictionModel = field(default_factory=_NullModel)
    enabled: bool = False  # disabled at launch — the interface exists, the bet doesn't

    def propose(self, *, bars=None, bankroll_cad: float = 200.0) -> Pitch | None:
        self.last_status = "disabled (Phase 3 — not yet activated)"
        return None
