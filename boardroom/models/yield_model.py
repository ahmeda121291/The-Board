"""Yield model — the floor / hurdle rate.

Yield is not a price bet; it is cash flow. The model reports the current carry
(staking/lending APR on Kraken, or short-duration held cash on the IBKR side)
converted to the decision horizon. This sets the hurdle every other division
must beat, risk-adjusted, net of cost (scope §4). Near-certain, low variance.
"""

from __future__ import annotations

from dataclasses import dataclass

from boardroom.data.snapshot import Bars
from boardroom.models.base import ModelOutput, PredictionModel


@dataclass
class YieldModel(PredictionModel):
    name: str = "yield"
    version: str = "v0-carry"
    horizon_days: float = 1.0
    #: Annualized carry. Replaced at runtime by the live Kraken staking APR when
    #: the venue is wired (Milestone 6). Conservative default.
    carry_apr: float = 0.04

    def carry_over(self, days: float) -> float:
        return self.carry_apr * (days / 365.0)

    def predict(self, bars: Bars | None = None) -> ModelOutput:  # bars unused: carry isn't price
        expected = self.carry_over(self.horizon_days)
        return ModelOutput(
            expected_return=expected,
            win_probability=0.99,   # carry is near-certain over a day
            raw_confidence=0.99,
            horizon_days=self.horizon_days,
            features={"carry_apr": self.carry_apr},
            model_name=self.name,
            model_version=self.version,
        )
