"""Explicit, inspectable prediction models: features -> (expected_return,
win_probability). Start simple (a backtested rule or a small logistic fit) and
keep them VERSIONED and reproducible. These produce the numbers — never the LLM.
"""

from boardroom.models.base import ModelOutput, PredictionModel
from boardroom.models.directional import DirectionalModel
from boardroom.models.event import EventTriggerModel
from boardroom.models.yield_model import YieldModel

__all__ = [
    "ModelOutput",
    "PredictionModel",
    "DirectionalModel",
    "EventTriggerModel",
    "YieldModel",
]
