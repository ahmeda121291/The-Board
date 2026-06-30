"""Crypto Trend division — the always-on crypto workhorse.

Unlike Event (rare dislocation) and Momentum (confirmed breakout), it proposes a
long whenever the trend model sees positive edge, executes on Kraken, and is
fundable under the venue rule. Long-only: bearish reads are dropped by the gates.
"""

from __future__ import annotations

from boardroom.divisions.crypto_trend import CryptoTrendDivision
from boardroom.data.sources import synthetic_bars
from boardroom.schemas import Division as DivisionEnum, Venue


def test_pitches_a_kraken_long_on_an_uptrend():
    bars = synthetic_bars("XBTUSD", Venue.KRAKEN, n=160, seed=7, drift=0.004, vol=0.02)
    div = CryptoTrendDivision(fetch=lambda: bars)
    pitch = div.propose(bankroll_cad=200.0)
    assert pitch is not None
    assert pitch.division == DivisionEnum.CRYPTO_TREND
    assert pitch.venue == Venue.KRAKEN          # crypto → fundable under the venue rule
    assert pitch.expected_return > 0            # long-only: only positive-edge longs survive
    assert pitch.signals.features["price"] > 0  # reference price stamped for the dashboard


def test_is_fundable_in_the_loop_universe():
    # The default org wires a CryptoTrendDivision on the Kraken universe.
    from boardroom.factory import build_default_org

    org = build_default_org(data_mode="synthetic")
    kinds = {type(d).__name__ for d in org.divisions}
    assert "CryptoTrendDivision" in kinds
    ct = next(d for d in org.divisions if type(d).__name__ == "CryptoTrendDivision")
    assert ct.venue == Venue.KRAKEN
    assert ct.advisory is False  # auto-funded, not advisory
