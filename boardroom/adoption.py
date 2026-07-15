"""Adopt or flatten UNTRACKED venue holdings.

The daily reconciliation (``Orchestrator.reconcile_positions``) compares what
Kraken actually holds against the tracked open positions and flags any orphan —
a coin sitting on the venue that the auto-sell engine is not managing. Orphans
are the residue of a crashed run (2026-07-01) or of a buy made on the exchange
outside the system entirely. The dashboard alert said "adopt or sell manually",
but no code path existed for either; this module is that path, driven by
``boardroom adopt``:

  * :func:`adopt_untracked` — bring the orphan under management: a synthetic
    FUND decision + a live OpenPosition for the real quantity held, so the
    resolution loop prices it every checkpoint and the auto-sell engine exits
    it on its stop / horizon exactly like any funded position.
  * :func:`sell_untracked` — flatten the orphan now with a market sell, behind
    the same two-key live gate as every other real order.

Every number recorded here is deterministic from real data (venue balance,
live ticker) or operator-supplied parameters — the LLM is nowhere near this.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from boardroom.brokers.base import Broker, Fill, Order, OrderSide
from boardroom.persistence.repository import OpenPosition, Repository
from boardroom.schemas import Decision, DecisionKind, Division, Venue

#: Kraken taker fee — the exit leg an adopted position still has to pay,
#: matching the fee model used everywhere else in the execution layer.
TAKER_FEE = 0.0026

#: Deterministic exit parameters for an adopted position (overridable per call
#: from the CLI). Aligned with the trading models: horizons run 3–5 days and
#: stops are volatility-scaled; without the entry-time volatility a flat 15%
#: stop is the conservative "don't ride an orphan into the ground" backstop.
DEFAULT_STOP_FRACTION = 0.15
DEFAULT_HORIZON_DAYS = 3.0


def find_untracked(held: list[dict] | None, tracked_assets) -> list[dict]:
    """Venue holdings with no tracked open position behind them. Pure.

    ``held`` is ``broker.get_positions()`` output (``{symbol, qty,
    market_value_cad}`` per coin); ``tracked_assets`` is any container of the
    base assets open positions cover. Shared by the checkpoint reconciliation
    and the ``boardroom adopt`` command so both always agree on what an
    orphan is.
    """
    orphans: list[dict] = []
    for h in held or []:
        sym = h.get("symbol", "")
        qty = float(h.get("qty", 0.0) or 0.0)
        if qty <= 1e-8:
            continue  # dust / zero
        if sym not in tracked_assets:
            orphans.append(
                {"asset": sym, "qty": qty, "market_value_cad": h.get("market_value_cad")}
            )
    return orphans


def untracked_holdings(repo: Repository, broker: Broker) -> list[dict]:
    """The orphans on ``broker``'s venue right now: real holdings minus the
    base assets covered by tracked open positions."""
    from boardroom.graph.decision_loop import _base_asset

    held = broker.get_positions()
    tracked = {
        _base_asset(p.symbol)
        for p in repo.open_positions()
        if p.venue == broker.venue.value
    }
    return find_untracked(held, tracked)


def build_adoption(
    asset: str,
    qty: float,
    market_value_cad: float,
    *,
    stop_fraction: float,
    horizon_days: float,
    now: datetime | None = None,
) -> tuple[Decision, OpenPosition]:
    """Deterministic Decision + OpenPosition for an orphaned holding.

    The entry basis is ADOPTION time: resolution recovers the entry price from
    the bars at/just before ``opened_at``, so the stop and P&L measure from the
    moment the system took responsibility — not from the unknown original buy.
    The symbol is the USD analysis pair (deep history universe); execution
    still translates to the account's quote currency at order time.
    """
    now = now or datetime.now(timezone.utc)
    decision_id = str(uuid.uuid4())
    decision = Decision(
        decision_id=decision_id,
        created_at=now,
        kind=DecisionKind.FUND,
        division=Division.CRYPTO_TREND,
        pitch_id=None,
        size_cad=round(market_value_cad, 2),
        hurdle_rate=0.0,
        rationale=(
            f"ADOPTED untracked venue holding: {qty:.8f} {asset} "
            f"(~{market_value_cad:.2f} CAD) sat on Kraken with no tracked position "
            f"behind it (venue reconciliation). Now under management: the auto-sell "
            f"engine exits on a {stop_fraction:.0%} stop or after {horizon_days:g} "
            f"day(s), like any funded position. P&L measures from adoption, not "
            f"from the original (unrecorded) buy."
        ),
        live=True,
    )
    position = OpenPosition(
        decision_id=decision_id,
        division=Division.CRYPTO_TREND.value,
        venue=Venue.KRAKEN.value,
        symbol=f"{asset}USD",
        size_cad=round(market_value_cad, 2),
        predicted_return=0.0,  # no model made a claim — a neutral prior
        predicted_confidence=0.5,
        cost_cad=round(market_value_cad * TAKER_FEE, 2),  # the exit leg's taker fee
        stop_fraction=stop_fraction,
        band_low=0.0,
        band_high=0.0,  # no take-profit — the stop and the horizon manage it
        horizon_days=horizon_days,
        opened_at=now,
        live=True,  # it IS real money on the venue — exits must really sell
        qty=round(qty, 8),
    )
    return decision, position


def adopt_untracked(
    repo: Repository,
    broker: Broker,
    asset: str,
    *,
    stop_fraction: float = DEFAULT_STOP_FRACTION,
    horizon_days: float = DEFAULT_HORIZON_DAYS,
    now: datetime | None = None,
) -> OpenPosition:
    """Adopt one orphaned holding into a tracked, auto-managed position.

    Refuses (ValueError) when the asset isn't an orphan on the venue or has no
    live market value — an adopted position the loop can't value would never
    exit, which is worse than staying loudly untracked.
    """
    if not 0.0 < stop_fraction < 1.0:
        raise ValueError(f"stop_fraction must be in (0, 1), got {stop_fraction}")
    if horizon_days <= 0:
        raise ValueError(f"horizon_days must be positive, got {horizon_days}")
    orphans = {o["asset"]: o for o in untracked_holdings(repo, broker)}
    if asset not in orphans:
        have = ", ".join(sorted(orphans)) or "none"
        raise ValueError(
            f"{asset} is not an untracked holding on the venue (untracked right now: {have})"
        )
    orphan = orphans[asset]
    value = orphan.get("market_value_cad")
    if not value or value <= 0:
        raise ValueError(
            f"{asset} has no live market value — cannot set a deterministic entry "
            f"basis (no priceable market for it right now)"
        )
    decision, position = build_adoption(
        asset,
        orphan["qty"],
        float(value),
        stop_fraction=stop_fraction,
        horizon_days=horizon_days,
        now=now,
    )
    # FK parent FIRST, then the position — the 2026-07-01 ordering lesson.
    repo.save_decision(decision, [])
    repo.save_open_position(position)
    repo.audit(
        "position_adopted",
        {
            "asset": asset,
            "symbol": position.symbol,
            "qty": position.qty,
            "market_value_cad": round(float(value), 2),
            "decision_id": decision.decision_id,
            "stop_fraction": stop_fraction,
            "horizon_days": horizon_days,
        },
    )
    return position


def sell_untracked(repo: Repository, broker: Broker, asset: str, *, live: bool) -> Fill:
    """Market-sell one orphaned holding for its full quantity.

    ``live`` must already have passed the two-key gate (LIVE_TRADING AND
    --confirm-live); this refuses to run otherwise — a paper sell of real
    money on the venue would be a fiction. If the broker still declines to go
    live (e.g. credentials missing), nothing is recorded and it raises.
    """
    if not live:
        raise RuntimeError(
            "selling an untracked holding requires the live gate "
            "(LIVE_TRADING=true AND --confirm-live) — nothing was sold"
        )
    orphans = {o["asset"]: o for o in untracked_holdings(repo, broker)}
    if asset not in orphans:
        have = ", ".join(sorted(orphans)) or "none"
        raise ValueError(
            f"{asset} is not an untracked holding on the venue (untracked right now: {have})"
        )
    orphan = orphans[asset]
    order = Order(
        symbol=f"{asset}USD",
        side=OrderSide.SELL,
        notional_cad=float(orphan.get("market_value_cad") or 0.0),
        division=Division.CRYPTO_TREND.value,
        client_order_id=str(uuid.uuid4()),
        base_qty=orphan["qty"],  # sell exactly what the venue holds
    )
    fill = broker.place_order(order, live=True)
    if not fill.is_live:
        raise RuntimeError(
            "the venue refused to go live (missing credentials or LIVE_TRADING "
            "off at the broker layer) — nothing was sold, nothing recorded"
        )
    # The fill is the record of truth that money moved — persist it before
    # anything else can fail (mirrors the execution layer's ordering).
    order_ref = None
    raw = getattr(fill, "raw", None)
    if isinstance(raw, dict):
        tx = raw.get("txid")
        if isinstance(tx, (list, tuple)) and tx:
            order_ref = str(tx[0])
    repo.save_fill(
        {
            "run_id": None,
            "decision_id": None,  # nothing decided this buy — that's the point
            "venue": fill.venue.value if hasattr(fill.venue, "value") else str(fill.venue),
            "symbol": fill.symbol,
            "side": "sell",
            "qty": fill.filled_qty,
            "price": fill.avg_price,
            "notional_cad": round(abs(fill.filled_qty * fill.avg_price), 2)
            if fill.filled_qty and fill.avg_price
            else round(order.notional_cad, 2),
            "fee_cad": fill.fee_cad,
            "is_live": fill.is_live,
            "order_ref": order_ref,
            "exit_reason": "untracked_sell",
        }
    )
    repo.audit(
        "untracked_sold",
        {
            "asset": asset,
            "qty": orphan["qty"],
            "market_value_cad": orphan.get("market_value_cad"),
            "order_ref": order_ref,
        },
    )
    return fill
