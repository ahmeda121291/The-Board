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

    def risk_review(self, pitches: list[Pitch]) -> tuple[list[Pitch], dict[str, RiskChallenge]]:
        survivors: list[Pitch] = []
        challenges: dict[str, RiskChallenge] = {}
        for p in pitches:
            ch = self.risk_manager.challenge(p)
            challenges[p.pitch_id] = ch
            if ch.approved:
                survivors.append(p)
            else:
                self.repo.audit("risk_veto", {"pitch_id": p.pitch_id, "objections": ch.hard_objections})
        return survivors, challenges

    def load_adaptive_state(self) -> None:
        """Hydrate the CEO engine with live calibration posteriors and leashes."""
        from boardroom.adaptive.calibration import CalibrationPosterior

        for div in self.divisions:
            st = self.repo.get_division_state(div.division.value)
            self.engine.posteriors[div.division.value] = CalibrationPosterior(
                division=st.division, alpha=st.alpha, beta=st.beta
            )
            self.engine.leashes[div.division.value] = 0.0 if st.retired else st.leash

    def decide(self, pitches: list[Pitch], hurdle_rate: float, deployed_cad: float) -> tuple[Decision, list]:
        decision, ranked = self.engine.decide(
            pitches, hurdle_rate=hurdle_rate, deployed_cad=deployed_cad
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
        return fills

    # ---- the whole loop ------------------------------------------------------
    def run_once(self, *, bankroll_cad: float | None = None, deployed_cad: float = 0.0) -> LoopResult:
        bankroll = bankroll_cad if bankroll_cad is not None else self.settings.total_deployable_cad
        self.load_adaptive_state()
        hurdle_rate = self.yield_division.hurdle_for(horizon_days=1.0)

        pitches = self.gather_pitches(bankroll)
        survivors, challenges = self.risk_review(pitches)
        decision, ranked = self.decide(survivors, hurdle_rate, deployed_cad)

        ranking_payload = [
            {
                "pitch_id": r.pitch.pitch_id,
                "division": r.pitch.division.value,
                "score": r.score,
                "trust": r.trust,
                "trusted_size_cad": r.trusted_size_cad,
                "rejected_reason": r.rejected_reason,
            }
            for r in ranked
        ]
        self.repo.save_decision(decision, ranking_payload)
        fills = self.execute(decision, pitches)
        return LoopResult(decision, pitches, ranked, challenges, fills)


def build_decision_graph(orch: Orchestrator):
    """Expose the orchestrator's nodes as a LangGraph StateGraph.

    Same logic as ``run_once``; this is the mandated LangGraph wiring with
    explicit control over who runs when (scope §12). Imported lazily so the core
    package does not hard-depend on langgraph for tests.
    """
    from langgraph.graph import END, START, StateGraph

    def n_gather(state: dict) -> dict:
        orch.load_adaptive_state()
        state["hurdle_rate"] = orch.yield_division.hurdle_for(1.0)
        state["pitches"] = orch.gather_pitches(state["bankroll_cad"])
        return state

    def n_risk(state: dict) -> dict:
        survivors, challenges = orch.risk_review(state["pitches"])
        state["survivors"] = survivors
        state["challenges"] = challenges
        return state

    def n_decide(state: dict) -> dict:
        decision, ranked = orch.decide(
            state["survivors"], state["hurdle_rate"], state.get("deployed_cad", 0.0)
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
