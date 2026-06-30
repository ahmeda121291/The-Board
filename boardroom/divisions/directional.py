"""Directional division — the equities/ETF analyst. Liquid names via IBKR,
trend + mean-reversion, days-to-weeks holds. Most analyzable, fastest clean
feedback loop (scope §3).

ADVISORY by design: the system does NOT auto-trade equities. IBKR is treated as
a recommendation surface — Directional's pitches feed the recommended portfolio
the dashboard publishes (twice daily) and are NEVER funded with real capital.
Only crypto (the Event division on Kraken) auto-trades. See ``boardroom.recommend``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from boardroom.divisions.base import Division
from boardroom.models.directional import DirectionalModel
from boardroom.schemas import Division as DivisionEnum, Venue


@dataclass
class DirectionalDivision(Division):
    division: DivisionEnum = DivisionEnum.DIRECTIONAL
    venue: Venue = Venue.IBKR
    model: DirectionalModel = field(default_factory=DirectionalModel)
    #: Advisory: equities are recommendations only — never auto-funded. The
    #: recommendation engine ranks these pitches into a target portfolio the user
    #: executes by hand in IBKR.
    advisory: bool = True
    min_stop_fraction: float = 0.015
    stop_vol_multiple: float = 2.5
