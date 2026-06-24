"""Venue execution, hidden behind one interface so the rest of the system is
venue-agnostic (scope §12). Kraken and IBKR are isolated accounts with separate
credentials — a leak in one can never touch the other (scope §7 "Blast radius").
"""

from boardroom.brokers.base import Broker, Fill, Order, OrderSide
from boardroom.brokers.stub import StubBroker

__all__ = ["Broker", "Order", "Fill", "OrderSide", "StubBroker"]
