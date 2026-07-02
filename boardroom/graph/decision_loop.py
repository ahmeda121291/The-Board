"""The daily decision loop.

End to end (scope §10):
  each division pulls fresh data + computes + pitches/abstains
    -> narrator fills prose -> cost gate (built into the pitch)
    -> risk manager adversarially challenges (vetoes drop the pitch)
    -> CEO ranks survivors against the hurdle & track record -> FUND/FUND_NONE/HOLD
    -> execute (LIVE only behind the flag; stubbed otherwise) -> log everything.

Implemented as a plain ``Orchestrator`` (fully testable, no graph runtime needed)
plus a ``build_decision_graph`` that exposes the same nodes as a LangGraph
StateGraph for the mandated orchestration layer.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from boardroom.agents.ceo import write_rationale
from boardroom.agents.llm import LLM
from boardroom.agents.narrator import narrate_pitch
from boardroom.agents.risk_manager import RiskChallenge, RiskManager
from boardroom.brokers.base import Broker, Order, OrderSide
from boardroom.brokers.stub import StubBroker
from boardroom.ceo.engine import CEODecisionEngine
from boardroom.config import Settings, get_settings
from boardroom.divisions.base import Division
from boardroom.divisions.yield_div import YieldDivision
from boardroom.persistence.repository import Repository, get_repository
from boardroom.schemas import Decision, DecisionKind, Pitch, Venue


#: Quote currencies stripped when mapping a pair symbol to its base asset
#: (SOLUSD/SOLCAD → SOL). Order matters: check longer quotes first.
_QUOTES = ("USDT", "USDC", "CAD", "USD")


def _base_asset(symbol: str) -> str:
    for q in _QUOTES:
        if symbol.endswith(q) and len(symbol) > len(q):
            return symbol[: -len(q)]
    return symbol


@dataclass
class LoopResult:
    decision: Decision
    pitches: list[Pitch]
    ranked: list[Any]
    challenges: dict[str, RiskChallenge]
    fills: list[Any] = field(default_factory=list)
    breakers: list[str] = field(default_factory=list)


@dataclass
class Orchestrator:
    """Owns the divisions, the CEO, the risk manager, brokers, and the repo."""

    divisions: list[Division]
    yield_division: YieldDivision
    settings: Settings = field(default_factory=get_settings)
    repo: Repository = field(default_factory=get_repository)
    llm: LLM = field(default_factory=LLM)
    brokers: dict[Venue, Broker] = field(default_factory=dict)
    risk_manager: RiskManager | None = None
    engine: CEODecisionEngine | None = None
    #: Second key of the two-key live gate. LIVE_TRADING (env) arms the system;
    #: this per-run flag — set only when the CLI was invoked with --confirm-live —
    #: fires it. A real order (buy OR sell) requires BOTH; either alone is a
    #: dry-run, exactly as the docs have always promised.
    confirm_live: bool = False

    @property
    def effective_live(self) -> bool:
        return bool(self.settings.live_trading and self.confirm_live)

    def __post_init__(self) -> None:
        caps = self.settings.caps
        if self.risk_manager is None:
            self.risk_manager = RiskManager(caps=caps, llm=self.llm)
        if self.engine is None:
            # Equity-scaled aggression: a lower bar while the account is small,
            # rising to the conservative bar as it grows. Hard caps unaffected.
            self.engine = CEODecisionEngine(
                caps=caps,
                deviation_threshold=self.settings.ceo_deviation_threshold,
                deviation_threshold_low=self.settings.ceo_deviation_threshold_low,
                aggressive_below_cad=self.settings.aggressive_below_cad,
                conservative_above_cad=self.settings.conservative_above_cad,
                event_cap_pct_small=self.settings.event_hard_cap_pct_small,
                min_order_cad=self.settings.min_order_cad,
            )
        # Default to stub brokers; real Kraken/IBKR are injected at Milestone 6.
        self.brokers.setdefault(Venue.KRAKEN, StubBroker(Venue.KRAKEN))
        self.brokers.setdefault(Venue.IBKR, StubBroker(Venue.IBKR))
        for b in self.brokers.values():
            b.assert_no_withdrawal()

    # ---- nodes ---------------------------------------------------------------
    def gather_pitches(self, bankroll_cad: float) -> list[Pitch]:
        pitches: list[Pitch] = []
        for div in self.divisions:
            for pitch in div.propose_all(bankroll_cad=bankroll_cad):
                pitch = narrate_pitch(pitch, self.llm)
                self.repo.save_pitch(pitch)
                pitches.append(pitch)
        return pitches

    def risk_review(
        self, pitches: list[Pitch], portfolio_value_cad: float = 200.0
    ) -> tuple[list[Pitch], dict[str, RiskChallenge]]:
        survivors: list[Pitch] = []
        challenges: dict[str, RiskChallenge] = {}
        for p in pitches:
            ch = self.risk_manager.challenge(p, portfolio_value_cad)
            challenges[p.pitch_id] = ch
            if ch.approved:
                survivors.append(p)
            else:
                self.repo.audit("risk_veto", {"pitch_id": p.pitch_id, "objections": ch.hard_objections})
        return survivors, challenges

    def settle_and_ratchet(self) -> float:
        """Mark equity to (deposits + realized P&L), run the gains ratchet, persist
        the reserve, and return the INVESTABLE base (equity minus reserve) the caps
        resolve against. The reserve is structurally out of the agents' reach."""
        from boardroom.adaptive.ratchet import RatchetState, investable_cad, ratchet_update

        baseline = self.settings.starting_portfolio_cad
        outcomes = self.repo.recent_outcomes(limit=10000)
        equity = baseline + sum(o.pnl_cad for o in outcomes)
        s = self.repo.get_system_state()
        # HWM never sits below the funded baseline — only gains above it are swept.
        state = RatchetState(
            reserve_cad=s.get("reserve_cad", 0.0),
            hwm_cad=max(s.get("hwm_cad", 0.0), baseline),
        )
        new = ratchet_update(equity_cad=equity, state=state)
        if new.reserve_cad != s.get("reserve_cad", 0.0) or new.hwm_cad != s.get("hwm_cad", 0.0):
            self.repo.set_system_state(new.reserve_cad, new.hwm_cad)
            if new.reserve_cad > s.get("reserve_cad", 0.0):
                self.repo.audit("ratchet", {"reserve_cad": new.reserve_cad, "equity_cad": round(equity, 2)})
        return investable_cad(equity, new.reserve_cad)

    def growth_tier(self, investable_cad: float) -> dict:
        """Measure TOTAL equity (investable + protected reserve, so the ratchet
        never demotes the system) against the deterministic growth ladder.
        Signals only — no trading behavior changes: the payload is audited every
        checkpoint and carried in the session so the trail/dashboard show which
        future capabilities (requires_human) the equity now justifies."""
        from boardroom.adaptive.growth import tier_for, tier_payload

        reserve = self.repo.get_system_state().get("reserve_cad", 0.0) or 0.0
        equity = max(0.0, investable_cad) + max(0.0, reserve)
        payload = tier_payload(tier_for(equity), equity)
        self.repo.audit("growth_tier", payload)
        return payload

    def load_adaptive_state(self) -> None:
        """Hydrate the CEO engine with live calibration posteriors and leashes."""
        from boardroom.adaptive.calibration import CalibrationPosterior

        for div in self.divisions:
            st = self.repo.get_division_state(div.division.value)
            self.engine.posteriors[div.division.value] = CalibrationPosterior(
                division=st.division, alpha=st.alpha, beta=st.beta
            )
            self.engine.leashes[div.division.value] = 0.0 if st.retired else st.leash

    def load_model_params(self) -> None:
        """Apply persisted (re-fit) model coefficients to each division's model.

        A division with no stored params keeps its documented prior. Only known,
        numeric coefficient fields are applied — defensive against schema drift."""
        for div in self.divisions:
            params = self.repo.get_model_params(div.division.value)
            if not params:
                continue
            model = div.model
            for key, value in params.items():
                if hasattr(model, key) and isinstance(value, (int, float)):
                    setattr(model, key, float(value))

    def refit_models(self) -> list:
        """Guardrailed walk-forward re-fit of fittable division models on fresh
        data. Accepted re-fits are persisted and applied to the live model;
        rejected ones leave it untouched. Best-effort and isolated per division."""
        from boardroom.adaptive.refit import refit_directional

        results = []
        for div in self.divisions:
            # A representative series for the (symbol-agnostic) model: the single
            # fetch if set, else the first of the multi-symbol universe.
            fetcher = div.fetch or (div.fetchers[0] if div.fetchers else None)
            if not hasattr(div.model, "fit") or fetcher is None:
                continue
            try:
                bars = fetcher()
                result = refit_directional(div.model, bars)
            except Exception as e:  # noqa: BLE001
                self.repo.audit("refit_error", {"division": div.division.value, "error": str(e)[:120]})
                continue
            if result.accepted:
                self.repo.save_model_params(div.division.value, result.new_coefficients)
            self.repo.audit(
                "refit",
                {
                    "division": div.division.value,
                    "accepted": result.accepted,
                    "reason": result.reason,
                    "n_train": result.n_train,
                    "in_sample": round(result.in_sample_score, 5),
                    "out_of_sample": round(result.out_of_sample_score, 5),
                },
            )
            results.append(result)
        return results

    def decide(
        self,
        pitches: list[Pitch],
        hurdle_rate: float,
        deployed_cad: float,
        portfolio_value_cad: float = 200.0,
    ) -> tuple[Decision, list]:
        decision, ranked = self.engine.decide(
            pitches,
            hurdle_rate=hurdle_rate,
            deployed_cad=deployed_cad,
            portfolio_value_cad=portfolio_value_cad,
        )
        decision.rationale = write_rationale(decision, ranked, self.llm)
        return decision, ranked

    def execute(self, decision: Decision, pitches: list[Pitch]) -> list[Any]:
        fills: list[Any] = []
        if decision.kind != DecisionKind.FUND:
            return fills
        pitch = next((p for p in pitches if p.pitch_id == decision.pitch_id), None)
        if pitch is None:
            return fills
        broker = self.brokers.get(pitch.venue)
        if broker is None:
            return fills
        live = self.effective_live  # two-key gate: LIVE_TRADING AND --confirm-live

        # Equities only fill during the regular session. If we'd go live on an
        # equity venue while the market is closed, hold the leg rather than queue
        # a blind after-hours order. Crypto (Kraken) is 24/7 and unaffected.
        from boardroom.market import equities_session_open, is_equities_venue, session_note

        if live and is_equities_venue(pitch.venue) and not equities_session_open():
            decision.live = False
            self.repo.audit(
                "equity_market_closed",
                {
                    "decision_id": decision.decision_id,
                    "venue": pitch.venue.value,
                    "symbol": pitch.symbol,
                    "reason": session_note(),
                },
            )
            return fills

        order = Order(
            symbol=pitch.symbol,
            side=OrderSide.BUY,
            notional_cad=decision.size_cad,
            division=pitch.division.value,
            client_order_id=str(uuid.uuid4()),
            stop_price=None,
        )
        # A broker rejection (e.g. insufficient funds, no market for the pair,
        # below min order size) must NOT crash the checkpoint — log it and finish
        # so balances/recommendations/portfolio still refresh. No position is
        # recorded when the order didn't go through.
        try:
            fill = broker.place_order(order, live=live)
        except Exception as e:  # noqa: BLE001
            decision.live = False
            self.repo.audit(
                "execute_error",
                {
                    "decision_id": decision.decision_id,
                    "venue": pitch.venue.value,
                    "symbol": pitch.symbol,
                    "size_cad": decision.size_cad,
                    "error": str(e)[:200],
                },
            )
            return fills

        decision.live = fill.is_live
        fills.append(fill)

        # 1. The fill is the record of truth that money moved — persist it FIRST,
        #    with everything needed to reconstruct the trade, before any other
        #    write can fail. (A mid-run crash on 2026-07-01 lost a live BUY's
        #    decision AND position because both were saved after execution.)
        self._record_fill(fill, decision_id=decision.decision_id, notional_cad=decision.size_cad)
        self.repo.audit("execute", {"decision_id": decision.decision_id, "live": fill.is_live})

        # 2. The open position (isolated: a failure here is loudly audited and
        #    must not prevent the decision itself from being saved by run_once).
        from boardroom.graph.resolution_loop import build_open_position

        try:
            self.repo.save_open_position(build_open_position(pitch, decision, qty=fill.filled_qty))
        except Exception as e:  # noqa: BLE001
            self.repo.audit(
                "position_record_error",
                {
                    "decision_id": decision.decision_id,
                    "symbol": pitch.symbol,
                    "size_cad": decision.size_cad,
                    "error": str(e)[:200],
                },
            )
        return fills

    def _record_fill(
        self,
        fill,
        *,
        decision_id: str | None = None,
        exit_reason: str | None = None,
        notional_cad: float | None = None,
    ) -> None:
        """Persist a broker fill into the ``fills`` table. Never raises — but a
        failure is loudly audited, because losing a fill record means the
        dashboard's 'Executed' section lies."""
        order_ref = None
        raw = getattr(fill, "raw", None)
        if isinstance(raw, dict):
            tx = raw.get("txid")
            if isinstance(tx, (list, tuple)) and tx:
                order_ref = str(tx[0])
        row = {
            "run_id": getattr(self, "_run_id", None),
            "decision_id": decision_id,
            "venue": fill.venue.value if hasattr(fill.venue, "value") else str(fill.venue),
            "symbol": fill.symbol,
            "side": fill.side.value if hasattr(fill.side, "value") else str(fill.side),
            "qty": fill.filled_qty,
            "price": fill.avg_price,
            "notional_cad": round(abs(fill.filled_qty * fill.avg_price), 2)
            if fill.filled_qty and fill.avg_price
            else round(notional_cad or 0.0, 2),
            "fee_cad": fill.fee_cad,
            "is_live": fill.is_live,
            "order_ref": order_ref,
            "exit_reason": exit_reason,
        }
        try:
            self.repo.save_fill(row)
        except Exception as e:  # noqa: BLE001
            self.repo.audit(
                "fill_record_error",
                {"symbol": fill.symbol, "side": row["side"], "error": str(e)[:200]},
            )

    def snapshot_balances(self) -> dict:
        """Pull real cash from each venue (we hold the keys here) and persist it
        so the dashboard shows real numbers, not a hardcoded baseline. Best-effort
        per venue — an unauthenticated/unreachable venue is left as None."""
        from boardroom.schemas import Venue

        def _cash(venue) -> float | None:
            broker = self.brokers.get(venue)
            if broker is None or type(broker).__name__ == "StubBroker":
                return None
            try:
                return round(float(broker.get_cash_cad()), 2)
            except Exception:
                return None

        kraken = _cash(Venue.KRAKEN)
        ibkr = _cash(Venue.IBKR)
        equity = None
        if kraken is not None or ibkr is not None:
            equity = round((kraken or 0.0) + (ibkr or 0.0), 2)
        self.repo.set_balances(kraken_cash_cad=kraken, ibkr_cash_cad=ibkr, equity_cad=equity)
        return {"kraken_cash_cad": kraken, "ibkr_cash_cad": ibkr, "equity_cad": equity}

    def generate_recommendations(self, pitches: list[Pitch], hurdle_rate: float):
        """Build the advisory equities recommendation and persist it.

        Stocks are never auto-traded — this turns the advisory equity pitches into
        a target portfolio, reads the user's ACTUAL IBKR holdings (when a real
        gateway is wired; empty otherwise), diffs them, and writes the plain-English
        buy/sell note the dashboard shows. Best-effort: any failure is logged and
        returns None rather than breaking the decision loop.
        """
        from boardroom.agents.advisor import write_discrepancy_note
        from boardroom.recommend import (
            CurrentHolding,
            RecommendationReport,
            build_recommended_portfolio,
            diff_portfolio,
        )
        from boardroom.schemas import utcnow

        broker = self.brokers.get(Venue.IBKR)
        current: list = []
        ibkr_cash: float | None = None
        if broker is not None and type(broker).__name__ != "StubBroker":
            try:
                for r in broker.get_positions():
                    current.append(
                        CurrentHolding(
                            symbol=r.get("symbol", ""),
                            qty=float(r.get("qty", 0.0) or 0.0),
                            avg_cost=float(r.get("avg_cost", 0.0) or 0.0),
                            market_value_cad=float(r.get("market_value_cad", 0.0) or 0.0),
                        )
                    )
            except Exception:
                current = []
            try:
                ibkr_cash = round(float(broker.get_cash_cad()), 2)
            except Exception:
                ibkr_cash = None

        holdings_value = sum(c.market_value_cad for c in current)
        base_cash = ibkr_cash if ibkr_cash is not None else self.settings.starting_portfolio_cad
        stock_equity = round(base_cash + holdings_value, 2)
        # Always size the recommendation against SOMETHING so the ranked target
        # book shows even before the IBKR account is funded — the user asked for
        # "which stocks to buy", not just sizing for cash they already hold.
        if stock_equity <= 0:
            stock_equity = round(self.settings.starting_portfolio_cad, 2)

        recommended = build_recommended_portfolio(
            pitches, hurdle_rate=hurdle_rate, stock_equity_cad=stock_equity, caps=self.settings.caps
        )
        actions = diff_portfolio(current, recommended)
        narrative = write_discrepancy_note(actions, recommended, current, self.llm)
        invested = sum(h.target_weight for h in recommended)
        report = RecommendationReport(
            generated_at=utcnow().isoformat(),
            stock_equity_cad=stock_equity,
            cash_weight=max(0.0, 1.0 - invested),
            holdings=recommended,
            current=current,
            actions=actions,
            narrative=narrative,
            universe_size=len([p for p in pitches if p.venue == Venue.IBKR]),
        )
        self.repo.save_recommendation(report.as_dict())
        return report

    def snapshot_portfolio(self) -> dict | None:
        """Read what's actually held on each venue and persist a full portfolio
        snapshot (crypto coins + stock holdings + cash + performance + merged
        split) for the dashboard. Best-effort per venue; never raises into the
        loop. Returns the snapshot dict, or None on total failure."""
        from boardroom.portfolio import build_portfolio_snapshot
        from boardroom.schemas import utcnow

        def _read(venue):
            broker = self.brokers.get(venue)
            if broker is None or type(broker).__name__ == "StubBroker":
                return None, []
            cash = None
            try:
                cash = round(float(broker.get_cash_cad()), 2)
            except Exception:
                cash = None
            positions: list = []
            try:
                positions = broker.get_positions() or []
            except Exception:
                positions = []
            return cash, positions

        kraken_cash, kraken_pos = _read(Venue.KRAKEN)
        ibkr_cash, ibkr_pos = _read(Venue.IBKR)
        if kraken_cash is None and ibkr_cash is None and not kraken_pos and not ibkr_pos:
            return None  # nothing live to snapshot (e.g. all stubs / offline)

        snapshot = build_portfolio_snapshot(
            generated_at=utcnow().isoformat(),
            kraken_cash_cad=kraken_cash,
            kraken_positions=kraken_pos,
            ibkr_cash_cad=ibkr_cash,
            ibkr_positions=ibkr_pos,
        )
        payload = snapshot.as_dict()
        try:
            self.repo.save_portfolio(payload)
        except Exception as e:  # noqa: BLE001
            self.repo.audit("portfolio_snapshot_error", {"error": str(e)[:160]})
        return payload

    def resolve_positions(self) -> list:
        """Resolve any ready open positions against fresh prices and fold the
        outcomes into calibration/leash/retirement.

        Builds a price cache from the divisions' own fetchers (synthetic offline,
        live when wired), keyed by the actual bars symbol so a position resolves
        against the same series it was opened on. Skipped entirely when nothing is
        open, so a routine HOLD checkpoint does no extra fetching."""
        from boardroom.graph.resolution_loop import resolve_open_positions

        if not self.repo.open_positions():
            return []

        cache: dict[str, Any] = {}
        for d in self.divisions:
            fetchers = d.fetchers or ([d.fetch] if d.fetch else [])
            for fetch in fetchers:
                try:
                    bars = fetch()
                except Exception:
                    continue
                if bars is not None:
                    cache[bars.symbol] = bars

        return resolve_open_positions(
            self.repo, lambda pos: cache.get(pos.symbol), close_live=self._close_position_live
        )

    def _close_position_live(self, pos, outcome) -> bool:
        """Execute the EXIT for a resolved position: sell the held quantity on the
        venue. Returns whether the position is now actually closed.

        - A paper position (never executed live) needs no real sell → closed.
        - A live position is sold for the qty we hold (falling back to its CAD
          notional if the qty wasn't recorded). If the sell can't go live — no
          real broker, or LIVE_TRADING off — we DON'T finalize it (return False),
          so we never book a sale that didn't happen; it retries next checkpoint.
        """
        if not pos.live:
            return True  # paper position — resolve on paper, nothing to sell
        broker = self.brokers.get(Venue(pos.venue))
        if broker is None or type(broker).__name__ == "StubBroker":
            return False
        order = Order(
            symbol=pos.symbol,
            side=OrderSide.SELL,
            notional_cad=pos.size_cad,
            division=pos.division,
            client_order_id=str(uuid.uuid4()),
            base_qty=pos.qty if pos.qty and pos.qty > 0 else None,
        )
        fill = broker.place_order(order, live=self.effective_live)
        if not fill.is_live:
            return False  # dry-run can't close a real live position — keep it open
        # The sell filled — record it before anything else can fail.
        r = outcome.realized_return
        exit_reason = (
            "stop_loss"
            if pos.stop_fraction > 0 and r <= -pos.stop_fraction
            else "take_profit"
            if pos.band_high and pos.band_high > 0 and r >= pos.band_high
            else "horizon"
        )
        self._record_fill(
            fill, decision_id=pos.decision_id, exit_reason=exit_reason, notional_cad=pos.size_cad
        )
        self.repo.audit(
            "exit_executed",
            {
                "decision_id": pos.decision_id,
                "symbol": pos.symbol,
                "qty": round(pos.qty, 8),
                "realized_return": round(outcome.realized_return, 5),
                "pnl_cad": round(outcome.pnl_cad, 2),
            },
        )
        return True

    # ---- the whole loop ------------------------------------------------------
    def run_once(
        self,
        *,
        portfolio_value_cad: float | None = None,
        bankroll_cad: float | None = None,  # deprecated alias for portfolio_value_cad
        deployed_cad: float = 0.0,
        trigger: str = "manual",
    ) -> LoopResult:
        """One checkpoint, wrapped in a durable run record.

        The run row (status running → ok/crashed) is what makes a mid-run crash
        VISIBLE on the dashboard instead of silent. The body itself is ordered
        so the highest-stakes facts persist earliest: fills at execution time,
        then the position, then the decision, then the advisory extras.
        """
        run_id = str(uuid.uuid4())
        self._run_id = run_id
        try:
            self.repo.start_run(run_id, trigger, self.effective_live)
        except Exception:  # noqa: BLE001 — health record must not block the run
            pass
        try:
            result = self._run_once_body(
                run_id,
                portfolio_value_cad=portfolio_value_cad,
                bankroll_cad=bankroll_cad,
                deployed_cad=deployed_cad,
            )
        except BaseException as e:
            try:
                self.repo.finish_run(run_id, status="crashed", error=str(e)[:300])
            except Exception:  # noqa: BLE001
                pass
            raise
        return result

    def _run_once_body(
        self,
        run_id: str,
        *,
        portfolio_value_cad: float | None,
        bankroll_cad: float | None,
        deployed_cad: float,
    ) -> LoopResult:
        portfolio = (
            portfolio_value_cad
            if portfolio_value_cad is not None
            else bankroll_cad
            if bankroll_cad is not None
            else self.settle_and_ratchet()  # live equity minus the protected reserve
        )
        growth = self.growth_tier(portfolio)
        # Resolve matured positions FIRST so today's decision uses the freshest
        # calibration/leashes the just-resolved outcomes produced.
        self.resolve_positions()
        self.load_adaptive_state()
        self.load_model_params()  # apply any persisted walk-forward re-fit
        self.yield_division.refresh_floor()  # live APR if wired; else configured carry
        hurdle_rate = self.yield_division.hurdle_for(horizon_days=1.0)

        # Circuit breakers, evaluated EVERY run: any trip halts all new risk
        # today (the exits above already ran — they reduce risk). The evaluation
        # result is persisted either way, so "breakers clear" on the dashboard
        # means "evaluated and clear", never "never checked".
        breakers = self.check_circuit_breakers(portfolio)
        if breakers:
            decision = Decision(
                decision_id=str(uuid.uuid4()),
                kind=DecisionKind.HOLD,
                hurdle_rate=hurdle_rate,
                rationale=(
                    "Circuit breaker tripped — all new risk halted, capital stays "
                    "in the floor: " + "; ".join(breakers)
                ),
            )
            self.repo.audit("circuit_breaker", {"tripped": breakers})
            session = self._build_session(decision, [], {}, [], hurdle_rate, portfolio, growth=growth)
            session["circuit_breakers"] = breakers
            self.repo.save_decision(decision, session)
            self._finish_run_ok(run_id, decision, breakers, recon=None)
            return LoopResult(decision, [], [], {}, [], breakers)

        pitches = self.gather_pitches(portfolio)
        # Funding rule: ONLY crypto (Kraken) is auto-traded. Every equity (IBKR)
        # pitch is advisory and feeds the recommendation engine instead — so a
        # crypto Momentum breakout can be funded while the same division's stock
        # pitches never are. This is the venue split, enforced here.
        fundable = [p for p in pitches if p.venue == Venue.KRAKEN]
        survivors, challenges = self.risk_review(fundable, portfolio)

        # Per-asset aggregate exposure cap: not a "never rebuy" rule — the CEO
        # may keep adding to a winner until the asset holds ASSET_MAX_EXPOSURE_PCT
        # of the book; past that, its pitches step aside and the next-best idea
        # gets the capital. Prevents one trending coin eating every checkpoint.
        asset_cap_cad = self.settings.asset_max_exposure_pct * max(0.0, portfolio)
        exposure: dict[str, float] = {}
        for pos in self.repo.open_positions():
            a = _base_asset(pos.symbol)
            exposure[a] = exposure.get(a, 0.0) + pos.size_cad
        capped_ids: set[str] = set()
        for p in list(survivors):
            a = _base_asset(p.symbol)
            if exposure.get(a, 0.0) >= asset_cap_cad > 0:
                capped_ids.add(p.pitch_id)
                survivors.remove(p)
                self.repo.audit(
                    "asset_cap_skip",
                    {
                        "pitch_id": p.pitch_id,
                        "symbol": p.symbol,
                        "asset": a,
                        "exposure_cad": round(exposure[a], 2),
                        "cap_cad": round(asset_cap_cad, 2),
                    },
                )

        # Fund up to MAX_FUNDINGS_PER_CHECKPOINT ideas, best-first. Every pick
        # must clear the bar and every cap independently; a funded asset is
        # excluded from the rest of this checkpoint, so the second slot goes to
        # a DIFFERENT coin — diversification instead of winner-take-all.
        max_fund = max(1, int(self.settings.max_fundings_per_checkpoint))
        remaining = list(survivors)
        deployed = deployed_cad
        decisions: list[Decision] = []
        fills: list[Any] = []
        decision, ranked = self.decide(remaining, hurdle_rate, deployed, portfolio)
        session = self._build_session(
            decision, pitches, challenges, ranked, hurdle_rate, portfolio,
            capped_ids=capped_ids, growth=growth,
        )
        # Persist the decision BEFORE execution: open_positions has a foreign key
        # to decisions, so the parent row must exist before the position insert.
        # Then re-save after execution so decision.live reflects the actual fill.
        self.repo.save_decision(decision, session)
        fills += self.execute(decision, pitches)
        self.repo.save_decision(decision, session)
        decisions.append(decision)

        while decisions[-1].kind == DecisionKind.FUND and len(decisions) < max_fund:
            last = decisions[-1]
            deployed += last.size_cad
            funded = next((p for p in pitches if p.pitch_id == last.pitch_id), None)
            funded_asset = _base_asset(funded.symbol) if funded else None
            remaining = [
                p
                for p in remaining
                if p.pitch_id != last.pitch_id and _base_asset(p.symbol) != funded_asset
            ]
            if not remaining:
                break
            extra, extra_ranked = self.decide(remaining, hurdle_rate, deployed, portfolio)
            if extra.kind != DecisionKind.FUND:
                break  # nothing else clears the bar — don't log a noise HOLD row
            extra_session = self._build_session(
                extra, remaining, challenges, extra_ranked, hurdle_rate, portfolio,
                capped_ids=capped_ids,
            )
            extra_session["additional_funding"] = len(decisions) + 1
            self.repo.save_decision(extra, extra_session)
            fills += self.execute(extra, pitches)
            self.repo.save_decision(extra, extra_session)
            decisions.append(extra)

        # Reconcile what the venue actually holds against what we track — the
        # net that catches an orphaned position no matter how it was created.
        recon = self.reconcile_positions()

        # Advisory equities (SUNSET by default — ENABLE_EQUITIES resurrects):
        # publish the recommended stock portfolio + the IBKR diff. Never trades;
        # best-effort so a failure can't affect the (crypto) execution above.
        if self.settings.enable_equities:
            try:
                self.generate_recommendations(pitches, hurdle_rate)
            except Exception as e:  # noqa: BLE001
                self.repo.audit("recommendation_error", {"error": str(e)[:160]})

        # Snapshot what's actually held on each venue (crypto coins + stock
        # holdings + cash + performance) for the dashboard. Best-effort.
        try:
            self.snapshot_portfolio()
        except Exception as e:  # noqa: BLE001
            self.repo.audit("portfolio_snapshot_error", {"error": str(e)[:160]})

        self._finish_run_ok(run_id, decision, [], recon=recon)
        return LoopResult(decision, pitches, ranked, challenges, fills)

    def _finish_run_ok(self, run_id: str, decision: Decision, breakers: list[str], recon) -> None:
        try:
            self.repo.finish_run(
                run_id,
                status="ok",
                decision_id=decision.decision_id,
                decision_kind=decision.kind.value,
                breakers=breakers,
                breakers_evaluated=True,
                recon=recon,
            )
        except Exception:  # noqa: BLE001 — health record must not fail the run
            pass

    def check_circuit_breakers(self, equity_cad: float) -> list[str]:
        """Evaluate daily-loss / drawdown / fee-drag against realized outcomes.
        Non-empty == halt all NEW risk this checkpoint. Pure inputs, pure rule
        (``risk.caps.circuit_breaker_tripped``); this just assembles the state."""
        from datetime import datetime, timezone

        from boardroom.risk.caps import PortfolioState, circuit_breaker_tripped

        outcomes = self.repo.recent_outcomes(limit=10000)
        today = datetime.now(timezone.utc).date()
        pnl_today = sum(
            o.pnl_cad - o.cost_cad for o in outcomes if o.resolved_at.date() == today
        )
        s = self.repo.get_system_state()
        peak = max(s.get("hwm_cad", 0.0) or 0.0, self.settings.starting_portfolio_cad)
        state = PortfolioState(
            equity_cad=equity_cad,
            peak_equity_cad=peak,
            realized_pnl_today_cad=pnl_today,
            cumulative_cost_cad=sum(o.cost_cad for o in outcomes),
            cumulative_gross_return_cad=sum(max(0.0, o.pnl_cad) for o in outcomes),
        )
        return circuit_breaker_tripped(state, self.settings.caps)

    def reconcile_positions(self) -> dict | None:
        """Compare the coins Kraken actually holds against tracked open positions.

        Any asset held on the venue with no tracked position is an ORPHAN — money
        the auto-sell loop would never manage (it happened on 2026-07-01 when a
        crash lost a filled BUY's position row). Result is persisted on the run
        row and surfaced on the dashboard. Best-effort, never raises.
        """
        from datetime import datetime, timezone

        broker = self.brokers.get(Venue.KRAKEN)
        if broker is None or type(broker).__name__ == "StubBroker":
            return None
        try:
            held = broker.get_positions()  # [{symbol, qty, market_value_cad, ...}]
        except Exception:  # noqa: BLE001
            return None

        tracked: dict[str, float] = {}
        for pos in self.repo.open_positions():
            if pos.venue != "kraken":
                continue
            base = _base_asset(pos.symbol)
            tracked[base] = tracked.get(base, 0.0) + (pos.qty or 0.0)

        untracked = []
        for h in held or []:
            sym = h.get("symbol", "")
            qty = float(h.get("qty", 0.0) or 0.0)
            if qty <= 1e-8:
                continue
            if sym not in tracked:
                untracked.append(
                    {"asset": sym, "qty": qty, "market_value_cad": h.get("market_value_cad")}
                )

        recon = {
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "held": [
                {"asset": h.get("symbol"), "qty": h.get("qty"), "market_value_cad": h.get("market_value_cad")}
                for h in (held or [])
            ],
            "tracked_assets": sorted(tracked),
            "untracked": untracked,
        }
        if untracked:
            self.repo.audit("reconciliation_untracked", {"untracked": untracked})
        return recon

    def _build_session(
        self, decision, pitches, challenges, ranked, hurdle_rate, portfolio,
        capped_ids: set[str] | None = None, growth: dict | None = None,
    ) -> dict:
        """The full boardroom session — every division's status, what it pitched,
        the risk manager's verdict, and the CEO's ranking + reason. This is the
        narrative the dashboard renders."""
        ranked_by_id = {r.pitch.pitch_id: r for r in ranked}
        capped_ids = capped_ids or set()

        pitch_rows = []
        for p in pitches:
            ch = challenges.get(p.pitch_id)
            r = ranked_by_id.get(p.pitch_id)
            # Equities (IBKR) are advisory — recommendation only, never funded.
            if p.venue != Venue.KRAKEN:
                status, reason = "shadow", "advisory — feeds the recommended portfolio, not auto-traded"
            elif decision.pitch_id == p.pitch_id and decision.kind.value == "fund":
                status, reason = "funded", "CEO funded — best risk-adjusted edge over the floor"
            elif p.pitch_id in capped_ids:
                status, reason = (
                    "passed",
                    "asset exposure cap reached — already holding the max share of "
                    "this coin; capital goes to the next-best idea instead",
                )
            elif ch is not None and not ch.approved:
                status, reason = "vetoed", "; ".join(ch.hard_objections) or "risk manager veto"
            elif r is not None and r.rejected_reason:
                status, reason = "passed", r.rejected_reason
            else:
                status, reason = "passed", "ranked below the deviation threshold (floor wins)"
            pitch_rows.append(
                {
                    "pitch_id": p.pitch_id,
                    "division": p.division.value,
                    "symbol": p.symbol,
                    "venue": p.venue.value,
                    "expected_return": p.expected_return,
                    "confidence": p.confidence,
                    "capital_required": p.capital_required,
                    "max_loss": p.max_loss,
                    "expected_cost": p.expected_cost,
                    "horizon_days": p.time_horizon_days,
                    "opportunity": p.opportunity,
                    "why_now": p.why_now,
                    "features": p.signals.features,
                    "news": p.signals.news,
                    "risk_approved": (ch.approved if ch else None),
                    "risk_objections": (ch.hard_objections if ch else []),
                    "risk_concern": (ch.qualitative_concern if ch else ""),
                    "ceo_score": (r.score if r else None),
                    "ceo_trust": (r.trust if r else None),
                    "ceo_size_cad": (r.trusted_size_cad if r else None),
                    "status": status,
                    "reason": reason,
                }
            )

        self.yield_division.last_status = (
            f"floor — resting state · carry {self.yield_division.carry_apr:.1%} APR"
        )
        division_rows = [
            {"division": d.division.value, "status": getattr(d, "last_status", "idle")}
            for d in [self.yield_division, *self.divisions]
        ]
        universe = {}
        for d in self.divisions:
            syms = getattr(d, "universe_symbols", None)
            if syms:
                universe[d.division.value] = {"venue": d.venue.value, "symbols": list(syms)}
        return {
            "hurdle_rate": hurdle_rate,
            "portfolio_value_cad": portfolio,
            "growth_tier": growth,
            "pitches": pitch_rows,
            "divisions": division_rows,
            "universe": universe,
        }


