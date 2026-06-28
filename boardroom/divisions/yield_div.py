"""Yield division — the floor and the benchmark.

The floor is the DEFAULT state, not a competing pitch, so ``propose`` returns
None: it never bids against itself. Its real job is to publish the hurdle rate
the CEO prices everything else against (scope §4).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from boardroom.divisions.base import Division
from boardroom.models.yield_model import YieldModel
from boardroom.schemas import Division as DivisionEnum, Pitch, Venue


@dataclass
class YieldDivision(Division):
    division: DivisionEnum = DivisionEnum.YIELD
    venue: Venue = Venue.KRAKEN
    model: YieldModel = field(default_factory=YieldModel)

    def refresh_floor(self) -> float:
        """Refresh the floor's carry from the live APR provider (best-effort).

        Delegates to the model, which only accepts a validated, in-band value and
        otherwise keeps the configured carry. Returns the effective APR.
        """
        return self.model.resolve_carry()

    def hurdle_for(self, horizon_days: float) -> float:
        """The floor's expected fractional return over ``horizon_days`` — the bar."""
        return self.model.carry_over(horizon_days)

    @property
    def carry_apr(self) -> float:
        return self.model.carry_apr

    def propose(self, *, bars=None, bankroll_cad: float = 200.0) -> Pitch | None:
        # The floor is the resting state; it does not pitch.
        self.last_status = f"floor — resting state · carry {self.carry_apr:.1%} APR"
        return None
