"""Daily checkpoint scheduling.

The CEO convenes once a day at a configured UTC time. ``next_checkpoint`` is a
pure function so the dashboard and the runner agree on when the next run is.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def parse_hhmm(value: str) -> tuple[int, int]:
    """Parse 'HH:MM' (UTC) into (hour, minute). Defaults to 21:00 on bad input."""
    try:
        h, m = value.strip().split(":")
        hour, minute = int(h), int(m)
        if 0 <= hour < 24 and 0 <= minute < 60:
            return hour, minute
    except Exception:
        pass
    return 21, 0


def next_checkpoint(now: datetime, checkpoint_utc: str) -> datetime:
    """The next UTC datetime at the daily checkpoint time, strictly after ``now``."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    hour, minute = parse_hhmm(checkpoint_utc)
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate
