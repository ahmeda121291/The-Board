"""The four divisions — orthogonal opportunity hunters. Each pulls real data,
computes features and model outputs, and pitches in the standard schema, or
ABSTAINS (stale data, or no edge today). Quantitative fields are computed; the
narrative is added later by the LLM narrator.
"""

from boardroom.divisions.base import Division as DivisionBase
from boardroom.divisions.directional import DirectionalDivision
from boardroom.divisions.effort import EffortDivision
from boardroom.divisions.event import EventDivision
from boardroom.divisions.yield_div import YieldDivision

__all__ = [
    "DivisionBase",
    "YieldDivision",
    "DirectionalDivision",
    "EventDivision",
    "EffortDivision",
]
