"""The single broker interface every venue implements.

Keeping the rest of the system venue-agnostic means Kraken (crypto/yield/event)
and IBKR (equities) are interchangeable from the CEO's point of view. A broker
can *trade* but, by construction of how we scope credentials, can never
*withdraw*. ``supports_withdrawal`` exists only so we can assert it is False.
"""

from __future__ import annotations

import abc
import enum
from dataclasses import dataclass
from datetime import datetime

from boardroom.schemas import Venue


class OrderSide(str, enum.Enum):
    BUY = "buy"
    SELL = "sell"


@dataclass(frozen=True)
class Order:
    symbol: str
    side: OrderSide
    notional_cad: float          # we size in CAD; the broker converts to qty
    division: str
    client_order_id: str
    limit_price: float | None = None  # None == market
    stop_price: float | None = None   # hard stop (mandatory for Event)
    #: Exact base-asset quantity to trade. Used to CLOSE a position (sell exactly
    #: what's held) rather than sizing from a CAD notional. When set, it overrides
    #: ``notional_cad`` for the order volume.
    base_qty: float | None = None


@dataclass(frozen=True)
class Fill:
    client_order_id: str
    venue: Venue
    symbol: str
    side: OrderSide
    filled_qty: float
    avg_price: float
    fee_cad: float
    fx_cost_cad: float
    filled_at: datetime
    is_live: bool                # False == dry-run/stubbed, did not touch real money
    raw: dict | None = None


class Broker(abc.ABC):
    """Abstract venue. Implementations: StubBroker, KrakenBroker, IBKRBroker."""

    venue: Venue

    #: Must remain False everywhere. We never enable withdrawal scopes; this is
    #: asserted at startup so a misconfigured credential is caught loudly.
    supports_withdrawal: bool = False

    @abc.abstractmethod
    def health_check(self) -> bool:
        """True iff the venue session is authenticated and reachable."""

    @abc.abstractmethod
    def get_cash_cad(self) -> float:
        """Free CAD balance available to this venue's divisions."""

    def get_positions(self) -> list[dict]:
        """Open positions held at this venue.

        Returns a list of ``{symbol, qty, avg_cost, market_value_cad}`` dicts.
        Default is empty (stubs / venues we don't read holdings from); IBKR
        overrides this to read the real equity book for the recommendation diff.
        """
        return []

    @abc.abstractmethod
    def place_order(self, order: Order, *, live: bool) -> Fill:
        """Place ``order``. When ``live`` is False, simulate without touching funds.

        Implementations MUST refuse to place a live order if ``live`` is True but
        the global ``LIVE_TRADING`` flag is false — that check lives in the
        execution layer, but defense in depth is welcome here too.
        """

    def assert_no_withdrawal(self) -> None:
        if self.supports_withdrawal:
            raise RuntimeError(
                f"{self.venue} broker reports withdrawal capability — refusing to "
                "run. Re-scope the API credential to trade-only."
            )
