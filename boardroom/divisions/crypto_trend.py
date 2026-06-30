"""Crypto Trend division — the always-on crypto workhorse.

Where Event waits for a rare dislocation and Momentum waits for a confirmed
breakout, this division proposes a position **whenever the trend/mean-reversion
model sees a positive-edge long** on a Kraken pair — so the system is regularly
in the market rather than holding cash until a rare trigger fires. It reuses the
grounded ``DirectionalModel`` (trend + mean-reversion, magnitude tied to realized
volatility) on the crypto universe and executes on Kraken, so its pitches are
auto-funded under the venue rule.

Still fully gated: long-only (bearish reads produce negative expected return →
dropped by the floor/cost gate), every quant field is computed, and the CEO's
cost gate, per-trade/Event caps, daily-loss and drawdown breakers all apply.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from boardroom.divisions.base import Division
from boardroom.models.directional import DirectionalModel
from boardroom.schemas import Division as DivisionEnum, Venue


@dataclass
class CryptoTrendDivision(Division):
    division: DivisionEnum = DivisionEnum.CRYPTO_TREND
    venue: Venue = Venue.KRAKEN
    model: DirectionalModel = field(default_factory=DirectionalModel)
    # Crypto is more volatile than equities; a slightly wider stop keeps the
    # max-loss grounded in realized vol without being trivially tight.
    min_stop_fraction: float = 0.02
    stop_vol_multiple: float = 2.5
