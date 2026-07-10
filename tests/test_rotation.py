"""Capital rotation (owner mandate): a fresh idea that beats the weakest
holding's remaining edge by more than the switching cost takes its money."""

from __future__ import annotations

import datetime as dt
import uuid

from boardroom.config import Settings
from boardroom.factory import build_default_org
from boardroom.persistence.repository import InMemoryRepository, OpenPosition
from boardroom.schemas import ComputedSignals, DataSnapshot, Division, Pitch, Venue


def _pitch(symbol: str, er: float, capital: float = 25.0) -> Pitch:
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


def _pos(symbol: str, *, days_ago: float = 2.0) -> OpenPosition:
    # Paper position (live=False) so the rotation sell closes without a broker.
    return OpenPosition(
        decision_id=str(uuid.uuid4()), division="crypto_trend", venue="kraken",
        symbol=symbol, size_cad=25.0, predicted_return=0.02, predicted_confidence=0.6,
        cost_cad=0.1, stop_fraction=0.30, band_low=-0.4, band_high=0.5,
        horizon_days=5.0, live=False, qty=0.5,
        opened_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days_ago),
    )


def _org(repo, pitches, **settings_kwargs):
    org = build_default_org(
        data_mode="synthetic", repo=repo, settings=Settings(_env_file=None, **settings_kwargs)
    )
    org.gather_pitches = lambda pv: list(pitches)
    org.risk_review = lambda ps, pv: (list(ps), {})
    return org


def test_strong_leftover_idea_rotates_out_the_weakest_holding():
    repo = InMemoryRepository()
    # Hold XBT (the synthetic org fetches XBTUSD, so it can be force-priced).
    # The scan produced NO pitch for XBT today (remaining edge 0). With ONE
    # funding slot, DOT (10%) takes it and UNI (9%) is left over — strong
    # enough to evict the stale XBT holding (1.5× the ~0.17 CAD switch cost).
    repo.save_open_position(_pos("XBTUSD"))
    dot, uni = _pitch("DOTUSD", er=0.10), _pitch("UNIUSD", er=0.09)
    org = _org(repo, [dot, uni], MAX_FUNDINGS_PER_CHECKPOINT="1")
    org.run_once(portfolio_value_cad=200.0)

    held = {p.symbol for p in repo.open_positions()}
    assert "DOTUSD" in held, "the best idea took the normal funding slot"
    assert "UNIUSD" in held and "XBTUSD" not in held, "the leftover idea took XBT's money"
    rot = [p for e, p in repo.audit_log if e == "rotation"]
    assert rot and rot[0]["sold"] == "XBTUSD" and rot[0]["bought"] == "UNIUSD"
    # The forced exit was booked as a real outcome — the loop learns from it.
    assert repo.outcomes and repo.outcomes[-1].symbol == "XBTUSD"


def test_marginal_idea_does_not_churn_the_book():
    repo = InMemoryRepository()
    repo.save_open_position(_pos("XBTUSD"))
    meh = _pitch("UNIUSD", er=0.004)  # ~0.1 CAD of edge on $25 — below the cost bar
    org = _org(repo, [meh])
    org.run_once(portfolio_value_cad=200.0)

    # UNI may be funded with FRESH cash (that's fine) but XBT must not be sold.
    assert not [e for e, _ in repo.audit_log if e == "rotation"]
    assert any(p.symbol == "XBTUSD" for p in repo.open_positions())


def test_rotation_never_swaps_a_coin_for_itself():
    repo = InMemoryRepository()
    repo.save_open_position(_pos("UNIUSD"))
    uni_again = _pitch("UNIUSD", er=0.09)
    org = _org(repo, [uni_again])
    org.run_once(portfolio_value_cad=200.0)
    assert not [e for e, _ in repo.audit_log if e == "rotation"]


def test_rotation_can_be_disabled():
    repo = InMemoryRepository()
    repo.save_open_position(_pos("XBTUSD"))
    uni = _pitch("UNIUSD", er=0.09)
    org = _org(repo, [uni], ENABLE_ROTATION="false")
    org.run_once(portfolio_value_cad=200.0)
    assert not [e for e, _ in repo.audit_log if e == "rotation"]
    assert any(p.symbol == "XBTUSD" for p in repo.open_positions())
