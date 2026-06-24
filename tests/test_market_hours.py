"""Market-hours guard: equities only fill during the regular session."""

from datetime import datetime, timezone

from boardroom.market import (
    EQUITIES_VENUES,
    equities_session_open,
    is_equities_venue,
    session_note,
)
from boardroom.schemas import Venue


def _utc(y, mo, d, h, mi):
    return datetime(y, mo, d, h, mi, tzinfo=timezone.utc)


def test_equities_venue_classification():
    assert is_equities_venue(Venue.SNAPTRADE)
    assert is_equities_venue(Venue.IBKR)
    assert not is_equities_venue(Venue.KRAKEN)  # crypto is 24/7
    assert Venue.KRAKEN not in EQUITIES_VENUES


def test_open_midsession_summer():
    # 2026-06-24 is a Wednesday. 18:00 UTC = 14:00 EDT — inside 9:30–16:00 ET.
    assert equities_session_open(_utc(2026, 6, 24, 18, 0)) is True


def test_closed_after_hours_summer():
    # 21:00 UTC = 17:00 EDT — after the 16:00 ET close.
    assert equities_session_open(_utc(2026, 6, 24, 21, 0)) is False


def test_closed_before_open_summer():
    # 13:00 UTC = 09:00 EDT — before the 09:30 ET open.
    assert equities_session_open(_utc(2026, 6, 24, 13, 0)) is False


def test_closed_on_weekend():
    # 2026-06-27 is a Saturday; mid-day UTC must still be closed.
    assert equities_session_open(_utc(2026, 6, 27, 18, 0)) is False


def test_default_checkpoint_1900_is_open():
    # The new default CHECKPOINT_UTC=19:00 must fall inside the session (summer).
    assert equities_session_open(_utc(2026, 6, 24, 19, 0)) is True


def test_session_note_is_human_readable():
    note = session_note(_utc(2026, 6, 24, 21, 0))
    assert "ET" in note
