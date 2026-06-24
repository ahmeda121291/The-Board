"""A deterministic in-memory broker for dry-run and tests.

This is what runs until ``LIVE_TRADING`` is flipped and the real Kraken/IBKR
brokers are wired (Milestone 6). It simulates fills at the requested price with a
modeled fee/FX cost so the whole loop — sizing, cost gate, measurement — exercises
end to end without real money.
"""

from __future__ import annotations

from datetime import datetime, timezone

from boardroom.brokers.base import Broker, Fill, Order
from boardroom.schemas import Venue


class StubBroker(Broker):
    supports_withdrawal = False

    def __init__(self, venue: Venue = Venue.NONE, cash_cad: float = 200.0) -> None:
        self.venue = venue
        self._cash_cad = cash_cad
        self.placed: list[Order] = []

    def health_check(self) -> bool:
        return True

    def get_cash_cad(self) -> float:
        return self._cash_cad

    def place_order(self, order: Order, *, live: bool) -> Fill:
        # In dry-run the stub never executes "live", regardless of the flag.
        self.placed.append(order)
        price = order.limit_price if order.limit_price is not None else 1.0
        qty = order.notional_cad / price if price else 0.0
        # Modeled costs: 0.26% taker-style fee + a hair of FX. Pessimistic on purpose.
        fee = abs(order.notional_cad) * 0.0026
        fx = abs(order.notional_cad) * 0.0002 if order.symbol.upper().endswith("USD") else 0.0
        return Fill(
            client_order_id=order.client_order_id,
            venue=self.venue,
            symbol=order.symbol,
            side=order.side,
            filled_qty=qty,
            avg_price=price,
            fee_cad=fee,
            fx_cost_cad=fx,
            filled_at=datetime.now(timezone.utc),
            is_live=False,
            raw={"stub": True},
        )
