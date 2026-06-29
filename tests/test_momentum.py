"""Momentum/breakout model — rides volume-confirmed catalysts (the LLY fix)."""

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from boardroom.data.snapshot import Bars
from boardroom.divisions.momentum import MomentumDivision
from boardroom.models.momentum import MomentumModel
from boardroom.schemas import Venue


def _bars(closes, volumes, venue=Venue.IBKR, symbol="TST"):
    n = len(closes)
    end = datetime(2026, 6, 26, tzinfo=timezone.utc)
    times = [end - timedelta(days=(n - 1 - i)) for i in range(n)]
    c = np.array(closes, dtype=float)
    df = pd.DataFrame({
        "time": pd.to_datetime(times, utc=True),
        "open": c, "high": c * 1.001, "low": c * 0.999, "close": c,
        "volume": np.array(volumes, dtype=float),
    })
    return Bars(symbol=symbol, venue=venue, df=df, source="test")


def test_breakout_on_volume_fires_positive():
    # 50 calm days ~100, then a sharp +8% thrust on 4x volume = a catalyst.
    closes = [100 + np.sin(i / 5) for i in range(50)] + [108.0]
    vols = [1e6] * 50 + [4e6]
    out = MomentumModel().predict(_bars(closes, vols))
    assert out.raw_confidence > 0          # it fired
    assert out.expected_return > 0         # and it's a BUY, not a fade
    assert out.win_probability > 0.5


def test_spike_without_volume_does_not_fire():
    # Same price spike but on NORMAL volume = noise, not a catalyst.
    closes = [100 + np.sin(i / 5) for i in range(50)] + [108.0]
    vols = [1e6] * 51
    out = MomentumModel().predict(_bars(closes, vols))
    assert out.raw_confidence == 0.0       # no volume confirmation -> abstain


def test_calm_market_does_not_fire():
    closes = [100 + np.sin(i / 5) for i in range(60)]
    vols = [1e6] * 60
    out = MomentumModel().predict(_bars(closes, vols))
    assert out.raw_confidence == 0.0


def test_division_is_advisory_and_routes_venue():
    d = MomentumDivision()
    assert d.advisory is True
    assert d.venue_for(_bars([100, 101], [1, 1], venue=Venue.KRAKEN)) == Venue.KRAKEN
    assert d.venue_for(_bars([100, 101], [1, 1], venue=Venue.IBKR)) == d.equity_venue
