"""News / catalyst feed — the qualitative layer on top of price+volume.

Keyless via Yahoo Finance's search endpoint. We compute a deterministic
``news_intensity`` (a recency-weighted count of recent headlines) — a catalyst
produces a *burst* of coverage, so a high score is the computed "something is
happening" tell that confirms a volume-backed breakout. Headlines themselves are
attached for the human/CFO to read. We never let the model free-form a number:
the score is code; the headlines are context.

Fetched only for symbols that already broke out (cheap), and any failure degrades
gracefully to "no news" (score 0, empty list) — never blocks a decision.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

_YAHOO_SEARCH = "https://query1.finance.yahoo.com/v1/finance/search"


def fetch_news(ticker: str, *, count: int = 10) -> list[dict]:
    """Recent news items for a ticker: ``[{title, publisher, link, published_at}]``.

    Returns [] on any failure (no key, network, parse) — news is enrichment, not
    a hard dependency.
    """
    from boardroom.data.sources import _http_get

    try:
        payload = _http_get(
            _YAHOO_SEARCH, {"q": ticker, "newsCount": count, "quotesCount": 0}
        ).json()
    except Exception:
        return []

    items: list[dict] = []
    for n in payload.get("news") or []:
        ts = n.get("providerPublishTime")
        if not ts:
            continue
        try:
            published = datetime.fromtimestamp(int(ts), tz=timezone.utc)
        except (ValueError, OSError, TypeError):
            continue
        items.append(
            {
                "title": str(n.get("title", "")).strip(),
                "publisher": str(n.get("publisher", "")).strip(),
                "link": str(n.get("link", "")),
                "published_at": published,
            }
        )
    return items


def news_intensity(
    items: list[dict],
    *,
    now: datetime | None = None,
    halflife_hours: float = 24.0,
    lookback_hours: float = 96.0,
) -> float:
    """Recency-weighted count of recent headlines (a catalyst = a burst).

    Each headline contributes ``0.5 ** (age / halflife)`` if within the lookback;
    fully deterministic given the inputs. ~0 = quiet, several = active coverage.
    """
    if not items:
        return 0.0
    now = now or datetime.now(timezone.utc)
    score = 0.0
    for it in items:
        pub = it.get("published_at")
        if pub is None:
            continue
        age_h = (now - pub).total_seconds() / 3600.0
        if age_h < 0.0 or age_h > lookback_hours:
            continue
        score += math.pow(0.5, age_h / halflife_hours)
    return round(float(score), 3)


def top_headlines(items: list[dict], k: int = 3) -> list[str]:
    """The k most recent non-empty headlines, newest first."""
    dated = [i for i in items if i.get("published_at") and i.get("title")]
    dated.sort(key=lambda i: i["published_at"], reverse=True)
    return [i["title"] for i in dated[:k]]
