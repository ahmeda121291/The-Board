"""Deterministic catalyst scoring for the Event division.

The grounding law (scope §5) still holds here: the *score* is computed by code
from structured headline data, never an LLM's free-form read of the news. We take
a list of timestamped headlines and produce a single non-negative ``catalyst
score`` from (a) whether a headline is about the asset, (b) a fixed impact lexicon
(hacks, regulatory action, ETF/listing news, halts, …), and (c) linear recency
decay over a lookback window. No model, no network, no randomness.

The Event division uses this only as a *confirmation gate*: a price dislocation
that already fired its quantitative trigger is additionally required to coincide
with a real catalyst. When no news provider is configured (or a fetch fails) the
gate is neutral and the division behaves exactly as it did before — this layer is
strictly additive and never suppresses a trigger on a news outage.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

#: Fixed impact lexicon: catalyst keyword -> weight. Deterministic and inspectable
#: — the kind of event, not anyone's opinion of it. Lowercased substring match.
_IMPACT_KEYWORDS: dict[str, float] = {
    "hack": 3.0,
    "exploit": 3.0,
    "breach": 2.5,
    "sec": 2.5,
    "lawsuit": 2.0,
    "ban": 2.0,
    "halt": 2.5,
    "delist": 2.5,
    "default": 2.5,
    "bankrupt": 3.0,
    "insolven": 3.0,  # insolvent / insolvency
    "etf": 2.0,
    "approval": 2.0,
    "listing": 1.5,
    "upgrade": 1.5,
    "fork": 1.5,
    "partnership": 1.0,
    "outage": 1.5,
    "depeg": 3.0,
}

#: Known crypto symbol -> asset aliases (lowercased substring match in titles).
_ASSET_ALIASES: dict[str, tuple[str, ...]] = {
    "XBT": ("bitcoin", "btc", "xbt"),
    "BTC": ("bitcoin", "btc", "xbt"),
    "ETH": ("ethereum", "eth", "ether"),
    "SOL": ("solana", "sol"),
    "ADA": ("cardano", "ada"),
    "XRP": ("ripple", "xrp"),
    "DOT": ("polkadot", "dot"),
}


@dataclass(frozen=True)
class Headline:
    """One timestamped news item. ``impact`` is an optional pre-scored weight from
    the source (e.g. CryptoPanic vote counts); when absent the lexicon decides."""

    title: str
    published_at: datetime
    source: str = ""
    impact: float | None = None


#: A news provider takes an asset symbol and returns recent headlines for it.
NewsProvider = Callable[[str], list[Headline]]


def default_keywords(symbol: str) -> tuple[str, ...]:
    """Asset aliases to match in headline text, derived from a venue symbol.

    Strips a common quote suffix (USD/USDT/…) and looks the base up in the alias
    table; falls back to the lowercased base token itself.
    """
    s = symbol.upper()
    for quote in ("USDT", "USDC", "USD", "EUR", "CAD"):
        if s.endswith(quote) and len(s) > len(quote):
            s = s[: -len(quote)]
            break
    return _ASSET_ALIASES.get(s, (s.lower(),))


def _impact_weight(title_lower: str, explicit: float | None) -> float:
    """Catalyst weight for a headline: explicit source score if given, else the
    sum of matched lexicon weights. Returns 0.0 when nothing catalytic matches."""
    if explicit is not None:
        return max(0.0, float(explicit))
    return float(sum(w for kw, w in _IMPACT_KEYWORDS.items() if kw in title_lower))


def catalyst_score(
    headlines: list[Headline],
    *,
    keywords: tuple[str, ...],
    now: datetime,
    lookback_hours: float = 48.0,
) -> float:
    """Recency-weighted sum of catalyst impact for headlines about the asset.

    A headline contributes only if (1) it mentions one of ``keywords``, and (2) it
    falls within ``[now - lookback_hours, now]``. Its contribution is the impact
    weight times a linear recency factor (1.0 at ``now``, 0.0 at the edge of the
    window). Deterministic and non-negative.
    """
    if lookback_hours <= 0:
        raise ValueError("lookback_hours must be > 0")
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    window_seconds = lookback_hours * 3600.0
    kws = tuple(k.lower() for k in keywords)

    total = 0.0
    for h in headlines:
        title_lower = h.title.lower()
        if not any(k in title_lower for k in kws):
            continue
        published = h.published_at
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        age = (now - published).total_seconds()
        if age < 0 or age > window_seconds:
            continue  # future-dated or older than the window
        recency = 1.0 - age / window_seconds
        total += _impact_weight(title_lower, h.impact) * recency
    return total


def fetch_cryptopanic_headlines(
    symbol: str, *, token: str, timeout: float = 15.0
) -> list[Headline]:
    """Fetch recent headlines for ``symbol`` from CryptoPanic (needs an auth token).

    Best-effort and defensive: maps the venue symbol to a CryptoPanic currency
    code and returns parsed :class:`Headline` objects. Any network/parse failure
    raises, and the Event gate treats a raise as "no opinion" (fires on price
    alone). Imported lazily so the package needs no httpx to load.
    """
    import httpx

    base = symbol.upper()
    for quote in ("USDT", "USDC", "USD", "EUR", "CAD"):
        if base.endswith(quote) and len(base) > len(quote):
            base = base[: -len(quote)]
            break
    currency = "BTC" if base == "XBT" else base

    resp = httpx.get(
        "https://cryptopanic.com/api/v1/posts/",
        params={"auth_token": token, "currencies": currency, "kind": "news"},
        timeout=timeout,
    )
    resp.raise_for_status()
    results = resp.json().get("results", [])
    out: list[Headline] = []
    for r in results:
        published = datetime.fromisoformat(r["published_at"].replace("Z", "+00:00"))
        votes = r.get("votes") or {}
        importance = votes.get("important")
        out.append(
            Headline(
                title=r.get("title", ""),
                published_at=published,
                source=(r.get("source") or {}).get("title", "cryptopanic"),
                impact=float(importance) if importance else None,
            )
        )
    return out
