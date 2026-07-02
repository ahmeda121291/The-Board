"""Growth ladder — equity milestones as signals only (scope §4)."""

from __future__ import annotations

from boardroom.adaptive.growth import TIERS, tier_for, tier_payload
from boardroom.factory import build_default_org
from boardroom.persistence.repository import InMemoryRepository


def test_tier_boundaries():
    assert tier_for(0.0).name == "seed"
    assert tier_for(200.0).name == "seed"
    assert tier_for(499.99).name == "seed"
    assert tier_for(500.0).name == "sprout"
    assert tier_for(1000.0).name == "sapling"
    assert tier_for(2500.0).intraday_tick_exits_eligible
    assert not tier_for(2500.0).surge_entries_eligible
    top = tier_for(10_000.0)
    assert top.intraday_tick_exits_eligible and top.surge_entries_eligible


def test_negative_equity_is_floor_tier():
    assert tier_for(-50.0).name == "seed"


def test_tiers_only_ever_unlock():
    for lo, hi in zip(TIERS, TIERS[1:]):
        assert hi.min_equity_cad > lo.min_equity_cad
        # Eligibility never regresses as equity thresholds rise.
        assert hi.intraday_tick_exits_eligible >= lo.intraday_tick_exits_eligible
        assert hi.surge_entries_eligible >= lo.surge_entries_eligible


def test_tier_payload_points_at_next_unlock():
    p = tier_payload(tier_for(200.0), 200.0)
    assert p["tier"] == "seed"
    assert p["next_tier"] == "sprout"
    assert p["next_tier_at_cad"] == 500.0
    assert p["intraday_tick_exits_eligible"] is False
    assert p["surge_entries_eligible"] is False
    top = tier_payload(TIERS[-1], 9999.0)
    assert top["next_tier"] is None and top["next_tier_at_cad"] is None


def test_ladder_rungs_match_the_aggression_schedule():
    # The $500/$5,000 rungs narrate the same ramp the CEO sizing already rides.
    from boardroom.config import get_settings

    s = get_settings()
    assert TIERS[1].min_equity_cad == s.aggressive_below_cad
    assert TIERS[-1].min_equity_cad == s.conservative_above_cad


def test_run_once_audits_tier_and_carries_it_in_the_session():
    repo = InMemoryRepository()
    org = build_default_org(data_mode="synthetic", repo=repo)
    org.run_once(portfolio_value_cad=200.0)

    audits = [p for e, p in repo.audit_log if e == "growth_tier"]
    assert audits and audits[-1]["tier"] == "seed"
    assert audits[-1]["surge_entries_eligible"] is False
    assert audits[-1]["next_tier_at_cad"] == 500.0

    _, session = repo.decisions[-1]
    assert session["growth_tier"]["tier"] == "seed"


def test_run_once_tier_rises_with_equity():
    repo = InMemoryRepository()
    org = build_default_org(data_mode="synthetic", repo=repo)
    org.run_once(portfolio_value_cad=6000.0)
    audits = [p for e, p in repo.audit_log if e == "growth_tier"]
    assert audits[-1]["tier"] == "canopy"
    assert audits[-1]["intraday_tick_exits_eligible"] is True
    assert audits[-1]["surge_entries_eligible"] is True
