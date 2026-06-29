"""Equities market-hours guard.

Crypto (Kraken) trades 24/7, so a checkpoint can fire at any time and the Event
division fills fine. Equities do NOT: IBKR only
fill during the regular session — 9:30am–4:00pm America/New_York, Mon–Fri (the
US and Toronto exchanges share these hours). A market order sent after the close
either gets rejected or queued blindly to the next open, where it fills at an
unknown gap price. For a small, careful book that breaks the grounding law
("code calculates"): the decision was made on stale closing prices but would
fill somewhere else entirely.

So we gate LIVE equity orders on the session being open. If it's closed, the
Directional leg is HELD (logged, not sent) rather than queued into the dark.

Holidays are not modelled — on a market holiday this returns True (a weekday in
window) and the broker simply rejects the order, which we log. That's harmless
for a $200 book; a holiday calendar isn't worth the maintenance here.
"""

from __future__ import annotations

from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from boardroom.schemas import Venue

_ET = ZoneInfo("America/New_York")
_OPEN = time(9, 30)
_CLOSE = time(16, 0)

# Venues that only fill during the regular equities session.
EQUITIES_VENUES = {Venue.IBKR}


def is_equities_venue(venue: Venue) -> bool:
    return venue in EQUITIES_VENUES


def equities_session_open(now_utc: datetime | None = None) -> bool:
    """True if the North American equities regular session is open right now.

    ``now_utc`` defaults to the current UTC time; pass one in for testing.
    """
    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    et = now.astimezone(_ET)
    if et.weekday() >= 5:  # Saturday/Sunday
        return False
    return _OPEN <= et.time() < _CLOSE


def session_note(now_utc: datetime | None = None) -> str:
    """A short human reason string for the audit log."""
    now = now_utc or datetime.now(timezone.utc)
    et = now.astimezone(_ET)
    return f"equities session closed at {et:%a %H:%M ET} (regular 09:30–16:00 ET, Mon–Fri)"
