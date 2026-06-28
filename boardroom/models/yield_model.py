"""Yield model — the floor / hurdle rate.

Yield is not a price bet; it is cash flow. The model reports the current carry
(staking/lending APR on Kraken, or short-duration held cash on the IBKR side)
converted to the decision horizon. This sets the hurdle every other division
must beat, risk-adjusted, net of cost (scope §4). Near-certain, low variance.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from boardroom.data.snapshot import Bars
from boardroom.models.base import ModelOutput, PredictionModel


@dataclass
class YieldModel(PredictionModel):
    name: str = "yield"
    version: str = "v0-carry"
    horizon_days: float = 1.0
    #: Annualized carry. Seeded from FLOOR_CARRY_APR and refreshed at runtime by
    #: the live Kraken staking APR when the venue is wired (Milestone 6).
    carry_apr: float = 0.04
    #: Optional live APR source (e.g. the Kraken broker). Called by
    #: :meth:`resolve_carry`; any failure leaves ``carry_apr`` untouched.
    apr_provider: Callable[[], float] | None = None
    #: Sanity band for an externally-sourced APR. A value outside this band (or
    #: non-finite) is rejected, not trusted — the hurdle is load-bearing, so a
    #: garbage feed must never widen or collapse it.
    apr_min: float = 0.0
    apr_max: float = 0.25

    def resolve_carry(self) -> float:
        """Refresh ``carry_apr`` from the live provider, if one is set.

        The provider's value is accepted only if it is finite and within
        ``[apr_min, apr_max]`` (clamped to the band). On a missing provider or
        ANY failure/garbage the configured carry stands — the floor is never
        moved by a feed we can't validate. Returns the effective carry.
        """
        if self.apr_provider is None:
            return self.carry_apr
        try:
            value = float(self.apr_provider())
        except Exception:
            return self.carry_apr  # offline / auth / parse failure -> keep config
        if not math.isfinite(value):
            return self.carry_apr
        self.carry_apr = min(self.apr_max, max(self.apr_min, value))
        return self.carry_apr

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
