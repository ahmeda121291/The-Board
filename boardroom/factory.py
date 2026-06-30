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


# The scanned equity universe. Equities are ADVISORY (recommendations, not
# auto-trades), so the universe is deliberately WIDE — the more liquid names we
# scan, the less likely a genuine breakout (the SNDK-up-4000% case) slips past
# us. Every symbol still runs the same grounded model + risk/cost gates; the
# recommendation engine ranks them into a target portfolio.
DIRECTIONAL_UNIVERSE = (
    "SPY", "QQQ", "IWM", "DIA",          # broad-market ETFs
    "XLK", "XLF", "XLE", "XLV",          # sector ETFs (rotation candidates)
    "AAPL", "MSFT", "NVDA", "AMZN",      # liquid mega-caps
    "GOOGL", "META", "LLY", "AVGO",      # incl. high-catalyst megacaps (LLY = the Trump-news case)
    "COST", "UNH", "V",
)
# Crypto pairs are CAD-quoted to match the CAD-funded account — a CAD account
# can only BUY CAD pairs, so data, signals, and execution all use *CAD. (An
# unknown CAD pair simply fails its data fetch and is skipped, never fatal.)
EVENT_UNIVERSE = (
    "XBTCAD", "ETHCAD", "SOLCAD", "XRPCAD", "ADACAD", "LINKCAD", "DOTCAD",
)

# "Wide scan" — the broad equity universe used for the daily recommendation
# (now the DEFAULT). A large, liquid, sector-diverse set spanning megacaps,
# high-momentum semis/AI names, growth, and the major ETFs — chosen so a runaway
# winner can't hide. Still liquid-only (no penny/illiquid names); equities are
# advisory so a wide list is safe — it just produces better recommendations.
DIRECTIONAL_UNIVERSE_WIDE = DIRECTIONAL_UNIVERSE + (
    # more ETFs (sectors, factors, themes)
    "SMH", "XLY", "XLP", "XLI", "XLU", "XLC", "XLRE", "XLB",
    "GLD", "SLV", "TLT", "EEM", "ARKK", "IBB", "XBI", "SOXX", "VGT", "IGV",
    # megacap / large-cap leaders
    "TSLA", "AMD", "NFLX", "CRM", "JPM", "BAC", "WMT", "XOM", "CVX", "MA", "HD",
    "ORCL", "ADBE", "INTC", "QCOM", "TXN", "MU", "PYPL", "DIS", "PEP", "KO",
    "PFE", "MRK", "ABBV", "TMO", "CAT", "GE", "BA", "UBER", "SHOP", "PANW",
    # high-momentum / catalyst growth names (the kind that run hard)
    "SNDK", "PLTR", "SMCI", "ARM", "COIN", "MSTR", "CRWD", "DDOG", "SNOW",
    "NOW", "ANET", "MRVL", "DELL", "WDC", "MARA", "RIOT", "HOOD", "RBLX",
)
# Wider crypto — additional CAD-quoted majors/large-caps with Kraken CAD markets.
# Anything without a real CAD pair just abstains at data-fetch, so the list is
# safe to keep generous.
EVENT_UNIVERSE_WIDE = EVENT_UNIVERSE + (
    "LTCCAD", "AVAXCAD", "DOGECAD", "ATOMCAD", "ALGOCAD", "MATICCAD",
    "BCHCAD", "XLMCAD", "ETCCAD", "FILCAD", "UNICAD", "AAVECAD",
    "GRTCAD", "SANDCAD", "MANACAD", "AXSCAD", "EOSCAD", "KAVACAD",
)


def _live_fetchers(wide: bool = False):
    from boardroom.data.sources import fetch_equity_daily, fetch_kraken_ohlc

    dsyms = DIRECTIONAL_UNIVERSE_WIDE if wide else DIRECTIONAL_UNIVERSE
    esyms = EVENT_UNIVERSE_WIDE if wide else EVENT_UNIVERSE
    directional = [partial(fetch_equity_daily, s) for s in dsyms]
    event = [partial(fetch_kraken_ohlc, p, 1440) for p in esyms]
    return directional, event, list(dsyms), list(esyms)


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
    wide: bool = True,  # equities are advisory → scan wide by default so winners aren't missed
    **orch_kwargs,
) -> Orchestrator:
    if data_mode == "live":
        directional_fetchers, event_fetchers, dir_syms, evt_syms = _live_fetchers(wide=wide)
    else:
        directional_fetchers, event_fetchers = _synthetic_fetchers()
        dir_syms, evt_syms = ["SPY", "QQQ"], ["XBTUSD", "ETHUSD"]

    from boardroom.brokers import StubBroker, directional_execution_venue, make_brokers
    from boardroom.config import get_settings
    from boardroom.models.yield_model import YieldModel

    settings = get_settings()

    # The Directional leg executes on IBKR (Client Portal Gateway). The division
    # is tagged with it so its pitches route to the matching broker.
    dv = directional_execution_venue()

    from boardroom.divisions.crypto_trend import CryptoTrendDivision
    from boardroom.divisions.momentum import MomentumDivision

    # Seed the floor from the configured carry (your real earned APR); the live
    # Kraken Earn provider is attached below when a real broker is present.
    yield_div = YieldDivision(model=YieldModel(carry_apr=settings.floor_carry_apr))
    directional = DirectionalDivision(
        fetchers=directional_fetchers, venue=dv, universe_symbols=dir_syms
    )
    event = EventDivision(
        fetchers=event_fetchers, enabled=enable_event, universe_symbols=evt_syms
    )
    # Momentum (catalyst-continuation) scans equities AND crypto and routes each
    # pitch to its venue. Advisory: it logs breakouts but never trades real money
    # until validated. This is the structural answer to missing catalyst moves.
    momentum = MomentumDivision(
        fetchers=list(directional_fetchers) + list(event_fetchers),
        equity_venue=dv,
        universe_symbols=dir_syms + evt_syms,
    )
    # Crypto Trend — the always-on crypto workhorse. Scans the same Kraken pairs
    # as Event but with the trend/mean-reversion model, so it proposes a long
    # whenever there's positive edge (not just on a rare dislocation). Executes on
    # Kraken → auto-funded under the venue rule. This is what makes the system
    # regularly take crypto positions instead of holding cash for a trigger.
    crypto_trend = CryptoTrendDivision(
        fetchers=list(event_fetchers), universe_symbols=evt_syms
    )
    effort = EffortDivision()  # disabled

    divisions = [directional, event, momentum, crypto_trend, effort]

    # Real adapters when requested + credentialed; stubs otherwise. Live
    # execution still requires the LIVE_TRADING master switch regardless.
    if "brokers" not in orch_kwargs:
        if prefer_live_brokers:
            orch_kwargs["brokers"] = make_brokers(prefer_live=True)
        else:
            orch_kwargs["brokers"] = {Venue.KRAKEN: StubBroker(Venue.KRAKEN), dv: StubBroker(dv)}

    # If a real Kraken broker is present, let the floor refresh its APR from the
    # live Earn endpoint (validated + clamped in resolve_carry; falls back to the
    # configured carry on any failure).
    kraken = orch_kwargs["brokers"].get(Venue.KRAKEN)
    if kraken is not None and type(kraken).__name__ == "KrakenBroker":
        yield_div.model.apr_provider = kraken.staking_apr

    return Orchestrator(divisions=divisions, yield_division=yield_div, **orch_kwargs)
