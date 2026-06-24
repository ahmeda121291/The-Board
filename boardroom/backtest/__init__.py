"""The backtest gate (scope §5). A division's rule may not deploy real capital
until it shows historical edge net of cost. The backtest does double duty: it
also seeds the division's initial calibration prior.
"""

from boardroom.backtest.engine import BacktestResult, backtest_division

__all__ = ["BacktestResult", "backtest_division"]
