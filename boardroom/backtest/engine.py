"""A simple walk-forward backtester.

For each step it gives the model only the data available up to that point
(no lookahead), opens a position when the model has edge, holds for the horizon,
and books the realized return net of modeled cost. Aggregates into a hit rate
and net edge — the gate — and a calibration prior seed.
"""

from __future__ import annotations

from dataclasses import dataclass

from boardroom.adaptive.calibration import CalibrationPosterior, seed_prior
from boardroom.data.snapshot import Bars
from boardroom.models.base import PredictionModel
from boardroom.risk.cost import CostModel
from boardroom.schemas import Venue


@dataclass
class BacktestResult:
    n_trades: int
    hit_rate: float
    gross_return: float          # summed fractional returns
    net_return: float            # after modeled round-trip cost
    avg_edge_after_cost: float   # mean net fractional return per trade
    passes_gate: bool            # net edge after cost > 0 with a min sample
    prior: CalibrationPosterior

    def summary(self) -> str:
        verdict = "PASS" if self.passes_gate else "FAIL"
        return (
            f"[{verdict}] n={self.n_trades} hit_rate={self.hit_rate:.2%} "
            f"net_return={self.net_return:.2%} avg_edge_after_cost={self.avg_edge_after_cost:.4f} "
            f"prior=Beta({self.prior.alpha:.1f},{self.prior.beta:.1f})"
        )


def backtest_division(
    *,
    division: str,
    venue: Venue,
    model: PredictionModel,
    bars: Bars,
    warmup: int = 40,
    min_trades: int = 20,
    conf_threshold: float = 0.0,
    cost_model: CostModel | None = None,
    needs_fx: bool = False,
    notional_cad: float = 40.0,
) -> BacktestResult:
    cost_model = cost_model or CostModel()
    closes = bars.closes
    horizon = max(1, int(round(getattr(model, "horizon_days", 5.0))))

    wins = 0
    n = 0
    gross = 0.0
    net = 0.0
    for i in range(warmup, len(closes) - horizon):
        window = Bars(symbol=bars.symbol, venue=bars.venue, df=bars.df.iloc[: i + 1], source=bars.source)
        out = model.predict(window)
        if out.raw_confidence <= conf_threshold:
            continue
        entry = closes[i]
        exit_ = closes[i + horizon]
        realized = exit_ / entry - 1.0
        # Take the side the model leans: long if expected_return >= 0, else short.
        directional = realized if out.expected_return >= 0 else -realized
        cost_frac = cost_model.round_trip_cost_cad(
            venue=venue, notional_cad=notional_cad, needs_fx=needs_fx
        ) / notional_cad
        net_trade = directional - cost_frac
        gross += directional
        net += net_trade
        wins += 1 if net_trade > 0 else 0
        n += 1

    hit_rate = (wins / n) if n else 0.0
    avg_edge = (net / n) if n else 0.0
    passes = n >= min_trades and net > 0
    return BacktestResult(
        n_trades=n,
        hit_rate=hit_rate,
        gross_return=gross,
        net_return=net,
        avg_edge_after_cost=avg_edge,
        passes_gate=passes,
        prior=seed_prior(hit_rate if n else 0.5),
    )
