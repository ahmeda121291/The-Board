"""Momentum division — the catalyst-continuation strategy (rides breakouts).

Unlike Directional/Event (which fade strength), this BUYS volume-confirmed upside
breakouts — the structural fix for missing catalyst-driven moves (e.g. a stock
ripping on news). It is asset-agnostic: it scans both equities and crypto and
routes each pitch to the right venue off the data source.

Ships ``advisory=True`` — it pitches and logs but is never funded with real
capital — so its breakout calls can be validated on live data before it earns a
real leash.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from boardroom.data.snapshot import Bars
from boardroom.divisions.base import Division
from boardroom.models.momentum import MomentumModel
from boardroom.schemas import Division as DivisionEnum, Venue


@dataclass
class MomentumDivision(Division):
    division: DivisionEnum = DivisionEnum.MOMENTUM
    venue: Venue = Venue.SNAPTRADE  # default; venue_for routes per symbol
    model: MomentumModel = field(default_factory=MomentumModel)
    min_stop_fraction: float = 0.02
    stop_vol_multiple: float = 2.5
    advisory: bool = True  # validate on live data before it can trade real money
    #: Execution venue for crypto symbols; equities route to ``equity_venue``.
    equity_venue: Venue = Venue.SNAPTRADE

    def needs_fx(self) -> bool:
        return False  # resolved per-pitch; FX handled by the equity venue if needed

    def venue_for(self, bars: Bars) -> Venue:
        # Kraken-sourced bars are crypto; everything else is the equity venue.
        return Venue.KRAKEN if bars.venue == Venue.KRAKEN else self.equity_venue
