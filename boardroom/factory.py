"""Assemble the default Boardroom organization.

Wires the four divisions to their data sources and models and returns a ready
``Orchestrator``. ``data_mode='live'`` uses real keyless public feeds (Kraken
public OHLC + Stooq daily); ``'synthetic'`` uses deterministic local bars so the
loop runs fully offline (tests, demos, no network).
"""

from __future__ import annotations

from functools import partial

from boardroom.divisions.directional import DirectionalDivision
from boardroom.divisions.effort import EffortDivision
from boardroom.divisions.event import EventDivision
from boardroom.divisions.yield_div import YieldDivision
from boardroom.graph.decision_loop import Orchestrator
from boardroom.schemas import Venue


# The scanned universe. More liquid names = more chances something is a genuine
# positive-edge, non-stretched buy that clears the floor after cost. Every symbol
# still runs the same grounded model + risk/cost gates; the CEO funds the best one.
DIRECTIONAL_UNIVERSE = (
    "SPY", "QQQ", "IWM", "DIA",          # broad-market ETFs
    "XLK", "XLF", "XLE", "XLV",          # sector ETFs (rotation candidates)
    "AAPL", "MSFT", "NVDA", "AMZN",      # liquid mega-caps
    "GOOGL", "META",
)
EVENT_UNIVERSE = (
    "XBTUSD", "ETHUSD", "SOLUSD", "XRPUSD", "ADAUSD", "LINKUSD", "DOTUSD",
)


def _live_fetchers():
    from boardroom.data.sources import fetch_equity_daily, fetch_kraken_ohlc

    directional = [partial(fetch_equity_daily, s) for s in DIRECTIONAL_UNIVERSE]
    event = [partial(fetch_kraken_ohlc, p, 1440) for p in EVENT_UNIVERSE]
    return directional, event


def _synthetic_fetchers():
    from boardroom.data.sources import synthetic_bars

    # A small varied basket so offline/test runs still exercise multi-symbol ranking.
    directional = [
        partial(synthetic_bars, "SPY.US", Venue.IBKR, n=160, seed=11, drift=0.0008, vol=0.012),
        partial(synthetic_bars, "QQQ.US", Venue.IBKR, n=160, seed=12, drift=0.0011, vol=0.014),
    ]
    event = [
        partial(synthetic_bars, "XBTUSD", Venue.KRAKEN, n=160, seed=29, drift=0.0, vol=0.045),
        partial(synthetic_bars, "ETHUSD", Venue.KRAKEN, n=160, seed=31, drift=0.0005, vol=0.05),
    ]
    return directional, event


def build_default_org(
    *,
    data_mode: str = "live",
    enable_event: bool = True,
    prefer_live_brokers: bool = False,
    **orch_kwargs,
) -> Orchestrator:
    directional_fetchers, event_fetchers = (
        _live_fetchers() if data_mode == "live" else _synthetic_fetchers()
    )

    from boardroom.brokers import StubBroker, directional_execution_venue, make_brokers

    # The Directional leg's execution venue follows the configured credentials:
    # SnapTrade (Wealthsimple) if set, else IBKR. The division is tagged with it
    # so its pitches route to the matching broker.
    dv = directional_execution_venue()

    yield_div = YieldDivision()
    directional = DirectionalDivision(fetchers=directional_fetchers, venue=dv)
    event = EventDivision(fetchers=event_fetchers, enabled=enable_event)
    effort = EffortDivision()  # disabled

    divisions = [directional, event, effort]

    # Real adapters when requested + credentialed; stubs otherwise. Live
    # execution still requires the LIVE_TRADING master switch regardless.
    if "brokers" not in orch_kwargs:
        if prefer_live_brokers:
            orch_kwargs["brokers"] = make_brokers(prefer_live=True)
        else:
            orch_kwargs["brokers"] = {Venue.KRAKEN: StubBroker(Venue.KRAKEN), dv: StubBroker(dv)}

    return Orchestrator(divisions=divisions, yield_division=yield_div, **orch_kwargs)
