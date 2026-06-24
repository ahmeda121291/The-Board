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


def _live_fetchers():
    from boardroom.data.sources import fetch_kraken_ohlc, fetch_stooq_daily

    return (
        partial(fetch_stooq_daily, "spy.us"),
        partial(fetch_kraken_ohlc, "XBTUSD", 1440),
    )


def _synthetic_fetchers():
    from boardroom.data.sources import synthetic_bars

    return (
        partial(synthetic_bars, "SPY.US", Venue.IBKR, n=160, seed=11, drift=0.0008, vol=0.012),
        partial(synthetic_bars, "XBTUSD", Venue.KRAKEN, n=160, seed=29, drift=0.0, vol=0.045),
    )


def build_default_org(
    *,
    data_mode: str = "live",
    enable_event: bool = True,
    prefer_live_brokers: bool = False,
    **orch_kwargs,
) -> Orchestrator:
    directional_fetch, event_fetch = (
        _live_fetchers() if data_mode == "live" else _synthetic_fetchers()
    )

    from boardroom.brokers import StubBroker, directional_execution_venue, make_brokers

    # The Directional leg's execution venue follows the configured credentials:
    # SnapTrade (Wealthsimple) if set, else IBKR. The division is tagged with it
    # so its pitches route to the matching broker.
    dv = directional_execution_venue()

    yield_div = YieldDivision()
    directional = DirectionalDivision(fetch=directional_fetch, venue=dv)
    event = EventDivision(fetch=event_fetch, enabled=enable_event)
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
