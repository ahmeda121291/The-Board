"""Real market-data sources, plus a deterministic synthetic source for tests.

- Kraken public OHLC: no API key required (public endpoint) — covers the crypto
  legs (Yield/Event) for research and the Event triggers.
- Stooq daily CSV: keyless equities/ETF daily bars — covers Directional research
  before the optional paid market-data feed is wired.

Network failures, bad payloads, or empty frames raise; callers translate any
failure into an abstain (no fresh data, no trade).
"""

from __future__ import annotations

import io
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from boardroom.data.snapshot import Bars
from boardroom.schemas import Venue

_KRAKEN_OHLC = "https://api.kraken.com/0/public/OHLC"
_STOOQ_CSV = "https://stooq.com/q/d/l/"


# A browser-ish UA + Accept; free sources (esp. Stooq) often refuse the default
# python-httpx agent or throttle it harder.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/csv,application/json,text/plain,*/*",
}


def _http_get(url: str, params: dict, timeout: float = 15.0):
    import httpx  # local import so the package imports without httpx in minimal envs

    resp = httpx.get(url, params=params, timeout=timeout, headers=_HEADERS, follow_redirects=True)
    resp.raise_for_status()
    return resp


def fetch_kraken_ohlc(pair: str = "XBTUSD", interval_minutes: int = 1440) -> Bars:
    """Daily (or finer) OHLC for a Kraken pair from the public endpoint.

    ``interval_minutes``: 1, 5, 15, 30, 60, 240, 1440, 10080, 21600.
    """
    resp = _http_get(_KRAKEN_OHLC, {"pair": pair, "interval": interval_minutes})
    payload = resp.json()
    if payload.get("error"):
        raise RuntimeError(f"Kraken error for {pair}: {payload['error']}")
    result = payload["result"]
    key = next(k for k in result if k != "last")
    rows = result[key]
    df = pd.DataFrame(
        rows, columns=["time", "open", "high", "low", "close", "vwap", "volume", "count"]
    )
    df = df.assign(
        time=pd.to_datetime(df["time"], unit="s", utc=True),
        open=df["open"].astype(float),
        high=df["high"].astype(float),
        low=df["low"].astype(float),
        close=df["close"].astype(float),
        volume=df["volume"].astype(float),
    )[["time", "open", "high", "low", "close", "volume"]]
    return Bars(symbol=pair, venue=Venue.KRAKEN, df=df, source="kraken_public_ohlc")


def fetch_stooq_daily(symbol: str = "spy.us", *, attempts: int = 3) -> Bars:
    """Daily equity/ETF bars from Stooq (keyless). Symbols like 'spy.us', 'qqq.us'.

    Stooq throttles bursts (a multi-symbol scan hits it many times at once) and
    answers a blocked request with a non-CSV body ("Exceeded the daily hits
    limit") rather than an HTTP error. Retry with backoff, which also spaces the
    burst out enough to recover. Raises with the real reason if it still fails.
    """
    import time as _time

    last_err: Exception | None = None
    for i in range(attempts):
        try:
            text = _http_get(_STOOQ_CSV, {"s": symbol, "i": "d"}).text.strip()
            head = text.splitlines()[0] if text else ""
            if not text or "Close" not in head:
                raise RuntimeError(f"Stooq blocked/empty for {symbol}: {text[:80]!r}")
            df = pd.read_csv(io.StringIO(text))
            if df.empty or "Close" not in df.columns:
                raise RuntimeError(f"Stooq returned no rows for {symbol}")
            df = df.rename(columns=str.lower)
            df = df.assign(time=pd.to_datetime(df["date"], utc=True))[
                ["time", "open", "high", "low", "close", "volume"]
            ].astype({"open": float, "high": float, "low": float, "close": float, "volume": float})
            return Bars(symbol=symbol.upper(), venue=Venue.IBKR, df=df, source="stooq_daily")
        except Exception as e:  # transient block / network — back off and retry
            last_err = e
            if i < attempts - 1:
                _time.sleep(1.0 * (i + 1))  # 1s, 2s — spreads the burst out
    raise RuntimeError(f"Stooq failed for {symbol} after {attempts} attempts: {last_err}")


def synthetic_bars(
    symbol: str = "SYN",
    venue: Venue = Venue.IBKR,
    *,
    n: int = 120,
    seed: int = 7,
    drift: float = 0.0005,
    vol: float = 0.02,
    end: datetime | None = None,
) -> Bars:
    """Deterministic geometric-random-walk bars for tests and offline dev.

    Seeded, so it is reproducible — never used for real decisions, only to
    exercise the loop without a live feed.
    """
    rng = np.random.default_rng(seed)
    end = end or datetime.now(timezone.utc)
    rets = rng.normal(drift, vol, size=n)
    close = 100.0 * np.exp(np.cumsum(rets))
    high = close * (1 + np.abs(rng.normal(0, vol / 2, n)))
    low = close * (1 - np.abs(rng.normal(0, vol / 2, n)))
    open_ = np.concatenate([[close[0]], close[:-1]])
    vol_series = rng.uniform(1e5, 5e5, n)
    times = [end - timedelta(days=(n - 1 - i)) for i in range(n)]
    df = pd.DataFrame(
        {
            "time": pd.to_datetime(times, utc=True),
            "open": open_,
            "high": np.maximum.reduce([open_, high, close]),
            "low": np.minimum.reduce([open_, low, close]),
            "close": close,
            "volume": vol_series,
        }
    )
    return Bars(symbol=symbol, venue=venue, df=df, source="synthetic")
