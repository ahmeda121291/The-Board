"""The exit watcher — intraday exit checks between checkpoints. Sells only.

Why this exists: on 2026-08-06 the book rode LIT +75% overnight to ~$969 and
round-tripped to a -14% stop-out. Checkpoints ran four times during the move,
but exits evaluated on daily closes — the pump never printed as a close, so
nothing sold. The watcher closes that blindness structurally: every
``EXIT_WATCH_MINUTES`` it prices ONLY the held book on intraday bars
(``EXIT_BAR_MINUTES``) and executes any stop / take-profit / trailing exit
immediately, at any hour. Crypto trades 24/7; the exits now do too.

Scope is deliberately narrow — no LLM, no pitches, no new entries, no
rotation: a pure risk-and-profit-capture pass over open positions, cheap
enough to run every few minutes (one public OHLC call per held symbol).
Entries remain the boardroom's job at checkpoints; when the watcher frees
capital the scheduler convenes one immediately (``EXIT_REENTRY_ENABLED``) so
the cash is re-bet on the current best idea instead of idling.
"""

from __future__ import annotations

from boardroom.graph.learning_loop import LearningUpdate
from boardroom.graph.resolution_loop import resolve_open_positions


def watch_exits(orch) -> list[LearningUpdate]:
    """One watcher pass: resolve any triggered exits on the held book.

    Returns the learning updates for positions that actually closed (empty on
    a quiet pass). Never raises — a failed pass is audited and skipped; the
    next pass (or checkpoint) retries.
    """
    try:
        if not orch.repo.open_positions():
            return []
        orch._fine_cache = None  # fresh intraday series every pass
        lookup = orch._resolution_price_lookup()
        updates = resolve_open_positions(
            orch.repo, lookup, close_live=orch._close_position_live
        )
        if updates:
            orch.repo.audit("exit_watch", {"exits": len(updates)})
        return updates
    except Exception as e:  # noqa: BLE001 — the watcher must never kill the scheduler
        try:
            orch.repo.audit("exit_watch_error", {"error": str(e)[:160]})
        except Exception:  # noqa: BLE001
            pass
        return []
