"""Sizing resolves against the LIVE venue book, so deposits are picked up
automatically — no STARTING_PORTFOLIO_CAD edit after topping up the account."""

from __future__ import annotations

from boardroom.factory import build_default_org
from boardroom.persistence.repository import InMemoryRepository
from boardroom.schemas import Venue


class _FakeKraken:
    """Looks like a live broker (not a StubBroker) with a readable book."""

    def __init__(self, cash: float, holdings: list[dict]):
        self._cash, self._holdings = cash, holdings

    def get_cash_cad(self) -> float:
        return self._cash

    def get_positions(self) -> list[dict]:
        return self._holdings

    def assert_no_withdrawal(self) -> None:  # Orchestrator invariant hook
        pass


def _org_with_book(repo, cash: float, holdings: list[dict]):
    org = build_default_org(data_mode="synthetic", repo=repo)
    org.brokers[Venue.KRAKEN] = _FakeKraken(cash, holdings)
    return org


def test_deposits_flow_into_sizing_automatically():
    repo = InMemoryRepository()
    org = _org_with_book(
        repo, cash=300.0, holdings=[{"market_value_cad": 197.0}, {"market_value_cad": None}]
    )
    org.run_once()  # no explicit portfolio — must read the venue

    _, session = repo.decisions[-1]
    # 300 cash + 197 priced holdings (unpriced counts 0) = 497, reserve 0.
    assert abs(session["portfolio_value_cad"] - 497.0) < 1e-6
    # The live HWM advanced for the drawdown breaker.
    assert repo.get_system_state().get("equity_hwm_cad") == 497.0


def test_reserve_stays_out_of_reach_of_live_sizing():
    repo = InMemoryRepository()
    repo.system_state["reserve_cad"] = 50.0
    org = _org_with_book(repo, cash=300.0, holdings=[])
    org.run_once()
    _, session = repo.decisions[-1]
    assert abs(session["portfolio_value_cad"] - 250.0) < 1e-6  # 300 - 50 reserve


def test_unreadable_venue_falls_back_to_baseline():
    class _Broken(_FakeKraken):
        def get_cash_cad(self):
            raise RuntimeError("venue down")

    repo = InMemoryRepository()
    org = build_default_org(data_mode="synthetic", repo=repo)
    org.brokers[Venue.KRAKEN] = _Broken(0, [])
    org.run_once()
    _, session = repo.decisions[-1]
    # Baseline: STARTING_PORTFOLIO_CAD + realized P&L (no outcomes yet).
    assert abs(session["portfolio_value_cad"] - org.settings.starting_portfolio_cad) < 1e-6


def test_stub_broker_never_pretends_to_be_a_live_book():
    repo = InMemoryRepository()
    org = build_default_org(data_mode="synthetic", repo=repo)  # stub brokers
    assert org.live_investable_cad() is None