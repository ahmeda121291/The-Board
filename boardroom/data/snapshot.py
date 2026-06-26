"""Freshness/sanity checks and content hashing for market data.

The grounding rule depends on this: a division may only pitch on data that is
fresh, complete, and sane. Anything else -> abstain. The ``content_hash`` pins
exactly what was seen so a decision can be replayed (scope §5).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from boardroom.schemas import DataSnapshot, Venue

#: Required OHLCV columns for any bar set.
OHLCV = ("time", "open", "high", "low", "close", "volume")


class SanityError(Exception):
    """Raised when data fails a sanity check. Callers translate this to abstain."""


@dataclass
class Bars:
    """A validated OHLCV series for one symbol on one venue."""

    symbol: str
    venue: Venue
    df: pd.DataFrame  # columns == OHLCV, sorted ascending by time
    source: str

    @property
    def last_time(self) -> datetime:
        ts = self.df["time"].iloc[-1]
        return ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts

    @property
    def closes(self) -> np.ndarray:
        return self.df["close"].to_numpy(dtype=float)

    @property
    def volumes(self) -> np.ndarray:
        return self.df["volume"].to_numpy(dtype=float)


def sanity_check(df: pd.DataFrame, *, min_rows: int = 30) -> None:
    """Raise :class:`SanityError` if the frame is unusable.

    Catches the realistic failure modes of live feeds: gaps, NaNs, non-positive
    prices, zero-variance (a stuck feed), and out-of-order timestamps.
    """
    missing = [c for c in OHLCV if c not in df.columns]
    if missing:
        raise SanityError(f"missing columns: {missing}")
    if len(df) < min_rows:
        raise SanityError(f"too few rows: {len(df)} < {min_rows}")
    if df[list(OHLCV)].isnull().any().any():
        raise SanityError("contains NaNs")
    if (df[["open", "high", "low", "close"]] <= 0).any().any():
        raise SanityError("non-positive prices")
    if (df["high"] < df["low"]).any():
        raise SanityError("high < low on some bar")
    if not df["time"].is_monotonic_increasing:
        raise SanityError("timestamps not monotonically increasing")
    if float(np.std(df["close"].to_numpy(dtype=float))) == 0.0:
        raise SanityError("zero price variance — feed likely stuck")


def content_hash(df: pd.DataFrame) -> str:
    """Stable SHA-256 over the bar values, for reconstructability."""
    numeric = ["open", "high", "low", "close", "volume"]
    out = df[["time"]].copy()
    out["time"] = out["time"].astype(str)
    out[numeric] = df[numeric].round(8)
    payload = out[list(OHLCV)].to_dict(orient="records")
    blob = json.dumps(payload, sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()


def build_snapshot(
    bars: Bars,
    *,
    max_age_seconds: float,
    now: datetime | None = None,
    min_rows: int = 30,
) -> DataSnapshot:
    """Validate ``bars`` and produce a :class:`DataSnapshot`.

    Never raises on staleness — instead returns a snapshot with ``is_fresh`` set
    appropriately so the division can decide to abstain. *Does* raise
    :class:`SanityError` on structurally broken data (which also means abstain).
    """
    now = now or datetime.now(timezone.utc)
    sanity_check(bars.df, min_rows=min_rows)

    last = bars.last_time
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    age = (now - last).total_seconds()

    return DataSnapshot(
        symbol=bars.symbol,
        venue=bars.venue,
        as_of=last,
        age_seconds=age,
        is_fresh=0 <= age <= max_age_seconds,
        rows=len(bars.df),
        content_hash=content_hash(bars.df),
        source=bars.source,
        notes=None if 0 <= age <= max_age_seconds else f"stale: {age:.0f}s old",
    )
