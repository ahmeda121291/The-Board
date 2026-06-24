"""Directional division — the workhorse. Liquid equities/ETFs via IBKR,
trend + mean-reversion, days-to-weeks holds. Most analyzable, fastest clean
feedback loop (scope §3).
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
    min_stop_fraction: float = 0.015
    stop_vol_multiple: float = 2.5
