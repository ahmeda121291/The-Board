"""Repository interface + an in-memory implementation.

The Supabase-backed implementation lives in ``supabase_repo`` and is selected by
``get_repository()`` when SUPABASE_URL/SERVICE_KEY are set. Both share this
interface so the rest of the system never knows which is in play.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import datetime

from boardroom.config import get_settings
from boardroom.schemas import Decision, Pitch, ResolvedOutcome


@dataclass
class DivisionState:
    """Live adaptive state for one division (mirrors the ``division_state`` table)."""

    division: str
    alpha: float = 1.0          # Beta posterior
    beta: float = 1.0
    leash: float = 1.0          # risk leash in [0, 1]
    retired: bool = False       # leash forced to zero, benched
    shadow: bool = False        # computes pitches but gets no real capital
    n_resolved: int = 0
    net_vs_floor_cad: float = 0.0


@dataclass
class OpenPosition:
    """A funded position awaiting resolution (mirrors the ``open_positions`` table).

    Everything needed to score the decision later from the price series alone:
    the entry price is recovered by timestamp at resolution, so dry-run (paper)
    and live positions resolve identically off real market data.
    """

    decision_id: str
    division: str
    venue: str
    symbol: str
    size_cad: float
    predicted_return: float
    predicted_confidence: float
    cost_cad: float
    stop_fraction: float
    band_low: float
    band_high: float
    horizon_days: float
    opened_at: datetime
    live: bool = False


class Repository(abc.ABC):
    @abc.abstractmethod
    def save_pitch(self, pitch: Pitch) -> None: ...

    @abc.abstractmethod
    def save_decision(self, decision: Decision, ranking: list[dict]) -> None: ...

    @abc.abstractmethod
    def save_outcome(self, outcome: ResolvedOutcome) -> None: ...

    @abc.abstractmethod
    def get_division_state(self, division: str) -> DivisionState: ...

    @abc.abstractmethod
    def upsert_division_state(self, state: DivisionState) -> None: ...

    @abc.abstractmethod
    def recent_outcomes(self, division: str | None = None, limit: int = 200) -> list[ResolvedOutcome]: ...

    @abc.abstractmethod
    def save_open_position(self, position: OpenPosition) -> None: ...

    @abc.abstractmethod
    def open_positions(self) -> list[OpenPosition]: ...

    @abc.abstractmethod
    def close_position(self, decision_id: str) -> None: ...

    @abc.abstractmethod
    def get_model_params(self, division: str) -> dict | None:
        """Persisted model coefficients for a division, or None if never re-fit."""
        ...

    @abc.abstractmethod
    def save_model_params(self, division: str, params: dict) -> None: ...

    @abc.abstractmethod
    def save_performance(self, snapshot: dict) -> None: ...

    @abc.abstractmethod
    def save_weekly_report(self, report: str, payload: dict) -> None: ...

    @abc.abstractmethod
    def audit(self, event: str, payload: dict) -> None: ...

    @abc.abstractmethod
    def get_system_state(self) -> dict: ...

    @abc.abstractmethod
    def set_system_state(self, reserve_cad: float, hwm_cad: float) -> None: ...

    @abc.abstractmethod
    def set_live_armed(self, armed: bool) -> None:
        """Persist whether the system is armed for live trading.

        Durable (DB-backed) so the dashboard reflects live configuration even
        before any live trade executes, and across redeploys.
        """
        ...

    @abc.abstractmethod
    def claim_next_run_request(self) -> dict | None:
        """Claim the oldest pending on-demand run request (status -> running).

        Returns the claimed row, or None if none are pending. Used by the local
        poller so a dashboard "Run now" click triggers a checkpoint on the PC.
        """
        ...

    @abc.abstractmethod
    def complete_run_request(
        self, request_id: int, status: str, result: dict, decision_id: str | None = None
    ) -> None:
        """Mark a claimed run request done/error with a result summary."""
        ...

    @abc.abstractmethod
    def save_strategy_review(
        self, headline: str, narrative: str, recommendations: list, standing: dict
    ) -> None: ...

    @abc.abstractmethod
    def recent_strategy_reviews(self, limit: int = 10) -> list[dict]: ...


@dataclass
class InMemoryRepository(Repository):
    """Non-persistent repo for dry-run and tests."""

    pitches: list[Pitch] = field(default_factory=list)
    decisions: list[tuple[Decision, list[dict]]] = field(default_factory=list)
    outcomes: list[ResolvedOutcome] = field(default_factory=list)
    positions: dict[str, OpenPosition] = field(default_factory=dict)
    model_params: dict[str, dict] = field(default_factory=dict)
    states: dict[str, DivisionState] = field(default_factory=dict)
    performance: list[dict] = field(default_factory=list)
    weekly: list[tuple[str, dict]] = field(default_factory=list)
    audit_log: list[tuple[str, dict]] = field(default_factory=list)
    system_state: dict = field(
        default_factory=lambda: {"reserve_cad": 0.0, "hwm_cad": 0.0, "live_armed": False}
    )
    strategy_reviews: list[dict] = field(default_factory=list)
    run_requests: list[dict] = field(default_factory=list)

    def save_pitch(self, pitch: Pitch) -> None:
        self.pitches.append(pitch)

    def save_decision(self, decision: Decision, ranking: list[dict]) -> None:
        self.decisions.append((decision, ranking))

    def save_outcome(self, outcome: ResolvedOutcome) -> None:
        self.outcomes.append(outcome)
        st = self.get_division_state(outcome.division.value)
        st.alpha += 1.0 if outcome.win else 0.0
        st.beta += 0.0 if outcome.win else 1.0
        st.n_resolved += 1
        st.net_vs_floor_cad += outcome.pnl_cad - outcome.cost_cad
        self.upsert_division_state(st)

    def get_division_state(self, division: str) -> DivisionState:
        return self.states.setdefault(division, DivisionState(division=division))

    def upsert_division_state(self, state: DivisionState) -> None:
        self.states[state.division] = state

    def recent_outcomes(self, division: str | None = None, limit: int = 200) -> list[ResolvedOutcome]:
        rows = [o for o in self.outcomes if division is None or o.division.value == division]
        return rows[-limit:]

    def save_open_position(self, position: OpenPosition) -> None:
        self.positions[position.decision_id] = position

    def open_positions(self) -> list[OpenPosition]:
        return list(self.positions.values())

    def close_position(self, decision_id: str) -> None:
        self.positions.pop(decision_id, None)

    def get_model_params(self, division: str) -> dict | None:
        return self.model_params.get(division)

    def save_model_params(self, division: str, params: dict) -> None:
        self.model_params[division] = dict(params)

    def save_performance(self, snapshot: dict) -> None:
        self.performance.append(snapshot)

    def save_weekly_report(self, report: str, payload: dict) -> None:
        self.weekly.append((report, payload))

    def audit(self, event: str, payload: dict) -> None:
        self.audit_log.append((event, payload))

    def get_system_state(self) -> dict:
        return dict(self.system_state)

    def set_system_state(self, reserve_cad: float, hwm_cad: float) -> None:
        self.system_state = {
            "reserve_cad": reserve_cad,
            "hwm_cad": hwm_cad,
            "live_armed": self.system_state.get("live_armed", False),
        }

    def set_live_armed(self, armed: bool) -> None:
        self.system_state["live_armed"] = bool(armed)

    def claim_next_run_request(self) -> dict | None:
        for req in self.run_requests:
            if req.get("status") == "pending":
                req["status"] = "running"
                return dict(req)
        return None

    def complete_run_request(
        self, request_id: int, status: str, result: dict, decision_id: str | None = None
    ) -> None:
        for req in self.run_requests:
            if req.get("id") == request_id:
                req["status"] = status
                req["result"] = result
                req["decision_id"] = decision_id
                return

    def save_strategy_review(
        self, headline: str, narrative: str, recommendations: list, standing: dict
    ) -> None:
        self.strategy_reviews.append(
            {
                "headline": headline,
                "narrative": narrative,
                "recommendations": recommendations,
                "standing": standing,
            }
        )

    def recent_strategy_reviews(self, limit: int = 10) -> list[dict]:
        return self.strategy_reviews[-limit:]


def get_repository() -> Repository:
    """Supabase repo if configured, else in-memory."""
    settings = get_settings()
    if settings.supabase_configured():
        from boardroom.persistence.supabase_repo import SupabaseRepository

        return SupabaseRepository()
    return InMemoryRepository()
