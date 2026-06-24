"""Repository interface + an in-memory implementation.

The Supabase-backed implementation lives in ``supabase_repo`` and is selected by
``get_repository()`` when SUPABASE_URL/SERVICE_KEY are set. Both share this
interface so the rest of the system never knows which is in play.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field

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
    def save_performance(self, snapshot: dict) -> None: ...

    @abc.abstractmethod
    def save_weekly_report(self, report: str, payload: dict) -> None: ...

    @abc.abstractmethod
    def audit(self, event: str, payload: dict) -> None: ...


@dataclass
class InMemoryRepository(Repository):
    """Non-persistent repo for dry-run and tests."""

    pitches: list[Pitch] = field(default_factory=list)
    decisions: list[tuple[Decision, list[dict]]] = field(default_factory=list)
    outcomes: list[ResolvedOutcome] = field(default_factory=list)
    states: dict[str, DivisionState] = field(default_factory=dict)
    performance: list[dict] = field(default_factory=list)
    weekly: list[tuple[str, dict]] = field(default_factory=list)
    audit_log: list[tuple[str, dict]] = field(default_factory=list)

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

    def save_performance(self, snapshot: dict) -> None:
        self.performance.append(snapshot)

    def save_weekly_report(self, report: str, payload: dict) -> None:
        self.weekly.append((report, payload))

    def audit(self, event: str, payload: dict) -> None:
        self.audit_log.append((event, payload))


def get_repository() -> Repository:
    """Supabase repo if configured, else in-memory."""
    settings = get_settings()
    if settings.supabase_configured():
        from boardroom.persistence.supabase_repo import SupabaseRepository

        return SupabaseRepository()
    return InMemoryRepository()
