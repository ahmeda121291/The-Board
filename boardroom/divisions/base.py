"""Division base — the pitch-or-abstain machinery shared by all divisions.

The flow is the grounding rule made concrete (scope §5):
    fetch real data -> snapshot (freshness/sanity) -> model.predict ->
    deterministic sizing/risk/cost -> Pitch with COMPUTED fields and EMPTY
    narrative. If data is stale/insane or the model has no edge -> return None.
"""

from __future__ import annotations

import abc
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from boardroom.data.snapshot import Bars, SanityError, build_snapshot
from boardroom.models.base import ModelOutput, PredictionModel
from boardroom.risk.cost import CostModel
from boardroom.schemas import ComputedSignals, Division as DivisionEnum, Pitch, Venue


@dataclass
class Division(abc.ABC):
    """Abstract division. Subclasses set the enum, venue, model, and stop logic."""

    division: DivisionEnum
    venue: Venue
    model: PredictionModel
    fetch: Callable[[], Bars] | None = None  # real data source; None -> needs injected bars
    fetchers: list[Callable[[], Bars]] | None = None  # multi-symbol universe; one pitch each
    universe_symbols: list[str] = field(default_factory=list)  # display names of the scanned set
    #: Advisory divisions pitch and log but are NEVER funded with real capital —
    #: a safe way to validate a new strategy on live data before it can trade.
    advisory: bool = False
    enabled: bool = True
    max_age_seconds: float = 60 * 60 * 36  # daily bars: ~1.5 days tolerance
    min_rows: int = 40
    min_stop_fraction: float = 0.01
    stop_vol_multiple: float = 2.0
    cost_model: CostModel = field(default_factory=CostModel)
    #: Human-readable outcome of the last propose() — for the boardroom session
    #: feed (why a division abstained or what it pitched).
    last_status: str = "idle"

    # ---- subclass hooks ------------------------------------------------------
    def needs_fx(self) -> bool:
        """True if the trade crosses CAD<->USD (IBKR USD names, USD crypto pairs)."""
        return self.venue == Venue.IBKR

    def venue_for(self, bars: Bars) -> Venue:
        """Execution venue for a pitch. Default = the division's venue; an
        asset-agnostic division (Momentum scans stocks AND crypto) overrides this
        to route per symbol off the data source."""
        return self.venue

    def enrich(self, pitch: Pitch, bars: Bars) -> Pitch:
        """Hook to add context to a freshly-built pitch (only called when the
        division actually pitches). Default no-op; Momentum overrides it to attach
        catalyst news. Runs after the quant fields are fixed, so it never changes
        the numbers the system acts on."""
        return pitch

    def stop_fraction(self, output: ModelOutput) -> float:
        """Fractional loss if the stop is hit — grounds max_loss in real volatility."""
        vol = output.features.get("volatility", 0.0)
        return max(self.min_stop_fraction, vol * self.stop_vol_multiple)

    def base_size_cad(self, output: ModelOutput, bankroll_cad: float) -> float:
        """The division's own sizing request (CEO re-sizes authoritatively).

        A timid fraction of bankroll scaled by confidence — the division proposes,
        the CEO disposes.
        """
        conf = output.raw_confidence
        return round(max(0.0, conf) * 0.15 * bankroll_cad, 2)

    # ---- the public entry point ---------------------------------------------
    def propose_all(self, *, bankroll_cad: float = 200.0) -> list[Pitch]:
        """Scan the division's whole universe; return one Pitch per qualifying symbol.

        Uses ``self.fetchers`` (the multi-symbol universe) when set, else falls back
        to the single ``fetch``. The CEO then ranks across everything returned and
        funds at most the single best. More symbols = more chances something clears
        the floor after cost — the same grounding rules apply per symbol.
        """
        if not self.enabled:
            self.last_status = "disabled"
            return []
        fetchers = self.fetchers or ([self.fetch] if self.fetch else [])
        if not fetchers:
            return [p for p in [self.propose(bankroll_cad=bankroll_cad)] if p is not None]

        # Fetch every symbol's bars concurrently — the slow part is network I/O,
        # so this turns ~N sequential round-trips into a few parallel rounds.
        from concurrent.futures import ThreadPoolExecutor

        def _safe_fetch(f):
            try:
                return f()
            except Exception:
                return None  # dead/slow symbol -> abstain, never blocks the others

        with ThreadPoolExecutor(max_workers=min(8, len(fetchers))) as ex:
            all_bars = list(ex.map(_safe_fetch, fetchers))

        pitches: list[Pitch] = []
        last_reason = "abstained — no edge / trigger not fired"
        for bars in all_bars:
            if bars is None:
                last_reason = "abstained — data feed unavailable"
                continue
            p = self.propose(bars=bars, bankroll_cad=bankroll_cad)
            if p is not None:
                pitches.append(p)
            else:
                last_reason = self.last_status
        self.last_status = (
            f"pitched {len(pitches)} of {len(fetchers)} scanned"
            if pitches
            else f"{last_reason} (scanned {len(fetchers)})"
        )
        return pitches

    def propose(
        self,
        *,
        bars: Bars | None = None,
        bankroll_cad: float = 200.0,
        fetch: Callable[[], Bars] | None = None,
    ) -> Pitch | None:
        """Produce a computed Pitch, or None to abstain (recording why).

        ``fetch`` overrides the division's default source (used by ``propose_all``
        to scan each symbol in the universe).
        """
        if not self.enabled:
            self.last_status = "disabled"
            return None

        source = fetch or self.fetch
        try:
            bars = bars if bars is not None else (source() if source else None)
        except Exception as e:
            self.last_status = f"abstained — data feed unavailable ({str(e)[:90]})"
            return None  # any data failure -> abstain (no trade on garbage)
        if bars is None:
            self.last_status = "abstained — no data"
            return None

        try:
            snapshot = build_snapshot(
                bars, max_age_seconds=self.max_age_seconds, min_rows=self.min_rows
            )
        except SanityError as e:
            self.last_status = f"abstained — data failed sanity checks ({e})"
            return None
        if not snapshot.is_fresh:
            self.last_status = f"abstained — stale data ({snapshot.age_seconds / 3600:.0f}h old)"
            return None  # stale data -> abstain

        output = self.model.predict(bars)
        if output.raw_confidence <= 0.0:
            self.last_status = "abstained — no edge / trigger not fired"
            return None  # no edge / sentinel not fired -> abstain

        capital = self.base_size_cad(output, bankroll_cad)
        if capital <= 0.0:
            self.last_status = "abstained — computed size rounds to zero"
            return None

        venue = self.venue_for(bars)
        stop_frac = self.stop_fraction(output)
        cost = self.cost_model.round_trip_cost_cad(
            venue=venue, notional_cad=capital, needs_fx=self.needs_fx()
        )
        max_loss = round(capital * stop_frac + cost, 2)

        # Stamp the reference (entry) price the decision was computed on, so the
        # dashboard can show "buying at $X, we value it at $Y" without recomputing.
        signals = ComputedSignals(
            features={**output.features, "price": float(bars.closes[-1])},
            model_name=output.model_name,
            model_version=output.model_version,
            expected_return=output.expected_return,
            win_probability=output.win_probability,
            raw_confidence=output.raw_confidence,
            horizon_days=output.horizon_days,
        )

        self.last_status = "pitched"
        pitch = Pitch(
            pitch_id=str(uuid.uuid4()),
            division=self.division,
            venue=venue,
            symbol=bars.symbol,
            snapshot=snapshot,
            signals=signals,
            capital_required=capital,
            expected_return=output.expected_return,
            confidence=output.win_probability,
            time_horizon_days=output.horizon_days,
            max_loss=max_loss,
            expected_cost=round(cost, 2),
            opportunity="",  # narrative filled by the LLM narrator, never here
            why_now="",
        )
        return self.enrich(pitch, bars)
