"""Directional model — a small, inspectable logistic over technical features.

It blends momentum (trend-following) and a mean-reversion z-score, scaled by
realized volatility. The default coefficients are a documented prior; the
backtest (``boardroom.backtest``) can re-fit them on historical outcomes with
``fit()``. Magnitude of expected_return is tied to realized volatility, so the
model never claims a move larger than the asset's own variability supports.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from boardroom.data.snapshot import Bars
from boardroom.features import momentum, rsi, volatility, zscore_meanrev
from boardroom.models.base import ModelOutput, PredictionModel


@dataclass
class DirectionalModel(PredictionModel):
    name: str = "directional"
    version: str = "v0-heuristic"
    horizon_days: float = 5.0
    lookback: int = 20
    # logit = intercept + w·features (features are standardized-ish technicals)
    intercept: float = 0.0
    w_momentum: float = 6.0      # trend-following: positive momentum -> up
    w_meanrev: float = -0.15     # stretched above mean -> slight pull down
    w_rsi: float = -0.01         # overbought (>50) -> mild fade
    coefficients_source: str = "prior"  # becomes "backtest_fit" after fit()
    feature_names: tuple[str, ...] = field(
        default=("momentum", "meanrev_z", "rsi_centered"), repr=False
    )

    def _features(self, bars: Bars) -> dict[str, float]:
        c = bars.closes
        return {
            "momentum": momentum(c, self.lookback),
            "meanrev_z": zscore_meanrev(c, self.lookback),
            "rsi_centered": rsi(c, 14) - 50.0,
            "volatility": volatility(c, self.lookback),
        }

    def predict(self, bars: Bars) -> ModelOutput:
        f = self._features(bars)
        logit = (
            self.intercept
            + self.w_momentum * f["momentum"]
            + self.w_meanrev * f["meanrev_z"]
            + self.w_rsi * f["rsi_centered"]
        )
        p_up = 1.0 / (1.0 + math.exp(-_clip(logit, -8, 8)))

        # Expected per-bar move, scaled to the horizon, capped by realized vol so
        # the magnitude is grounded in the asset's own variability.
        per_bar_vol = f["volatility"]
        horizon_move = per_bar_vol * math.sqrt(self.horizon_days)
        expected_return = (2.0 * p_up - 1.0) * horizon_move

        # Confidence is distance from a coin flip, not the raw probability.
        raw_conf = abs(2.0 * p_up - 1.0)

        return ModelOutput(
            expected_return=expected_return,
            win_probability=max(p_up, 1.0 - p_up),  # prob of the side we'd take
            raw_confidence=raw_conf,
            horizon_days=self.horizon_days,
            features=f,
            model_name=self.name,
            model_version=self.version,
        )

    def fit(self, feature_rows: list[dict[str, float]], wins: list[bool]) -> "DirectionalModel":
        """Re-fit coefficients on historical outcomes with a small logistic.

        Pure scikit-learn; deterministic given the data. Returns self with
        coefficients replaced and ``coefficients_source`` flipped to
        ``backtest_fit`` so provenance is explicit.
        """
        from sklearn.linear_model import LogisticRegression

        cols = ("momentum", "meanrev_z", "rsi_centered")
        X = np.array([[row[c] for c in cols] for row in feature_rows], dtype=float)
        y = np.array([1 if w else 0 for w in wins], dtype=int)
        if len(set(y.tolist())) < 2:
            # Degenerate target — keep the prior rather than fit to noise.
            return self
        clf = LogisticRegression(max_iter=1000)
        clf.fit(X, y)
        self.intercept = float(clf.intercept_[0])
        self.w_momentum, self.w_meanrev, self.w_rsi = (float(c) for c in clf.coef_[0])
        self.coefficients_source = "backtest_fit"
        self.version = "v1-fit"
        return self


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))
