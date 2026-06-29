"""Venue execution, hidden behind one interface so the rest of the system is
venue-agnostic (scope §12). Kraken (crypto) and IBKR (equities) are isolated
accounts with separate credentials — a leak in one can never touch the other
(scope §7 "Blast radius").
"""

from boardroom.brokers.base import Broker, Fill, Order, OrderSide
from boardroom.brokers.stub import StubBroker

__all__ = [
    "Broker",
    "Order",
    "Fill",
    "OrderSide",
    "StubBroker",
    "make_brokers",
    "directional_execution_venue",
]


def directional_execution_venue(settings=None):
    """Which venue executes the Directional leg. Equities run on IBKR."""
    from boardroom.schemas import Venue

    return Venue.IBKR


def make_brokers(*, prefer_live: bool = False) -> dict:
    """Return the venue->broker map.

    With ``prefer_live`` and credentials present, returns the real Kraken (crypto)
    plus the real IBKR (equities) adapter; otherwise stubs. Real brokers still only
    place LIVE orders when the global LIVE_TRADING flag is set — ``prefer_live``
    only selects the adapter, it never bypasses the master switch.
    """
    from boardroom.config import get_settings
    from boardroom.schemas import Venue

    s = get_settings()
    brokers: dict = {}

    # Crypto leg (Yield + Event).
    if prefer_live and s.kraken_api_key and s.kraken_api_secret:
        from boardroom.brokers.kraken import KrakenBroker

        brokers[Venue.KRAKEN] = KrakenBroker()
    else:
        brokers[Venue.KRAKEN] = StubBroker(Venue.KRAKEN)

    # Directional leg — IBKR (Client Portal Gateway), else stub.
    if prefer_live and s.ibkr_account_id:
        from boardroom.brokers.ibkr import IBKRBroker

        brokers[Venue.IBKR] = IBKRBroker()
    else:
        brokers[Venue.IBKR] = StubBroker(Venue.IBKR)
    return brokers
