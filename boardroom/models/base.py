"""Base contract for prediction models."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field

from boardroom.data.snapshot import Bars


@dataclass
class ModelOutput:
    """Everything a model produces — all of it logged for reconstructability."""

    expected_return: float        # fractional, over the horizon
    win_probability: float        # [0, 1]
    raw_confidence: float         # model's own confidence pre-trust-adjustment
    horizon_days: float
    features: dict[str, float] = field(default_factory=dict)
    model_name: str = "base"
    model_version: str = "v0"

    def __post_init__(self) -> None:
        self.win_probability = min(1.0, max(0.0, self.win_probability))
        self.raw_confidence = min(1.0, max(0.0, self.raw_confidence))


class PredictionModel(abc.ABC):
    """Maps real features to numbers. Deterministic; the only source of quant fields."""

    name: str = "base"
    version: str = "v0"

    @abc.abstractmethod
    def predict(self, bars: Bars) -> ModelOutput:
        """Compute features from ``bars`` and return a :class:`ModelOutput`."""

    @property
    def fullname(self) -> str:
        return f"{self.name}:{self.version}"
