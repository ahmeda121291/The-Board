"""Deterministic tests for the measurement layer (no network, no LLM, no DB)."""

from __future__ import annotations

import math

import pytest

from boardroom.measurement import (
    brier_score,
    buy_and_hold_return,
    calibration_error,
    compare,
    compute_performance,
    critique,
    floor_return,
    tag_process_luck,
)
from boardroom.schemas import Division, ProcessLuckTag, ResolvedOutcome


def make_outcome(
    *,
    decision_id: str = "d",
    division: Division = Division.DIRECTIONAL,
    predicted_return: float = 0.0,
    realized_return: float = 0.0,
    predicted_confidence: float = 0.5,
    win: bool = False,
    pnl_cad: float = 0.0,
    cost_cad: float = 0.0,
    inside_band: bool = True,
    process_luck: ProcessLuckTag | None = None,
) -> ResolvedOutcome:
    return ResolvedOutcome(
        decision_id=decision_id,
        division=division,
        predicted_return=predicted_return,
        realized_return=realized_return,
        predicted_confidence=predicted_confidence,
        win=win,
        pnl_cad=pnl_cad,
        cost_cad=cost_cad,
        inside_band=inside_band,
        process_luck=process_luck,
    )


# --------------------------------------------------------------------------- #
# benchmarks
# --------------------------------------------------------------------------- #


def test_floor_return_known_numbers():
    # 5% APR over half a year ~ 2.5%.
    assert floor_return(0.05, 182.5) == pytest.approx(0.025)
    # A full year of carry equals the APR.
    assert floor_return(0.10, 365) == pytest.approx(0.10)
    assert floor_return(0.0, 100) == 0.0


def test_buy_and_hold_known_numbers():
    assert buy_and_hold_return(100.0, 110.0) == pytest.approx(0.10)
    assert buy_and_hold_return(100.0, 90.0) == pytest.approx(-0.10)
    assert buy_and_hold_return(50.0, 50.0) == 0.0


def test_buy_and_hold_zero_start_raises():
    with pytest.raises(ValueError):
        buy_and_hold_return(0.0, 10.0)


def test_compare_excess_signs():
    # strategy 8% over a period where floor is 2.5% and bnh is 10%.
    cmp = compare(
        strategy_return=0.08,
        carry_apr=0.05,
        days=182.5,
        start_price=100.0,
        end_price=110.0,
    )
    assert cmp.floor_return == pytest.approx(0.025)
    assert cmp.buy_and_hold_return == pytest.approx(0.10)
    # Beat the floor (positive) ...
    assert cmp.excess_vs_floor == pytest.approx(0.055)
    assert cmp.excess_vs_floor > 0
    assert cmp.beat_floor() is True
    # ... but lost to buy-and-hold (negative).
    assert cmp.excess_vs_bnh == pytest.approx(-0.02)
    assert cmp.excess_vs_bnh < 0
    assert cmp.beat_buy_and_hold() is False


# --------------------------------------------------------------------------- #
# performance (the Analyst)
# --------------------------------------------------------------------------- #


def test_compute_performance_basic():
    outcomes = [
        make_outcome(
            decision_id="a",
            division=Division.DIRECTIONAL,
            realized_return=0.10,
            win=True,
            pnl_cad=20.0,
            cost_cad=1.0,
        ),
        make_outcome(
            decision_id="b",
            division=Division.DIRECTIONAL,
            realized_return=-0.05,
            win=False,
            pnl_cad=-10.0,
            cost_cad=1.0,
        ),
        make_outcome(
            decision_id="c",
            division=Division.EVENT,
            realized_return=0.20,
            win=True,
            pnl_cad=15.0,
            cost_cad=2.0,
        ),
    ]
    rpt = compute_performance(
        outcomes,
        carry_apr=0.04,
        period_days=30.0,
        bnh_start=100.0,
        bnh_end=101.0,
        starting_equity_cad=160.0,
    )

    assert rpt.n_outcomes == 3
    # net_roi = (20 - 10 + 15) / 160 = 25/160
    assert rpt.net_roi == pytest.approx(25.0 / 160.0)
    # 2 wins of 3.
    assert rpt.hit_rate == pytest.approx(2.0 / 3.0)
    # attribution by division.value.
    assert rpt.attribution == {
        "directional": pytest.approx(10.0),  # 20 + (-10)
        "event": pytest.approx(15.0),
    }
    # cost drag.
    assert rpt.total_cost_cad == pytest.approx(4.0)
    assert rpt.cost_drag_pct == pytest.approx(4.0 / 160.0)
    # avg win / loss.
    assert rpt.avg_win == pytest.approx((20.0 + 15.0) / 2.0)
    assert rpt.avg_loss == pytest.approx(-10.0)
    # profit factor = (20 + 15) / 10.
    assert rpt.profit_factor == pytest.approx(35.0 / 10.0)
    # benchmark wired through with strategy_return == net_roi.
    assert rpt.benchmark.strategy_return == pytest.approx(rpt.net_roi)
    assert rpt.benchmark.buy_and_hold_return == pytest.approx(0.01)
    # summary_lines is plain text and non-empty.
    lines = rpt.summary_lines()
    assert isinstance(lines, list) and all(isinstance(s, str) for s in lines)
    assert lines


