"""The gains ratchet and the Strategist (CFO) agent."""

from __future__ import annotations

from boardroom.adaptive.ratchet import RatchetState, investable_cad, ratchet_update
from boardroom.agents.strategist import build_recommendations, build_standing, generate_review
from boardroom.persistence.repository import InMemoryRepository


# ---- ratchet ----------------------------------------------------------------
def test_ratchet_no_capture_below_step():
    st = RatchetState(reserve_cad=0.0, hwm_cad=200.0)
    out = ratchet_update(equity_cad=205.0, state=st)  # +5, below 10 step
    assert out.reserve_cad == 0.0
    assert out.hwm_cad == 205.0  # tracks the peak


def test_ratchet_captures_quarter_of_gain():
    st = RatchetState(reserve_cad=0.0, hwm_cad=200.0)
    out = ratchet_update(equity_cad=240.0, state=st)  # +40 gain
    assert out.reserve_cad == 10.0  # 25% of 40
    assert out.hwm_cad == 240.0


def test_ratchet_reserve_only_grows():
    st = RatchetState(reserve_cad=10.0, hwm_cad=240.0)
    out = ratchet_update(equity_cad=210.0, state=st)  # equity dropped
    assert out.reserve_cad == 10.0  # never shrinks
    assert out.hwm_cad == 240.0  # HWM holds


def test_investable_excludes_reserve():
    assert investable_cad(240.0, 10.0) == 230.0
    assert investable_cad(100.0, 150.0) == 0.0  # never negative


# ---- strategist -------------------------------------------------------------
def test_standing_empty_system():
    repo = InMemoryRepository()
    standing = build_standing(repo, 200.0)
    assert standing["equity_cad"] == 200.0
    assert standing["n_resolved_total"] == 0
    assert len(standing["divisions"]) == 6  # yield, directional, event, momentum, crypto_trend, effort


def test_recommendations_low_sample_says_hold():
    repo = InMemoryRepository()
    standing = build_standing(repo, 200.0)
    recs = build_recommendations(standing)
    assert any(r["area"] == "system" and not r["requires_human"] for r in recs)


def test_generate_review_runs_without_llm():
    # No ANTHROPIC key in tests -> templated narrative, still a valid review.
    repo = InMemoryRepository()
    review = generate_review(repo, llm=None, starting_portfolio_cad=200.0)
    assert review.headline
    assert review.narrative
    assert isinstance(review.recommendations, list)
    assert review.standing["equity_cad"] == 200.0
