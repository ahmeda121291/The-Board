"""Transaction-cost model.

At a $200 account, cost is existential: a 0.5% edge means nothing if the round
trip costs 0.6%. So expected cost is computed *before* the CEO decides and used
as a gate — not merely reported after the fact (scope §8).

All numbers here are deterministic functions of venue + notional. They are
unit-tested and intentionally pessimistic; underestimating cost is how a small
account bleeds out.
"""

from __future__ import annotations

from dataclasses import dataclass

from boardroom.schemas import Venue


@dataclass(frozen=True)
class CostModel:
    """Round-trip cost assumptions per venue. Fractions of notional."""

    # Kraken taker fee ~0.26% per side; staking/yield is near-zero entry cost.
    kraken_fee_per_side: float = 0.0026
    # IBKR equities are cheap per-share but min-ticket dominates at $200; model
    # a conservative per-side fraction plus near-spot FX.
    ibkr_fee_per_side: float = 0.0010
    ibkr_fx_per_conversion: float = 0.0002  # near-spot; IBKR's real advantage
    # SnapTrade->Wealthsimple: ~$0 commission on stocks/ETFs, but a punishing
    # ~1.5% FX on USD conversions. Modeling that honestly makes the cost gate
    # correctly steer the Directional leg toward CAD-listed ETFs.
    snaptrade_fee_per_side: float = 0.0000
    snaptrade_fx_per_conversion: float = 0.015
    # Slippage we assume we eat on each side for a small marketable order.
    slippage_per_side: float = 0.0010

    def round_trip_cost_cad(
        self, *, venue: Venue, notional_cad: float, needs_fx: bool
    ) -> float:
        """Expected CAD cost to enter AND exit a ``notional_cad`` position."""
        notional = abs(notional_cad)
        if venue == Venue.KRAKEN:
            fee = self.kraken_fee_per_side * 2
            fx = 0.0
        elif venue == Venue.IBKR:
            fee = self.ibkr_fee_per_side * 2
            # FX charged once each way only if the trade crosses CAD<->USD.
            fx = (self.ibkr_fx_per_conversion * 2) if needs_fx else 0.0
        elif venue == Venue.SNAPTRADE:
            fee = self.snaptrade_fee_per_side * 2
            fx = (self.snaptrade_fx_per_conversion * 2) if needs_fx else 0.0
        else:
            fee = 0.0
            fx = 0.0
        slip = self.slippage_per_side * 2
        return notional * (fee + fx + slip)
