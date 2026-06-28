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


@dataclass
class LoopResult:
    decision: Decision
    pitches: list[Pitch]
    ranked: list[Any]
    challenges: dict[str, RiskChallenge]
    fills: list[Any] = field(default_factory=list)


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

    def __post_init__(self) -> None:
        caps = self.settings.caps
        if self.risk_manager is None:
            self.risk_manager = RiskManager(caps=caps, llm=self.llm)
        if self.engine is None:
            self.engine = CEODecisionEngine(caps=caps)
        # Default to stub brokers; real Kraken/IBKR are injected at Milestone 6.
        self.brokers.setdefault(Venue.KRAKEN, StubBroker(Venue.KRAKEN))
        self.brokers.setdefault(Venue.IBKR, StubBroker(Venue.IBKR))
        for b in self.brokers.values():
            b.assert_no_withdrawal()

    # ---- nodes ---------------------------------------------------------------
    def gather_pitches(self, bankroll_cad: float) -> list[Pitch]:
        pitches: list[Pitch] = []
        for div in self.divisions:
            pitch = div.propose(bankroll_cad=bankroll_cad)
            if pitch is None:
                continue
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
            if not hasattr(div.model, "fit") or div.fetch is None:
                continue
            try:
                bars = div.fetch()
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
        live = self.settings.live_trading  # the hard gate

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
        fill = broker.place_order(order, live=live)
        decision.live = fill.is_live
        fills.append(fill)
        self.repo.audit("execute", {"decision_id": decision.decision_id, "live": fill.is_live})

        # Record the open position so it can be resolved (paper or live) at a
        # later checkpoint and fed back into the adaptive engine.
        from boardroom.graph.resolution_loop import build_open_position

        self.repo.save_open_position(build_open_position(pitch, decision))
        return fills

    def resolve_positions(self) -> list:
        """Resolve any ready open positions against fresh prices and fold the
        outcomes into calibration/leash/retirement. Reuses each division's own
        fetcher (synthetic offline, live when wired)."""
        from boardroom.graph.resolution_loop import resolve_open_positions

        div_by_name = {d.division.value: d for d in self.divisions}

        def fetch_for(pos):
            d = div_by_name.get(pos.division)
            if d is None or d.fetch is None:
                return None
            return d.fetch()

        return resolve_open_positions(self.repo, fetch_for)

    # ---- the whole loop ------------------------------------------------------
    def run_once(
        self,
        *,
        portfolio_value_cad: float | None = None,
        bankroll_cad: float | None = None,  # deprecated alias for portfolio_value_cad
        deployed_cad: float = 0.0,
    ) -> LoopResult:
        portfolio = (
            portfolio_value_cad
            if portfolio_value_cad is not None
            else bankroll_cad
            if bankroll_cad is not None
            else self.settle_and_ratchet()  # live equity minus the protected reserve
        )
        # Resolve matured positions FIRST so today's decision uses the freshest
        # calibration/leashes the just-resolved outcomes produced.
        self.resolve_positions()
        self.load_adaptive_state()
        self.load_model_params()  # apply any persisted walk-forward re-fit
        self.yield_division.refresh_floor()  # live APR if wired; else configured carry
        hurdle_rate = self.yield_division.hurdle_for(horizon_days=1.0)

        pitches = self.gather_pitches(portfolio)
        survivors, challenges = self.risk_review(pitches, portfolio)
        decision, ranked = self.decide(survivors, hurdle_rate, deployed_cad, portfolio)

        session = self._build_session(decision, pitches, challenges, ranked, hurdle_rate, portfolio)
        self.repo.save_decision(decision, session)
        fills = self.execute(decision, pitches)
        return LoopResult(decision, pitches, ranked, challenges, fills)

    def _build_session(self, decision, pitches, challenges, ranked, hurdle_rate, portfolio) -> dict:
        """The full boardroom session — every division's status, what it pitched,
        the risk manager's verdict, and the CEO's ranking + reason. This is the
        narrative the dashboard renders."""
        ranked_by_id = {r.pitch.pitch_id: r for r in ranked}

        pitch_rows = []
        for p in pitches:
            ch = challenges.get(p.pitch_id)
            r = ranked_by_id.get(p.pitch_id)
            if decision.pitch_id == p.pitch_id and decision.kind.value == "fund":
                status, reason = "funded", "CEO funded — best risk-adjusted edge over the floor"
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
        return {
            "hurdle_rate": hurdle_rate,
            "portfolio_value_cad": portfolio,
            "pitches": pitch_rows,
            "divisions": division_rows,
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
