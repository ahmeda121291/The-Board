"""Executability gate: a coin with no CAD market on Kraken never eats a
funding slot (UNIUSD burned three before this gate existed)."""

from __future__ import annotations

import datetime as dt
import uuid

from boardroom.brokers.kraken import exec_pair_for
from boardroom.config import Settings
from boardroom.factory import build_default_org
from boardroom.persistence.repository import InMemoryRepository
from boardroom.schemas import ComputedSignals, DataSnapshot, Division, Pitch, Venue

CAD_PAIRS = frozenset({"XBTCAD", "ETHCAD", "SOLCAD", "XRPCAD", "ADACAD"})


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


def _org(repo, pitches, cad_pair_lookup):
    org = build_default_org(
        data_mode="synthetic",
        repo=repo,
        settings=Settings(_env_file=None),
        cad_pair_lookup=cad_pair_lookup,
    )
    org.gather_pitches = lambda pv: list(pitches)
    org.risk_review = lambda ps, pv: (list(ps), {})
    return org


def test_exec_pair_translation():
    assert exec_pair_for("UNIUSD") == "UNICAD"
    assert exec_pair_for("XBTUSD") == "XBTCAD"
    assert exec_pair_for("SOLCAD") == "SOLCAD"  # already correct: unchanged


def test_no_cad_market_never_eats_a_funding_slot():
    repo = InMemoryRepository()
    # UNI has the better edge but no CAD market; SOL is executable.
    uni, sol = _pitch("UNIUSD", er=0.09), _pitch("SOLUSD", er=0.05)
    org = _org(repo, [uni, sol], cad_pair_lookup=lambda: CAD_PAIRS)
    result = org.run_once(portfolio_value_cad=200.0)

    assert result.decision.kind.value == "fund"
    assert result.decision.pitch_id == sol.pitch_id, "the slot goes to the executable coin"

    skips = [p for e, p in repo.audit_log if e == "no_cad_market_skip"]
    assert len(skips) == 1
    assert skips[0]["symbol"] == "UNIUSD" and skips[0]["exec_pair"] == "UNICAD"

    # The session tells the human WHY the better-scoring idea wasn't funded.
    _, session = repo.decisions[0]
    uni_row = next(r for r in session["pitches"] if r["symbol"] == "UNIUSD")
    assert uni_row["status"] == "passed"
    assert "no CAD market" in uni_row["reason"]


def test_gate_fails_open_when_lookup_unavailable():
    # Lookup returns None (Kraken API down) -> no filtering, execution still
    # errors cleanly downstream, exactly the pre-gate behavior.
    repo = InMemoryRepository()
    uni = _pitch("UNIUSD", er=0.09)
    org = _org(repo, [uni], cad_pair_lookup=lambda: None)
    result = org.run_once(portfolio_value_cad=200.0)

    assert result.decision.pitch_id == uni.pitch_id  # still funded (stub broker fills)
    assert not [e for e, _ in repo.audit_log if e == "no_cad_market_skip"]


def test_gate_absent_in_synthetic_mode_by_default():
    org = build_default_org(data_mode="synthetic", repo=InMemoryRepository())
    assert org.cad_pair_lookup is None, "synthetic/test runs must never touch the network"