def test_compute_performance_empty():
    rpt = compute_performance(
        [],
        carry_apr=0.04,
        period_days=30.0,
        bnh_start=100.0,
        bnh_end=100.0,
        starting_equity_cad=160.0,
    )
    assert rpt.n_outcomes == 0
    assert rpt.net_roi == 0.0
    assert rpt.hit_rate == 0.0
    assert rpt.attribution == {}
    assert rpt.max_drawdown_cad == 0.0
    assert rpt.sharpe == 0.0


def test_max_drawdown_is_non_positive():
    outcomes = [
        make_outcome(decision_id="1", pnl_cad=10.0),
        make_outcome(decision_id="2", pnl_cad=-30.0),
        make_outcome(decision_id="3", pnl_cad=5.0),
    ]
    rpt = compute_performance(
        outcomes,
        carry_apr=0.0,
        period_days=1.0,
        bnh_start=1.0,
        bnh_end=1.0,
        starting_equity_cad=100.0,
    )
    # Peak 10, trough -20 => drawdown -30.
    assert rpt.max_drawdown_cad == pytest.approx(-30.0)
    assert rpt.max_drawdown_cad <= 0


# --------------------------------------------------------------------------- #
# critic
# --------------------------------------------------------------------------- #


def test_calibration_error_well_vs_badly_calibrated():
    # Perfectly calibrated: confidence 0.5 with exactly half wins -> low ECE.
    confs = [0.5, 0.5, 0.5, 0.5]
    wins = [True, False, True, False]
    well = calibration_error(confs, wins, n_bins=5)
    assert well == pytest.approx(0.0)

    # Badly calibrated: 0.9 confidence but every bet lost -> high ECE (~0.9).
    bad_confs = [0.9, 0.9, 0.9, 0.9]
    bad_wins = [False, False, False, False]
    bad = calibration_error(bad_confs, bad_wins, n_bins=5)
    assert bad == pytest.approx(0.9)
    assert bad > well


def test_calibration_error_empty():
    assert calibration_error([], []) == 0.0


def test_brier_score_perfect_and_worst():
    # Perfect predictions: 1.0 conf when win, 0.0 conf when loss -> 0.
    assert brier_score([1.0, 0.0], [True, False]) == pytest.approx(0.0)
    # Worst predictions: 0.0 conf when win, 1.0 conf when loss -> 1.
    assert brier_score([0.0, 1.0], [True, False]) == pytest.approx(1.0)
    # 0.5 everywhere -> 0.25.
    assert brier_score([0.5, 0.5], [True, False]) == pytest.approx(0.25)


def test_brier_score_empty():
    assert brier_score([], []) == 0.0


def test_tag_process_luck_2x2():
    assert tag_process_luck(good_process=True, win=True) == (
        ProcessLuckTag.GOOD_PROCESS_GOOD_OUTCOME
    )
    assert tag_process_luck(good_process=True, win=False) == (
        ProcessLuckTag.GOOD_PROCESS_BAD_OUTCOME
    )
    assert tag_process_luck(good_process=False, win=True) == (
        ProcessLuckTag.BAD_PROCESS_GOOD_OUTCOME
    )
    assert tag_process_luck(good_process=False, win=False) == (
        ProcessLuckTag.BAD_PROCESS_BAD_OUTCOME
    )


def test_critique_report():
    outcomes = [
        make_outcome(
            decision_id="a",
            predicted_confidence=0.5,
            win=True,
            inside_band=True,
            process_luck=ProcessLuckTag.GOOD_PROCESS_GOOD_OUTCOME,
        ),
        make_outcome(
            decision_id="b",
            predicted_confidence=0.5,
            win=False,
            inside_band=False,
            process_luck=ProcessLuckTag.GOOD_PROCESS_BAD_OUTCOME,
        ),
        make_outcome(
            decision_id="c",
            predicted_confidence=0.5,
            win=True,
            inside_band=True,
            process_luck=ProcessLuckTag.GOOD_PROCESS_GOOD_OUTCOME,
        ),
        make_outcome(
            decision_id="d",
            predicted_confidence=0.5,
            win=False,
            inside_band=True,
            process_luck=None,
        ),
    ]
    rpt = critique(outcomes)
    assert rpt.n_resolved == 4
    # half wins at 0.5 confidence -> perfectly calibrated.
    assert rpt.calibration_error == pytest.approx(0.0)
    assert rpt.brier_score == pytest.approx(0.25)
    # 3 of 4 inside band.
    assert rpt.inside_band_rate == pytest.approx(0.75)
    # only tagged outcomes counted.
    assert rpt.process_luck_counts == {
        "good_process_good_outcome": 2,
        "good_process_bad_outcome": 1,
    }
    assert rpt.summary_lines()


def test_critique_empty():
    rpt = critique([])
    assert rpt.n_resolved == 0
    assert rpt.calibration_error == 0.0
    assert rpt.brier_score == 0.0
    assert rpt.inside_band_rate == 0.0
    assert rpt.process_luck_counts == {}
