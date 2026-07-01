"""Crypto-first milestone: equities sunset, per-asset aggregate exposure cap,
and multi-idea funding per checkpoint (diversification, not winner-take-all)."""

from __future__ import annotations

import datetime as dt
import uuid

from boardroom.config import Settings
from boardroom.factory import build_default_org
from boardroom.graph.decision_loop import _base_asset
from boardroom.persistence.repository import InMemoryRepository, OpenPosition
from boardroom.schemas import (
    ComputedSignals,
    DataSnapshot,
    DecisionKind,
    Division,
    Pitch,
    Venue,
)


def _pitch(symbol: str, er: float = 0.05, capital: float = 20.0) -> Pitch:
    snap = DataSnapshot(
        symbol=symbol, venue=Venue.KRAKEN, as_of=dt.datetime.now(dt.timezone.utc),
        age_seconds=10, is_fresh=True, rows=60, content_hash="h", source="test",
    )
    sig = ComputedSignals(
        features={"volatility": 0.02}, model_name="m", model_version="v0",
        expected_return=er, win_probability=0.7, raw_confidence=0.7, horizon_days=5.0,
    )
    return Pitch(
        pitch_id=str(uuid.uuid4()), division=Division.EVENT, venue=Venue.KRAKEN,
        symbol=symbol, snapshot=snap, signals=sig, capital_required=capital,
        expected_return=er, confidence=0.7, time_horizon_days=5.0,
        max_loss=capital * 0.06, expected_cost=0.1,
    )


def _open_pos(symbol: str, size: float) -> OpenPosition:
    return OpenPosition(
        decision_id=str(uuid.uuid4()), division="crypto_trend", venue="kraken",
        symbol=symbol, size_cad=size, predicted_return=0.02, predicted_confidence=0.6,
        cost_cad=0.1, stop_fraction=0.05, band_low=-0.1, band_high=0.15,
        horizon_days=5.0, opened_at=dt.datetime.now(dt.timezone.utc), live=True, qty=0.1,
    )


def _org(repo, pitches, **settings_kwargs):
    """A synthetic org whose checkpoint considers exactly ``pitches``."""
    org = build_default_org(
        data_mode="synthetic",
        repo=repo,
        settings=Settings(_env_file=None, **settings_kwargs),
    )
    org.gather_pitches = lambda pv: list(pitches)
    org.risk_review = lambda ps, pv: (list(ps), {})
    return org


def test_base_asset_strips_quotes():
    assert _base_asset("SOLUSD") == "SOL"
    assert _base_asset("SOLCAD") == "SOL"
    assert _base_asset("PEPEUSDT") == "PEPE"
    assert _base_asset("XBTUSDC") == "XBT"


# ---- equities sunset -----------------------------------------------------------

def test_equities_sunset_by_default():
    org = build_default_org(data_mode="synthetic", repo=InMemoryRepository())
    names = [type(d).__name__ for d in org.divisions]
    assert "DirectionalDivision" not in names, "equities are sunset by default"
    assert "CryptoTrendDivision" in names and "EventDivision" in names
    # Momentum survives but hunts crypto only.
    momentum = next(d for d in org.divisions if type(d).__name__ == "MomentumDivision")
    assert all(s.endswith(("USD", "USDT", "USDC")) for s in momentum.universe_symbols or [])


def test_enable_equities_resurrects_the_stock_leg():
    org = build_default_org(
        data_mode="synthetic",
        repo=InMemoryRepository(),
        settings=Settings(_env_file=None, ENABLE_EQUITIES=True),
    )
    names = [type(d).__name__ for d in org.divisions]
    assert "DirectionalDivision" in names


def test_no_recommendations_generated_when_sunset():
    repo = InMemoryRepository()
    org = _org(repo, [])
    org.run_once(portfolio_value_cad=250.0)
    assert repo.latest_recommendation() is None


# ---- per-asset aggregate exposure cap ----------------------------------------------

def test_asset_cap_diverts_capital_to_next_best_idea():
    repo = InMemoryRepository()
    # SOL already holds 20% of a $250 book ($50) — at the cap.
    repo.save_open_position(_open_pos("SOLUSD", 25.0))
    repo.save_open_position(_open_pos("SOLCAD", 25.0))

    sol = _pitch("SOLUSD", er=0.06)   # best idea, but capped out
    eth = _pitch("ETHUSD", er=0.04)   # next best — should get the capital
    org = _org(repo, [sol, eth], MAX_FUNDINGS_PER_CHECKPOINT=1)

    result = org.run_once(portfolio_value_cad=250.0)

    assert result.decision.kind == DecisionKind.FUND
    funded = next(p for p in result.pitches if p.pitch_id == result.decision.pitch_id)
    assert funded.symbol == "ETHUSD", "capped SOL must step aside for the next-best coin"
    assert any(e == "asset_cap_skip" for e, _ in repo.audit_log)
    # The session explains WHY SOL was passed over.
    _, session = repo.decisions[0]
    sol_row = next(r for r in session["pitches"] if r["symbol"] == "SOLUSD")
    assert "asset exposure cap" in sol_row["reason"]


def test_below_cap_rebuying_is_still_allowed():
    repo = InMemoryRepository()
    repo.save_open_position(_open_pos("SOLUSD", 25.0))  # 10% of book — below the 20% cap
    org = _org(repo, [_pitch("SOLUSD", er=0.06)], MAX_FUNDINGS_PER_CHECKPOINT=1)
    result = org.run_once(portfolio_value_cad=250.0)
    assert result.decision.kind == DecisionKind.FUND, "no hard no-rebuy rule — value is value"


# ---- multi-idea funding per checkpoint -----------------------------------------------

def test_funds_two_different_assets_in_one_checkpoint():
    repo = InMemoryRepository()
    org = _org(
        repo,
        [_pitch("SOLUSD", er=0.06), _pitch("ETHUSD", er=0.05), _pitch("XBTUSD", er=0.001)],
        MAX_FUNDINGS_PER_CHECKPOINT=2,
    )
    org.run_once(portfolio_value_cad=250.0)

    funded_symbols = []
    for d, _ in repo.decisions:
        if d.kind == DecisionKind.FUND and d.pitch_id:
            funded_symbols.append(d.pitch_id)
    assert len(funded_symbols) == 2, "two ideas clear the bar → two fundings"
    assert len(repo.open_positions()) == 2
    assets = {_base_asset(p.symbol) for p in repo.open_positions()}
    assert assets == {"SOL", "ETH"}, "second slot goes to a DIFFERENT asset"


def test_same_asset_not_funded_twice_in_one_checkpoint():
    repo = InMemoryRepository()
    # Two divisions both pitch SOL; only one SOL lot may open per checkpoint.
    org = _org(
        repo,
        [_pitch("SOLUSD", er=0.06), _pitch("SOLUSD", er=0.05)],
        MAX_FUNDINGS_PER_CHECKPOINT=2,
    )
    org.run_once(portfolio_value_cad=250.0)
    assert len(repo.open_positions()) == 1
