"""Deterministic catalyst scoring + the Event division's confirmation gate.

The score is pure code over structured headlines (no LLM); the gate only makes
the sentinel MORE selective when news is available, and is neutral otherwise.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from boardroom.data.news import Headline, catalyst_score, default_keywords
from boardroom.data.snapshot import Bars
from boardroom.models.event import EventTriggerModel
from boardroom.schemas import Venue

_NOW = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _h(title: str, hours_ago: float, impact: float | None = None) -> Headline:
    return Headline(title=title, published_at=_NOW - timedelta(hours=hours_ago), impact=impact)


# --------------------------------------------------------------------------- #
# default_keywords
# --------------------------------------------------------------------------- #
def test_default_keywords_known_symbol():
    assert default_keywords("XBTUSD") == ("bitcoin", "btc", "xbt")


def test_default_keywords_unknown_symbol_falls_back():
    assert default_keywords("FOOUSD") == ("foo",)


# --------------------------------------------------------------------------- #
# catalyst_score
# --------------------------------------------------------------------------- #
def test_relevant_impactful_recent_scores_positive():
    heads = [_h("Major Bitcoin exchange hack drains funds", hours_ago=1.0)]
    score = catalyst_score(heads, keywords=("bitcoin", "btc"), now=_NOW)
    assert score > 0.0


def test_irrelevant_asset_scores_zero():
    heads = [_h("Ethereum upgrade ships on schedule", hours_ago=1.0)]
    assert catalyst_score(heads, keywords=("bitcoin", "btc"), now=_NOW) == 0.0


def test_outside_window_scores_zero():
    heads = [_h("Bitcoin ETF approval", hours_ago=100.0)]
    assert catalyst_score(heads, keywords=("bitcoin",), now=_NOW, lookback_hours=48.0) == 0.0


def test_recency_decay_newer_scores_higher():
    new = catalyst_score([_h("Bitcoin hack", 1.0)], keywords=("bitcoin",), now=_NOW)
    old = catalyst_score([_h("Bitcoin hack", 40.0)], keywords=("bitcoin",), now=_NOW)
    assert new > old > 0.0


def test_explicit_impact_overrides_lexicon():
    # No lexicon keyword, but an explicit source importance score still counts.
    heads = [_h("Bitcoin sees quiet trading", hours_ago=1.0, impact=5.0)]
    assert catalyst_score(heads, keywords=("bitcoin",), now=_NOW) > 0.0


def test_future_dated_headline_ignored():
    heads = [_h("Bitcoin hack", hours_ago=-5.0)]  # 5h in the future
    assert catalyst_score(heads, keywords=("bitcoin",), now=_NOW) == 0.0


def test_lookback_must_be_positive():
    with pytest.raises(ValueError):
        catalyst_score([], keywords=("btc",), now=_NOW, lookback_hours=0.0)


# --------------------------------------------------------------------------- #
# Event confirmation gate
# --------------------------------------------------------------------------- #
def _dislocated_bars() -> Bars:
    """A series that fires the price trigger: high vol + a sharp final z-score."""
    rng = np.random.default_rng(0)
    base = 100.0 * np.cumprod(1.0 + rng.normal(0.0, 0.05, 25))  # ~5% per-bar vol
    closes = np.append(base, base[-1] * 1.30)  # a sharp dislocation at the end
    n = closes.size
    end = datetime(2026, 6, 1, tzinfo=timezone.utc)
    times = pd.to_datetime([end - timedelta(days=(n - 1 - i)) for i in range(n)], utc=True)
    df = pd.DataFrame(
        {
            "time": times,
            "open": closes,
            "high": closes * 1.01,
            "low": closes * 0.99,
            "close": closes,
            "volume": np.full(n, 1e6),
        }
    )
    return Bars(symbol="XBTUSD", venue=Venue.KRAKEN, df=df, source="test")


def test_price_trigger_fires_without_news_provider():
    model = EventTriggerModel()
    fired, _ = model.evaluate(_dislocated_bars())
    assert fired is True  # anchors that the series genuinely dislocates


def test_strong_catalyst_confirms_the_trigger():
    model = EventTriggerModel(news_provider=lambda sym: [_h("Bitcoin exchange hack", 1.0)])
    fired, f = model.evaluate(_dislocated_bars())
    assert fired is True
    assert f["catalyst_score"] > 0.0


def test_no_catalyst_suppresses_the_trigger():
    # Provider works but finds nothing relevant -> sentinel stays silent.
    model = EventTriggerModel(news_provider=lambda sym: [_h("Unrelated market chatter", 1.0)])
    fired, f = model.evaluate(_dislocated_bars())
    assert fired is False
    assert f["catalyst_score"] == 0.0


def test_news_outage_does_not_suppress_trigger():
    def boom(sym: str):
        raise RuntimeError("news feed down")

    model = EventTriggerModel(news_provider=boom)
    fired, f = model.evaluate(_dislocated_bars())
    assert fired is True            # neutral fallback: price decides alone
    assert "catalyst_score" not in f


def test_predict_silent_when_gate_suppresses():
    model = EventTriggerModel(news_provider=lambda sym: [])
    out = model.predict(_dislocated_bars())
    assert out.raw_confidence == 0.0  # division will abstain
