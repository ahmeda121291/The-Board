"""News-intensity scoring — deterministic catalyst confirmation."""

from datetime import datetime, timedelta, timezone

from boardroom.data.news import news_intensity, top_headlines

NOW = datetime(2026, 6, 26, 12, 0, tzinfo=timezone.utc)


def _item(title, hours_ago):
    return {"title": title, "published_at": NOW - timedelta(hours=hours_ago)}


def test_no_news_is_zero():
    assert news_intensity([], now=NOW) == 0.0


def test_recent_burst_scores_higher_than_old():
    burst = [_item(f"h{i}", 1) for i in range(5)]        # 5 headlines, 1h old
    stale = [_item(f"h{i}", 90) for i in range(5)]       # 5 headlines, ~4d old
    assert news_intensity(burst, now=NOW) > news_intensity(stale, now=NOW)


def test_recency_halflife():
    # One headline at the halflife (24h) ~= 0.5; fresh ~= 1.0.
    fresh = news_intensity([_item("x", 0)], now=NOW, halflife_hours=24.0)
    half = news_intensity([_item("x", 24)], now=NOW, halflife_hours=24.0)
    assert abs(fresh - 1.0) < 0.01
    assert abs(half - 0.5) < 0.02


def test_outside_lookback_ignored():
    assert news_intensity([_item("x", 200)], now=NOW, lookback_hours=96.0) == 0.0


def test_top_headlines_newest_first():
    items = [_item("old", 50), _item("new", 1), _item("mid", 10)]
    assert top_headlines(items, 2) == ["new", "mid"]
