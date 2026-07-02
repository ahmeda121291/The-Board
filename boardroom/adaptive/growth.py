"""The growth ladder — equity milestones, measured every checkpoint. Signals only.

The portfolio is already re-measured at every checkpoint (``settle_and_ratchet``
marks equity to deposits + realized P&L). This module turns that measurement
into a named TIER — a PURE, deterministic map from total equity (investable +
protected reserve, so the ratchet sweeping gains can never demote the system)
to where the account stands and what it has earned next.

The ladder changes NO trading behavior. Sizing already scales through the
percent-of-portfolio caps and the CEO aggression schedule; scanning is already
universe-wide. What the ladder adds is the *requires_human* signal layer:
each checkpoint audits a ``growth_tier`` event and the session carries the
tier, so the audit trail and dashboard show which future capabilities the
equity now justifies building/enabling:

- ``intraday_tick_exits_eligible`` — exits currently evaluate on daily closes
  at checkpoints; tick-level stop/take-profit monitoring is the flagged upgrade.
- ``surge_entries_eligible`` — entries currently happen only at the scheduled
  checkpoints; intraday surge-entry scanning is the flagged upgrade.

Both need code/scheduler changes outside the agents' reach and are NEVER
auto-enabled: crossing a threshold makes the feature worth the fee drag; it
does not conjure it into existence.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GrowthTier:
    index: int
    name: str
    min_equity_cad: float                # inclusive lower bound
    milestone: str                       # what this rung means, in one line
    intraday_tick_exits_eligible: bool   # tick-level exit monitoring (requires_human)
    surge_entries_eligible: bool         # intraday surge entries (requires_human)


#: Ascending by ``min_equity_cad``; ``tier_for`` picks the highest bound met.
#: The $500/$5,000 rungs deliberately match the CEO aggression schedule
#: (AGGRESSIVE_BELOW_CAD / CONSERVATIVE_ABOVE_CAD) so the ladder narrates the
#: same ramp the sizing already rides.
TIERS: tuple[GrowthTier, ...] = (
    GrowthTier(0, "seed", 0.0,
               "max aggression — low CEO bar, bold Event cap, compounding the seed",
               False, False),
    GrowthTier(1, "sprout", 500.0,
               "aggression taper begins — the CEO bar starts rising with equity",
               False, False),
    GrowthTier(2, "sapling", 1000.0,
               "book supports steadier sizing — caps now resolve to meaningful CAD",
               False, False),
    GrowthTier(3, "grove", 2500.0,
               "intraday tick-level exits are now worth their cost — human call to build",
               True, False),
    GrowthTier(4, "canopy", 5000.0,
               "fully conservative bar — intraday surge entries eligible, human call",
               True, True),
)


def tier_for(equity_cad: float) -> GrowthTier:
    """The highest tier whose threshold ``equity_cad`` meets. Pure and total."""
    eq = max(0.0, equity_cad)
    current = TIERS[0]
    for t in TIERS:
        if eq >= t.min_equity_cad:
            current = t
    return current


def tier_payload(tier: GrowthTier, equity_cad: float) -> dict:
    """The audit/session record of the checkpoint's tier — what the dashboard renders."""
    nxt = TIERS[tier.index + 1] if tier.index + 1 < len(TIERS) else None
    return {
        "tier": tier.name,
        "index": tier.index,
        "equity_cad": round(equity_cad, 2),
        "milestone": tier.milestone,
        "intraday_tick_exits_eligible": tier.intraday_tick_exits_eligible,
        "surge_entries_eligible": tier.surge_entries_eligible,
        "next_tier": nxt.name if nxt else None,
        "next_tier_at_cad": nxt.min_equity_cad if nxt else None,
    }
