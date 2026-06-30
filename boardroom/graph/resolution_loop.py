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
from datetime import datetime, timezone

from boardroom.data.snapshot import Bars
from boardroom.graph.learning_loop import LearningUpdate, record_resolution, update_division
from boardroom.persistence.repository import OpenPosition, Repository
from boardroom.schemas import Decision, Division, Pitch, ResolvedOutcome

#: Resolution fetches fresh bars for a position's symbol; None means "no data
#: this checkpoint" (the position simply waits for the next one).
PriceFetcher = Callable[[OpenPosition], "Bars | None"]


def build_open_position(
    pitch: Pitch, decision: Decision, opened_at: datetime | None = None, qty: float = 0.0
) -> OpenPosition:
    """Snapshot a funded pitch into an OpenPosition for later resolution.

    The stop fraction is recovered from the pitch's computed ``max_loss``; the
    predicted band is the expected return ± 2 horizon-scaled volatilities — the
    "did reality land near our prediction" window the Critic reads for process.
    """
    capital = pitch.capital_required
    stop_fraction = (pitch.max_loss - pitch.expected_cost) / capital if capital > 0 else 0.0
    stop_fraction = max(0.0, stop_fraction)
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
    )


def _as_utc(ts: datetime) -> datetime:
    return ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts


def resolve_position(
    pos: OpenPosition, bars: Bars, *, now: datetime | None = None
) -> ResolvedOutcome | None:
    """Resolve one open position against a fresh price series, or None if not yet.

    Long-only (the system only opens BUY): realized return is close-to-close from
    the entry bar. Resolves (i.e. signals an EXIT) at the first post-entry close
    that breaches the **stop-loss** (``-stop_fraction``) OR hits the **take-profit**
    (``band_high`` — the top of the predicted move); else at the latest close once
    the **horizon** has elapsed; otherwise it keeps waiting. The caller turns a
    resolution into a real sell.
    """
    df = bars.df
    opened_at = _as_utc(pos.opened_at)
    now = _as_utc(now) if now is not None else _as_utc(bars.last_time)

    times = df["time"]
    closes = df["close"].to_numpy(dtype=float)
    # Entry = the last close at or before the open time.
    entry_mask = [_as_utc(t.to_pydatetime() if hasattr(t, "to_pydatetime") else t) <= opened_at
                  for t in times]
    if not any(entry_mask):
        return None  # series starts after the open — can't price the entry
    entry_idx = max(i for i, m in enumerate(entry_mask) if m)
    entry_price = closes[entry_idx]
    if entry_price <= 0:
        return None

    cost_fraction = pos.cost_cad / pos.size_cad if pos.size_cad > 0 else 0.0

    # Walk post-entry closes; EXIT at the first stop-loss breach (down) or
    # take-profit hit (up). Take-profit = the top of the predicted band.
    take_profit = pos.band_high if pos.band_high and pos.band_high > 0 else None
    for i in range(entry_idx + 1, len(closes)):
        r = closes[i] / entry_price - 1.0
        hit_stop = pos.stop_fraction > 0 and r <= -pos.stop_fraction
        hit_tp = take_profit is not None and r >= take_profit
        if hit_stop or hit_tp:
            resolved_time = times.iloc[i]
            resolved_time = resolved_time.to_pydatetime() if hasattr(resolved_time, "to_pydatetime") else resolved_time
            return _make_outcome(pos, r, cost_fraction, _as_utc(resolved_time))

    # No stop hit — resolve on horizon elapse, otherwise keep waiting.
    elapsed_days = (now - opened_at).total_seconds() / 86400.0
    if elapsed_days < pos.horizon_days:
        return None
    realized = closes[-1] / entry_price - 1.0
    return _make_outcome(pos, realized, cost_fraction, now)


def _make_outcome(
    pos: OpenPosition, realized: float, cost_fraction: float, resolved_at: datetime
) -> ResolvedOutcome:
    net = realized - cost_fraction
    return ResolvedOutcome(
        decision_id=pos.decision_id,
        division=Division(pos.division),
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
            outcome = resolve_position(pos, bars, now=now)
        except Exception:
            repo.audit("resolution_error", {"decision_id": pos.decision_id, "symbol": pos.symbol})
            continue
        if outcome is None:
            continue
        # Execute the real exit before booking the outcome. If the sell fails,
        # keep the position open and don't record a fictional realized P&L.
        if close_live is not None:
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