def build_decision_graph(orch: Orchestrator):
    """Expose the orchestrator's nodes as a LangGraph StateGraph.

    Same logic as ``run_once``; this is the mandated LangGraph wiring with
    explicit control over who runs when (scope §12). Imported lazily so the core
    package does not hard-depend on langgraph for tests.
    """
    from langgraph.graph import END, START, StateGraph

    def _pv(state: dict) -> float:
        return state.get("portfolio_value_cad", state.get("bankroll_cad", 200.0))

    def n_gather(state: dict) -> dict:
        state["growth_tier"] = orch.growth_tier(_pv(state))
        orch.resolve_positions()
        orch.load_adaptive_state()
        orch.load_model_params()
        orch.yield_division.refresh_floor()
        state["hurdle_rate"] = orch.yield_division.hurdle_for(1.0)
        state["pitches"] = orch.gather_pitches(_pv(state))
        return state

    def n_risk(state: dict) -> dict:
        survivors, challenges = orch.risk_review(state["pitches"], _pv(state))
        state["survivors"] = survivors
        state["challenges"] = challenges
        return state

    def n_decide(state: dict) -> dict:
        decision, ranked = orch.decide(
            state["survivors"], state["hurdle_rate"], state.get("deployed_cad", 0.0), _pv(state)
        )
        state["decision"] = decision
        state["ranked"] = ranked
        return state

    def n_execute(state: dict) -> dict:
        state["fills"] = orch.execute(state["decision"], state["pitches"])
        return state

    g = StateGraph(dict)
    g.add_node("gather", n_gather)
    g.add_node("risk", n_risk)
    g.add_node("decide", n_decide)
    g.add_node("execute", n_execute)
    g.add_edge(START, "gather")
    g.add_edge("gather", "risk")
    g.add_edge("risk", "decide")
    g.add_edge("decide", "execute")
    g.add_edge("execute", END)
    return g.compile()
