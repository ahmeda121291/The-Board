"""Event division — the risk-defined sentinel (the lottery ticket).

Tiny FIXED sizing, hard stops, fires only when quantitative triggers cross, and
assumes it is wrong most of the time. The CEO can NEVER override its hard cap
(enforced in ``RiskCaps.cap_for('event')``). Its base size is intentionally a
flat tiny fraction, not confidence-scaled — this division does not get to size up.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from boardroom.divisions.base import Division
from boardroom.models.base import ModelOutput
from boardroom.models.event import EventTriggerModel
from boardroom.schemas import Division as DivisionEnum, Venue


@dataclass
class EventDivision(Division):
    division: DivisionEnum = DivisionEnum.EVENT
    venue: Venue = Venue.KRAKEN
    model: EventTriggerModel = field(default_factory=EventTriggerModel)
    min_stop_fraction: float = 0.05   # hard stop, always present
    stop_vol_multiple: float = 1.0
    #: Flat tiny stake as a fraction of bankroll — the lottery never scales up.
    fixed_stake_fraction: float = 0.03

    def base_size_cad(self, output: ModelOutput, bankroll_cad: float) -> float:
        # Fixed tiny size regardless of model confidence; the hard cap still binds
        # downstream in the CEO/caps layer.
        return round(self.fixed_stake_fraction * bankroll_cad, 2)
