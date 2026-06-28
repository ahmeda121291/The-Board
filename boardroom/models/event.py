"""Event model — a risk-defined sentinel, NOT a surge-spotter.

By the time an LLM can write a clean thesis about a "massive opportunity," it's
usually over (scope §3). So this division does not try to predict surges. It
fires ONLY when predefined quantitative triggers cross, takes tiny fixed size,
sets a hard stop, and assumes it is wrong most of the time. No trigger -> no
pitch (the model returns ``fired=False``).
"""

from __future__ import annotations

from dataclasses import dataclass

from boardroom.data.news import NewsProvider, catalyst_score, default_keywords
from boardroom.data.snapshot import Bars
from boardroom.features import drawdown, momentum, volatility, zscore_meanrev
from boardroom.models.base import ModelOutput, PredictionModel


@dataclass
class EventTriggerModel(PredictionModel):
    name: str = "event"
    version: str = "v0-sentinel"
    horizon_days: float = 3.0
    lookback: int = 14
    # Triggers: a sharp dislocation (deep z-score) AFTER a volatility expansion.
    z_trigger: float = 2.5           # |z| must exceed this
    vol_expansion_min: float = 0.04  # recent per-bar vol must exceed this
    # The sentinel's honest base rate: assumed wrong most of the time.
    assumed_win_prob: float = 0.30
    # Asymmetric payoff: small fixed stop, larger target (the lottery shape).
    target_multiple: float = 3.0
    # ---- optional news/catalyst confirmation gate ---------------------------
    #: When set, a fired price trigger ALSO requires a real catalyst (computed,
    #: not LLM-judged) within ``news_lookback_hours``. Unset -> price-only, exactly
    #: as before. A fetch failure is treated as "no opinion" (fires on price).
    news_provider: NewsProvider | None = None
    catalyst_threshold: float = 1.0
    news_lookback_hours: float = 48.0
    #: Asset aliases to match in headlines; derived from the symbol when empty.
    asset_keywords: tuple[str, ...] = ()

    def _catalyst(self, bars: Bars) -> float | None:
        """Catalyst score for this asset, or None when news can't be evaluated
        (no provider / fetch failed) — None means the gate stays neutral."""
        if self.news_provider is None:
            return None
        keywords = self.asset_keywords or default_keywords(bars.symbol)
        try:
            headlines = self.news_provider(bars.symbol)
            return catalyst_score(
                headlines,
                keywords=keywords,
                now=bars.last_time,
                lookback_hours=self.news_lookback_hours,
            )
        except Exception:
            return None  # news outage must never suppress a legitimate trigger

    def evaluate(self, bars: Bars) -> tuple[bool, dict[str, float]]:
        c = bars.closes
        f = {
            "meanrev_z": zscore_meanrev(c, self.lookback),
            "volatility": volatility(c, self.lookback),
            "momentum": momentum(c, self.lookback),
            "drawdown": drawdown(c),
        }
        price_fired = (
            abs(f["meanrev_z"]) >= self.z_trigger and f["volatility"] >= self.vol_expansion_min
        )

        catalyst = self._catalyst(bars)
        if catalyst is not None:
            f["catalyst_score"] = catalyst
        # Confirmation gate: when news was successfully evaluated, a fired trigger
        # must be corroborated by a catalyst at/above threshold. Neutral (None) ->
        # price decides alone, preserving the pre-news behavior.
        if price_fired and catalyst is not None and catalyst < self.catalyst_threshold:
            return False, f
        return price_fired, f

    def predict(self, bars: Bars) -> ModelOutput:
        fired, f = self.evaluate(bars)
        if not fired:
            # Sentinel silent: a non-fired model still returns output, but the
            # division checks ``raw_confidence == 0`` and abstains.
            return ModelOutput(
                expected_return=0.0,
                win_probability=0.0,
                raw_confidence=0.0,
                horizon_days=self.horizon_days,
                features=f,
                model_name=self.name,
                model_version=self.version,
            )

        # Asymmetric expected value: p*target - (1-p)*stop, in fractional terms.
        # Stop is one unit of recent vol; target is target_multiple units.
        stop = f["volatility"]
        target = self.target_multiple * stop
        p = self.assumed_win_prob
        expected_return = p * target - (1.0 - p) * stop
        # Direction: fade the dislocation (z>0 stretched up -> short bias; here we
        # express magnitude only, the division sets side from the z sign).
        return ModelOutput(
            expected_return=expected_return,
            win_probability=p,
            raw_confidence=0.5,  # deliberately modest — never high-conviction
            horizon_days=self.horizon_days,
            features=f,
            model_name=self.name,
            model_version=self.version,
        )
