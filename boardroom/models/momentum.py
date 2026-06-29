"""Momentum / breakout model — the catalyst-continuation strategy.

This is the deliberate counterweight to the mean-reversion bias in the
Directional and Event models. Those FADE strength; this one RIDES it — but only
when a move is *confirmed by volume*, the fingerprint of a real catalyst (news,
a Trump comment, an upgrade) rather than noise.

It is long-only and fires ONLY on upside breakouts: a recent thrust of at least
``breakout_z`` volatility-units, on at least ``volume_min`` × normal volume. No
breakout → ``raw_confidence == 0`` → the division abstains. The expected return
is grounded in the asset's own realized volatility, never a free-form guess.

Why volume-gated: a price spike without volume is usually noise that mean-reverts;
a spike *on* heavy volume is participation — the kind of move that continues.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from boardroom.data.snapshot import Bars
from boardroom.features import breakout_strength, momentum, rsi, volatility, volume_surge
from boardroom.models.base import ModelOutput, PredictionModel


@dataclass
class MomentumModel(PredictionModel):
    name: str = "momentum"
    version: str = "v0-breakout"
    horizon_days: float = 5.0
    lookback: int = 20
    short: int = 5
    breakout_z: float = 1.5     # recent move must be >= this many vols, to the upside
    volume_min: float = 1.5     # AND on >= 1.5x normal volume (catalyst confirmation)
    base_win_prob: float = 0.55  # modest continuation edge; rises a touch with strength

    def predict(self, bars: Bars) -> ModelOutput:
        c = bars.closes
        v = bars.volumes
        bo = breakout_strength(c, self.lookback, self.short)
        vs = volume_surge(v, self.lookback)
        vol = volatility(c, self.lookback)
        f = {
            "breakout_z": bo,
            "volume_surge": vs,
            "volatility": vol,
            "momentum": momentum(c, self.lookback),
            "rsi_centered": rsi(c, 14) - 50.0,
        }

        fired = bo >= self.breakout_z and vs >= self.volume_min
        if not fired:
            return ModelOutput(
                expected_return=0.0,
                win_probability=0.0,
                raw_confidence=0.0,
                horizon_days=self.horizon_days,
                features=f,
                model_name=self.name,
                model_version=self.version,
            )

        # Confirmation strength scales win prob slightly above the base, capped so
        # the model never claims high conviction.
        strength = min(bo / self.breakout_z, 3.0) * min(vs / self.volume_min, 2.0)  # 1..6
        p_up = min(0.66, self.base_win_prob + 0.02 * (strength - 1.0))

        # Continuation expected return, magnitude bounded by the asset's own vol.
        horizon_move = vol * math.sqrt(self.horizon_days)
        expected_return = (2.0 * p_up - 1.0) * horizon_move  # POSITIVE for an up-breakout

        return ModelOutput(
            expected_return=expected_return,
            win_probability=p_up,
            raw_confidence=min(0.5, 0.15 * strength),  # modest, never overconfident
            horizon_days=self.horizon_days,
            features=f,
            model_name=self.name,
            model_version=self.version,
        )
