"""The hurdle — price everything against the floor.

First move each day: does anything beat carry, risk-adjusted, after cost? Every
pitch is judged as EXCESS return over the floor, per unit of risk, net of
expected transaction cost (scope §4, §8). Without a hurdle, the CEO just picks
the best story.
"""

from __future__ import annotations

from boardroom.schemas import Pitch


def excess_over_floor(pitch: Pitch, hurdle_rate: float) -> float:
    """Fractional return in excess of the floor's carry over the same horizon.

    ``hurdle_rate`` is the floor's expected fractional return for this pitch's
    horizon (already horizon-matched by the caller).
    """
    return pitch.expected_return - hurdle_rate


def risk_adjusted_score(pitch: Pitch, hurdle_rate: float) -> float:
    """The CEO's ranking score: net excess edge per unit of risk.

    Numerator: expected CAD return in excess of the floor, minus expected cost.
    Denominator: the capital at risk (max_loss). Higher is better. A pitch that
    doesn't clear its cost, or doesn't beat the floor, scores <= 0 and will lose
    to the null default.
    """
    excess_fraction = excess_over_floor(pitch, hurdle_rate)
    excess_cad = pitch.capital_required * excess_fraction
    net_excess_cad = excess_cad - pitch.expected_cost
    risk = max(pitch.max_loss, 1e-9)
    return net_excess_cad / risk
