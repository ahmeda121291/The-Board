"""CLI smoke tests — the command paths run end-to-end without crashing.

Guards regressions like the advisory-pitch KeyError: equities carry no risk
challenge, so the `decide` display must look challenges up defensively.
"""

from __future__ import annotations

from boardroom.cli import main


def test_decide_synthetic_runs():
    # Synthetic data, dry-run: exercises gather -> advisory split -> decide ->
    # the pitch/challenge display. Equity pitches have no challenge entry.
    assert main(["decide", "--synthetic"]) == 0


def test_doctor_runs():
    assert main(["doctor"]) == 0


def test_backtest_synthetic_runs():
    assert main(["backtest", "--synthetic"]) == 0
