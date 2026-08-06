"""Resolution loop — close the feedback cycle that makes the system self-improve.

The decision loop opens positions; nothing closed them, so no outcome ever
resolved and the adaptive engine (calibration → trust → leash → retirement) could
never move. This module is the missing transmission:

  open position  ──(fresh prices)──►  resolved? ──►  ResolvedOutcome
        ▲                                                   │
        └──────────  update_division (guardrailed)  ◄───────┘

A position resolves when its horizon elapses OR a close breaches its stop. The
entry price is recovered from the series by timestamp, so paper (dry-run) and
live positions are scored identically off real market data — the system builds a
genuine track record before and after going live. ``win`` is net of the modeled
round-trip cost, matching the backtest's definition, so calibration is consistent
end to end.

Everything here is deterministic given (position, price series, now); the loop
swallows per-position fetch/resolve errors so one bad symbol can't stall the rest.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from boardroom.data.snapshot import Bars
from boardroom.graph.learning_loop import LearningUpdate, record_resolution, update_division
from boardroom.persistence.repository import OpenPosition, Repository
from boardroom.schemas import Decision, Division, Pitch, ResolvedOutcome

#: Resolution fetches fresh bars for a position's symbol; None means "no data
#: this checkpoint" (the position simply waits for the next one).
PriceFetcher = Callable[[OpenPosition], "Bars | None"]


def build_open_position(
    pitch: Pitch,
    decision: Decision,
    opened_at: datetime | None = None,
    qty: float = 0.0,
    entry_price: float = 0.0,
) -> OpenPosition:
    """Snapshot a funded pitch into an OpenPosition for later resolution.

    The stop fraction is recovered from the pitch's computed ``max_loss`` but
    CAPPED (`EXIT_STOP_CAP_PCT`), and the take-profit is a fixed R-multiple of
    the stop (`EXIT_TP_R_MULTIPLE`) — symmetric exits by construction. A month
    of live outcomes showed the old shape (TP at the band top ~+20-28%, stops
    10-14% deep) hit the TP once in 29 trades: small wins, big losses. The
    predicted band (± 2 horizon-scaled volatilities) is unchanged — it stays
    the Critic's "did reality land near our prediction" scoring window, no
    longer the exit trigger.
    """
    from boardroom.config import get_settings

    s = get_settings()
    capital = pitch.capital_required
    raw_stop = (pitch.max_loss - pitch.expected_cost) / capital if capital > 0 else 0.0
    cap = max(0.0, s.exit_stop_cap_pct)
    stop_fraction = min(raw_stop, cap) if raw_stop > 0 else cap
    take_profit = s.exit_tp_r_multiple * stop_fraction
    vol = float(pitch.signals.features.get("volatility", 0.0))
    horizon_vol = vol * math.sqrt(max(1.0, pitch.time_horizon_days))
    return OpenPosition(
        decision_id=decision.decision_id,
        division=pitch.division.value,
        venue=pitch.venue.value,
        symbol=pitch.symbol,
        size_cad=decision.size_cad,
        predicted_return=pitch.expected_return,
        predicted_confidence=pitch.confidence,
        cost_cad=pitch.expected_cost,
        stop_fraction=stop_fraction,
        band_low=pitch.expected_return - 2.0 * horizon_vol,
        band_high=pitch.expected_return + 2.0 * horizon_vol,
        horizon_days=pitch.time_horizon_days,
        opened_at=opened_at or decision.created_at,
        live=decision.live,
        qty=qty,
        take_profit=take_profit,
        entry_price=entry_price,
    )


def _as_utc(ts: datetime) -> datetime:
    return ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts


@dataclass
class WalkResult:
    """One resolution pass over a position: the outcome (if an exit triggered)
    plus the trail state the caller persists when the position stays open."""

    outcome: ResolvedOutcome | None
    entry_price: float = 0.0
    peak_return: float = 0.0
    trail_armed: bool = False


def walk_position(
    pos: OpenPosition, bars: Bars, *, now: datetime | None = None, force_now: bool = False
) -> WalkResult:
    """Walk one open position over a fresh price series.

    Long-only (the system only opens BUY): realized return is measured from the
    entry price — the fill-time price when the position carries one
    (``entry_price``), else recovered from the series by timestamp (legacy
    rows). Signals an EXIT at the first post-entry close that breaches the
    **stop-loss** (``-stop_fraction``) or — with trailing disabled — hits the
    **take-profit**; else at the latest close once the **horizon** has elapsed;
    otherwise it keeps waiting.

    ``force_now=True`` resolves at the latest close even before any trigger —
    the capital-rotation path uses it to close a weak position early when a
    better idea is waiting for the money.

    **Trailing exits** (``EXIT_TRAIL_ENABLED``, owner mandate 2026-08-04 "let
    winners run"): the take-profit printing ARMS a trailing stop instead of
    selling. Arming and the peak ride off bar **HIGHS** — a pump is a wick
    long before it is a close — while the exit itself fires on a CLOSE that
    gives back the stop distance from the peak, even past the horizon. Upside
    is uncapped; the give-back is bounded by the same capped stop fraction.
    Armed/peak state is seeded from the position (persisted across
    checkpoints) so a ride survives restarts and rolling bar windows — the
    2026-08-06 LIT round-trip happened because this state lived only inside
    one daily-bar walk.
    """
    from boardroom.config import get_settings

    trail_enabled = get_settings().exit_trail_enabled
    df = bars.df
    opened_at = _as_utc(pos.opened_at)
    now = _as_utc(now) if now is not None else _as_utc(bars.last_time)

    times = df["time"]
    closes = df["close"].to_numpy(dtype=float)
    # Arming/peak ride off HIGHS (a pump is a wick long before it's a close);
    # a series without them (older tests/fixtures) degrades to close-only.
    highs = df["high"].to_numpy(dtype=float) if "high" in df.columns else closes
    bar_times = [
        _as_utc(t.to_pydatetime() if hasattr(t, "to_pydatetime") else t) for t in times
    ]

    entry_price = float(getattr(pos, "entry_price", 0.0) or 0.0)
    if entry_price <= 0:
        # Legacy row: entry = the last close at or before the open time.
        entry_idx = max((i for i, t in enumerate(bar_times) if t <= opened_at), default=None)
        if entry_idx is None:
            return WalkResult(None)  # series starts after the open — can't price the entry
        entry_price = closes[entry_idx]
        if entry_price <= 0:
            return WalkResult(None)
        start = entry_idx + 1
    else:
        start = next((i for i, t in enumerate(bar_times) if t > opened_at), len(closes))

    cost_fraction = pos.cost_cad / pos.size_cad if pos.size_cad > 0 else 0.0

    # Take-profit = the explicit R-multiple trigger; legacy rows (take_profit 0)
    # fall back to the old band-top behavior.
    tp_level = pos.take_profit if getattr(pos, "take_profit", 0.0) > 0 else pos.band_high
    take_profit = tp_level if tp_level and tp_level > 0 else None
    # Trail distance = the position's own (capped) stop fraction; fall back to
    # the take-profit distance if a legacy row carries no stop.
    trail_fraction = pos.stop_fraction if pos.stop_fraction > 0 else (take_profit or 0.0)
    armed = bool(getattr(pos, "trail_armed", False)) and trail_enabled and trail_fraction > 0
    peak_r = max(0.0, float(getattr(pos, "peak_return", 0.0) or 0.0))

    def _state(outcome: ResolvedOutcome | None) -> WalkResult:
        return WalkResult(outcome, entry_price=entry_price, peak_return=peak_r, trail_armed=armed)

    for i in range(start, len(closes)):
        r = closes[i] / entry_price - 1.0
        r_high = highs[i] / entry_price - 1.0
        if not armed:
            if pos.stop_fraction > 0 and r <= -pos.stop_fraction:
                return _state(_make_outcome(pos, r, cost_fraction, bar_times[i]))
            if take_profit is not None and r_high >= take_profit:
                if not (trail_enabled and trail_fraction > 0):
                    if r >= take_profit:  # hard TP fires on the close, as before
                        return _state(_make_outcome(pos, r, cost_fraction, bar_times[i]))
                    continue
                armed = True
                peak_r = max(peak_r, r_high)
            else:
                continue
        # Armed: ride the peak (highs); exit when a CLOSE gives back the trail
        # distance — same-bar pump-and-dump included.
        peak_r = max(peak_r, r_high)
        if (1.0 + r) <= (1.0 + peak_r) * (1.0 - trail_fraction):
            return _state(_make_outcome(pos, r, cost_fraction, bar_times[i]))

    if armed and not force_now:
        # A winner still riding its trail is never cut by the clock — the
        # trailing stop (bounded give-back from the peak) is the exit.
        return _state(None)

    # No trigger — resolve on horizon elapse (or on demand for a rotation),
    # otherwise keep waiting.
    elapsed_days = (now - opened_at).total_seconds() / 86400.0
    if elapsed_days < pos.horizon_days and not force_now:
        return _state(None)
    realized = closes[-1] / entry_price - 1.0
    return _state(_make_outcome(pos, realized, cost_fraction, now))


def resolve_position(
    pos: OpenPosition, bars: Bars, *, now: datetime | None = None, force_now: bool = False
) -> ResolvedOutcome | None:
    """Resolve one open position, or None if not yet — ``walk_position`` without
    the trail-state plumbing, for callers that only need the outcome."""
    return walk_position(pos, bars, now=now, force_now=force_now).outcome


def _make_outcome(
    pos: OpenPosition, realized: float, cost_fraction: float, resolved_at: datetime
) -> ResolvedOutcome:
    net = realized - cost_fraction
    return ResolvedOutcome(
        decision_id=pos.decision_id,
        division=Division(pos.division),
        symbol=pos.symbol,
        resolved_at=resolved_at,
        predicted_return=pos.predicted_return,
        realized_return=realized,
        predicted_confidence=pos.predicted_confidence,
        win=net > 0.0,
        pnl_cad=pos.size_cad * realized,
        cost_cad=pos.cost_cad,
        inside_band=pos.band_low <= realized <= pos.band_high,
    )


def resolve_open_positions(
    repo: Repository,
    fetch_for: PriceFetcher,
    *,
    now: datetime | None = None,
    close_live: "Callable[[OpenPosition, ResolvedOutcome], bool] | None" = None,
) -> list[LearningUpdate]:
    """Resolve every ready open position and fold each into the adaptive engine.

    For each open position: fetch fresh prices, resolve if ready, **execute the
    exit** (``close_live`` sells the held qty on the venue), persist the outcome
    (which advances the division's Beta posterior), close the tracking row, and
    re-derive its leash/retirement via ``update_division``. Per-position failures
    are isolated so one bad symbol can't stall the others.

    ``close_live(pos, outcome) -> bool`` places the real sell and returns whether
    the position is now actually closed. If it returns False (e.g. the sell was
    rejected), the position is LEFT OPEN to retry next checkpoint and no outcome
    is booked — so the system's record never claims a sale that didn't happen.
    When ``close_live`` is None, positions resolve on paper (dry-run / tests).
    """
    updates: list[LearningUpdate] = []
    for pos in repo.open_positions():
        try:
            bars = fetch_for(pos)
        except Exception:
            bars = None
        if bars is None:
            continue
        try:
            walk = walk_position(pos, bars, now=now)
        except Exception:
            repo.audit("resolution_error", {"decision_id": pos.decision_id, "symbol": pos.symbol})
            continue
        outcome = walk.outcome
        if outcome is None:
            # Still riding — persist the trail state (entry backfill, peak off
            # highs, armed flag) so the ride survives restarts and rolling
            # intraday bar windows.
            changed = (
                walk.entry_price != (pos.entry_price or 0.0)
                or walk.peak_return != (pos.peak_return or 0.0)
                or walk.trail_armed != bool(pos.trail_armed)
            )
            if changed and walk.entry_price > 0:
                try:
                    repo.update_position_trail(
                        pos.decision_id,
                        entry_price=walk.entry_price,
                        peak_return=walk.peak_return,
                        trail_armed=walk.trail_armed,
                    )
                except Exception:  # noqa: BLE001 — state persistence is best-effort
                    pass
            continue
        # Execute the real exit before booking the outcome. If the sell fails,
        # keep the position open and don't record a fictional realized P&L.
        if close_live is not None:
            # Two processes can pass here now (a one-shot checkpoint and the
            # poller's exit watcher): re-read just before selling so a row a
            # concurrent pass already closed is never sold or booked twice.
            try:
                if all(p.decision_id != pos.decision_id for p in repo.open_positions()):
                    continue
            except Exception:  # noqa: BLE001 — an unreadable repo must not block the exit
                pass
            try:
                closed = close_live(pos, outcome)
            except Exception as e:  # noqa: BLE001
                closed = False
                repo.audit("exit_error", {"decision_id": pos.decision_id, "symbol": pos.symbol, "error": str(e)[:160]})
            if not closed:
                continue
        record_resolution(outcome, repo)
        repo.close_position(pos.decision_id)
        repo.audit(
            "position_resolved",
            {
                "decision_id": pos.decision_id,
                "division": pos.division,
                "realized_return": round(outcome.realized_return, 5),
                "win": outcome.win,
                "pnl_cad": round(outcome.pnl_cad, 2),
            },
        )
        updates.append(update_division(pos.division, repo))
    return updates
