"""Outcome hydration from Supabase rows: resolved_at must come from the ROW.

The schema default stamps "now"; when recent_outcomes dropped the row's
resolved_at, every historical outcome read as freshly resolved, so the
DAILY-loss breaker summed ALL-TIME losses and force-held every checkpoint once
lifetime losses passed the daily limit (frozen live from 2026-08-01 to -04)."""

from __future__ import annotations

import datetime as dt

from boardroom.persistence.supabase_repo import _outcome_from_row


def _row(**overrides) -> dict:
    row = {
        "decision_id": "11111111-1111-1111-1111-111111111111",
        "division": "momentum",
        "symbol": "COTIUSD",
        "resolved_at": "2026-08-03T00:00:00+00:00",
        "predicted_return": 0.08,
        "realized_return": -0.29,
        "predicted_confidence": 0.7,
        "win": False,
        "pnl_cad": -7.25,
        "cost_cad": 0.31,
        "inside_band": True,
        "process_luck": None,
        "postmortem": "",
    }
    row.update(overrides)
    return row


def test_resolved_at_comes_from_the_row_not_now():
    o = _outcome_from_row(_row())
    assert o.resolved_at.date() == dt.date(2026, 8, 3)
    assert o.resolved_at.tzinfo is not None
    # The exact failure mode: an old outcome must NOT read as resolved today.
    assert o.resolved_at.date() != dt.datetime.now(dt.timezone.utc).date()


def test_postgres_style_timestamp_parses():
    o = _outcome_from_row(_row(resolved_at="2026-08-03 00:00:00+00"))
    assert o.resolved_at.date() == dt.date(2026, 8, 3)


def test_symbol_is_hydrated():
    assert _outcome_from_row(_row()).symbol == "COTIUSD"
    assert _outcome_from_row(_row(symbol=None)).symbol == ""


def test_missing_or_bad_resolved_at_falls_back_to_now():
    today = dt.datetime.now(dt.timezone.utc).date()
    assert _outcome_from_row(_row(resolved_at=None)).resolved_at.date() == today
    assert _outcome_from_row(_row(resolved_at="not-a-date")).resolved_at.date() == today
