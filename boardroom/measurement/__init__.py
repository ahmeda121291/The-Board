"""Measurement: the system's honest mirror (scope §8).

It answers two questions that must never be conflated:

    (A) did the account grow?      -> performance.py  (the Analyst)
    (B) was each decision sound?   -> critic.py       (the Critic)

...and judges every strategy against two hurdles: the FLOOR (carry/yield) and
BUY-AND-HOLD (benchmarks.py). Everything here is pure and deterministic — no
network, no LLM, no DB.
"""

from __future__ import annotations

from .benchmarks import (
    BenchmarkComparison,
    buy_and_hold_return,
    compare,
    floor_return,
)
from .critic import (
    CriticReport,
    brier_score,
    calibration_error,
    critique,
    tag_process_luck,
)
from .performance import PerformanceReport, compute_performance

__all__ = [
    # benchmarks
    "BenchmarkComparison",
    "compare",
    "floor_return",
    "buy_and_hold_return",
    # performance (the Analyst)
    "PerformanceReport",
    "compute_performance",
    # critic (decision quality)
    "CriticReport",
    "critique",
    "tag_process_luck",
    "calibration_error",
    "brier_score",
]
