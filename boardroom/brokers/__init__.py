"""Venue execution, hidden behind one interface so the rest of the system is
venue-agnostic (scope §12). Kraken and IBKR are isolated accounts with separate
credentials — a leak in one can never touch the other (scope §7 "Blast radius").
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
    """Which venue executes the Directional leg, given the configured creds.

    SnapTrade (Wealthsimple etc.) wins if configured; else IBKR; else IBKR-stub.
    """
    from boardroom.config import get_settings
    from boardroom.schemas import Venue

    s = settings or get_settings()
    if s.snaptrade_client_id and s.snaptrade_account_id:
        return Venue.SNAPTRADE
    return Venue.IBKR


def make_brokers(*, prefer_live: bool = False) -> dict:
    """Return the venue->broker map.

    With ``prefer_live`` and credentials present, returns the real Kraken plus
    the chosen Directional adapter (SnapTrade or IBKR); otherwise stubs. Real
    brokers still only place LIVE orders when the global LIVE_TRADING flag is set
    — ``prefer_live`` only selects the adapter, it never bypasses the master switch.
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

    # Directional leg — SnapTrade preferred, then IBKR, else stub.
    dv = directional_execution_venue(s)
    if prefer_live and dv == Venue.SNAPTRADE:
        from boardroom.brokers.snaptrade import SnapTradeBroker

        brokers[Venue.SNAPTRADE] = SnapTradeBroker()
    elif prefer_live and s.ibkr_account_id:
        from boardroom.brokers.ibkr import IBKRBroker

        brokers[Venue.IBKR] = IBKRBroker()
    else:
        brokers[dv] = StubBroker(dv)
    return brokers
