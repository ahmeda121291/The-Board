"""Conviction sizing — size by edge x trust-adjusted-confidence, capped by the
risk envelope (scope §4). Equal sizing is forbidden; the variance of position
size is how the CEO expresses judgment. Event is always hard-capped.

This is a fractional-Kelly style sizer kept deliberately timid (a fraction of
Kelly) because at a $200 account, ruin is the dominant risk.
"""

from __future__ import annotations

from boardroom.config import RiskCaps
from boardroom.schemas import Division


def conviction_size(
    *,
    division: Division,
    edge: float,                 # expected fractional excess return over the floor
    win_probability: float,      # trust-adjusted, [0,1]
    risk_unit_fraction: float,   # fractional loss if the stop is hit (>0)
    caps: RiskCaps,
    deployed_cad: float,
    portfolio_value_cad: float,  # current total portfolio value (caps resolve against this)
    leash: float = 1.0,          # per-division risk leash in [0, 1]
    kelly_fraction: float = 0.25,
) -> float:
    """Return the CAD size for a position, already clamped to the hard caps.

    Uses a fraction of the Kelly bet: ``f* = edge / risk_unit``, scaled by the
    win probability, the leash, and ``kelly_fraction``, applied to the current
    portfolio value. Then clamped to the per-division/per-trade cap, the
    deployable headroom, and (for Event) the hard cap — all PERCENTAGES of
    portfolio value, so the dollar ceilings scale as the account grows. Returns
    0.0 if the edge is non-positive.
    """
    if edge <= 0 or risk_unit_fraction <= 0 or win_probability <= 0:
        return 0.0

    # Fraction of portfolio to risk, before caps.
    kelly = (edge / risk_unit_fraction) * win_probability
    fraction = max(0.0, kelly) * kelly_fraction * max(0.0, min(1.0, leash))
    size = fraction * max(0.0, portfolio_value_cad)

    # Hard caps the CEO cannot override (percent of portfolio value).
    size = min(size, caps.cap_for(division.value, portfolio_value_cad))

    headroom = max(0.0, caps.deployable_cad(portfolio_value_cad) - deployed_cad)
    size = min(size, headroom)

    return round(max(0.0, size), 2)
